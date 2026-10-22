# WebGPURenderer (three.js r186)

When to read this: setting up, configuring, debugging or profiling `THREE.WebGPURenderer` (imports, constructor options, async init, WebGL2 fallback, render targets, readback, timestamps, Inspector, clipping, OIT, XR, workers). For compute-shader/GPGPU work read `compute.md`; for TSL syntax read `tsl-reference.md`. All facts below were checked against r186 source (`src/renderers/common/Renderer.js`, `src/renderers/webgpu/*`, `src/renderers/webgl-fallback/*`) and the local docs; where docs and source disagree, source wins and it is flagged.

## Contents
1. Imports and bundles
2. Constructor options (verified list)
3. Async init, animation loop, render-before-init rules
4. Backends: WebGPU vs automatic WebGL2 fallback, detection
5. Feature parity and limitations vs WebGLRenderer
6. Size, pixel ratio, canvas, CanvasTarget, multiple canvases
7. Output: color space, tone mapping, MSAA, output buffer type, internal framebuffer
8. Shadows, clipping (ClippingGroup), OIT, render bundles
9. Render targets (MRT, depth, cube/3D/array, mipmaps, samples)
10. Copy and readback
11. Compute dispatch API (summary)
12. Profiling: timestamps, renderer.info, Inspector
13. Debugging: shader source, errors, device loss
14. Capabilities, limits, features
15. XR
16. OffscreenCanvas / workers
17. Lifecycle: compile, dispose
18. Pitfalls checklist
19. See also

---

## 1. Imports and bundles

```js
import * as THREE from 'three/webgpu';              // everything from core + WebGPURenderer + all *NodeMaterial classes
import { Fn, uniform, texture, vec3 } from 'three/tsl';   // TSL functions (separate bundle: build/three.tsl.js)
import { Inspector } from 'three/addons/inspector/Inspector.js';
```

- `package.json` exports: `"."` -> `three.module.js` (WebGLRenderer), `"./webgpu"` -> `three.webgpu.js`, `"./tsl"` -> `three.tsl.js`, `"./addons/*"` -> `examples/jsm/*`.
- `three.tsl.js` itself does `import { TSL } from 'three/webgpu'`, so TSL always binds to the webgpu bundle instance. Importing node classes from plain `'three'` gives you a different module graph (only `three.core.js` is shared). Rule: in a WebGPU app, import `THREE` from `'three/webgpu'` only. Never `import * as THREE from 'three'` next to it, and never `WebGLRenderer` from `'three'` in the same scene graph.
- Import map used by every official WebGPU example (maps bare `three` to the webgpu build so addons that `import ... from 'three'` resolve to the same instance):

```html
<script type="importmap">{ "imports": {
  "three": "../build/three.webgpu.js",
  "three/webgpu": "../build/three.webgpu.js",
  "three/tsl": "../build/three.tsl.js",
  "three/addons/": "./jsm/" } }</script>
```

- Bundlers (Vite/webpack): alias `three` -> `three/webgpu` if any dependency/addon imports bare `three`; otherwise you get two copies of node classes and `instanceof`/`isNode` checks silently break.
- Tree-shaking: `package.json` has `sideEffects: ["./src/nodes/**/*"]`; node method chaining (`.add()`, `.mul()`, `.compute()`) is installed by side-effect imports, so import from `three/webgpu`, not deep `src/` paths.
- `PostProcessing` is a deprecated alias of `RenderPipeline` (renamed r183, warns once).

## 2. Constructor options (verified)

`new THREE.WebGPURenderer( parameters )`. Destructured in `Renderer` constructor (common) and `WebGPUBackend` / `WebGLBackend` (backend-specific):

| option | default | scope | notes |
|---|---|---|---|
| `antialias` | `false` | both | MSAA on/off. If true and `samples` is 0, 4 samples. |
| `samples` | `0` | both | Explicit sample count; overrides the antialias default (4). Forced to 0 in WebGPU compatibility mode. |
| `alpha` | `true` | both | Canvas transparency. WebGPU: `alphaMode` = `'premultiplied'` if true else `'opaque'`. WebGL backend always creates the context with alpha true. |
| `depth` | `true` | both | Default framebuffer depth buffer. |
| `stencil` | `false` | both | Default framebuffer stencil buffer. |
| `logarithmicDepthBuffer` | `false` | both | Read in `NodeMaterial` and shadow nodes; readonly after construction. |
| `reversedDepthBuffer` | `false` | both | Reversed-Z. Readonly after construction. |
| `outputBufferType` | `HalfFloatType` | both | Type of internal output buffers (frame buffer target). `UnsignedByteType` saves memory/bandwidth, lowers quality. **Renamed from `colorBufferType`** (`getColorBufferType()` deprecated r182, use `getOutputBufferType()`); the old option name is not read by r186. |
| `outputType` | `undefined` | WebGPU | Canvas texture type. `HalfFloatType` sets `toneMapping.mode = 'extended'` on the canvas context (HDR output). Other formats than the device preferred one cost extra conversion. |
| `forceWebGL` | `false` | both | Skip WebGPU, use the WebGL2 backend. |
| `canvas` | auto-created | both | Existing `HTMLCanvasElement` or `OffscreenCanvas` (`Backend.getDomElement`). |
| `context` | `undefined` | both | WebGPU: a `GPUCanvasContext` (default canvas target only). WebGL: a `WebGL2RenderingContext`. |
| `device` | `undefined` | WebGPU | Existing `GPUDevice`; renderer then does not create (or destroy) one. |
| `powerPreference` | `undefined` | WebGPU | Passed to `navigator.gpu.requestAdapter`. |
| `requiredLimits` | `{}` | WebGPU | Passed to `adapter.requestDevice`; request fails if adapter cannot provide them. Example: `{ maxStorageBuffersInVertexStage: 3 }` (birds), `2` (water), `1` (cloth/points/fluid) when a vertex shader reads storage buffers. |
| `trackTimestamp` | `false` | both | Enables GPU timestamp queries. WebGPU: only effective if the device has `timestamp-query`. WebGL: `EXT_disjoint_timer_query_webgl2`. |
| `multiview` | `false` | both | WebXR multiview if supported. Not supported for WebGPU XR (renderer warns and disables it). |
| `getFallback` | set by WebGPURenderer | internal | Callback providing the WebGL backend when WebGPU init fails. Do not set. |

