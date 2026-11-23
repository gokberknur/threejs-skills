# Post-processing and atmosphere (three.js r187)

## When to read this
Building the effect stack (bloom, AO, SSR/SSGI, DoF, motion blur, god rays, grain/vignette/CA, LUT, outline) on WebGLRenderer (EffectComposer / `renderer.setEffects`) or WebGPURenderer (`RenderPipeline` + TSL nodes), and the atmosphere layer (fog, sky, water, reflections, refraction, particles, volumes, clouds). Read `color-and-tone-mapping.md` first: pass ordering relative to tone mapping is the top source of bugs.

## Contents
1. Pipelines side by side (WebGL, WebGL built-in, WebGPU)
2. Pass ordering rules
3. Effects with default parameters (WebGL | WebGPU)
4. Atmosphere: fog, sky, water, reflections, refraction, particles, volumes, clouds
5. Cinematic look checklist (impact per effort)
6. Stack A: realistic product
7. Stack B: stylized / game
8. Stack C: cinematic exterior
9. Performance notes
10. See also

## 1. Pipelines
### WebGL: EffectComposer
```js
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';

renderer.toneMapping = THREE.ACESFilmicToneMapping;       // consumed by OutputPass
const composer = new EffectComposer(renderer);            // default targets: HalfFloatType
composer.setPixelRatio(Math.min(devicePixelRatio, 2));    // call BEFORE setSize
composer.setSize(innerWidth, innerHeight);
composer.addPass(new RenderPass(scene, camera));          // beauty
/* ...linear HDR effects... */
composer.addPass(new OutputPass());                       // tone map + sRGB
/* ...display-referred effects (FXAA, LUT, grain)... */
renderer.setAnimationLoop(() => composer.render());       // composer.render(deltaTime?)
```
- The last enabled pass renders to the screen automatically (`renderToScreen`); set `composer.renderToScreen = false` for composers that feed another (selective bloom). `insertPass(pass, index)`, `removePass`, `isLastEnabledPass`, `reset`, `dispose`, `swapBuffers` exist.
- Resize: `renderer.setSize(w,h); composer.setSize(w,h)` (passes with their own buffers get `setSize`).
- Custom effect: `new ShaderPass(MyShader)` (`CopyShader`, `VignetteShader`, `RGBShiftShader`, `BleachBypassShader`, `SepiaShader`, `BrightnessContrastShader` ship in `three/addons/shaders/`).
- MSAA: pass a `WebGLRenderTarget` with `samples: 4, type: HalfFloatType` to the composer constructor, or use SSAA/TAA/FXAA.
- Masking: `MaskPass`/`ClearMaskPass` (example `webgl_postprocessing_masking`); `renderPass.clearAlpha = 0` for transparent canvases.

### WebGL built-in chain (new in r186): `setEffects`
```js
const renderer = new THREE.WebGLRenderer({ antialias: true, outputBufferType: THREE.HalfFloatType }); // HalfFloat/Float required
renderer.toneMapping = THREE.AgXToneMapping;
renderer.setEffects([bloomPass /*, taaPass, ... */]);     // no OutputPass (warns). setEffects(null) to disable
renderer.render(scene, camera);
```
MSAA scene target (4 samples with `antialias`), effects ping-pong on half-float targets, then built-in tone mapping + sRGB. If the first effect is a `RenderPass`/`TAARenderPass` it renders the scene itself. Passes need `render(renderer, writeBuffer, readBuffer, dt)`, optional `setSize`, `enabled`, `needsSwap`. Examples: `webgl_shaders_ocean`, `webgl_watch`. Effects needing sRGB input (FXAA, LUT) cannot go after the built-in output, so use EffectComposer for those.

### WebGPU: RenderPipeline
(`PostProcessing` was renamed `RenderPipeline` in r183; the old class is a deprecated wrapper. Use `RenderPipeline`.) `WebGPURenderer` only.
```js
import * as THREE from 'three/webgpu';
import { pass, mrt, output, emissive, velocity, normalView, renderOutput } from 'three/tsl';

const renderer = new THREE.WebGPURenderer({ antialias: true });  // outputBufferType defaults to HalfFloat
await renderer.init();
renderer.toneMapping = THREE.ACESFilmicToneMapping;              // applied automatically at the end
const rp = new THREE.RenderPipeline(renderer);
const scenePass = pass(scene, camera);                           // options e.g. { samples: 4 } via scenePass.options
const color = scenePass.getTextureNode('output');
const depth = scenePass.getTextureNode('depth');
rp.outputNode = color;                                           // compose nodes here
// rp.outputColorTransform = false  -> you call renderOutput(node) yourself (FXAA / LUT / grain after)
// rp.needsUpdate = true            -> after replacing outputNode
renderer.setAnimationLoop(() => rp.render());                    // not renderer.render()
```
`mrt({ output, emissive, velocity, normal: packNormalToRGB(normalView), ... })` via `scenePass.setMRT(...)` produces extra attachments in ONE render; read them with `getTextureNode(name)`; depth is free (`'depth'`), `getLinearDepthNode()`, `getViewZNode()`. Reduce bandwidth: `scenePass.getTexture('normal').type = THREE.UnsignedByteType` (pack normals with `packNormalToRGB`/`unpackRGBToNormal`, wrap with `sample(uv => ...)`). `pass(scene, camera).setResolutionScale(.25)`, `.setLayers(layers)`, `.contextNode` (`builtinAOContext`, `builtinGIContext`).

