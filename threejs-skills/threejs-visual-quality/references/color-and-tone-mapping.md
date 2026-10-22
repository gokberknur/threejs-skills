# Color pipeline and tone mapping (three.js r186)

## When to read this
Scene looks washed out, too dark, too saturated, "plastic", clips to white, or you add post-processing / LUTs / HDR output and need to know where tone mapping and sRGB conversion happen. Read before touching `toneMapping`, `colorSpace`, `OutputPass`, `renderOutput`.

## Contents
1. Mental model
2. ColorManagement and Color
3. Texture colorSpace rules and loaders
4. Output color space, wide gamut, HDR output
5. Tone mapping modes (table) and exposure
6. toneMapped=false
7. Post-processing placement (WebGL and WebGPU)
8. LUT color grading
9. Deprecated / removed
10. Debugging checklist
11. See also

## 1. Mental model
- Author in display-referred sRGB (hex colors, PNG/JPG albedo). Light in scene-referred **linear** (`LinearSRGBColorSpace`, the default working space). Tone map HDR linear to [0,1]. Encode to the display transfer (sRGB). Never skip a stage.
- Why: lighting math (sum of photons, inverse-square falloff, BRDFs) is only correct on values proportional to energy. sRGB is perceptual; adding/multiplying sRGB values gives dark, muddy gradients and blown highlights.
- Pipeline: `texture/color (sRGB)` -> decode to linear -> lights/material/env in linear (HDR, values > 1 allowed) -> exposure -> tone map -> OETF (sRGB) -> canvas.
- Tone mapping in `WebGLRenderer` is applied in the material's fragment shader when rendering to the screen; with `EffectComposer`/`setEffects`/`RenderPipeline` it is deferred to an output step.

## 2. ColorManagement and Color
```js
import * as THREE from 'three';
THREE.ColorManagement.enabled;          // true by default (do not turn off)
THREE.ColorManagement.workingColorSpace; // 'srgb-linear' (THREE.LinearSRGBColorSpace)

const c = new THREE.Color(0x808080);     // hex/CSS are interpreted as sRGB, stored linear
c.r;                                     // 0.2140 (not 0.5)
c.getHex();                              // 0x808080 (converted back to sRGB)
c.setHex(0x808080, THREE.LinearSRGBColorSpace); // override: r = 0.5
c.setRGB(0.5, 0.5, 0.5);                 // raw components, assumed already working space
c.setRGB(0.5, 0.5, 0.5, THREE.SRGBColorSpace); // sRGB components, converted
c.convertSRGBToLinear(); c.convertLinearToSRGB(); // explicit manual conversion
```
- `Color.r/g/b`, `.setRGB()` without a space, `.lerp`, `.multiplyScalar` never convert implicitly. Values > 1 are legal (emissive, light colors).
- Vertex colors (`BufferAttribute` `color`) are read as linear working-space. If you author them as sRGB bytes, convert once on the CPU (`new Color().setRGB(r,g,b,SRGBColorSpace)` then write `.r,.g,.b`).
- Lights, `material.color`, `emissive`, `sheenColor`, `specularColor`, `attenuationColor`, `scene.background` (Color), `fog.color` are all working-space linear after `Color.set(hex)`.
- Convert between spaces: `ColorManagement.workingToColorSpace(color, space)` and `ColorManagement.colorSpaceToWorking(color, space)`; `ColorManagement.convert(color, from, to)`; `ColorManagement.getLuminanceCoefficients(target, space)`. `fromWorkingColorSpace` / `toWorkingColorSpace` are deprecated since r177 (renamed to the two above).
- Never set `ColorManagement.enabled = false` to "fix" brightness; it only hides a wrong texture annotation and breaks every Color setter.

## 3. Texture colorSpace rules
`Texture.colorSpace` default is `NoColorSpace` (data, no conversion).

