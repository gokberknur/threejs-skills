# Shader Cost, Program Churn and WebGPU / TSL Performance (three.js r187)

## When to read this

Read when the GPU is shader-bound (fill rate, expensive materials), when custom shaders or `onBeforeCompile` cause hitches or program counts to grow, when moving simulation / particles to the GPU, when porting from WebGLRenderer to WebGPURenderer, or when choosing between Points, InstancedMesh and compute particles, GPU picking vs raycasting, and morph/skin approaches.

GLSL-level statements about GPU hardware are general graphics knowledge (rule of thumb); API statements were checked against the r186 docs and source; every "in r186" claim was re-checked against r187.

## Table of contents

1. Shader cost basics
2. ShaderMaterial and `onBeforeCompile` pitfalls (WebGLRenderer)
3. Uniform cost and UBOs (`UniformsGroup`)
4. How WebGPURenderer caches programs and pipelines
5. TSL performance rules
6. Uniform groups in TSL
7. Compute, storage buffers and instancing (WebGPU)
8. Avoiding readbacks
9. Indirect draws, render bundles, `static`
10. Compilation: `compileAsync`, `compileComputeAsync`
11. Morph targets and skinning
12. Particles: Points vs InstancedMesh vs compute
13. GPU picking vs raycasting
14. BVH and spatial structures
15. Timestamps and profiling
16. See also

---

## 1. Shader cost basics

Fragment shaders run per covered pixel per layer; vertex shaders per vertex per instance. The expensive resources, roughly in order, are: memory bandwidth (texture fetches, render target reads/writes, overdraw), dependent texture reads, transcendental math (pow, exp, sin, normalize chains), and divergent branching. Reduce work, then reduce how often it runs.

Rules of thumb:

- ALU vs texture fetch: modern GPUs hide texture latency by switching to other threads, so many independent fetches are fine; fetches whose coordinates depend on the previous fetch result (dependent reads, e.g. noise-of-noise, parallax occlusion loops, refraction offsets) cannot be hidden and stall. Compute UVs in the vertex stage and let the hardware interpolate them (varyings) so the fragment stage's fetch address is known early. In TSL: `vertexStage(node)` (alias of `varying`) moves a computation to the vertex shader; `positionGeometry.toVarying(name)` is the same idea.
- Move work up the pipeline: per-object -> CPU or uniform; per-vertex -> vertex shader; per-pixel -> only what must vary per pixel. Per-pixel normalize/pow on values that are smooth across a triangle can be done per vertex and interpolated.
- Texture sampling cost: filtering mode matters (trilinear 8 texels, anisotropic multiplies samples, see `textures-and-memory.md`). Use `textureLoad` (no sampler / no filtering; TSL: `textureLoad = texture(...).setSampler(false)`) for data textures with integer coordinates. Cubemap and 3D textures cost more bandwidth than 2D. Pack channels (ORM) and use smaller formats.
- Branching: GPUs execute in lockstep groups (warps / waves). A branch whose condition is uniform across the group (a uniform flag) is nearly free; a divergent branch executes both sides for threads in a group that disagree. Prefer uniform-driven branches, or arithmetic selection (`mix`/`step`) when both sides are cheap. In TSL `If(cond, () => {...})` is a real branch; `select(cond, a, b)` and `mix` evaluate both operands (rule of thumb: ternary-like).
- Loops with a data-dependent trip count (raymarching, many-light loops, blur kernels) multiply cost. Use fixed small counts, early-out on uniform conditions, and lower resolution for the pass.
- Precision: `precision: 'mediump'` (renderer option or `material.precision`, WebGLRenderer) can be faster on mobile GPUs, with visible artifacts if used for positions, large UVs or accumulations; `highp` is default. WebGPU has f32 and optionally f16 (feature dependent) with no per-material precision setting in three.js.
- Overdraw multiplies everything: see `rendering-strategies.md` sections 8 and 9.
- Alpha tested / discarding shaders and shaders that write depth (`gl_FragDepth`, `logarithmicDepthBuffer`) defeat early-z (documented for the log depth option in `WebGLRenderer.md`).
- Built-in material cost ladder (rule of thumb, cheapest first): `MeshBasicMaterial` < `MeshLambertMaterial` (per-vertex or simple) < `MeshPhongMaterial` < `MeshToonMaterial` < `MeshStandardMaterial` < `MeshPhysicalMaterial` (feature branches such as clearcoat, sheen, transmission, iridescence are compiled only when enabled, but are costly when on; transmission renders an extra pass).
- Cost scales with the number of lights evaluated per fragment (see `rendering-strategies.md` section 7).

---

## 2. ShaderMaterial and `onBeforeCompile` pitfalls (WebGLRenderer)

