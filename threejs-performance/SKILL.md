---
name: threejs-performance
description: Diagnose and fix three.js (r187) performance problems and design scenes that stay fast: low FPS, jank, stutter on load, high draw calls, too many objects, GPU/CPU bottlenecks, memory leaks and growing `renderer.info.memory`, slow mobile, thermal throttling, large glTF files, texture memory, shadow cost, post-processing cost, rendering only when needed, OffscreenCanvas workers, InstancedMesh vs BatchedMesh vs merged geometry, LOD, frustum culling, compute-based particles. Use whenever a user mentions FPS, "laggy", "slow", "optimize", "thousands of objects", "draw calls", "memory", "dispose", "profile", "Spector", "stats.js", or asks how to scale a three.js scene, even if they do not say "performance". Pair with the `threejs` core skill (API lookup) and `threejs-tsl-webgpu` for compute/WebGPU specifics.
---

# three.js r187 performance

Performance work is diagnosis first, technique second. Most three.js slowness is one of five bottlenecks, each with a different fix. Measure, name the bottleneck, then pick from the table. Never apply "optimizations" blind; instancing a scene that is fill-rate bound does nothing.

## 1. Measure (2 minutes, always)

```js
import Stats from 'three/addons/libs/stats.module.js';   // FPS/ms panel
const stats = new Stats(); document.body.append(stats.dom);
// in loop: stats.update();
console.log(renderer.info.render);   // { calls, triangles, points, lines, frame }
console.log(renderer.info.memory);   // { geometries, textures }  (WebGL also: programs)
```

- WebGPURenderer: `renderer.inspector = new Inspector()` (`three/addons/inspector/Inspector.js`) gives per-pass GPU timings, memory, parameters; `new WebGPURenderer({ trackTimestamp: true })` enables GPU timestamp queries, read via `await renderer.resolveTimestampsAsync()` and `renderer.info.render.timestamp` / `renderer.info.compute.timestamp`.
- Chrome DevTools Performance panel: long yellow (scripting) frames = CPU bound; GPU track saturated = GPU bound. Quick test: shrink the window to a quarter. FPS rises → fill-rate/fragment bound. Unchanged → CPU/draw-call or vertex bound.
- `renderer.info.render.calls` is the number of draw calls per frame. Rule of thumb: desktop fine under ~1000, mobile under ~200-300. `triangles` over a few million on mobile is vertex bound.

## 2. Bottleneck → fix table

| Symptom | Bottleneck | Fix (in order of payoff) |
|---|---|---|
| Many `calls`, CPU-bound frames, lots of small meshes | Draw calls / state changes | `InstancedMesh` (same geometry+material), `BatchedMesh` (different geometries, one material), `mergeGeometries`, share materials, `SceneOptimizer` auto-batching; `object.static = true` on WebGPURenderer |
| Few calls but GPU busy, improves at smaller resolution | Fill rate / fragment | cap `setPixelRatio(Math.min(dpr, 2))` (1-1.5 on mobile), cheaper material (`MeshLambert`/`MeshBasic` where unlit), fewer transparent overlapping layers (overdraw), lower shadow map size, half-res post-processing, no MSAA + FXAA instead |
| High `triangles`, slow with high-poly models | Vertex | LOD, `SimplifyModifier` or Draco/meshopt-simplified assets offline, cull with `frustumCulled` and tight bounding spheres, fewer shadow casters (shadow pass re-renders geometry) |
| Stutter on first render / when objects appear | Shader compile + upload | `await renderer.compileAsync(scene, camera)` after loading, `renderer.initTexture(tex)`, KTX2 textures (no decode on main thread), `ImageBitmapLoader`, preload with `LoadingManager` |
| Periodic hitches, memory grows, GC spikes | JS allocation / leaks | no `new Vector3()` in loops (reuse temps), `dispose()` geometry/material/texture/render targets, remove listeners, check `renderer.info.memory` stays flat |
| Fine on desktop, bad on phone | All of the above plus thermal | pixel ratio 1-1.5, 1 shadow light max at 1024, no transmission/clearcoat stacks, KTX2 textures, `powerPreference: 'high-performance'`, render on demand when static |
| Slow only while moving thousands of things | CPU simulation | move to GPU: compute shaders (WebGPURenderer, `instancedArray` + `Fn().compute()`), or `DataTexture` + vertex shader; update matrices in bulk with `setMatrixAt` + single `needsUpdate` |

## 3. The ten rules of a fast three.js scene