| Texture use | colorSpace |
|---|---|
| `map`, `emissiveMap`, `sheenColorMap`, `specularColorMap`, `matcap`, LDR `lightMap` | `SRGBColorSpace` (for color maps) |
| `normalMap`, `roughnessMap`, `metalnessMap`, `aoMap`, `bumpMap`, `displacementMap`, `alphaMap`, `clearcoatMap`, `transmissionMap`, `thicknessMap`, `iridescenceMap`, `anisotropyMap`, `specularIntensityMap` | `NoColorSpace` (leave default) |
| HDR equirect (`.hdr`, `.exr`) | `LinearSRGBColorSpace` (HDRLoader and EXRLoader set it) |
| `scene.background` / env cube from LDR JPG | `SRGBColorSpace` |

```js
const albedo = new THREE.TextureLoader().load('albedo.jpg');
albedo.colorSpace = THREE.SRGBColorSpace;          // MUST for color maps
albedo.anisotropy = renderer.capabilities.getMaxAnisotropy(); // WebGLRenderer
// WebGPURenderer: renderer.getMaxAnisotropy()
```
- Wrong sRGB annotation on an albedo: colors look too dark/contrasty (decoded twice) or too bright/washed (not decoded). Wrong annotation on a normal/roughness map: shading looks off, no obvious tint.
- Loaders that set it for you: `GLTFLoader` (baseColor, emissive, sheenColor, specularColor textures = sRGB; color factors set as linear via `setRGB(..., LinearSRGBColorSpace)`; all data textures untouched), `HDRLoader`/`EXRLoader` (linear), `UltraHDRLoader` (sRGB tagged base, HalfFloat output), `KTX2Loader` (parses container color space). `TextureLoader`, `ImageBitmapLoader` do not guess: you must set it.
- Canvas / video / render-target textures: set `colorSpace = SRGBColorSpace` for 8-bit sRGB content (CanvasTexture, VideoTexture). Render targets used as inputs by custom shaders stay linear unless you tag them.
- Custom `ShaderMaterial`/`RawShaderMaterial`: add `#include <colorspace_fragment>` at the end of `main()` (and `<tonemapping_fragment>` if you want tone mapping) or output will be linear on screen.

## 4. Output color space, wide gamut, HDR
```js
renderer.outputColorSpace;   // THREE.SRGBColorSpace (default, both renderers). Leave it.
```
Wide gamut (Display-P3). Lives in addons, must be registered:
```js
import * as THREE from 'three';
import WebGL from 'three/addons/capabilities/WebGL.js';
import { DisplayP3ColorSpace, DisplayP3ColorSpaceImpl,
         LinearDisplayP3ColorSpace, LinearDisplayP3ColorSpaceImpl } from 'three/addons/math/ColorSpaces.js';

THREE.ColorManagement.define({
  [DisplayP3ColorSpace]: DisplayP3ColorSpaceImpl,
  [LinearDisplayP3ColorSpace]: LinearDisplayP3ColorSpaceImpl,
});
const p3 = WebGL.isColorSpaceAvailable(DisplayP3ColorSpace) && matchMedia('(color-gamut: p3)').matches;
if (p3) {
  THREE.ColorManagement.workingColorSpace = LinearDisplayP3ColorSpace; // set BEFORE creating colors/materials
  renderer.outputColorSpace = DisplayP3ColorSpace;
}
photo.colorSpace = DisplayP3ColorSpace; // P3-tagged textures
```
Other addon spaces in `three/addons/math/ColorSpaces.js`: `ExtendedSRGBColorSpace`, `LinearRec2020ColorSpace` (each with `...Impl`). Example: `webgl_test_wide_gamut`.

HDR canvas output (WebGPURenderer, experimental, example `webgpu_hdr`):
```js
import * as THREE from 'three/webgpu';
import { ExtendedSRGBColorSpace, ExtendedSRGBColorSpaceImpl } from 'three/addons/math/ColorSpaces.js';
THREE.ColorManagement.define({ [ExtendedSRGBColorSpace]: ExtendedSRGBColorSpaceImpl });
const renderer = new THREE.WebGPURenderer({ antialias: true, outputType: THREE.HalfFloatType });
renderer.outputColorSpace = ExtendedSRGBColorSpace; // values > 1 reach an HDR display
matchMedia('(dynamic-range: high)').matches; // feature-detect
```
`ColorManagement.getToneMappingMode(space)` returns `'extended'` or `'standard'` from the space's `outputColorSpaceConfig.toneMappingMode`. No such HDR canvas switch is documented for `WebGLRenderer`.

