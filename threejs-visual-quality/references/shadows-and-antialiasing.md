# Shadows and anti-aliasing (three.js r187)

## When to read this
Shadows are blocky, noisy, acned, detached ("peter-panning"), too expensive, or objects float; edges crawl/shimmer; you must choose between MSAA / FXAA / SMAA / TAA / SSAA for WebGL or WebGPU, or antialiasing breaks once you add post-processing.

## Contents
1. How shadow maps work and what they cost
2. Shadow map types (WebGL vs WebGPU)
3. Fitting the frustum, resolution, bias
4. Softness: radius, blurSamples, intensity
5. Light types: directional, spot, point
6. Cascades: CSM, SunLight, TileShadowNode
7. Contact shadows, ShadowMaterial, baked and static shadows
8. Acne / peter-panning / light-leak troubleshooting
9. Anti-aliasing overview table
10. MSAA, FXAA, SMAA, TAA/TRAA, SSAA recipes (WebGL and WebGPU)
11. Specular, texture, geometry and line aliasing
12. Recommended presets
13. See also

## 1. How it works
Per shadow-casting light, every `castShadow` object is rendered again from the light's point of view into a depth map; receivers compare their light-space depth to it. N shadow lights x M casters = N x M extra draws; a **PointLight shadow renders 6 cube faces** (manual: "scene has to be drawn 6 times just for that light"). Cost is geometry-bound (draw calls, triangles), not resolution-bound, until maps exceed 2048.
Rules: one shadowed directional light (the sun/key) + unshadowed fills; point-light shadows only for the hero lamp; ambient occlusion/baking for the rest.
```js
renderer.shadowMap.enabled = true;           // off by default (both renderers)
light.castShadow = true; mesh.castShadow = true; floor.receiveShadow = true;
```

## 2. Shadow map types
Constants: `BasicShadowMap=0, PCFShadowMap=1, PCFSoftShadowMap=2 (removed), VSMShadowMap=3`. Default `PCFShadowMap` on both renderers.

| Type | Look | Cost | Notes |
|---|---|---|---|
| `BasicShadowMap` | Hard, jagged, pixelated | Cheapest | `shadow.radius` has no effect. Needed for custom shaders that read raw depth (PCSS example `webgl_shadowmap_pcss` sets it) |
| `PCFShadowMap` (default) | Filtered hard shadow; in r187 hardware 4-tap PCF x 5 Vogel-disk taps scaled by `shadow.radius` | Low-medium | Best default. Raise `radius` 1 -> 3-5 to soften (banding above ~6 at 1024 maps) |
| `PCFSoftShadowMap` | -- | -- | **Removed.** Setting it logs a warning and uses PCF (WebGLRenderer, WebGPURenderer). Do not use |
| `VSMShadowMap` | Softest, blurred, penumbra-like (Gaussian blur via `radius` + `blurSamples`) | Medium-high (extra blur passes, RG half-float maps) | Light bleeding, can look "floating". All receivers also render into the map (`receiveShadow` objects cast). **Not supported for PointLights** (warns; use PCF/Basic) |

```js
renderer.shadowMap.type = THREE.PCFShadowMap;        // or VSMShadowMap / BasicShadowMap
// WebGPURenderer: same property; types handled by ShadowNode (Basic, PCF, VSM). Point lights use their own PointShadowNode (Basic or PCF filter).
```
WebGL-only knobs on `WebGLRenderer.shadowMap`: `enabled`, `autoUpdate`, `needsUpdate`, `type`. `ShadowMaterial`/`MeshDepthMaterial` custom depth: `object.customDepthMaterial` for alpha-tested/animated vertex displacement.