1. **One draw call per material, not per object.** `InstancedMesh` for repeated geometry (grass, trees, particles, UI), `BatchedMesh` when geometries differ but material is shared. Both support raycasting (`instanceId`/`batchId`) and per-instance color. With `BatchedMesh`, decide its two per-frame CPU flags explicitly: keep `perObjectFrustumCulled` on when the camera sees only part of the batch, turn `sortObjects` off for opaque batches with little overdraw (details in `references/draw-calls-and-geometry.md`).
2. **Static things do not update.** `object.matrixAutoUpdate = false` after placing; `scene.matrixWorldAutoUpdate = false` + manual `updateMatrixWorld()` for fully static scenes; `renderer.shadowMap.autoUpdate = false` and set `needsUpdate = true` only when a caster moves.
3. **Render only when something changed.** Controls `change` event + `requestRenderIfNotRequested()` pattern for viewers, editors, configurators. Cuts GPU/battery to near zero.
4. **Texture memory is width × height × 4 × 1.33.** 4096² RGBA = 89 MB. Use 1024-2048 for most maps, KTX2 (UASTC for normal maps, ETC1S for albedo) via `KTX2Loader`, `generateMipmaps` on, `anisotropy` ≤ 8 unless needed.
5. **Shadows are the most expensive checkbox.** Each shadow-casting light re-renders every caster. One directional light with a tight `shadow.camera` box and 1024-2048 map; `CSM` only for large outdoor scenes; `PointLight` shadows cost 6 passes.
6. **Transparency = overdraw + sorting.** Prefer `alphaTest` / `alphaHash` cutouts, `depthWrite: false` for additive particles, keep transparent object count small, limit `transmission` (it renders the scene to a texture first).
7. **Post-processing at the right resolution.** Bloom/AO/DOF at half resolution; one AA method (MSAA via `antialias: true` or TRAA/FXAA, not both); `HalfFloatType` targets only when HDR is needed.
8. **Never allocate per frame.** Module-level `_v = new THREE.Vector3()` temps, `getWorldPosition(_v)`, reuse `Raycaster`, avoid `array.map` in the loop, avoid `traverse` per frame (cache lists).
9. **Dispose what you remove.** `geometry.dispose()`, `material.dispose()` (and every texture on it), `renderTarget.dispose()`, `controls.dispose()`, `renderer.dispose()` on teardown. Use the traverse helper in `references/textures-and-memory.md`. GLTFLoader textures are often `ImageBitmap`s: `texture.dispose()` does not free them, `texture.source.data.close?.()` does, but only close a bitmap no other page or cache still uses; a closed bitmap cannot be uploaded again, so a shared texture would break. In an SPA, make teardown available before any `await`: if the user leaves while a GLB is still loading, a cancel flag (or `AbortController` passed to the loader manager) must stop the pending load and dispose whatever arrives late, or that scene leaks.
10. **Load smart.** Draco or meshopt compressed glTF, KTX2 textures, `ImageBitmapLoader` / `createImageBitmap` for off-thread decode, `compileAsync` before the first frame, progressive loading with `LoadingManager`; heavy sim or whole renderer in a Worker via `OffscreenCanvas`.

## Quick wins snippet

```js
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.shadowMap.enabled = true;
renderer.shadowMap.autoUpdate = false;       // WebGL: set renderer.shadowMap.needsUpdate = true when casters move
// WebGPURenderer: shadowMap has only enabled/type/transmitted; use light.shadow.autoUpdate = false + light.shadow.needsUpdate = true
sun.shadow.mapSize.set(2048, 2048);
sun.shadow.camera.left = -20; sun.shadow.camera.right = 20;   // tight fit; check with CameraHelper
sun.shadow.camera.top = 20;   sun.shadow.camera.bottom = -20;
sun.shadow.camera.near = 1;   sun.shadow.camera.far = 60;

await renderer.compileAsync(scene, camera);   // after assets load, before first frame

// instancing
const mesh = new THREE.InstancedMesh(geometry, material, N);
mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);   // only if updated every frame
const m = new THREE.Matrix4();
for (let i = 0; i < N; i++) { m.setPosition(x(i), y(i), z(i)); mesh.setMatrixAt(i, m); }
mesh.instanceMatrix.needsUpdate = true;
mesh.computeBoundingSphere();                 // for correct frustum culling
```

## Reference map

| Need | Read |
|---|---|
| Diagnosing with `renderer.info`/Inspector, InstancedMesh and BatchedMesh in depth, merging, LOD, culling, bounding volumes, matrix update costs, sorting, `compileAsync`, the manual's "lots of objects" walkthroughs | `references/draw-calls-and-geometry.md` |
| GPU memory math, KTX2/Basis, atlases, upload hitches, render target cost, PMREM, disposal discipline, allocation-free loops | `references/textures-and-memory.md` |
| Render on demand, pixel ratio and dynamic resolution, OffscreenCanvas worker, shadow and light budgets, overdraw/transparency, post-processing cost, mobile, measuring (timestamps, Inspector, stats) | `references/rendering-strategies.md` |
| Shader cost, ShaderMaterial recompile pitfalls, UBOs, TSL/WebGPU perf (uniform groups, storage, compute, indirect draw, readbacks), GPU picking, particles strategies | `references/shader-and-webgpu-perf.md` |
| API page for any class (`InstancedMesh`, `BatchedMesh`, `LOD`, `SceneOptimizer`, `KTX2Loader`, `Renderer`...) | `python3 ../threejs/scripts/api.py <Name>` |
| Compute shaders and storage buffers in detail | `../threejs-tsl-webgpu/references/compute.md` |

Official examples worth copying: `webgl_instancing_performance`, `webgl_mesh_batch`, `webgpu_mesh_batch`, `webgpu_instance_mesh`, `webgl_lod`, `webgl_worker_offscreencanvas`, `webgpu_compute_particles`, `webgpu_lights_clustered`, `webgl_loader_texture_ktx2` (`https://threejs.org/examples/#<name>`).

## Reporting back to the user

State the measured numbers before and after (fps, `calls`, `triangles`, memory), which bottleneck you identified and why, and what you deliberately did not do (e.g. "did not instance: only 40 draw calls, the cost is the 4K shadow map"). If you cannot measure in their environment, say so and give them the measuring snippet above.