Buffer precision:
- `WebGLRenderer({ outputBufferType: THREE.HalfFloatType })`: scene renders to a half-float target (MSAA 4x if `antialias:true`), then tone mapping + sRGB happens in a final blit. Required for `renderer.setEffects()`; default `UnsignedByteType`.
- `WebGPURenderer({ outputBufferType })` default `HalfFloatType` (recommended); `outputType` = canvas format (device default if omitted).
- Why half-float: linear HDR needs >= 12 bits; 8-bit linear bands in dark gradients and clips highlights before bloom.

## 5. Tone mapping
Constants (src/constants.js): `NoToneMapping=0, LinearToneMapping=1, ReinhardToneMapping=2, CineonToneMapping=3, ACESFilmicToneMapping=4, CustomToneMapping=5, AgXToneMapping=6, NeutralToneMapping=7`. Default `NoToneMapping`, `toneMappingExposure = 1`.

| Mode | Look | Use when |
|---|---|---|
| `NoToneMapping` | Clips at 1.0, no rolloff | UI, flat/unlit stylized, pure LDR, or when you tone map yourself |
| `LinearToneMapping` | `color * exposure`, then clip | Debugging exposure only |
| `ReinhardToneMapping` | Soft shoulder, low contrast, desaturates | Quick fix for blown highlights; looks flat |
| `CineonToneMapping` | Film-like, contrasty, crushed blacks | Stylized warm look |
| `ACESFilmicToneMapping` | High contrast, saturated, hue shifts (blues to purple, hot colors to yellow/white) | Cinematic default; used by most official examples (exposure ~0.5-1.25). Impl is scaled by 1/0.6 internally so exposure 1 is bright |
| `AgXToneMapping` | Low contrast, natural desaturation to white, no hue skew | Photographic realism, bright emissives, sunsets; often needs exposure ~1-1.5 and a touch more light |
| `NeutralToneMapping` | Khronos PBR Neutral: near-identity below ~0.76, compresses highlights | Product/e-commerce: material base colors stay true to albedo. Best for glTF viewers |
| `CustomToneMapping` | You override GLSL `CustomToneMapping(vec3)` | Uncharted2, filmic curves; see `webgl_tonemapping`. WebGL only |

Choosing (why): ACES = punchy/cinematic but changes hues; AgX = most natural for outdoors/lit emissives; Neutral = color accurate. If the client's brand color must match, use Neutral (or No + keep lights low).

Exposure (`renderer.toneMappingExposure`, multiplies linear color before the curve = camera EV):
- Starting points: Neutral 1.0; ACES 0.5-1.0 (1.25 for dim HDRI studio); AgX 1.0-1.5; with `Sky` shader 0.1-0.5 (sky is very bright).
- Change exposure, not light intensity, to globally brighten; change lights to alter ratios. Animate exposure for eye adaptation.
- Mid-gray target: a 18% gray card in key light should land near sRGB 118 (0x76) after tone mapping.

TSL / WebGPU:
```js
import { toneMapping, toneMappingExposure, renderOutput } from 'three/tsl';
renderer.toneMapping = THREE.NeutralToneMapping;       // same API on WebGPURenderer
renderer.toneMappingExposure = 1;
const graded = toneMapping(THREE.ACESFilmicToneMapping, 1.0, colorNode); // manual use on any node
```

## 6. material.toneMapped = false
```js
const ui = new THREE.MeshBasicMaterial({ color: 0xffffff, toneMapped: false }); // WebGLRenderer, direct-to-screen
```
- Use for pure-white UI quads, debug colors, logos, brand-exact flat colors, video planes that must match source.
- `Material.toneMapped` is **ignored** when rendering into a render target, with post-processing (`EffectComposer`, `setEffects`) and on `WebGPURenderer` (all materials get tone mapped). Under post-processing render the UI separately after the composer (second `renderer.autoClear=false` render) or composite with `renderOutput` boundaries.
- Emissive glow: do NOT turn toneMapped off; push emissive > 1 (e.g. `emissive`, `emissiveIntensity` 2-10) and bloom it.