## 3. Fit, resolution, bias
`DirectionalLight.shadow.camera` is an OrthographicCamera: fit it TIGHTLY to what the camera sees. Texel size = frustum width / mapSize. 2048 map over 100 m = 5 cm texels (blocky); over 10 m = 5 mm.
```js
const s = dir.shadow;
s.mapSize.set(2048, 2048);                 // powers of two; default 512. 1024 mobile, 2048 desktop, 4096 hero only
Object.assign(s.camera, { left: -8, right: 8, top: 8, bottom: -8, near: 0.5, far: 30 }); // then:
s.camera.updateProjectionMatrix();
scene.add(new THREE.CameraHelper(s.camera)); // always visualize while tuning
dir.target.position.set(0, 0, 0); scene.add(dir.target);
```
- `near/far` as tight as possible (depth precision). SpotLight: shadow camera fov follows `angle`; set `shadow.camera.near/far`, `shadow.focus` (0-1).
- Shadow shimmer (edges crawl while the camera moves) is its own cause, separate from geometry aliasing: the shadow camera moves by sub-texel amounts each frame. Fix it by stabilizing, not by more MSAA:
  - `CSM` and `SunLight` already do this in r187: `CSM.js` snaps each cascade's center to the texel grid (`Math.floor(center / texelWidth) * texelWidth`) and keeps cascade size constant; `SunLightShadow` fits a rotation-stable bounding sphere per cascade and snaps it to the texel grid. Using either one is the stabilization; say so.
  - For one hand-rolled `DirectionalLight` that follows the player, snap in light space each frame:
```js
const texel = (s.camera.right - s.camera.left) / s.mapSize.x;   // world units per shadow texel
const lightView = new THREE.Matrix4().lookAt(dir.position, dir.target.position, THREE.Object3D.DEFAULT_UP);
const p = player.position.clone().applyMatrix4(lightView.clone().invert());  // player in light space
p.x = Math.floor(p.x / texel) * texel; p.y = Math.floor(p.y / texel) * texel; // snap to the texel grid
const snapped = p.applyMatrix4(lightView);                                    // back to world space
const offset = dir.position.clone().sub(dir.target.position);
dir.target.position.copy(snapped); dir.position.copy(snapped).add(offset);
```
  Keep the frustum size fixed (never refit `left/right` per frame), or the texel size changes and the snap stops working.
- Bias (`shadow.bias`, default 0): tiny negative values, -0.0001 to -0.002 (examples: directional -0.0005, spot -0.002 for VSM; SunLight uses `normalBias`). Bias shifts depth: too small = acne, too large = peter-panning (shadow detaches from the contact point).
- `shadow.normalBias` (default 0): offsets the lookup along the surface normal. Preferred fix for acne on grazing surfaces: 0.01-0.05 for ~1 m objects, 0.02-0.1 in large scenes; scales with world units. `SunLight` demo uses `normalBias = 1` (km scale) / 0.05.
- WebGPU: `shadow.biasNode` (a node, overrides `bias`) for slope-/distance-scaled bias.
- Typical start: `bias = -0.0002; normalBias = 0.02`.
- `material.shadowSide` (null = same side logic): set `THREE.BackSide`/`DoubleSide` for thin/open meshes to fix leaks; don't flip globally.
- Casting only from big objects: set `castShadow=false` on tiny props; ground `castShadow=false`.

## 4. Softness and intensity
- `shadow.radius` (default 1): PCF/VSM blur radius in texels. Real shadows are soft far from the contact and sharp at it (PCSS); three has no built-in PCSS (example patches the shader chunk with `BasicShadowMap`). Approximate with PCF radius 2-4 + contact shadow/AO.
- `shadow.blurSamples` (default 8): VSM only. 8-16.
- `shadow.intensity` (0..1, default 1): fades the shadow darkness; use 0.6-0.85 so shadows are lit by sky/bounce (outdoor shadows are never black; they take the sky color). Complement: `HemisphereLight`/env (`scene.environmentIntensity`) fills shadows.
- Large soft shadows from a big light: VSM at 512-1024 with `radius 4-8` is cheaper than PCF at 4096.
- `shadow.autoUpdate`, `shadow.needsUpdate` per light; `renderer.shadowMap.autoUpdate`/`needsUpdate` global.