**Not options** (do not exist in r186): `requiredFeatures` (the WebGPU backend requests every feature the adapter exposes, filtered through `GPUFeatureName`), `colorBufferType` (see above), `premultipliedAlpha`, `preserveDrawingBuffer`.

Adapter request uses `featureLevel: 'compatibility'` and `xrCompatible: renderer.xr.enabled`; the device may therefore be in compatibility mode (`renderer.backend.compatibilityMode === true`, set after init when the device lacks `core-features-and-limits`). In compat mode MSAA is forced to 0 and depth-texture comparison paths differ.

```js
const renderer = new THREE.WebGPURenderer( {
  antialias: true,
  powerPreference: 'high-performance',
  requiredLimits: { maxStorageBuffersInVertexStage: 2 },
  trackTimestamp: true
} );
```

## 3. Async init, animation loop, render-before-init rules

WebGPU adapter/device acquisition is async, so the renderer must be initialized before use.

```js
const renderer = new THREE.WebGPURenderer( { antialias: true } );
renderer.setPixelRatio( window.devicePixelRatio );
renderer.setSize( innerWidth, innerHeight );
document.body.appendChild( renderer.domElement );
await renderer.init();              // idempotent: returns the same promise on repeat calls
renderer.setAnimationLoop( ( t ) => renderer.render( scene, camera ) );
```

Rules in r186 (source behavior, stricter than the manual):

| call | before `init()` finished |
|---|---|
| `renderer.setAnimationLoop( cb )` | async; awaits `init()` itself, so using it alone is enough |
| `renderer.render()` | **throws** `"called before the backend is initialized"` |
| `renderer.compute()` | `warn` then delegates to `computeAsync()` (returns a Promise); ordering vs later sync calls is not guaranteed |
| `renderer.computeAsync()`, `compileAsync()`, `compileComputeAsync()`, `clearAsync()`, `resolveTimestampsAsync()`, `getArrayBufferAsync()` path | await init internally |
| `hasFeature()`, `hasCompatibility()`, `initTexture()`, `initRenderTarget()` | **throw** (the JSDoc says "returns false" - source throws) |
| `renderer.backend.device`, `renderer.backend.isWebGPUBackend` | `device` is `null`; `backend` object may still be replaced by the fallback during init |
| `renderer.initialized` / `hasInitialized()` | boolean getter/method |

Deprecated async variants (r181, still present, warn once): `renderAsync()`, `hasFeatureAsync()`, `initTextureAsync()`. `renderer.waitForGPU()` is removed (logs an error, see three.js issue 32012). `QuadMesh.renderAsync` and `RenderPipeline.renderAsync` are also deprecated; use `.render()` after `await renderer.init()`.

`setAnimationLoop( cb )` callback signature `( time: DOMHighResTimeStamp, frame?: XRFrame )`. Pass `null` to stop. The loop also drives XR frames. `getAnimationLoop()` returns the callback. If you use your own `requestAnimationFrame` loop, `await renderer.init()` first and set `renderer.info.autoReset = false` if you call `renderer.info.reset()` yourself once per frame.

`render( scene, camera )` inside a custom loop, with RenderPipeline (post-processing) use `renderPipeline.render()` instead of `renderer.render()`.

## 4. Backends: WebGPU vs WebGL2 fallback, detection

`WebGPURenderer` constructs `WebGPUBackend`; if `backend.init()` throws (e.g. `navigator.gpu.requestAdapter()` returns null) it constructs `WebGLBackend( parameters )`, logs `"WebGPURenderer: WebGPU is not available, running under WebGL2 backend."`, and swaps `renderer.backend`. With `forceWebGL: true` WebGL is used directly. If both fail, `init()` rejects.

```js
await renderer.init();                                   // backend is final only after this
const isWebGPU = renderer.backend.isWebGPUBackend === true;
const isGL2    = renderer.backend.isWebGLBackend === true;

import WebGPU from 'three/addons/capabilities/WebGPU.js';   // pre-flight, before creating the renderer
if ( WebGPU.isAvailable() === false ) document.body.appendChild( WebGPU.getErrorMessage() );
```

- `WebGPU.isAvailable()` is `navigator.gpu !== undefined` and, in a window, `Boolean( await navigator.gpu.requestAdapter() )` evaluated with **top-level await** at module load. Your bundler/target must allow TLA. Skip it if you rely on automatic fallback (it would wrongly block users who could run the WebGL2 backend).
- `WebGL.isWebGL2Available()` / `WebGL.getWebGL2ErrorMessage()` (`three/addons/capabilities/WebGL.js`) are the WebGL2 counterparts.
- Per-backend capability: `renderer.backend.isWebGPUBackend`, `renderer.backend.compatibilityMode` (WebGPU only), `renderer.hasFeature( name )`, `renderer.hasCompatibility( THREE.Compatibility.TEXTURE_COMPARE )` (`'depthTextureCompare'`).
- Fallback ignores WebGPU-only options (`requiredLimits`, `device`, `powerPreference`).
- XR test example creates the renderer with an `createRenderer( forceWebGL )` factory plus `setupWebGLXRFallback` from `three/addons/webxr/WebGLXRFallback.js` (webgpu_xr_cubes.html).