## 7. Post-processing placement
Rule: linear HDR effects (bloom, AO, SSR, DoF, motion blur, TAA) go BEFORE tone mapping; effects that need display-referred input (FXAA, LUT, film grain, vignette, sharpen, dithering) go AFTER.

WebGLRenderer, EffectComposer (HalfFloat target by default):
```js
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
import { FXAAPass } from 'three/addons/postprocessing/FXAAPass.js';
import { LUTPass } from 'three/addons/postprocessing/LUTPass.js';

renderer.toneMapping = THREE.ACESFilmicToneMapping; // read by OutputPass, not applied by RenderPass
const composer = new EffectComposer(renderer);       // internal target type: HalfFloatType
composer.addPass(new RenderPass(scene, camera));
composer.addPass(new UnrealBloomPass(new THREE.Vector2(innerWidth, innerHeight), 0.6, 0.5, 0.9)); // (res, strength, radius, threshold)
composer.addPass(new OutputPass());   // tone mapping + sRGB; settings read from renderer
composer.addPass(new FXAAPass());     // needs sRGB input -> after OutputPass
composer.addPass(lutPass);            // LUT after OutputPass
```
Omitting `OutputPass` = dark, linear, un-tone-mapped image. Two `OutputPass`es or `GammaCorrectionShader` + OutputPass = double-gamma washed-out image.

WebGLRenderer built-in effect chain (r186, lighter than EffectComposer; OutputPass NOT needed, it warns):
```js
const renderer = new THREE.WebGLRenderer({ antialias: true, outputBufferType: THREE.HalfFloatType }); // required
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.setEffects([bloomPass]);   // passes with render(renderer, writeBuffer, readBuffer, dt); first may be a RenderPass/TAARenderPass
renderer.render(scene, camera);     // no composer.render()
renderer.setEffects(null);          // disable
```
Scene is MSAA'd (antialias -> 4 samples), effects ping-pong in single-sampled half-float targets, final blit applies tone mapping + output color space. Examples: `webgl_shaders_ocean`, `webgl_watch`.

WebGPURenderer, `RenderPipeline` (`PostProcessing` is the deprecated pre-r183 alias; do not use):
```js
import * as THREE from 'three/webgpu';
import { pass, renderOutput } from 'three/tsl';
import { bloom } from 'three/addons/tsl/display/BloomNode.js';
import { fxaa } from 'three/addons/tsl/display/FXAANode.js';

renderer.toneMapping = THREE.ACESFilmicToneMapping;
const rp = new THREE.RenderPipeline(renderer);
const scenePass = pass(scene, camera);
const color = scenePass.getTextureNode('output');

// A) default: tone mapping + sRGB are appended automatically after outputNode
rp.outputNode = color.add(bloom(color, 0.6, 0.5, 0.9)); // bloom(node, strength, radius, threshold)

// B) manual: effects needing display-referred input
rp.outputColorTransform = false;                // you now own the transform
rp.outputNode = fxaa(renderOutput(color.add(bloom(color)))); // renderOutput(node[, toneMapping, outputColorSpace])
// chain form also exists: someNode.renderOutput()

function loop() { rp.render(); }               // not renderer.render
```
`rp.needsUpdate = true` after replacing `outputNode`. `renderAsync()` is deprecated; `render()` is enough after `await renderer.init()`.

## 8. LUT color grading
Grade in display space: apply AFTER tone mapping/sRGB. A 3D LUT is a display-referred creative look (teal-orange, bleach bypass, night).

WebGL:
```js
import { LUTCubeLoader } from 'three/addons/loaders/LUTCubeLoader.js'; // also LUT3dlLoader, LUTImageLoader (png strip)
const lutPass = new LUTPass();            // fields: .lut (Data3DTexture), .intensity (0..1)
composer.addPass(new OutputPass());
composer.addPass(lutPass);
new LUTCubeLoader().load('look.CUBE', (r) => { lutPass.lut = r.texture3D; lutPass.intensity = 0.8; });
```
Loader result has `.texture3D` (and `.size`). `LUTCubeLoader.setType(FloatType|UnsignedByteType)`. Example `webgl_postprocessing_3dlut`.