## 5. Light types
- Directional/Sun: ortho frustum, best quality/cost. 
- Spot: perspective frustum, one map; cheap; use for lamps and as a controlled key. Keep `angle` small to concentrate texels.
- Point: cube map (6 renders), `shadow.camera.near/far` = light radius; use `mapSize` 512-1024; no VSM. Prefer baked or a spot cone.
- Hemisphere, Ambient, RectArea, IES (no/limited shadows; `IESSpotLight` castShadow works in WebGPU).
- WebGPU only: `LightShadow.biasNode`; `ProjectorLight`, `IESSpotLight` shadows through ShadowNode.

## 6. Cascades
Single maps cannot cover near detail and far distance. Cascaded shadow maps split the view frustum.

WebGLRenderer `CSM` (`three/addons/csm/CSM.js`): materials are patched, one DirectionalLight per cascade.
```js
import { CSM } from 'three/addons/csm/CSM.js';
import { CSMHelper } from 'three/addons/csm/CSMHelper.js';
const csm = new CSM({
  camera, parent: scene,
  cascades: 4,                 // default 3
  maxFar: 300,                 // default 100000: shorten to the distance you need shadows
  mode: 'practical',           // 'uniform' | 'logarithmic' | 'practical' | 'custom' (customSplitsCallback)
  shadowMapSize: 2048,         // default 2048 per cascade
  shadowBias: 0.000001,
  lightDirection: new THREE.Vector3(-1, -1, -1).normalize(),
  lightIntensity: 3,           // default 3
  lightNear: 1, lightFar: 2000, lightMargin: 200, // margin = how far casters outside the view still cast in
  fade: true,                  // blend between cascades (default false)
});
csm.setupMaterial(mat);        // every lit material that should receive CSM shadows
// loop: csm.update();  before renderer.render
// on camera/settings change: csm.updateFrustums();   on teardown: csm.remove(); csm.dispose();
```
`practical` = blend of uniform and logarithmic (default, good). Each cascade is another full shadow render: 3 cascades x scene. Example `webgl_shadowmap_csm`.

WebGPURenderer `CSMShadowNode` (`three/addons/csm/CSMShadowNode.js`): no material patching.
```js
import { CSMShadowNode } from 'three/addons/csm/CSMShadowNode.js';
const light = new THREE.DirectionalLight(0xffffff, 3); light.castShadow = true;
light.shadow.mapSize.set(2048, 2048);
const csm = new CSMShadowNode(light, { cascades: 4, maxFar: 300, mode: 'practical' }); // also fade, lightMargin, camera
light.shadow.shadowNode = csm;  scene.add(light);
```
Example `webgpu_shadowmap_csm`.

`SunLight` + `SunLightShadow` (addons `lights/SunLight.js`): lightweight 2-cascade sun with automatic fitting to the view frustum up to `shadow.camera.far`; direction from `position` (no target); `shadow.mapSize` default 1024 per cascade. WebGPU: `SunLight.registerNode(SunLightNode)` (r187; was `renderer.library.addLight(SunLightNode, SunLight)`) (`SunShadowNode`, `sunShadow`). Examples `webgl_lights_sunlight`, `webgpu_lights_sunlight`. Best zero-config outdoor option.

`TileShadowNode` (WebGPU, `three/addons/tsl/shadows/TileShadowNode.js`): splits one directional shadow into `tilesX x tilesY` tiles (default 2 x 2) for huge worlds; no VSM. Example `webgpu_shadowmap_array`.

## 7. Contact shadows, catchers, baked
Shadow catcher (floor shows only shadow, transparent otherwise):
```js
const catcher = new THREE.Mesh(new THREE.PlaneGeometry(40, 40), new THREE.ShadowMaterial({ opacity: 0.25 })); // color default black
catcher.rotation.x = -Math.PI / 2; catcher.receiveShadow = true; scene.add(catcher);
```
Contact shadow (blurred, view-from-below, works without lights; example `webgl_shadow_contact`, WebGPU `webgpu_shadow_contact`):
1. Orthographic camera under the ground plane looking up (`rotation.x = PI/2`, near 0, far = max object height).
2. Render the scene with an override depth material: black with alpha `(1 - depth) * darkness` into a 512 `WebGLRenderTarget`.
3. Blur it separably (`HorizontalBlurShader`/`VerticalBlurShader`, or `gaussianBlur` node) twice (blur, blur*0.4).
4. Show it on a plane just above the floor (`depthWrite:false`).
Re-render only when objects move. Cost ~3 small passes; soft grounding for products where a shadow-casting light would be harsh. Use blur 3-5, darkness 1-3, opacity 0.5-1.