Features that exist **only** on the WebGPU backend (from API docs/source):
`StorageTexture` / `Storage3DTexture` / `StorageArrayTexture`, `IndirectStorageBufferAttribute` and `geometry.setIndirect()`, indirect dispatch, atomics, `workgroupArray` (barriers are emitted as comments on the WebGL backend), subgroup ops (need the `subgroups` device feature), `renderer.compute( node, [x,y,z] )` (WebGL accepts a single number only; arrays and indirect warn once and fall back to `node.count`), MSAA with `OITPassNode`, `viewport` `minDepth/maxDepth`. `ClippingGroup` and `RenderPipeline` are documented as WebGPURenderer-only classes (they work on its WebGL2 backend too since that is the same renderer).

Compute on the WebGL fallback is emulated with transform feedback (`drawArrays( POINTS )` under `RASTERIZER_DISCARD`, ping-pong of buffers). Storage buffers that are read back or sampled from vertex/fragment need `.setPBO( true )` (see `compute.md`).

## 5. Feature parity and limitations vs WebGLRenderer

From the manual (`webgpurenderer.md`) plus source:

Works: `render`, `clear*`, `setRenderTarget`, `dispose`, scissor/viewport, clear color/alpha/depth/stencil, `autoClear*`, `sortObjects`, `setOpaqueSort/setTransparentSort`, shadows (`shadowMap.enabled/type`), tone mapping, `outputColorSpace`, fog, environment, logarithmic and reversed depth, instancing, skinning, morph targets, multiple render targets (`count`), MRT node, 3D/array/cube render targets, XR (`renderer.xr`), post-processing through `RenderPipeline`, TSL/node materials, compute.

Not supported / different:
- `ShaderMaterial`, `RawShaderMaterial`, `material.onBeforeCompile()` are unsupported. Port to `NodeMaterial` + TSL (`colorNode`, `positionNode`, `vertexNode`, `fragmentNode`, `Fn`, `wgslFn`, `glslFn`).
- `EffectComposer` / `Pass` classes unsupported. Use `RenderPipeline` + `pass()` + TSL display nodes (`three/addons/tsl/display/*`).
- Stock materials (`MeshStandardMaterial`...) are auto-mapped to their `*NodeMaterial` twins by the renderer's `NodeLibrary`; custom GLSL chunks (`THREE.ShaderChunk` edits) have no effect.
- `WebGLRenderer.info.programs`, `renderer.capabilities`, `renderer.extensions`, `renderer.state`, `renderer.properties`, `renderer.getContext().getExtension(...)`: not available / not equivalent. Use `renderer.backend`, `renderer.hasFeature()`.
- Sync readback `readRenderTargetPixels` does not exist; only `readRenderTargetPixelsAsync`.
- Clipping: global `renderer.clippingPlanes` and `material.clippingPlanes` handling is replaced by `ClippingGroup` (scene-graph scoped), see 8.
- Render-target `WebGLRenderTarget`/`WebGLCubeRenderTarget`/`WebGL3DRenderTarget`/`WebGLArrayRenderTarget` -> `RenderTarget`, `CubeRenderTarget`, `RenderTarget3D`, plus `RenderTarget` with `depth`/array options. Do not use the `WebGL*` classes.
- Manual states the renderer "is still in an experimental state"; use latest release, expect gaps, and prefer WebGLRenderer for pure WebGL2 apps (no new large features land there).
- WebGLRenderer can run node materials in a limited way via `examples/jsm/tsl/WebGLNodesHandler.js` (compatibility loader); not a replacement for WebGPURenderer.
- `texture.flipY` is honored by the WebGPU texture upload path (flip pass in `WebGPUTexturePassUtils`), default `true` as on WebGL. Check orientation when migrating loaders that bake the flip in (`ImageBitmapLoader` with `imageOrientation`, KTX2/compressed data). `renderer.coordinateSystem` returns `WebGPUCoordinateSystem` or `WebGLCoordinateSystem` depending on the backend; code that hardcodes a Y flip for render-target UVs must branch on it.
- `material.needsUpdate = true` still bumps `material.version` and triggers a rebuild of the node program; for node materials changing a `*Node` property (e.g. `colorNode`) requires `material.needsUpdate = true`. Changing a uniform `.value` never needs it.

## 6. Size, pixel ratio, canvas, CanvasTarget

```js
renderer.setPixelRatio( Math.min( devicePixelRatio, 2 ) );
renderer.setSize( w, h );                 // updateStyle = true by default (sets canvas.style.width/height)
renderer.setSize( w, h, false );          // required for OffscreenCanvas (no .style) and CSS-sized canvases
renderer.getSize( v2 ); renderer.getDrawingBufferSize( v2 ); renderer.getPixelRatio();
renderer.setDrawingBufferSize( w, h, pixelRatio );    // set all at once
renderer.setViewport( x, y, w, h, minDepth = 0, maxDepth = 1 );   // minDepth/maxDepth WebGPU only
renderer.setScissor( x, y, w, h ); renderer.setScissorTest( true );
```

`renderer.domElement` is a getter of the backend canvas (auto-created unless `canvas` passed). Setting `data-engine="three.js r186 webgpu"` is skipped for OffscreenCanvas.

