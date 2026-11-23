# Rendering Strategies: Frame Budget, Shadows, Lights, Overdraw, Post-processing, Measuring (three.js r187)

## When to read this

Read when the GPU is the bottleneck (fill rate, overdraw, shadows, post-processing, too many lights), when battery / heat matters, when the canvas must stay responsive while the main thread is busy, or when you need to measure where frame time goes.

Numbers marked "rule of thumb" are heuristics, not API facts. The bottleneck classification below decides which section applies.

## Table of contents

1. Find the bottleneck first
2. Rendering on demand
3. Pixel ratio and dynamic resolution
4. Animation loop: `setAnimationLoop` vs `requestAnimationFrame`
5. OffscreenCanvas in a worker
6. Shadows budget
7. Light count budget (and WebGPU tiled / clustered lighting)
8. Overdraw and transparency
9. Post-processing cost
10. Depth buffer, near/far, fog, layers
11. Renderer creation options (`powerPreference`, `precision`, ...)
12. Mobile-specific advice
13. Measuring
14. See also

---

## 1. Find the bottleneck first

| Symptom | Likely bottleneck | Go to |
|---|---|---|
| FPS rises a lot when the canvas is shrunk (`setSize` small / pixel ratio 0.5) | Fragment / fill rate: overdraw, expensive shaders, post-processing, shadow resolution, MSAA | sections 3, 6, 8, 9; `shader-and-webgpu-perf.md` |
| FPS unchanged when shrinking, JS main thread busy in `render` | CPU draw-call / state-change cost | `draw-calls-and-geometry.md` |
| FPS unchanged, GPU busy, millions of triangles | Vertex throughput | LOD, simplification (`draw-calls-and-geometry.md`) |
| Periodic hitches, flat average | GC pressure or shader compile / texture upload | `textures-and-memory.md` (sections 6 and 12), `draw-calls-and-geometry.md` section 14 |
| Fine at start, degrades over minutes | Leak, thermal throttling on mobile | `textures-and-memory.md` section 10; section 12 below |
| Idle scene burns battery | Rendering continuously when nothing changes | section 2 |

Browsers cap rAF at the display refresh; 60 fps means about 16.6 ms per frame, 120 Hz about 8.3 ms. The GPU and CPU work in a pipeline: the slower stage defines FPS.

---

## 2. Rendering on demand

If nothing animates, a rAF loop only burns power. Render once and again only on change (manual: Rendering on Demand). Triggers: texture/model finished loading, data arrived, UI setting changed, camera moved, resize, tween progress.

```js
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

let renderRequested = false;

function render() {
  renderRequested = false;
  if (resizeRendererToDisplaySize(renderer)) {
    const canvas = renderer.domElement;
    camera.aspect = canvas.clientWidth / canvas.clientHeight;
    camera.updateProjectionMatrix();
  }
  controls.update();                 // needed for damping
  renderer.render(scene, camera);
}

function requestRenderIfNotRequested() {
  if (!renderRequested) {
    renderRequested = true;
    requestAnimationFrame(render);
  }
}

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;       // needs controls.update() each frame while damping
controls.addEventListener('change', requestRenderIfNotRequested);
window.addEventListener('resize', requestRenderIfNotRequested);
texture = loader.load(url, requestRenderIfNotRequested);   // render when a texture finishes
gui.add(obj, 'x').onChange(requestRenderIfNotRequested);

render();                            // first frame
```

Details:

- `OrbitControls` dispatch a `change` event whenever the camera changes. With `enableDamping`, calling `render()` directly from `change` would recurse (the render calls `controls.update()`, which emits `change` again) and the manual fixes it with the "request if not requested" pattern above: the flag coalesces multiple triggers into one frame, and the damping tail keeps requesting frames until the motion decays. `controls.update()` returns a boolean (`true` when the camera moved), which you can use to request another frame.
- Animations in an on-demand app: drive them with a manager that reports "still running" and keeps requesting frames (the manual's `TweenManager.update()` returns `numTweensRunning > 0` and the render function calls `requestRenderIfNotRequested()` while true). When the last animation ends, rendering stops.
- Every external change must request a frame: loaders (`onLoad`), WebSocket data, GUI `onChange`, video textures (a playing `VideoTexture` makes this a continuous render app), XR (XR needs `setAnimationLoop`, see section 4).
- Static scene extras: also stop shadow updates (section 6), and `scene.matrixWorldAutoUpdate = false` (see `draw-calls-and-geometry.md`) while nothing moves.
- `preserveDrawingBuffer: false` (default) clears the canvas after compositing. In an on-demand app, take screenshots by calling `render()` right before `canvas.toBlob` (manual: Tips), not by enabling `preserveDrawingBuffer` (it can cost performance and memory on some platforms; rule of thumb).
- Pause when hidden: browsers throttle rAF in background tabs automatically; for `setAnimationLoop` you can also stop on `document.visibilitychange`. `Timer.connect(document)` avoids a giant delta when the tab returns (see `textures-and-memory.md`).

---

## 3. Pixel ratio and dynamic resolution

Fragment cost scales with `pixelRatio^2`. A phone with `devicePixelRatio = 3` renders 9 CSS-pixel-equivalent samples per pixel versus 1.

```js
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));   // common cap
renderer.setSize(canvasWidth, canvasHeight, false);              // false: do not touch CSS size
```

- Cap at 2 for desktop / tablets, 1.5 or even 1 for weak mobile GPUs, heavy post-processing, or large canvases (rule of thumb). `setPixelRatio` resizes the drawing buffer if needed. `getPixelRatio()` and `getDrawingBufferSize(target)` (WebGLRenderer) report the real size.
- Do not call `setSize(..., true)` per frame; resize only when the displayed size changes (`resizeRendererToDisplaySize` from the manual, which compares `canvas.width` with `clientWidth * pixelRatio` effectively).

Dynamic resolution scaling (a pattern, not a built-in API): measure frame time and lower the pixel ratio when over budget, raise it back slowly when comfortably under.

```js
let ratio = Math.min(devicePixelRatio, 2);
const MIN = 0.6, MAX = Math.min(devicePixelRatio, 2);
let avg = 16.7;
let last = performance.now();
let cooldown = 0;

function tick(now) {
  const dt = now - last; last = now;
  avg = avg * 0.95 + dt * 0.05;                       // smoothed frame time
  if (cooldown-- <= 0) {
    if (avg > 20 && ratio > MIN) { ratio = Math.max(MIN, ratio - 0.25); apply(); }
    else if (avg < 14 && ratio < MAX) { ratio = Math.min(MAX, ratio + 0.125); apply(); }
  }
}
function apply() {
  cooldown = 60;                                       // hysteresis: wait 60 frames
  renderer.setPixelRatio(ratio);                       // reallocates drawing buffer (and composer targets if you resize them)
  composer?.setPixelRatio(ratio);                      // EffectComposer (WebGL)
}
```

Caveats: each change reallocates buffers (a hitch), so step in coarse increments with a cooldown, never every frame. Frame time measured in rAF reflects the display refresh cap: if the GPU is 3x faster than needed, `avg` stays about 16.7, so only raise the ratio when `avg` is under refresh and you have headroom from timestamps (section 13). Alternatives that avoid reallocation: render the heavy pass at lower resolution only (`PassNode.setResolutionScale(scale)` for WebGPU post-processing; `BloomNode.setResolutionScale`; half-res passes in `EffectComposer` via per-pass `setSize`), and `setViewport` / `setScissor` to render into a sub-rectangle of a fixed-size buffer.

---

## 4. `setAnimationLoop` vs `requestAnimationFrame`

```js
// WebGLRenderer
renderer.setAnimationLoop((time, frame) => { ... renderer.render(scene, camera); });
renderer.setAnimationLoop(null);   // stop

// WebGPURenderer: initialize first (render() throws before init in r187)
await renderer.init();
renderer.setAnimationLoop(animate);
```

- The docs advise defining the loop with `setAnimationLoop` rather than manual rAF for best compatibility: it is required for WebXR (the XR session has its own frame callback, not `window.requestAnimationFrame`) and works inside workers.
- For on-demand rendering use plain `requestAnimationFrame` as above, or `setAnimationLoop` that you null out when idle.
- WebGPURenderer: `render()` is synchronous but throws if called before `await renderer.init()` (`Renderer.render` in r187). `renderAsync`, `clearAsync`, `hasFeatureAsync`, `initTextureAsync`, `waitForGPU` are deprecated. `setAnimationLoop` returns a promise and handles init for you.
- Multiple `render` calls in one frame (post-processing, multi-view): `renderer.info.autoReset = false` and `renderer.info.reset()` per frame to get meaningful totals.
- `renderer.autoClear = false` when you composite several renders (`clear` manually; `autoClearDepth` etc.), saving redundant clears.

---

## 5. OffscreenCanvas in a worker

Moves rendering (and asset decode / parse) off the main thread so UI, layout and input stay responsive. Cost: no DOM in the worker; input and sizing must be forwarded. Browser support varies by version (the manual, when written, said Chrome only; the three.js example gates Safari on version >= 17 because older Safari lacks OffscreenCanvas with a WebGL context, and links caniuse). Feature-detect `canvas.transferControlToOffscreen`, keep a main-thread fallback, and verify support for your targets. WebGL via `OffscreenCanvas` is the path documented by the manual.

Main thread:

```js
const canvas = document.querySelector('#c');

if (canvas.transferControlToOffscreen) {
  const offscreen = canvas.transferControlToOffscreen();
  const worker = new Worker(new URL('./worker.js', import.meta.url), { type: 'module' });
  worker.postMessage({
    type: 'init',
    canvas: offscreen,
    width: canvas.clientWidth,
    height: canvas.clientHeight,
    pixelRatio: window.devicePixelRatio,
  }, [offscreen]);                       // transfer list: ownership moves to the worker

  const sendSize = () => worker.postMessage({
    type: 'size',
    width: canvas.clientWidth,
    height: canvas.clientHeight,
  });
  new ResizeObserver(sendSize).observe(canvas);
  // forward input: see "Input" below
} else {
  startOnMainThread(canvas);             // fallback: same code path, canvas is the real element
}
```

Worker (`worker.js`):

```js
import * as THREE from 'three';

const state = { width: 300, height: 150 };
let renderer, camera, scene;

const handlers = { init, size };
self.onmessage = (e) => {
  const fn = handlers[e.data.type];
  if (typeof fn !== 'function') throw new Error('no handler for type: ' + e.data.type);
  fn(e.data);
};

function init({ canvas, width, height, pixelRatio }) {
  state.width = width; state.height = height;
  renderer = new THREE.WebGLRenderer({ antialias: true, canvas });   // canvas = OffscreenCanvas
  renderer.setPixelRatio(pixelRatio);
  // ... build scene; load textures with ImageBitmapLoader (no DOM Image in workers)
  requestAnimationFrame(render);                                      // self.requestAnimationFrame
}

function size(data) { state.width = data.width; state.height = data.height; }

function resizeRendererToDisplaySize() {
  const canvas = renderer.domElement;                                 // OffscreenCanvas: no clientWidth
  const w = state.width * renderer.getPixelRatio() | 0;
  const h = state.height * renderer.getPixelRatio() | 0;
  if (canvas.width !== w || canvas.height !== h) {
    renderer.setSize(state.width, state.height, false);               // false: never touch style (none in worker)
    return true;
  }
  return false;
}

function render(time) {
  if (resizeRendererToDisplaySize()) {
    camera.aspect = state.width / state.height;
    camera.updateProjectionMatrix();
  }
  renderer.render(scene, camera);
  requestAnimationFrame(render);
}
```

Key points from the manual and `examples/jsm/offscreen/*`:

- `canvas.transferControlToOffscreen()` returns the `OffscreenCanvas`; it must be listed in `postMessage`'s transfer array. After transfer the main thread cannot draw to or resize that canvas via its drawing buffer attributes.
- Workers cannot read `clientWidth` / `clientHeight`: send size messages (the manual's `size` handler keeps `state.width`/`state.height`). Always `setSize(w, h, false)`.
- Loading: use `ImageBitmapLoader` (with `setOptions({ imageOrientation: 'flipY' })`) and `CanvasTexture(imageBitmap)`; `TextureLoader`/`ImageLoader` need the DOM. The repo example does exactly this in `examples/jsm/offscreen/scene.js`. Decode and parse happen in the worker as well ("possibly less jank while the page loads").
- Input: the worker has no DOM events. The manual builds, on the main thread, an `ElementProxy` that registers an id with the worker (`makeProxy` message) and forwards a whitelist of event properties (`clientX/clientY/pointerId/button/ctrlKey/...`, wheel `deltaX/deltaY`, keydown `keyCode`) for `contextmenu`, `mouse*`, `pointer*`, `touch*`, `wheel` and `keydown` via `postMessage({type: 'event', id, data})`. In the worker an `ElementProxyReceiver extends EventDispatcher` stands in for the `HTMLElement`: it re-dispatches the data, adds no-op `preventDefault`/`stopPropagation` to each event, a no-op `focus()`, `clientWidth`/`clientHeight` getters and `getBoundingClientRect()` built from `left/top/width/height` that the main page sends in `size` messages (the manual does not handle the canvas moving, only resizing). Pass the receiver as the `inputElement` to `new OrbitControls(camera, inputElement)`; picking code also listens on `inputElement` and uses its rect, so picking runs inside the worker.
- Fallback: when `transferControlToOffscreen` is missing, run the same module on the main thread, passing the real canvas as `canvas` and as the controls' `inputElement`. Structure code as `init(data)` taking `{ canvas, inputElement }` so both paths share it.
- Interplay: on-demand rendering inside the worker is fine (`requestAnimationFrame` exists in dedicated workers in modern browsers; the repo example falls back for old Firefox).
- Data heavy apps: keep simulation in another worker and transfer typed arrays (zero-copy with transferables or `SharedArrayBuffer` with cross-origin isolation headers) to the render worker. `WorkerPool` (`three/addons/utils/WorkerPool.js`) manages a pool for batch jobs such as geometry building.
- Debugging: errors inside workers appear in the worker's DevTools context; add `self.onerror` logging.
- Demo: `webgl_worker_offscreencanvas.html` (spawns `jsm/offscreen/offscreen.js`, passes `drawingSurface`, `width`, `height`, `pixelRatio`, `path`, and includes a "jank" loop on the main thread to prove the worker stays smooth).

---

## 6. Shadows budget

A shadow-casting light renders the casters into a depth map (an extra scene pass) every frame, then every lit fragment samples the map. Cost = (casters' draw calls + vertices) x (passes) + shadow map fill + per-fragment filtering.

Pass counts (manual and shadow classes):

| Light | Shadow passes | Notes |
|---|---|---|
| `DirectionalLight`, `SpotLight` | 1 | cheapest |
| `PointLight` | 6 (one per cube face) | manual: "much slower since the entire scene must be drawn 6 times" |
| CSM (cascaded) | `cascades` (default 3) | one directional light per cascade (`CSM` for WebGLRenderer, `CSMShadowNode` for WebGPURenderer) |
| `TileShadowNode` | `tilesX * tilesY` (default 2 x 2) | WebGPU; splits one shadow map into tiles each with its own camera; no `VSMShadowMap` support |

Budget rules (rule of thumb unless stated):

1. Enable shadows globally only if needed: `renderer.shadowMap.enabled = true` (default `false`). One shadow-casting directional light is the usual budget for mobile; avoid shadow-casting point lights.
2. `light.shadow.mapSize` default is 512 x 512; values must be powers of two (docs). Memory and fill grow quadratically: 1024 is common, 2048 for hero directional lights, 4096 only on strong GPUs. Prefer fitting the frustum over raising the size.
3. Tight shadow frustum: for directional / spot lights set `light.shadow.camera.left/right/top/bottom/near/far` to enclose only what needs shadows (manual: "smaller means better look" for the same map size). Use `CameraHelper(light.shadow.camera)` to visualize. A tight box raises texel density for free and lets the renderer cull casters outside it (`LightShadow.getFrustum()` is used to cull).
4. Limit casters and receivers: `mesh.castShadow` / `mesh.receiveShadow` default `false`; set `castShadow` only on objects that matter (skip small props, far objects, and large flat ground: make ground `receiveShadow` only, as the manual does). Fewer casters means fewer shadow-pass draws. Each caster is also drawn with the depth material: material `side`/`shadowSide` and `alphaTest`/clipping change that pass.
5. Static scenes: render shadows once.
   ```js
   // WebGLRenderer: renderer-wide
   renderer.shadowMap.autoUpdate = false;
   renderer.shadowMap.needsUpdate = true;     // update on next render only; then it stays cached
   // per light (both renderers): LightShadow.autoUpdate / needsUpdate
   light.shadow.autoUpdate = false;
   light.shadow.needsUpdate = true;           // refresh when the scene changes
   ```
   `WebGLShadowMap` skips a shadow when `autoUpdate === false && needsUpdate === false`; the flag resets after the update. WebGPURenderer's `renderer.shadowMap` config has `enabled`, `transmitted`, `type` only, so use the per-light flags there (source: `ShadowNode.js` checks `shadow.needsUpdate || shadow.autoUpdate`). Common hybrid: static shadow for the world (baked into one light), dynamic shadow only for the moving hero via a second light with a small tight frustum.
6. Filter type (`renderer.shadowMap.type`): `BasicShadowMap` (hard, cheapest), `PCFShadowMap` (default, filtered), `VSMShadowMap` (soft, uses extra blur passes each update controlled by `shadow.radius` and `shadow.blurSamples`, and a second map: heavier, light-bleeding artifacts). `PCFSoftShadowMap` is deprecated since r186 (use `PCFShadowMap`). `light.shadow.radius` blurs edges (values above 1 take effect for PCF/VSM depending on type; very high values band without a larger map). Avoid VSM on mobile.
7. Bias: tune `shadow.bias` and `shadow.normalBias` once to remove acne; do not compensate by raising map size.
8. `light.shadow.dispose()` / remove light and dispose the map when removing shadowed lights; changing the number of shadow-casting lights after the first render changes the shader (new program) so do it at load time.
9. For lots of static lighting use baked lightmaps / AO maps ("lightmaps and or ambient occlusion maps to pre-compute the effects of lighting offline", manual) or `ProgressiveLightMap` (`webgpu_shadowmap_progressive.html`). The manual also suggests: many lights, but only one directional light generating shadows.
10. Shadow-casting transmissive / transparent objects: `shadowMap.transmitted` (WebGPU config) enables light transmission through non-opaque materials: leave off unless required.
11. `webgl_shadowmap_performance.html` is the reference for casters count vs fps.

---

## 7. Light count budget

Forward rendering in three.js evaluates every light in every lit fragment of every lit material (per-fragment loop). Cost per fragment scales with light count x BRDF cost. Changing the number or type of lights after first render recompiles every lit material (a hitch).

Rules of thumb:

- Aim for single-digit dynamic light counts on desktop and 1 to 3 on mobile; `PointLight`/`SpotLight` cost more than directional or hemisphere/ambient; `RectAreaLight` is expensive; with WebGLRenderer it needs `RectAreaLightUniformsLib.init()` (`three/addons/lights/RectAreaLightUniformsLib.js`).
- Cheap ambient: `AmbientLight`, `HemisphereLight`, `LightProbe` (spherical harmonics), or an IBL `scene.environment` (PMREM, evaluated as one lookup) instead of many fill lights.
- Bake static lighting (lightmaps, `material.lightMap`, `aoMap`); use emissive meshes for glows; fake small lights with unlit additive sprites/decals.
- Cheaper materials: `MeshLambertMaterial` / `MeshPhongMaterial` / `MeshToonMaterial` for lighting cost much lower than `MeshStandardMaterial` / `MeshPhysicalMaterial` (physical adds clearcoat, sheen, transmission, iridescence branches that are compiled only when used, but then cost heavily; `transmission` renders an extra scene pass).
- Keep light count constant at runtime: fade intensities to 0 instead of adding/removing lights. WebGPURenderer addon `DynamicLighting` does this for you.

WebGPURenderer lighting systems (addons, replace `renderer.lighting`):

```js
import { ClusteredLighting } from 'three/addons/lighting/ClusteredLighting.js';
import { DynamicLighting } from 'three/addons/lighting/DynamicLighting.js';

// Forward+ clustered shading: many point lights, only lights reaching each fragment cluster are evaluated
renderer.lighting = new ClusteredLighting(/* maxLights */ 1024, /* tileSize */ 32, /* zSlices */ 24, /* maxLightsPerCluster */ 64);

// Batches analytic lights into uniform arrays so light count changes do not recompile materials
renderer.lighting = new DynamicLighting({
  maxDirectionalLights: 8, maxPointLights: 16, maxSpotLights: 16, maxHemisphereLights: 4,
});
```

- `ClusteredLighting` (docs): "suitable for 3D scenes with many point lights and real depth complexity": partitions the view frustum into a 3D grid (XY tile size in pixels x exponential Z slices) and lights are assigned to clusters; fragment cost depends on lights per cluster, not total lights. Tune `tileSize` (smaller = finer cull, more cluster overhead), `zSlices`, and `maxLightsPerCluster` (overflow lights are dropped). Example: `webgpu_lights_clustered.html`. Only point lights are documented as clustered ("Maximum number of point lights").
- `DynamicLighting`: trades a fixed worst-case per-fragment cost (arrays sized by `max*`) for no recompile when lights come and go; set the maxima to what you really use.
- Both are WebGPURenderer (node-based) only. The r187 examples are `webgpu_lights_clustered.html` and, new in r187, `webgpu_lights_clustered_city.html` (there is no `webgpu_lights_tiled.html`).
- Light shadows remain separate: clustering does not make shadow-casting point lights cheap.

---

## 8. Overdraw and transparency

Overdraw = shading the same pixel multiple times. Opaque geometry rendered front-to-back lets the depth test reject hidden fragments before the fragment shader ("early-z"); blended transparent geometry cannot, and every layer costs a full shading plus a framebuffer read-modify-write.

Sorting behavior (source `WebGLRenderLists`):

- Opaque list: sorted by `groupOrder`, `renderOrder`, material id, then z front-to-back. So three.js already minimizes state changes first, then overdraw within the same material. Keep large occluders opaque and shared-material.
- Transparent list: sorted `groupOrder`, `renderOrder`, then z back-to-front, per object (object origin, not per triangle; manual: sorting individual triangles "would be extremely slow"). Intersecting or self-overlapping transparent meshes can still sort incorrectly.
- Double-sided transparent objects render in two passes (back faces then front faces) by default, which doubles draw calls; set `material.forceSinglePass = true` where the quality gain is nil (foliage cards, grass).

Cheaper alternatives to blending (`Material` docs):

| Technique | Properties | Cost / caveat |
|---|---|---|
| Alpha test (cutout) | `alphaTest = 0.5`, `transparent = false` | Opaque queue, writes depth, no sort; aliased edges. Fragment discards disable early-z for that draw (rule of thumb: still usually cheaper than blending) |
| Alpha to coverage | `alphaToCoverage = true` (needs MSAA `antialias: true`) | Smooths alphaTest edges; cost tied to MSAA sample count |
| Alpha hash | `alphaHash = true` | Stochastic opaque dither, no sorting; noisy unless TAA / TRAA denoises |
| Premultiplied / additive blend | `blending = AdditiveBlending`, `depthWrite = false` | Order-independent for additive: no sort issues; still overdraw cost |

Overdraw reducers:

1. `depthWrite = false` for particles/glows/UI so they do not occlude each other and need no strict order; `depthTest` stays true so opaque geometry still hides them. For overlays, `depthTest = false` plus `renderOrder`.
2. Particles: keep sprites small; trim texture alpha to the visible shape (use a tighter quad or mesh instead of a large square of mostly transparent pixels); limit count and size; use `Points` / instancing; fade by distance. A screen-filling smoke sprite stack of 10 layers is 10x full-screen fill (rule of thumb: this is the most common cause of mobile GPU slowness).
3. Order solid occluders first: `renderOrder` and the default opaque sorting already do this. Manual `renderOrder` on a `Group` forces all descendants together.
4. Hide hidden things: `visible = false`, fog/`camera.far`, layers, occlusion (WebGPU `renderer.isOccluded(object)`), portals/zones in indoor scenes.
5. Avoid full-screen quads with heavy shaders; avoid stacking large transparent planes (water, glass, fog volumes). `MeshPhysicalMaterial.transmission` renders the scene again into a target (`renderer.transmissionResolutionScale`, documented, can be lowered).
6. Transparent materials with `side: DoubleSide` and multiple objects at the same position (manual example of windows): split objects so three.js can sort them, and set `renderOrder` where needed.
7. `renderer.sortObjects = false` only if you set `renderOrder` for everything; otherwise artifacts. Use `setTransparentSort(fn)` for custom ordering (e.g. by priority).
8. `colorWrite = false` + `renderOrder` creates invisible occluders (Material docs) for cheap occlusion tricks.
9. Instanced / batched transparency: `BatchedMesh` sorts per instance back-to-front when `material.transparent` is true (`sortObjects` option); `InstancedMesh` does not sort instances.

---

## 9. Post-processing cost

Each full-screen pass reads and writes a screen-sized buffer. Cost = passes x pixels x shader cost x bytes per pixel. Chains of 5 to 10 passes at 4K DPR 3 are a common mobile killer.

WebGLRenderer: `EffectComposer` (`three/addons/postprocessing/EffectComposer.js`).
WebGPURenderer: `RenderPipeline` (r183+; `PostProcessing` is a deprecated alias) with TSL display nodes.

```js
// WebGPU
import * as THREE from 'three/webgpu';
import { pass, mrt, output, normalView, renderOutput } from 'three/tsl';
import { bloom } from 'three/addons/tsl/display/BloomNode.js';
import { fxaa } from 'three/addons/tsl/display/FXAANode.js';

const renderPipeline = new THREE.RenderPipeline(renderer);
const scenePass = pass(scene, camera);
scenePass.setResolutionScale(1);               // PassNode: scale relative to renderer size; lower for expensive passes

const bloomed = bloom(scenePass.getTextureNode(), 0.6 /*strength*/, 0.4 /*radius*/, 0.9 /*threshold*/);
bloomed.setResolutionScale(0.5);             // BloomNode.setResolutionScale exists; half-res blur chain

renderPipeline.outputNode = scenePass.getTextureNode().add(bloomed);
// loop: renderPipeline.render();   (not renderer.render)
```

Budget and techniques:

- Half-resolution (or lower) for blur-like effects: bloom, SSAO/GTAO (`ao()` from `GTAONode`), SSR, DOF, volumetrics, god rays. They are low-frequency; half res is a quarter of the cost. `PassNode.setResolutionScale`, `BloomNode.setResolutionScale`, `GaussianBlurNode` has a `resolutionScale` option; in `EffectComposer`, pass `Vector2(w/2, h/2)` to `UnrealBloomPass` (its `resolution` argument) and size custom passes explicitly.
- Combine passes: do tone mapping + color grading + vignette in a single shader/node chain rather than separate passes; every extra full-screen target is memory plus bandwidth.
- Skip buffers you do not need: depth/normal/velocity outputs are only requested when an effect needs them.
- MRT (multiple render targets): one geometry pass writes several attachments (color, normals, velocity, emissive). It is cheaper than re-rendering the scene per attachment, but bandwidth and memory scale with attachment count and format. `scenePass.setMRT(mrt({ output, normal: normalView }))` (`PassNode.setMRT`, `MRTNode`); for the renderer itself `renderer.setMRT(mrt)` / `getMRT()`. Use narrow formats where possible (see `shader-and-webgpu-perf.md`).
- Anti-aliasing options, cheapest to most expensive (rule of thumb on cost; characteristics from docs):

| AA | Where | Cost | Notes |
|---|---|---|---|
| FXAA | `fxaa()` node (`FXAANode`), `FXAAPass` (WebGL composer) | One cheap full-screen pass | Blurs slightly; needs sRGB input so for `RenderPipeline` set `outputColorTransform = false` and apply `renderOutput(scenePass)` first |
| SMAA | `smaa()` (`SMAANode`), `SMAAPass` | A few passes | Sharper than FXAA |
| MSAA | `new WebGLRenderer({ antialias: true })`, `new WebGPURenderer({ antialias: true, samples: 4 })`, render target `samples` | N x color + depth memory & bandwidth, resolve | Best edges for geometry, does not fix shader aliasing; with `EffectComposer` set `samples` on the composer's render target (`new WebGLRenderTarget(w, h, { samples: 4 })`) because the canvas `antialias` flag does not apply to offscreen buffers |
| TAA / TRAA | `traa()` (`TRAANode`), `TAARenderPass` | Needs velocity + history buffers, per-frame camera jitter | Docs: "MSAA must be disabled when TRAA is in use". Reduces shader aliasing and cleans alphaHash noise; ghosting on fast motion |
| SSAA | `ssaaPass` (`SSAAPassNode`), `SSAARenderPass` | Re-renders the whole scene N times | Docs: "extremely expensive"; only for stills / screenshots |

- Pick one AA technique. MSAA + bloom chain: only the main scene target needs MSAA; effect targets must not be multisampled.
- Float precision: `HalfFloatType` buffers for HDR; `UnsignedByteType` (`outputBufferType`) saves bandwidth when HDR is not needed (WebGPURenderer default is HalfFloat).
- When post-processing is on, tone mapping is applied by the output transform of the pipeline; `Material.toneMapped` is ignored with post-processing (docs). Avoid double tone mapping.
- WebGLRenderer also has `renderer.setEffects(effects)` ("sets the post-processing effects to be applied after rendering", r187 API) as a lighter path; verify its supported effect classes in the release you use.
- Update expensive effects at lower frequency when the camera is static: AO and reflections can accumulate or skip frames; with on-demand rendering (section 2) post-processing stops costing power entirely while idle.
- Dispose composer / pipeline (`dispose()`) on teardown (render targets).
- Examples: `webgl_postprocessing_*` family, `webgpu_postprocessing_*` family (the latter show node-based chains).

---

## 10. Depth buffer, near/far, fog, layers

Depth buffer options:

- `logarithmicDepthBuffer: true` (both renderers): fixes z-fighting for enormous depth ranges but writes `gl_FragDepth`, which per the WebGLRenderer docs "disables the Early Fragment Test optimization and can cause a decrease in performance". Use only when you need it.
- `reversedDepthBuffer: true` (WebGL needs `EXT_clip_control`; also an option in WebGPURenderer): documented as "more faster and accurate version than logarithmic depth buffer" because floating-point depth plus reversed mapping gives near-uniform precision without disabling early-z. Prefer it to logarithmic when supported (`renderer.capabilities.reversedDepthBuffer` tells you).
- Camera `near`/`far`: depth precision is concentrated near the near plane; the ratio far/near drives z-fighting. Raise `near` as far as the scene allows (0.1 to 1 typical) and lower `far` to the visible range. Tight ranges also improve culling and allow cheaper shadow cameras.
- Do not put coplanar surfaces: offset by a small amount, or use `material.polygonOffset` (decals) instead of precision hacks; the manual fixes the box-vs-floor z-fight by offsetting geometry.
- `depth: false` on the renderer if you never depth test (pure 2D overlay): saves memory; `stencil: false` is the default; keep it off unless needed.

Fog as a cheap depth cull:

```js
scene.fog = new THREE.Fog(0x88aacc, near, far);        // linear; FogExp2 for exponential density
camera.far = far * 1.05;                                // anything beyond far is fully fogged: cull it for free
camera.updateProjectionMatrix();
scene.background = new THREE.Color(0x88aacc);           // match fog color
```

Objects beyond `camera.far` are clipped (not drawn); with fog hiding the transition the pop-in is invisible. Fog is applied in the fragment shader of materials with `fog: true` (default); it costs a few instructions per fragment. In WebGPURenderer, fog is a node (`scene.fog` still works).

Layers for selective rendering:

```js
mesh.layers.set(1);            // only visible to cameras that have layer 1 enabled
camera.layers.enable(1);       // camera sees layer 0 and 1
minimapCamera.layers.set(1);   // sees only layer 1
raycaster.layers.set(1);       // picking filter
```

Use layers to render sub-sets per camera or pass (minimap, outlines, selective bloom, debug helpers) without moving objects around in the scene graph. Layers are a bitmask test (32 layers); checked per object per camera, extremely cheap.

---

## 11. Renderer creation options

WebGLRenderer (`WebGLRenderer.md` options):

| Option | Default | Performance note |
|---|---|---|
| `antialias` | `false` | MSAA on the default framebuffer. Turn off on weak/mobile GPUs or when using post-processing AA |
| `powerPreference` | `'default'` | `'high-performance'` asks for the discrete GPU on dual-GPU laptops; `'low-power'` favors the integrated GPU / battery. It is only a hint; set `'low-power'` for light scenes/embeds |
| `precision` | `'highp'` | `'mediump'` on mobile can speed up fragment math on some GPUs; it risks artifacts (banding, jitter in positions/UVs). Per-material override: `material.precision`. Check `renderer.capabilities.precision` / `getMaxPrecision('highp')` |
| `stencil` | `false` | Keep off unless needed |
| `depth` | `true` | Required for depth testing |
| `alpha` | `false` | Opaque canvas is cheaper to composite; transparent canvas (`alpha: true`) forces browser compositing with the page; use only when needed |
| `premultipliedAlpha` | `true` | Matches compositor expectations |
| `preserveDrawingBuffer` | `false` | Leave false (manual: needed only for painting-style apps or screenshots; can cost performance) |
| `failIfMajorPerformanceCaveat` | `false` | Set `true` to refuse software rendering and show a fallback UI |
| `logarithmicDepthBuffer` | `false` | See section 10 |
| `reversedDepthBuffer` | `false` | See section 10 |
| `outputBufferType` | `UnsignedByteType` | `HalfFloatType` only for HDR output with post-processing |

Runtime flags:

- `renderer.debug.checkShaderErrors = false` in production: skips program link/compile status checks (documented performance gain; keep enabled in development; shader errors then fail silently).
- `renderer.info.autoReset`, `renderer.sortObjects`, `renderer.shadowMap.*`, `renderer.autoClear`.
- `renderer.toneMapping`: cheap in-shader per-fragment op; skip when output goes through post-processing tone mapping.
- WebGPURenderer: `antialias`, `samples`, `forceWebGL` (WebGL2 backend fallback), `outputBufferType` (HalfFloat default; `UnsignedByteType` saves memory/bandwidth), `outputType`, `multiview` (WebXR single-pass stereo), `trackTimestamp`, `alpha` (default `true`). Custom `ShaderMaterial` / `onBeforeCompile` are not supported with WebGPURenderer (port to nodes/TSL).
- Context hygiene: one renderer per page where possible (see `textures-and-memory.md`).

---

## 12. Mobile-specific advice

Hardware realities (rule of thumb): tile-based GPUs, bandwidth-limited, thermal throttling after minutes of sustained load, small caches, low driver headroom, aggressive tab eviction.

Checklist:

1. Cap pixel ratio to 1.5 or 2 (section 3), or 1 for heavy scenes. Start lower, raise adaptively.
2. `antialias: false` plus FXAA/SMAA, or 2x MSAA only if affordable. Prefer on-demand rendering for non-animated scenes to save battery and keep the device cool (manual states the battery rationale directly).
3. Shadows: one directional light, 1024 map, tight frustum, `PCFShadowMap`/`BasicShadowMap`, static where possible (section 6). No shadow-casting point lights, no VSM.
4. Lights: 1 to 3 plus IBL; bake the rest. Use `MeshLambertMaterial`/`MeshPhongMaterial`/`MeshBasicMaterial` with baked lighting where PBR fidelity is not needed.
5. Textures: KTX2 (ETC1S/UASTC) transcoded to ASTC/ETC2; max 1024 to 2048 for most maps; mipmaps on; anisotropy 2 to 4; no 4K textures in bulk (`textures-and-memory.md`). Memory limits on iOS Safari are tight.
6. Check device limits: `renderer.capabilities.maxTextures` (texture units per shader; PBR + shadows + env can approach the limit), `maxTextureSize`, `maxVertexTextures` (needed for `BatchedMesh`/bone/morph textures), `maxVaryings`, `maxVertexUniforms`/`maxFragmentUniforms`, `maxSamples`, `getMaxAnisotropy()`.
7. Float textures / render targets: `HalfFloatType` is broadly renderable in WebGL2 when the `EXT_color_buffer_half_float` / `EXT_color_buffer_float` extensions exist (three.js enables them as available); `FloatType` filtering (`OES_texture_float_linear`) is not guaranteed on mobile: check `renderer.extensions.has('OES_texture_float_linear')` (WebGLRenderer.extensions) before relying on linear filtering of float data, otherwise use `NearestFilter` or half float.
8. `precision`: default `highp`; many mobile GPUs report `highp` in the fragment stage nowadays, but `mediump` may be faster. Use `mediump` only for color-only math and test visually; keep positions/UV/world-space math in `highp` (set `material.precision` per material).
9. Avoid `discard`-heavy overdraw, large transparent particles, full-screen post-processing chains (tile GPUs pay a bandwidth penalty to leave and re-enter tiles).
10. Prefer fewer, larger draw calls and static batching; avoid per-frame CPU matrix churn. Mobile CPUs are 3x to 10x slower than desktop (rule of thumb).
11. Thermal: sustained 60 fps at max load throttles within minutes. Offer a 30 fps cap (skip every other rAF, or render on a timer) and a quality setting; dynamic resolution reacts to throttling.
12. Handle context loss and tab eviction (`webglcontextlost` / `webglcontextrestored`, see `textures-and-memory.md`).
13. Test on real mid/low devices with remote DevTools; desktop mobile emulation does not emulate GPU limits.

30 fps cap example:

```js
let last = 0;
const interval = 1000 / 30;
renderer.setAnimationLoop((t) => {
  if (t - last < interval - 1) return;   // skip frames
  last = t;
  renderer.render(scene, camera);
});
```

---

## 13. Measuring

Principles: measure on the target device in a production build; one change at a time; watch frame time (ms), not FPS; separate CPU and GPU.

### 13.1 renderer.info (per frame, both renderers)

See `draw-calls-and-geometry.md` section 2. WebGL: `info.render.calls/triangles/points/lines`, `info.memory.geometries/textures`, `info.programs`. WebGPU: `info.render.drawCalls/frameCalls/triangles/timestamp`, `info.memory.*Size`, `info.compute.*`.

### 13.2 stats.js (frame time overlay)

```js
import Stats from 'three/addons/libs/stats.module.js';

const stats = new Stats();
stats.showPanel(0);                // 0: fps, 1: ms, 2: MB (Chrome only)
document.body.appendChild(stats.dom);

function animate() {
  stats.begin();
  renderer.render(scene, camera);
  stats.end();                     // or call stats.update() once per frame
}
```

This is CPU-side wall time between begin/end; it does not include GPU execution time (the GPU runs asynchronously), but frame-to-frame time (FPS panel) does reflect GPU stalls.

### 13.3 GPU timestamps (WebGPURenderer)

Requires the `timestamp-query` WebGPU feature (Chrome with WebGPU; check `renderer.hasFeature('timestamp-query')` after `await renderer.init()`).

```js
import * as THREE from 'three/webgpu';

const renderer = new THREE.WebGPURenderer({ trackTimestamp: true }); // backend option; also set by Inspector
await renderer.init();

async function frame() {
  renderer.render(scene, camera);
  // Resolve outstanding queries (async: reads GPU timestamps back without stalling the frame)
  await renderer.resolveTimestampsAsync(THREE.TimestampQuery.RENDER);   // 'render'
  await renderer.resolveTimestampsAsync(THREE.TimestampQuery.COMPUTE);   // 'compute'
  console.log(renderer.info.render.timestamp, renderer.info.compute.timestamp); // milliseconds of GPU time
}
```

Facts:

- `trackTimestamp` is a WebGPURenderer / backend constructor parameter (default `false`; it is only effective if the adapter supports `timestamp-query`); the examples `webgpu_compute_reduce.html`, `webgpu_storage_buffer.html` use `new THREE.WebGPURenderer({ antialias: false, trackTimestamp: true })`. The `TimestampQuery` constants are `COMPUTE: 'compute'` and `RENDER: 'render'` (exported from `three`/`three/webgpu`).
- `resolveTimestampsAsync(type = 'render')` stores the duration into `renderer.info[type].timestamp`. Do not `await` it inside the render path in a way that serializes frames; fire it (examples call it without awaiting each frame) and read `info` when ready. `TimestampQueryPool` (abstract; implementations `WebGPUTimestampQueryPool`, and a WebGL-fallback pool in `webgl-fallback`) holds `currentQueryIndex`, `maxQueries` (default 256 queries per pool: very large numbers of render passes per frame can exhaust it), `lastValue`, `getTimestamp(uid)`, `resolveQueriesAsync()`.
- Timestamp results are GPU durations summed per context; they tell you whether you are GPU bound (render timestamp near frame time) or CPU bound (render timestamp much shorter than frame time).
- On the WebGL2 fallback backend timestamp queries use `EXT_disjoint_timer_query_webgl2` when available (`WebGLTimestampQueryPool`).
- WebGLRenderer has no built-in timestamp API; use Spector.js, browser tools, or the third-party `EXT_disjoint_timer_query_webgl2` directly.

### 13.4 Inspector addon (WebGPURenderer)

```js
import { Inspector } from 'three/addons/inspector/Inspector.js';

renderer.inspector = new Inspector();       // sets trackTimestamp = true after init and shows the panel
await renderer.init();
const gui = renderer.inspector.createParameters('Settings');   // tweak parameters live while watching the Performance tab
```

Tabs in r187 (`examples/jsm/inspector/tabs`): Performance (frame, CPU/GPU times via the timestamp pools), Memory (GPU resource usage), Timeline, Console (captures three.js warnings), Settings, Viewer (inspect render targets / textures), Parameters; extensions `tsl-graph`, `color-grading`. It resolves timestamps for compute and render each frame itself (`RendererInspector.resolveTimestamp`). `InspectorBase` is the base class for custom inspectors (hooks: `begin`, `finish`, `beginRender`, `finishRender`, `beginCompute`, `finishCompute`, `inspect(node)`); use it to forward metrics to your own telemetry. Examples: `webgpu_performance.html`, `webgpu_instance_mesh.html`, `webgpu_compute_particles.html`.

### 13.5 Browser tools

- Chrome DevTools Performance panel: record a few seconds, look at the Main thread track. A long `render` (script) block with small GPU track means CPU bound; long gaps with GPU busy means GPU bound. Turn on "Screenshots" and the "Frames" track to see dropped frames; enable "Memory" to see heap sawtooth (GC). The manual's `debugging-javascript` article covers DevTools use generally (breakpoints, console, `?param=value` toggles).
- Chrome DevTools rendering tab: "Frame Rendering Stats" (frame-rate meter used by the manual's optimize article).
- `chrome://gpu` shows whether hardware acceleration and WebGPU are active (software rendering is a common cause of "inexplicably slow").
- Spector.js (third party browser extension, not part of three.js): captures a frame and lists every WebGL call, draw call, state change, bound textures and shader sources; best tool to see redundant state changes and large uploads.
- Lighthouse / WebPageTest are for load metrics, not frame performance.
- A/B toggles: URL parameters or GUI flags (manual: debugging article) to disable shadows, post-processing, MSAA, specific objects (`layers`/`visible`) and compare ms.

### 13.6 Procedure

1. Identify CPU vs GPU (section 1; Chrome Performance panel; timestamps).
2. Log `info` baselines (calls, triangles, programs, textures, memory).
3. Remove features one by one (shadows, post, MSAA, transparency, lights) to find the dominant cost.
4. Fix biggest first; re-measure on the slowest target.
5. Keep a performance budget in the repo (max calls, triangles, texture memory) and re-check after content changes.

---

## 14. See also

API pages: `../threejs/references/api/WebGLRenderer.md` (`info`, `setPixelRatio`, `shadowMap`, `debug`, `powerPreference`, `precision`, `setAnimationLoop`, `setEffects`), `Renderer.md` and `WebGPURenderer.md` (options, `samples`, `setMRT`, `isOccluded`, `compileAsync`), `Info.md`, `TimestampQueryPool.md`, `InspectorBase.md`, `LightShadow.md`, `DirectionalLightShadow.md`, `PointLightShadow.md`, `CSM.md`, `CSMShadowNode.md`, `TileShadowNode.md`, `ClusteredLighting.md`, `DynamicLighting.md`, `Material.md` (`alphaTest`, `alphaHash`, `alphaToCoverage`, `depthWrite`, `forceSinglePass`, `precision`, `colorWrite`), `Fog.md`, `FogExp2.md`, `Layers.md`, `OrbitControls.md`, `EffectComposer.md`, `RenderPipeline.md` (`PostProcessing.md` deprecated), `PassNode.md`, `MRTNode.md`, `BloomNode.md`, `FXAANode.md`, `SMAANode.md`, `TRAANode.md`, `SSAAPassNode.md`, `GTAONode.md`, `RenderTarget.md`, `WorkerPool.md`, `ImageBitmapLoader.md`, `Timer.md`.

Examples: `webgl_performance.html`, `webgl_shadowmap_performance.html`, `webgl_worker_offscreencanvas.html` (+ `examples/jsm/offscreen/`), `webgpu_performance.html`, `webgpu_performance_renderbundle.html`, `webgpu_lights_clustered.html`, `webgpu_shadowmap.html`, `webgpu_shadowmap_csm.html`, `webgpu_shadowmap_vsm.html`, `webgpu_shadowmap_progressive.html`, `webgpu_occlusion.html`, `webgpu_compute_reduce.html` (timestamps).

Official manual: https://threejs.org/manual/en/rendering-on-demand, https://threejs.org/manual/en/offscreencanvas, https://threejs.org/manual/en/shadows, https://threejs.org/manual/en/transparency, https://threejs.org/manual/en/tips, https://threejs.org/manual/en/debugging-javascript, https://threejs.org/manual/en/webgpurenderer, https://threejs.org/docs/

Third party (not in core): Spector.js, stats.js (three ships a copy: `three/addons/libs/stats.module.js`), three-mesh-bvh.

Related reference files: `draw-calls-and-geometry.md`, `textures-and-memory.md`, `shader-and-webgpu-perf.md`.