### Equivalent map
| Concept | WebGL EffectComposer | WebGPU RenderPipeline |
|---|---|---|
| Manager | `EffectComposer` | `RenderPipeline` |
| Beauty | `RenderPass` | `pass(scene, camera)` |
| Tone map + sRGB | `OutputPass` | automatic, or `renderOutput()` with `outputColorTransform=false` |
| Extra buffers | separate depth/normal passes inside pass | `mrt({...})` |
| Chain | `addPass` order | node composition |
| Loop | `composer.render()` | `rp.render()` |
| Resize | `composer.setSize` | handled by renderer |

## 2. Pass ordering (why)
Linear HDR (before tone map): AO (modulates ambient), SSR, SSGI, godrays, DoF, motion blur, bloom (needs > 1 values), lens flare, TAA/TRAA, fog (if post). Then tone mapping/sRGB. Then display-referred: FXAA/SMAA (SMAA is used pre-output in `webgpu_postprocessing_ssr` and post-RenderPass in `webgl_postprocessing_smaa`; both work, FXAA must be post), LUT grading, film grain, vignette, chromatic aberration, sharpen, dithering. Reason: bloom thresholds and DoF bokeh weights depend on real scene energy; LUTs and grain are authored in display space.
Canonical WebGL order: `RenderPass -> GTAOPass -> SSRPass -> BokehPass -> UnrealBloomPass -> OutputPass -> (LUTPass/FilmPass/ShaderPass(Vignette)) -> FXAAPass`.

## 3. Effects
All values are starting points; tune by eye with exposure fixed.

### 3.1 Bloom
Why: real lenses scatter strong highlights. Bloom of everything (low threshold) = foggy/"dreamy"; use for emissives and suns only.
WebGL (`UnrealBloomPass(resolution, strength, radius, threshold)`; props `strength`, `radius`, `threshold`):
```js
const bloom = new UnrealBloomPass(new THREE.Vector2(innerWidth, innerHeight), 0.5, 0.4, 0.95);
composer.addPass(bloom);   // after RenderPass (and after AO/DoF), before OutputPass
// defaults in official demo: strength 1, radius 0.5, threshold 0 (everything blooms; reduce)
```
Recommended: threshold 0.85-1.0 (linear luminance; > 1 = only HDR emissives), strength 0.2-0.8 (subtle) up to 1.5 (neon), radius 0.3-0.6. Lower `toneMappingExposure` ~ bloom looks stronger: tune together.
Selective bloom (WebGL), two options:
1. Emissive-driven: make glowing materials `emissive` with `emissiveIntensity` 3-10 and `threshold ~1`; nothing else exceeds 1. Cheapest.
2. Layers (`webgl_postprocessing_unreal_bloom_selective`): `bloomLayer = new THREE.Layers(); bloomLayer.set(1)`; render a `bloomComposer` (`renderToScreen=false`, HalfFloat target) with non-bloom meshes swapped to a black material (`scene.traverse(darkenNonBloomed)`), then `finalComposer` mixes `bloomComposer.renderTarget2.texture` via a `ShaderPass` (additive) before `OutputPass`. Two scene renders.
WebGPU (`bloom(node, strength = 1, radius = 0, threshold = 0)`; uniforms `.strength/.radius/.threshold` are nodes: set `.value`):
```js
import { bloom } from 'three/addons/tsl/display/BloomNode.js';
const b = bloom(color, 0.5, 0.4, 0.95);
rp.outputNode = color.add(b);        // bloom returns only the glow; add it to the beauty
b.setResolutionScale(0.5);           // cheaper
```
Selective via MRT emissive (example `webgpu_postprocessing_bloom_emissive`):
```js
scenePass.setMRT(mrt({ output, emissive }));
const em = scenePass.getTextureNode('emissive');
rp.outputNode = scenePass.getTextureNode().add(bloom(em, 2.5, 0.5));  // only emissive buffer blooms
```
Per-object intensity (example `webgpu_postprocessing_bloom_selective`): `material.mrtNode = mrt({ bloomIntensity: uniform(1) })`, scene pass default `bloomIntensity: float(0)`, `bloom(output.mul(bloomIntensityTex))`, `rp.outputColorTransform = false; rp.outputNode = out.add(b).renderOutput()`.

