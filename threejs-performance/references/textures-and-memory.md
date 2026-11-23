# Textures, GPU Memory and Allocation Discipline (three.js r187)

## When to read this

Read when the app runs out of memory (especially mobile / iOS), the page reloads or the WebGL context is lost, loading causes hitches on first render, `renderer.info.memory` keeps growing, frame times show GC spikes, or you are choosing texture formats, sizes and render target settings.

Numbers marked "rule of thumb" are heuristics. Byte math is exact arithmetic.

## Table of contents

1. GPU memory math
2. Mipmaps, power-of-two and filtering rules
3. Compressed textures: KTX2 / Basis
4. Atlases and `DataArrayTexture`
5. Anisotropy cost
6. Upload hitches: `initTexture`, `ImageBitmapLoader`
7. Video textures
8. Render targets, MSAA, depth textures
9. PMREM and environment maps
10. Disposal discipline
11. Shared resources
12. Avoiding per-frame allocations and GC pressure
13. Memory audit workflow
14. See also

---

## 1. GPU memory math

The GPU needs uncompressed (or block-compressed) texel data. File size on disk is irrelevant to VRAM.

```
bytes = width * height * bytesPerTexel * (generateMipmaps ? 4/3 : 1)
```

- RGBA8 (`UnsignedByteType`, `RGBAFormat`): 4 bytes per texel. The manual's formula is `width * height * 4 * 1.33`.
- Manual example: a 157 KB JPEG of 3024 x 3761 pixels uses `3024 * 3761 * 4 * 1.33` = about 60 MB of GPU memory ("A few textures like that and you'll be out of memory").
- Manual (`cleanup`): each 1024 x 1024 texture takes about 4 to 6 MB; a model can add 1 to 20 MB of vertex data.
- Other common sizes (exact arithmetic, RGBA8 with mips): 512^2 = 1.4 MB, 1024^2 = 5.6 MB, 2048^2 = 22.4 MB, 4096^2 = 89.5 MB, 8192^2 = 358 MB.
- Float formats: `HalfFloatType` RGBA = 8 bytes per texel; `FloatType` RGBA = 16 bytes per texel. A 1024 x 1024 RGBA float data texture is 16 MB (BatchedMesh and bone textures are float RGBA data textures).
- Single channel (`RedFormat`, `RedIntegerFormat`) is 1 byte per texel for 8-bit types: use for masks, roughness, AO, height when you do not need four channels. Channel-pack AO / roughness / metalness into one RGB texture (glTF ORM convention: R=occlusion, G=roughness, B=metalness).
- Cube map: 6 faces. 1024 cube RGBA8 with mips = 6 x 5.6 MB = 33.5 MB.
- Block compressed (GPU formats, rule of thumb values): BC7 / ASTC 4x4 / ETC2 RGBA = 8 bits per texel (1 byte), ETC1 / BC1 = 4 bits per texel. That is 4x to 8x less than RGBA8, and also less bandwidth per sample.

Verify at runtime:

- WebGLRenderer: `renderer.info.memory.textures` (count only).
- WebGPURenderer: `renderer.info.memory.texturesSize` and `.total` in bytes, plus `.attributesSize`, `.uniformBuffersSize`, `.programs` and render target counts.
- Inspector Memory tab (WebGPU): `examples/jsm/inspector/tabs/Memory.js`.

Rule: shrink dimensions, not just file size. Choose the lowest resolution that looks acceptable at the largest on-screen size the texture will have (texel density). Typical budgets (rule of thumb): mobile total texture memory a few hundred MB at most; iOS Safari kills tabs aggressively, so aim lower.

---

## 2. Mipmaps, power-of-two, filtering

