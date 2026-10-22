# three.js versions and migration (target: r186, three@0.186.1)

## When to read this

Read this before writing or reviewing any three.js code, before suggesting install or CDN snippets, and whenever existing code or a tutorial uses an API you do not recognise. It tells you which release is current, how the package is laid out, which patterns are outdated (with the revision that changed them), and what is coming in r187. Sources: the official Migration Guide wiki, `docs/llms.txt`, and the r186 checkout (`package.json`, `src/`, `build/`, `examples/jsm/`). Where the migration guide and `src/` disagree, `src/` is stated explicitly.

## Contents

1. Version facts
2. Package layout: exports map, build files, bundlers, types
3. CDN import maps
4. Outdated patterns to never emit (old -> modern)
5. Still-deprecated names in r186 (warn vs gone)
6. Per-revision changelog r186 -> r150
7. Notable changes before r150
8. r186 -> r187 upcoming changes (in development)
9. Release highlights r185 and r186
10. See also

---

## 1. Version facts

- Current stable: r186, npm `three@0.186.1` (`package.json` "version": "0.186.1"). Always write "0.186.x" when speaking generally; pin `0.186.1` in snippets.
- In development: r187 (the Migration Guide already has a "186 -> 187" section).
- Release cadence: roughly one release per month; revision numbers are integers (r185, r186, r187), npm versions are `0.<rev>.<patch>`.
- Deprecation window: "deprecation warnings last for 10 releases" (top of the Migration Guide). Update old projects in increments of 10 revisions. Since r141 "Legacy code is going to be removed from the core after ten releases".
- Revision string: `export const REVISION = '186';` in `src/constants.js`. Available as `THREE.REVISION` or `import { REVISION } from 'three'`.
- Check installed version:
  - `npm ls three`
  - `node -e "import('three').then(m => console.log(m.REVISION))"`
  - in the browser: `console.log(THREE.REVISION)` or `import { REVISION } from 'three'`.
- Rule: write r186 code. When the user's project pins an older version, read section 6 for the revision where each API changed and match their version.

## 2. Package layout

### package.json facts (r186)