Baked:
- `material.lightMap` (+ `lightMapIntensity`, uses `uv1`) and `aoMap` for static scenes. Bake in Blender (Cycles bake) = highest quality, zero runtime cost.
- `ProgressiveLightMap` (WebGL `three/addons/misc/ProgressiveLightMap.js`: `new ProgressiveLightMap(renderer, 1024)`, `addObjectsToLightMap`, `update(camera)` each frame; WebGPU: `ProgressiveLightMapGPU.js`) accumulates jittered-light shadows into a lightmap at runtime. Examples `webgl_shadowmap_progressive`, `webgpu_shadowmap_progressive`.
- Static caching: when nothing in the scene moves, set `renderer.shadowMap.autoUpdate = false; renderer.shadowMap.needsUpdate = true;` (WebGL) or per light `light.shadow.autoUpdate = false; light.shadow.needsUpdate = true;`. Re-set `needsUpdate` when a caster moves. With moving casters keep `autoUpdate` true and reduce casters/maps instead.
- Light probes / `LightProbeGrid` give baked diffuse GI shadows-ish occlusion (see PBR file).
- Screen-space: GTAO/SSAO for contact darkening (post file).

## 8. Troubleshooting
| Artifact | Cause | Fix |
|---|---|---|
| Stripes/moire on lit faces (acne) | bias too small / grazing angles / low-res map | `normalBias` 0.02-0.05, `bias -0.0002`, tighten frustum, raise `mapSize` |
| Shadow detached from object (peter-panning) | bias/normalBias too big | reduce; thicken thin geometry; `shadowSide = BackSide` for closed meshes |
| Blocky edges | large frustum, small map | tighten, CSM, `radius` 2-4 |
| Shimmer when moving | shadow camera follows camera continuously | snap to texel grid; fix to world |
| Shadow cut off in a rectangle | ortho frustum too small | enlarge `left/right/top/bottom/far` (use CameraHelper) |
| Light bleeding (VSM) | variance overlap | PCF; raise bias; separate casters |
| Whole scene cast black | `intensity` 1, no fill | `shadow.intensity` 0.7, add env/hemisphere |
| Transparent/alpha-cutout casts solid shadow | depth material ignores alpha | `alphaTest` (honored) or `customDepthMaterial` |
| Receives but no shadow | `receiveShadow` false, material `MeshBasicMaterial` (unlit) | use lit material |
| FPS drop | too many shadow lights/casters, point lights, 4096 maps | section 1 rules, static cache, fewer cascades |

## 9. Anti-aliasing comparison
| Method | Quality | Cost | Motion artifacts | Handles shader/specular aliasing | WebGL | WebGPU |
|---|---|---|---|---|---|---|
| MSAA 4x | Geometry edges only, crisp | Low-med (memory x4) | none | No | `antialias:true` | `antialias:true` / `samples` |
| FXAA | Edges + some texture, blurry | Very low | Slight crawl | Partly (blurs) | `FXAAPass` | `fxaa` node |
| SMAA | Sharper than FXAA, edges only | Low | Slight | No | `SMAAPass` | `smaa` node |
| TAA / TRAA | Best overall, handles shaders, shadows, specular | Low-med (history + jitter) | Ghosting, blur on fast motion | Yes | `TAARenderPass` (accumulating, for static scenes; not velocity-based) | `traa` node (velocity MRT), `taau` upscale |
| SSAA | Ground truth, expensive | Very high (2^n renders) | none | Yes | `SSAARenderPass` / `renderer.setPixelRatio(2)` | `ssaaPass(scene,camera)` |
| Pixel ratio supersample | brute force | x4 fill at 2x | none | Yes | `setPixelRatio` | same |
| FSR1 / sharpen | upscale quality | low | | | | `fsr1`, `sharpen` nodes |