Multiple canvases with one renderer (one GPU device) use `CanvasTarget`:

```js
const target = new THREE.CanvasTarget( someCanvas );
target.setPixelRatio( devicePixelRatio ); target.setSize( 200, 200 );
renderer.setCanvasTarget( target );        // subsequent render() draws to this canvas
renderer.render( scene, camera );          // webgpu_multiple_canvas.html (40 canvases, one renderer)
renderer.getCanvasTarget();
```

`CanvasTarget` holds `colorTexture`, `depthTexture`, viewport/scissor/pixel ratio; call `.dispose()` when removing a canvas. Alternative (one canvas, many views): `setViewport` + `setScissor` + `setScissorTest( true )` per view (webgpu_multiple_elements.html, passes `canvas` and uses `setSize( w, h, false )`).

`setOutputRenderTarget( rt )` redirects the final screen output of the renderer (including tone mapping/color space pass) into a render target instead of the canvas (used by XR).

## 7. Output: color space, tone mapping, MSAA, output buffer

```js
renderer.outputColorSpace = THREE.SRGBColorSpace;        // default
renderer.toneMapping = THREE.NeutralToneMapping;         // or ACESFilmicToneMapping, AgXToneMapping, ...
renderer.toneMappingExposure = 1.0;
```

- Tone mapping and output color space are applied **only when the target is the screen**: `currentToneMapping`/`currentColorSpace` return `NoToneMapping` / working color space when a custom render target is bound. Rendering to a `RenderTarget` yields linear HDR (working color space) values; convert when you display them with `texture()` through a material that is itself drawn to screen.
- If tone mapping != none or `outputColorSpace` != working color space, the renderer allocates an internal frame-buffer `RenderTarget` (type `outputBufferType`, `samples: renderer.samples`), renders into it, then draws a fullscreen output pass to the canvas (`needsFrameBufferTarget`). MSAA therefore resolves in that internal target.
- With `RenderPipeline`, the output transform runs at the end of the pipeline; set `renderPipeline.outputColorTransform = false` and use `renderOutput( node )` for effects that need pre-transform input (e.g. FXAA wants sRGB). `DirectRenderPipeline` applies the transform inside material shaders (no intermediate buffer, changes blending, not compatible with materials that sample the framebuffer such as transmission).
- MSAA: only via `antialias: true` / `samples: n` on the renderer. `WebGPUUtils.getSampleCount` maps any count >= 4 to 4 and everything else to 1, so effective WebGPU MSAA is 1x or 4x. There is no FXAA/SMAA toggle on the renderer; use post-processing nodes. `renderer.samples` (getter) is the configured count; `renderer.currentSamples` is the effective one (0 when drawing the output fullscreen pass, `renderTarget.samples` while a custom target is bound).
- `alpha: true` canvas is premultiplied. `renderer.setClearColor( 0x000000, 0 )` for transparent canvas.
- `logarithmicDepthBuffer` is implemented in `NodeMaterial` (fragment depth) and shadow nodes; it costs early-z. `reversedDepthBuffer` flips depth func and clear value.

## 8. Shadows, clipping, OIT, render bundles

Shadows:
```js
renderer.shadowMap.enabled = true;                 // default false
renderer.shadowMap.type = THREE.PCFShadowMap;      // default; also PCFSoftShadowMap, VSMShadowMap, BasicShadowMap
renderer.shadowMap.transmitted = false;            // light transmission through non-opaque materials
light.castShadow = true; mesh.castShadow = true; mesh.receiveShadow = true;
```

Clipping: `ClippingGroup` (WebGPURenderer only) scopes planes to its descendants; nest them, they accumulate.
```js
const globalClip = new THREE.ClippingGroup();
globalClip.clippingPlanes = [ new THREE.Plane( new THREE.Vector3( 0, - 1, 0 ), 0 ) ];
const knotClip = new THREE.ClippingGroup();
knotClip.clippingPlanes = [ planeA, planeB ];
knotClip.clipIntersection = true;      // intersection instead of union
knotClip.clipShadows = true;           // default false
knotClip.enabled = true;               // toggle without rebuilding
scene.add( globalClip ); globalClip.add( knotClip ); knotClip.add( mesh );
```
`material.clippingPlanes` still exists on the base `Material` (copied/cloned, excluded from NodeMaterial property copy). Stencil-capped clipping: webgpu_clipping_stencil.html; basic: webgpu_clipping.html.

Order-independent transparency (addon, weighted blended OIT, McGuire/Bavoil):
```js
import { oitPass } from 'three/addons/tsl/display/OITPassNode.js';
const renderPipeline = new THREE.RenderPipeline( renderer );
renderPipeline.outputNode = oitPass( scene, camera );   // swap with pass( scene, camera ) to compare
```
Only transparent `NormalBlending` materials without transmission qualify; others render normally. Custom `setMRT` applies to the default pass only; OIT objects do not write custom MRT outputs. MSAA with OIT only on the WebGPU backend. Example: webgpu_oit.html. After changing `renderPipeline.outputNode` set `renderPipeline.needsUpdate = true`.

Render bundles (CPU cost reduction for large static scenes): put objects in `new THREE.BundleGroup()` and set `group.static = true` (default true); if you add/remove objects or change materials, set `static = false` or the cached bundle is stale. Example: webgpu_performance_renderbundle.html. Per-object `static` toggles: webgpu_performance.html.

`renderer.isOccluded( object )` uses occlusion queries when `object.occlusionTest = true` (webgpu_occlusion.html).