WebGPU:
```js
import { lut3D } from 'three/addons/tsl/display/Lut3DNode.js';
import { texture3D, uniform, pass, renderOutput } from 'three/tsl';
rp.outputColorTransform = false;
const out = renderOutput(pass(scene, camera));
const lutNode = lut3D(out, texture3D(lut.texture3D), lut.texture3D.image.width, uniform(1)); // (node, lut, size, intensity)
rp.outputNode = lutNode;               // lutNode.intensityNode.value to animate
```
Example `webgpu_postprocessing_3dlut`. Keep intensity 0.5-1.0; strong LUTs on top of ACES double-contrast the image.

## 9. Deprecated / removed
- `renderer.outputEncoding`, `THREE.sRGBEncoding`, `LinearEncoding`: removed; use `outputColorSpace`, `texture.colorSpace`.
- `renderer.physicallyCorrectLights` and `useLegacyLights`: removed; physical units always on.
- `GammaCorrectionShader`: still shipped; superseded by `OutputPass` (tone mapping + color space). Do not combine.
- `ColorManagement.fromWorkingColorSpace/toWorkingColorSpace` -> `workingToColorSpace/colorSpaceToWorking`.
- `PostProcessing` (WebGPU) -> `RenderPipeline` (r183). `Clock` -> `Timer` (r183).
- `PCFSoftShadowMap`: removed, falls back to `PCFShadowMap` with a warning.

## 10. Debugging washed-out / too-dark
| Symptom | Cause | Fix |
|---|---|---|
| Everything dark, high contrast, colors too saturated | Output stage missing (composer without `OutputPass`, or ShaderMaterial without `colorspace_fragment`) | Add `OutputPass` / include chunk |
| Everything pale, low contrast | sRGB applied twice (OutputPass + GammaCorrectionShader, or `renderOutput` + default transform) | Remove one; set `rp.outputColorTransform = false` when using `renderOutput` manually |
| One object too dark | albedo texture missing `SRGBColorSpace` | set `colorSpace` before first render |
| One object too bright/pale | normal/roughness map tagged sRGB, or albedo double-decoded | `NoColorSpace` for data maps |
| Hex color looks different from CSS | Passed through `setRGB` without space, or `ColorManagement.enabled=false` | `new Color(hex)` / `setRGB(...,SRGBColorSpace)` |
| Highlights clip to flat white | no tone mapping, lights too strong | `NeutralToneMapping`/`AgX` + lower exposure |
| Banding in dark gradients / bloom stepping | 8-bit buffer | `outputBufferType: HalfFloatType` (WebGL) |
| Fog/background color off | `scene.background` set from texture without `SRGBColorSpace` | tag the texture |
| Matches in editor, not in three | file not glTF 2.0, or viewer used a different tone map | test in glTF viewer, match `toneMapping` |

Diagnostics: set `renderer.toneMapping = NoToneMapping` to isolate tone mapping; swap the albedo into `MeshBasicMaterial({ map, toneMapped:false })` - it must look identical to the source image (if not, the texture is mis-tagged).

## See also
- `../threejs/references/api/ColorManagement` (see `module-ColorSpaces.md`, `Color.md`), `WebGLRenderer.md`, `Renderer.md`, `WebGPURenderer.md`, `RenderPipeline.md`, `RenderOutputNode.md`, `ToneMappingNode.md`, `ColorSpaceNode.md`, `OutputPass.md`, `EffectComposer.md`, `LUTPass.md`, `LUTCubeLoader.md`, `LUT3dlLoader.md`, `LUTImageLoader.md`, `Lut3DNode.md`, `Texture.md`, `Material.md` (toneMapped), `module-GammaCorrectionShader.md`, `module-ColorSpaces.md`
  (path form: `../threejs/references/api/<Name>.md`)
- Examples: `webgl_tonemapping`, `webgpu_tonemapping`, `webgl_test_wide_gamut`, `webgpu_hdr`, `webgl_postprocessing_3dlut`, `webgpu_postprocessing_3dlut`, `webgpu_postprocessing_fxaa`, `webgl_loader_gltf`
- Manual: https://threejs.org/manual/en/color-management , https://threejs.org/manual/en/webgpu-postprocessing , https://threejs.org/manual/en/how-to-use-post-processing
