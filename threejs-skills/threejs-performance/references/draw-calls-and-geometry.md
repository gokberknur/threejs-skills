# Draw Calls and Geometry (three.js r186)

## When to read this

Read when the scene has many objects, the CPU frame time is high while the GPU is idle, `renderer.info.render.calls` is in the hundreds or thousands, or you must pick between merging, `InstancedMesh`, `BatchedMesh`, LOD and culling. Covers diagnosing, instancing, batching, merging, LOD, culling, matrix updates, sort/state changes, and shader pre-compilation.

Numbers marked "rule of thumb" are heuristics, not API facts. Always measure on the target device.

## Table of contents

1. Why draw calls cost (the actual bottleneck)
2. Diagnosing: `renderer.info` and the Inspector
3. Decision table: merge vs instance vs batch vs LOD
4. InstancedMesh deep dive
5. BatchedMesh deep dive
6. SceneOptimizer (auto-batching)
7. Merging geometries
8. The manual walkthrough, condensed (merge, then morph targets)
9. LOD
10. Frustum culling and bounding volumes
11. Reducing vertex count
12. Matrix updates
13. Sorting, renderOrder, state changes, shared materials
14. Pre-compiling shaders (`compile` / `compileAsync`)
15. Other draw-call reducers (draw range, layers, visible, WebGPU render bundles)
16. See also

---

## 1. Why draw calls cost

Each `Mesh` (per material group) is at least one draw call. Cost is mostly CPU and driver side, not GPU:

- three.js JS work per object: culling test, sort key, uniform upload (`modelViewMatrix`, `normalMatrix`), program/state lookup, attribute binding.
- Driver / browser validation per `drawElements` / `drawArrays` (WebGL) or per command encode (WebGPU).
- State changes between calls: program switch, material uniforms, texture binds, blend/depth state, VAO/bind-group switches. Program switches are the most expensive.

Consequence: 10,000 tiny meshes can be slower than one 5,000,000 triangle mesh. When frame time is CPU bound (main thread busy in `renderer.render`), reduce calls. When GPU bound (fill rate, shader cost, vertex count), reducing calls does nothing; see `rendering-strategies.md` and `shader-and-webgpu-perf.md`.

Quick CPU vs GPU test: shrink the canvas to a tiny size (`renderer.setSize(64, 64)`). If FPS jumps, you are fill-rate / fragment bound. If not, you are CPU / vertex / call bound.

Draw call budget (rule of thumb only): low thousands of calls on desktop, a few hundred on mobile before CPU becomes the limiter. Static scenes with a few hundred calls are usually fine.

---

## 2. Diagnosing

### 2.1 `renderer.info`

WebGLRenderer (`src/renderers/WebGLRenderer.js`, type `WebGLRenderer~Info`):

```js
import * as THREE from 'three';
const renderer = new THREE.WebGLRenderer();

function log() {
  const { render, memory, programs } = renderer.info;
  console.log({
    calls: render.calls,          // draw calls this frame
    triangles: render.triangles,
    points: render.points,
    lines: render.lines,
    frame: render.frame,
    geometries: memory.geometries, // GPU geometries alive
    textures: memory.textures,     // GPU textures alive
    programs: programs.length,     // compiled shader programs (WebGL: array of WebGLProgram)
  });
}
```

By default the counters reset at every `render()` call. With multiple render passes per frame (post-processing, shadow-less secondary views), disable auto reset and reset once per frame yourself:

```js
renderer.info.autoReset = false;
function frame() {
  renderer.info.reset();
  composer.render();           // several renderer.render calls inside
  console.log(renderer.info.render.calls);
}
```

WebGPURenderer (`three/webgpu`, class `Info` in `src/renderers/common/Info.js`). Field names differ:

```js
import * as THREE from 'three/webgpu';
const renderer = new THREE.WebGPURenderer();
await renderer.init();

const { render, memory, compute } = renderer.info;
render.drawCalls;     // draw calls of the current frame
render.frameCalls;    // render() calls of the current frame
render.triangles; render.points; render.lines;
memory.geometries; memory.textures; memory.renderTargets;
memory.programs; memory.attributes;
memory.texturesSize; memory.attributesSize; memory.total; // bytes (WebGPU Info only)
compute.frameCalls;
```

Rules of reading:

- `calls` / `drawCalls` high, `triangles` low: batching problem (sections 4 to 8).
- `triangles` very high (millions) with few calls: vertex count problem (LOD, simplification, sections 9 and 11).
- `programs` growing over time: material churn, `onBeforeCompile` variants, `needsUpdate` abuse (see `shader-and-webgpu-perf.md`).
- `memory.geometries` / `memory.textures` growing monotonically: leak, see `textures-and-memory.md` (disposal).
- `info.render.calls` counts shadow-pass draws too (each shadow-casting light re-draws casters). A scene with 300 meshes and 2 shadow lights can report ~900 calls.

### 2.2 Inspector addon (WebGPURenderer)

`examples/jsm/inspector/Inspector.js` extends `RendererInspector` (base: `InspectorBase`). It ships tabs for Performance, Memory, Timeline, Console, Settings, Viewer and Parameters, and enables GPU timestamp queries when the adapter supports `timestamp-query`.

```js
import * as THREE from 'three/webgpu';
import { Inspector } from 'three/addons/inspector/Inspector.js';

const renderer = new THREE.WebGPURenderer({ antialias: true });
renderer.inspector = new Inspector();         // set before/around init
await renderer.init();

const gui = renderer.inspector.createParameters('Settings'); // lil-gui-like panel in the Inspector
gui.add(mesh, 'count', 1, 100000, 1);
```

Used in `webgpu_performance.html`, `webgpu_instance_mesh.html`. It is a dev tool: remove it from production builds (it adds UI and per-frame resolve work). Per-pass GPU timings and timestamp API are in `rendering-strategies.md` section on measuring.

