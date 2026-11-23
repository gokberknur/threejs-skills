# PBR materials, environment lighting, studio lighting (three.js r187)

## When to read this
Materials look plastic/flat/CG, glass looks fake, metals look black, product shots lack depth, or you need a lighting recipe (HDRI + key light, 3-point area lights, sun + sky) and complete starter scenes. Pair with `color-and-tone-mapping.md` (mandatory) and `shadows-and-antialiasing.md`.

## Contents
1. What makes PBR convincing
2. Value ranges (albedo, roughness, metalness)
3. Texture set and quality
4. MeshPhysicalMaterial features (ranges, cost)
5. Subsurface (MeshSSSNodeMaterial)
6. Environment lighting (HDRI, PMREM, RoomEnvironment, GroundedSkybox)
7. Background vs environment, blur
8. Light units, sun + sky coherence
9. Studio lighting: RectAreaLight 3-point recipe, IES, light probes
10. glTF best practices
11. Starter: product viewer (WebGL + WebGPU)
12. Starter: architectural exterior (WebGL + WebGPU)
13. The 10 things that make a three.js scene look amateur
14. See also

## 1. What makes PBR convincing
PBR convincing = energy-correct materials x **a rich environment** x tone mapping. 80% of "CG look" is missing reflections: every material (even rough) reflects the environment; a metal with no env map is black because metals have no diffuse.
1. Always provide `scene.environment` (HDRI or `RoomEnvironment`). Physical docs: "For best results, always specify an environment map" with `MeshPhysicalMaterial`.
2. Vary roughness spatially (roughnessMap, noise, edge wear). Uniform roughness reads as plastic.
3. Bevel edges (even 0.5-2 mm): highlights on edges sell scale. Sharp CAD edges look fake.
4. Contact grounding: AO + contact shadow (see shadows file).
5. Correct color pipeline, tone mapping, albedo within physical range.
6. Fresnel: grazing angles reflect more (built in); keep `specularIntensity`/`ior` at defaults unless needed.

## 2. Value ranges
| Parameter | Guidance | Why |
|---|---|---|
| Albedo (`color`/`map`, non-metal) | sRGB 30-240 (linear 0.02-0.85). Charcoal ~ 50 sRGB, fresh snow ~ 240 max, avoid pure 0 and pure 255 | Nothing absorbs or reflects 100%; pure white clips and kills detail, pure black has no shading |
| Metal albedo (F0 color) | Bright: gold ~ #FFE29B..#FFD27F, copper #F9C9AE (approx), iron #C4C7C7, aluminum #F5F6F6; sRGB 180-255 | Metal color IS its reflectance |
| `metalness` | 0 or 1. Fractions only on transition pixels in a map (rust edge, paint chips) | Real materials are binary; 0.5 = nothing physical |
| `roughness` (smooth glass/polish) | 0.02-0.15 | roughness 0 is a mirror; tiny values avoid aliasing |
| (paint / plastic / ceramic) | 0.2-0.45 | |
| (brushed metal / wood / leather) | 0.4-0.7 | |
| (concrete / fabric / stone / matte) | 0.7-1.0 | |
| `clearcoat` | 1 with `clearcoatRoughness` 0.03-0.2 (car paint) | |
| `emissiveIntensity` | 1 for screens, 2-10 for lights to bloom | HDR values > 1 trigger bloom |
| `envMapIntensity` / `scene.environmentIntensity` | 0.3-1.5 (1 default) | Raise only when env is dim; cap highlights |

Default `MeshStandardMaterial`: `roughness = 1`, `metalness = 0`, `envMapIntensity = 1`, `normalScale = (1,1)`, `aoMapIntensity = 1`.

