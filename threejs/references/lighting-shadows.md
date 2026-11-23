# Lighting, shadows, environment, and color management

When to read this: you are adding or tuning lights, shadows (including cascaded/tiled), image-based lighting (HDR/PMREM/RoomEnvironment), light probes, area lights, baked light maps, many-light setups on WebGPU, or debugging "too dark / too bright / shadow wrong". Covers WebGLRenderer and WebGPURenderer differences. Version: three r187.

## Contents
1. Color management essentials
2. Physical light units and intensity semantics
3. Light types: usage and cost
4. Shadows: enable, per-light setup, tuning
5. Shadow map types and filtering
6. Cascaded shadow maps (CSM / CSMShadowNode / SunLight)
7. Tiled shadows (TileShadowNode)
8. Cheap shadow alternatives
9. Environment lighting (IBL)
10. Light probes and spherical harmonics
11. RectAreaLight setup
12. Baked light maps and AO
13. Many lights on WebGPU (clustered / dynamic lighting)
14. Special lights (Projector, IES, Sun)
15. Helpers for debugging
16. Common mistakes and checklist
17. Doc gaps
18. See also

---

## 1. Color management essentials

- Working space is Linear-sRGB; `THREE.ColorManagement.enabled` is true by default. Hex/CSS colors given to `Color`, materials and lights are treated as sRGB and converted to linear on input.
- Color textures (`map`, `emissiveMap`, `matcap`, `specularColorMap`): `texture.colorSpace = THREE.SRGBColorSpace`. Data textures (normal, roughness, metalness, AO, displacement, bump): default `NoColorSpace`. HDR/EXR environment textures are linear (`LinearSRGBColorSpace`), loaders set it.
- GLTFLoader sets texture color spaces correctly. Vertex colors are linear.
- Output: `renderer.outputColorSpace` defaults to `SRGBColorSpace` (both renderers). Convert on output only once; with post-processing (`EffectComposer`) add `OutputPass`, otherwise output is dark (no sRGB conversion) or double-converted.
- `renderer.toneMapping` defaults to `NoToneMapping`; set `THREE.ACESFilmicToneMapping` / `AgXToneMapping` / `NeutralToneMapping` with `renderer.toneMappingExposure` for HDR content or physical light units. Tone mapping is applied on the final output (not into render targets).
- `ShaderMaterial`/`RawShaderMaterial` must include `#include <colorspace_fragment>` at the end of `main()` to convert output.
- Symptoms: whole scene dark = missing sRGB output; scene washed out = double conversion; one object washed out/dark = wrong texture `colorSpace`. Do not "fix" with more light.
- Use `color.setRGB(r, g, b)` for linear values; `color.convertSRGBToLinear()` manually if needed.

---

## 2. Physical light units and intensity semantics

Since r155 lights use physical units; `renderer.useLegacyLights` / `physicallyCorrectLights` no longer exist (grep of `src/` finds none). Old scenes lit with intensity 1 look too bright or dim: re-tune.

| Light | `intensity` unit | Notes |
|---|---|---|
| `PointLight` | candela (cd) | `power` getter/setter in lumens: `power = intensity * 4PI`. Bulb of 800 lm (60 W) -> `light.power = 800` (intensity ~63.7) |
| `SpotLight` | candela (cd) | `power = intensity * PI` (lm). Same cone-independent intensity |
| `DirectionalLight` | lux (illuminance), unitless in practice | Sunny day ~ 50000-100000 lx physically; in practice use 2-5 with tone mapping unless you go full physical |
| `HemisphereLight` | lux-like (irradiance) | Example uses 0.0001 lx (moonless night) to 50000 lx (direct sun) with matching exposure (`webgl_lights_physical.html`) |
| `AmbientLight` | unitless multiplier | `color = materialColor * light.color * light.intensity` (flat, no shading) |
| `RectAreaLight` | luminance-like (nits); `power` getter exists | Needs PBR material; `intensity` ~ 5-10 for visible results in the manual |
| `LightProbe` | unitless multiplier of SH irradiance | |
| `scene.environment` | scaled by `scene.environmentIntensity` (and per material `envMapIntensity`) | |

- `distance` (default 0): 0 = infinite range with inverse-square falloff. > 0 = hard-ish cutoff at that range (not physical; use only for culling/perf). `decay` default 2 (physical; do not change normally).
- Reasonable starting values when not using physical units: `PointLight(0xffffff, 50..150)` at 5-10 units away (the manual uses 150 at 10 units), `SpotLight` ~ 100-500, `DirectionalLight` 2-4, `HemisphereLight` 1-2, environment intensity 1.
- Physical workflow: pick units (meters), set `renderer.toneMapping`, tune `toneMappingExposure` (example: `Math.pow(exposure, 5)`), light by `power`.

---

## 3. Light types: usage and cost