`renderer.setRenderObjectFunction( fn )` replaces per-object drawing (e.g. pre-pass with an override material); `fn` must call `renderer.renderObject( object, scene, camera, geometry, material, group, lightsNode, clippingContext, passId )`. `null` resets; `getRenderObjectFunction()` reads it.

## 9. Render targets

```js
const rt = new THREE.RenderTarget( w, h, {
  count: 2,                         // MRT: rt.textures[0], rt.textures[1]
  type: THREE.HalfFloatType, format: THREE.RGBAFormat,
  minFilter: THREE.NearestFilter, magFilter: THREE.NearestFilter,
  depthBuffer: true, stencilBuffer: false,
  depthTexture: new THREE.DepthTexture( w, h ),   // sample depth later: texture( rt.depthTexture )
  samples: 4,                       // MSAA; resolveColorBuffer/resolveDepthBuffer/resolveStencilBuffer default true
  generateMipmaps: false,
  // storeMultisampledColorBuffer|DepthBuffer|StencilBuffer (default true): set false to save bandwidth
} );
rt.textures[ 0 ].name = 'output';   // names show in Inspector/debuggers
rt.setSize( w, h );                 // also rt.setSize( w, h, depth ) for 3D/array
```

Full `RenderTarget~Options` list in r186: `generateMipmaps, magFilter, minFilter, format, type, internalFormat, wrapS, wrapT, anisotropy, colorSpace, depthBuffer, stencilBuffer, resolveColorBuffer, resolveDepthBuffer, resolveStencilBuffer, storeMultisampledColorBuffer, storeMultisampledDepthBuffer, storeMultisampledStencilBuffer, depthTexture, samples, count, depth, multiview, useArrayDepthTexture`.

Usage:
```js
renderer.setRenderTarget( rt );                    // + (activeCubeFace = 0, activeMipmapLevel = 0)
renderer.setMRT( mrt( { output, normal: normalWorld } ) );   // MRTNode; names must match texture names/order
renderer.render( scene, camera );
renderer.setMRT( null ); renderer.setRenderTarget( null );
renderer.getRenderTarget(); renderer.getActiveCubeFace(); renderer.getActiveMipmapLevel();
```
- `count` defines color attachments; the same material output is written to all attachments unless an `MRTNode` maps names to nodes. Attachments share type/format.
- Cube: `new THREE.CubeRenderTarget( size, options )` (`.texture` is a `DataArrayTexture`, `.clear( renderer, c, d, s )`), render with `CubeCamera` or `setRenderTarget( rt, faceIndex )`.
- 3D: `new THREE.RenderTarget3D( w, h, depth, options )`; array targets: `RenderTarget` with `depth` > 1 (layer chosen by `activeCubeFace` argument or `faceIndex` in readback).
- Mipmaps: `generateMipmaps: true` + `minFilter: LinearMipmapLinearFilter`; render a given level with `setRenderTarget( rt, 0, level )`. Note storage textures auto-generate mips after compute writes (`mipmapsAutoUpdate`).
- Sampling: `texture( rt.texture )` in TSL (use `rt.textures[ i ]` for MRT). RTT helper: `rtt( node, w, h )` (see `tsl-guide/58-rtt.md`); full-screen draws: `new THREE.QuadMesh( nodeMaterial ).render( renderer )`.
- `rt.samples > 0` on a custom target gives MSAA independent of `antialias`; the resolved texture is what you sample.
- Resize with `rt.setSize( w * dpr, h * dpr )` (render targets ignore the renderer pixel ratio).
- Preinitialize to avoid first-frame hitches: `renderer.initRenderTarget( rt )`, `renderer.initTexture( tex )` (both require init).
- Overriding scene materials for a pre-pass (rain collision map): `scene.overrideMaterial = mat; renderer.setRenderTarget( rt ); renderer.render( scene, orthoCamera ); scene.overrideMaterial = null;` plus `camera.layers` to choose casters (webgpu_compute_particles_rain.html).

## 10. Copy and readback

```js
renderer.copyTextureToTexture( src, dst, srcRegion?: Box2|Box3, dstPosition?: Vector2|Vector3, srcLevel = 0, dstLevel = 0 );
renderer.copyFramebufferToTexture( framebufferTexture /* THREE.FramebufferTexture */, rect?: Vector2|Vector4 );   // copies current bound framebuffer
const pixels = await renderer.readRenderTargetPixelsAsync( rt, x, y, w, h, textureIndex = 0, faceIndex = 0 );   // TypedArray
const buf = await renderer.getArrayBufferAsync( storageAttribute, target?: ReadbackBuffer|ArrayBuffer, offset = 0, count = -1 );
```
- `readRenderTargetPixelsAsync`: `textureIndex` selects an MRT attachment, `faceIndex` the cube face / 3D slice / array layer. The returned TypedArray class is derived from the texture's GPU format (`_getTypedArrayType`: Uint8Array for 8-bit unorm, Float32Array for 32-bit float, etc.); for HalfFloat targets verify what you get before interpreting values. Stalls the pipeline; avoid per frame, size small (example reads 512x512, webgpu_multiple_rendertargets_readback.html).
- `getArrayBufferAsync`: `offset` and `count` must be multiples of 4 (throws otherwise). Passing a `ReadbackBuffer` (`new THREE.ReadbackBuffer( maxByteLength )`, number) as `target` lets you reuse the staging buffer: the promise resolves with the ReadbackBuffer and data is in `rb.buffer`; call `.release()` to unmap (sets `rb.buffer = null`; must happen before the next use of the same ReadbackBuffer or it throws) and `.dispose()` to free it. A plain `ArrayBuffer` target receives a copy. The renderer tallies it under `renderer.info.memory.readbackBuffers`. (webgpu_compute_reduce.html passes an attribute to the `ReadbackBuffer` constructor and omits the attribute argument of `getArrayBufferAsync`; that does not match the r186 signature.)
- `copyFramebufferToTexture` needs a `FramebufferTexture` whose `image.width/height` define the copy size; used by refraction/backdrop-style effects. When tone mapping forces the internal frame buffer target, the copy comes from that target (linear working space).
- Framebuffer feedback nodes: `viewportSharedTexture()`, `viewportTexture()` (see `tsl-reference.md`).

