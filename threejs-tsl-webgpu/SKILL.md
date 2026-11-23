---
name: threejs-tsl-webgpu
description: Three.js r187 WebGPURenderer, TSL (Three.js Shading Language), node materials, compute shaders and node-based post-processing (`RenderPipeline`, formerly `PostProcessing`), with the complete official TSL guide (82 sections) and the full TSL function reference (every exported function) bundled offline. Use this skill whenever a task mentions TSL, `three/tsl`, `three/webgpu`, WebGPURenderer, WGSL, NodeMaterial / MeshStandardNodeMaterial, colorNode / positionNode, Fn(), uniform(), storage buffers, compute shaders, GPGPU particles, instancedArray, RenderPipeline / PostProcessing / pass() / mrt(), bloom/gtao/ssr/traa nodes, or asks to port GLSL / ShaderMaterial / onBeforeCompile / Shadertoy code to the new renderer, write a custom shader "without GLSL", or make three.js use WebGPU. Also load it when a user on WebGPURenderer reports that ShaderMaterial, EffectComposer or onBeforeCompile "does nothing". Use together with the `threejs` core skill.
---

# three.js r187: TSL, node materials, WebGPURenderer, compute

TSL is three.js's JavaScript shading language. You write shader graphs as chained JS node expressions; the `NodeBuilder` compiles them once per material to WGSL (WebGPU backend) or GLSL (WebGL 2 fallback backend). This skill makes you fluent in it and in the renderer built around it. Everything below is r187 (`three@0.187.0`); the TSL API moved fast between r160 and r175, so verify names in the bundled reference instead of relying on memory.

## Setup that is always the same

```js
import * as THREE from 'three/webgpu';          // NOT 'three'; never mix the two builds
import { Fn, uniform, uv, texture, time, vec3, positionLocal, normalWorld, mix, sin } from 'three/tsl';

const renderer = new THREE.WebGPURenderer({ antialias: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.setSize(innerWidth, innerHeight);
document.body.append(renderer.domElement);
renderer.setAnimationLoop(animate);              // waits for async init; `renderer.render()` before init throws, so `await renderer.init()` for manual loops
```

Import map: `"three": ".../three.webgpu.js"`, `"three/webgpu": ".../three.webgpu.js"`, `"three/tsl": ".../three.tsl.js"`, `"three/addons/": ".../examples/jsm/"` (pin `three@0.187.0`). With `three/webgpu`, the plain material classes (`MeshStandardMaterial` etc.) are the node versions, so `material.colorNode = ...` works on them; explicit `MeshStandardNodeMaterial` is equivalent. The WebGL 2 fallback kicks in automatically when WebGPU is unavailable; `forceWebGL: true` to test it. Not supported on WebGPURenderer: `ShaderMaterial`, `RawShaderMaterial`, `onBeforeCompile`, `EffectComposer` and its passes.

## TSL mental model (read before writing any node code)

- Node expressions run **once in JS at compile time** and build a graph; they are not evaluated per pixel in JS. `sin(time)` is a graph node, not a number. JS `if`/`for` run at build time (fine for unrolling or choosing variants); shader-side branches and loops are `If()`, `Select()`/`select()`, `Switch()`, `Loop()`.
- Values are typed nodes: `float(1)`, `vec3(1, 0, 0)`, `color(0xff0000)`, `int()`, `uint()`, `bool()`, `mat3/4`. Plain JS numbers auto-convert in operators (`a.mul(2)`). Convert with `.toFloat()`, `.toVec3()`, `.toInt()` etc. Swizzle with `.xyz`, `.rgb`, `.x`, `.xxy`; assign components `v.x.assign(...)`.
- Operators are methods: `add sub mul div mod pow equal notEqual lessThan greaterThan lessThanEqual greaterThanEqual and or not xor bitAnd bitOr shiftLeft shiftRight negate`. Math is free functions or methods: `sin(x)` or `x.sin()`; `mix(a,b,t)`, `smoothstep(e0,e1,x)`, `clamp`, `saturate`, `normalize`, `dot`, `cross`, `length`, `fract`, `abs`, `pow`, `oneMinus`, `remap`, `remapClamp`.
- `Fn(([a, b]) => { ... return x; })` defines a shader function with a stack: inside it you can use `.toVar()`, `.assign()`, `If`, `Loop`. Call it like a JS function; param objects also work `Fn(({ a, b }) => ...)`. Plain arrow functions compose inline (no stack). Define `Fn`s at module scope; mark exports `/*@__PURE__*/` for tree shaking.
- `x.toVar()` materializes a shader variable (needed before `.assign`, and to avoid recomputing an expensive subgraph; the builder otherwise inlines/caches by node identity). `toConst()` for constants. `.assign/addAssign/subAssign/mulAssign/divAssign` mutate variables.
- `uniform(value)` wraps a JS value you update from the CPU: `const u = uniform(1.0); u.value = 2;` or `u.onFrameUpdate(({ time }) => ...)`, `.onObjectUpdate`, `.onRenderUpdate`. `uniform(new THREE.Color())`, `uniform(vector3)` keep live references; `uniformArray([...])` for arrays; `uniformGroup`/`objectGroup`/`renderGroup`/`frameGroup` control update frequency.
- Accessors give you the built-in inputs: `positionLocal/positionWorld/positionView`, `normalLocal/normalView/normalWorld`, `tangentWorld`, `uv()` / `uv(1)`, `vertexColor()`, `attribute('name','vec3')`, `cameraPosition`, `cameraViewMatrix`, `modelWorldMatrix`, `screenUV`, `viewportUV`, `viewportSharedTexture()` (what is already rendered behind the surface), `viewportLinearDepth`, `time`, `deltaTime`, `frameId`, `instanceIndex`, `vertexIndex`, `frontFacing`.
- Textures: `texture(tex)` samples at `uv()`; `texture(tex, myUv)`; `.level(n)` / `.bias(n)` mip control; `cubeTexture()`, `texture3D()`, `pmremTexture()` for env maps.
- Stage control: most nodes are evaluated in the fragment stage; `varying(node)` or `vertexStage(node)` computes in the vertex stage and interpolates. Assign to `positionNode` for vertex displacement.
- Context: `node.setName('x')` names the WGSL variable (debugging), `.context({...})` overrides builder context, `.once()` caches a `Fn` result per build, `.label()` is deprecated since r179 (use `setName`).
- Debug: `renderer.debug.getShaderAsync(scene, camera, mesh)` returns compiled WGSL/GLSL; `debug(node)` logs; the TSL playground at https://threejs.org/tsl/ shows generated code; `three/addons/inspector/Inspector.js` for frame/GPU timings.