## 10. Recipes
### MSAA
```js
const renderer = new THREE.WebGLRenderer({ antialias: true });   // 4 samples on the default framebuffer
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));           // 1x on retina = blurry/aliased; >2 wastes fill
```
- MSAA applies only to the default framebuffer. With `EffectComposer` the scene renders into an offscreen target which is NOT multisampled unless you give it `samples`:
```js
const rt = new THREE.WebGLRenderTarget(w * pr, h * pr, { type: THREE.HalfFloatType, samples: 4 });
const composer = new EffectComposer(renderer, rt);   // composer.setPixelRatio(pr); composer.setSize(w, h)
```
(Pattern from `webgl_postprocessing_unreal_bloom_selective`.) Or use `WebGLRenderer({ antialias:true, outputBufferType: HalfFloatType })` + `renderer.setEffects([...])` where the scene target is MSAA 4x automatically.
- WebGPU: `new WebGPURenderer({ antialias: true })` (`samples` 4 by default when `antialias`; set `samples` to override; `renderer.samples`). Inside `RenderPipeline`, `pass(scene, camera)` options `{ samples }` control the pass target: `scenePass.options.samples = 4` (0 with TRAA, as in `webgpu_postprocessing_ao`). `Reflector` has `multisample` option (default 4).

### FXAA (needs display-referred sRGB input)
```js
// WebGL: after OutputPass
composer.addPass(new RenderPass(scene, camera)); composer.addPass(new OutputPass()); composer.addPass(new FXAAPass());
// WebGPU
rp.outputColorTransform = false;
rp.outputNode = fxaa(renderOutput(pass(scene, camera)));  // import { fxaa } from 'three/addons/tsl/display/FXAANode.js'
```
### SMAA
```js
composer.addPass(new SMAAPass());                         // three/addons/postprocessing/SMAAPass.js, no params; place near the end
rp.outputNode = smaa(color);                              // three/addons/tsl/display/SMAANode.js (used before output transform in webgpu_postprocessing_ssr)
```
### TAA
WebGL `TAARenderPass(scene, camera, clearColor, clearAlpha)`: jitter + accumulation, replaces RenderPass; `sampleLevel` (0 default; 2^n samples, max 5), `accumulate` (set false while moving, true when still), `unbiased`. Great for static viewers (product/arch), blurs on motion. Include `OutputPass`.
```js
const taa = new TAARenderPass(scene, camera); taa.sampleLevel = 2; taa.unbiased = false;
composer.addPass(taa); composer.addPass(new OutputPass());
controls.addEventListener('start', () => taa.accumulate = false);
controls.addEventListener('end',   () => taa.accumulate = true);
```
Also usable in `renderer.setEffects([taa, bloomPass])` (example `webgl_watch`).

WebGPU TRAA (temporal reprojection with velocity):
```js
import { pass, mrt, output, velocity } from 'three/tsl';
import { traa } from 'three/addons/tsl/display/TRAANode.js';
const sp = pass(scene, camera);
sp.setMRT(mrt({ output, velocity }));
rp.outputNode = traa(sp.getTextureNode('output'), sp.getTextureNode('depth'), sp.getTextureNode('velocity'), camera);
// traa.useSubpixelCorrection, depthThreshold, edgeDepthDiff, maxVelocityLength
```
The renderer is jittered via camera view offsets (`setViewOffset`/`clearViewOffset` on the node). Use it with SSGI/GTAO since those need temporal denoise. Moving instanced/skinned meshes need correct velocity.

### SSAA
```js
const ssaa = new SSAARenderPass(scene, camera); ssaa.sampleLevel = 3; // 2^3 = 8 samples, default 4 (16), unbiased true
composer.addPass(ssaa); composer.addPass(new OutputPass());
// WebGPU: const p = ssaaPass(scene, camera); p.sampleLevel = 3; rp.outputNode = p;   (three/addons/tsl/display/SSAAPassNode.js)
```
Use for offline screenshots/"high quality" mode, not realtime.