- `texture.generateMipmaps = true` is the default for `Texture`. Mips add 1/3 memory but are required for quality and performance of minified sampling: a GPU samples the small mip, which is cache-friendly. Disabling mips on textures that are sometimes minified causes shimmering and more memory traffic (manual: with `Nearest`/`Linear` filters the GPU picks from the original and "flicker in the distance").
- `minFilter` default is `LinearMipmapLinearFilter` (trilinear, 8 texel reads per sample, best quality). `LinearMipmapNearestFilter` / `NearestMipmapNearestFilter` are cheaper; `LinearFilter` and `NearestFilter` do not use mips.
- Turn mipmaps off (`generateMipmaps = false`, `minFilter = LinearFilter`) for: UI/HUD textures drawn 1:1, render target textures sampled at the same resolution (post-processing inputs), data textures (positions, matrices, lookup tables), and `DataArrayTexture` (defaults are already `generateMipmaps = false`, `magFilter = NearestFilter`).
- `texture.mipmapsAutoUpdate = false` (r187, default `true`; needs `generateMipmaps`): keep mips allocated but stop the renderer regenerating them on every upload, render or copy. Use it for render targets or video/canvas textures updated often where you write mip levels yourself or stale mips are acceptable, to skip a mip-chain rebuild each update.
- Non-power-of-two (NPOT): WebGL2 and WebGPU support NPOT with mipmaps and repeat wrapping, so POT is not required for correctness. Keep POT (or multiples of 4 for block-compressed formats) as a rule of thumb: block compression requires dimensions that are multiples of the block size (4 for ETC/BC/ASTC 4x4), mip chains are cleaner, and GPU texture caches handle them well.
- `texture.flipY` / `premultiplyAlpha` are applied at upload for HTML images (a CPU pass in the driver); ignored for `ImageBitmap` (configure at bitmap creation, section 6). Compressed textures cannot be flipped at upload.
- `texture.colorSpace`: set `SRGBColorSpace` for color maps; leave data maps (normal, roughness, AO) at the default `NoColorSpace`. Wrong settings cost correctness, not memory.
- Textures sharing the same image data should share a `Source` (`texture.clone()` shares `texture.source`; the docs mention spritesheets): one GPU upload, many transform variants (`offset`, `repeat`, `rotation`).

---

## 3. Compressed textures: KTX2 / Basis

`KTX2Loader` reads KTX 2.0 containers that hold Basis Universal data and transcodes at load time (WASM) into whatever block-compressed format the GPU supports, then uploads it compressed. Memory and bandwidth drop 4x to 8x vs RGBA8, and decode on the GPU is free.

```js
import { KTX2Loader } from 'three/addons/loaders/KTX2Loader.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { MeshoptDecoder } from 'three/addons/libs/meshopt_decoder.module.js';

const ktx2 = new KTX2Loader()
  .setTranscoderPath('/basis/')     // folder with basis_transcoder.js + basis_transcoder.wasm (copy from three/examples/jsm/libs/basis/)
  .setWorkerLimit(4)                // transcode in a pool of workers
  .detectSupport(renderer);         // MUST be called before loading; works with WebGLRenderer and WebGPURenderer

const gltf = await new GLTFLoader()
  .setKTX2Loader(ktx2)
  .setMeshoptDecoder(MeshoptDecoder)
  .loadAsync('model.glb');          // glTF with KHR_texture_basisu

// stand-alone
const tex = await ktx2.loadAsync('diffuse.ktx2');
tex.colorSpace = THREE.SRGBColorSpace; // check: glTF path sets it for you
ktx2.dispose();                       // when no more KTX2 files will be loaded (frees workers)
```

Facts (from `KTX2Loader.md` and source):

- Default transcoder path is `examples/jsm/libs/basis` inside the package; for bundlers copy the two files to your public folder and call `setTranscoderPath`. `detectSupportAsync(renderer)` is deprecated; use `detectSupport` (WebGPU renderers must be `init()`ed first so features are known).
- `detectSupport` inspects the renderer for ASTC, BPTC (BC6H/BC7), S3TC, ETC1/ETC2 and PVRTC and picks a transcode target. Result formats seen in the loader source: `RGBA_ASTC_4x4_Format`, `RGBA_BPTC_Format`, `RGBA_S3TC_DXT5_Format`, `RGBA_ETC2_EAC_Format`, `RGB_ETC1_Format`, `RGBA_PVRTC_*`, falling back to uncompressed `RGBAFormat` when none is supported (memory benefit lost).
- Two Basis modes (source `BasisFormat`: `ETC1S`, `UASTC`, `UASTC_HDR`):
  - ETC1S: smallest files and VRAM, lower quality, blocky on gradients and normal maps. Good for diffuse/albedo of stylized or noisy content.
  - UASTC: higher quality, larger files; use for normal maps and anything quality-critical. `UASTC_HDR` carries HDR data (transcodes to BC6H or runs directly on ASTC hardware).
  - Choose per texture at encode time (toktx / basisu / gltf-transform), not at runtime.