## Node material slots (the API you set)

`colorNode` (vec3, replaces color/map), `opacityNode`, `alphaTestNode`, `normalNode` (view space), `emissiveNode`, `roughnessNode`, `metalnessNode`, `aoNode`, `envNode`, `positionNode` (local vertex displacement), `vertexNode`/`fragmentNode` (full stage override), `outputNode` (post-lighting vec4), `depthNode`, `backdropNode`/`backdropAlphaNode` (refraction of what is behind), `lightsNode` (`lights([a, b])` to restrict lights), `castShadowNode`, `receivedShadowNode`, `castShadowPositionNode`, `receivedShadowPositionNode`, `maskNode`, `maskShadowNode`, `mrtNode`. Physical extras: `clearcoatNode`, `clearcoatRoughnessNode`, `clearcoatNormalNode`, `sheenNode`, `sheenRoughnessNode`, `transmissionNode`, `thicknessNode`, `iorNode`, `iridescenceNode`, `iridescenceIORNode`, `iridescenceThicknessNode`, `specularColorNode`, `specularIntensityNode`, `anisotropyNode`, `dispersionNode`. `PointsNodeMaterial`: `sizeNode`, `rotationNode`, `scaleNode`; `SpriteNodeMaterial`: `rotationNode`, `scaleNode`, `positionNode`. Lines: `Line2NodeMaterial` with `dashScaleNode` etc. Node slots override the classic property; `materialColor`, `materialRoughness`, `materialOpacity`… nodes read the classic properties so you can combine (`material.colorNode = materialColor.mul(myMask)`).

Minimal example, animated fresnel rim on a standard PBR material:

```js
const rimColor = uniform(new THREE.Color(0x44aaff));
const rimPower = uniform(3);
const fresnel = Fn(() => {
  const viewDir = positionView.negate().normalize();
  return normalView.dot(viewDir).saturate().oneMinus().pow(rimPower);
});
const mat = new THREE.MeshStandardMaterial({ color: 0x222222, roughness: 0.4 });
mat.emissiveNode = rimColor.mul(fresnel()).mul(sin(time.mul(2)).mul(0.5).add(0.5));
```

## Compute in one screen

```js
import { Fn, instancedArray, instanceIndex, hash, float, vec3, deltaTime } from 'three/tsl';
const COUNT = 100_000;
const positions = instancedArray(COUNT, 'vec3');      // StorageBufferAttribute wrapper
const velocities = instancedArray(COUNT, 'vec3');

const init = Fn(() => {
  const p = positions.element(instanceIndex);
  p.assign(vec3(hash(instanceIndex), hash(instanceIndex.add(1)), hash(instanceIndex.add(2))).sub(0.5).mul(10));
  velocities.element(instanceIndex).assign(vec3(0));
})().compute(COUNT);

const update = Fn(() => {
  const p = positions.element(instanceIndex);
  const v = velocities.element(instanceIndex);
  v.addAssign(vec3(0, -9.8, 0).mul(deltaTime));
  p.addAssign(v.mul(deltaTime));
  If(p.y.lessThan(-5), () => { p.y.assign(5); v.assign(vec3(0)); });
})().compute(COUNT);

await renderer.computeAsync(init);                     // once
const mat = new THREE.SpriteNodeMaterial();
mat.positionNode = positions.toAttribute();   // storage as vertex attribute; .element(instanceIndex) in a vertex stage needs maxStorageBuffersInVertexStage
const sprites = new THREE.Sprite(mat); sprites.count = COUNT; scene.add(sprites);
renderer.setAnimationLoop(() => { renderer.compute(update); renderer.render(scene, camera); });
```