Program identity: three.js hashes the material's shader-affecting parameters (type, defines, maps present, lights count, fog, vertex colors, skinning, morph, instancing, tone mapping, color space, shadow flags, `customProgramCacheKey()`, and so on) and reuses an existing `WebGLProgram` for identical hashes (manual: "three.js tries to reuse existing shader programs"). Compiling is the expensive step (tens of ms, longer on Windows/ANGLE per the manual).

Things that force a new program or recompile:

1. Changing any of the following after first render, then `material.needsUpdate = true` (from the manual `how-to-update-things`): number/type of uniforms, presence of a texture, fog, vertex colors, morphing, shadow map, alpha test, `transparent`. Fix: use dummy values instead (white texture, zero-intensity light, zero-density fog) so the program stays identical.
2. Changing `material.defines` (a `ShaderMaterial` feature): defines are part of the program key; each distinct value is a new program. Do not drive animation with defines; use uniforms.
3. `onBeforeCompile` (WebGLRenderer only): the callback modifies shader source before compile. `Material.customProgramCacheKey()` defaults to `this.onBeforeCompile.toString()` (source: `Material.js`), so the program key includes the function text. Two materials whose callbacks have the same text but different closure state (for example a different injected constant) share one program and one of them renders wrong; override `customProgramCacheKey()` to return a string that identifies the variant:
   ```js
   const timeUniform = { value: 0 };
   const mat = new THREE.MeshStandardMaterial();
   mat.onBeforeCompile = (shader) => {
     shader.uniforms.uTime = timeUniform;                 // share one uniform object across materials
     shader.vertexShader = shader.vertexShader.replace(
       '#include <begin_vertex>',
       '#include <begin_vertex>\n transformed.y += sin(uTime + position.x) * 0.1;'
     );
   };
   mat.customProgramCacheKey = () => 'wave-v1';           // identify the variant
   ```
   Pitfalls: variants that differ only in closure state need distinct keys; include names (`#include <begin_vertex>`) can change between releases (re-test after upgrading); keep a reference to the uniform object you inject (`timeUniform.value = t`), because the shader compiles once and reads that object later.
4. A new material per object with the same parameters is fine for compilation (programs are shared) but each material has its own uniform set to upload and its own `id` in the sort key (extra state changes). Share material instances.
5. Pre-compile with the real configuration (`renderer.compileAsync(scene, camera)`), see `draw-calls-and-geometry.md` section 14.
6. Lights: adding or removing lights, or toggling `castShadow` after first render, changes the lights state hash; every lit material recompiles. Keep counts constant (fade intensity instead).
7. `InstancedMesh.setColorAt` for the first time (creates `instanceColor`) or `BatchedMesh.setColorAt` after first render also switches the program.
8. `renderer.debug.checkShaderErrors = false` in production skips status queries after compile (documented performance gain); keep on in development.
9. `WebGLRenderer` programs list: `renderer.info.programs.length`. A steadily growing number is the symptom of the problems above.

`ShaderMaterial` uniforms: `uniforms.foo.value` changes are uploaded when the material is used in a draw (no flag needed except for arrays you mutate on some structures; `material.uniformsNeedUpdate` for edge cases). Uploading hundreds of uniforms per object per frame costs CPU; the next section addresses that.

WebGPURenderer note (manual `webgpurenderer`): custom `ShaderMaterial`, `RawShaderMaterial` and `onBeforeCompile()` are NOT supported there; port to node materials and TSL. `EffectComposer` is not supported either; use `RenderPipeline`.

---

## 3. Uniform cost and UBOs (`UniformsGroup`, WebGL2)

In WebGL each program has its own uniforms uploaded by `gl.uniform*` calls whenever the program/material changes or values change. Shared data (camera matrices, lighting parameters, time) is re-uploaded per material even though it is identical.

`UniformsGroup` maps a set of `Uniform`s to a Uniform Buffer Object that can be shared by many `ShaderMaterial`s: update once, bind everywhere.

```js
const camData = new THREE.UniformsGroup();
camData.setName('ViewData');                                   // must match the GLSL uniform block name
camData.add(new THREE.Uniform(camera.projectionMatrix));       // order and std140 layout matter
camData.add(new THREE.Uniform(camera.matrixWorldInverse));

material.uniformsGroups = [camData];

// GLSL (ShaderMaterial, glslVersion = THREE.GLSL3):
// layout(std140) uniform ViewData { mat4 projectionMatrix; mat4 viewMatrix; };
```

- Only for `ShaderMaterial` and so only for WebGLRenderer (`UniformsGroup.md`: "only supported in WebGLRenderer"); `webgl_ubo.html` and `webgl_ubo_arrays.html` are the examples.
- Worth it when many materials share the same large block. For a handful of materials, plain uniforms are fine.
- In WebGPURenderer the equivalent mechanism is built in: uniform buffers per group (section 6).
- Cheaper per-frame uniform updates in general: update a `Vector3`/`Matrix4` value in place (no new objects), update only on change, keep array uniforms small, and avoid per-object uniform changes where instancing could carry the data in an attribute.