---

## 3. Decision table

| Situation | Use | Why |
|---|---|---|
| Thousands of copies, same geometry + material, different transform/color | `InstancedMesh` | 1 draw call, per-instance data in a buffer |
| Different geometries, same material (attribute layout), per-object transform/visibility | `BatchedMesh` | 1 multi-draw call, per-instance culling and sorting built in |
| Static, never changes individually | `mergeGeometries` (+ vertex colors / groups) | 1 call, zero per-frame cost, but cannot move parts |
| Many different materials | Reduce materials first (atlas, vertex colors, shared material), then batch | Program/state switches dominate |
| Far objects are expensive | `LOD` (or LOD levels as separate `InstancedMesh` ranges) | Cuts vertex cost, not call count |
| Huge animated crowds | `InstancedMesh` + `morphTexture`, or WebGPU skinning + instancing examples | CPU skinning per object does not scale |
| Static scene, WebGPU only | `BundleGroup` render bundles | Replays recorded commands, saves CPU encode |

`InstancedMesh` vs `BatchedMesh` summary:

| | InstancedMesh | BatchedMesh |
|---|---|---|
| Geometry | exactly one | many (same attribute set), added with `addGeometry` |
| Per-instance matrix | `instanceMatrix` attribute (`setMatrixAt`, then `instanceMatrix.needsUpdate`) | float `DataTexture` (`setMatrixAt` flags the texture itself) |
| Per-instance color | `instanceColor` (`setColorAt`) | colors `DataTexture` (`setColorAt`, `Vector4` for alpha) |
| Per-instance visibility | none (shrink to zero scale, or lower `count`) | `setVisibleAt` |
| Frustum culling per instance | no (only whole mesh bounding sphere) | yes (`perObjectFrustumCulled`, CPU) |
| Sorting | none | `sortObjects` front-to-back (opaque) or back-to-front (transparent), CPU |
| Add/remove at runtime | change `count` | `addInstance` / `deleteInstance`, `optimize()` |
| Morph targets | `morphTexture` + `setMorphAt` | not supported by API above |
| Per-frame CPU cost | upload of changed buffer | culling + sort loop over all instances every frame (source: `BatchedMesh.onBeforeRender`) |
| Custom attributes | add `InstancedBufferAttribute` | not directly; use extra textures / custom material |

---

## 4. InstancedMesh deep dive

Class: `InstancedMesh(geometry, material, count)` extends `Mesh`. `count` is fixed at construction as the capacity of buffers; `mesh.count` can be lowered (down to 0) to draw only the first N instances, but cannot exceed the allocated size.

### 4.1 Setup and per-frame updates

```js
import * as THREE from 'three';

const count = 10000;
const mesh = new THREE.InstancedMesh(geometry, material, count);
mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage); // hint: updated often

const dummy = new THREE.Object3D();   // reuse, never allocate in the loop
const color = new THREE.Color();

for (let i = 0; i < count; i++) {
  dummy.position.set(Math.random() * 100, 0, Math.random() * 100);
  dummy.updateMatrix();
  mesh.setMatrixAt(i, dummy.matrix);
  mesh.setColorAt(i, color.setHSL(Math.random(), 1, 0.5)); // creates mesh.instanceColor on first call
}
scene.add(mesh);

// every frame that you change data:
mesh.instanceMatrix.needsUpdate = true;
if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
```

Facts (from `InstancedMesh.md` and source):

- `setMatrixAt` / `setColorAt` only write into the CPU typed array. Nothing reaches the GPU until `needsUpdate = true` and the next render. Set the flag once after the loop, not per instance.
- `instanceColor` is `null` until the first `setColorAt`. If the first `setColorAt` happens after the mesh has already rendered, the renderer sees an `instancingColor` mismatch and rebuilds the shader program (hitch). Call `setColorAt` for at least one instance before the first render, or before `compile`.
- Same applies to `morphTexture` (created by `setMorphAt`).
- `DynamicDrawUsage` is a driver hint (`BufferAttribute.setUsage`). Per the BufferAttribute docs, after the first use of the buffer its usage cannot be changed; set it before first render.
- Upload cost is the full buffer: 16 floats (64 bytes) per instance for matrices. 100k dynamic instances is 6.4 MB per frame of bandwidth. For purely GPU-driven motion, compute the motion in the vertex shader (TSL / `onBeforeCompile`, time uniform) and upload nothing.
- Partial uploads: `instanceMatrix.addUpdateRange(start, count)` (floats, not instances) uploads only a slice; call `clearUpdateRanges()` after. See `BufferAttribute.md`.

```js
// only instances 100..199 changed
mesh.instanceMatrix.clearUpdateRanges();
mesh.instanceMatrix.addUpdateRange(100 * 16, 100 * 16);
mesh.instanceMatrix.needsUpdate = true;
```

### 4.2 Rendering a subset: `count`

```js
mesh.count = visibleInstances;   // draws instances [0, count)
```

Reorder (swap visible instances to the front) rather than leaving holes. `count` is a plain property read at draw time, so no re-upload. In WebGPU examples (`webgpu_instance_mesh.html`) a GUI drives `mesh.count`. Note `Mesh.count` (inherited) is documented as "can only be used with WebGPURenderer"; `InstancedMesh.count` overrides it and is used by both renderers (WebGL: `renderer.renderInstances(start, drawCount, object.count)`).

### 4.3 Per-instance custom attributes

WebGLRenderer, custom shader or `onBeforeCompile`:

```js
const heights = new Float32Array(count);
geometry.setAttribute('aHeight', new THREE.InstancedBufferAttribute(heights, 1)); // meshPerAttribute = 1
// vertex shader: attribute float aHeight;
// update: geometry.getAttribute('aHeight').needsUpdate = true;
```