## 3. Texture set and quality
- Maps: albedo (sRGB), normal (NoColorSpace; OpenGL +Y convention for glTF; flip `normalScale.y = -1` for DirectX maps), roughness+metalness packed (glTF: G=roughness, B=metalness; three reads `roughnessMap` from G, `metalnessMap` from B, `aoMap` from R, so one ORM image can be assigned to all three), AO (needs `uv1`/`aoMap` channel; baked occlusion only affects indirect/env light, not direct lights), emissive (sRGB).
- `texture.anisotropy = renderer.capabilities.getMaxAnisotropy()` (WebGPU: `renderer.getMaxAnisotropy()`): 8-16 on floors and any surface seen at grazing angles; kills smeared textures. Cheap on modern GPUs.
- Keep mipmaps (default `LinearMipmapLinearFilter`, `generateMipmaps = true`); never use `LinearFilter` min filter on detailed textures (shimmer).
- Normal map mips + roughness = **specular antialiasing**: filtered normals flatten and the highlight should widen. Author roughness with the normal in mind (Toksvig); avoid roughness < 0.05 on high-frequency normals (sparkle).
- KTX2 (Basis): UASTC for normal maps/data (quality, ~4x smaller than PNG VRAM 8 bit/px), ETC1S for albedo (smallest). 
```js
import { KTX2Loader } from 'three/addons/loaders/KTX2Loader.js';
const ktx2 = new KTX2Loader().setTranscoderPath('/basis/').detectSupport(renderer); // WebGPURenderer: await detectSupportAsync(renderer)
gltfLoader.setKTX2Loader(ktx2);
```
- Max 2048 for most props, 4096 hero assets. Power-of-two not required in WebGL2/WebGPU but mipmaps are cheaper.
- Lightmaps: `material.lightMap` + `lightMapIntensity` (uses `uv1`), baked AO in `aoMap`. `ProgressiveLightMap` (WebGL: `three/addons/misc/ProgressiveLightMap.js`, WebGPU: `ProgressiveLightMapGPU.js`) accumulates baked shadows at runtime.

## 4. MeshPhysicalMaterial (extends MeshStandardMaterial)
Cost: higher per-pixel cost; each feature adds shader work only when enabled (most default off). Transmission adds an extra scene render.

| Feature | Properties (default) | Recommended | Notes / cost |
|---|---|---|---|
| Clearcoat | `clearcoat` 0, `clearcoatRoughness` 0, `clearcoatMap`, `clearcoatRoughnessMap`, `clearcoatNormalMap`, `clearcoatNormalScale` (1,1) | 1.0 / 0.03-0.15; clearcoatNormal for orange peel (scale ~ (2,-2) in example) | Second specular lobe, +1 env sample. Car paint, lacquer, wet look |
| Sheen | `sheen` 0, `sheenColor` (0,0,0), `sheenRoughness` 1 (+maps) | `sheen` 1, `sheenColor` slightly lighter than base, `sheenRoughness` 0.3-0.8 | Velvet/cloth rim glow; cheap |
| Transmission | `transmission` 0, `thickness` 0, `attenuationColor` white, `attenuationDistance` Infinity, `ior` 1.5, `specularIntensity` 1, `specularColor`, `dispersion` 0 | glass: `transmission 1, roughness 0-0.1, ior 1.45-1.52, thickness 0.01-1 (mesh units)` ; tinted: `attenuationColor` + `attenuationDistance` ~ object size | Opaque scene is rendered to a render target first (every frame) and sampled with roughness-driven mips. Expensive on large fill. Mitigate: `renderer.transmissionResolutionScale = 0.5` (WebGLRenderer, default 1), few transmissive objects, keep them small on screen, no overlapping transmissive objects (they do not see each other well) |
| Volume | `thickness > 0` makes a volume boundary; `thickness 0` = thin-walled | thin bottle wall ~ 0.002-0.02 in mesh units; solid gem 0.5-2 | `attenuationDistance` is in world units: smaller = stronger tint |
| Dispersion | `dispersion` 0, typical range [0,1] | diamond/crystal 0.3-1; glass 0-0.1 | Only for transmissive; 3 refraction samples |
| IOR | `ior` 1.5 (range 1.0-2.333); `reflectivity` 0.5 == ior 1.5 | water 1.33, glass 1.5, sapphire 1.77, diamond 2.4 (clamped 2.333) | `reflectivity` and `ior` are linked; set one |
| Iridescence | `iridescence` 0, `iridescenceIOR` 1.3, `iridescenceThicknessMinimum` 100 / `iridescenceThicknessMaximum` 400 nm (r187; `iridescenceThicknessRange` deprecated), maps | soap bubble: 1, IOR 1.3, [100,800]; oil slick/beetle: 1, [200,500]; subtle car flip: 0.3 | Thin-film interference; costs extra Fresnel math |
| Diffuse roughness (r187) | `diffuseRoughness` 0, `diffuseRoughnessMap` (R) | matte powdery surfaces (clay, plaster, dust): try 0.5-1; leave 0 for most materials | 0 is Lambert; >0 switches to the EON (energy-preserving Oren-Nayar) diffuse BRDF, the flatter look of rough matte surfaces |
| Anisotropy | `anisotropy` 0..1, `anisotropyRotation` (radians), `anisotropyMap` | brushed metal/hair/CD: 0.5-1; rotation aligns stretch direction | `anisotropyMap`: R,G = direction in tangent space, B = strength; needs UVs |
| Specular | `specularIntensity` 1, `specularColor` white (+maps) | leave default; <1 for dull dielectrics | Non-metal F0 control; glTF KHR_materials_specular |
| Retroreflectivity | `retroreflectivity` 0..1 | road signs, tape: 1 | New in recent releases |
| Env | `envMap`, `envMapIntensity`, `envMapRotation` | see sect. 6 | |