```js
import * as THREE from 'three';
scene.add(new THREE.AmbientLight(0xffffff, 0.3));                         // flat fill; no shadows
scene.add(new THREE.HemisphereLight(0xb1e1ff, 0xb97a20, 1));               // sky/ground gradient; no shadows
const sun = new THREE.DirectionalLight(0xffffff, 3);
sun.position.set(5, 10, 7);                                               // direction = position -> target
sun.target.position.set(0, 0, 0);
scene.add(sun, sun.target);                                               // target must be in scene if moved from origin
const bulb = new THREE.PointLight(0xffaa55, 100, 0, 2);                   // color, intensity(cd), distance, decay
const spot = new THREE.SpotLight(0xffffff, 200, 0, Math.PI / 6, 0.3, 2);  // color, cd, distance, angle(rad, max PI/2), penumbra 0..1, decay
scene.add(spot, spot.target);
```
| Light | Shadows | Cost / notes |
|---|---|---|
| AmbientLight | no | cheapest; flattens look |
| HemisphereLight | no | cheap; good ambient substitute with Directional |
| DirectionalLight | yes (ortho frustum) | cheap; rotation is ignored (position -> `target`); `light.target` must be added to scene to move it |
| PointLight | yes (cube, 6 renders) | shadows are 6x scene draws; avoid casting from many |
| SpotLight | yes (perspective, 1 render) | `angle` drives shadow camera fov; `map` texture (cookie) requires `castShadow = true` |
| RectAreaLight | no | PBR materials only (`MeshStandardMaterial`/`MeshPhysicalMaterial`); needs LTC data init (section 11); no `target`, use rotation or `lookAt` |
| LightProbe | no | diffuse-only SH; cheap |
| SunLight (addon) | yes (2 cascades) | no target; direction from position (section 14) |
| ProjectorLight, IESSpotLight | yes (SpotLight subclasses) | WebGPURenderer only |

Every light adds per-fragment cost, and adding/removing lights (or toggling `castShadow`) changes the lights hash and recompiles shaders on WebGL. Prefer fewer lights + environment map + baked light maps. On WebGPURenderer use `DynamicLighting` to avoid recompiles (section 13).
Light `target`: `DirectionalLight`/`SpotLight` aim at `light.target.position`. Moving the target requires adding `light.target` to the scene (so its `matrixWorld` updates), then call `helper.update()`.

---

## 4. Shadows: enable, per-light setup, tuning