`InstancedBufferAttribute(array, itemSize, normalized, meshPerAttribute)`: `meshPerAttribute` = how many consecutive instances share one value. Without `InstancedMesh` you use `InstancedBufferGeometry` (`instanceCount`, default `Infinity`) plus `InstancedBufferAttribute`s (examples `webgl_buffergeometry_instancing.html`, `webgl_buffergeometry_instancing_interleaved.html` uses `InstancedInterleavedBuffer`).

WebGPURenderer / TSL (`three/tsl`):

```js
import { instancedBufferAttribute, instancedDynamicBufferAttribute, attribute } from 'three/tsl';

const heightAttr = new THREE.InstancedBufferAttribute(new Float32Array(count), 1);
material.positionNode = positionLocal.add(vec3(0, instancedBufferAttribute(heightAttr), 0));
// instancedDynamicBufferAttribute(...) = same but DynamicDrawUsage
// attribute('aHeight') also works if the attribute is on the geometry
```

`instancedBufferAttribute(array, type, stride, offset)` accepts a `BufferAttribute`, `InterleavedBuffer` or typed array. Alternative for GPU-written data: storage buffers (`instancedArray`, `storage`), see `shader-and-webgpu-perf.md`.

Per-instance data in a texture is also an option (like `BatchedMesh` does): useful when you exceed `maxVertexAttributes` or want random access.

### 4.4 Raycasting

```js
const hits = raycaster.intersectObject(mesh);   // hits[0].instanceId
if (hits.length) mesh.getMatrixAt(hits[0].instanceId, matrix);
```

`InstancedMesh.raycast` first tests `boundingSphere` (computing it lazily if `null`) and then loops over every instance (CPU, O(count) per ray, each against the full geometry). With 100k instances and a high-poly geometry this is slow:

- Pick against a low-poly proxy geometry; or
- Use GPU picking (render ids to a render target, see `shader-and-webgpu-perf.md`); or
- Pre-filter with your own spatial grid and only test candidates.
- `raycaster.firstHitOnly` is not documented in the local `Raycaster.md`; do not rely on it.

Example: `webgl_instancing_raycast.html`.

### 4.5 Culling and bounding volume of an InstancedMesh

Frustum culling tests one sphere for the whole mesh: `InstancedMesh.boundingSphere` (if `null`, computed lazily by `Frustum.intersectsObject`, then cached). Pitfalls:

1. The sphere is computed once from the instance matrices at that time. If you later move instances outside it, the whole mesh can pop out when the stale sphere leaves the view. After bulk changes call `mesh.computeBoundingSphere()` (and `computeBoundingBox()` if used). The manual (`how-to-update-things`) states this explicitly.
2. For fast-moving or GPU-animated instances where recomputation is too costly, set `mesh.frustumCulled = false` (then everything is always submitted; vertex work for off-screen instances is wasted but there is no popping).
3. There is no per-instance culling. For large worlds split instances into spatial chunks (several `InstancedMesh`es, each with its own tight sphere) or use `BatchedMesh` with `perObjectFrustumCulled`.

### 4.6 Morph targets, skinning, limits

- `InstancedMesh.morphTexture` (a `DataTexture`) stores per-instance morph weights; fill with `setMorphAt(index, mesh)` where `mesh.morphTargetInfluences` holds that instance's weights, then set `mesh.morphTexture.needsUpdate = true`. Example: `webgl_instancing_morph.html`, `webgpu_instancing_morph.html`.
- Skinning plus instancing is not provided by `InstancedMesh` itself. WebGPU examples `webgpu_skinning_instancing.html` and `webgpu_skinning_instancing_individual.html` show node-based approaches.
- `WebGPURenderer.highPrecision` (CPU 64-bit model-view) is documented as incompatible with `InstancedMesh` and `SkinnedMesh`.
- Materials: all instances share one material. Variation comes from `instanceColor`, custom attributes, or textures indexed by instance id (`instanceIndex` in TSL, `gl_InstanceID` in GLSL).

### 4.7 Disposal

`mesh.dispose()` frees GPU buffers of the instance attributes. Geometry and material still need their own `dispose()`.

---

## 5. BatchedMesh deep dive

Class: `BatchedMesh(maxInstanceCount, maxVertexCount, maxIndexCount, material)`. One draw (via multi-draw: `renderMultiDraw` in the WebGL buffer renderer) renders many geometries, each with its own transform, visibility and optional color. Matrices live in a float `DataTexture` read in the vertex shader; an indirect texture maps draw ids to instance ids.

```js
import * as THREE from 'three';

const box = new THREE.BoxGeometry(1, 1, 1);
const sphere = new THREE.SphereGeometry(1, 12, 12);

// capacities are fixed buffers: size them to the sum of everything you will add
const batch = new THREE.BatchedMesh(
  1000,                                   // maxInstanceCount
  box.attributes.position.count + sphere.attributes.position.count, // maxVertexCount
  (box.index.count + sphere.index.count),                           // maxIndexCount
  new THREE.MeshStandardMaterial()
);

const boxId = batch.addGeometry(box);         // geometry id
const sphereId = batch.addGeometry(sphere);

const a = batch.addInstance(boxId);           // instance id
const b = batch.addInstance(sphereId);
batch.setMatrixAt(a, matrixA);                // no needsUpdate flag needed
batch.setMatrixAt(b, matrixB);
batch.setColorAt(a, new THREE.Color(0xff0000));
batch.setVisibleAt(b, false);
scene.add(batch);
```

### 5.1 API reference (verified in `BatchedMesh.md` / source)

Constructor properties: `maxInstanceCount`, `instanceCount` (readonly, active instances), `unusedVertexCount`, `unusedIndexCount` (readonly), `boundingBox`, `boundingSphere` (null until `computeBoundingBox()` / `computeBoundingSphere()`, or lazily on culling).