```js
// glass
new THREE.MeshPhysicalMaterial({ transmission: 1, roughness: 0.05, ior: 1.5, thickness: 0.05,
  attenuationColor: 0x99ffcc, attenuationDistance: 0.5, dispersion: 0.05, specularIntensity: 1 });
// car paint
new THREE.MeshPhysicalMaterial({ color: 0x9a0f12, metalness: 0.9, roughness: 0.45, clearcoat: 1, clearcoatRoughness: 0.05 });
// velvet
new THREE.MeshPhysicalMaterial({ color: 0x400808, roughness: 0.9, sheen: 1, sheenColor: new THREE.Color(0xff6a6a), sheenRoughness: 0.4 });
// soap bubble
new THREE.MeshPhysicalMaterial({ transmission: 1, roughness: 0, thickness: 0.001, iridescence: 1, iridescenceIOR: 1.3, iridescenceThicknessMinimum: 100, iridescenceThicknessMaximum: 800 });
```
Transparent alternative for cheap glass: `transparent:true, opacity:0.2` + high `specularIntensity`/env; opacity attenuates reflections too, which is why transmission looks better. Sort with `renderOrder`, `depthWrite:false`, `side: DoubleSide` (`forceSinglePass: true` for double-sided transmissive meshes if artifacts).

WebGPU: `MeshPhysicalNodeMaterial` (same properties plus `*Node` overrides such as `colorNode`, `roughnessNode`, `normalNode`, `emissiveNode`, `backdropNode`). Note: `THREE.MeshPhysicalMaterial` is auto-mapped to its node equivalent by `WebGPURenderer`.

## 5. Subsurface scattering (skin, wax, marble, leaves)
WebGPU only: `MeshSSSNodeMaterial` (experimental, extends `MeshPhysicalNodeMaterial`). Properties: `thicknessColorNode, thicknessDistortionNode, thicknessAmbientNode, thicknessAttenuationNode, thicknessPowerNode, thicknessScaleNode, useSSS (true)`. Back-lit translucency, not true diffusion.
```js
import { texture, uniform, vec3 } from 'three/tsl';
const m = new THREE.MeshSSSNodeMaterial();      // values from webgpu_materials_sss
m.thicknessColorNode = texture(thicknessMap).mul(vec3(0.5, 0.3, 0.0)); // tint of transmitted light (warm for skin)
m.thicknessDistortionNode = uniform(0.1);
m.thicknessAmbientNode = uniform(0.4);
m.thicknessAttenuationNode = uniform(0.8);
m.thicknessPowerNode = uniform(2.0);
m.thicknessScaleNode = uniform(16.0);
```
Screen-space SSS post effect: `sss(depthNode, camera, mainLight)` from `three/addons/tsl/display/SSSNode.js` (example `webgpu_postprocessing_sss`). WebGL: `SubsurfaceScatteringShader` (`module-SubsurfaceScatteringShader.md`) as a `ShaderMaterial` shader; cheap fake alternative: `MeshPhysicalMaterial` with `sheen`, slightly red `sheenColor`, and `transmission` low + `thickness`.

## 6. Environment lighting
Image-based lighting (IBL) is the single biggest realism lever. Equirect HDR is prefiltered into a PMREM (GGX-convolved mip chain: sharp mip for roughness 0, blurred for roughness 1).
```js
import { HDRLoader } from 'three/addons/loaders/HDRLoader.js';      // .hdr, default HalfFloatType
import { EXRLoader } from 'three/addons/loaders/EXRLoader.js';      // .exr
import { UltraHDRLoader } from 'three/addons/loaders/UltraHDRLoader.js'; // .hdr.jpg gain-map JPEG, 5-10x smaller
const env = await new HDRLoader().loadAsync('studio_2k.hdr');
env.mapping = THREE.EquirectangularReflectionMapping;   // renderer PMREMs it automatically
scene.environment = env;                 // lighting + reflections for all Standard/Physical/Phong/Lambert
scene.background = env;                  // optional visible sky
scene.environmentIntensity = 1;          // scale lighting only
scene.environmentRotation.y = 0.8;       // rotate light direction (radians) without moving the camera
scene.backgroundIntensity = 1; scene.backgroundBlurriness = 0.3; scene.backgroundRotation.y = 0.8;
```
Explicit PMREM (needed for `RoomEnvironment`, `fromScene`, and when you want to dispose the source):
```js
const pmrem = new THREE.PMREMGenerator(renderer);                 // WebGPU: same class from 'three/webgpu'
const rt = pmrem.fromEquirectangular(env);                         // ideal source 1k x 512 (2k okay)
scene.environment = rt.texture;  env.dispose(); pmrem.dispose();
// procedural studio, no download:
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture; // sigma 0.04 blur
```
Methods: `fromEquirectangular(tex, renderTarget)`, `fromCubemap(cube, renderTarget)`, `fromScene(scene, sigma=0, near=0.1, far=100, options)`, `compileEquirectangularShader()`, `dispose()`. `fromScene` also works for a custom light-box built from emissive planes (softbox studio) or a `Sky` mesh (sect. 8).

