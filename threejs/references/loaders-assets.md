# Loaders, Assets, Textures I/O, Exporters (three.js r187)

When to read this: loading glTF/other models, setting up Draco/KTX2/Meshopt decoders, loading textures / HDR / EXR / cube maps / Gaussian splats, tracking load progress, cloning skinned models, exporting scenes, or freeing loaded assets. For material/texture property semantics see `materials.md`.

## Contents
1. Loader base API, async patterns, LoadingManager
2. Paths, CORS, credentials, Cache, URL modifier
3. GLTFLoader canonical setup (Draco + KTX2 + Meshopt)
4. glTF result structure, traversal, cloning (SkeletonUtils)
5. Supported glTF extensions
6. Texture loading (TextureLoader, ImageBitmapLoader, color space, flipY)
7. HDR / EXR / UltraHDR environments, PMREM, cube maps
8. Compressed textures (KTX2 / Basis)
9. Video and canvas textures (pointer)
10. Other model loaders (OBJ+MTL, FBX, Collada, STL, PLY, SVG, fonts, USD, LUT)
11. Gaussian splat loaders
12. Exporters
13. Decoder files in node_modules
14. Disposing loaded assets
15. See also

---

## 1. Loader base API, async patterns, LoadingManager

All loaders extend `Loader` (`src/loaders/Loader.js`): `load(url, onLoad, onProgress, onError)` plus `loadAsync(url, onProgress) -> Promise`. Prefer `loadAsync`.

```js
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';

const gltf = await new GLTFLoader().loadAsync('model.glb', (e) => console.log(e.loaded / e.total));
scene.add(gltf.scene);

// parallel
const tl = new THREE.TextureLoader(), gl = new GLTFLoader();
const [albedo, normal, model] = await Promise.all([
  tl.loadAsync('a.jpg'), tl.loadAsync('n.jpg'), gl.loadAsync('m.glb'),
]);
```

Gotchas:
- `TextureLoader.load()` returns the Texture immediately (image fills in later); `loadAsync` resolves when the image has loaded. `TextureLoader` has no progress events (dropped in r84): `onProgress` never fires.
- `onProgress` is an XHR/fetch `ProgressEvent`; `total` is 0 when the server omits `Content-Length` or uses compression (gzip) -> do not divide blindly.
- `loadAsync` rejects on error; `load()` swallows errors unless you pass `onError` (or `manager.onError`). Always handle.
- `Loader.abort()` exists (abstract; implemented by FileLoader, ImageBitmapLoader). `manager.abort()` aborts all requests through that manager (needs `AbortSignal.any`).

### LoadingManager

```js
const manager = new THREE.LoadingManager(
  () => console.log('all loaded'),                           // onLoad
  (url, loaded, total) => bar.style.width = `${loaded / total * 100}%`, // onProgress (per item)
  (url) => console.error('failed', url),                     // onError
);
manager.onStart = (url, loaded, total) => {};               // also settable as properties
const tl = new THREE.TextureLoader(manager);
const gl = new GLTFLoader(manager);                         // gltf's external textures/bins count too
```
- A default global manager `THREE.DefaultLoadingManager` is used when none passed.
- `onLoad` fires each time the pending count reaches 0 (can fire more than once if loads start later or in waves). Items = individual URL requests, so total grows as dependencies are discovered (glTF with N textures).
- `manager.addHandler(/\.tga$/i, new TGALoader())` / `getHandler` / `removeHandler`: pick loaders by URL pattern (used by MTL/OBJ/FBX/Collada for texture types).
- `manager.setURLModifier(url => ...)` / `resolveURL(url)`: remap URLs (blob URLs from dropped files, zip contents, data URIs). Revoke object URLs after load.
- `itemStart/itemEnd/itemError(url)`: for custom loaders.
- Use separate managers for separate progress bars.

```js
// load from drag-and-drop File objects
const files = new Map([...fileList].map((f) => [f.name, URL.createObjectURL(f)]));
const m = new THREE.LoadingManager();
m.setURLModifier((url) => files.get(url.split('/').pop()) ?? url);
```

---

## 2. Paths, CORS, credentials, Cache, URL modifier

`Loader` properties/setters (chainable):