## 11. Other aliasing sources
- **Specular aliasing** (sparkling highlights on bumpy/low-roughness surfaces): floor roughness at >= 0.05-0.1 for normal-mapped surfaces; keep mipmaps on normal maps (never disable `generateMipmaps`); bake a roughness increase where the normal map is high-frequency; avoid super-thin geometry with `roughness 0`; TAA fixes most of the rest.
- **Texture aliasing / blur**: `texture.anisotropy = maxAnisotropy` (8-16); `minFilter = LinearMipmapLinearFilter` (default); avoid `NearestFilter` unless pixel-art; use power-of-two atlas with padding.
- **Alpha-tested foliage/fences**: `material.alphaToCoverage = true` with MSAA (`alphaTest 0.5`); otherwise shimmer.
- **Thin lines**: `LineBasicMaterial.linewidth` is always 1px in WebGL. Use `Line2` + `LineMaterial` + `LineGeometry` (`three/addons/lines/Line2.js`, `LineMaterial.js`, `LineGeometry.js`):
```js
const mat = new LineMaterial({ color: 0xffffff, linewidth: 2, worldUnits: false, alphaToCoverage: true, dashed: false });
mat.resolution.set(innerWidth, innerHeight);   // update on resize
```
WebGPU: `Line2NodeMaterial`.
- **Geometric**: avoid sub-pixel triangles and coplanar faces (z-fight): increase `near`, use `logarithmicDepthBuffer` or `reversedDepthBuffer` (requires `EXT_clip_control`), `polygonOffset` for decals.
- **Shadow edge shimmer**: section 3.
- **Post-effect buffers**: render AO/SSR/bloom at `resolutionScale 0.5` but keep the scene pass at full resolution.

## 12. Presets
| Target | Shadows | AA |
|---|---|---|
| Mobile / low | one Directional, `PCF`, 1024, radius 2; no point shadows; baked rest | `antialias:true`, pixelRatio <= 2 (<=1.5 low-end) |
| Product viewer | Directional 2048 tight + `ShadowMaterial` catcher + GTAO | MSAA composer target or TAA accumulate on idle |
| Outdoor game | `SunLight` or CSM 3-4 cascades x 2048, `maxFar` 200-400, `fade` | FXAA/SMAA cheap, TRAA (WebGPU) best |
| Cinematic exterior | CSM 4 x 2048-4096 + contact AO | TAA/TRAA + sharpen, SSAA for stills |

## 13. See also
- API: `../threejs/references/api/LightShadow.md`, `DirectionalLightShadow.md`, `SpotLightShadow.md`, `PointLightShadow.md`, `ShadowNode.md`, `ShadowBaseNode.md`, `PointShadowNode.md`, `CSM.md`, `CSMShadowNode.md`, `SunLight.md`, `SunLightShadow.md`, `SunShadowNode.md`, `TileShadowNode.md`, `ShadowMaterial.md`, `ProgressiveLightMap.md`, `MeshDepthMaterial.md`, `WebGLRenderer.md`, `Renderer.md`, `WebGPURenderer.md`, `EffectComposer.md`, `FXAAPass.md`, `SMAAPass.md`, `TAARenderPass.md`, `SSAARenderPass.md`, `TRAANode.md`, `FXAANode.md`, `SMAANode.md`, `Line2.md`, `LineMaterial.md`, `Line2NodeMaterial.md`, `RenderTarget.md`
- Examples: `webgl_shadowmap`, `webgl_shadowmap_vsm`, `webgl_shadowmap_csm`, `webgl_shadowmap_pcss`, `webgl_shadowmap_pointlight`, `webgl_shadowmap_performance`, `webgl_shadowmap_progressive`, `webgl_shadow_contact`, `webgpu_shadowmap_csm`, `webgpu_shadowmap_vsm`, `webgpu_shadowmap_array`, `webgpu_shadow_contact`, `webgl_postprocessing_fxaa`, `webgl_postprocessing_smaa`, `webgl_postprocessing_taa`, `webgl_postprocessing_ssaa`, `webgpu_postprocessing_traa`, `webgpu_postprocessing_fxaa`, `webgpu_postprocessing_smaa`, `webgpu_postprocessing_ssaa`
- Manual: https://threejs.org/manual/en/shadows