## 11. Compute dispatch API (summary; details in `compute.md`)

```js
renderer.compute( node | [ nodeA, nodeB ] );                 // sync; throws if first element is not a ComputeNode
renderer.compute( node, 4096 );                              // number = invocations; workgroups = ceil( n / prod( workgroupSize ) )
renderer.compute( node, [ 8, 8, 1 ] );                       // array = WORKGROUP counts (x,y,z), not invocations
renderer.compute( node, indirectStorageBufferAttribute );    // indirect dispatch (WebGPU only)
await renderer.computeAsync( node );                         // inits first
await renderer.compileComputeAsync( node | [ nodes ] );      // pre-build pipelines
```
An array of nodes shares one command encoder / compute pass (one timestamp entry). `renderer.compute` increments `info.compute.calls` and `info.compute.frameCalls`. Compute nodes referenced by a material node graph also run automatically once per frame via `ComputeNode.updateBefore`.

## 12. Profiling: timestamps, info, Inspector

```js
const renderer = new THREE.WebGPURenderer( { trackTimestamp: true } );
await renderer.init();
// each frame (do not await in the render loop; resolve is async and coalesced):
renderer.resolveTimestampsAsync( THREE.TimestampQuery.RENDER );    // 'render'
renderer.resolveTimestampsAsync( THREE.TimestampQuery.COMPUTE );   // 'compute'
const ms = renderer.info.render.timestamp;    // GPU ms for the render passes
const cms = renderer.info.compute.timestamp;  // GPU ms for compute passes
```
- Without `trackTimestamp` (or without device feature `timestamp-query`) `resolveTimestampsAsync` logs `"Timestamp tracking is disabled"` once and returns undefined. `WebGPUTimestampQueryPool( device, type, maxQueries = 2048 )` is created lazily per type.
- Timestamps are keyed per render context / per compute-node group (uid prefix `c:` for compute), so many separate `renderer.compute()` calls each consume a query pair; pools are bounded (`TimestampQueryPool` default 256, `WebGPUTimestampQueryPool` default 2048). Pass an array of compute nodes to share one entry.

`renderer.info` (class `Info`):
- `render`: `calls, frameCalls, drawCalls, triangles, points, lines, timestamp`
- `compute`: `calls, frameCalls, timestamp`
- `memory`: `geometries, textures, attributes, indexAttributes, storageAttributes, indirectStorageAttributes, readbackBuffers, uniformBuffers, programs, renderTargets, *Size (bytes), total`
- `frame`, `calls`; `autoReset = true` (set false and call `info.reset()` yourself once per frame when you manage the loop; the bitonic sort example resets per step). `info.dispose()` full reset.

Inspector addon (replaces stats/lil-gui in official examples, r18x):
```js
import { Inspector } from 'three/addons/inspector/Inspector.js';
renderer.inspector = new Inspector();                 // setter calls inspector.setRenderer( renderer )
const gui = renderer.inspector.createParameters( 'Settings' );    // lil-gui like: gui.add( obj, 'prop', min, max ), addFolder, .name()
```
- Tabs: Parameters, Viewer, Performance, Memory, Timeline, Console, Settings; extensions `color-grading`, `tsl-graph` under `examples/jsm/inspector/extensions`.
- `Inspector extends RendererInspector extends InspectorBase` (`createParameters( name )` exists on `Inspector`). `InspectorBase` hooks called by the renderer: `begin/finish`, `beginRender/finishRender`, `beginCompute/finishCompute`, `computeAsync`, `copyFramebufferToTexture`, `copyTextureToTexture`, `inspect( node )`, `dispose`. Default `renderer.inspector` is a no-op `InspectorBase`.
- In TSL: `.setName( 'x' )` on compute nodes, storage nodes and uniforms labels them in generated shader source and tooling (the birds example notes labels "are reflected within the shader output"). `inspect( node, name?, callback? )` (also `node.toInspector( name, callback )`; `InspectorNode`, WebGPU only) wraps a node so `renderer.inspector.inspect()` receives its value, shown in the Viewer tab.
- Name your compute nodes (`.setName( 'Update Particles' )`) so Performance/Timeline entries are identifiable.
- `trackTimestamp` is independent of the Inspector but the Performance tab reads the same pools.

## 13. Debugging