- Compressed textures ship their own mip chain (encode with mips). `CompressedTexture` has `mipmaps` array; `generateMipmaps` is not applicable.
- Transcoding cost is CPU/worker time at load, not per frame: preload during a loading screen. Workers: `setWorkerLimit(n)`.
- Examples: `webgl_loader_texture_ktx2.html`, `webgpu_loader_texture_ktx2.html`, `webgl_loader_gltf_compressed.html`, `webgpu_loader_gltf_compressed.html`, `webgl_texture2darray_compressed.html`, `misc_exporter_ktx2.html`.

Mesh data compression (separate, geometry): Draco via `DRACOLoader`, meshopt via `MeshoptDecoder`; reduce download size, not VRAM (see `draw-calls-and-geometry.md`).

Decision: if you can run an asset pipeline, KTX2 (UASTC for normals, ETC1S or UASTC for color) is the best default for large texture sets on mobile. Plain JPEG/PNG/WebP/AVIF only save download time.

---

## 4. Atlases and DataArrayTexture

Fewer distinct textures means fewer binds, fewer materials (so batching works) and fewer texture units per shader.

- Atlas: pack many images into one texture and offset UVs per mesh. Bleeding at mip edges requires padding; atlases cannot use `RepeatWrapping` per sub-image.
- `DataArrayTexture(data, width, height, depth)`: a texture with `depth` layers, all the same size, sampled with a layer index (GLSL `sampler2DArray`, TSL via texture node with `depth()`/layer). Good with instancing (layer per instance via instance attribute) and for terrain / sprite layers without UV bleeding. Defaults: `generateMipmaps = false`, `flipY = false`, filters `NearestFilter` (enable mips/linear explicitly if you want them).
  ```js
  import * as THREE from 'three';
  const data = new Uint8Array(w * h * 4 * layers);
  const tex = new THREE.DataArrayTexture(data, w, h, layers);
  tex.minFilter = THREE.LinearFilter; tex.magFilter = THREE.LinearFilter;
  tex.needsUpdate = true;
  // update only one layer later:
  tex.addLayerUpdate(layerIndex);   // see DataArrayTexture.md (layerUpdates, clearLayerUpdates)
  tex.needsUpdate = true;
  ```
  Examples: `webgl_texture2darray.html`, `webgl_texture2darray_layerupdate.html`, `webgl_texture2darray_compressed.html`, `webgpu_textures_2d-array_compressed.html`. `CompressedArrayTexture` is the compressed counterpart.
- Constraint: all layers share size and format. Max layers is limited by `MAX_ARRAY_TEXTURE_LAYERS` (device limit, rule of thumb 256 or more).
- `renderer.capabilities.maxTextures` (WebGLRenderer) caps texture units per shader (rule of thumb: 16; mobile may be lower). A PBR material with map, normal, ORM, emissive, plus shadow maps and an environment map can approach limits when many shadow-casting lights are present.

---

## 5. Anisotropy cost

`texture.anisotropy` (default `Texture.DEFAULT_ANISOTROPY`, 1) takes extra samples along the axis of highest texel density: sharper textures on surfaces seen at grazing angles (floors, roads), at the cost of more texture samples (up to N times the sample count per fetch) and bandwidth.

```js
// WebGLRenderer
const max = renderer.capabilities.getMaxAnisotropy();
// WebGPURenderer
const max2 = renderer.getMaxAnisotropy();

floorTexture.anisotropy = Math.min(8, max);   // 4 to 8 is usually enough (rule of thumb)
```

Apply only to large ground / wall textures seen at oblique angles; leave 1 on small props, UI, data textures. On mobile prefer 2 to 4. Changing anisotropy after upload needs `texture.needsUpdate = true`.