### 3.2 Ambient occlusion
Why: contact darkening where indirect light is blocked; grounds objects and gives crevice depth. GTAO > SSAO/SAO (SAO, SSAO are legacy; use for low-end).
WebGL:
```js
const gtao = new GTAOPass(scene, camera, innerWidth, innerHeight);       // addons/postprocessing/GTAOPass.js
gtao.output = GTAOPass.OUTPUT.Denoise;                                   // Default | Diffuse | AO | Denoise | Depth | Normal
gtao.blendIntensity = 1;
gtao.updateGtaoMaterial({ radius: 0.25, distanceExponent: 1, thickness: 1, scale: 1, samples: 16, distanceFallOff: 1, screenSpaceRadius: false });
gtao.updatePdMaterial({ lumaPhi: 10, depthPhi: 2, normalPhi: 3, radius: 4, radiusExponent: 1, rings: 2, samples: 16 }); // denoiser
gtao.setSceneClipBox(new THREE.Box3().setFromObject(model));             // tighten for quality
composer.addPass(gtao);                                                  // right after RenderPass; output = Default blends AO into the image
```
Alternatives: `SSAOPass(scene, camera, w, h, kernelSize)` (`kernelRadius`, `minDistance`, `maxDistance`, `output`), `SAOPass(scene, camera)` (`params`). Radius in world units: ~ 0.1-0.5 of object scale (0.25 default); big radius = halos.
WebGPU (`ao(depth, normal, camera)` from `GTAONode`, or `ssao(...)` from `SSAONode`). AO applied to ambient only through `builtinAOContext` (physically right, no halos on lit surfaces):
```js
import { ao } from 'three/addons/tsl/display/GTAONode.js';
import { pass, mrt, normalView, velocity, sample, packNormalToRGB, unpackRGBToNormal, screenUV, builtinAOContext } from 'three/tsl';
const pre = pass(scene, camera); pre.setMRT(mrt({ output: packNormalToRGB(normalView), velocity }));
pre.getTexture('output').type = THREE.UnsignedByteType;
const preNormal = sample(uv => unpackRGBToNormal(pre.getTextureNode().sample(uv)));
const preDepth = pre.getTextureNode('depth');
const g = ao(preDepth, preNormal, camera);          // uniforms: radius 0.25, samples 16, thickness 1, scale 1; resolutionScale 1 (use 0.5)
g.resolutionScale = 0.5;  g.useTemporalFiltering = true;   // with TRAA
const main = pass(scene, camera);
main.contextNode = builtinAOContext(g.getTextureNode().sample(screenUV).r);
```
(`distanceExponent`, `distanceFallOff` deprecated r186.) Optional denoiser: `denoise(aoTex, depth, normal, camera)` (`DenoiseNode`), `recurrentDenoise`. Example `webgpu_postprocessing_ao` (switches GTAO | SSAO).

### 3.3 SSR / SSGI
SSR: sharp reflections of on-screen things on glossy/metal floors. Misses fall back to the env map. Cost medium-high; fails at screen edges.
WebGL `SSRPass({ renderer, scene, camera, width, height, groundReflector, selects })`: props `thickness 0.018`, `maxDistance 0.1` (example), `opacity`, `fresnel`, `distanceAttenuation`, `bouncing`, `blur`, `infiniteThick`; pair with `ReflectorForSSRPass` on floors; then `OutputPass` (example `webgl_postprocessing_ssr`). Legacy-feeling; for planar floors prefer `Reflector` (section 4).
WebGPU (`ssr(color, depth, normal, { metalnessNode, roughnessNode })`, add result to beauty):
```js
import { ssr } from 'three/addons/tsl/display/SSRNode.js';
scenePass.setMRT(mrt({ output, normal: packNormalToRGB(normalView), metalrough: vec2(metalness, roughness) }));
['normal','metalrough'].forEach(n => scenePass.getTexture(n).type = THREE.UnsignedByteType);
const sceneNormal = sample(uv => unpackRGBToNormal(scenePass.getTextureNode('normal').sample(uv)));
const mr = scenePass.getTextureNode('metalrough');
const s = ssr(color, depth, sceneNormal, { metalnessNode: mr.r, roughnessNode: mr.g });
s.quality.value = 0.5; s.maxDistance.value = 1; s.intensity.value = 1; s.thickness.value = 0.03; // defaults: quality .5, maxDistance 1, thickness .1
s.blurQuality = 2; s.binaryRefine = false;           // reflectNonMetals, stochastic, screenEdgeFade, envImportanceSampling also exist
rp.outputNode = smaa(color.add(s.rgb));
```
Example `webgpu_postprocessing_ssr`, `webgpu_postprocessing_ssr_denoise`.
SSGI (WebGPU only): `ssgi(beauty, depth, normal, camera)` from `SSGINode`; props `sliceCount` (default 1; 2 used), `stepCount` (12; 8 used), `radius` 12, `giIntensity` 10, `aoIntensity` 1, `thickness` 1, `useTemporalFiltering`; outputs `getAONode()`, `getGINode()` (`ao` node used as a multiplier on beauty, `gi` node rgb added to diffuse, as in the example). Composite: `beauty.rgb * ao + diffuse.rgb * gi`, then `traa`. MRT needs `output, diffuseColor, normal, velocity`. Example `webgpu_postprocessing_ssgi`. For large static interiors prefer `LightProbeGrid`/VXGI.