Intensity semantics (r187 `WebGLRenderer`): if `material.envMap === null` and `scene.environment !== null`, **`scene.environmentIntensity` is used and `material.envMapIntensity` is ignored**. `material.envMapIntensity` only applies when you assign `material.envMap` yourself. Same for rotation: `scene.environmentRotation` vs `material.envMapRotation`.
- Override per material: `mat.envMap = otherPmremTexture; mat.envMapIntensity = 2;` (e.g. a dedicated reflection env for a chrome ball, or a CubeCamera render for a dynamic mirror).
- HDRI exposure: indoor/studio HDRIs 1-3 intensity needs no light; outdoor sun HDRIs are very bright; use `renderer.toneMappingExposure` 0.3-0.8 or `environmentIntensity` 0.3-0.6 when adding a DirectionalLight for shadows.
- Env maps give no shadows. Add one `DirectionalLight` matching the brightest spot of the HDRI (same azimuth/elevation; flip rotation if you rotate the env) to get coherent shadows. Intensity: ~1-3 for studio fill, 3-5 for sun alongside environmentIntensity ~0.5.
- Box-projected / local reflections: `webgpu_materials_envmaps_bpcem`.
- WebGPU only: `ImportanceSampledEnvironment` (`three/addons/tsl/display/ImportanceSampledEnvironment.js`, ctor `(importanceSampling:boolean)`, builds luminance CDF via `EnvMapCDFGenerator`; methods `sampleEnvironmentBRDF`, `sampleEnvironmentMIS`, `sampleReflect`) feeds screen-space reflection misses; use via `ssr` node (`envImportanceSampling`, `setEnvMap(hdr)`, `environmentIntensity` default pi).
- Ground-projected HDRI (kills the "floating" floor):
```js
import { GroundedSkybox } from 'three/addons/objects/GroundedSkybox.js';
const sky = new GroundedSkybox(env, 15, 100);  // (map, height = camera height in photo, radius)
sky.position.y = 15 - 0.01;                     // put ground at y=0
scene.add(sky); scene.environment = env;        // keep scene.background null
```
WebGPU: `getGroundProjectedNormal` from `three/addons/tsl/utils/GroundedSkybox.js` (example `webgpu_materials_envmaps_groundprojected`). Keep models within ~height*0.3 of the origin; scale the model so the horizon looks right.

Global illumination (indirect bounce): `LightProbe` (single SH, `LightProbeGenerator`), `LightProbeGrid` (WebGPU: `three/addons/lighting/LightProbeGrid.js`, ctor `(w,h,d,wProbes,hProbes,dProbes)`, `await probes.bake(renderer, scene, options)`, `priority` for overlapping grids (r187; `falloff` removed); WebGL: `LightProbeGridWebGL.js`; helper `LightProbeGridHelper`). It is a Light: add to scene, position-dependent diffuse GI for static interiors (examples `webgpu_lightprobes`, `webgl_lightprobes`, `webgl_lightprobes_sponza`). Realtime GI: SSGI node (post file), `VXGI` (`three/addons/lighting/vxgi/VXGINode.js`, example `webgpu_vxgi`, heavy).

## 7. Background vs environment
- `scene.environment` lights objects; `scene.background` is just what the camera sees. They can differ: dark/blurred/solid background with a bright studio env.
- Product shots: `scene.background = color` (or CSS gradient behind a transparent canvas: `new WebGLRenderer({alpha:true})`) + HDR env for reflections. A sharp HDRI background behind a product competes with it; use `backgroundBlurriness 0.3-0.8` (0-1, only for env-map backgrounds) and `backgroundIntensity 0.5-1`.
- WebGPU: `scene.backgroundNode = screenUV.distance(0.5).remap(0,0.5).mix(color(0x888877), color(0x776666))` (vignette gradient, example `webgpu_postprocessing_ssr`). `scene.fogNode = fog(color, factor)` (see post file) also works.