---

## 6. Upload hitches

A texture is decoded (CPU) and uploaded (GPU) lazily: at the first frame in which a visible object uses it. Large uploads freeze that frame.

Pre-upload behind a loading screen:

```js
// WebGLRenderer
renderer.initTexture(texture);          // decode + upload now
renderer.initRenderTarget(rt);          // allocate framebuffer memory (WebGLRenderer, WebGPURenderer)

// WebGPURenderer (must be initialized): same names
await renderer.init();
renderer.initTexture(texture);          // initTextureAsync is deprecated
```

Staggering: initialize one or two large textures per frame instead of all at once.

Decode off the main thread with `ImageBitmapLoader`:

```js
const loader = new THREE.ImageBitmapLoader();
loader.setOptions({ imageOrientation: 'flipY', premultiplyAlpha: 'none' }); // matches Texture defaults
const bitmap = await loader.loadAsync('albedo.jpg');   // createImageBitmap: decode in browser, off main thread
const texture = new THREE.Texture(bitmap);
texture.colorSpace = THREE.SRGBColorSpace;
texture.needsUpdate = true;
// CanvasTexture(bitmap) is used in jsm/offscreen/scene.js (workers have no DOM image elements)
```

Facts (from `ImageBitmapLoader.md`):

- `Texture.flipY` and `Texture.premultiplyAlpha` are ignored for `ImageBitmap`; set them via `setOptions` before loading (`{ imageOrientation: 'flipY', premultiplyAlpha: 'none' }` to match `Texture` defaults). Default loader options are `{ premultiplyAlpha: 'none' }`.
- `setOptions` accepts the `createImageBitmap` options object. With `Cache.enabled`, the cache key is the URL only, so the same URL with different options returns the first result.
- `ImageBitmap` memory is not freed by `texture.dispose()`: call `bitmap.close()` yourself (manual: how-to-dispose-of-objects). Only close when no one else uses it, and note it cannot be re-uploaded after a context loss.
- It also works in workers (OffscreenCanvas example), where `ImageLoader` (DOM `Image`) does not.
- `THREE.Cache.enabled = true` caches `FileLoader` results (CPU side) so repeated loads of the same URL do not re-fetch.

CPU-side image memory: the decoded HTMLImageElement / bitmap remains in RAM after upload. For huge textures, drop references once uploaded (`texture.image = null` is not documented; use `onUpdate` or the `ImageBitmap.close()` route and verify behavior in your target browsers). BufferAttributes have the documented hook `attribute.onUpload(cb)` to release CPU arrays after GPU upload (`BufferAttribute.md`).

---

## 7. Video textures

`VideoTexture(video)` re-uploads the current frame to the GPU on each new video frame. In r187 it uses `video.requestVideoFrameCallback` when available (flagging `needsUpdate` only on actual new frames), otherwise polls `update()` each render.

Costs:

- One full-resolution upload per video frame: a 4K video at 30 fps uploads about 33 MB x 30 per second (RGBA8) in the worst case. Use the smallest video resolution that fits the on-screen size.
- Mipmaps: `VideoTexture` defaults to linear filtering without mips (check constructor defaults in `VideoTexture.md`); keep it that way, mip generation per frame is wasteful.
- Decode cost is the browser's hardware decoder; keep `video.playsInline = true`, `muted` for autoplay.
- WebGPURenderer: `texture.colorSpace` must be set to `SRGBColorSpace` (docs note).
- Several screens showing the same video: share one `VideoTexture` (one upload per frame), not one per mesh.
- After first use, a video texture's dimensions/format/type cannot change; `dispose()` and recreate.
- `VideoFrameTexture` exists for `VideoFrame` sources (WebCodecs).
- Remove: `video.pause(); video.removeAttribute('src'); video.load(); texture.dispose();`.

---

## 8. Render targets, MSAA, depth

Render target memory = `width * height * bytesPerTexel * attachments` (+ depth/stencil + mips + MSAA storage).

