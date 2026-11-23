---
name: threejs-visual-quality
description: Make three.js (r187) scenes look professional, realistic or cinematic: correct color/tone-mapping pipeline, PBR materials (MeshPhysicalMaterial clearcoat, transmission, sheen, iridescence), HDR environment lighting and PMREM, studio and sun lighting setups, shadow quality (CSM, VSM, contact shadows), anti-aliasing (MSAA/FXAA/SMAA/TAA/TRAA), post-processing stacks (bloom, GTAO, SSR, SSGI, DOF, LUT grading, film grain, god rays) for both WebGLRenderer (EffectComposer) and WebGPURenderer (RenderPipeline nodes), sky, water, fog and atmosphere. Use whenever a user says a scene looks flat, washed out, too dark, plastic, fake, "like a demo", or asks for "realistic", "photoreal", "beautiful", "AAA", "cinematic", "product viewer", "architectural", "glass", "car paint", "glow", "depth of field", "ambient occlusion", "HDRI", "environment map", "skybox", or wants a polished portfolio-quality scene. Pair with the `threejs` core skill and `threejs-performance` to keep it fast.
---

# three.js r187 visual quality

Most three.js scenes look amateur for pipeline reasons, not material reasons. Fix the pipeline in this order, each step is a bigger win than everything after it: color/tone mapping → environment lighting → material correctness → shadows → anti-aliasing → post-processing → atmosphere. Do not tweak `roughness` sliders on a scene with no environment map.

## The baseline every good-looking scene has

```js
import * as THREE from 'three';   // or 'three/webgpu'
import { HDRLoader } from 'three/addons/loaders/HDRLoader.js';   // RGBELoader is the deprecated name
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';

renderer.toneMapping = THREE.ACESFilmicToneMapping;   // or AgXToneMapping / NeutralToneMapping (product shots)
renderer.toneMappingExposure = 1.0;
renderer.outputColorSpace = THREE.SRGBColorSpace;     // default; stated for clarity
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.VSMShadowMap;          // soft; PCFShadowMap is the default. PCFSoftShadowMap is a deprecated constant: setting it logs "has been removed" and falls back to PCFShadowMap

// Environment lighting: this is what makes PBR materials read as real
const pmrem = new THREE.PMREMGenerator(renderer);
scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;   // studio, no file needed
// or an HDRI:
const hdr = await new HDRLoader().loadAsync('studio.hdr');
hdr.mapping = THREE.EquirectangularReflectionMapping;
scene.environment = hdr;            // IBL (renderer builds PMREM lazily)
scene.background = hdr;             // optional; scene.backgroundBlurriness = 0.5 for product shots
scene.environmentIntensity = 1.0;   // scene.environmentRotation / backgroundRotation to orient the sun
pmrem.dispose();

// One key light with shadows, matched to the HDRI's sun direction
const sun = new THREE.DirectionalLight(0xfff2e0, 3);
sun.position.set(5, 10, 4);
sun.castShadow = true;
sun.shadow.mapSize.set(2048, 2048);
sun.shadow.bias = -0.0002; sun.shadow.normalBias = 0.02; sun.shadow.radius = 4;   // radius applies to VSM/PCF blur
Object.assign(sun.shadow.camera, { left: -10, right: 10, top: 10, bottom: -10, near: 1, far: 40 });
scene.add(sun);
```

Texture rules: color/albedo/emissive maps `texture.colorSpace = THREE.SRGBColorSpace`; normal/roughness/metalness/AO/height maps stay `NoColorSpace` (linear). glTF loader handles this. `texture.anisotropy = renderer.capabilities.getMaxAnisotropy()` (WebGL) for ground planes seen at grazing angles. Never set `material.toneMapped = false` except for UI/overlays.

## Tone mapping modes (r187 constants)