| API | Meaning |
|---|---|
| `setPath(p)` | prefix for the **main** file: `setPath('models/').load('a.glb')` -> `models/a.glb` |
| `setResourcePath(p)` | prefix for **dependencies** (textures, .bin) referenced by the main file; if unset, GLTFLoader/OBJ etc. derive it from the main file's directory (`LoaderUtils.extractUrlBase`) |
| `setCrossOrigin('anonymous')` | `crossOrigin` for image loads. Default `'anonymous'`. WebGL texture upload fails (SecurityError) for images from other origins without CORS headers |
| `setWithCredentials(true)` | send cookies/auth with cross-origin fetch/XHR |
| `setRequestHeader({Authorization: 'Bearer ...'})` | custom headers (FileLoader) |
| `setPriority('high' \| 'low' \| 'auto')` (r187) | browser fetch-priority hint (`HTMLImageElement.fetchPriority` for image loaders); inherited by internally created loaders; e.g. `high` for the hero model, `low` for background props. Browsers may ignore it |
| `setCache('default' \| 'no-store' \| 'reload' \| 'no-cache' \| 'force-cache')` (r187) | HTTP cache mode passed to `fetch()` (`no-cache` revalidates, `no-store` bypasses); does not affect `THREE.Cache` or image-element requests |
| `FileLoader.setResponseType('arraybuffer'|'json'|'blob'|'document'|'')`, `setMimeType()` | low-level fetch (`FileLoader` uses fetch) |

- Absolute URLs (`http`, `//`, `data:`, `blob:`) ignore `path` prefix.
- Serve from an HTTP server (`vite`, `npx serve`): `file://` fails with CORS errors.
- glTF `.gltf` with relative texture paths: resources resolve against `resourcePath` or the .gltf URL; if you `parse()` an ArrayBuffer/string yourself, pass `path` (base URL) as 2nd arg or textures 404.
- WASM/MIME: the server must serve `.wasm` as `application/wasm` for streaming compile (fallback works otherwise).

### Cache

`THREE.Cache.enabled = false` by default. Enable once to cache responses of `FileLoader` (and thus most loaders) by URL: `THREE.Cache.enabled = true;` API: `add(key, file)`, `get(key)`, `remove(key)`, `clear()`, `files`. Caveats: ImageBitmapLoader/ImageLoader only de-duplicate concurrent requests when Cache is enabled; cached Blob/ArrayBuffer stay in memory until `Cache.clear()`; two `load()` of the same texture URL return two Texture objects (reuse the Texture yourself or `tex.clone()`; clones share `source`).

---

## 3. GLTFLoader canonical setup

```js
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { DRACOLoader } from 'three/addons/loaders/DRACOLoader.js';
import { KTX2Loader } from 'three/addons/loaders/KTX2Loader.js';
import { MeshoptDecoder } from 'three/addons/libs/meshopt_decoder.module.js';

const renderer = new THREE.WebGLRenderer({ antialias: true });

const draco = new DRACOLoader();
// optional: override bundled decoder location
draco.setDecoderPath('https://www.gstatic.com/draco/versioned/decoders/1.5.7/');   // folder containing draco_decoder.js/.wasm, draco_wasm_wrapper.js
// or self-host: draco.setDecoderPath('/draco/');  (copy node_modules/three/examples/jsm/libs/draco/gltf/)

const ktx2 = new KTX2Loader()
  .setTranscoderPath('/basis/')                // copy node_modules/three/examples/jsm/libs/basis/
  .detectSupport(renderer);                    // required BEFORE loading; picks BC/ASTC/ETC/PVRTC target

const loader = new GLTFLoader()
  .setDRACOLoader(draco)
  .setKTX2Loader(ktx2)
  .setMeshoptDecoder(MeshoptDecoder);          // plain object, not a loader

const gltf = await loader.loadAsync('model.glb');
scene.add(gltf.scene);
```