Geometry management:

- `addGeometry(geometry, reservedVertexCount = -1, reservedIndexCount = -1)` returns geometry id. Reserve extra space if you will later `setGeometryAt` with a bigger geometry (e.g. LOD swap).
- `setGeometryAt(geometryId, geometry)` replaces data in place (throws if the reserved space is too small); every instance using it changes.
- `deleteGeometry(geometryId)` also removes instances referencing it.
- `getGeometryRangeAt`, `getBoundingBoxAt(geometryId, target)`, `getBoundingSphereAt(geometryId, target)`, `getGeometryIdAt(instanceId)`, `setGeometryIdAt(instanceId, geometryId)` (switch an instance to another geometry: cheap LOD switching).
- `setGeometrySize(maxVertexCount, maxIndexCount)` and `setInstanceCount(maxInstanceCount)` resize buffers (shrinking throws if used space is in the way). Resizing reallocates GPU buffers: avoid at runtime.
- `optimize()` repacks geometry to remove gaps left by `deleteGeometry`.

Instance management:

- `addInstance(geometryId)` returns instance id (reuses ids freed by `deleteInstance`). Throws `Maximum item count reached` at capacity.
- `deleteInstance(instanceId)`; `setMatrixAt` / `getMatrixAt(instanceId, target)`; `setColorAt` / `getColorAt` (`Color` or `Vector4` for alpha); `setVisibleAt` / `getVisibleAt`.
- `validateInstanceId`, `validateGeometryId` throw on invalid/deleted ids.
- Negatively scaled matrices are not supported (documented).

Culling and ordering:

- `perObjectFrustumCulled` (default `true`): per-instance CPU frustum test every frame in `onBeforeRender`.
- `sortObjects` (default `true`): opaque sorted front-to-back, transparent back-to-front, per instance on CPU.
- `setCustomSort(fn)` / `customSort`: `fn(list, camera)` over items with a `z` field; `addons/utils/SortUtils.js` exports `radixSort` (expects unsigned 32-bit integer keys) as a ready-made fast sort.
- Cost model: with both flags `false` and no visibility changes, `onBeforeRender` returns early (source: `if (!this._visibilityChanged && !this.perObjectFrustumCulled && !this.sortObjects) return;`). Otherwise there is an O(instances) loop per frame, per camera, and again for each shadow pass (`onBeforeShadow`). For 100k+ instances turn off what you do not need.
- Raycasting is supported (`BatchedMesh.raycast`).

### 5.2 Constraints

- All geometries must share the same attribute set: same names, `itemSize`, `normalized`, and all indexed or all non-indexed (`_validateGeometry` throws otherwise). Normalize attributes up front (add missing `uv`, or delete extras).
- One material for the whole batch. Per-instance variation: color, plus whatever you derive from the instance id in a custom node/shader.
- Needs float vertex textures (WebGL2 always has them) and multi-draw. In WebGLRenderer it uses the multi-draw path (`renderer.renderMultiDraw`); in WebGPURenderer it is handled in `RenderObject`. The first `setColorAt` creates the colors texture, and calling it after the first render triggers a program change like `InstancedMesh.instanceColor`: set colors before first render.
- No morph targets or skinning in the public API.
- Buffers are fixed capacity; plan `maxVertexCount` / `maxIndexCount` as the sum of all geometries including reserved space.

### 5.3 BatchedMesh + LOD

Pattern (see `webgl_batch_lod_bvh.html`, which uses the third-party `@three.ez/batched-mesh-extensions` and `meshoptimizer`; those are not part of core):

1. Add each LOD level as its own geometry via `addGeometry`.
2. Each frame, per instance, choose a level by distance and call `setGeometryIdAt(instanceId, lodGeometryId)`.
3. Do the distance loop on a coarse spatial grid, not per instance, if instance counts are high.

### 5.4 Examples

`webgl_mesh_batch.html` (GUI toggles `sortObjects`, `perObjectFrustumCulled`, custom sort), `webgpu_mesh_batch.html`, `webgl_batch_lod_bvh.html`.

---

## 6. SceneOptimizer (auto-batching)

`examples/jsm/utils/SceneOptimizer.js`. Experimental, described in docs as "an experimental attempt to implement auto-batching".

```js
import { SceneOptimizer } from 'three/addons/utils/SceneOptimizer.js';

const optimizer = new SceneOptimizer(scene, { debug: false });
optimizer.toBatchedMesh();        // replaces compatible meshes with BatchedMesh instances
// optimizer.toInstancingMesh();  // abstract, NOT implemented in r186
```

How it works (read from source):