## 8. Light units and sun + sky coherence
- Physical units are always on (the old `physicallyCorrectLights`/`useLegacyLights` flags are gone). `PointLight`/`SpotLight` intensity = candela, `.power` = lumens; default `decay = 2` (inverse square) so intensities are large: a PointLight 3 m from a subject needs ~20-200 cd (manual uses 150). `DirectionalLight` is in lux-like units: 2-5 is a sunlit look in examples (e.g. 3). `AmbientLight`/`HemisphereLight` 0.3-1.5 (prefer HDR env instead).
- Light color temperature: key warm ~ #FFE8D0, sky fill cool ~ #B8D4FF; slight complementary tint = depth.
- Sun + procedural sky (WebGL), shared sun vector for light, sky and env:
```js
import { Sky } from 'three/addons/objects/Sky.js';
const sky = new Sky(); sky.scale.setScalar(450000); scene.add(sky);
const u = sky.material.uniforms;               // turbidity, rayleigh, mieCoefficient, mieDirectionalG, sunPosition, cloudCoverage, cloudDensity, cloudElevation, showSunDisc, time
u.turbidity.value = 10; u.rayleigh.value = 3; u.mieCoefficient.value = 0.005; u.mieDirectionalG.value = 0.7;
const sun = new THREE.Vector3().setFromSphericalCoords(1, THREE.MathUtils.degToRad(90 - elevation), THREE.MathUtils.degToRad(azimuth));
u.sunPosition.value.copy(sun);
dirLight.position.copy(sun).multiplyScalar(100);
renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 0.5; // sky is very bright
// bake sky into env for reflections/IBL
const rt = new THREE.PMREMGenerator(renderer).fromScene(skyOnlyScene); scene.environment = rt.texture; // re-run when sun moves
```
WebGPU: `SkyMesh` from `three/addons/objects/SkyMesh.js` with `sky.turbidity.value`, `rayleigh`, `mieCoefficient`, `mieDirectionalG`, `sunPosition.value`, `cloudCoverage/Density/Elevation/Scale/Speed`, `showSunDisc.value = false` (let the light be the sun). Use `SunLight` (`three/addons/lights/SunLight.js`, `SunLight.registerNode(SunLightNode)` for WebGPU, r187+) for large-scene 2-cascade shadows (see shadows file).
- Elevation drives color: low sun (< 10 deg) = warm light color + fog; midday = near white. Lerp `light.color` and `light.intensity` with elevation (example `webgpu_lights_sunlight`: `intensity = 3 + daylight*2`, `daylight = min(1, elev/30)`).

## 9. Studio lighting
RectAreaLight: soft, physically shaped reflections (softbox highlights on glossy things). No shadows, only Standard/Physical materials.
```js
import { RectAreaLightUniformsLib } from 'three/addons/lights/RectAreaLightUniformsLib.js'; // WebGLRenderer
import { RectAreaLightHelper } from 'three/addons/helpers/RectAreaLightHelper.js';
RectAreaLightUniformsLib.init();
// WebGPU: import { RectAreaLightTexturesLib } from 'three/addons/lights/RectAreaLightTexturesLib.js';
//         THREE.RectAreaLightNode.setLTC(RectAreaLightTexturesLib.init());
```
Three-point recipe (subject at origin, ~1 m tall, intensity of RectAreaLight is nits-like; start here and adjust exposure):
| Light | Size (w x h) | Position | Intensity | Color |
|---|---|---|---|---|
| Key | 2 x 2 | (2.5, 2.5, 3) lookAt(0,0.5,0) (45 deg off axis, 45 deg up) | 8-15 | 0xfff1e0 |
| Fill | 3 x 3 | (-3, 1, 2) | 2-4 (key:fill 3:1 to 4:1) | 0xdbe8ff |
| Rim / back | 0.5 x 3 strip | (-1.5, 2.5, -3) | 12-25 | 0xffffff |
| Top softbox (reflections) | 3 x 3 | (0, 4, 0) facing down | 4-8 | white |
Add `new THREE.DirectionalLight(0xffffff, 1.5)` at the key position with `castShadow` for the actual shadow (area lights cast none). Strip lights placed beside glossy bodies give the long white highlights that define shape.

IES profiles (WebGPU only): photometric distribution for architectural light fixtures.
```js
import { IESLoader } from 'three/addons/loaders/IESLoader.js';
const ies = await new IESLoader().setPath('./ies/').loadAsync('fixture.ies');
const spot = new THREE.IESSpotLight(0xffffff, 500); // (color, intensity cd, distance, angle, penumbra, decay)
spot.iesMap = ies; spot.angle = Math.PI / 8; spot.penumbra = 0.7; spot.distance = 20; spot.castShadow = true;
```
`ProjectorLight` (WebGPU, gobo/projection map) example `webgpu_lights_projector`. Also `webgpu_lights_clustered` / `ClusteredLighting` for hundreds of lights, `DynamicLighting`.