- `"type": "module"`, `"main": "./build/three.cjs"`, `"module": "./build/three.module.js"`.
- `"sideEffects": ["./src/nodes/**/*"]` (everything else is tree-shakeable).
- `"files"`: `build`, `examples/jsm`, `LICENSE`, `package.json`, `README.md`, `src`.
- No `types` field and no `@types` dependency: types are NOT bundled. Install `@types/three` (maintained at https://github.com/three-types/three-ts-types; the Migration Guide r125 -> r126 entry says declaration files moved there). Match `@types/three` minor to the three revision (e.g. `@types/three@0.186.x`) - this matching convention is not stated in the sources, verify on npm.

### exports map (complete)

| Specifier | Resolves to |
|---|---|
| `three` (import) | `./build/three.module.js` |
| `three` (require) | `./build/three.cjs` |
| `three/webgpu` | `./build/three.webgpu.js` |
| `three/tsl` | `./build/three.tsl.js` |
| `three/addons` | `./examples/jsm/Addons.js` (barrel re-exporting all addons) |
| `three/addons/*` | `./examples/jsm/*` (e.g. `three/addons/controls/OrbitControls.js`) |
| `three/examples/jsm/*` | `./examples/jsm/*` (older long form, still valid) |
| `three/examples/fonts/*` | `./examples/fonts/*` |
| `three/src/*` | `./src/*` (raw source modules; avoid - double-bundles core) |

Not exported: `three/build/*`, `three/examples/js/*` (removed r148). `three/webgpu.nodes` does not exist as an export (see build files).

Prefer `three/addons/...` over `three/examples/jsm/...` in new code (the llms.txt and docs use `three/addons/`).

### Build files in `build/` (r186 checkout)

| File | Source entry | What it is |
|---|---|---|
| `three.module.js` | `src/Three.js` | WebGL build: `export * from './Three.Core.js'` plus `WebGLRenderer`, `WebGLCubeRenderTarget`, `ShaderLib`, `UniformsLib`, `UniformsUtils`, `ShaderChunk`, `PMREMGenerator`, `WebGLUtils`. Small (~660 KB unminified) because it imports `three.core.js`. |
| `three.core.js` | `src/Three.Core.js` | Renderer-independent core (Object3D, geometries, materials, math, loaders, `Timer`, `Clock`, `REVISION`...). Shared by `three.module.js` and `three.webgpu.js`. |
| `three.webgpu.js` | `src/Three.WebGPU.js` | `export * from './Three.Core.js'` + `NodeMaterials` + `WebGPURenderer`, `WebGPUBackend`, `WebGLBackend` (fallback), `Renderer`, `Backend`, `Lighting`, `BundleGroup`, `QuadMesh`, its own `PMREMGenerator`, `RenderPipeline`, `DirectRenderPipeline`, `PostProcessing`, `ReadbackBuffer`, `RendererUtils`, `CubeRenderTarget`, `StorageTexture`, `Storage3DTexture`, `StorageArrayTexture`, `StorageBufferAttribute`, `StorageInstancedBufferAttribute`, `IndirectStorageBufferAttribute`, `IESSpotLight`, `ProjectorLight`, `NodeLoader`, `NodeObjectLoader` and node classes. |
| `three.webgpu.nodes.js` | `src/Three.WebGPU.Nodes.js` | Variant with `WebGPURenderer` from `WebGPURenderer.Nodes.js` (node-only, no WebGL-GLSL path). Not in the exports map; only reachable via a deep path. Do not recommend. |
| `three.tsl.js` | `src/Three.TSL.js` | Flat re-export of TSL functions (`float`, `vec3`, `texture`, `uv`, `Fn`, `uniform`, ...). Imports from `three/webgpu`. |
| `three.cjs` | (hand-written shim) | Deprecated CommonJS shim. It emits `process.emitWarning(... code: 'THREE_CJS_DEPRECATED')` and does `module.exports = require('./three.module.js')` (require(esm)). Header: "three is ESM-only going forward ... will be removed in a future release." |

Absent in r186: `three.js`, `three.min.js`, `three.module.min.js` (the UMD builds `build/three.js` / `build/three.min.js` were deprecated r150 and removed r161). Do not emit `<script src=".../three.min.js">`.

### Bundler behaviour and double-bundling

- Vite, webpack, esbuild, Rollup, Parcel: use the `import` condition -> `three.module.js` (+ `three.core.js`). `require()` hits the deprecated `three.cjs`.
- `three` and `three/webgpu` both `export *` from the same `three.core.js`. In a bundler this resolves to one module instance only if both entries are loaded from the same installed package. Do not mix `three/src/*` imports or a second installed copy with the build files, or core classes (e.g. `Object3D`, `Color`) get duplicated and `instanceof` checks break.
- WebGPU apps: import everything from `three/webgpu` (it re-exports all of core) - do NOT also `import * as THREE from 'three'` in the same app; `three/webgpu` already contains the core and its own `PMREMGenerator`. TSL functions from `three/tsl`.
- In `three.tsl.js` build config `external: ['three/webgpu']` (rollup.config.js), so `three/tsl` and `three/webgpu` must resolve to the same package copy (in an import map, map both).
- Addons (`three/addons/*`) import the bare specifier `three` (since r128: "ES6 modules in `examples/jsm` now import using the bare specifier `three`"). WebGPU-only addons import `three/webgpu` / `three/tsl`. An import map (browser) or bundler alias must resolve these.
- esbuild-style bundlers require file extensions for `examples/jsm` and `examples/fonts` imports (r137): always write `.js`.
- ESM only: CommonJS (`three.cjs`) is deprecated in r186 (see header above; the Migration Guide gives no revision for this). Use `import`, set `"type": "module"` or use a bundler.
- Tree-shaking: r186 removed top-level side effects from node modules (#34332, per release notes); `sideEffects` in package.json only lists `./src/nodes/**/*`.
- Dev servers: Vite generally needs no config; if you see duplicate-three warnings, use `resolve.dedupe: ['three']` (general bundler practice, not from the sources).

## 3. CDN import maps

The official `llms.txt` pattern (note: it pins `0.186.0`; npm latest is `0.186.1`). Pin an exact version; never use unversioned `three` URLs.

### WebGL (default)

```html
<script type="importmap">
{
  "imports": {
    "three": "https://cdn.jsdelivr.net/npm/three@0.186.1/build/three.module.js",
    "three/addons/": "https://cdn.jsdelivr.net/npm/three@0.186.1/examples/jsm/"
  }
}
</script>
<script type="module">
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
</script>
```

unpkg equivalent:

```html
<script type="importmap">
{
  "imports": {
    "three": "https://unpkg.com/three@0.186.1/build/three.module.js",
    "three/addons/": "https://unpkg.com/three@0.186.1/examples/jsm/"
  }
}
</script>
```

Important: `three.module.js` imports `./three.core.js` by relative path, so the CDN directory structure must be preserved (jsdelivr/unpkg do this). Do not copy only `three.module.js` to your own server.

### WebGPU + TSL variant

```html
<script type="importmap">
{
  "imports": {
    "three": "https://cdn.jsdelivr.net/npm/three@0.186.1/build/three.webgpu.js",
    "three/webgpu": "https://cdn.jsdelivr.net/npm/three@0.186.1/build/three.webgpu.js",
    "three/tsl": "https://cdn.jsdelivr.net/npm/three@0.186.1/build/three.tsl.js",
    "three/addons/": "https://cdn.jsdelivr.net/npm/three@0.186.1/examples/jsm/"
  }
}
</script>
<script type="module">
import * as THREE from 'three/webgpu';
import { texture, uv, color } from 'three/tsl';
const renderer = new THREE.WebGPURenderer();
await renderer.init();
</script>
```

The `"three"` key mapped to `three.webgpu.js` is a safe pattern so addons that `import ... from 'three'` share the same module (and the same core) as the app; this mapping is the common approach in the official WebGPU examples but is not spelled out in `llms.txt` - verify if unsure. Mapping `three` to `three.module.js` AND `three/webgpu` to `three.webgpu.js` also works but then addons get a different `THREE` instance from your `WebGPURenderer` code, which breaks `instanceof` checks on shared classes only if core is duplicated; both builds load the same `three.core.js` URL so browsers dedupe it.

Notes:
- Import-map-required since r137: "The ES6 import of three.js and examples/jsm modules in web sites now requires the usage of an import map to resolve the `three` bare import specifier."
- Do not use `esm.sh`/skypack hacks; r128 note about skypack is obsolete now that import maps are supported.
- `llms.txt` guidance: WebGLRenderer = default, mature; WebGPURenderer = when you need TSL, compute shaders, node-based materials. `await renderer.init()` is required before sync calls unless you use `renderer.setAnimationLoop()` (r181).

## 4. Outdated patterns to never emit

Format: Old -> Modern (revision of change, per Migration Guide unless noted).

| Old (never emit) | Modern (r186) | Rev |
|---|---|---|
| `<script src=".../three.min.js">` / `build/three.js` / cdnjs `r128` | Import map + `<script type="module">` | deprecated r150, removed r161 |
| `examples/js/...` scripts, `THREE.OrbitControls` globals | `import { OrbitControls } from 'three/addons/controls/OrbitControls.js'` | removed r148 |
| `examples/js/libs/draco/`, `.../basis/` paths | `examples/jsm/libs/draco/`, `examples/jsm/libs/basis/` (`three/addons/libs/...`) | r148 |
| `THREE.Geometry`, `Face3`, `geometry.vertices`, `faces` | `BufferGeometry` + attributes (`setAttribute('position', new Float32BufferAttribute(...))`) | Geometry removed from core r125 (shim `examples/jsm/deprecated/Geometry.js`), class deleted r141 |
| `BoxBufferGeometry`, `SphereBufferGeometry`... | `BoxGeometry`, `SphereGeometry`... (all are BufferGeometry) | alias deprecated r145 |
| `renderer.outputEncoding = THREE.sRGBEncoding` | `renderer.outputColorSpace = THREE.SRGBColorSpace` (default already) | r152 |
| `texture.encoding = THREE.sRGBEncoding` | `texture.colorSpace = THREE.SRGBColorSpace` (colour/albedo/emissive maps); data maps (normal, roughness, metalness, ao) stay `NoColorSpace` | r152 |
| `THREE.LinearEncoding` | `THREE.LinearSRGBColorSpace` | r152 |
| `THREE.ColorManagement.legacyMode = false` | `THREE.ColorManagement.enabled = true` (default true since r152) | r150/r152 |
| `renderer.physicallyCorrectLights = true` | removed; `useLegacyLights = false` r150; legacy lights removed afterwards. Light intensity is physical (candela/lux) | r150, r155 |
| `renderer.useLegacyLights = ...` | Do not set. Default `false` since r155 and deprecated. Tune intensities for physical units (point/spot in candela, `decay = 2`) | r155 |
| `renderer.gammaOutput`, `gammaInput`, `gammaFactor`, `GammaEncoding` | `outputColorSpace`, `texture.colorSpace`; gamma pass if needed | gammaInput/Output removed r112, gammaFactor r136 |
| `GammaCorrectionShader` / `ShaderPass(GammaCorrectionShader)` at end of EffectComposer | `OutputPass` (tone mapping + colour-space conversion, reads renderer settings, no ctor params) | r153/r155 |
| `new EffectComposer` with `UnsignedByteType` render targets | Default composer target is `HalfFloatType` since r153 | r153 |
| `AdaptiveToneMappingPass` | `OutputPass` | removed r153 |
| `scene.add( transformControls )` | `scene.add( transformControls.getHelper() )` (TransformControls extends `Controls`) | r169 |
| `new OrbitControls( camera )` (no element), `document` as domElement | `new OrbitControls( camera, renderer.domElement )`; `Controls.connect( element )` needs a DOM element | r110, r175 |
| `OrbitControls` key events assumed | call `controls.listenToKeyEvents( window )` | r125 |
| `DragControls.activate()/deactivate()/getObjects()/setObjects()/getRaycaster()` | `connect()/disconnect()`, `controls.objects`, `controls.raycaster` | r168 |
| `PointerLockControls.getObject()` | `controls.object` | r168 |
| `MeshFaceMaterial` | array of materials on `Mesh` (`new Mesh( geo, [ mat1, mat2 ] )` + geometry groups) | not in the r150+ guide entries; long gone |
| `Matrix4.getInverse( m )` / `Matrix3.getInverse` | `matrixInv.copy( matrix ).invert()` | r123 (r115 behaviour change); gone in r186 src |
| `Quaternion.inverse()` | `Quaternion.invert()` | r123 |
| `object.applyMatrix( m )`, `geometry.applyMatrix( m )` | `applyMatrix4( m )` | r113 |
| `Frustum.setFromMatrix` | `Frustum.setFromProjectionMatrix` | r113 |
| `THREE.Math.*` | `THREE.MathUtils.*` | r113 |
| `geometry.addAttribute()`, `removeAttribute()` | `setAttribute()`, `deleteAttribute()` | r110 |
| `BufferAttribute.dynamic`, `setDynamic( true )` | `attr.usage = THREE.DynamicDrawUsage` / `setUsage( THREE.DynamicDrawUsage )` | r110 |
| `attr.updateRange = { offset, count }` | `attr.addUpdateRange( start, count )`, `clearUpdateRanges()`; property is `updateRanges` | r159 |
| `BufferGeometryUtils.mergeBufferGeometries()` | `BufferGeometryUtils.mergeGeometries()` | r151 |
| `BufferGeometryUtils.mergeBufferAttributes()` | `mergeAttributes()` | r151 |
| `geometry.merge( other )` | `BufferGeometryUtils.mergeGeometries([...])` | removed r144 |
| `import { Curves } from 'CurveExtras'` | `import * as Curves from 'three/addons/curves/CurveExtras.js'` | r138 |
| `RGBELoader` | `HDRLoader` (`RGBELoader.js` still exists as a subclass that `console.warn`s) | r180 |
| `RGBMLoader` | `EXRLoader`, `HDRLoader`, `HDRCubeTextureLoader`, `UltraHDRLoader` | removed r180 |
| `BasisTextureLoader` | `KTX2Loader` (Basis Universal in `.ktx2`) | deprecated r137, removed r150 |
| `KTX2Loader.detectSupportAsync()` | `loader.detectSupport( renderer )` after `await renderer.init()` | r181 |
| `DRACOLoader.setDecoderConfig()` | deprecated; WASM will be the only path | r185 |
| `WebGLMultisampleRenderTarget` | `new WebGLRenderTarget( w, h, { samples: 4 } )` | r138 |
| `WebGLMultipleRenderTargets` | render target `count` option (MRT) | r162 |
| `WebGLRenderTargetCube` | `WebGLCubeRenderTarget` | r113 |
| `Scene.background = cubeRenderTarget` | assign `cubeRenderTarget.texture` | r127 |
| `FontLoader`, `Font`, `TextGeometry`, `ParametricGeometry` from `THREE` | `three/addons/loaders/FontLoader.js`, `three/addons/geometries/TextGeometry.js`, `.../ParametricGeometry.js` | r133 |
| `TextGeometry({ height })` | `TextGeometry({ depth })` | r163 |
| `SoftwareRenderer`, `RaytracingRenderer`, `WebGLDeferredRenderer` (and `CanvasRenderer`) | removed; use `WebGLRenderer`/`WebGPURenderer` | r110, r113, r113 (`CanvasRenderer`: not in the r110+ entries read) |
| `WebGL1Renderer`, WebGL 1 | removed; WebGL 2 only | deprecated r153, removed r163 |
| `import Stats from 'three/examples/jsm/libs/stats.module.js'` | `import Stats from 'three/addons/libs/stats.module.js'` (file exists in r186) | path alias |
| `dat.gui` | `lil-gui` (`three/addons/libs/lil-gui.module.min.js`) | r135 |
| `THREE.Clock` | `THREE.Timer` (in core since r179; `Clock` warns "has been deprecated" since r183). Use `timer.update()` + `timer.getDelta()`; call `timer.connect( document )` for Page Visibility handling | r179, r183, r174 |
| `renderer.setAnimationLoop( fn )` | KEEP using it (correct). With `WebGPURenderer` it also auto-inits | - |
| `renderer.renderAsync()`, `clearAsync()`, `initTextureAsync()`, `hasFeatureAsync()` | sync `render()`, `clear()`...; `await renderer.init()` once | deprecated r181 |
| `renderer.computeAsync()` | KEEP: not deprecated (r186). Awaits `init()` then calls `compute()`; use it when the renderer may be uninitialised | - |
| `new PostProcessing( renderer )` (WebGPU) | `new RenderPipeline( renderer )` (r186 `three/webgpu` still exports `PostProcessing` too) | r183 |
| `Material.vertexColors = 'VertexColors'` / `THREE.VertexColors`, `FaceColors` | `material.vertexColors = true` (boolean) | r114 |
| `material.skinning`, `morphTargets`, `morphNormals` | removed; automatic | r129, r131 |
| `MeshStandardMaterial.vertexTangents` | removed; `BufferGeometry.computeTangents()` is in core | r131, r125 |
| `uv2` attribute for `aoMap`/`lightMap` | `texture.channel` (0 = `uv`, 1 = second set); attributes renamed `uv, uv2, uv3, uv4` -> `uv, uv1, uv2, uv3` | r151 / r152 |
| `MeshPhysicalMaterial.transparency` | `.transmission` | r119 |
| `MeshPhysicalMaterial.iridescenceThicknessRange` | `iridescenceThicknessMinimum` / `iridescenceThicknessMaximum` | r187 (dev) |
| `material.envMapIntensity` to dim whole-scene env | `scene.environmentIntensity` (`envMapIntensity` only for material `envMap`) | r163 |
| `TwoPassDoubleSide` | removed; transparent double-sided materials render in two draw calls by default; `material.forceSinglePass = true` to disable | r149 |
| `PCFSoftShadowMap` | `PCFShadowMap` (now soft); removed from WebGPURenderer r186 | deprecated r182 (WebGL), removed r186 (WebGPU); marked `@deprecated since r186` in `src/constants.js` |
| `Source` (texture source class) | `TextureSource` (alias still exported with a warning) | r186 |
| `ShaderMaterial` custom GLSL on `WebGPURenderer` | use `NodeMaterial` + TSL (`MeshStandardNodeMaterial`, `colorNode`, `positionNode`...). `ShaderMaterial`/`onBeforeCompile` only work with `WebGLRenderer` | node materials WebGPU-only since r164 |
| `WebGLNodeBuilder` / node materials with `WebGLRenderer` | NodeMaterials require `WebGPURenderer` | r164 |
| TSL `import { ... } from 'three/examples/jsm/nodes/Nodes.js'` | `import { ... } from 'three/tsl'`; materials from `three/webgpu` | r166/r167, r171 |
| `renderer.library.addLight( CustomLightNode, CustomLight )` | `CustomLight.registerNode( CustomLightNode )` | r187 (dev) |
| `light.decay = 1` assumption | `PointLight`/`SpotLight` default `decay = 2` (physical) | r147 |
| `Scene.autoUpdate` | `Object3D.matrixWorldAutoUpdate` | r144 |
| `Object3D.DefaultUp`, `DefaultMatrixAutoUpdate`, `Euler.DefaultOrder` | `Object3D.DEFAULT_UP`, `DEFAULT_MATRIX_AUTO_UPDATE`, `DEFAULT_MATRIX_WORLD_AUTO_UPDATE`, `Euler.DEFAULT_ORDER` | r149 |
| `Raycaster.intersectObject( o )` assuming non-recursive | `recursive` defaults to `true` | r133 |
| `glslVersion` omitted with `#version 300 es` in ShaderMaterial | set `glslVersion: THREE.GLSL3`; never write the `#version` directive | r120 |
| `object.lookAt()` | unchanged API (`lookAt( x, y, z )` / `lookAt( Vector3 )`); no migration entry. Not outdated. | - |
| `Color` hex literal `new Color( 0xff0000 )` | unchanged; hex/CSS strings are interpreted as sRGB and converted to the working space (linear-srgb) when `ColorManagement.enabled` (default). Use `.setRGB( r, g, b, colorSpace )` for linear values | r152 |
| `ColorManagement.fromWorkingColorSpace` / `toWorkingColorSpace` | `workingToColorSpace` / `colorSpaceToWorking` | r177 |
| `WebGLRenderer.copyTextureToTexture( pos, src, dst )` old signature | `copyTextureToTexture( srcTexture, dstTexture, srcRegion, dstPosition, level )`; `copyTextureToTexture3D` deprecated r170 | r165 |
| `DataTexture3D`, `DataTexture2DArray` | `Data3DTexture`, `DataArrayTexture` | r138 |
| `RGBFormat`, `RGBIntegerFormat` | `RGBAFormat`, `RGBAIntegerFormat` | r137 |
| `SkinnedMesh.boneTransform()` | `applyBoneTransform()` | r151 |
| `BatchedMesh.applyGeometry()` | `addGeometry()` then `addInstance()` | r159, r166 |
| `GroundProjectedEnv` / `GroundProjectedSkybox` | `GroundedSkybox` | r151, r161 |
| `LightProbeGrid` | `LightProbeGridWebGL` | r186 |
| `PeppersGhostEffect`, `CinematicCamera`, `LogLuvLoader`, `HDRJPGLoader` | removed (`UltraHDRLoader` for HDR JPG) | r177, r170, r168, r167 |

Rules of thumb that follow:
- Import everything via ES modules and an import map or bundler; never globals.
- Colour: textures that hold colour data get `colorSpace = THREE.SRGBColorSpace`; the renderer already outputs sRGB. Do not tweak gamma.
- Lights: set intensities with physical units in mind; do not set `useLegacyLights`.
- Prefer `Timer` over `Clock` in new code (verified: `src/core/Clock.js` logs `'Clock: This module has been deprecated. Please use THREE.Timer instead.'`).
- Prefer `HDRLoader` over `RGBELoader`.

## 5. Legacy shims in r186

`src/Three.Legacy.js` exists but is EMPTY (0 bytes) in r186. Deprecated aliases from earlier revisions were removed (r185: "Deprecated code removed across the codebase", #33407, per release notes). Consequences:

- Anything the guide lists as "renamed" before r185 and not listed below is GONE: calling it throws `TypeError: x is not a function` or is silently `undefined` (e.g. `Matrix4.getInverse`, `BufferAttribute.updateRange`, `mergeBufferGeometries`, `Geometry`, `BoxBufferGeometry`). There is no warning.
- Names that still exist and only warn (found via `@deprecated` in `src/` and `examples/jsm`):

| Name | Replacement | Behaviour |
|---|---|---|
| `Clock` (`src/core/Clock.js`) | `Timer` | `warn( 'Clock: This module has been deprecated. Please use THREE.Timer instead.' )` (since r183) |
| `Source` (`src/textures/TextureSource.js`) | `TextureSource` | still exported; `warnOnce` (since r186); `isSource` flag deprecated for `isTextureSource` |
| `PCFSoftShadowMap` (`src/constants.js`) | `PCFShadowMap` | `@deprecated since r186`; WebGLRenderer treats as PCF with warning; removed from WebGPURenderer |
| `Matrix3.scale()`, `rotate()`, `translate()` | `makeScale()`, `makeRotation()`, `makeTranslation()` | `warnOnce` (since r185) |
| `ColorManagement.fromWorkingColorSpace()` / `toWorkingColorSpace()` | `workingToColorSpace()` / `colorSpaceToWorking()` | `warnOnce` (since r177) |
| GLSL `inverseTransformDirection` | `transformDirectionByInverseViewMatrix()` / `transformNormalByInverseViewMatrix()` | `#define` alias in `common.glsl.js` (since r185) |
| `RGBELoader` | `HDRLoader` | subclass with `console.warn` (since r180) |
| `USDZLoader` | `USDLoader` | `@deprecated, r179` |
| `VTKLoader` | export other format | warns; "will be removed with r194" (since r184) |
| `LWOLoader` | export other format | warns; "will be removed with r195" (since r185) |
| `SVGLoader.createShapes()` | `shapePath.toShapes()` | warns (since r185) |
| `KTX2Loader.detectSupportAsync()` | `detectSupport()` after `await renderer.init()` | warns (since r181) |
| `DRACOLoader.setDecoderConfig()` | none (WASM only) | `@deprecated` (since r185) |
| `DRACOExporter.parse()` | `parseAsync()` | `@deprecated` (since r185) |
| `VOXLoader` old result shape | new `onLoad` result is a scene | `@deprecated, r182` |
| `GaussianBlurNode` `resolution`, `premultipliedGaussianBlur()` | `resolutionScale`; `gaussianBlur()` with `premultipliedAlpha: true` | `warnOnce` |
| `GTAONode` `distanceExponent`, `distanceFallOff` | (no effect) | `@deprecated since r186` |
| `Line2NodeMaterial.lineColorNode` | `colorNode` | `warnOnce` (since r185) |
| `SkyMesh.isSky` | `isSkyMesh` | `@deprecated, r182` |
| `FirstPersonControls` method | no longer needed | `@deprecated, r184` |
| `MeshPhysicalMaterial.iridescenceThicknessRange` | `iridescenceThicknessMinimum/Maximum` | listed in 186 -> 187 section (dev) |

## 6. Per-revision changelog r186 -> r150

Exact API names from the official Migration Guide. Items in r187 are in section 8.

### 185 -> 186
- `Object3D` has a `dispose()` method (#34141). Custom subclasses with `dispose()` must call `super.dispose()`.
- `GTAONode`: `distanceExponent` and `distanceFallOff` deprecated, no effect (#33895).
- `BufferGeometryUtils.toTrianglesDrawMode()` no longer clones; mutates index in place (#33878). `clone()` first for old behaviour.
- `LightProbeGrid` -> `LightProbeGridWebGL`; `LightProbeGridHelper` -> `LightProbeGridHelperWebGL` (#33911).
- `PCFSoftShadowMap` removed with `WebGPURenderer`; use `PCFShadowMap` (soft now) (#33987).
- `SimplifyModifier` reimplemented on `meshoptimizer`; `SimplifyModifier.modify()` is now async (#34021).
- `Source` -> `TextureSource` (#34202).
- `up` uniform of `Sky`/`SkyMesh` removed; +Y up always.
- `DotScreenNode`/`RGBShiftNode`: `angle`, `amount`, `scale` accept numbers or nodes (#34417).

### 184 -> 185
- `WebGPURenderer` premultiplied-alpha implementation changed (#33369). If blending issues, set opaque `Scene.background` or opaque `renderer.setClearColor()`; use transparent only to blend with HTML background.
- `SSAAPassNode`: `clearColor`, `clearAlpha` removed (#33478); set clear colors on the renderer.
- `SVGLoader.createShapes()` deprecated; use `shapePaths.toShapes()` (#33503).
- `AnamorphicNode` removed; use `BloomNode` (#33600).
- `DRACOLoader.setDecoderConfig()` deprecated; always WASM later (#33602).
- `PLYLoader` honours PLY data types: `float64` -> `Float64Array` attributes; convert to `Float32BufferAttribute` to render (#33622).
- `PLYExporter` honours attribute data type; only `Uint8Array` colour attributes export as `uchar` (#33625).
- `GTAONode` more physically correct, darker and wider; lower `radius` and `scale` (#33654).
- `LWOLoader` deprecated (#33621).
- TSL: `positionLocal` does not include `SkinnedMesh` etc. transforms when used in `material.positionNode`; use `positionGeometry`.
- TSL: `directionToColor()` -> `packNormalToRGB()`; `colorToDirection()` -> `unpackRGBToNormal()` (#33715).
- WebGL shaders: `inverseTransformDirection()` deprecated; use `transformNormalByInverseViewMatrix()` (normals) / `transformDirectionByInverseViewMatrix()` (directions) (#33351).
- `Object3D.updateWorldMatrix()` honours `matrixWorldNeedsUpdate`; when `matrixAutoUpdate = false` and you write `Object3D.matrix`, set `matrixWorldNeedsUpdate = true` (#33746).
- `TiledLighting` removed; use `ClusteredLighting` (#33751).
- `Matrix3.translate()`, `scale()`, `rotate()` deprecated (#33757, #24733).
- `DRACOExporter.parse()` replaced by `parseAsync()` (#33789).
- `SSRNode` API slightly changed, optional denoiser (#33843).
- `SSGINode` switched to `RG11B10` internal render target; see PR #33822 for node setup.

### 183 -> 184
- Background and environment map rotation aligned with object rotation (#33077, #33232).
- `FirstPersonControls`: new interaction model, better mobile support (#33124).
- Raw WebGL 2 pixel storage: use `renderer.state.pixelStorei()` (#33227).
- `FBXLoader` auto-converts +Z-up to +Y-up; remove manual rotations.
- `VTKLoader` deprecated (#33363).
- `FileLoader.load()` and `ImageBitmapLoader.load()` return nothing; use `onLoad()` (#33380).

### 182 -> 183
- `PostProcessing` -> `RenderPipeline`.
- `SSRNode` blend changed: use additive blending instead of `blendColor()`.
- `Clock` deprecated; use `Timer`.
- `WebGPURenderer` shadows improved; reduce/remove shadow bias.
- `RoomEnvironment` scene position updated; PMREM lighting looks different (#32646).
- Legacy gamma correction removed from `Sky`/`SkyMesh` (#32677).
- `MeshPostProcessingMaterial` removed.
- `WebGLCubeRenderTarget` unusable with `WebGPURenderer`; use `CubeRenderTarget` (#32871).

### 181 -> 182
- `PCFSoftShadowMap` with `WebGLRenderer` deprecated; use `PCFShadowMap` (soft now).
- `WebGPURenderer` `colorBufferType` param -> `outputBufferType`; `getColorBufferType()` -> `getOutputBufferType()`.
- `VOXLoader.load()` changed: `onLoad()` result holds a scene with parsed meshes (#32488).

### 180 -> 181
- Indirect specular for PBR improved (#32054); energy conservation, rough materials (> 0.5) brighter (#32072); PMREM reflections improved (#32102, #32134).
- `WebGPURenderer`: `renderAsync()`, `clearAsync()`, `initTextureAsync()`, `hasFeatureAsync()` deprecated (`computeAsync()` was not). Renderer must be initialised first: automatic inside `renderer.setAnimationLoop()` or manual `await renderer.init()` (needed for on-demand rendering and feature detection).
- `WebGPURenderer.waitForGPU()` removed (#32012).
- `KTX2Loader.detectSupportAsync()` deprecated; use `detectSupport()` after `await renderer.init()`.
- TSL `PI2` -> `TWO_PI`.
- `GTAONode` AO only in `r` channel: `vec4( scenePassColor.rgb.mul( aoPass.r ), scenePassColor.a )`.
- `PassNode.setResolution()/getResolution()` -> `setResolutionScale()/getResolutionScale()`.
- `AfterImageNode.damp` is `Node<float>`; `afterImage()` accepts number, constant or uniform.
- `WaterMesh.resolution` -> `resolutionScale`.
- New JSDoc-generated API docs (English only; i18n dropped).

### 179 -> 180
- `DepthOfFieldNode` new implementation/API (see example `webgpu_postprocessing_dof`).
- `RGBELoader` -> `HDRLoader`.
- `RGBMLoader` removed; use `EXRLoader`, `HDRLoader`, `HDRCubeTextureLoader` or `UltraHDRLoader`.
- `resolution` of `ReflectorNode`, `AnamorphicNode`, `GaussianBlurNode` -> `resolutionScale` (scalar, not `Vector2`).
- Define `USE_REVERSEDEPTHBUF` -> `USE_REVERSED_DEPTH_BUFFER`; `USE_LOGDEPTHBUF` -> `USE_LOGARITHMIC_DEPTH_BUFFER`.

### 178 -> 179
- `Timer` moved into core (accessible as `THREE.Timer`; no addon import).
- `USDZLoader` deprecated; use `USDLoader`.
- `TRAAPassNode` -> `TRAANode`, new setup (example `webgpu_postprocessing_traa`).
- `WebGLRenderer` param `reverseDepthBuffer` -> `reversedDepthBuffer`.
- TSL `label()` -> `setName()`.
- `GaussianBlurNode` blur improved; double custom `sigma` values to match old strength.

### 177 -> 178
- `MultiplyBlending` and `SubtractiveBlending` require `Material.premultipliedAlpha = true`.

### 176 -> 177
- `ColorManagement.fromWorkingColorSpace()` -> `workingToColorSpace()`; `toWorkingColorSpace()` -> `colorSpaceToWorking()`.
- JSON Object Scene format version `4.6` -> `4.7`.
- `GLTFExporter` pushes parent node indices first.
- `PeppersGhostEffect` removed.

### 175 -> 176
- `CapsuleGeometry` param `length` -> `height`.
- WebP/AVIF support detection removed from `GLTFLoader`.
- `LottieLoader` deprecated; use `lottie-web`.

### 174 -> 175
- `AnimationClip.parseAnimation()` deprecated.
- `ParametricGeometries` -> `ParametricFunctions` (only functions now).
- `LUTImageLoader` ctor takes only a loading manager; `flipVertical` param removed; set loader `flip = true`.
- `SMAAPass` ctor: `width`/`height` removed.
- `HalftonePass` ctor: `width`/`height` removed.
- `Controls.connect()` requires a DOM element.

### 173 -> 174
- `Timer` no longer uses Page Visibility API automatically; call `timer.connect( document )` to restore.
- `RenderTarget.clone()` is a full structural clone (no shared texture resources).

### 172 -> 173
- `MeshGouraudMaterial` deprecated; use `MeshLambertMaterial`.
- `InstancedPointsNodeMaterial` removed; use `PointsNodeMaterial`.
- TSL `varying()` -> `toVarying()`; `vertexStage()` -> `toVertexStage()`.

### 171 -> 172
- `TextureNode.uv()` -> `TextureNode.sample()`.
- TSL `rangeFog( color, near, far )` deprecated -> `fog( color, rangeFogFactor( near, far ) )`.
- TSL `densityFog( color, density )` deprecated -> `fog( color, densityFogFactor( density ) )`.
- `DotScreenNode.center` removed.
- TSL `materialAOMap` -> `materialAO`; `shadowWorldPosition` -> `shadowPositionWorld`.
- `PostProcessingUtils` -> `RendererUtils`.

### 170 -> 171
- Imports: `three/webgpu` for `WebGPURenderer` and `NodeMaterial`; `three/tsl` for TSL.
- TSL `burn()`, `dodge()`, `screen()`, `overlay()` -> `blendBurn()`, `blendDodge()`, `blendScreen()`, `blendOverlay()`.
- TSL `storageObject()` deprecated -> `storage().setPBO( true )`.

### 169 -> 170
- `Material.type` is a static property; app code cannot modify it (affects `onBeforeCompile` hacks that change `type`).
- Some TSL modules moved from core to addons (issue #29505).
- Mipmaps always generated when `Texture.generateMipmaps = true`, regardless of filter.
- `GLTFExporter` non-PBR materials: `metallicFactor` 0, `roughnessFactor` 1.
- MMD modules deprecated; use `three-mmd-loader`.
- `WebGLRenderer.copyTextureToTexture3D()` deprecated -> `copyTextureToTexture()` (supports 3D and array textures).
- `WebXRManager` honours scene camera layers (PR 29742).
- `CinematicCamera` removed.
- `LDrawLoader`: do not inject conditional line material via `setConditionalLineMaterial()` before loading.

### 168 -> 169
- `TransformControls` derives from `Controls`; `scene.add( controls.getHelper() )` instead of `scene.add( controls )`.
- `EXRExporter.parse()`, `KTX2Exporter.parse()`, `LightProbeGenerator.fromCubeRenderTarget()` are async.
- `PackedPhongMaterial`, `SDFGeometryGenerator`, `TiltLoader` removed.
- `GPUStatsPanel` removed; use `stats-gl`.
- `GeometryCompressionUtils` functions take geometries, not meshes.

### 167 -> 168
- TSL chaining removed for tree-shaking: `outputPass.fxaa()` -> `fxaa( outputPass )` (PR 29187).
- TSL `viewportTopLeft` -> `viewportUV`; `viewportBottomLeft` removed (`viewportUV.flipY()`).
- TSL `uniforms()` -> `uniformArray()`.
- `DragControls.activate()/deactivate()` -> `connect()/disconnect()`; `getObjects()/setObjects()` removed (`controls.objects`); `getRaycaster()` removed (`controls.raycaster`).
- `PointerLockControls.getObject()` removed (`controls.object`).
- `LogLuvLoader` removed; consider `UltraHDRLoader`.

### 166 -> 167
- `WebGPURenderer` and TSL imports changed (PR 28650).
- `HDRJPGLoader` removed; use `UltraHDRLoader`.
- `utils/packLDrawModel.js` -> `.mjs`.

### 165 -> 166
- `BatchedMesh`: call `addInstance` after adding a geometry so it renders.

### 164 -> 165
- `WebGLRenderer.copyTextureToTexture( srcTexture, dstTexture, srcRegion = null, dstPosition = null, level = 0 )` (also `copyTextureToTexture3D`).
- `WebGLRenderer.copyFramebufferToTexture( texture, position = null, level = 0 )`.

### 163 -> 164
- `LWOLoader` new left-to-right-handed conversion (PR 28029).
- `USDZLoader` async parse renamed `parseAsync()`; new `parse()` takes callbacks.
- Shader chunk `lightmap_fragment` removed.
- `WebGLNodeBuilder` removed; node materials only with `WebGPURenderer`.

### 162 -> 163
- `WebGLRenderer` no longer supports WebGL 1.
- `stencil` context attribute `false` by default (also `WebGPURenderer.stencil`).
- `TextGeometry` `height` -> `depth`.
- `Scene.environmentIntensity` added; `envMapIntensity` on `MeshStandardMaterial`/`MeshPhysicalMaterial` attenuates only the material's own `envMap`.

### 161 -> 162
- `WebGLMultipleRenderTargets` removed; render target `count` property.
- Hand tracking not requested by default in XR.
- `InteractiveGroup`: `listenToXRControllerEvents()` and `listenToPointerEvents()`.
- Texture from `HTMLImageElement` uses `naturalWidth`/`naturalHeight`.

### 160 -> 161
- `build/three.js` and `build/three.min.js` removed; use ES Modules.
- `WebGLRenderer` precision qualifiers for all sampler types.
- `GroundProjectedSkybox` -> `GroundedSkybox`.
- Equirectangular env maps auto-converted to larger cube maps (more memory).

### 159 -> 160
- `HBAOPass` -> `GTAOPass`.
- `Triangle.getBarycoord()`/`getInterpolation()` return `null` for degenerate triangles.

### 158 -> 159
- `BatchedMesh.applyGeometry()` -> `addGeometry()`.
- `BufferAttribute.updateRange`/`InterleavedBuffer.updateRange` -> `updateRanges`; `addUpdateRange()`, `clearUpdateRanges()`.
- `SkinnedMesh` unsupported on WebGL 1.

### 157 -> 158
- `Quaternion`s must be normalised.
- `bumpScale` invariant to UV scale (PR 26899); retune.

### 156 -> 157
- `AmbientLightProbe`, `HemisphereLightProbe` removed -> `AmbientLight`, `HemisphereLight`.
- GLSL struct `GeometricContext` removed (affects `onBeforeCompile` patches).
- `AnimationUtils.arraySlice()` removed.

### 155 -> 156
- `FilmPass` ctor: `scanlinesIntensity`, `scanlinesCount` removed.
- `SAOPass` ctor: `useDepthTexture`, `useNormals` removed.
- `SSAOPass` requires a prior `RenderPass`.

### 154 -> 155
- `WebGLRenderer.useLegacyLights` default `false`, deprecated (physical light units; forum "Updates to lighting in three.js r155").
- Inline `WebGLRenderer.toneMapping` applies only when rendering to screen (like `outputColorSpace`); in post-processing use `OutputPass`.
- `OutputPass` ctor has no params; reads renderer settings.

### 153 -> 154
- Shader chunk `encodings_fragment` -> `colorspace_fragment`; `output_fragment` -> `opaque_fragment`.

### 152 -> 153
- WebGL 1 deprecated (removed r163).
- `EffectComposer` default render target type `THREE.HalfFloatType`.
- `AdaptiveToneMappingPass` removed; use `OutputPass`.
- `ColladaExporter`, `PRWMLoader`, `LightningStrike`, `LightningStorm` removed.
- `CubeTextureLoader` loads in sRGB by default.

### 151 -> 152
- `uv` attributes renamed: `uv, uv2, uv3, uv4` -> `uv, uv1, uv2, uv3`.
- `WebGLRenderer.outputEncoding` -> `outputColorSpace` (default `THREE.SRGBColorSpace`).
- `Texture.encoding` -> `Texture.colorSpace` (default `THREE.NoColorSpace`).
- `THREE.sRGBEncoding` -> `THREE.SRGBColorSpace`; `THREE.LinearEncoding` -> `THREE.LinearSRGBColorSpace`.
- `THREE.ColorManagement.enabled` default `true`.
- `SVGLoader` shapes need `renderOrder` defined.
- Guide: "Updates to Color Management in three.js r152" (discourse).

### 150 -> 151
- `Float16BufferAttribute` converts to/from half float in setters/getters.
- `SkinnedMesh.boneTransform()` -> `applyBoneTransform()`.
- `InstancedMesh.frustumCulled` default `true`; call `computeBoundingSphere()` after updating instance transforms.
- `MapControls` in its own module `three/addons/controls/MapControls.js`.
- Tween.js: `import TWEEN from 'three/addons/libs/tween.module.js'`.
- `Triangle.getUV()` -> `getInterpolation()`.
- `GroundProjectedEnv` -> `GroundProjectedSkybox`.
- `BufferGeometryUtils.mergeBufferAttributes()` -> `mergeAttributes()`; `mergeBufferGeometries()` -> `mergeGeometries()`.
- Editor uses `useLegacyLights = false`.
- `Points` supports `uv` for `map`/`alphaMap` per point.
- `ShaderMaterial.forceSinglePass` default `true`.
- `aoMap`/`lightMap` no longer use `uv2`; set `material.lightMap.channel` to `0` for `uv` and `1` for `uv2` (guide wording; after the r152 rename the second set is `uv1`); `uv2_*` shader chunks removed.

### 149 -> 150
- `build/three.js` and `build/three.min.js` deprecated (removed r161 per guide).
- `BasisTextureLoader` removed -> `KTX2Loader`.
- `ColorManagement.legacyMode = false` -> `ColorManagement.enabled = true`.
- `WebGLRenderer.physicallyCorrectLights = true` -> `useLegacyLights = false`.

## 7. Notable changes before r150 (still relevant)

- r149: `Euler.DefaultOrder` -> `Euler.DEFAULT_ORDER`; `Euler.RotationOrders` removed; `Object3D.DefaultUp`/`DefaultMatrixAutoUpdate`/`DefaultMatrixWorldAutoUpdate` -> `DEFAULT_UP`/`DEFAULT_MATRIX_AUTO_UPDATE`/`DEFAULT_MATRIX_WORLD_AUTO_UPDATE`; `ViewHelper.controls` removed (use `center`); `THREE.TwoPassDoubleSide` removed, transparent double-sided now two draw calls (`Material.forceSinglePass`).
- r148: `examples/js` removed; addons only as ES modules in `examples/jsm`; libs moved to `examples/jsm/libs`. Default radial segments of `CircleGeometry`, `RingGeometry`, `CylinderGeometry`, `ConeGeometry`, `TorusGeometry` increased. `GLTFLoader` preserves glTF node order.
- r147: `PointLight`/`SpotLight` `decay` default `2`. `KHR_materials_pbrSpecularGlossiness` removed from `GLTFLoader`/`GLTFExporter`. `PixelShader` removed -> `RenderPixelatedPass`.
- r146: `ShaderLib.cube` uniforms: `envMap` -> `tCube`, `flipEnvMap` -> `tFlip`. `BufferGeometryUtils.mergeBufferGeometries()` ignores `userData`.
- r145: `BoxBufferGeometry`-style aliases deprecated -> `BoxGeometry`. `FlyControls`/`FirstPersonControls` use Pointer Events.
- r144: `BufferGeometry.merge()` removed. `MeshLambertMaterial` per-fragment. `BufferAttribute` getters/setters respect `normalized`. `Scene.autoUpdate` -> `Object3D.matrixWorldAutoUpdate`.
- r141: deprecated `Geometry` class deleted; `DepthTexture` default type `UnsignedIntType`; legacy removed after ten releases; `GLTFExporter` `embedImages` removed.
- r140: `Material.fog` only on materials that support it; `SkinnedMesh` needs float vertex textures.
- r139: `CubeUVRefractionMapping`, `MeshStandardMaterial.refractionRatio` removed (use `MeshPhysicalMaterial` transmission).
- r138: `WebGLMultisampleRenderTarget` removed (use `samples`); `DataTexture3D`/`DataTexture2DArray` -> `Data3DTexture`/`DataArrayTexture`; `Euler.toVector3()` removed (`Vector3.setFromEuler()`); `CurveExtras` import is a namespace import.
- r137: import map required for bare `three`; `RGBFormat`/`RGBIntegerFormat` removed; sRGB textures use `RGBAFormat` + `UnsignedByteType`; changing `Material.transparent` after first use needs `needsUpdate = true`; esbuild needs file extensions.
- r136: `copyFramebufferToTexture` needs `FramebufferTexture`; `RGBE`/`RGBM`/`RGBD`/`LogLuv` encodings removed; `gammaFactor` and `GammaEncoding` removed; `PMREMGenerator` uses half float; changing `toneMapping` no longer needs `Material.needsUpdate`.
- r135: `dat.gui` -> `lil-gui`; texture dimensions/format/type fixed after first use; `GLTFExporter.parse( input, onCompleted, onError, options )`.
- r134: `FileLoader` uses `fetch`; `ImmediateRenderObject` removed.
- r133: `Raycaster.intersectObject(s)` `recursive` default `true`; `ExtrudeGeometry` defaults (`depth` 1, `bevelThickness` 0.2); `ParametricGeometry`, `TextGeometry`, `FontLoader`, `Font` moved to `examples/jsm`.
- r132: `BufferGeometryUtils` namespace import `import * as BufferGeometryUtils from ...`.
- r131: `morphTargets`/`morphNormals` material props removed; `SphereGeometry` defaults 32x16; HDR loaders default `HalfFloatType`; `envMap` auto-PMREM.
- r129: `renderTarget`/`forceClear` args of `render()` removed (use `setRenderTarget()` + `clear()`); material `skinning` removed.
- r128: Core classes are ES6 classes; `examples/jsm` imports bare `three`; `XLoader` removed.
- r127: `Scene.background` takes `.texture`, not render target; controls no longer `stopPropagation()`; `Plane.intersectLine()` returns `null` on miss.
- r126: types moved to `three-types/three-ts-types` (`@types/three`); `Face3` removed from core.
- r125: `Geometry` removed from core (to `examples/jsm/deprecated/Geometry.js`); generators produce `BufferGeometry`; `OrbitControls.listenToKeyEvents()`; `BufferGeometry.computeTangents()` in core; `TeapotBufferGeometry` -> `TeapotGeometry`; `RoundedBoxBufferGeometry` -> `RoundedBoxGeometry`.
- r123: `Matrix3/4.getInverse()` deprecated -> `invert()`; `Quaternion.inverse()` -> `invert()`.
- r120: `glslVersion` (`THREE.GLSL3`) needed for GLSL 3.0; `Scene.dispose()` removed; `stencilBuffer` default false for render targets.
- r118: `Uncharted2ToneMapping` removed (`CustomToneMapping`); `WebGL2` context default; `OrbitControls.screenSpacePanning` default `true`.
- r116: `WebGLRenderer.toneMapping` default `NoToneMapping`.
- r114: `Material.vertexColors` boolean; `GLTFLoader` returns `Group`.
- r113: `Math` -> `MathUtils`; `WebGLRenderTargetCube` -> `WebGLCubeRenderTarget`; `applyMatrix` -> `applyMatrix4`; default material colour white.
- r112: `PMREMGenerator` rewritten and in core; `gammaInput`/`gammaOutput` removed; `Mesh.drawMode` removed (`BufferGeometryUtils.toTrianglesDrawMode()`); `MeshStandardMaterial` defaults roughness 1, metalness 0; WebVR removed (use WebXR).
- r111: `Material.needsUpdate = true` increments a version counter (cannot be used in conditionals).
- r110: `addAttribute` -> `setAttribute`; `removeAttribute` -> `deleteAttribute`; `BufferAttribute.setUsage`; controls require `domElement`.
- (Older revisions r47-r109 are in the Migration Guide; consult the wiki if the user is on a pre-r110 codebase. Update in increments of 10 revisions.)

## 8. r186 -> r187 upcoming changes (in development)

Not released as of 0.186.1. Do not use these names unless the user is on a dev build; do mention them when asked about upgrading. Source: top section "186 -> 187" of the Migration Guide.

- TSL: operands and parameters of math functions are implicitly coerced to broader common types (#33695).
- PMREMs are based on cube render targets (#34585). `CubeUVReflectionMapping` removed. Quality improved, materials look slightly different.
- `WebGPURenderer` and `WebGLRenderer` use `WeakRef` and `FinalizationRegistry` internally (#34368).
- XR camera transformation and projection matrix derived from the first sub camera (e.g. left eye) (#34275).
- `WebGLRenderer.setViewport()` and `setScissor()` no longer scale by pixel ratio when a render target is bound (#34460).
- `pixelationPass()` TSL: `pixelSize` is now just a `Number` (#34543); nodes unsupported.
- Registering a light in `WebGPURenderer`: `CustomLight.registerNode( CustomLightNode )` replaces `renderer.library.addLight( CustomLightNode, CustomLight )` (#34622).
- TSL struct storage buffers always arrays, even with one element: replace `storage.get( 'member' )` with `storage.element( 0 ).get( 'member' )` when using `storage( buffer, StructType )` (#34807).
- `MeshPhysicalMaterial.iridescenceThicknessRange` deprecated -> `iridescenceThicknessMinimum` and `iridescenceThicknessMaximum` (#35039).

## 9. Release highlights r185 and r186

Fetched from https://github.com/mrdoob/three.js/releases (page truncated at 100 000 of 182 641 characters; only the top of the page, r186 and r185, was read; year not shown on the page).

### r186 (marked "Latest")
- Playground Projects and Templates (#34437).
- Retroreflectivity for `MeshPhysicalMaterial` (#33949), environment lighting added later (#33995).
- Spiral blur replaces separable blur in `PMREMGenerator` on both renderers (#32367).
- `SunLight` with cascaded shadow maps (#34221), later reduced to 2 cascades.
- `DirectRenderPipeline` in the WebGPU renderer (#34166).
- `compileComputeAsync()` (#32551).
- Async renderer `dispose()` (#34364).
- `Object3D.dispose()` (#34141) and `Object3D.intersectsFrustum()` (#34065).
- Watertight `Ray.intersectTriangle()` (#33661).
- `Source` -> `TextureSource` (#34202).
- Removals: remaining `PCFSoftShadowMap` code (#33987, with warnings); `BRDF_GGX_Multiscatter` (#33983).
- Tree-shaking: top-level side effects removed from Nodes (#34332).

### r185
- Deprecated code removed across the codebase (#33407).
- `Matrix3.scale()/rotate()/translate()` deprecated (#33757).
- `Matrix4.determinant3x3()` -> `determinantAffine()` (#33823).
- `MaterialLoader.registerMaterial()` and `Material.fromJSON()` (#33714).
- `DataTextureLoader.createDataTexture()` (#33705).
- `HTMLTexture` supports new WICG HTML-in-Canvas API signatures (#33788).
- Rendering to texture arrays in WebGPU (#33507).
- WebXR with WebGPU (#33583).
- Uncaptured GPU errors and WGSL diagnostics surfaced (#33418).
- `storageTexture3D` in TSL (#33443).
- `lighting.enabled` option (#33721).
- Wireframe rendering disables bump mapping (#33777).

## 10. See also

- Migration Guide: https://github.com/mrdoob/three.js/wiki/Migration-Guide
- Releases: https://github.com/mrdoob/three.js/releases
- LLM guidance: https://threejs.org/docs/llms.txt