- Size to what you sample. A reflection / portal / minimap / shadow-like pass rarely needs full canvas resolution. Half size is a quarter of the fill cost and memory.
- Pixel ratio multiplies targets too: post-processing buffers match drawing buffer size (`css size x pixelRatio`).
- `samples` (MSAA) on a `WebGLRenderTarget` / `RenderTarget`: `samples: 4` stores 4x color (and depth) per pixel and adds a resolve step each frame. WebGLRenderer limits: `renderer.capabilities.maxSamples`. WebGPURenderer: `new WebGPURenderer({ antialias: true, samples: 4 })` (default 4 when `antialias`), `renderer.samples`. Use MSAA on the final scene render target only; do not multisample intermediate effect buffers.
- Type: `HalfFloatType` is 2x `UnsignedByteType`; `FloatType` 4x. WebGPURenderer's default output buffer is `HalfFloatType` for quality; `new WebGPURenderer({ outputBufferType: THREE.UnsignedByteType })` saves memory and bandwidth at reduced quality (documented in `WebGPURenderer.md` options). WebGLRenderer: `outputBufferType` option (default `UnsignedByteType`) only needs HalfFloat for HDR + tone-mapped post-processing.
- Depth reuse: attach a `DepthTexture` to a render target instead of rendering depth twice, and share it among effects (SSAO, fog, depth of field) that need scene depth. `RenderTarget.resolveDepthBuffer = false` skips resolving the depth buffer when you do not need depth afterwards (documented as saving memory bandwidth); `resolveStencilBuffer` likewise. `depthBuffer = false` / `stencilBuffer = false` when unused.
- `MeshPhysicalMaterial.transmission` renders the scene into an internal transmission target: `renderer.transmissionResolutionScale` (WebGLRenderer, default 1) can be lowered for large wins (documented).
- Mip-mapped targets (`generateMipmaps = true`) regenerate mips every render; leave off unless sampled with mip filtering (e.g. blur chains, `viewportMipTexture`).
- Cube render targets (`CubeRenderTarget`, `WebGLCubeRenderTarget`) cost 6 scene renders per update: update them on change or at low rate (every N frames), at 128 to 256 per face for reflections (rule of thumb).
- `StorageTexture`, `Storage3DTexture` and compute resources live in GPU memory until disposed; count them in `info.memory`.
- Always `renderTarget.dispose()` and `composer.dispose()` / `renderPipeline.dispose()` (see section 10).

---

## 9. PMREM and environment maps

`PMREMGenerator` (WebGLRenderer) converts an equirectangular / cube / scene into a prefiltered cube render target (a `WebGLCubeRenderTarget` since r187; the old cube-UV atlas and `CubeUVReflectionMapping` are gone) used for roughness-dependent IBL. Generation does several GPU passes and compiles shaders: a one-time cost (tens to hundreds of milliseconds at 256 output; rule of thumb) that must not happen per frame or per object.

```js
const pmrem = new THREE.PMREMGenerator(renderer);
pmrem.compileEquirectangularShader();          // do this while the HDR file is downloading

const hdr = await new HDRLoader().loadAsync('env.hdr');  // see HDRLoader.md
hdr.mapping = THREE.EquirectangularReflectionMapping;
const envRT = pmrem.fromEquirectangular(hdr);
scene.environment = envRT.texture;

hdr.dispose();        // source no longer needed
pmrem.dispose();      // frees the generator's internal shader/targets
// keep envRT alive as long as scene.environment uses it; envRT.dispose() when replacing it
```

Rules:

- Generate once, reuse for all materials via `scene.environment` rather than setting `material.envMap` on every material.
- Output size follows the input since r187 (`PMREMGenerator.md`): equirect face size = image width / 4, cube face size = input face size, both rounded down to a power of two and at least 256. So a 1024 x 512 equirect gives 256 faces, and a 4096 x 2048 one gives 1024 faces (16x the VRAM of 256). Pick the source width for the reflection sharpness you need; use a high-resolution source for `scene.background` separately if only the backdrop must be sharp.
- `fromScene(scene, sigma, near, far, { size, position })` renders a scene into a PMREM (default `size` 256), useful for procedural skies: it re-renders the scene 6 times; call once or rarely.
- `PMREMGenerator` is documented as "static": one instance is enough, and disposing one makes any others unusable.
- Dispose the old PMREM render target when swapping environments (`oldRT.dispose()`).
- WebGPURenderer does the equivalent internally (`src/nodes/pmrem`); you assign `scene.environment` with an equirect/cube texture and the renderer generates and caches it. The manual notes that such internally created textures can still appear in `renderer.info.memory` after a scene cleanup; they are reused, not leaked.
- `scene.backgroundBlurriness > 0` makes the renderer run the background texture through PMREM as well (`WebGLBackground.js`: `usePMREM`): an extra conversion for the background; leave at 0 if you do not need a blurred sky.
- Environment intensity and rotation (`scene.environmentIntensity`, `environmentRotation`) are free uniforms.
- `LightProbe` (spherical harmonics) is a far cheaper diffuse-only ambient than a PMREM if you do not need specular reflections.

---

## 10. Disposal discipline

three.js cannot know lifetimes, so GPU resources are never freed automatically. Removing a mesh from the scene frees nothing on the GPU.

What each `dispose()` frees (manual: how-to-dispose-of-objects):

| Object | `dispose()` frees | Notes |
|---|---|---|
| `BufferGeometry` | one GL buffer per attribute (plus index) | Shared geometries: dispose only when the last mesh is gone |
| `Material` | shader program, only when all materials using it are disposed | Does not dispose textures it references |
| `Texture` | the GPU texture | `ImageBitmap` sources need `bitmap.close()` separately; no-op if never uploaded |
| `WebGLRenderTarget` / `RenderTarget` | texture, framebuffer, renderbuffers | Also post-processing passes / composers have `dispose()` |
| `Skeleton` | bone texture | Skeletons can be shared across skinned meshes |
| `InstancedMesh`, `BatchedMesh` | instance buffers / textures | Geometry and material still separate |
| `ShadowLight.shadow` (`LightShadow.dispose()`) | shadow map render target | Dispose when removing the light |
| Controls (`OrbitControls`...), loaders (`KTX2Loader`, `DRACOLoader`), `Timer`, `PMREMGenerator`, `WorkerPool` | listeners, workers, internal targets | After `dispose()` controls and renderers are unusable; make new ones |

Using a disposed geometry / material / texture again is allowed: the renderer re-creates the GPU resource (with a performance hit, such as recompiling shaders). Controls and renderers are the exception.

Traverse-and-dispose helper (dispose every material texture too):

```js
function disposeObject(root) {
  root.traverse((obj) => {
    if (obj.geometry) obj.geometry.dispose();
    const mats = Array.isArray(obj.material) ? obj.material : obj.material ? [obj.material] : [];
    for (const m of mats) {
      for (const key in m) {
        const v = m[key];
        if (v && v.isTexture) v.dispose();           // map, normalMap, envMap (skip if shared!), ...
      }
      m.dispose();
    }
    if (obj.isSkinnedMesh) obj.skeleton.dispose();   // only if not shared
    if (obj.dispose && (obj.isInstancedMesh || obj.isBatchedMesh)) obj.dispose();
  });
  root.removeFromParent();
}
```

Caveats: do not dispose textures shared with other live materials (`scene.environment`, a shared atlas). Uniform textures inside `ShaderMaterial.uniforms` are not found by the loop above: walk `m.uniforms` too. `userData`-held resources need manual handling.

Manual `ResourceTracker` pattern (`cleanup`): wrap every creation in `track(...)`, keeping a `Set`; `untrack` for shared/persistent ones; on teardown remove tracked `Object3D`s from their parent and call `dispose()` on each. For glTF: `track(gltf.scene)` and traverse for geometry/material/texture.

Teardown of an entire view (SPA route change, hot reload):

```js
cancelAnimationFrame(rafId);            // or renderer.setAnimationLoop(null)
controls.dispose();                     // removes DOM listeners
window.removeEventListener('resize', onResize);
disposeObject(scene);
composer?.dispose();                    // or renderPipeline.dispose() on WebGPU
pmrem.dispose(); envRT.dispose();
renderer.dispose();                     // WebGPURenderer: dispose() is async
renderer.forceContextLoss();            // WebGLRenderer: simulates context loss (needs WEBGL_lose_context) to release the context immediately
renderer.domElement.remove();
```