`NoToneMapping`, `LinearToneMapping`, `ReinhardToneMapping`, `CineonToneMapping`, `ACESFilmicToneMapping` (classic filmic, desaturates brights), `AgXToneMapping` (modern filmic, best highlight rolloff, slightly lower contrast), `NeutralToneMapping` (Khronos PBR Neutral, preserves colors for e-commerce), `CustomToneMapping`. Exposure 0.6-1.5 typical. With post-processing, tone mapping happens in `OutputPass` (WebGL) or at the end of `RenderPipeline` via `outputColorTransform`/`renderOutput()` (WebGPU), not during the scene pass.

## The ten things that make a scene look amateur (and the fix)

1. No environment map → lit by a single light: black reflections, plastic look. Fix: `scene.environment` (RoomEnvironment or HDRI).
2. Washed-out or neon colors → color textures not sRGB or double-converted. Fix: `colorSpace` on color maps only.
3. Flat lighting → only `AmbientLight` + one `DirectionalLight` at intensity 1. Fix: key + fill + rim (or HDRI + key), physical intensities (directional 2-5, hemisphere 1-3, point/spot in candela, `decay = 2`).
4. Hard, aliased, acne-ridden shadows → default 512 map, huge frustum. Fix: tight frustum, 2048 map, `normalBias`, VSM + `radius`, or CSM for large terrains, contact shadows for product shots. Edges that crawl while the camera moves are shadow shimmer: stabilize the shadow camera (CSM and SunLight snap to texels for you; manual snap code in `references/shadows-and-antialiasing.md`), separately from anti-aliasing.
5. Jaggy edges and shimmering → no AA, or `antialias` ignored because of `EffectComposer`. Fix: MSAA (`antialias: true`, `samples` on composer target) or TRAA/FXAA/SMAA passes.
6. Everything is `roughness: 0.5, metalness: 0.5` → dull. Fix: use real PBR ranges: dielectrics metalness 0, roughness 0.2-0.8 with a roughness map; metals metalness 1 and tinted base color; add normal maps for micro detail.
7. Glass that is just `transparent: true, opacity: 0.5` → fake. Fix: `MeshPhysicalMaterial` with `transmission: 1, thickness, ior: 1.5, roughness ≤ 0.2`, env map, optional `dispersion`.
8. Floating objects → no contact shadow or AO. Fix: GTAO pass, baked AO map, ground `ShadowMaterial` plane, contact shadow technique.
9. Flat, 8-bit looking render → no bloom on emissives, no subtle grain/vignette, no depth cue. Fix: `UnrealBloomPass`/`bloom()` on emissive-only (MRT on WebGPU), slight `FilmPass`/`film()`, `FogExp2` or height fog, DOF for hero shots.
10. Background sticks out → solid `0x000000` or a mismatched JPEG. Fix: blurred HDRI (`backgroundBlurriness`), `Sky` with sun position synced to the key light, or a gradient + fog matched color.

## Post-processing stack cheat sheet

| Goal | WebGLRenderer (`three/addons/postprocessing/*`) | WebGPURenderer (`three/addons/tsl/display/*`, `three/tsl`) |
|---|---|---|
| Pipeline | New in r186: `new WebGLRenderer({ outputBufferType: THREE.HalfFloatType })` + `renderer.setEffects([bloomPass, taaPass])` (passes from `three/addons/postprocessing`, tone map + sRGB applied by the renderer, no composer; `setEffects(null)` to clear). Classic: `EffectComposer` → `RenderPass` → effects → `OutputPass` last | `RenderPipeline` (`PostProcessing` is the deprecated alias) with `pass(scene, camera)` → nodes → `outputColorTransform` |
| Bloom | `UnrealBloomPass(res, strength 0.3-1, radius 0.2-0.8, threshold 0.8-1)`; bloom ONLY on chosen objects needs layers + a second composer (`webgl_postprocessing_unreal_bloom_selective`), a threshold alone also blooms speculars | `bloom(node, strength, radius, threshold)`; selective via `mrt({ output, emissive })` |
| AO | `GTAOPass` (best), `SSAOPass`/`SAOPass` (older) | `ao(depth, normal, camera)` from `GTAONode.js` + `denoise()`, `ssao()` |
| Reflections / GI | `SSRPass` | `ssr()`, `ssgi()`, VXGI (`three/addons/lighting/vxgi/`) |
| Depth of field | `BokehPass({ focus, aperture, maxblur })` | `dof(color, viewZ, focusDistance, focalLength, bokehScale)` |
| Anti-aliasing | MSAA via `samples` on the composer's render target; `FXAAPass`, `SMAAPass`, `TAARenderPass`, `SSAARenderPass` | `antialias: true` (MSAA), `fxaa()`, `smaa()`, `traa()` (needs `velocity` MRT), `ssaaPass()`, `taau()`, `fsr1()` |
| Grade / grain | `LUTPass` + `LUTCubeLoader`, `FilmPass` | `lut3D()`, `film()`, `sepia()`, `bleach()`, CRT helpers (`scanlines`, `vignette`, `barrelUV`) |
| Motion blur / god rays / outline / lens flare | `AfterimagePass`, `OutlinePass`, `Lensflare` object | `motionBlur()` (velocity MRT), `godrays()`, `outline()`, `LensflareMesh` / `lensflare` node |