### 3.4 Depth of field
Why: shallow DoF = scale and focus; most effective for macro/product and cinematic stills. Physical aperture is faked.
WebGL `BokehPass(scene, camera, { focus, aperture, maxblur })` (renders its own depth):
```js
composer.addPass(new BokehPass(scene, camera, { focus: 3.0, aperture: 0.0002, maxblur: 0.01 })); // focus = world distance along view
// pass.uniforms.focus.value / aperture.value / maxblur.value at runtime; the demo uses aperture = 5 * 0.00001 with focus 500 (scene-scale dependent)
```
Class defaults (focus 1, aperture 0.025) assume a unit scale; reduce aperture for large scenes. Update `focus` from a raycast to the cursor / subject distance; animate with damping (rack focus).
WebGPU:
```js
import { dof } from 'three/addons/tsl/display/DepthOfFieldNode.js';
const focusDistance = uniform(5), focalLength = uniform(0.5), bokehScale = uniform(3);
rp.outputNode = dof(color, scenePass.getViewZNode(), focusDistance, focalLength, bokehScale);
```
Example uses focusDistance 500, focalLength 200, bokehScale 10 on a ~1000-unit scene: scale `focusDistance` to world units; larger `bokehScale` = bigger discs; `focalLength` widens the in-focus band. `webgpu_postprocessing_dof`, `_dof_basic`.

### 3.5 Motion blur
WebGPU only (velocity buffer): 
```js
import { motionBlur } from 'three/addons/tsl/display/MotionBlur.js';
scenePass.setMRT(mrt({ output, velocity }));
rp.outputNode = motionBlur(scenePass.getTextureNode('output'), scenePass.getTextureNode('velocity'), /* numSamples */ 16); // subtle: scale velocity by 0.5-1
```
WebGL: no built-in; use TAA accumulation (`TAARenderPass`) or `AfterimagePass(damp)` (damp 0.9-0.97) for trails. Only apply to moving cameras/objects; motion blur on 60 fps content should be light (shutter 180 deg ~ 0.5).

### 3.6 God rays / volumetric light
WebGPU `godrays(depth, camera, light)` (light: `DirectionalLight` or `PointLight`, must cast shadow): props `raymarchSteps` (60), `density` (0.7), `maxDensity` (0.5), `distanceAttenuation` (2), `resolutionScale` 0.5. Denoise + blend with edge preservation:
```js
import { godrays } from 'three/addons/tsl/display/GodraysNode.js';
import { bilateralBlur } from 'three/addons/tsl/display/BilateralBlurNode.js';
import { depthAwareBlend } from 'three/addons/tsl/display/depthAwareBlend.js';
const g = godrays(depth, camera, light);
const blurred = bilateralBlur(g.getTextureNode());
rp.outputNode = depthAwareBlend(color, blurred.getTextureNode(), depth, camera, { blendColor: uniform(new THREE.Color(0xffe2b0)), edgeRadius: uniform(2), edgeStrength: uniform(2) });
```
Real volumetric lighting (shadowed fog beams, local lights) via `VolumeNodeMaterial` + `VolumetricLightingModel` (example `webgpu_volume_lighting`): box mesh on its own layer, `steps = 12`, `offsetNode = bayer16(screenCoordinate)` (dither), `scatteringNode` = density function, render with `pass(scene, camera, { depthBuffer:false })` + `setLayers`, `setResolutionScale(.25)`, `gaussianBlur` denoise, add to beauty: `scenePass.add(blurred.mul(intensity))`. Light must cast shadows and be on the volumetric layer. `webgpu_volume_lighting_rectarea`, `webgpu_volume_lighting_traa`.
WebGL: no core god-ray pass (example `webgl_postprocessing_godrays` uses third-party `postprocessing` + `godrays` packages). Cheap fake: additive cone/billboard mesh with gradient texture, `depthWrite:false`, or Sprite beams.

### 3.7 Film grain, vignette, chromatic aberration, sharpen
Subtle is professional: grain intensity 0.05-0.2, vignette darkness 0.3-0.6, CA 0.001-0.003. Apply after tone mapping.
WebGL:
```js
composer.addPass(new OutputPass());
composer.addPass(new FilmPass(0.2, false));                    // (intensity, grayscale)
const vig = new ShaderPass(VignetteShader); vig.uniforms.offset.value = 1.0; vig.uniforms.darkness.value = 1.1; composer.addPass(vig);
const ca  = new ShaderPass(RGBShiftShader); ca.uniforms.amount.value = 0.0015; composer.addPass(ca);
```
(`three/addons/shaders/VignetteShader.js`, `RGBShiftShader.js`, `FilmPass` from `postprocessing/FilmPass.js`.)
WebGPU (all in `three/addons/tsl/display/`): `film(inputNode, intensityNode, uvNode)`, `vignette(color, intensity = .4, smoothness = .5, coord)` (`three/addons/tsl/display/CRT.js`, with `scanlines`, `barrelUV`), `chromaticAberration(node, strength = 1, center = null, scale = 1.1)`, `sharpen(node, sharpness, denoise)`, `rgbShift(node, amount, angle)`, `dotScreen`, `sobel`, `bleach`, `sepia`, `scanlines`, `radialBlur`.
```js
rp.outputColorTransform = false;
let o = renderOutput(bloomed);
o = chromaticAberration(o, 0.6);
o = vignette(o, 0.35, 0.5);       // exported by CRT.js
rp.outputNode = film(o, 0.15);
```
Dither final output to kill banding in smooth gradients (low-res gradient skies): add ±0.5/255 noise after output.