Browsers cap live WebGL contexts (rule of thumb: about 8 to 16; the oldest is lost when exceeded), so creating a renderer per route without releasing contexts eventually kills earlier canvases. Prefer one renderer reused across views.

Verify with `renderer.info.memory.geometries` / `.textures` (and `.programs` length on WebGLRenderer, `.total` on WebGPURenderer). After full scene teardown some internal textures/geometries (environment, background) legitimately remain and are reused on the next populate (manual FAQ).

Leak hunting:

1. Log `info.memory` after load, after teardown, after reload cycle. A count that rises each cycle is a leak.
2. Chrome DevTools Memory tab: heap snapshot, compare, look for detached `Mesh`, `Texture`, `ImageBitmap`, and retained event listeners / closures (usual culprit: listeners on `window` or `controls` that capture the scene).
3. Examples: `webgl_test_memory.html`, `webgl_test_memory2.html` (referenced in the manual).

---

## 11. Shared resources

- One geometry per shape, shared by all meshes (and cloned meshes: `mesh.clone()` shares geometry and material by reference).
- One material per look, shared. Per-object variation: `InstancedMesh` color, vertex colors, uniform per object via `onBeforeRender` (costly), on WebGPURenderer `NodeMaterialInstance` (r187: per-instance values, one shared shader build; see `threejs-tsl-webgpu` node-materials), or `material.clone()` only when really needed (each clone is its own set of uniforms; programs are shared when parameters match).
- Textures: reuse the same `Texture` instance (or share `Source`) across materials; load each URL once (keep a `Map<url, Promise<Texture>>`; `THREE.Cache.enabled = true` also caches raw file data).
- `gltf.scene.clone()` shares geometry/material/texture (and `SkinnedMesh` needs `SkeletonUtils.clone`). Dispose the shared resources once, at the end.
- `AnimationObjectGroup`: a group of objects sharing one animation state so a mixer/clip action drives many objects with one property binding set; the properties must be compatible among all objects (documented limitation).

---

## 12. Avoiding per-frame allocations and GC pressure

JS garbage collection pauses show as irregular frame spikes (dropped frames every second or so even though average time is low). Sources of garbage in three.js code: `new THREE.Vector3()/Matrix4()/Color()/Quaternion()/Box3()` inside `animate` or per-object loops, `.clone()`, array methods creating arrays (`map`, `filter`, spread), closures created per frame, `Object3D.getWorldPosition()` without a target, `raycaster.intersectObjects()` (returns a new array unless you pass one), string building in the loop.

Pattern: module-level scratch objects.

```js
const _v = new THREE.Vector3();
const _m = new THREE.Matrix4();
const _q = new THREE.Quaternion();
const _c = new THREE.Color();
const _hits = [];

function update(dt) {
  for (let i = 0; i < n; i++) {
    obj[i].getWorldPosition(_v);                  // target argument: no allocation
    _v.addScaledVector(vel[i], dt);               // in place
    _m.compose(_v, _q, scale);
    instanced.setMatrixAt(i, _m);
  }
  _hits.length = 0;
  raycaster.intersectObjects(pickables, false, _hits); // 3rd param is the target array
}
```

API facts: `Object3D.getWorldPosition(target)`, `getWorldQuaternion(target)`, `getWorldScale(target)`, `getWorldDirection(target)` all take a target. `InstancedMesh.getMatrixAt(i, target)`, `getColorAt(i, target)`, `Box3.setFromObject(obj, precise)`, `Raycaster.intersectObject(obj, recursive, intersects)` take outputs. Prefer `copy`, `set`, `setFromMatrixPosition`, `lerpVectors`, `applyMatrix4` in place.

Other discipline:

- Object pooling for spawned entities (bullets, particles, decals, damage numbers): allocate `N` meshes once (or `InstancedMesh` slots), toggle `visible` / `count` / scale 0, and recycle indices from a free list. Creating and disposing meshes at runtime also creates GPU buffers and may recompile materials.
- Allocate typed arrays once with `new Float32Array(max * 3)` and update in place (see "can't resize buffers" in the manual's `how-to-update-things`; use `setDrawRange`).
- Avoid `Array.prototype.forEach/map` with closures on hot paths with 100k elements; a plain `for` loop is allocation-free.
- Do not build strings (`name`, UI labels) each frame; write DOM text only when the value changes.
- `Clock` is deprecated since r183; use `Timer`:
  ```js
  import { Timer } from 'three';
  const timer = new Timer();
  timer.connect(document);         // Page Visibility API: no giant delta after tab switch
  renderer.setAnimationLoop((timestamp) => {
    timer.update(timestamp);       // call once per frame
    const dt = timer.getDelta();   // same value however often you call it within the frame
    const t = timer.getElapsed();
    // ...
  });
  ```
  A clamped `dt` (for example `Math.min(dt, 0.1)`) avoids physics explosions after a stall; `Timer.setTimescale()` for slow motion without touching update code.
- Measure GC: Chrome DevTools Performance panel with the "Memory" checkbox shows sawtooth heap growth; any steady sawtooth during idle animation indicates per-frame garbage. Take allocation sampling profiles to find the call sites.
- `renderer.info` and Inspector calls themselves allocate if you log objects each frame: read numbers, not whole objects.

---

## 13. Memory audit workflow

1. Print `renderer.info.memory` (and `.texturesSize` / `.total` on WebGPU) after load.
2. List textures by size: traverse materials, compute `w * h * bytes * 1.33`; flag anything over 2048^2 that is not hero content.
3. Convert big color/normal sets to KTX2; channel-pack ORM; drop unused maps; reduce env map to 1k.
4. Check render targets: composer buffers at half-res, MSAA only where needed, depth shared.
5. Check geometry: `BufferGeometryUtils.estimateBytesUsed(geometry)`; quantize / simplify heavy meshes.
6. Reload/teardown cycle test for leaks.
7. Test on the weakest target device, not the dev machine; mobile browsers evict tabs and lose contexts first.

Handle context loss gracefully: listen to `renderer.domElement` `webglcontextlost` (call `event.preventDefault()`) and `webglcontextrestored` (three.js re-uploads resources lazily when you render again; CPU-side data such as closed `ImageBitmap`s cannot be re-uploaded, which is another reason to keep sources until you are sure).

---

## 14. See also

API pages: `../threejs/references/api/Texture.md`, `CompressedTexture.md`, `CompressedArrayTexture.md`, `DataArrayTexture.md`, `DataTexture.md`, `KTX2Loader.md`, `ImageBitmapLoader.md`, `VideoTexture.md`, `VideoFrameTexture.md`, `DepthTexture.md`, `RenderTarget.md`, `WebGLRenderTarget.md`, `PMREMGenerator.md`, `Timer.md`, `Clock.md` (deprecated), `AnimationObjectGroup.md`, `Cache.md`, `Info.md`, `WebGLRenderer.md` (`initTexture`, `initRenderTarget`, `dispose`, `forceContextLoss`, `capabilities`), `Renderer.md` (`initTexture`, `getMaxAnisotropy`, `dispose`), `module-BufferGeometryUtils.md`, `Object3D.md` (`getWorldPosition`).

Examples: `webgl_loader_texture_ktx2.html`, `webgpu_loader_texture_ktx2.html`, `webgl_texture2darray.html`, `webgl_texture2darray_layerupdate.html`, `webgl_test_memory.html`, `webgl_test_memory2.html`, `webgl_worker_offscreencanvas.html` (ImageBitmapLoader in a worker).

Official manual: https://threejs.org/manual/en/textures (Memory Usage), https://threejs.org/manual/en/cleanup, https://threejs.org/manual/en/how-to-dispose-of-objects, https://threejs.org/manual/en/how-to-update-things, https://threejs.org/docs/#KTX2Loader

Related reference files: `draw-calls-and-geometry.md`, `rendering-strategies.md`, `shader-and-webgpu-perf.md`.