Mechanism: each shadow-casting light renders every `castShadow` object from its point of view into a depth map; the main pass samples it. Cost = (#shadow lights x scene draw), x6 for point lights.

Enable (3 switches, all required):
```js
renderer.shadowMap.enabled = true;                 // WebGLRenderer and WebGPURenderer
light.castShadow = true;                           // DirectionalLight / SpotLight / PointLight (+ SunLight, ProjectorLight, IESSpotLight)
mesh.castShadow = true;  ground.receiveShadow = true;
```
Material must be lit (`MeshBasicMaterial` ignores shadows; Lambert/Phong/Standard/Physical/Toon OK). Changing `renderer.shadowMap.enabled` or `renderer.shadowMap.type` after first render requires `material.needsUpdate = true` on affected materials (WebGL).

### LightShadow properties (all verified in `api/LightShadow.md`)
| Property | Default | Meaning |
|---|---|---|
| `mapSize` (Vector2) | 512x512 | depth texture size, powers of two; bigger = sharper + more memory/time |
| `camera` | per type | the light's shadow camera |
| `bias` | 0 | added to depth compare; tiny (about -0.0001 .. -0.005) cures acne; too large -> peter-panning |
| `normalBias` | 0 | offsets lookup position along normal (world units; 0.01-0.1); fixes acne on shallow angles w/o much peter-panning |
| `radius` | 1 | blur radius for edge softness (PCF/VSM); no effect with `BasicShadowMap`; too high -> banding |
| `blurSamples` | 8 | VSM blur samples |
| `intensity` | 1 | shadow darkness 0..1 (0 = no shadow) |
| `autoUpdate` | true | per-light; set false for static scenes then set `needsUpdate = true` for one refresh |
| `needsUpdate` | false | forces update on next render when `autoUpdate = false` |
| `biasNode` | null | WebGPU only; overrides `bias` |

SpotLightShadow extra: `focus` (0..1, shadow camera fov as fraction of the spot's cone; default 1), `aspect`.
Renderer-level (WebGL): `renderer.shadowMap.autoUpdate`, `renderer.shadowMap.needsUpdate`. WebGPURenderer: `renderer.shadowMap.enabled/type`; `renderer.shadowMap.transmitted = true` needed when using `material.castShadowNode` (see `webgpu_shadowmap_opacity.html`).

### DirectionalLight: size the frustum (the #1 shadow bug)
Shadow camera is an `OrthographicCamera(-5, 5, 5, -5, 0.5, 500)` by default. Only what is inside this box is shadowed.
```js
const s = sun.shadow;
s.camera.left = -20; s.camera.right = 20; s.camera.top = 20; s.camera.bottom = -20;
s.camera.near = 1;  s.camera.far = 60;      // tight near/far: more depth precision
s.camera.updateProjectionMatrix();          // REQUIRED after editing the camera
s.mapSize.set(2048, 2048);
s.bias = -0.0005; s.normalBias = 0.03;
scene.add(new THREE.CameraHelper(s.camera)); // visualize; call helper.update() after changes
```
Texel size = frustum width / mapSize. Cover only what the player sees; 40 units over 2048 px ~ 2 cm/texel. For large worlds follow the camera (`sun.position`/`target` snapped to texel multiples to avoid shimmer) or use CSM (section 6).
### SpotLight
Shadow camera is a `PerspectiveCamera(50, 1, 0.5, 500)` whose fov is driven by the spot's `angle` (and `focus`). Set `shadow.camera.near/far` tight to the scene; no left/right.
### PointLight
`PerspectiveCamera(90, 1, 0.5, 500)` x 6 faces; only `near`/`far` matter. 6x draw cost; set `distance` and shadow `far` small.

### Tune workflow
1. Add `CameraHelper(light.shadow.camera)`; make the box hug the visible area.
2. Raise `mapSize` only as needed (1024-4096).
3. Fix acne: `normalBias` first (0.02-0.05), then tiny negative `bias`.
4. Fix peter-panning (shadow detached from contact): reduce `bias`/`normalBias`; for thin geometry set `material.shadowSide = THREE.BackSide`/`FrontSide` (WebGL default: back faces render for shadow when material is `FrontSide`).
5. Soften: `radius` 2-4 with `PCFShadowMap`, or `VSMShadowMap` with `blurSamples`.
6. Static scenes: `shadow.autoUpdate = false; shadow.needsUpdate = true;` once.

---

## 5. Shadow map types and filtering

```js
renderer.shadowMap.type = THREE.PCFShadowMap;   // default recommended
```
| Constant | Meaning |
|---|---|
| `BasicShadowMap` (0) | unfiltered, fastest, aliased; ignores `radius` |
| `PCFShadowMap` (1) | percentage-closer filtering, `radius` respected; default quality |
| `PCFSoftShadowMap` (2) | DEPRECATED since r186 and REMOVED: setting it logs a warning and uses `PCFShadowMap` (both WebGLShadowMap and WebGPU Renderer). Use `PCFShadowMap` + `shadow.radius`. |
| `VSMShadowMap` (3) | variance shadow maps: soft, blur via `radius`/`blurSamples`; light bleeding artifacts; all receivers also cast shadows; point lights fall back to standard (VSM not applied to PointLightShadow in WebGPU) |

WebGPU: `TileShadowNode` does not support VSM. PCSS (contact-hardening) is a WebGL example (`webgl_shadowmap_pcss.html`) that patches the shadow shader chunk; no built-in API.

---

## 6. Cascaded shadow maps

For large outdoor scenes: split the view frustum into N slices, one tight directional shadow per slice.

### WebGL: `CSM` (`three/addons/csm/CSM.js`)
```js
import { CSM } from 'three/addons/csm/CSM.js';
import { CSMHelper } from 'three/addons/csm/CSMHelper.js';
const csm = new CSM({
  maxFar: 300, cascades: 4, mode: 'practical',        // 'uniform' | 'logarithmic' | 'practical' | 'custom'
  parent: scene, shadowMapSize: 2048,
  lightDirection: new THREE.Vector3(1, -1, 1).normalize(),
  camera,                                             // the view camera
});
csm.fade = true;                                      // blend between cascades
scene.traverse((o) => { if (o.isMesh) csm.setupMaterial(o.material); });  // EVERY material that receives CSM shadows
// each frame, before render:
camera.updateMatrixWorld(); csm.update();
// on camera/settings change (fov, aspect, mode, maxFar...): csm.updateFrustums();
// teardown: csm.remove(); csm.dispose();
```
CSM creates one `DirectionalLight` per cascade (`csm.lights`); also properties `lightIntensity`, `lightNear/lightFar/lightMargin`, `shadowBias`, `breaks`. Materials need `castShadow/receiveShadow` meshes as usual. `CSMHelper(csm)` + `helper.update()` per frame visualizes cascades (`displayFrustum`, `displayPlanes`, `displayShadowBounds`; call `updateVisibility()` after toggling). Example: `webgl_shadowmap_csm.html`.

### WebGPU: `CSMShadowNode` (`three/addons/csm/CSMShadowNode.js`)
```js
import { CSMShadowNode } from 'three/addons/csm/CSMShadowNode.js';
const light = new THREE.DirectionalLight(0xffffff, 3);
light.castShadow = true;
light.shadow.mapSize.set(2048, 2048);
light.shadow.camera.near = 1; light.shadow.camera.far = 2000;
light.shadow.camera.top = 1000; light.shadow.camera.bottom = -1000; light.shadow.camera.left = -1000; light.shadow.camera.right = 1000;
const csm = new CSMShadowNode(light, { cascades: 4, maxFar: 500, mode: 'practical' });
light.shadow.shadowNode = csm;       // replaces the standard shadow with the cascaded one
scene.add(light);
```
No `setupMaterial` / `update()` needed. `csm.updateFrustums()` after changing camera/settings, `csm.fade`, `csm.lightMargin`. Example: `webgpu_shadowmap_csm.html`.

### `SunLight` (addon, 2 cascades, auto-fit)
```js
import { SunLight } from 'three/addons/lights/SunLight.js';
const sun = new SunLight(0xfff2e3, 3);     // no target: direction from position toward origin
sun.position.set(1, 1, 1); sun.castShadow = true;
sun.shadow.camera.far = 200;               // maximum shadow distance
sun.shadow.mapSize.setScalar(2048);        // per cascade (default 1024)
sun.shadow.normalBias = 0.05;
scene.add(sun);
// WebGPU only, once: import { SunLightNode } from 'three/addons/lights/SunLightNode.js'; SunLight.registerNode(SunLightNode);  // r187; was renderer.library.addLight(SunLightNode, SunLight)
```
`SunLightShadow` fits cascades to the view frustum automatically (`camera.left/right/top/bottom` ignored; `getCamera(i)`, `getFrustum(i)`, `getMatrix(i)`). Examples: `webgl_lights_sunlight.html`, `webgpu_lights_sunlight.html`. Choose SunLight for a zero-config sun; CSM/CSMShadowNode when you need 3-5 cascades or split-mode control.

---

## 7. Tiled shadows (WebGPU)

`TileShadowNode` splits one big shadow map into `tilesX x tilesY` tiles, each with its own light and camera, for sharper shadows over a large area (a "shadow map array").
```js
import { TileShadowNode } from 'three/addons/tsl/shadows/TileShadowNode.js';
import { TileShadowNodeHelper } from 'three/addons/tsl/shadows/TileShadowNodeHelper.js';
dirLight.castShadow = true;
dirLight.shadow.camera.left = -180; dirLight.shadow.camera.right = 180;   // area to cover
dirLight.shadow.camera.top = 180;   dirLight.shadow.camera.bottom = -160;
dirLight.shadow.camera.near = 1;    dirLight.shadow.camera.far = 200;
dirLight.shadow.mapSize.set(4096, 4096);
const tsm = new TileShadowNode(dirLight, { tilesX: 2, tilesY: 2 });       // options also: resolution, debug
dirLight.shadow.shadowNode = tsm;
scene.add(dirLight, new TileShadowNodeHelper(tsm));                        // helper optional (debug)
```
Not supported with `VSMShadowMap`. Static-frustum alternative to CSM (cascades follow the view; tiles divide a fixed area). Example: `webgpu_shadowmap_array.html`. (`webgpu_lights_tiled.html` does not exist in r187; see Doc gaps.)

---

## 8. Cheap shadow alternatives

- **Fake blob shadow:** textured plane just above the ground (`position.y = 0.001`), `MeshBasicMaterial({ map, transparent: true, depthWrite: false })`; fade opacity with height. No lights needed, great for mobile.
- **`ShadowMesh`** (`three/addons/objects/ShadowMesh.js`): flattens a mesh onto one plane: `const s = new ShadowMesh(cube); scene.add(s); s.update(plane, lightPosition4D)` (Vector4, w=1 for point light). Hard shadow on one flat plane only. Example `webgl_shadowmesh.html`.
- **Contact shadows:** render depth from below into a render target and blur (`webgl_shadow_contact.html`, `webgpu_shadow_contact.html`).
- **Baked light maps / AO:** section 12. **`ProgressiveLightMap`** accumulates soft baked shadows at runtime (`three/addons/misc/ProgressiveLightMap.js`, WebGL; `ProgressiveLightMapGPU.js` for WebGPU): `const p = new ProgressiveLightMap(renderer, 1024); p.addObjectsToLightMap([...objects]); p.update(camera)` each frame while jittering lights; it rewrites objects' lightmaps and UV channel 1 (`uv1`), so objects must not need that channel. Examples `webgl_shadowmap_progressive.html`, `webgpu_shadowmap_progressive.html`.
- **`LightMapper`** (r187, WebGPU only, `three/addons/lighting/LightMapper.js`): bakes indirect diffuse into a light map from any TSL irradiance function, e.g. `new LightMapper(renderer, size, (p, n) => lightProbeGridIrradiance(probes, p, n))`; `addObjects(meshes)`, then `update()` per frame (progressive) or bake N samples at once (max 256). Needs `uv1` light-map UVs; call `reset()` after moving geometry or lights.
- One shadow-casting directional light + hemisphere/environment fill is the usual budget.

---

## 9. Environment lighting (IBL)

`scene.environment` lights every PBR material (Standard/Physical) with diffuse irradiance + specular reflection; `scene.background` is separate (see `recipes.md` section 3).

### From an HDR equirect (best quality)
```js
import { HDRLoader } from 'three/addons/loaders/HDRLoader.js';       // also RGBELoader.js, EXRLoader.js, UltraHDRLoader.js
const hdr = await new HDRLoader().loadAsync('studio_2k.hdr');
hdr.mapping = THREE.EquirectangularReflectionMapping;
scene.environment = hdr;           // WebGL converts equirect to PMREM internally (cached); explicit PMREM below gives control
scene.background = hdr;            // optional
scene.environmentIntensity = 1.0;  // global scale (default 1)
scene.environmentRotation.y = Math.PI / 2;   // Euler; rotates lighting + reflections (backgroundRotation for the sky)
```
Per-material overrides: `material.envMap`, `envMapIntensity` (MeshStandard/Physical), `envMapRotation`. With `scene.environment` set, `material.envMap` null uses the scene's.

### Explicit PMREM (prefiltered mip radiance map)
```js
const pmrem = new THREE.PMREMGenerator(renderer);
const envRT = pmrem.fromEquirectangular(hdr);      // fromCubemap(cube), fromScene(scene, sigma, near, far)
scene.environment = envRT.texture;
hdr.dispose(); pmrem.dispose();                    // free source + generator; keep envRT until done
```
- `fromEquirectangular` ideal input 1024x512 (min 64x32); `fromCubemap` ideal 256 per face (min 16).
- WebGPURenderer: `await renderer.init()` first (PMREM before init throws); async variants `fromSceneAsync`, `fromEquirectangularAsync` exist. Import `PMREMGenerator` from `three/webgpu`.
- `pmrem.compileEquirectangularShader()` during texture fetch speeds first generation.

### Procedural, no asset download
```js
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
const env = new RoomEnvironment();
scene.environment = pmrem.fromScene(env, 0.04).texture;    // soft studio lighting; ideal for GLTF viewers
env.dispose();
```
- `RoomEnvironment`: production-grade neutral studio (from model-viewer). `DebugEnvironment`: dev-only simple room. `ColorEnvironment(color)`: uniform ambient IBL of one color.
- `ImportanceSampledEnvironment` (TSL, WebGPU): preprocesses an HDR environment into luminance CDF textures to do BRDF/MIS importance sampling (used by path-tracing/SSR-miss techniques; not needed for ordinary IBL).

### Ground projection and live reflections
- `GroundedSkybox(envMap, height, radius)` (`three/addons/objects/GroundedSkybox.js`): ground-projected skybox mesh; `skybox.position.y = height`; use alongside the same texture as `scene.environment`.
- `CubeCamera(near, far, renderTarget)` + `WebGLCubeRenderTarget(size, { generateMipmaps: true, minFilter: LinearMipmapLinearFilter })`: dynamic reflections: hide the reflecting mesh, `cubeCamera.update(renderer, scene)`, show it; set `material.envMap = rt.texture`. WebGPU: `CubeRenderTarget`. Re-rendering a cube map = 6 scene renders; throttle.
- `WebGLCubeRenderTarget.fromEquirectangularTexture(renderer, tex)` converts an equirect to a cube target (WebGPU: `CubeRenderTarget` has the same method).

Gotchas: HDR must be float/half-float (loaders handle); `scene.environment` + several lights double-lights, reduce `environmentIntensity` or lights; PMREM textures are render-target textures, do not flip/modify; environments do not cast shadows (pair with one directional light for shadows); `Scene.environment` intensity uses `environmentIntensity` and per-material `envMapIntensity` multiplicatively.

---

## 10. Light probes and spherical harmonics

A `LightProbe` stores diffuse irradiance as 9 SH coefficients (`SphericalHarmonics3`, `.sh.coefficients`: 9 `Vector3`). Position is NOT used in lighting; one global ambient-like diffuse term.
```js
import { LightProbeGenerator } from 'three/addons/lights/LightProbeGenerator.js';
import { LightProbeHelper } from 'three/addons/helpers/LightProbeHelper.js';   // WebGPU: LightProbeHelperGPU.js
const probe = new THREE.LightProbe();
scene.add(probe);
probe.copy(LightProbeGenerator.fromCubeTexture(cubeTexture));    // sync, from CubeTexture
// from a render target (async, RGBA required): probe.copy(await LightProbeGenerator.fromCubeRenderTarget(renderer, cubeRT));
probe.intensity = 1;
```
Use for cheap ambient from a cubemap, or XR light estimation. Examples `webgl_lightprobe.html`, `webgl_lightprobe_cubecamera.html`.

### Position-dependent GI: `LightProbeGrid`
3D grid of L2 SH probes baked from the scene; adding it to the scene lights lit materials with local diffuse GI.
```js
// WebGPU
import { LightProbeGrid } from 'three/addons/lighting/LightProbeGrid.js';
import { LightProbeGridHelper } from 'three/addons/helpers/LightProbeGridHelper.js';
const grid = new LightProbeGrid(5.6, 4.7, 5.6, 6, 6, 6);          // width,height,depth (world), probes per axis (defaults from size)
grid.position.set(0, 2.35, 0);                                    // volume is centered on position
scene.add(grid);
await grid.bake(renderer, scene, { cubemapSize: 32, near: 0.05, far: 20, bounces: 1 });   // also sampleCount (512), start/count/pass for incremental
grid.priority = 1;                                                // r187: where grids overlap, highest priority wins (ties: newest grid); `falloff` was removed
// WebGL: import { LightProbeGridWebGL } from 'three/addons/lighting/LightProbeGridWebGL.js' (same bake API); helper LightProbeGridHelperWebGL
```
Bake at load/offline; GPU-resident (no CPU readback); shadow-casting `SunLight`s are temporarily replaced by directional lights during bake. Examples `webgpu_lightprobes.html`, `webgl_lightprobes.html`, `*_lightprobes_complex`, `*_lightprobes_sponza`. Also `examples/jsm/lighting/vxgi` (voxel GI experiment; not documented in api/).

---

## 11. RectAreaLight setup

```js
// WebGLRenderer: must init LTC uniforms ONCE, before first render
import { RectAreaLightUniformsLib } from 'three/addons/lights/RectAreaLightUniformsLib.js';
RectAreaLightUniformsLib.init();
// WebGPURenderer: node equivalent
import { RectAreaLightTexturesLib } from 'three/addons/lights/RectAreaLightTexturesLib.js';
THREE.RectAreaLightNode.setLTC(RectAreaLightTexturesLib.init());   // with `three/webgpu` import

import { RectAreaLightHelper } from 'three/addons/helpers/RectAreaLightHelper.js';
const rect = new THREE.RectAreaLight(0xffffff, 5, 12, 4);          // color, intensity, width, height
rect.position.set(0, 10, 0);
rect.lookAt(0, 0, 0);                                              // no target; rotation/lookAt orients the emitting face
scene.add(rect);
rect.add(new RectAreaLightHelper(rect));                           // helper is a CHILD OF THE LIGHT (not scene)
```
Rules: only `MeshStandardMaterial`/`MeshPhysicalMaterial` respond; no shadows; no `target`; forgetting `init()` still renders but looks wrong; light emits from one face (front toward `lookAt` direction).

---

## 12. Baked light maps and AO

```js
material.lightMap = bakedTexture;        // adds baked light to indirect; works in Basic/Lambert/Phong/Standard/Physical
material.lightMapIntensity = 1;
material.aoMap = aoTexture;              // ambient occlusion, affects indirect only
material.aoMapIntensity = 1;
lightTexture.channel = 1;                // which UV set to use: 0 = uv, 1 = uv1, 2 = uv2, 3 = uv3 (Texture.channel, default 0)
aoTexture.channel = 1;
lightTexture.colorSpace = THREE.LinearSRGBColorSpace;  // EXR/HDR baked data is linear; sRGB for baked PNG/JPG color
```
- `uv2` as an attribute name was replaced by the per-texture `channel` mechanism: the geometry attribute must be named `uv1` (or `uv2`/`uv3`) and the texture `channel` set to match (GLTF `TEXCOORD_1` becomes `uv1`).
- Lightmap UVs must be non-overlapping unwraps; a lightmap and a color map may use different channels.
- Baked lights are static: remove the corresponding real lights for those objects to avoid double lighting.
- Tools: DCC bake (Blender), or `ProgressiveLightMap` at runtime (section 8). Example: `webgpu_materials_lightmap.html`.

---

## 13. Many lights on WebGPU

By default `WebGPURenderer` evaluates every light in every fragment, and the light list is baked into the shader (adding/removing lights recompiles). Opt-in lighting systems replace `renderer.lighting`:

```js
import { ClusteredLighting } from 'three/addons/lighting/ClusteredLighting.js';
renderer.lighting = new ClusteredLighting(/* maxLights=1024, tileSize=32, zSlices=24, maxLightsPerCluster=64 */);
// Forward+ clustered shading for 100s-1000s of PointLights: the frustum is split into a 3D cluster grid and each fragment only evaluates lights in its cluster.
// Set before first render. Debug: lighting.getNode(scene).getClusterLightCount(...) / lighting.zSlices / lighting.maxLightsPerCluster.
// Only non-shadow-casting PointLights are clustered (ClusteredLightsNode skips castShadow lights); other light types go through the normal path. Example: webgpu_lights_clustered.html, webgpu_lights_pointlights.html

import { DynamicLighting } from 'three/addons/lighting/DynamicLighting.js';
renderer.lighting = new DynamicLighting({ maxDirectionalLights: 8, maxPointLights: 16, maxSpotLights: 16, maxHemisphereLights: 4 });
// Lights batched into uniform arrays: adding/removing supported lights does NOT recompile materials. Fixed caps per type.
```
Pick Clustered for very many point lights, Dynamic for scenes whose light count changes at runtime (spawn/despawn). Also `webgpu_lights_selective.html` (per-object light sets) and `webgpu_lights_custom.html` (custom lighting model).
WebGL has no equivalent: budget a handful of lights; use emissive meshes + light probes/baked maps for the rest, or `InstancedMesh` with emissive materials.

---

## 14. Special lights

- **`SpotLight.map`**: texture "cookie" modulating light color (requires `castShadow = true`). 
- **`ProjectorLight`** (WebGPU only, `THREE.ProjectorLight`, extends SpotLight): projects `map` (image/video texture) like a projector; `aspect` (null = texture aspect), uses `shadow.focus`; example `webgpu_lights_projector.html`.
- **`IESSpotLight`** (WebGPU only, `THREE.IESSpotLight`): `iesMap` from `IESLoader` (`three/addons/loaders/IESLoader.js`); intensity in cd (example uses 500); example `webgpu_lights_ies_spotlight.html`.
- **`SunLight`**: section 6.
- Light + custom nodes: `webgpu_lights_custom.html`.

---

## 15. Helpers for debugging

| Helper | Create | Notes |
|---|---|---|
| `DirectionalLightHelper(light, size, color)` | `scene.add(h)` | plane + line to target; `h.update()` after moving light/target |
| `SpotLightHelper(light, color)` | `scene.add(h)` | cone; `h.update()` after changes |
| `PointLightHelper(light, sphereSize, color)` | `scene.add(h)` | sphere |
| `HemisphereLightHelper(light, size, color)` | `scene.add(h)` | `h.update()` |
| `RectAreaLightHelper(light, color)` | `light.add(h)` (child of the light) | addon |
| `CameraHelper(light.shadow.camera)` | `scene.add(h)` | shows the shadow frustum; `h.update()` after camera edit; must be in scene |
| `CSMHelper(csm)` | `scene.add(h)` | `update()` per frame; works with `CSM` and `CSMShadowNode` |
| `TileShadowNodeHelper(tsm)` | `scene.add(h)` | debug planes/cameras |
| `LightProbeHelper(probe, size)` | `scene.add(h)` | WebGL; `LightProbeHelperGPU` for WebGPU |
| `LightProbeGridHelper(grid)` / `LightProbeGridHelperWebGL(grid)` | `scene.add(h)` | sphere per probe |

Helpers are debug only: `dispose()` and remove in production. Shadow debugging: `renderer.shadowMap` viewer example `webgl_shadowmap_viewer.html`; temporarily set `mapSize` low to see texel size; check `light.shadow.map` after one render.

---

## 16. Common mistakes and checklist

| Symptom | Cause / fix |
|---|---|
| No shadow at all | Missing one of: `renderer.shadowMap.enabled`, `light.castShadow`, `mesh.castShadow`, `receiveShadow`; `MeshBasicMaterial`; light type unsupported; object outside shadow frustum. |
| Shadow cut off / only partial | Shadow camera too small (default 10x10 ortho). Enlarge left/right/top/bottom, call `camera.updateProjectionMatrix()`, verify with `CameraHelper`. |
| Blocky/low-res shadows | Frustum too big for `mapSize`; shrink frustum, raise `mapSize`, or use CSM. |
| Shadow acne (stripes/moire on lit surfaces) | Raise `normalBias` (0.02-0.1), small negative `bias`; reduce frustum depth range (`near/far`). |
| Peter-panning (shadow detached) | `bias`/`normalBias` too large; reduce; thicken thin geometry. |
| Shadows vanish at distance | Beyond `shadow.camera.far` or frustum; use CSM. |
| Shadows flicker/shimmer when camera moves | Following light frustum with sub-texel movement: snap to texel size; use CSM (handles it). |
| Slow frame time | Too many shadow lights (each = scene redraw; point = 6x). Keep <= 1-2 shadow lights; shrink casters (`castShadow` only where needed); `autoUpdate = false` for static; lower `mapSize`. |
| Light seems to do nothing | `DirectionalLight` aimed at `target` not added to scene; Ambient/Hemisphere have no direction; material is `MeshBasic`; `intensity` far too small for physical units (point light needs ~50+ cd at a few meters). |
| Everything blown out after upgrading | Legacy light intensities; use physical values; check environment AND lights both enabled; adjust `toneMappingExposure`. |
| PBR model looks dead/flat gray | No `scene.environment`; add `RoomEnvironment` or HDR. |
| RectAreaLight shows strange | `RectAreaLightUniformsLib.init()` (WebGL) / `RectAreaLightNode.setLTC(...)` (WebGPU) missing; non-PBR material. |
| Rendering lag when toggling lights | Light count changes -> shader recompile (WebGL). Pre-create the lights and set `intensity = 0` instead of adding/removing or toggling `visible` (which changes the light list). On WebGPU use `DynamicLighting`. |
| VSM artifacts | Light bleeding; raise `radius`/`blurSamples`, lower bias; or use `PCFShadowMap`. |
| `PCFSoftShadowMap` warning | Removed in r186; use `PCFShadowMap` + `radius`. |
| Env map HDR looks banded/dark | Source must be HDR half/float; set `toneMapping`; check `mapping = EquirectangularReflectionMapping`. |
| Double sided plane receives no/wrong shadow | Set `material.shadowSide`; add `normalBias`. |

Checklist for a standard outdoor scene: `HemisphereLight` (or `scene.environment` from `RoomEnvironment`/HDR) + one `DirectionalLight` with `castShadow`, tight frustum with `CameraHelper`, `mapSize 2048`, `normalBias ~0.03`, `bias -0.0005`, ACES/AgX tone mapping, ground `receiveShadow`, meshes `castShadow`.

---

## 17. Doc gaps

- `webgpu_lights_tiled.html` does not exist in r187 examples; tiled shadows are shown in `webgpu_shadowmap_array.html`; tiled/clustered lights in `webgpu_lights_clustered.html` and `webgpu_lights_clustered_city.html` (new in r187).
- Local docs do not state units for `DirectionalLight` (lux) or `RectAreaLight` (nits) intensity; they are inferred from `webgl_lights_physical.html` and upstream conventions.
- `api/SpotLightShadow.md` description says "directional lights" (typo upstream). `api/SpotLightHelper.md` constructor type lists `HemisphereLight` (typo; takes SpotLight).
- No manual page on PMREM or IBL beyond API pages; `LightProbeGrid` baking options documented partially (`start`, `count`, `pass`).
- `vxgi` folder under `examples/jsm/lighting` has no API page.

---

## 18. See also

API pages (`references/api/`): `Light.md`, `AmbientLight.md`, `HemisphereLight.md`, `DirectionalLight.md`, `PointLight.md`, `SpotLight.md`, `RectAreaLight.md`, `LightProbe.md`, `LightProbeGenerator.md`, `LightProbeGrid.md`, `LightProbeGridWebGL.md`, `IESSpotLight.md`, `ProjectorLight.md`, `SunLight.md`, `LightShadow.md`, `DirectionalLightShadow.md`, `SpotLightShadow.md`, `PointLightShadow.md`, `SunLightShadow.md`, `DirectionalLightHelper.md`, `SpotLightHelper.md`, `PointLightHelper.md`, `HemisphereLightHelper.md`, `RectAreaLightHelper.md`, `CameraHelper.md`, `LightProbeHelper.md`, `LightProbeGridHelperWebGL.md`, `RectAreaLightUniformsLib.md`, `RectAreaLightTexturesLib.md`, `RectAreaLightNode.md`, `CSM.md`, `CSMHelper.md`, `CSMShadowNode.md`, `TileShadowNode.md`, `TileShadowNodeHelper.md`, `PMREMGenerator.md`, `RoomEnvironment.md`, `DebugEnvironment.md`, `ColorEnvironment.md`, `ImportanceSampledEnvironment.md`, `GroundedSkybox.md`, `CubeCamera.md`, `WebGLCubeRenderTarget.md`, `ProgressiveLightMap.md`, `ShadowMesh.md`, `ClusteredLighting.md`, `DynamicLighting.md`, `SphericalHarmonics3.md`, `Scene.md`, `WebGLRenderer.md`, `Renderer.md`, `Material.md`, `MeshStandardMaterial.md`.

Examples: `webgl_lights_physical`, `webgl_lights_rectarealight`, `webgl_lights_spotlight(s)`, `webgl_lights_hemisphere`, `webgl_lights_sunlight`, `webgl_shadowmap`, `webgl_shadowmap_csm`, `webgl_shadowmap_vsm`, `webgl_shadowmap_pcss`, `webgl_shadowmap_pointlight`, `webgl_shadowmap_performance`, `webgl_shadowmap_progressive`, `webgl_shadowmesh`, `webgl_lightprobe*`, `webgpu_lights_clustered`, `webgpu_lights_dynamic`, `webgpu_lights_projector`, `webgpu_lights_ies_spotlight`, `webgpu_lights_rectarealight`, `webgpu_lights_sunlight`, `webgpu_shadowmap`, `webgpu_shadowmap_csm`, `webgpu_shadowmap_array`, `webgpu_shadowmap_vsm`, `webgpu_shadowmap_opacity`, `webgpu_lightprobes`.

Official: https://threejs.org/manual/#lights, https://threejs.org/manual/#shadows, https://threejs.org/manual/#color-management, https://threejs.org/manual/#backgrounds, https://threejs.org/docs/#Light, https://threejs.org/docs/#LightShadow, https://threejs.org/docs/#DirectionalLight, https://threejs.org/docs/#PointLight, https://threejs.org/docs/#SpotLight, https://threejs.org/docs/#RectAreaLight, https://threejs.org/docs/#LightProbe, https://threejs.org/docs/#PMREMGenerator, https://threejs.org/docs/#RoomEnvironment, https://threejs.org/docs/#CSM, https://threejs.org/docs/#CSMShadowNode, https://threejs.org/docs/#TileShadowNode, https://threejs.org/docs/#SunLight.