```js
renderer.debug.checkShaderErrors = true;    // default true; false skips error queries (small perf gain in prod)
renderer.debug.onShaderError = ( gl, program, vs, fs ) => {};   // WebGL backend only today
renderer.debug.onNodeBuilderCreated = ( builder ) => {};         // inspect/modify NodeBuilder before build
renderer.debug.diagnostics.keywords = true;  // rename identifiers that collide with WGSL/GLSL reserved words
const { vertexShader, fragmentShader } = await renderer.debug.getShaderAsync( scene, camera, mesh );   // generated WGSL or GLSL for a mesh
```
- `getShaderAsync` compiles `object` then returns the built vertex/fragment source of its `RenderObject`. For compute, log from the node builder: `renderer.debug.onNodeBuilderCreated = ( b ) => { ... }` or attach `.debug()` (`debug()` TSL utility, `tsl-guide/66-debug.md`) to an expression to print the generated code up to that point for stage `compute`. (No dedicated `getComputeShaderAsync` exists in r186.)
- Uncaptured GPU errors are routed to `renderer.onError( { api, type, message, originalEvent } )` (default logs). Device loss to `renderer.onDeviceLost( { api, message, reason, originalEvent } )`; default logs and sets an internal flag that makes `compute`, `compileAsync` no-ops. Override both for production:
```js
renderer.onDeviceLost = ( info ) => { if ( info.reason !== 'destroyed' ) rebuildRenderer(); };
```
- `renderer.getContext()` returns `GPUCanvasContext` (WebGPU) or `WebGL2RenderingContext`. `renderer.backend.device` is the `GPUDevice` (after init). Use `GPUDevice.pushErrorScope` yourself if needed.
- GLSL/WGSL authoring helpers: `wgslFn`, `glslFn`, `wgsl`, `glsl` TSL nodes (`tsl-guide/81-wgsl.md`, `82-glsl.md`). Builders: `WGSLNodeBuilder`, `GLSLNodeBuilder`; transpiler: `three/addons/transpiler/*` (`tsl-guide/80-transpiler.md`).

## 14. Capabilities, limits, features

```js
await renderer.init();
renderer.hasFeature( 'timestamp-query' );        // WebGPU: device.features.has(name); WebGL: GL extension name map
renderer.hasFeature( 'subgroups' );              // needed by subgroup* TSL nodes
renderer.hasFeature( 'shader-f16' );
const limits = renderer.backend.device.limits;   // WebGPU only; e.g. limits.maxComputeWorkgroupsPerDimension, maxStorageBufferBindingSize, maxComputeInvocationsPerWorkgroup
renderer.getMaxAnisotropy();
```
Known `GPUFeatureName` entries the backend requests when the adapter has them: `depth-clip-control, depth32float-stencil8, texture-compression-bc/etc2/astc (+sliced-3d variants), timestamp-query, indirect-first-instance, shader-f16, rg11b10ufloat-renderable, bgra8unorm-storage, float32-filterable, float32-blendable, clip-distances, dual-source-blending, subgroups, texture-formats-tier1/2`.

Limits are device defaults unless you pass `requiredLimits`. Raise only what you need (device creation fails if unsupported). Typical need: `maxStorageBuffersInVertexStage` when a vertex shader reads storage buffers (instanced compute output), `maxStorageBufferBindingSize`/`maxBufferSize` for very large buffers.

Dispatch workgroup counts above `maxComputeWorkgroupsPerDimension` are automatically folded into a second dimension for number dispatches (the backend splits `dispatchCount` into x,y).

## 15. XR

- Enable: `renderer.xr.enabled = true` (before `init()` so the adapter is requested with `xrCompatible`). Button: `XRButton.createButton( renderer, { optionalFeatures: [ 'webgpu' ] } )` from `three/addons/webxr/XRButton.js`; the XR session needs the `webgpu` feature for the WebGPU backend (`XRGPUBinding`), otherwise `XRManager` throws `"WebGPU XR sessions require the 'webgpu' session feature..."`.
- WebGPU XR does not support multiview yet (renderer warns and disables it).
- Fallback path: `setupWebGLXRFallback( renderer, () => createRenderer( true ), setRenderer )` swaps in a `forceWebGL` renderer when the browser lacks `XRGPUBinding`.
- Examples: webgpu_xr_cubes.html, webgpu_xr_native_layers.html, webgpu_xr_rollercoaster.html, webgpu_xr_shadows.html. API: `references/api/XRManager.md` (`renderer.xr`).

## 16. OffscreenCanvas / workers

WebGPURenderer accepts an `OffscreenCanvas` as `canvas` (`Backend.getDomElement`, `OffscreenCanvas does not have setAttribute` is handled). `navigator.gpu` is available in dedicated workers.

```js
// main.js
const offscreen = canvas.transferControlToOffscreen();
const worker = new Worker( new URL( './worker.js', import.meta.url ), { type: 'module' } );
worker.postMessage( { type: 'init', canvas: offscreen, w: innerWidth, h: innerHeight, dpr: devicePixelRatio }, [ offscreen ] );

// worker.js
import * as THREE from 'three/webgpu';
self.onmessage = async ( { data } ) => {
  const renderer = new THREE.WebGPURenderer( { canvas: data.canvas, antialias: true } );
  renderer.setPixelRatio( data.dpr );
  renderer.setSize( data.w, data.h, false );     // false: OffscreenCanvas has no .style
  await renderer.init();
  renderer.setAnimationLoop( () => renderer.render( scene, camera ) );
};
```
- No DOM in workers: send resize/pointer events as messages; use `ImageBitmapLoader` (not `ImageLoader`/`TextureLoader`) for textures; `Timer`/`performance.now` fine.
- No official WebGPU worker example ships in r186 (`examples/jsm/offscreen/*` use `WebGLRenderer`); the manual page `offscreencanvas.md` documents the WebGL pattern only. Treat the snippet above as derived from the API, not from an official sample.
- `OrbitControls` etc. need a DOM element: run them on the main thread and post camera state, or proxy events.

## 17. Lifecycle: compile, dispose