Facts (verified in r187 source/API):
- In r187, `DRACOLoader` and `KTX2Loader` default to decoders bundled next to the addon via `new URL('../libs/draco/draco_wasm_wrapper.js', import.meta.url)` / `libs/basis/basis_transcoder.*`. Works out of the box in bundlers that rewrite `new URL(..., import.meta.url)` (Vite, webpack 5); otherwise (CDN import map, strict bundlers, Next.js) the files 404: call `setDecoderPath`/`setTranscoderPath` with a folder you serve. Older tutorials requiring `setDecoderPath` first are partly obsolete but harmless.
- `DRACOLoader.setDecoderPath(path | {js, wasm, dep_js})`. `setDecoderConfig({type})` is deprecated (warns "will be removed in r194"); do not call it, the decoder type is picked automatically. `setWorkerLimit(n)` (default 4). Decoder/worker chosen automatically (WASM if supported). Create ONE DRACOLoader and reuse; `draco.dispose()` terminates workers when done (e.g. after the last glTF).
- `KTX2Loader.detectSupport(renderer)` accepts WebGLRenderer or WebGPURenderer; `detectSupportAsync` is **deprecated**. `ktx2.dispose()` terminates workers. `setWorkerLimit(n)`.
- `MeshoptDecoder` lives in `three/addons/libs/meshopt_decoder.module.js` (also `meshopt_clusterizer`, `meshopt_simplifier` there). Passed to `setMeshoptDecoder`; needed for `EXT_meshopt_compression`/`KHR_meshopt_compression`.
- Missing decoder throws: "No DRACOLoader instance provided", "setKTX2Loader must be called before loading KTX2 textures", "setMeshoptDecoder must be called before loading compressed files". Only needed if the file uses those extensions; set all three for generic viewers.
- `gltf-transform` / `gltfpack` (`-cc -tc`) produce meshopt + basisu files (see `examples/webgl_loader_gltf_compressed.html`: only KTX2 + Meshopt, no Draco). Draco + KTX2 combo: `examples/misc_exporter_usdz.html`.
- Examples in the repo load env via UltraHDRLoader or `RoomEnvironment` + `PMREMGenerator.fromScene(new RoomEnvironment(), 0.04).texture` (import `three/addons/environments/RoomEnvironment.js`), because glTF PBR materials render dark without `scene.environment`.
- `parse(data, path, onLoad, onError)` / `parseAsync(data, path)` for ArrayBuffer (GLB) or JSON string (glTF) you fetched yourself.
- Plugins: `loader.register(parser => new MyExtension(parser))` / `unregister`.
- WebGPURenderer uses the same GLTFLoader (examples `webgpu_loader_gltf*.html`); the GLTFLoader builds classic `MeshStandardMaterial`/`MeshPhysicalMaterial`, which WebGPURenderer maps to node materials.

---

## 4. glTF result structure, traversal, cloning

`gltf` (GLTFLoader~LoadObject):

| field | type | notes |
|---|---|---|
| `scene` | `Group` | default scene (`gltf.scenes[sceneIndex]`) |
| `scenes` | `Group[]` | all scenes |
| `animations` | `AnimationClip[]` | feed to `AnimationMixer(gltf.scene).clipAction(clip)` |
| `cameras` | `Camera[]` | cameras defined in file |
| `asset` | object | glTF `asset` metadata (generator, version, copyright) |
| `parser` | `GLTFParser` | `parser.json`, `getDependency('material', i)` etc. |
| `userData` | object | extra data from extensions |

Node `extras` land in `object.userData`. Names: `object.name` comes from glTF node names (`PropertyBinding.sanitizeNodeName`: whitespace becomes `_`; `[ ] . : /` are removed, so `getObjectByName` needs the sanitized name).

```js
const root = gltf.scene;
root.getObjectByName('Wheel_FL');
root.traverse((o) => {
  if (o.isMesh) {
    o.castShadow = o.receiveShadow = true;
    // glTF materials are MeshStandardMaterial / MeshPhysicalMaterial; envMapIntensity etc. available
    if (o.material.map) o.material.map.anisotropy = renderer.capabilities.getMaxAnisotropy();
  }
});

// auto-frame
const box = new THREE.Box3().setFromObject(root);
const size = box.getSize(new THREE.Vector3()).length();
const center = box.getCenter(new THREE.Vector3());

// play animation
const mixer = new THREE.AnimationMixer(root);
gltf.animations.forEach((clip) => mixer.clipAction(clip).play());
// in loop: mixer.update(clock.getDelta());
```

### Cloning