---

## 4. How WebGPURenderer caches programs and pipelines

(Source: `src/renderers/common/RenderObjects.js`, `RenderObject.js`, `Pipelines.js`.)

- Each (object, material, render context, lights, ...) combination becomes a cached `RenderObject`, holding the compiled node builder output, the pipeline and the bind groups. It is reused every frame.
- When `material.version` changes (that is, `material.needsUpdate = true`) the renderer recomputes the material cache key; if the key equals the original, the object keeps its pipeline and only the version is updated (cheap); if different, the old RenderObject is disposed and a new one is built (shader generation + pipeline creation, a hitch).
- The key includes (from `getMaterialCacheKey`): `customProgramCacheKey()`, every material property except `is*`, `_private`, `visible`, `version`, `uuid`, `name`, `opacity`, `userData`; numeric values are reduced to on/off (0 vs nonzero) except `side`, so changing `roughness` between 0.3 and 0.8 does not alter the key, but 0 to nonzero does; texture properties contribute mapping, uv `channel` (added to the key in r187, #34773) and, on WebGPU, filter/wrap modes (they are part of the bindings); clipping state; geometry attribute layout (names, strides, itemSize, normalized, morph targets, index presence); skeleton bone count; batched mesh and instancing flags.
- Consequences:
  - Swapping a texture for another texture with the same sampler settings does not rebuild the pipeline; changing `magFilter/minFilter/wrap*` does (WebGPU).
  - Geometry with a different attribute set under the same material creates a new RenderObject/pipeline. Keep attribute layouts consistent among meshes sharing a material.
  - Assigning different node graphs (`colorNode`, `positionNode`, ...) to a material and setting `needsUpdate = true` rebuilds. Prefer driving variation with uniforms (`uniform(...).value = x`) instead of swapping nodes.
  - Many variants of one node material (colors, params): `new THREE.NodeMaterialInstance( baseMaterial )` (r187) shares the base material's single shader build and reads per-instance values through `materialReference()` (docs: "All instances created from the same node material share a single shader build").
  - `Object3D.static = true` (WebGPURenderer only, `Object3D.md`) lets the renderer skip some per-frame state checks for objects whose geometry and material no longer change (`webgpu_performance.html` toggles it for a whole model). Use for scenery. Setting it and then mutating geometry/material gives stale results.
- Pipelines and bind groups are shared between objects whose render object data match; bind groups are updated when bound resources change. Texture and buffer resources are managed per resource, not per material. Fewer unique materials/geometry layouts means fewer pipelines and bind group switches.
- `renderer.info.memory.programs` / `programsSize` (WebGPU `Info`) track active programs.

---

## 5. TSL performance rules

TSL (`three/tsl`) builds a node graph; `NodeBuilder` generates WGSL (or GLSL for the WebGL2 backend) once per RenderObject. Performance is mostly about what code the graph generates and when it is rebuilt.

1. Nodes used multiple times: node results are cached within a build, but an expression consumed in several places can still be emitted inline more than once (rule of thumb; inspect generated code). Materialize an expensive expression into a shader variable with `.toVar()` so it is computed once and referenced:
   ```js
   import { Fn, texture, uv, vec3, float } from 'three/tsl';

   const shade = Fn(() => {
     const n = texture(normalMap, uv()).xyz.mul(2).sub(1).normalize().toVar('n'); // computed once
     return n.dot(lightDir).max(0).add(n.dot(viewDir).abs());                      // n reused
   });
   ```
   Use `.toVar()` for values mutated later (`assign`, `addAssign`, ...) and for values read many times; use `const` JS variables to share node references (graph sharing) for pure expressions the builder can cache.
2. `Fn(...).once()`: marks the function body so it is generated once and its result reused for later calls with the same sub-build (source: `ShaderNode.once`, `properties[subBuildProperty] = result`). Use for heavy helper functions invoked from many places, where call sites would otherwise re-expand the body.
3. `isolate(node)` (`IsolateNode`) controls cache sharing during build; the old `cache()` helper is deprecated in r186. Use it only to prevent unwanted caching of a sub-graph.
4. `Loop`, `If`, `Break`: real control flow. Keep loops bounded, hoist invariant math out of loops, avoid dynamic loop bounds that come from per-pixel data.
5. Precompute on the CPU what is constant: wrap JS numbers/vectors in `uniform()` only if they change; constants as plain numbers fold into the shader.
6. Node materials: set only the node slots you need (`colorNode`, `normalNode`, `positionNode`, `opacityNode`, `emissiveNode`). Every slot adds code. Use the simplest node material class (`MeshBasicNodeMaterial` < `MeshLambertNodeMaterial` < `MeshPhongNodeMaterial` < `MeshStandardNodeMaterial` < `MeshPhysicalNodeMaterial`), same ladder as section 1.
7. Do not construct nodes per frame: build the graph once at setup; per frame only set `.value` of uniforms (or use `onFrameUpdate` / `onRenderUpdate` / `onObjectUpdate` callbacks on nodes, source `Node.js`, which run at the right cadence).
8. Textures in TSL: `texture(tex)` samples with a sampler; `textureLoad` skips filtering; `textureStore` (storage textures) writes from compute. WebGPU limits sampled textures per shader stage (spec default limit 16, rule of thumb): large node graphs that sample many maps can hit it.
9. Output color transform and tone mapping are applied once at the end (`renderOutput`/pipeline); do not tone map intermediate nodes.
10. Debug generated shaders and node counts with the Inspector (`tsl-graph` extension, `inspect(node)` hooks), and keep an eye on the pipeline count (`info.memory.programs`).

---

## 6. Uniform groups in TSL

WebGPU uses uniform buffers. TSL groups `uniform()` nodes into buffers by `UniformGroupNode`; the group determines how often the buffer is updated.

```js
import { uniform, uniformGroup, sharedUniformGroup, frameGroup, renderGroup, objectGroup } from 'three/tsl';

const time = uniform(0).setGroup(frameGroup);             // shared buffer, updated once per frame
const exposure = uniform(1).setGroup(renderGroup);        // shared buffer, updated once per render() call
const tint = uniform(new THREE.Color(1, 1, 1));           // default groupNode is objectGroup (UniformNode source)
tint.setGroup(objectGroup);                               // explicit, same as default
const myShared = sharedUniformGroup('lighting', 0);       // custom shared group (order 0 sorts first)
const myGroup = uniformGroup('material', 1);              // custom non-shared group
```

Facts (source `UniformGroupNode.js`):

- `objectGroup`: uniform buffer per object (`NodeUpdateType.OBJECT`); `renderGroup`: shared buffer updated once per render call; `frameGroup`: shared buffer updated once per frame.
- `shared = true` groups share the same GPU buffer across all materials that use them (no duplicate upload), `order` sorts groups (shared groups typically first). Calling `group.update()` marks it as needing upload.
- Put values that are identical across all objects (time, camera-derived constants, global wind) in `frameGroup`/`renderGroup`; keep `objectGroup` for truly per-object values. Many small per-object buffers cost bind group churn.
- `uniform(value).onObjectUpdate(cb)` / `.onRenderUpdate(cb)` / `.onFrameUpdate(cb)` set the update callback cadence.
- Example of a custom per-object uniform node: `webgpu_instance_uniform.html` (a `Node` with `updateType = NodeUpdateType.OBJECT` that copies `mesh.color` into a uniform).

---

## 7. Compute, storage buffers and instancing (WebGPU)

Simulation on the GPU removes the CPU loop and the per-frame upload. Pattern: store state in storage buffers (`instancedArray`), update with a compute kernel (`Fn(...)().compute(count)`), render by reading the same buffers in the vertex stage, no readback.

```js
import * as THREE from 'three/webgpu';
import { Fn, If, uniform, instancedArray, instanceIndex, vec3, hash } from 'three/tsl';

const count = 200000;
const positions  = instancedArray(count, 'vec3');
const velocities = instancedArray(count, 'vec3');
const gravity = uniform(-0.001);

const update = Fn(() => {
  const p = positions.element(instanceIndex);
  const v = velocities.element(instanceIndex);
  v.addAssign(vec3(0, gravity, 0));
  p.addAssign(v);
  If(p.y.lessThan(0), () => { p.y.assign(0); v.y.assign(v.y.negate().mul(0.8)); });
})().compute(count).setName('Update');         // default workgroup size [64]

const material = new THREE.SpriteNodeMaterial();
material.positionNode = positions.toAttribute();         // vertex stage reads the storage buffer
const sprite = new THREE.Sprite(material);
sprite.count = count;                                    // instance count
sprite.frustumCulled = false;                            // GPU-driven positions: CPU bounds are meaningless
scene.add(sprite);

await renderer.init();
renderer.setAnimationLoop(() => {
  renderer.compute(update);                              // dispatches before render; renderer.computeAsync also exists
  renderer.render(scene, camera);
});
```

(Adapted from `webgpu_compute_particles.html`.)

API facts:

- `instancedArray(count, type)` creates a storage buffer attribute usable both as `storage` in compute and as an instanced attribute in render; `attributeArray(count, type)` is the non-instanced variant. `storage(bufferAttribute, type, count)` wraps your own `StorageBufferAttribute` / `StorageInstancedBufferAttribute`. `.element(index)` gives read/write access to one element; `.toAttribute()` exposes it as a vertex attribute (instanced draws); `.toReadOnly()` available where you only read (check `StorageBufferNode.md`).
- `compute(node, count, workgroupSize)` / `node.compute(count, workgroupSize)`: `count` is the number of invocations (a number) or `[x, y, z]` dispatch size; `workgroupSize` defaults to `[64]`. `computeKernel(node, workgroupSize)` creates a kernel without a count (dispatch size set later, or via `IndirectStorageBufferAttribute`).
- Workgroup size (rule of thumb): keep the product a multiple of the hardware wave size (32 on NVIDIA, 32 or 64 on AMD, 32 on Apple/Intel varies); 64 is a good default for 1D; 8x8 for 2D image kernels; larger groups only if you use workgroup shared memory (`workgroupArray`, `workgroupBarrier`). The WebGPU per-workgroup invocation limit is 256 by default (spec default).
- Built-ins: `instanceIndex` (global invocation index in compute / instance in render), `globalId`, `localId`, `workgroupId`, `invocationLocalIndex`, `workgroupArray(type, count)`, `workgroupBarrier()`, atomics (`atomicAdd`, ...). Use shared memory for reductions (`webgpu_compute_reduce.html`) to cut global memory traffic.
- Dispatch granularity: dispatch once per frame with enough work per invocation (avoid dispatching thousands of tiny kernels). Merge kernels that touch the same data, but separate passes are needed between steps that depend on each other's output across invocations (use multiple compute nodes in an array: `renderer.compute([a, b, c])`).
- Data layout: `vec3` storage elements are padded to 16 bytes in WGSL array layouts; prefer `vec4` or separate arrays to avoid surprises and wasted memory (WGSL array layout alignment; verify for your buffer type). Use half precision storage only if you verify support.
- Ping-pong textures for 2D simulations: `StorageTexture` + `textureStore`/`textureLoad` (`webgpu_compute_texture_pingpong.html`).
- `Mesh.count` (documented as WebGPURenderer-only) and `InstancedMesh.count` set the instance count; `InstancedMesh` is also a good fit for the render side with `positionNode` reading a storage buffer by `instanceIndex` (`webgpu_instance_mesh.html`, `webgpu_compute_birds.html`).
- Compute pipelines are compiled on first dispatch: `await renderer.compileComputeAsync(node)` ahead of time.
- Compute availability: the WebGL2 fallback backend of WebGPURenderer implements compute differently (the source uses transform feedback) and is more limited than native WebGPU compute (for example workgroup shared memory and atomics, rule of thumb); if you need compute features, require the WebGPU backend (`renderer.backend.isWebGPUBackend`) or test on the fallback with `forceWebGL: true`.

Instancing with TSL on the render side: `instancedBufferAttribute(attr)`, `instancedDynamicBufferAttribute(attr)`, `instance(matrices, colors)`, `instancedMesh(mesh)` accessors, `batch(batchedMesh)`, `morphReference(mesh)`, `skinning(skinnedMesh)` (the node materials wire these automatically for `InstancedMesh`, `BatchedMesh`, morphs, skinning).

---

## 8. Avoiding readbacks

Reading GPU data on the CPU synchronizes the pipeline: the CPU waits for the GPU to finish the work that produces the data, and the data round-trips over the bus. Keep data on the GPU.

- `renderer.getArrayBufferAsync(storageAttribute, target, offset, count)` (WebGPURenderer): async copy of a storage buffer to the CPU. Pass a `ReadbackBuffer` (`new ReadbackBuffer(maxByteLength)`) as `target` to reuse the staging buffer; call `readbackBuffer.release()` when done so the GPU can reuse it (docs). Read back small data (counts, reduction results), at low frequency, and consume it a frame or more later.
- `renderer.readRenderTargetPixelsAsync(rt, x, y, w, h, ...)` is async in WebGPURenderer and WebGLRenderer (use it instead of the synchronous `WebGLRenderer.readRenderTargetPixels`, which blocks).
- `renderer.waitForGPU()` is deprecated; do not use it to "synchronize".
- Replace readbacks by GPU-side use: indirect draws/dispatches (next section), GPU culling, GPU picking with a 1 x 1 target, or sort/prefix-sum in compute (`BitonicSort`, `CountingSort` in addons; example `webgpu_compute_sort_bitonic.html`).
- Do not `await` the result inside the render loop in a way that blocks the next frame; start the read, handle the promise later, ignore if stale.
- `renderer.info.memory.readbackBuffers` / `readbackBuffersSize` (WebGPU Info) show live readback resources; leaking them wastes memory.

---

## 9. Indirect draws, render bundles, `static`

- Indirect dispatch (node must come from `computeKernel()` since r187; count nodes throw): `renderer.compute(node, indirectStorageBufferAttribute)` takes `IndirectStorageBufferAttribute` for the dispatch size written by an earlier compute pass (GPU decides the workload). Indirect draw: `webgpu_struct_drawindirect.html` (see also `IndirectStorageBufferAttribute.md`). Together with GPU frustum culling in compute this is the high-end route for huge scenes (no CPU culling cost).
- Render bundles: `BundleGroup` records draw commands once and replays them: reduces CPU encode time for static content (`draw-calls-and-geometry.md` section 15). `static = true` by default; set `needsUpdate = true` after changing anything inside.
- `Object3D.static` (WebGPURenderer): see section 4.
- `renderer.isOccluded(object)`: occlusion query for visibility feedback (`webgpu_occlusion.html`); results arrive asynchronously (one-frame-late use).
- MRT: `renderer.setMRT(mrt({...}))` writes several outputs per fragment in one pass, but cost grows with attachment count and format size (bandwidth and tile memory); only request outputs that downstream passes consume. `renderer.getMRT()`. For post-processing passes use `pass.setMRT(...)`.
- Output format: `outputBufferType` default `HalfFloatType`; `UnsignedByteType` saves bandwidth (WebGPURenderer docs).

---

## 10. Compilation

Both backends compile lazily at first draw, which causes hitches. Compile ahead:

```js
await renderer.init();
await renderer.compileAsync(scene, camera);                 // all materials/object configs in scene
await renderer.compileComputeAsync(computeNodes);           // compute pipelines
```

- `Renderer.compile()` is an alias for `compileAsync()` in r187 (`Renderer.md`). WebGLRenderer has both `compile` (sync, blocking) and `compileAsync` (uses `KHR_parallel_shader_compile`; "recommended whenever possible").
- Set up lights, environment, fog, shadow settings, tone mapping and render targets first (compile uses current state). The third parameter lets you compile an object for a target scene before adding it.
- Compile progress: WebGPU `compileAsync(scene, camera, targetScene, onProgress)`.
- Reduce the number of programs: share materials, avoid per-object node graphs, keep attribute layouts stable (section 4).
- Textures upload separately: `renderer.initTexture(texture)`; `initRenderTarget`.

---

## 11. Morph targets and skinning

Morph targets (blend shapes):

- WebGLRenderer stores morph targets in a `DataArrayTexture` (source: `WebGLMorphtargets.js`, one layer per target) read in the vertex shader, so the practical limit is texture memory, not vertex attribute slots. The vertex shader (`morphtarget_vertex`) loops over all `MORPHTARGETS_COUNT` targets and skips those whose influence is exactly `0.0` (`if (morphTargetInfluences[i] != 0.0)`), so each active target costs a texture fetch per vertex and zero-influence targets cost only the loop/branch. Keep the number of non-zero influences per frame small (rule of thumb). The influences array is uploaded per draw.
- `geometry.morphTargetsRelative = true` stores deltas instead of absolute positions (smaller values, quantization friendly).
- Memory: `targets x vertices x 3 floats (x2 if normals)`. A 20k vertex head with 50 targets is about 12 MB for positions alone as float32 (arithmetic).
- Manual use: morph targets to animate 19,000 merged boxes between datasets entirely on the GPU (`draw-calls-and-geometry.md` section 8).
- Per-instance morph: `InstancedMesh.morphTexture` + `setMorphAt`.
- Bounding volumes do not follow morphs: recompute or disable culling (`SkinnedMesh`/`Mesh` bounds rules in `draw-calls-and-geometry.md` section 10).

Skinning (GPU):

- `SkinnedMesh` skinning runs in the vertex shader using a bone matrix `DataTexture` (`Skeleton.boneTexture`, `computeBoneTexture()`); CPU cost per frame is updating bone matrices (animation mixer + `skeleton.update()`), i.e. proportional to bones, not vertices.
- Cost drivers: bones per skeleton (rule of thumb: under about 60 to 100 for crowd characters), vertex influences (4 per vertex), number of skinned meshes (each is its own draw call and its own bone texture upload), mixer evaluation per object (`AnimationMixer.update` is the usual CPU hotspot with many characters).
- Share animation work: `AnimationObjectGroup` lets many objects share one animation state (same pose), when compatible.
- Crowds: GPU-driven instanced skinning in WebGPU (`webgpu_skinning_instancing.html`, `webgpu_skinning_instancing_individual.html`), or bake animation into vertex-animation textures and play them in the vertex shader with `InstancedMesh` (a technique, not a core API).
- LOD for characters: swap to fewer-bone, lower-poly meshes at distance, stop updating mixers for distant/offscreen characters (skip `mixer.update` or lower its rate).
- `SkinnedMesh` has its own bounding sphere: pose-dependent (`computeBoundingSphere()`).

---

## 12. Particles: Points vs InstancedMesh vs compute

| Approach | Strengths | Limits |
|---|---|---|
| `Points` + `PointsMaterial` / `ShaderMaterial` | 1 draw call, minimal vertex data (1 vertex per particle), simple | Square billboards only; `gl_PointSize` is capped by hardware (`ALIASED_POINT_SIZE_RANGE`, often 64 to 256 px, platform-dependent), clipped when the center leaves the screen; no per-particle rotation without shader work; WebGPU only supports point primitives of 1 px (`PointsNodeMaterial.md`), so on the WebGPU backend use `PointsNodeMaterial` in its instanced/sprite mode or `SpriteNodeMaterial` (examples `webgpu_instance_points.html`, `webgpu_instance_sprites.html`) |
| `InstancedMesh` with quad geometry (or `Sprite` with `count` in WebGPU) | Real quads: arbitrary size, rotation, per-instance attributes; no point size cap | 4 vertices/instance (or 2 triangles); CPU updates cost upload bandwidth if animated on CPU |
| `InstancedMesh` of low-poly meshes | Real 3D particles (debris) | Vertex cost scales with mesh size |
| Compute particles (WebGPU) | Millions of particles, physics, collisions, sorting; zero CPU per frame | WebGPU compute required; development complexity; set `frustumCulled = false` |
| CPU-updated `Points` | Easy | Per-frame JS loop + buffer upload; fine up to tens of thousands (rule of thumb) |
| Shader-only animation (time uniform) | No CPU or upload: positions computed from `time + per-particle seed` in the vertex shader | Stateless: no collisions/feedback |

Guidelines:

- Prefer shader-only animation (analytic motion from a time uniform and per-particle attributes) for fire, rain, dust, snow, sparks: zero upload cost.
- Overdraw dominates for big/soft particles: shrink quads to the opaque core, limit count near the camera, `depthWrite = false`, use additive blending or alpha testing (`rendering-strategies.md` section 8).
- Sort only if you must blend with normal alpha; additive blending needs no sort.
- Allocate buffers at maximum size and use `geometry.setDrawRange(0, n)` or `count` to vary active particles.
- Update dynamic buffers with `setUsage(THREE.DynamicDrawUsage)` and `needsUpdate`, or partial `addUpdateRange`.
- WebGPU compute particles examples: `webgpu_compute_particles.html` (200k bouncing, sprite material, `alphaToCoverage`), `webgpu_compute_particles_rain.html`, `webgpu_compute_particles_snow.html`, `webgpu_compute_particles_fluid.html`, `webgpu_compute_points.html`.

---

## 13. GPU picking vs raycasting

CPU `Raycaster`: cost is O(objects tested x triangles) per ray (each `Mesh.raycast` first tests its bounding sphere, then triangles; `InstancedMesh.raycast` loops all instances; skinned/morphed meshes test the bind pose unless you use special handling). Fine for tens of objects or low-poly proxies; slow for many high-poly or instanced objects, and for per-frame hover tests.

Cheaper CPU strategies:

- Raycast against a small list of low-poly proxies or bounding volumes, not the whole scene (`raycaster.intersectObjects(list, false)`); use `raycaster.layers`; only cast on pointer move/click, throttled to once per frame; reuse the `intersects` array (third argument); `near`/`far` limits.
- Pre-filter with a spatial structure (grid, `Octree` for static triangles, your own bounding-volume tests with `Box3`/`Sphere`/`Frustum`). BVH acceleration (for example the `three-mesh-bvh` library) is third party and not in core.

GPU picking (id rendering): render the scene with a flat-color id material (or per-object `uniform`) into a tiny render target covering only the pixel under the cursor, then read that pixel. Cost is one extra scene pass at 1 x 1 effective resolution (vertex work only, no fragment cost), independent of triangle count of picking math.

```js
// from webgl_interactive_cubes_gpu.html (pattern)
const pickingTexture = new THREE.WebGLRenderTarget(1, 1);            // 1 x 1 target
const pixelBuffer = new Uint8Array(4);

function pick(event) {
  // Render only the pixel under the pointer: shift the camera frustum to that pixel
  camera.setViewOffset(renderer.domElement.width, renderer.domElement.height,
    event.clientX * dpr | 0, event.clientY * dpr | 0, 1, 1);
  renderer.setRenderTarget(pickingTexture);
  renderer.render(pickingScene, camera);           // pickingScene: same meshes with MeshBasicMaterial color = id
  camera.clearViewOffset();
  renderer.setRenderTarget(null);
  return renderer.readRenderTargetPixelsAsync(pickingTexture, 0, 0, 1, 1, pixelBuffer)
    .then(() => (pixelBuffer[0] << 16) | (pixelBuffer[1] << 8) | pixelBuffer[2]);
}
```

Notes:

- The readback is the expensive part: use the async version (works in both renderers) and accept a frame of latency; do it on pointer events, not per frame without need.
- Works for instanced meshes (write the instance id into the color via an instance attribute / `instanceIndex`), vertex-shader displaced geometry, particles and skinned meshes with correct poses, where CPU raycasting is wrong or too slow.
- Needs `pickingScene` that shares geometry and uses an id material; for many objects keep the id material sharing one program (per-object color via `userData`/instance attribute or a uniform per object).
- GPU picking returns an id only (no hit point/normal): combine with a CPU ray against the single picked object if you need the point.
- Occlusion, alpha: ids render opaque; use alpha test materials for cutouts if needed.
- WebGPU: same pattern with `RenderTarget` and `readRenderTargetPixelsAsync`; or a compute pass that writes the picked id to a storage buffer read back via `getArrayBufferAsync`.
- The manual's Picking article covers both CPU raycast picking and GPU picking (render each object in a unique color, read the pixel under the mouse with a 1 x 1 `WebGLRenderTarget`).

---

## 14. BVH and spatial structures

Core has: `Box3`, `Sphere`, `Frustum`, `OBB`, `Octree` (triangle octree for static meshes), `Layers`. It does not include a BVH for mesh raycasting or `BatchedMesh` acceleration; `three-mesh-bvh` and `@three.ez/batched-mesh-extensions` (used in `webgl_batch_lod_bvh.html`) are third-party libraries, mentioned only for orientation: evaluate them separately when `Raycaster` or per-instance culling is the measured bottleneck.

---

## 15. Timestamps and profiling

- WebGPURenderer: create with `{ trackTimestamp: true }` (or attach an `Inspector`), `await renderer.resolveTimestampsAsync(THREE.TimestampQuery.RENDER | COMPUTE)`, read `renderer.info.render.timestamp` / `renderer.info.compute.timestamp` in ms (see `rendering-strategies.md` section 13). Name compute nodes with `.setName('...')` so they are identifiable in the Inspector.
- Use A/B toggles: replace a node material with `MeshBasicNodeMaterial` for a subset (`scene.overrideMaterial`) to see how much shading costs versus geometry/draw overhead.
- WebGLRenderer: `scene.overrideMaterial = new THREE.MeshBasicMaterial()` for the same test; Spector.js (third party) for state-change analysis.
- Track `renderer.info.programs.length` (WebGL) or `info.memory.programs` (WebGPU) across interactions: growth means churn (sections 2 and 4).

---

## 16. See also

API pages: `../threejs/references/api/ShaderMaterial.md` (`uniformsGroups`), `UniformsGroup.md`, `Uniform.md`, `Material.md` (`needsUpdate`, `precision`, `onBeforeCompile`, `customProgramCacheKey`), `NodeMaterial.md`, `Node.md`, `UniformGroupNode.md`, `UniformNode.md`, `StorageBufferNode.md`, `StorageBufferAttribute.md`, `StorageInstancedBufferAttribute.md`, `IndirectStorageBufferAttribute.md`, `ComputeNode.md`, `ComputeBuiltinNode.md`, `WorkgroupInfoNode.md`, `AtomicFunctionNode.md`, `ReadbackBuffer.md`, `StorageTexture.md`, `BundleGroup.md`, `MRTNode.md`, `PointsNodeMaterial.md`, `SpriteNodeMaterial.md`, `Points.md`, `SkinnedMesh.md`, `Skeleton.md`, `AnimationObjectGroup.md`, `InstancedMesh.md` (`morphTexture`), `Renderer.md` (`compute`, `computeAsync`, `compileAsync`, `compileComputeAsync`, `getArrayBufferAsync`, `readRenderTargetPixelsAsync`, `setMRT`, `isOccluded`, `waitForGPU` deprecated), `WebGPURenderer.md`, `Info.md`, `TimestampQueryPool.md`, `Raycaster.md`, `Octree.md`, `BitonicSort_BitonicSort.md`, `CountingSort.md`.

Examples: `webgpu_compute_particles.html`, `webgpu_compute_birds.html`, `webgpu_compute_reduce.html`, `webgpu_compute_texture_pingpong.html`, `webgpu_compute_sort_bitonic.html`, `webgpu_struct_drawindirect.html`, `webgpu_instance_mesh.html`, `webgpu_instance_points.html`, `webgpu_instance_sprites.html`, `webgpu_instance_uniform.html`, `webgpu_instancing_morph.html`, `webgpu_skinning_instancing.html`, `webgpu_performance.html`, `webgpu_performance_renderbundle.html`, `webgpu_occlusion.html`, `webgl_ubo.html`, `webgl_ubo_arrays.html`, `webgl_interactive_cubes_gpu.html`, `webgl_tsl_instancing.html`.

Official: https://threejs.org/manual/en/webgpurenderer, https://threejs.org/manual/en/how-to-update-things, https://threejs.org/manual/en/picking, https://github.com/mrdoob/three.js/wiki/Three.js-Shading-Language, https://threejs.org/docs/

Related reference files: `draw-calls-and-geometry.md`, `textures-and-memory.md`, `rendering-strategies.md`.