## 10. glTF best practices
```js
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { DRACOLoader, DRACO_GLTF_CONFIG } from 'three/addons/loaders/DRACOLoader.js';
import { KTX2Loader } from 'three/addons/loaders/KTX2Loader.js';
import { MeshoptDecoder } from 'three/addons/libs/meshopt_decoder.module.js';
const loader = new GLTFLoader()
  .setDRACOLoader(new DRACOLoader().setDecoderPath(DRACO_GLTF_CONFIG))
  .setKTX2Loader(new KTX2Loader().setTranscoderPath('/basis/').detectSupport(renderer))
  .setMeshoptDecoder(MeshoptDecoder);
const gltf = await loader.loadAsync('model.glb');
await renderer.compileAsync(gltf.scene, camera, scene); // avoid first-frame hitch (WebGPU: renderer.compileAsync too)
scene.add(gltf.scene);
gltf.scene.traverse(o => { if (o.isMesh) { o.castShadow = o.receiveShadow = true; } });
```
Supported by GLTFLoader: KHR_draco_mesh_compression, KHR_lights_punctual, KHR_materials_anisotropy, clearcoat, dispersion, emissive_strength, ior, specular, transmission, iridescence, unlit, volume, KHR_materials_sheen (in source, missing from the doc list), KHR_mesh_quantization, KHR_meshopt_compression, KHR_texture_basisu, KHR_texture_transform, EXT_materials_bump, EXT_meshopt_compression, EXT_mesh_gpu_instancing, EXT_texture_avif, EXT_texture_webp. Plugins: KHR_gaussian_splatting, KHR_materials_variants, KHR_animation_pointer, MSFT_texture_dds, NEEDLE_progressive.
- Draco = geometry only, meshopt = geometry+animation, KTX2 = textures. Combine meshopt + KTX2 for the best size/decoding. Author in Blender: Principled BSDF maps to glTF PBR; use Khronos glTF Validator; test in a neutral viewer first.
- glTF color factors are linear and textures tagged by the loader; do not retag.
- Reuse materials/geometries (instancing, `EXT_mesh_gpu_instancing`); merge static meshes to cut draw calls.
- Examples: `webgl_loader_gltf` (the canonical realism setup: `UltraHDRLoader` env + background, `ACESFilmicToneMapping`, `backgroundBlurriness` slider), `webgl_loader_gltf_transmission`, `_sheen`, `_iridescence`, `_anisotropy`, `_dispersion`, `_compressed`; WebGPU twins `webgpu_loader_gltf*`.

## 11. Starter: product viewer
WebGL (ESM):
```js
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { GTAOPass } from 'three/addons/postprocessing/GTAOPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';

const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.setSize(innerWidth, innerHeight);
renderer.toneMapping = THREE.NeutralToneMapping;      // true-to-albedo product colors
renderer.toneMappingExposure = 1;
renderer.shadowMap.enabled = true;                    // PCF default
document.body.appendChild(renderer.domElement);

const scene = new THREE.Scene();
scene.background = new THREE.Color(0xe9e9ec);
const pmrem = new THREE.PMREMGenerator(renderer);
scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
scene.environmentIntensity = 1;

const camera = new THREE.PerspectiveCamera(35, innerWidth / innerHeight, 0.05, 50); // long lens = less distortion
camera.position.set(2.2, 1.2, 3.2);
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true; controls.target.set(0, 0.5, 0);
controls.minPolarAngle = 0.2; controls.maxPolarAngle = Math.PI / 2 - 0.05;

const key = new THREE.DirectionalLight(0xfff1e0, 2.2);
key.position.set(3, 5, 3); key.castShadow = true;
key.shadow.mapSize.set(2048, 2048);
Object.assign(key.shadow.camera, { left: -3, right: 3, top: 3, bottom: -3, near: 0.5, far: 15 });
key.shadow.bias = -0.0002; key.shadow.normalBias = 0.02; key.shadow.radius = 4;
scene.add(key);

const floor = new THREE.Mesh(new THREE.CircleGeometry(20, 64), new THREE.ShadowMaterial({ opacity: 0.25 })); // shadow catcher
floor.rotation.x = -Math.PI / 2; floor.receiveShadow = true; scene.add(floor);

const gltf = await new GLTFLoader().loadAsync('product.glb');
gltf.scene.traverse(o => { if (o.isMesh) { o.castShadow = true; o.material.envMapIntensity = 1; } });
scene.add(gltf.scene);

const composer = new EffectComposer(renderer);
composer.addPass(new RenderPass(scene, camera));
const gtao = new GTAOPass(scene, camera, innerWidth, innerHeight); gtao.output = GTAOPass.OUTPUT.Default; composer.addPass(gtao);
composer.addPass(new OutputPass());
renderer.setAnimationLoop(() => { controls.update(); composer.render(); });
addEventListener('resize', () => { renderer.setSize(innerWidth, innerHeight); composer.setSize(innerWidth, innerHeight);
  camera.aspect = innerWidth / innerHeight; camera.updateProjectionMatrix(); });
```
(`material.envMapIntensity` is ignored here because the env comes from `scene.environment`; use `scene.environmentIntensity`.) For MSAA with the composer, pass `new EffectComposer(renderer, new THREE.WebGLRenderTarget(w*pr, h*pr, { type: THREE.HalfFloatType, samples: 4 }))`, or drop the composer and use `renderer.setEffects`.