Order that works: render (MRT) → AO → SSR/SSGI → bloom → DOF → motion blur → tone map/output → LUT → grain/vignette → AA (if not MSAA/TRAA earlier). Cost ranking high→low: SSGI, SSR, DOF (full res), GTAO, TRAA, bloom, FXAA, LUT, film.

## Reference map

| Need | Read |
|---|---|
| Color pipeline end to end, every tone mapping mode with when-to-use, exposure, LUT grading, HDR output, debugging washed-out/dark scenes | `references/color-and-tone-mapping.md` |
| PBR that convinces: value ranges, every MeshPhysicalMaterial feature with cost, HDRI/PMREM/RoomEnvironment, studio 3-point and sun setups with numbers, glTF best practices, product-viewer and exterior starter recipes | `references/pbr-materials-and-environment.md` |
| Shadow types compared, CSM (WebGL + WebGPU), contact shadows, baked lighting, acne fixes, every AA option with quality/cost table | `references/shadows-and-antialiasing.md` |
| Both post-processing pipelines side by side with sensible defaults per effect, fog/height fog, Sky, Water, reflections, refraction/backdrop, particles, volumes, three complete stacks (product, stylized, cinematic) | `references/post-processing-and-atmosphere.md` |
| API page for any class (`MeshPhysicalMaterial`, `PMREMGenerator`, `Sky`, `UnrealBloomPass`, `GTAONode`...) | `python3 ../threejs/scripts/api.py <Name>` |
| TSL syntax for custom looks (fresnel, stylized shading, custom fog) | `../threejs-tsl-webgpu/SKILL.md` |

Examples to copy from (`https://threejs.org/examples/#<name>`): `webgl_loader_gltf` (the reference realism setup), `webgl_materials_physical_transmission`, `webgl_materials_physical_clearcoat`, `webgl_materials_envmaps_hdr`, `webgl_tonemapping`, `webgl_shadowmap_csm`, `webgl_shadow_contact`, `webgl_postprocessing_unreal_bloom`, `webgl_postprocessing_gtao`, `webgl_shaders_sky`, `webgpu_postprocessing_bloom_emissive`, `webgpu_postprocessing_ao`, `webgpu_postprocessing_ssr`, `webgpu_postprocessing_traa`, `webgpu_postprocessing_dof`, `webgpu_sky`, `webgpu_ocean`, `webgpu_materials_sss`, `webgpu_backdrop`.

## Working method

1. Ask for or infer the target: product shot, architectural, game/stylized, data viz, cinematic. Each has a different default stack (see the three stacks in the atmosphere reference).
2. Apply the baseline block above first and show the user the before/after reasoning (environment + tone mapping fix 80% of complaints).
3. Then materials: correct colorSpace, PBR ranges, physical features only where they pay off.
4. Then shadows and AA with their budgets from `threejs-performance`.
5. Add post-processing last, one effect at a time, with conservative defaults; bloom threshold near 1 so only emissives glow.
6. Keep both renderers in mind: give WebGL code unless the user is on `three/webgpu`; never hand WebGPU node effects to an `EffectComposer` user or vice versa.