### 3.8 Lens flare
WebGL: `Lensflare` (`three/addons/objects/Lensflare.js`) attached to a light, occlusion-tested, cheap, sprites:
```js
const lf = new Lensflare();
lf.addElement(new LensflareElement(flare0, 700, 0, light.color));  // (texture, size px, distance 0..1, color)
lf.addElement(new LensflareElement(flare3, 60, 0.6));
lf.addElement(new LensflareElement(flare3, 120, 0.9));
light.add(lf);
```
`LensflareMesh` is the WebGPU variant (`three/addons/objects/LensflareMesh.js`). Post-process alternative (WebGPU): `lensflare(bloomNode, { threshold, ghostAttenuationFactor, ghostSpacing, ghostSamples, ghostTint, downSampleRatio })` + `gaussianBlur(flare, 8)`; `outputPass.add(bloomPass).add(blurPass)` (example `webgpu_postprocessing_lensflare`, uses `scene.environmentIntensity = 15`, emissive MRT). Use sparingly; anamorphic: `webgpu_postprocessing_anamorphic`.

### 3.9 Color grading LUT
See color file. WebGL `LUTPass` after `OutputPass`; WebGPU `lut3D(renderOutput(...), texture3D(lut), size, intensity)`.

### 3.10 Outline
WebGL `OutlinePass(resolution, scene, camera, selectedObjects)`: `edgeStrength 3`, `edgeGlow 0`, `edgeThickness 1`, `visibleEdgeColor`, `hiddenEdgeColor`, `pulsePeriod`, `usePatternTexture`, `downSampleRatio`. Place before OutputPass; follow with FXAA/SMAA.
WebGPU `outline(scene, camera, { selectedObjects, edgeGlow, edgeThickness })` returns `{ visibleEdge, hiddenEdge }`:
```js
const o = outline(scene, camera, { selectedObjects, edgeThickness: uniform(1), edgeGlow: uniform(0) });
const edges = o.visibleEdge.mul(uniform(new THREE.Color(0xffffff))).add(o.hiddenEdge.mul(uniform(new THREE.Color(0x4e3636)))).mul(3);
rp.outputNode = edges.add(scenePass);
```
Cheaper style outline: inverted-hull mesh, or `OutlineEffect` (legacy), `ToonOutlinePassNode`, `sobel`.

### 3.11 Afterimage, transitions, misc
`AfterimagePass(damp)` / `afterImage(node, damp)` (damp 0.96-0.99 trails); `RenderTransitionPass(sceneA, camA, sceneB, camB)` + `setTexture(mask)` / `transition(a, b, mixTexture, mixRatio, threshold, useTexture)`; `pixelationPass`, `RenderPixelatedPass`, `retroPass`, `HalftonePass`, `GlitchPass` for stylized.

## 4. Atmosphere
### Fog
Why: aerial perspective is the main depth cue outdoors; color it as the sky horizon.
```js
scene.fog = new THREE.Fog(0xcfe0ff, 50, 600);          // linear: near, far; cheap, artistic
scene.fog = new THREE.FogExp2(0xcfe0ff, 0.0025);       // exponential: density, plausible falloff; use 0.0005-0.01 depending on world scale
scene.background = scene.fog.color;                    // match horizon, else visible seam
material.fog = false;                                  // exclude (sky dome, UI)
```
Sky/background shaders and unlit `ShaderMaterial` need `fog: true` + fog chunks to receive fog. Fog color is linear working space like all Colors.
WebGPU TSL (Fog nodes in `three/tsl`; `scene.fogNode`):
```js
import { fog, rangeFogFactor, densityFogFactor, exponentialHeightFogFactor, uniform, color } from 'three/tsl';
scene.fogNode = fog(color(0xffdfc1), rangeFogFactor(10, 200));          // linear
scene.fogNode = fog(color(0xcfe0ff), densityFogFactor(0.01));           // exp
// height fog (thicker low, thins with altitude) - webgpu_fog_height
const density = uniform(0.04), height = uniform(2);
scene.fogNode = fog(color(0xffdfc1), exponentialHeightFogFactor(density, height));
scene.backgroundNode = color(0xffdfc1);
```
Custom per-material fog: `output` node mixing with `rangeFogFactor(reference('near','float',scene.fog), reference('far','float',scene.fog))` (see `webgpu_lights_sunlight`). Volumetric post fog: example `webgpu_postprocessing_fog` (3D-noise raymarch with `Loop`, SunLight).