- Traverses `scene` (calls `scene.updateMatrixWorld(true)` first) for every `isMesh` node.
- Groups meshes by a hash of material properties (type, transparency/side/blending flags, PBR numbers, map uuids + offset/repeat/rotation) combined with the geometry attribute signature.
- Single-mesh groups are left alone. For each group it creates a `BatchedMesh` sized to the group, adds each unique geometry once (deduplicated by content hash of index + position data), one instance per mesh with world matrix (relative to the first mesh's parent), resets the batch material color to white and copies each mesh's `material.color` into `setColorAt`.
- Helpers: `removeEmptyNodes(object)`, `disposeMeshes(set)`.

Limits to account for: only `color` varies per instance; different textures with different uuids end up in different batches; there is no explicit exclusion of `SkinnedMesh`/`InstancedMesh` nodes in the traversal (they satisfy `isMesh`), so run it on static, plain-mesh content only; hashing every vertex array is O(total vertices) and happens synchronously, so run it at load, not per frame.

---

## 7. Merging geometries

```js
import * as BufferGeometryUtils from 'three/addons/utils/BufferGeometryUtils.js';

const merged = BufferGeometryUtils.mergeGeometries(geometries, /* useGroups */ false);
// returns null if attributes are incompatible
```

Rules (from `module-BufferGeometryUtils.md`):

- All geometries need compatible attributes (same names, itemSize, types) and must be all indexed or all non-indexed (convert with `geometry.toNonIndexed()` or index them).
- Bake each part's transform first: `geometry.applyMatrix4(matrix)`. The merged mesh has one transform.
- `useGroups = true` adds one `geometry.groups` entry per source geometry so you can pass an array of materials (`new Mesh(merged, [matA, matB])`). Each group is still one draw call, so merging with groups reduces calls to the number of materials, not to one.
- Per-part color without extra materials: add a `color` vertex attribute per part and use `material.vertexColors = true` (the manual does this for the globe: fill a `Uint8Array` of RGB per vertex, `new BufferAttribute(array, 3, true)`).
- `mergeVertices(geometry, tolerance = 1e-4)` welds duplicate vertices into an indexed geometry: lowers vertex count and memory, enables smooth normals; but attributes must match within tolerance, so hard edges with different normals/UVs stay split.
- Other helpers: `mergeAttributes`, `mergeGroups`, `toCreasedNormals(geometry, creaseAngle)`, `estimateBytesUsed(geometry)` (memory budgeting), `interleaveAttributes` / `deinterleaveGeometry`, `computeMikkTSpaceTangents(geometry, MikkTSpace, negateSign)` (needs `position`, `normal`, `uv`; de-indexes).

Tradeoffs:

| Pro | Con |
|---|---|
| Zero per-frame cost; 1 call; works with any material, any renderer | Cannot move/hide/cull parts individually; one bounding sphere, so the whole thing is drawn if any part is visible |
| Good for static levels, buildings, terrain props | Memory duplicated per copy (no instancing); merging 1000 copies of a 10k-vertex tree = 10M vertices |
| Great with a texture atlas | Large merged meshes defeat culling: chunk by spatial region (for example a grid), merge per chunk |

Rule of thumb: merge per spatial chunk, with chunk size such that one chunk is a few thousand to tens of thousands of triangles, so culling still helps.

After merging, dispose the source geometries you no longer need: `geometries.forEach(g => g.dispose())` (they were never uploaded unless rendered, but free CPU memory by dropping references).

---

## 8. Manual walkthrough, condensed ("Optimize Lots of Objects" + "Animated")

Problem: a globe with ~19,000 box meshes (one `Mesh`, one `MeshBasicMaterial` each) renders under 20 fps on the manual author's machine; the cost is per-mesh overhead, not triangles.

Step 1: share work.
- One set of helper `Object3D`s (`lonHelper` -> `latHelper` -> `positionHelper` -> `originHelper`) positions all boxes, instead of 3 helper nodes per box (80,000 scene graph nodes avoided). Use `updateWorldMatrix(true, false)` on the helper then `geometry.applyMatrix4(originHelper.matrixWorld)`.

Step 2: merge.
```js
const geometries = [];
data.forEach((row, latNdx) => row.forEach((value, lonNdx) => {
  if (value === undefined) return;
  const geometry = new THREE.BoxGeometry(1, 1, 1);
  // ... set helper rotations / scale, then:
  geometry.applyMatrix4(originHelper.matrixWorld);
  // per-box color via vertex colors:
  const rgb = color.toArray().map(v => v * 255);
  const colors = new Uint8Array(geometry.getAttribute('position').count * 3);
  for (let i = 0; i < colors.length; i += 3) colors.set(rgb, i);
  geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3, true)); // normalized
  geometries.push(geometry);
}));
const mesh = new THREE.Mesh(
  BufferGeometryUtils.mergeGeometries(geometries, false),
  new THREE.MeshBasicMaterial({ vertexColors: true })
);
```
Result: 19,000 calls become 1; the manual reports 60 fps.

Step 3: animate merged data without un-merging: morph targets.
- Build one merged geometry per dataset (they must have identical vertex counts and ordering: skip a cell in all sets if any set lacks data for it).
- Use set 0 as the base geometry and attach the others as morph targets:
```js
baseGeometry.morphAttributes.position = geometries.map((g, i) => {
  const a = g.getAttribute('position'); a.name = `target${i}`; return a;
});
baseGeometry.morphAttributes.color = geometries.map((g, i) => {
  const a = g.getAttribute('color'); a.name = `target${i}`; return a;
});
const mesh = new THREE.Mesh(baseGeometry, new THREE.MeshBasicMaterial({ vertexColors: true }));
// switch dataset i: animate mesh.morphTargetInfluences[i] to 1 and the others to 0
```
- Other options the manual rejects: fading with `Material.opacity` (overlapping geometry z-fights) and scaling datasets (boxes sink into the planet).
- Why it scales: the interpolation runs on the GPU. CPU cost per frame is updating a few influence floats. This generalizes to "morph between layouts" (random scatter to final positions) and is the same idea as `InstancedMesh.morphTexture` for per-instance weights.

Also from the same manual: combine with rendering on demand (render only on tween/controls change); see `rendering-strategies.md`.

---

## 9. LOD

Reduces vertex/fragment work for distant objects. Does not reduce draw call count by itself (it swaps which object is visible).

```js
import * as THREE from 'three';

const lod = new THREE.LOD();
for (let i = 0; i < 3; i++) {
  const mesh = new THREE.Mesh(new THREE.IcosahedronGeometry(10, 3 - i), material);
  lod.addLevel(mesh, i * 75, 0.1); // object, distance, hysteresis (fraction of distance)
}
scene.add(lod);
```

API (`LOD.md`): `addLevel(object, distance = 0, hysteresis = 0)`, `levels` (array of `{object, distance, hysteresis}`), `getCurrentLevel()`, `getObjectForDistance(distance)`, `removeLevel(distance)`, `autoUpdate` (default `true`: the renderer calls `update(camera)` each frame), `update(camera)`.

- Hysteresis: threshold as a fraction of distance so objects near a boundary do not flicker between levels as the camera jitters.
- `autoUpdate = false` and call `lod.update(camera)` yourself at a lower rate (every few frames, or only when the camera moved) when you have hundreds of LODs; the update computes distance per LOD per frame.
- Sharing materials across levels keeps the program count and uniform uploads low. Each level is a separate mesh: with N LOD objects you still pay N draw calls.
- `LOD.raycast` overrides `Object3D.raycast` (see `LOD.md`).
- With instancing: a single `InstancedMesh` cannot switch geometry per instance. Options: (a) one `InstancedMesh` per level and each frame partition instances by distance into the three buffers (write matrices into the right mesh, set each `mesh.count`); (b) `BatchedMesh` with `setGeometryIdAt` per instance (section 5.3). Option (a) costs a per-frame CPU loop over all instances; use a spatial grid so you only re-bucket chunks whose distance band changed.
- Level generation: `SimplifyModifier` at build time (section 11), or authored LODs / meshopt in glTF. `webgl_lod.html` and `webgl_loader_gltf_progressive_lod.html` (progressive LOD loading for textures/geometry) are the reference examples.

Rule of thumb for level distances: switch when a level's triangles would cover roughly one pixel per triangle or less on screen; choose by screen-space size, not by raw distance, if the camera FOV or resolution varies.

---

## 10. Frustum culling and bounding volumes

The renderer culls per object when `object.frustumCulled` is `true` (default): it tests the world-transformed bounding sphere against the camera frustum (`Frustum.intersectsObject`). For a `Mesh` it uses `geometry.boundingSphere`, computing it lazily when `null`. For `InstancedMesh`, `BatchedMesh`, `SkinnedMesh` it uses the object's own `boundingSphere`.

Pitfalls:

- Modify vertices (CPU) after first render: call `geometry.computeBoundingSphere()` (and `computeBoundingBox()`), otherwise the object can vanish while on screen. The manual `how-to-update-things` says the same. When growing a buffer, prefer pre-allocating and `geometry.setDrawRange(0, n)`.
- Vertex shader displacement, GPU skinning, GPU particle movement, compute-written positions: CPU does not know the real extent. Either pad the bounding sphere once (`geometry.boundingSphere = new THREE.Sphere(center, bigRadius)`) or set `frustumCulled = false`. Setting `false` on many objects forfeits culling: measure; it is acceptable for single large GPU-driven objects (the `webgpu_compute_particles.html` example sets `particles.frustumCulled = false`).
- `SkinnedMesh` has its own `boundingBox` / `boundingSphere` and `computeBoundingBox()` / `computeBoundingSphere()` based on the current bone pose; recompute if the animation moves the mesh far from the bind pose (docs suggest per frame if you need accuracy, which has a CPU cost).
- Culling skips the draw, not the matrix traversal: `updateMatrixWorld` still visits culled nodes. Hide whole subtrees with `visible = false` (the renderer does not descend into invisible objects) or remove them from the scene.

Coarse broad-phase structures (when you do your own culling/collision):

- `Box3`, `Sphere`, `Frustum` (`intersectsBox`, `intersectsSphere`, `intersectsObject`, `containsPoint`, `setFromProjectionMatrix(m, coordinateSystem, reversedDepth)`). Build a frustum once per frame from `camera.projectionMatrix * camera.matrixWorldInverse` and test your chunk bounds; avoid allocating (reuse `Frustum`, `Matrix4`, `Sphere`).
- `OBB` (`three/addons/math/OBB.js`): oriented bounding box with `intersectsOBB`, `intersectsRay`, `intersectsSphere`; use for tighter tests of rotated boxes than AABBs.
- `Octree` (`three/addons/math/Octree.js`): triangle octree for static level geometry (`fromGraphNode`, `rayIntersect`, `sphereIntersect`, `capsuleIntersect`, `trianglesPerLeaf`, `maxLevel`); for collision/ray queries against static triangles, not for render culling.
- Layers (`Layers`, 32 bit mask; `object.layers`, `camera.layers`, `raycaster.layers`): an object renders only if it shares a layer with the camera. Use to skip groups of objects for a specific camera or pass; also filters raycasts.
- BVH acceleration for `raycast` is not in core (third party `three-mesh-bvh`).

---

## 11. Reducing vertex count

Vertex/triangle count matters for vertex shader cost, skinning/morphing cost, shadow passes (casters are drawn again per shadow light) and memory.

- Build-time simplification: glTF tooling (gltf-transform / gltfpack with meshopt simplification) is the production route; not part of three.js.
- `SimplifyModifier` (`three/addons/modifiers/SimplifyModifier.js`): meshoptimizer-based; `modify(geometry, count)` is async in r186 and returns a new geometry; `count` is the approximate number of vertices to REMOVE (not to keep).
  ```js
  import { SimplifyModifier } from 'three/addons/modifiers/SimplifyModifier.js';
  const modifier = new SimplifyModifier();
  const keep = 0.5;
  const lowGeo = await modifier.modify(geometry, Math.floor(geometry.attributes.position.count * (1 - keep)));
  ```
  Use for automatic LOD generation at load/build time, not per frame; expect UV/normal seams to degrade.
- Compression for download/memory: Draco (`DRACOLoader`: `setDecoderPath`, `setWorkerLimit`) and meshopt (`GLTFLoader.setMeshoptDecoder`) reduce download size and, for meshopt, can be GPU-friendly quantized data. Both decode on load; they do not change the in-GPU vertex count. Examples `webgl_loader_gltf_compressed.html`, `webgpu_loader_gltf_compressed.html`.
- Attribute quantization: `GeometryCompressionUtils` (`three/addons/utils/GeometryCompressionUtils.js`): `compressNormals(geometry, 'DEFAULT' | 'OCT1Byte' | 'OCT2Byte' | 'ANGLES')`, `compressPositions(geometry)`, `compressUvs(geometry)`. Lowers vertex memory and bandwidth; materials may need the matching decode support. Verify visually. Also `Float16BufferAttribute` for half-float data.
- Index and share: `mergeVertices` to index soup geometry; remove unused attributes (`geometry.deleteAttribute('uv1')`); `estimateBytesUsed(geometry)` to audit.
- Normal maps instead of geometry: bake detail into normal maps and keep low-poly meshes.
- Avoid very small triangles: tiny triangles waste GPU quad shading efficiency (rule of thumb: when most triangles cover under about 8 to 16 pixels, vertex/rasterization overhead dominates).

---

## 12. Matrix updates

Each frame the renderer calls `scene.updateMatrixWorld()` (checked via `scene.matrixWorldAutoUpdate`), which walks every node. For each node: if `matrixAutoUpdate` then `updateMatrix()` (compose from position/quaternion/scale), then if `matrixWorldNeedsUpdate` (set by `updateMatrix`) or a parent forced it, multiply into `matrixWorld` and force children.

Static objects:

```js
object.position.set(...);
object.updateMatrix();            // bake local matrix once
object.matrixAutoUpdate = false;  // renderer no longer recomposes it each frame
```

Important details from `Object3D.updateMatrixWorld` source:

- With `matrixAutoUpdate = false` the local matrix is not recomputed; the world matrix is refreshed only when `matrixWorldNeedsUpdate` is true or a parent forces it. If you later move the object, call `updateMatrix()` (which flags the world update) or set `matrixWorldNeedsUpdate = true`.
- Setting `matrixAutoUpdate = false` on a parent whose children still move: children get world updates only if the parent's world matrix is refreshed; moving a parent after disabling auto update requires manual `updateMatrix()`.
- The traversal still visits every node, even static ones (checks are cheap but O(nodes)).

Whole scene static (or you manage updates manually):

```js
scene.matrixWorldAutoUpdate = false;   // renderer skips scene.updateMatrixWorld() entirely
// when something changed:
scene.updateMatrixWorld(true);
```

`WebGLRenderer.render` and `Renderer` both check `scene.matrixWorldAutoUpdate === true` before calling `scene.updateMatrixWorld()`; cameras without a parent check their own `matrixWorldAutoUpdate`. Use this for mostly static worlds (call once after edits), or to update only dynamic sub-trees by calling `dynamicGroup.updateMatrixWorld()` yourself. `Object3D.DEFAULT_MATRIX_AUTO_UPDATE` and `DEFAULT_MATRIX_WORLD_AUTO_UPDATE` change defaults for new objects.

Other matrix costs:

- Deep hierarchies multiply cost; flatten wherever you do not need parenting (the manual: "the more nodes we add to a scene graph the slower it gets").
- `Object3D.static` is relevant to WebGPURenderer only (the docs: renderer can skip state checks for objects that will not change, including geometry and material). `webgpu_performance.html` toggles `child.static` on every mesh via the Inspector.
- Avoid `getWorldPosition()` etc. allocations: pass a reusable target vector (`obj.getWorldPosition(_v)`), see `textures-and-memory.md`.
- `updateWorldMatrix(updateParents, updateChildren)` updates a single branch cheaply when you need a world matrix mid-frame (as in the manual's helper chain).

---

## 13. Sorting, renderOrder, state changes

Render lists are sorted before drawing (`WebGLRenderLists`):

- Opaque (`painterSortStable`): by `groupOrder`, `renderOrder`, then `material.id`, then material variant (instanced/skinned), then `z` ascending (front to back), then object id. Sorting by material id first groups draws with the same program/material to minimize state changes; the front-to-back z order after that helps early-z reject overdraw.
- Transparent (`reversePainterSortStable`): by `groupOrder`, `renderOrder`, then `z` descending (back to front); material grouping is secondary, so many transparent objects with alternating materials cause many state changes.
- `renderer.sortObjects = false` disables sorting entirely (useful when you set `renderOrder` yourself). `setOpaqueSort(fn)` / `setTransparentSort(fn)` install custom comparators (`null` restores default). Same API exists on WebGPURenderer (`Renderer.sortObjects`, `setOpaqueSort`, `setTransparentSort`).
- `Object3D.renderOrder`: lower renders first, opaque and transparent lists still sorted separately; setting it on a `Group` sorts all descendants together.

State-change reduction checklist:

1. Share material instances (`new Mesh(geo, sharedMaterial)`). The program cache is keyed by material parameters, but separate material instances still mean separate uniform sets and uploads, and `material.id` ordering groups only identical instances.
2. Use fewer distinct textures: atlas or `DataArrayTexture` layers, or vertex colors (see `textures-and-memory.md`).
3. Do not toggle `material.transparent`, `alphaTest`, `side` at runtime unless needed: some changes require a program rebuild (manual `how-to-update-things` lists texture presence, fog, vertex colors, morphing, shadow map, alpha test, transparent as rebuild triggers when set after first render; `material.needsUpdate = true` and expect a hitch).
4. `Material.forceSinglePass`: double-sided transparent objects render in two draws (back faces then front faces) by default; for flat foliage/cards set `forceSinglePass = true` to halve those calls.
5. Prefer `alphaTest` / `alphaHash` / `alphaToCoverage` (opaque queue, depth write on) over blended `transparent` for cutouts; fewer sort problems and less overdraw (details in `rendering-strategies.md`).
6. Avoid per-object `onBeforeRender` / `onAfterRender` callbacks on thousands of objects.

---

## 14. Pre-compiling shaders

First use of a material/object configuration compiles a shader program and can freeze the main thread for tens to hundreds of milliseconds (rule of thumb; Windows ANGLE/Direct3D is slower, as the manual notes). Pre-compile behind a loading screen.

WebGLRenderer:

```js
// materials, lights, fog, environment of `scene` must already be configured
await renderer.compileAsync(scene, camera);  // uses KHR_parallel_shader_compile when available
// or sync, blocking: renderer.compile(scene, camera);

// to add an object to an already-rendering scene without a hitch:
await renderer.compileAsync(newObject, camera, scene); // third arg = target scene (lights, env)
```

WebGPURenderer:

```js
await renderer.init();
await renderer.compileAsync(scene, camera, null, (progress) => {});  // 4th arg: onProgress
await renderer.compileComputeAsync(computeNode);                      // pipelines for compute
// Renderer.compile() is an alias of compileAsync in r186
```

Notes:

- Compile with the same lights, fog, shadow settings, tone mapping, render target format and instancing/skinning/morph flags you will render with: any difference yields another program (for example an `InstancedMesh` without `instanceColor` compiled, then `setColorAt` later).
- Compile the object you are about to add via the `object, camera, targetScene` form if it is not yet in the scene.
- Texture upload is separate: `renderer.initTexture(texture)` (WebGL and WebGPU; WebGPU requires an initialized renderer; `initTextureAsync` is deprecated) uploads before first use; `renderer.initRenderTarget(target)` allocates a render target. See `textures-and-memory.md`.
- `material.needsUpdate = true` and `onBeforeCompile` changes after first render trigger recompiles; keep variants finite and pre-compiled.

---

## 15. Other draw-call and work reducers

- `geometry.setDrawRange(start, count)` renders part of one geometry without reallocating: growing lines/trails/particles into a pre-allocated buffer (manual `how-to-update-things`: you cannot resize buffers; pre-allocate to the maximum, update contents, flag `needsUpdate`, and recompute bounds if culling matters).
- `object.visible = false` hides a subtree at essentially zero render cost. Use it for streaming rooms/chunks.
- `Layers` to render different subsets per camera/pass.
- WebGPU render bundles: `BundleGroup` (`three/webgpu`) records the draw commands of its descendants once and replays them. Only renderable objects (no lights) inside; `static = true` by default (structure does not change); set `bundleGroup.needsUpdate = true` after changes, for example after resize (the example calls it in its resize handler). Without a WebGPU backend it renders but with no gain. Example: `webgpu_performance_renderbundle.html` (4000 children plus an `InstancedMesh`; toggle with `?renderBundle=false` to compare).
- WebGPU `Object3D.static = true` per mesh (see section 12) and `renderer.isOccluded(object)` (occlusion query, returns whether fully occluded; example `webgpu_occlusion.html`).
- Points / sprites at very high counts: `Points` is 1 draw call regardless of count; prefer it, instancing quads, or WebGPU compute particles (see `shader-and-webgpu-perf.md`).
- Timeslice heavy CPU work: building merged geometry for a big level can block the main thread; split across frames or do it in a worker (`WorkerPool` in `three/addons/utils/WorkerPool.js`: `postMessage(msg, transfer)` returns a promise, `setWorkerLimit`, `dispose()`), transferring typed arrays and building `BufferGeometry` on the main thread from the returned buffers.

---

## 16. See also

API pages (relative to the repo root of the threejs skill):

- `../threejs/references/api/InstancedMesh.md`, `InstancedBufferAttribute.md`, `InstancedBufferGeometry.md`, `BatchedMesh.md`, `SceneOptimizer.md`, `LOD.md`
- `../threejs/references/api/Mesh.md` (`count`), `BufferAttribute.md` (`usage`, `addUpdateRange`, `clearUpdateRanges`), `BufferGeometry.md` (`setDrawRange`, `computeBoundingSphere`, `groups`)
- `../threejs/references/api/Object3D.md` (`frustumCulled`, `matrixAutoUpdate`, `matrixWorldAutoUpdate`, `renderOrder`, `visible`, `layers`, `static`), `Scene.md`, `Layers.md`, `Frustum.md`, `Sphere.md`, `Box3.md`, `OBB.md`, `Octree.md`
- `../threejs/references/api/module-BufferGeometryUtils.md`, `module-GeometryCompressionUtils.md`, `SimplifyModifier.md`, `module-SortUtils.md`, `WorkerPool.md`, `BundleGroup.md`
- `../threejs/references/api/WebGLRenderer.md` (`info`, `sortObjects`, `compile`, `compileAsync`, `setOpaqueSort`), `Renderer.md` (WebGPU: `compileAsync`, `compileComputeAsync`, `isOccluded`), `Info.md`, `InspectorBase.md`, `Material.md` (`forceSinglePass`, `needsUpdate`)

Examples (three.js r186 `examples/`): `webgl_performance.html`, `webgl_instancing_performance.html`, `webgl_instancing_dynamic.html`, `webgl_instancing_raycast.html`, `webgl_instancing_morph.html`, `webgl_mesh_batch.html`, `webgpu_mesh_batch.html`, `webgl_batch_lod_bvh.html`, `webgpu_instance_mesh.html`, `webgpu_performance.html`, `webgpu_performance_renderbundle.html`, `webgl_lod.html`, `webgl_loader_gltf_progressive_lod.html`, `webgl_buffergeometry_instancing.html`.

Official manual: https://threejs.org/manual/en/optimize-lots-of-objects, https://threejs.org/manual/en/optimize-lots-of-objects-animated, https://threejs.org/manual/en/how-to-update-things, https://threejs.org/manual/en/how-to-dispose-of-objects

Related reference files in this skill: `textures-and-memory.md`, `rendering-strategies.md`, `shader-and-webgpu-perf.md`.