```js
await renderer.compileAsync( scene, camera );            // pre-build pipelines; avoids first-frame shader stutter
await renderer.compileAsync( object, camera, targetScene );   // object not yet added to targetScene
renderer.compile( ... );                                 // getter alias of compileAsync (returns Promise)
await renderer.compileComputeAsync( computeNode );
await renderer.dispose();                                // async; frees internal managers + backend; destroys the GPUDevice only if the renderer created it (not when you passed `device`)
```
Dispose geometries/materials/textures/render targets you created (`.dispose()`); the renderer drops GPU resources on their `dispose` events. `renderer.resetState()` clears cached state after external code touched the context. `renderer.dispose()` also calls `setAnimationLoop( null )`.

## 18. Pitfalls checklist

1. Forgot `await renderer.init()` before `render()` / `hasFeature()` / `initTexture()` -> throws. `setAnimationLoop` alone is safe; manual rAF is not.
2. `renderer.backend` can change during `init()` (fallback). Read `isWebGPUBackend` after init only.
3. Mixed `three` + `three/webgpu` imports -> duplicated classes, broken `instanceof`, "node.isNode undefined" style errors. Alias bare `three` to the webgpu build.
4. `ShaderMaterial`, `RawShaderMaterial`, `onBeforeCompile`, `EffectComposer` do not work. Use NodeMaterial/TSL/RenderPipeline.
5. `setSize( w, h )` on an OffscreenCanvas throws (touches `.style`); pass `false`.
6. `colorBufferType` option no longer exists; it is `outputBufferType`. `requiredFeatures` is not an option (all adapter features are requested).
7. `renderer.compute( node, [x,y,z] )` sets **workgroup counts**, `renderer.compute( node, n )` sets **invocation count**; the bounds-check `instanceIndex >= count` baked into the shader uses `node.count` (set at `.compute( count )`), not the override.
8. Tone mapping / `outputColorSpace` only apply to screen output. Render targets hold linear working-space data.
9. MSAA only through `antialias`/`samples` (or `RenderTarget.samples`); compat-mode devices force 0.
10. Storage buffers read in a vertex shader may need `requiredLimits.maxStorageBuffersInVertexStage`.
11. WebGL fallback: no storage textures, atomics, workgroup memory, indirect, array dispatch; compute is single-number transform feedback; use `.setPBO( true )` on storage nodes that need readback or fragment/vertex sampling (birds/water examples carry `TODO: Fix example with WebGL backend`).
12. Readbacks (`readRenderTargetPixelsAsync`, `getArrayBufferAsync`) are async and stall; offset/count multiples of 4; release `ReadbackBuffer`.
13. `timestamp-query` unsupported -> `trackTimestamp` silently off; `info.*.timestamp` stays 0.
14. After changing `renderPipeline.outputNode` set `renderPipeline.needsUpdate = true`.
15. After changing a material's `*Node` property set `material.needsUpdate = true`; uniform `.value` changes need nothing.
16. `WebGPU.isAvailable()` uses top-level await at import time; do not gate the automatic fallback on it unless you really want to block WebGL2-only devices.
17. Dispose: `renderer.dispose()` is async; do not reuse the canvas for a different renderer before it resolves.
18. Device lost: default handler only logs. Install `renderer.onDeviceLost` and rebuild.
19. `hasFeatureAsync`, `initTextureAsync`, `renderAsync`, `waitForGPU`, `getColorBufferType`, `PostProcessing`, `QuadMesh.renderAsync` are deprecated/removed.
20. `layers`/`overrideMaterial` pre-pass trick: reset `scene.overrideMaterial = null` before the main render.

## 19. See also

API pages (sibling `threejs` skill): `references/api/Renderer.md`, `WebGPURenderer.md`, `Backend.md`, `WebGPU.md`, `WebGL.md`, `CanvasTarget.md`, `RenderTarget.md`, `RenderTarget3D.md`, `CubeRenderTarget.md`, `RenderPipeline.md`, `DirectRenderPipeline.md`, `Info.md`, `TimestampQueryPool.md`, `WebGPUTimestampQueryPool.md`, `ReadbackBuffer.md`, `QuadMesh.md`, `ClippingGroup.md`, `InspectorBase.md`, `InspectorNode.md`, `ExternalTexture.md`, `VideoFrameTexture.md`, `XRManager.md`, `OITPassNode.md`, `WebGLNodesHandler.md`, `WGSLNodeBuilder.md`, `GLSLNodeBuilder.md`, `NodeBuilder.md`, `Transpiler.md`.

Local docs: `webgpurenderer.md` and `offscreencanvas.md` manual pages; `tsl-guide/28-compute-stage.md`, `54-pass.md`, `55-mrt.md`, `58-rtt.md`, `66-debug.md`, `80-transpiler.md`, `81-wgsl.md`, `82-glsl.md`; `compute.md` (this folder).

Examples: webgpu_multiple_canvas, webgpu_multiple_elements, webgpu_multiple_rendertargets, webgpu_multiple_rendertargets_readback, webgpu_rtt, webgpu_mrt, webgpu_mrt_mask, webgpu_clipping, webgpu_clipping_stencil, webgpu_oit, webgpu_performance, webgpu_performance_renderbundle, webgpu_occlusion, webgpu_storage_buffer (backend + timestamps comparison), webgpu_xr_cubes, webgpu_compute_reduce (timestamps, ReadbackBuffer).

Official: https://threejs.org/manual/#en/webgpurenderer, https://threejs.org/docs/#Renderer, https://threejs.org/docs/#WebGPURenderer, https://threejs.org/manual/#en/offscreencanvas, https://github.com/mrdoob/three.js/wiki/Three.js-Shading-Language