### Sky
WebGL `Sky` (uniforms): `turbidity` 10 (haze; 2 clear, 20 hazy), `rayleigh` 3 (blue scatter; 0.5-4; high = deep blue, low = washed), `mieCoefficient` 0.005 (haze glow near sun), `mieDirectionalG` 0.7 (sun halo tightness 0-1), `sunPosition` (Vector3), `cloudCoverage`, `cloudDensity`, `cloudElevation`, `showSunDisc`, `time`. Sun from angles:
```js
const sun = new THREE.Vector3().setFromSphericalCoords(1, THREE.MathUtils.degToRad(90 - elevation), THREE.MathUtils.degToRad(azimuth));
sky.material.uniforms.sunPosition.value.copy(sun);
renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 0.1 ~ 0.5; // sky radiance is huge
```
WebGPU `SkyMesh`: same params as nodes: `sky.turbidity.value = 3; sky.rayleigh.value = 2; sky.sunPosition.value.copy(sun); sky.cloudCoverage.value; showSunDisc.value`. Bake to PMREM (`fromScene`) for lighting. Examples `webgl_shaders_sky`, `webgpu_sky`.

### Ocean / water
WebGL `Water` (`three/addons/objects/Water.js`): options `{ textureWidth 512, textureHeight 512, waterNormals (RepeatWrapping), sunDirection, sunColor, waterColor 0x001e0f, distortionScale 3.7, fog: scene.fog !== undefined, alpha, time, clipBias, side }`; animate `water.material.uniforms.time.value += dt`; `sunDirection.value.copy(sun).normalize()`. Reflects the scene via an internal mirror pass; add bloom lightly.
WebGPU `WaterMesh` (`objects/WaterMesh.js`, options `resolutionScale 0.5, waterNormals, alpha, size, sunColor, sunDirection, waterColor, distortionScale`; nodes `distortionScale.value`, `size.value`, `waterColor.value`) and `Water2Mesh` (flow-map water, `webgpu_water`). Backdrop-based stylized water: `webgpu_backdrop_water`. Examples `webgl_shaders_ocean`, `webgpu_ocean`.

### Reflections
- Planar (mirror, glossy floor): WebGL `Reflector` (`geometry, { color 0x7F7F7F, textureWidth/Height 512, clipBias, multisample 4 }`), `reflector.getRenderTarget()`; costs a second scene render; lower size for blurry floors. Pair with roughness-blurred floor layer. WebGPU: `reflector({ resolutionScale: 0.2, bounces, generateMipmaps, depth })`, add `reflection.target` to the mesh, use as `colorNode`/mix input; blur with `gaussianBlur` for rough floors (`webgpu_reflection`, `webgpu_reflection_blurred`, `webgpu_reflection_roughness`, `webgpu_mirror`).
- Dynamic cube: `CubeCamera(near, far, new THREE.WebGLCubeRenderTarget(256))`, `cubeCamera.update(renderer, scene)` (hide the object first); assign `material.envMap = cubeRenderTarget.texture`; update every N frames. `LightProbeGenerator.fromCubeRenderTarget` for GI (example `webgl_lightprobe_cubecamera`).
- Screen-space: SSR (3.3). Static: env map + reflection probes.

### Refraction and backdrop
- Physical: `MeshPhysicalMaterial.transmission` (PBR file); `renderer.transmissionResolutionScale` (WebGL).
- WebGPU `backdropNode` / `backdropAlphaNode` on node materials sample the already-rendered scene behind the surface (like transmission, but fully programmable):
```js
import { viewportSharedTexture, viewportSafeUV, screenUV, grayscale, saturation } from 'three/tsl';
const m = new THREE.MeshBasicNodeMaterial({ transparent: true });
m.backdropNode = saturation(viewportSharedTexture().rgb, 10);           // post-filter whatever is behind
m.backdropNode = viewportSharedTexture(viewportSafeUV(screenUV.add(distortion))).rgb; // refraction
m.backdropAlphaNode = float(0.5);
```
(`webgpu_backdrop`, `webgpu_backdrop_area`, `webgpu_refraction`.) WebGL: `Refractor` (`objects/Refractor.js`, example `webgl_refraction`). Frosted glass: transmission + roughness 0.3-0.6.

### Particles, sprites, soft particles
Sprites (`Sprite` + `SpriteMaterial`) camera-facing; `depthWrite:false`, `transparent:true`, additive for fire/sparks, normal blending with premultiplied alpha for smoke. Hard intersections with geometry look cheap: fade by scene depth.
WebGPU `SpriteNodeMaterial` + `softParticles`:
```js
import { softParticles } from 'three/addons/tsl/utils/SoftParticles.js';
mat.opacityNode = softParticles({ opacity: baseOpacity, distance: 1, contrast: 2 }); // fades over `distance` world units against opaque depth; viewportDepth default viewportDepthTexture()
mat.depthWrite = false;
```
Example `webgpu_particles_soft`; instanced: `Sprite.count`; also `webgpu_tsl_vfx_flames`, `_linkedparticles`, `_tornado`. WebGL: soft fade via custom shader reading a depth texture, or keep particles away from surfaces. Order: `renderOrder`, sorting.

### Volumes and clouds
`VolumeNodeMaterial` (`steps` 25, `offsetNode` dithering, `scatteringNode`) raymarches inside a box; `RaymarchingBox(steps, ({positionRay}) => ...)` helper (`three/addons/tsl/utils/Raymarching.js`) with a 3D noise `Data3DTexture`/`texture3D` (`ImprovedNoise`) for clouds (`webgpu_volume_cloud`, `webgpu_volume_perlin`, `webgpu_volume_fire`, `webgpu_volume_caustics`). WebGL: `webgl_volume_cloud`, `webgl_volume_perlin` (`VolumeShader`). Clouds in the sky dome: `Sky`/`SkyMesh` `cloudCoverage` 0.3-0.5, `cloudDensity` 0.4-0.6, `cloudElevation` 0.5. Layered billboards (`Sprite` with soft particles) are the cheap game option.