WebGPU:
```js
import * as THREE from 'three/webgpu';
import { pass, mrt, output, normalView, velocity, sample, packNormalToRGB, unpackRGBToNormal, screenUV, builtinAOContext } from 'three/tsl';
import { ao } from 'three/addons/tsl/display/GTAONode.js';
import { traa } from 'three/addons/tsl/display/TRAANode.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';

const renderer = new THREE.WebGPURenderer({ antialias: true });
await renderer.init();
renderer.toneMapping = THREE.NeutralToneMapping;
renderer.shadowMap.enabled = true;
const pmrem = new THREE.PMREMGenerator(renderer);
scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;

const rp = new THREE.RenderPipeline(renderer);
const pre = pass(scene, camera);
pre.setMRT(mrt({ output: packNormalToRGB(normalView), velocity }));
pre.getTexture('output').type = THREE.UnsignedByteType;
const preNormal = sample(uv => unpackRGBToNormal(pre.getTextureNode().sample(uv)));
const preDepth = pre.getTextureNode('depth');
const aoNode = ao(preDepth, preNormal, camera); aoNode.resolutionScale = 0.5;
const main = pass(scene, camera);
main.contextNode = builtinAOContext(aoNode.getTextureNode().sample(screenUV).r); // AO applied to indirect light only
rp.outputNode = traa(main, preDepth, pre.getTextureNode('velocity'), camera);    // TAA replaces MSAA
renderer.setAnimationLoop(() => rp.render());
```
(Pattern from `webgpu_postprocessing_ao`; when not using TAA set `main.options.samples = 4`.)

## 12. Starter: architectural exterior
WebGL:
```js
import { Sky } from 'three/addons/objects/Sky.js';
import { SunLight } from 'three/addons/lights/SunLight.js'; // 2-cascade sun shadow
const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 0.5;
renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFShadowMap;
scene.fog = new THREE.Fog(0xcfe0ff, 200, 3000);
const sky = new Sky(); sky.scale.setScalar(450000); scene.add(sky);
const sun = new THREE.Vector3().setFromSphericalCoords(1, THREE.MathUtils.degToRad(90 - 35), THREE.MathUtils.degToRad(160));
sky.material.uniforms.sunPosition.value.copy(sun);
const sunLight = new SunLight(0xfff2e3, 4);       // position = direction from origin; no target
sunLight.position.copy(sun); sunLight.castShadow = true; sunLight.shadow.camera.far = 400; sunLight.shadow.normalBias = 1;
scene.add(sunLight);
const env = new THREE.PMREMGenerator(renderer).fromScene(skyOnly); scene.environment = env.texture; scene.environmentIntensity = 0.6;
// ground: large MeshStandardMaterial plane with tiled albedo+normal, anisotropy 16, receiveShadow
```
(`skyOnly` is a scene holding a second `Sky` with the same uniforms; render the sky into PMREM that way, as `webgpu_lights_sunlight` does with `sceneEnv`.) Add `HemisphereLight(0xbcd7ff, 0x8a7f6a, 0.4)` only if env is off; glass facades: `MeshPhysicalMaterial({transmission:1, roughness:0.03, thickness:0.05, ior:1.5})` or cheaper `transparent` + `envMapIntensity` boost with `Reflector`/env. Add post: GTAO + bloom + OutputPass (see post file). Fine mapped details: `normalMap` bricks, `aoMap`, anisotropy 16.