Workgroup size defaults to 64; pass `[size]` as second arg of `.compute()`. `renderer.compute(node, [x, y, z])` takes workgroup counts, not invocations, and since r187 only for nodes built with `.computeKernel(workgroupSize)`: passing any dispatch size for a `.compute(count)` node throws. Read back with `await renderer.getArrayBufferAsync(positions.value)` (rarely, never per frame). `Fn.once()` is build-time memoization, not a run-once dispatch: dispatch init explicitly once. The WebGL 2 fallback runs compute as transform feedback: 1D numeric counts only, no storage textures, atomics, barriers or indirect dispatch; see `references/compute.md`.

## Post-processing in one screen

```js
import { pass, mrt, output, emissive } from 'three/tsl';
import { bloom } from 'three/addons/tsl/display/BloomNode.js';

const pipeline = new THREE.RenderPipeline(renderer);   // `PostProcessing` is the deprecated r182 name (alias, warns)
const scenePass = pass(scene, camera);
scenePass.setMRT(mrt({ output, emissive }));
const beauty = scenePass.getTextureNode('output');
const glow = bloom(scenePass.getTextureNode('emissive'), 1.0, 0.5, 0.0);
pipeline.outputNode = beauty.add(glow);
renderer.setAnimationLoop(() => pipeline.render());   // replaces renderer.render
```

`pipeline.outputColorTransform = true` (default) applies tone mapping + sRGB at the end; set false and call `renderOutput(node)` yourself when you need effects after tone mapping (LUT, grain). Effects live in `three/addons/tsl/display/*Node.js` (bloom, gtao, ssr, ssgi, dof, traa, fxaa, smaa, film, lut3D, outline, godrays, chromaticAberration, pixelation...). Full catalog, ordering rules and MRT recipes: `references/post-processing-webgpu.md`.

## Reference map

| Need | Read |
|---|---|
| Syntax and every function grouped by purpose, type rules, top mistakes | `references/tsl-cheatsheet.md` |
| Exact signature/description of any TSL export (alphabetical, 658 entries; grep it: `grep -n "^### \.gtao\|^### \.mx_noise" tsl-reference.md`) | `references/tsl-reference.md` |
| Official TSL guide, 82 sections (intro, syntax, control flow, stages, lifecycle, inputs, accessors, lighting, scene, render pipeline, utilities, display, materialX, context, raymarching, native WGSL/GLSL, transpiler) | `references/tsl-guide/INDEX.md` then the section file |
| NodeMaterial family, every slot, lighting models, instancing/batching with nodes, porting GLSL/onBeforeCompile to TSL, 10 material recipes | `references/node-materials.md` |
| WebGPURenderer constructor options, init, backends, render targets/MRT, readback, timestamps, clipping, XR, limitations vs WebGLRenderer | `references/webgpu-renderer.md` |
| Compute: storage buffers/textures, atomics, barriers, indirect draw, ping-pong, sorting, 6 worked examples, perf | `references/compute.md` |
| RenderPipeline (ex PostProcessing) class, pass/mrt/renderOutput, every effect node with params and cost, cinematic and mobile stacks | `references/post-processing-webgpu.md` |
| All 243 WebGPU examples annotated with the technique each shows | `references/examples-webgpu.md` |
| Class docs for `Renderer`, `*Node`, `*NodeMaterial`, `StorageBufferAttribute` etc. | `../threejs/references/api/<Name>.md` or `python3 ../threejs/scripts/api.py <Name>` |

## Porting checklist (GLSL / ShaderMaterial / Shadertoy → TSL)

1. Uniforms → `uniform()`; `iTime` / `uTime` → the built-in `time` node (no CPU timer needed). If the time must be driven from JS, use `uniform(0)` updated from the `setAnimationLoop` timestamp or `THREE.Timer`; never `THREE.Clock`, deprecated since r183; `iResolution` → `screenSize`; `gl_FragCoord.xy / iResolution` → `screenUV` (normalized [0,1], origin per backend handled for you; use `uv()` for mesh UVs, `screenCoordinate` for pixels).
2. Varyings → compute in a `Fn` and wrap in `varying()`/`vertexStage()`.
3. `gl_Position` override → `material.vertexNode`; normally just set `positionNode` (local space) instead.
4. Fragment output → `colorNode` (lit) or `fragmentNode` (unlit raw vec4) or `outputNode`.
5. GLSL control flow → `If/ElseIf/Else`, `Loop({ start, end }, ({ i }) => ...)`, `Break()`, `Continue()`, `Discard()`.
6. Keep native code only when needed: `wgslFn` / `glslFn` with explicit types, or the `Transpiler` addon (GLSL → TSL source).
7. Verify every function name in `tsl-reference.md`; several were renamed in the r160-r180 window (pre-r170 tutorials use `tslFn`, `timerLocal`, `cond`, `storageObject`; r187 names are `Fn`, `time`, `select`, `storage().setPBO(true)`). The reference is the only source of truth for signatures.