## 5. Cinematic look checklist (impact per effort)
1. Correct color pipeline + tone mapping (`AgX`/`ACES`/`Neutral`), exposure tuned. Effort: minutes. Impact: huge.
2. HDR environment (or `RoomEnvironment`) + proper PBR values. 
3. Shadows fitted, `normalBias`, soft `radius`, shadow `intensity` < 1.
4. MSAA / TAA, pixelRatio min(dpr,2), anisotropy 16.
5. AO (GTAO) for contact depth.
6. Bloom restricted to emissives/sun (threshold ~0.9, strength 0.2-0.6).
7. Atmosphere: fog colored like the horizon; height fog; sky.
8. Light design: key/fill/rim, warm vs cool, light color variation.
9. Depth of field (subtle) for hero shots; lens flare on strong sources only.
10. Color grade (LUT intensity 0.4-0.8), vignette 0.3, grain 0.1, chromatic aberration 0.001. Final polish.
11. Reflections on floors (Reflector/SSR), bevels, roughness variation, decals.
12. Motion: camera easing, motion blur (WebGPU), eye adaptation (animate exposure).

## 6. Stack A: realistic product
WebGL:
```js
const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.toneMapping = THREE.NeutralToneMapping; renderer.shadowMap.enabled = true;
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
const rt = new THREE.WebGLRenderTarget(w * pr, h * pr, { type: THREE.HalfFloatType, samples: 4 });
const composer = new EffectComposer(renderer, rt); composer.setPixelRatio(pr); composer.setSize(w, h);
composer.addPass(new RenderPass(scene, camera));
composer.addPass(Object.assign(new GTAOPass(scene, camera, w, h), { output: GTAOPass.OUTPUT.Default }));
composer.addPass(new BokehPass(scene, camera, { focus: dist, aperture: 0.0003, maxblur: 0.006 })); // optional
composer.addPass(new UnrealBloomPass(new THREE.Vector2(w, h), 0.15, 0.4, 1.0));
composer.addPass(new OutputPass());
```
WebGPU:
```js
renderer.toneMapping = THREE.NeutralToneMapping;
const pre = pass(scene, camera); pre.setMRT(mrt({ output: packNormalToRGB(normalView), velocity }));
pre.getTexture('output').type = THREE.UnsignedByteType;
const nrm = sample(uv => unpackRGBToNormal(pre.getTextureNode().sample(uv)));
const depth = pre.getTextureNode('depth');
const g = ao(depth, nrm, camera); g.resolutionScale = 0.5;
const main = pass(scene, camera); main.contextNode = builtinAOContext(g.getTextureNode().sample(screenUV).r);
const col = main.getTextureNode('output');
rp.outputNode = traa(col.add(bloom(col, 0.15, 0.4, 1.0)), depth, pre.getTextureNode('velocity'), camera);
```

## 7. Stack B: stylized / game
Goal: cheap, readable. `NoToneMapping` or `Neutral`, flat/toon light, outlines, strong bloom, no AO/SSR.
WebGL:
```js
renderer.toneMapping = THREE.NoToneMapping;
const composer = new EffectComposer(renderer, new THREE.WebGLRenderTarget(w*pr, h*pr, { type: THREE.HalfFloatType, samples: 4 }));
composer.addPass(new RenderPass(scene, camera));
composer.addPass(new OutlinePass(new THREE.Vector2(w, h), scene, camera, selected));
composer.addPass(new UnrealBloomPass(new THREE.Vector2(w, h), 0.8, 0.5, 0.85));
composer.addPass(new OutputPass());
composer.addPass(new FXAAPass()); // cheap if MSAA target not used
```
WebGPU:
```js
const sp = pass(scene, camera);
const col = sp.getTextureNode('output');
const o = outline(scene, camera, { selectedObjects });
const edges = o.visibleEdge.mul(uniform(new THREE.Color(0x000000))).mul(3);   // dark ink lines
rp.outputColorTransform = false;
rp.outputNode = fxaa(renderOutput(col.add(bloom(col, 0.8, 0.5, 0.85)).sub(edges)));
```
Other stylized tools: `pixelationPass`, `posterize`, `dotScreen`, `sobel`, `retroPass`, `scanlines`; toon: `MeshToonMaterial` with `gradientMap` (`NearestFilter`, no mipmaps).