`object.clone()` shares geometry/materials but breaks skinned meshes (clone's `SkinnedMesh` still binds to original bones). Use SkeletonUtils:

```js
import * as SkeletonUtils from 'three/addons/utils/SkeletonUtils.js';
const copy = SkeletonUtils.clone(gltf.scene);      // clones hierarchy + rebinds skeletons
scene.add(copy);
const mixer2 = new THREE.AnimationMixer(copy);     // separate mixer per clone
```
- Geometry and materials are shared between clones (cheap); clone materials per instance if you tweak them: `mesh.material = mesh.material.clone()`.
- For hundreds of identical static meshes use `InstancedMesh`; skinned crowds need a custom GPU animation or BatchedMesh approach.
- Also in module: `SkeletonUtils.retarget`, `retargetClip`.
- Inspect original: loading the same URL twice with Cache enabled still parses twice; cloning `gltf.scene` is cheaper.

---

## 5. Supported glTF extensions (from GLTFLoader.js header)

Built in: `KHR_draco_mesh_compression`, `KHR_lights_punctual`, `KHR_materials_anisotropy`, `KHR_materials_clearcoat`, `KHR_materials_dispersion`, `KHR_materials_emissive_strength`, `KHR_materials_ior`, `KHR_materials_specular`, `KHR_materials_transmission`, `KHR_materials_iridescence`, `KHR_materials_unlit`, `KHR_materials_volume`, `KHR_mesh_quantization`, `KHR_meshopt_compression`, `KHR_texture_basisu`, `KHR_texture_transform`, `EXT_materials_bump`, `EXT_meshopt_compression`, `EXT_mesh_gpu_instancing`, `EXT_texture_avif`, `EXT_texture_webp`. (`KHR_materials_sheen` is also registered in source though absent from the header comment; example `webgl_loader_gltf_sheen.html`.)

Separate plugins: `KHR_gaussian_splatting` (`GLTFGaussianSplatLoaderExtension`, loadMesh returns `GaussianSplat` group, WebGPU only), `KHR_materials_variants`, `MSFT_texture_dds`, `KHR_animation_pointer` (third-party registrations), `NEEDLE_progressive`.

Mappings produced: base material -> `MeshStandardMaterial`; with physical extensions (clearcoat, transmission, volume, sheen, iridescence, anisotropy, ior, specular, dispersion) -> `MeshPhysicalMaterial`; `KHR_materials_unlit` -> `MeshBasicMaterial`. `KHR_materials_pbrSpecularGlossiness` is NOT supported in r186 (removed). Texture color spaces are set per slot automatically (sRGB for baseColor/emissive, none for others); `texture.flipY = false` for glTF.

---

## 6. Texture loading

```js
const loader = new THREE.TextureLoader(manager);
const tex = await loader.loadAsync('albedo.jpg');
tex.colorSpace = THREE.SRGBColorSpace;                        // MUST for color maps; TextureLoader leaves NoColorSpace
tex.anisotropy = renderer.capabilities.getMaxAnisotropy();    // WebGL; sharper at grazing angles
tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
// tex.generateMipmaps = true (default); minFilter default LinearMipmapLinearFilter
```

- `CubeTextureLoader` sets `SRGBColorSpace` itself; `TextureLoader` does NOT. GLTFLoader sets it itself; KTX2Loader derives it from the file; HDR/EXR loaders set `LinearSRGBColorSpace`.
- Data textures (normal/roughness/etc.): leave `NoColorSpace`.
- `flipY` default `true` (images flipped on upload to match UV origin bottom-left). glTF textures are authored with top-left convention: GLTFLoader sets `flipY = false`. Compressed (KTX2), DataTexture, render-target and ImageBitmap textures: no flip from Texture; for ImageBitmap use loader option.
- Memory: GPU memory ~ `width * height * 4 * 1.33` bytes regardless of JPG/PNG file size. A 4096x4096 map = ~90 MB. Keep dimensions small or use KTX2 (stays compressed on GPU, 4-8x smaller).
- Power-of-two not required in WebGL2/WebGPU; mipmaps work on any size.
- Same image used as `map` and `normalMap` with different color space: load/clone separately and set colorSpace on each (clones share `source`; colorSpace is per Texture object).
- Wait for textures: pass a `LoadingManager`, or `await Promise.all(...)`.
- Replacing the image later: set `tex.image = newImg; tex.needsUpdate = true`.

### ImageBitmapLoader (off-main-thread decode)

```js
const bl = new THREE.ImageBitmapLoader();
bl.setOptions({ imageOrientation: 'flipY', premultiplyAlpha: 'none' });   // reproduces Texture defaults (flipY true)
const bitmap = await bl.loadAsync('big.jpg');                              // returns ImageBitmap, NOT a Texture
const t = new THREE.Texture(bitmap);
t.colorSpace = THREE.SRGBColorSpace;
t.needsUpdate = true;
```
- `Texture.flipY` and `premultiplyAlpha` are ignored for ImageBitmap: set via `setOptions` before loading.
- GLTFLoader uses ImageBitmapLoader whenever possible (Chrome, Firefox); bitmaps are not GC'd: call `texture.dispose()` and, if you hold the bitmap, `bitmap.close()` (`texture.source.data.close?.()`).
- No `createImageBitmap`, Safari < 17 or Firefox < 98: GLTFLoader falls back to `TextureLoader` automatically.

---

## 7. HDR / EXR / UltraHDR environments, PMREM, cube maps

```js
import { HDRLoader } from 'three/addons/loaders/HDRLoader.js';       // .hdr (RGBE)
import { EXRLoader } from 'three/addons/loaders/EXRLoader.js';       // .exr
import { UltraHDRLoader } from 'three/addons/loaders/UltraHDRLoader.js'; // .jpg with gain map (e.g. royal_esplanade_2k.hdr.jpg)
import { JXLLoader } from 'three/addons/loaders/JXLLoader.js';         // .jxl HDR JPEG XL (r187), browser-native decode, half-float linear-sRGB; needs float16 Canvas2D + globalHDRHeadroom, so check support

const env = await new HDRLoader().loadAsync('studio.hdr');           // DataTexture, HalfFloatType default, LinearSRGBColorSpace
env.mapping = THREE.EquirectangularReflectionMapping;                // MUST set yourself
scene.environment = env;        // image-based lighting for PBR
scene.background = env;         // visible skybox (optional)
scene.backgroundBlurriness = 0.2; scene.environmentIntensity = 1;    // Scene props
```

- None of the HDR/EXR loaders set `mapping`: without `EquirectangularReflectionMapping` the texture is used as a plain 2D map and reflections look wrong/black.
- `setDataType(THREE.FloatType | THREE.HalfFloatType)` on HDRLoader/EXRLoader/UltraHDRLoader (Half is default and smaller; Float needs float-linear filtering support for smooth sampling). `EXRLoader`: `setOutputFormat(RGBAFormat|RGFormat|RedFormat)`, `setPart(i)`.
- `HDRCubeTextureLoader` (addon) for six HDR faces.
- UltraHDRLoader is the repo's canonical model-viewer environment source (`webgl_loader_gltf.html`): small JPEG-sized files with HDR range.
- PMREM: WebGLRenderer auto-runs `PMREMGenerator` on an equirect/cube assigned to `scene.environment`/`material.envMap` (cached on the texture; `needsPMREMUpdate`). Manual route for control:
```js
const pmrem = new THREE.PMREMGenerator(renderer);
const envRT = pmrem.fromEquirectangular(env);          // also fromScene(scene, sigma, near, far), fromCubemap(cube)
scene.environment = envRT.texture;
env.dispose(); pmrem.dispose();                        // free the source & generator; keep envRT until swapped
```
  PMREMGenerator is typed against WebGLRenderer; WebGPURenderer performs the prefilter internally via node environment (assigning `scene.environment` works the same).
- Procedural environment: `new RoomEnvironment()` (addons/environments) with `fromScene(room, 0.04)`; `environment.dispose()` after.
- Cube map (6 LDR images): order `px, nx, py, ny, pz, nz`:
```js
const cube = await new THREE.CubeTextureLoader().setPath('textures/cube/').loadAsync(['px.jpg','nx.jpg','py.jpg','ny.jpg','pz.jpg','nz.jpg']);
scene.background = cube; scene.environment = cube;     // colorSpace already SRGBColorSpace
```
  Cube maps follow a left-handed convention (+x right looking down +z); three.js is right-handed, so env maps appear mirrored vs. other tools (see CubeTextureLoader API note).
- Equirectangular LDR (jpg/png): `tex.mapping = EquirectangularReflectionMapping; tex.colorSpace = SRGBColorSpace`.
- `scene.background = tex` for equirect requires the mapping too.

---

## 8. Compressed textures (KTX2 / Basis)

```js
const ktx2 = new KTX2Loader().setTranscoderPath('/basis/').detectSupport(renderer);
const tex = await ktx2.loadAsync('albedo.ktx2');     // CompressedTexture; colorSpace read from the file's DFD
material.map = tex;
// when finished with all KTX2 work: ktx2.dispose();
```
- Transcodes Basis Universal (ETC1S or UASTC) to the GPU format available (BC7/ASTC/ETC2/PVRTC/uncompressed fallback) in a worker. Create files with `toktx` / `gltf-transform` / `gltfpack -tc`. Normal maps: UASTC; color maps: ETC1S for size or UASTC for quality.
- `detectSupport(renderer)` is mandatory before `load`. One loader instance per renderer.
- CompressedTexture: `flipY` false (pre-flipped at encode time), mipmaps embedded; `generateMipmaps` irrelevant. Cannot be modified or read back on CPU.
- Other compressed loaders (addons): `DDSLoader`, `KTXLoader`, `PVRLoader` (extend `CompressedTextureLoader`), `TGALoader`/`TIFFLoader` (DataTextureLoader).
- Examples: `webgl_loader_texture_ktx2.html`, `webgpu_loader_texture_ktx2.html`.
- Export a texture/render target to KTX2: `KTX2Exporter` (section 12).

---

## 9. Video and canvas textures

See `materials.md` section 8 for `VideoTexture`, `CanvasTexture`, `DataTexture`. Loading-specific notes:
- `<video>` needs `crossOrigin = 'anonymous'`, `muted` + `playsInline` for autoplay; `video.play()` after a user gesture otherwise; WebGPURenderer needs `colorSpace = SRGBColorSpace`.
- Canvas redraw -> `canvasTexture.needsUpdate = true`. Webcam: `navigator.mediaDevices.getUserMedia` -> `video.srcObject = stream` -> `VideoTexture`.
- Remember to `video.pause(); video.src = ''` and `texture.dispose()` when removing.

---

## 10. Other model loaders (addons, `three/addons/loaders/*.js`)

| Loader | Returns | Notes |
|---|---|---|
| `OBJLoader` | `Group` of Meshes | no materials unless `setMaterials(mtl)`; default `MeshPhongMaterial` |
| `MTLLoader` | `MaterialCreator` | `mtl = await new MTLLoader().setPath(dir).loadAsync('a.mtl'); mtl.preload(); obj.setMaterials(mtl)`; `setMaterialOptions({...})` |
| `FBXLoader` | `Group` (+ `.animations`) | textures resolved relative to file; `trimAnimationClips`; scale often 100x (cm); embedded textures supported |
| `ColladaLoader` | `{scene, animations, kinematics, library}` | legacy; `load` only (`new ColladaLoader()` takes no manager arg in docs) |
| `STLLoader` | `BufferGeometry` | add your own material; binary & ASCII |
| `PLYLoader` | `BufferGeometry` | vertex colors in `color` attribute -> `vertexColors: true`; `setPropertyNameMapping`, `setCustomPropertyNameMapping` |
| `SVGLoader` | `{paths, xml}` | `SVGLoader.createShapes(path)` -> `ShapeGeometry`; `defaultDPI`, `defaultUnit` |
| `FontLoader` | `Font` | for `TextGeometry`; typeface JSON |
| `TTFLoader` | typeface JSON | `new Font(json)`; `reversed` option |
| `USDLoader` | `Group` | USD, USDA, USDC, USDZ |
| `LUTCubeLoader` | `{title, size, domainMin, domainMax, texture3D}` (`Data3DTexture`) | `.cube` color LUTs; `setType(UnsignedByteType|FloatType)`; use with LUTPass/`lut3D` |
| `DRACOLoader` (standalone `.drc`) | `BufferGeometry` | no materials; `geometry.computeVertexNormals()` if needed |
| Others | | `ThreeMFLoader`, `AMFLoader`, `BVHLoader`, `GCodeLoader`, `KMZLoader`, `LDrawLoader`, `LWOLoader`, `MD2Loader`, `PCDLoader`, `PDBLoader`, `Rhino3dmLoader`, `TDSLoader`, `VOXLoader`, `VRMLLoader`, `VTKLoader`, `XYZLoader`, `MaterialXLoader`, `IESLoader`, `NRRDLoader` |

```js
import { OBJLoader } from 'three/addons/loaders/OBJLoader.js';
import { MTLLoader } from 'three/addons/loaders/MTLLoader.js';
const mtl = await new MTLLoader().setPath('models/').loadAsync('tree.mtl');
mtl.preload();
const obj = await new OBJLoader().setMaterials(mtl).setPath('models/').loadAsync('tree.obj');
scene.add(obj);
```

Core (non-addon) loaders in `three`: `FileLoader`, `ImageLoader`, `ImageBitmapLoader`, `TextureLoader`, `CubeTextureLoader`, `DataTextureLoader`/`CompressedTextureLoader` (abstract bases), `ObjectLoader` (three.js JSON scene), `BufferGeometryLoader`, `MaterialLoader`, `AnimationLoader`, `AudioLoader`, `NodeLoader`, `NodeObjectLoader`, `NodeMaterialLoader`.

Recommendation (manual): prefer glTF/GLB; FBX/OBJ/Collada only when unavoidable. Troubleshoot missing/distorted models: add `onError`, check the console, view the file in another glTF viewer, scale by 1000x / 0.001x, verify camera `near/far`, and that you used an HTTP server.

---

## 11. Gaussian splat loaders (new in recent releases; WebGPURenderer only)

`GaussianSplat` (`three/addons/objects/GaussianSplat.js`, extends Mesh) renders splats and works only with WebGPURenderer (WebGL2 `forceWebGL` fallback supported; plain WebGLRenderer is not). Import maps/package exports must resolve both `three/webgpu` and `three/tsl`. The loaders only decode to `BufferGeometry`.

```js
import * as THREE from 'three/webgpu';
import { GaussianSplat } from 'three/addons/objects/GaussianSplat.js';
import { SPLATLoader } from 'three/addons/loaders/SPLATLoader.js';

const renderer = new THREE.WebGPURenderer(); await renderer.init();
const geom = await new SPLATLoader().loadAsync('scene.splat');   // 32-byte rows: center, scale, color, rotation
scene.add(new GaussianSplat(geom));
```

| Loader | Format | Notes |
|---|---|---|
| `SPLATLoader` | `.splat` fixed-width | `parse(buffer) -> BufferGeometry` |
| `GaussianSplatPLYLoader` | INRIA 3DGS `.ply` | scans header `f_rest_N` to detect SH degree (0/9/24/45 -> 0/1/2/3) |
| `KSPLATLoader` | GaussianSplats3D `.ksplat` | SH exposed as `sphericalHarmonics1..3` uint32 attributes |
| `SPZLoader` | compressed `.spz` | `parse` may be async; `parseRawSPZ`, `parseRawSPZV4`; SH as `sphericalHarmonics1..3` |
| `GLTFGaussianSplatLoaderExtension` | glTF `KHR_gaussian_splatting` | `loader.register(p => new GLTFGaussianSplatLoaderExtension(p))` |

Large splat files: serve compressed (`.spz`/`.ksplat`) and show progress via `loadAsync(url, onProgress)`.

---

## 12. Exporters (`three/addons/exporters/*.js`)

| Exporter | Call | Output |
|---|---|---|
| `GLTFExporter` | `await new GLTFExporter().parseAsync(scene, {binary:true})` | `ArrayBuffer` (glb) or JSON object when `binary:false` |
| `USDZExporter` | `await new USDZExporter().parseAsync(scene)` | `ArrayBuffer` (AR Quick Look) |
| `OBJExporter` | `parse(object)` | string |
| `STLExporter` | `parse(scene, {binary:true})` | string or `DataView`/ArrayBuffer |
| `PLYExporter` | `parse(object, onDone, options)` | string or ArrayBuffer |
| `DRACOExporter` | `await parseAsync(meshOrPoints, options)` | `Int8Array` (`MESH_EDGEBREAKER_ENCODING`/`MESH_SEQUENTIAL_ENCODING`) |
| `EXRExporter` | `await parse(renderer, renderTarget, options)` or `parse(dataTexture, options)` | `Uint8Array` |
| `KTX2Exporter` | `await parse(renderer, renderTarget)` or `parse(dataTexture)` | `Uint8Array` |

GLTFExporter options: `trs`(false: export matrix), `onlyVisible`(true), `binary`(false), `maxTextureSize`, `animations`, `includeCustomExtensions`, `copyright`. `register(cb)` for extensions; `setTextureUtils(WebGLTextureUtils | WebGPUTextureUtils)` only for compressed textures. Exports `MeshStandard/Physical` + basic materials; ShaderMaterial / node graphs are not exported.

```js
const glb = await new GLTFExporter().parseAsync(scene, { binary: true, onlyVisible: true });
const a = Object.assign(document.createElement('a'), { href: URL.createObjectURL(new Blob([glb], { type: 'model/gltf-binary' })), download: 'scene.glb' });
a.click(); URL.revokeObjectURL(a.href);
```

Texture to PNG: draw to canvas, or `ImageUtils.getDataURL(image, type)` / `ImageUtils.sRGBToLinear(image)` (core `ImageUtils`).

`WorkerPool` (addon util): generic worker pool (`setWorkerCreator`, `postMessage`, `setWorkerLimit`, `dispose`) used by Draco/KTX2 loaders.

---

## 13. Decoder files in node_modules

```
node_modules/three/examples/jsm/libs/
  draco/            draco_decoder.js, draco_decoder.wasm, draco_wasm_wrapper.js
  draco/gltf/       same three files, tuned for glTF KHR_draco_mesh_compression (use for GLTFLoader)
  basis/            basis_transcoder.js, basis_transcoder.wasm
  meshopt_decoder.module.js (+ meshopt_clusterizer, meshopt_simplifier)
  fflate.module.js, ktx-parse.module.js, zstddec.module.js, utif.module.js (used by loaders)
```
Copy `draco/gltf/` and `basis/` into your `public/` folder (Vite: `public/draco/`, `public/basis/`) and point `setDecoderPath('/draco/')` / `setTranscoderPath('/basis/')`; trailing slash required. CDN alternatives: `https://www.gstatic.com/draco/versioned/decoders/1.5.7/` (Draco) or `https://cdn.jsdelivr.net/npm/three@0.187.0/examples/jsm/libs/draco/gltf/` / `.../libs/basis/`. Verify the CDN version matches your installed `three`.

---

## 14. Disposing loaded assets

GPU memory is not garbage collected. When removing a model/scene or switching levels:

```js
function disposeObject(root) {
  root.traverse((o) => {
    o.geometry?.dispose();
    const mats = Array.isArray(o.material) ? o.material : o.material ? [o.material] : [];
    for (const m of mats) {
      for (const v of Object.values(m)) if (v?.isTexture) { v.source.data?.close?.(); v.dispose(); }  // ImageBitmap.close
      m.dispose();
    }
    o.skeleton?.dispose?.();          // SkinnedMesh bone texture
  });
  root.removeFromParent();
}
```
- Shared resources between clones: dispose only once, after all users are gone (disposed resources are re-uploaded if rendered again).
- `InstancedMesh.dispose()`, `RenderTarget.dispose()`, `PMREMGenerator.dispose()`, `DRACOLoader.dispose()`, `KTX2Loader.dispose()` too. `renderer.dispose()` for full teardown.
- Also remove event listeners, stop `AnimationMixer` (`mixer.stopAllAction(); mixer.uncacheRoot(root)`), and revoke blob URLs.
- Check with `renderer.info.memory` (`geometries`, `textures`) and `renderer.info.programs`.
- Manual `cleanup`: write a `ResourceTracker` that records every geometry/material/texture/Object3D you create and disposes them together.

---

## 15. See also

API pages (`references/api/`): `Loader.md`, `LoadingManager.md`, `FileLoader.md`, `TextureLoader.md`, `ImageBitmapLoader.md`, `CubeTextureLoader.md`, `GLTFLoader.md`, `DRACOLoader.md`, `KTX2Loader.md`, `HDRLoader.md`, `EXRLoader.md`, `UltraHDRLoader.md`, `OBJLoader.md`, `MTLLoader.md`, `FBXLoader.md`, `ColladaLoader.md`, `STLLoader.md`, `PLYLoader.md`, `SVGLoader.md`, `FontLoader.md`, `TTFLoader.md`, `USDLoader.md`, `SPLATLoader.md`, `GaussianSplatPLYLoader.md`, `KSPLATLoader.md`, `SPZLoader.md`, `GLTFGaussianSplatLoaderExtension.md`, `GaussianSplat.md`, `GLTFExporter.md`, `USDZExporter.md`, `OBJExporter.md`, `STLExporter.md`, `PLYExporter.md`, `EXRExporter.md`, `KTX2Exporter.md`, `DRACOExporter.md`, `Cache.md`, `ImageUtils.md`, `WorkerPool.md`, `module-SkeletonUtils.md`, `LUTCubeLoader.md`, `PMREMGenerator.md`, `Texture.md`, `CompressedTexture.md`, `CubeTexture.md`.

Sibling reference: `materials.md`.

Official: https://threejs.org/docs/#GLTFLoader, https://threejs.org/docs/#DRACOLoader, https://threejs.org/docs/#KTX2Loader, https://threejs.org/docs/#LoadingManager, https://threejs.org/docs/#Loader, https://threejs.org/docs/#TextureLoader, https://threejs.org/docs/#HDRLoader, https://threejs.org/docs/#GLTFExporter, https://threejs.org/manual/#en/loading-3d-models, https://threejs.org/manual/#en/load-gltf, https://threejs.org/manual/#en/load-obj, https://threejs.org/manual/#en/textures, https://threejs.org/manual/#en/canvas-textures, https://threejs.org/manual/#en/cleanup