WebGPU:
```js
import * as THREE from 'three/webgpu';
import { SkyMesh } from 'three/addons/objects/SkyMesh.js';
import { SunLight } from 'three/addons/lights/SunLight.js';
import { SunLightNode } from 'three/addons/lights/SunLightNode.js';
const renderer = new THREE.WebGPURenderer({ antialias: true });
SunLight.registerNode(SunLightNode);   // register before use (r187; was renderer.library.addLight before)
renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 0.6;
renderer.shadowMap.enabled = true;
await renderer.init();
const sky = new SkyMesh(); sky.scale.setScalar(9000); sky.turbidity.value = 3; sky.rayleigh.value = 2;
sky.cloudSpeed.value = 0; sky.showSunDisc.value = false; scene.add(sky);
const sunLight = new SunLight(); sunLight.castShadow = true; sunLight.shadow.camera.far = 300;
sunLight.shadow.mapSize.setScalar(2048); sunLight.shadow.normalBias = 0.05; scene.add(sunLight);
sunLight.position.setFromSphericalCoords(1, THREE.MathUtils.degToRad(90 - 35), THREE.MathUtils.degToRad(160));
sky.sunPosition.value.copy(sunLight.position);
scene.fog = new THREE.Fog(0xcfe0ff, 500, 4000);
scene.environmentIntensity = 0.5;
// env from sky: const rt = pmrem.fromScene(sceneEnvContainingSky); scene.environment = rt.texture;
```
Source: `webgpu_lights_sunlight`.

## 13. The 10 things that make a three.js scene look amateur
1. No environment map: metals black, everything flat. Fix: `scene.environment` = HDRI/`RoomEnvironment`.
2. Default `NoToneMapping` + blown-out lights. Fix: `Neutral`/`AgX`/`ACES` + exposure.
3. Albedo textures not tagged `SRGBColorSpace` (or data maps tagged). Fix: section 3 table.
4. Aliased edges and shimmer: no MSAA/TAA, `pixelRatio` 1 on retina, roughness near 0 with normal maps. Fix: `antialias:true`, `setPixelRatio(min(dpr,2))`, TAA, anisotropy.
5. Floating objects: no contact shadow/AO, no ground. Fix: shadow catcher + AO + contact shadow.
6. Uniform roughness/pure colors (#ff0000 albedo, metalness 0.5). Fix: ranges in section 2, roughness variation, bevels.
7. Harsh hard-edged or acne-ridden shadows from a tiny shadow frustum or huge one. Fix: fit `shadow.camera`, `normalBias`, `radius`, CSM.
8. Pure-black background/void with a single directional light and no fill. Fix: key/fill/rim, colored (warm/cool) light, HDR env.
9. Ultra-wide default FOV 75 + near plane 0.001 / far 1e6 (z-fighting, distortion). Fix: FOV 25-45 for products, 45-60 architecture, tight near/far, `logarithmicDepthBuffer`/`reversedDepthBuffer` only if needed.
10. No atmosphere or lens: no fog/aerial perspective, no bloom on emissives, no subtle vignette/grain, no depth cue. Fix: `Fog`/height fog, bloom for emissive only, post stack (see post file).
Bonus: using `MeshBasicMaterial` for everything lit, `Clock` (deprecated; use `Timer`), `PCFSoftShadowMap` (removed).

## 14. See also
- API: `../threejs/references/api/MeshPhysicalMaterial.md`, `MeshStandardMaterial.md`, `MeshPhysicalNodeMaterial.md`, `MeshSSSNodeMaterial.md`, `module-SubsurfaceScatteringShader.md`, `PMREMGenerator.md`, `RoomEnvironment.md`, `GroundedSkybox.md`, `ImportanceSampledEnvironment.md`, `EnvMapCDFGenerator.md`, `HDRLoader.md`, `EXRLoader.md`, `UltraHDRLoader.md`, `KTX2Loader.md`, `GLTFLoader.md`, `Scene.md`, `Texture.md`, `RectAreaLight.md`, `IESSpotLight.md`, `ProjectorLight.md`, `SunLight.md`, `LightProbe.md`, `LightProbeGrid.md`, `Sky.md`, `SkyMesh.md`, `PointLight.md`, `DirectionalLight.md`, `ShadowMaterial.md`, `ProgressiveLightMap.md`
- Examples: `webgl_loader_gltf`, `webgl_materials_physical_clearcoat`, `webgl_materials_physical_transmission`, `webgl_materials_physical_transmission_alpha`, `webgl_materials_envmaps_hdr`, `webgl_materials_envmaps_exr`, `webgl_materials_envmaps_groundprojected`, `webgl_lights_rectarealight`, `webgl_lights_physical`, `webgl_lights_sunlight`, `webgl_shaders_sky`, `webgpu_materials_sss`, `webgpu_materials_transmission`, `webgpu_lights_ies_spotlight`, `webgpu_lights_sunlight`, `webgpu_lights_rectarealight`, `webgpu_lightprobes`
- Docs: https://threejs.org/docs/#MeshPhysicalMaterial , https://threejs.org/manual/en/lights , https://threejs.org/manual/en/color-management