## 8. Stack C: cinematic exterior
WebGL:
```js
renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 0.5; renderer.shadowMap.enabled = true;
scene.fog = new THREE.Fog(0xcfe0ff, 300, 4000);
// Sky + sun + CSM (see shadows file) + env from sky PMREM
const composer = new EffectComposer(renderer);
const taa = new TAARenderPass(scene, camera); taa.sampleLevel = 2; composer.addPass(taa);
composer.addPass(new GTAOPass(scene, camera, w, h));
composer.addPass(new UnrealBloomPass(new THREE.Vector2(w, h), 0.25, 0.5, 0.9));
composer.addPass(new OutputPass());
composer.addPass(lutPass);                                // LUTPass, intensity 0.6
composer.addPass(new FilmPass(0.12, false));
composer.addPass(vignetteShaderPass);
```
WebGPU:
```js
renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 0.6;
scene.fogNode = fog(color(0xcfe0ff), exponentialHeightFogFactor(uniform(0.004), uniform(30)));
const sp = pass(scene, camera);
sp.setMRT(mrt({ output, velocity }));
const col = sp.getTextureNode('output'), depth = sp.getTextureNode('depth');
const gr = godrays(depth, camera, sunLight);       // sunLight: DirectionalLight casting shadows (SunLight is not in the godrays type list)
let img = depthAwareBlend(col, bilateralBlur(gr.getTextureNode()).getTextureNode(), depth, camera, { blendColor: uniform(new THREE.Color(0xffe2b0)), edgeRadius: uniform(2), edgeStrength: uniform(2) });
img = dof(img, sp.getViewZNode(), uniform(80), uniform(40), uniform(2));       // subtle
img = img.add(bloom(img, 0.25, 0.5, 0.9));
img = traa(img, depth, sp.getTextureNode('velocity'), camera);
rp.outputColorTransform = false;
let out = renderOutput(img);
out = lut3D(out, texture3D(lut.texture3D), lut.texture3D.image.width, uniform(0.6));
out = vignette(out, 0.3, 0.5);
rp.outputNode = film(out, 0.1);
```
(Expensive: drop DoF/godrays on laptops; `resolutionScale 0.5` on AO/godrays/bloom.)

## 9. Performance notes
- Post cost scales with pixels: cap `pixelRatio` at 2 (1.5 on mobile); render AO/SSR/godrays at half resolution (`resolutionScale`); bloom mip chain is cheap.
- Each composer pass is a full-screen read/write; merge cheap color effects into one custom `ShaderPass`. WebGPU `RenderPipeline` fuses node chains.
- HalfFloat everywhere in linear stages; 8-bit for packed normals.
- Resize: recreate/resize on `resize`; dispose old `RenderTarget`s/passes (`pass.dispose()`).
- Profile with `renderer.info` (WebGL) / Inspector (WebGPU: `renderer.inspector = new Inspector()`), then cut by cost/benefit.

## 10. See also
- API (`../threejs/references/api/<Name>.md`): `EffectComposer`, `RenderPass`, `OutputPass`, `ShaderPass`, `UnrealBloomPass`, `GTAOPass`, `SSAOPass`, `SAOPass`, `SSRPass`, `BokehPass`, `FXAAPass`, `SMAAPass`, `TAARenderPass`, `SSAARenderPass`, `OutlinePass`, `LUTPass`, `FilmPass`, `AfterimagePass`, `RenderTransitionPass`, `RenderPipeline`, `PostProcessing` (deprecated), `PassNode`, `MRTNode`, `RenderOutputNode`, `BloomNode`, `GTAONode`, `SSAONode`, `SSRNode`, `SSGINode`, `DepthOfFieldNode`, `TRAANode`, `FXAANode`, `SMAANode`, `FilmNode`, `GodraysNode`, `LensflareNode`, `Lut3DNode`, `OutlineNode`, `DenoiseNode`, `VolumeNodeMaterial`, `VolumetricLightingModel`, `module-SoftParticles`, `Sky`, `SkyMesh`, `Water`, `WaterMesh`, `Reflector`, `ReflectorNode`, `Refractor`, `Lensflare`, `LensflareElement`, `LensflareMesh`, `Fog`, `FogExp2`, `Sprite`, `SpriteNodeMaterial`, `CubeCamera`, `module-VignetteShader`, `module-RGBShiftShader`, `module-VignetteShader`
- Examples: `webgl_postprocessing_unreal_bloom`, `_unreal_bloom_selective`, `_gtao`, `_ssao`, `_sao`, `_ssr`, `_dof`, `_dof2`, `_outline`, `_afterimage`, `_transition`, `_masking`, `_3dlut`, `_taa`, `_ssaa`, `webgpu_postprocessing_bloom`, `_bloom_emissive`, `_bloom_selective`, `_ao`, `_ssr`, `_ssr_denoise`, `_ssgi`, `_dof`, `_motion_blur`, `_godrays`, `_lensflare`, `_ca`, `_outline`, `_3dlut`, `_traa`, `_fog`, `webgpu_volume_lighting`, `webgpu_volume_cloud`, `webgpu_fog_height`, `webgpu_sky`, `webgpu_ocean`, `webgpu_water`, `webgpu_reflection`, `webgpu_backdrop`, `webgpu_particles_soft`, `webgl_shaders_sky`, `webgl_shaders_ocean`, `webgl_lensflares`, `webgl_mirror`, `webgl_refraction`
- Manual: https://threejs.org/manual/en/post-processing , https://threejs.org/manual/en/how-to-use-post-processing , https://threejs.org/manual/en/webgpu-postprocessing , https://threejs.org/manual/en/fog
