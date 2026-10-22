---
name: threejs
description: Expert three.js (r186 / three@0.186.x) knowledge with the complete official API docs, manual and examples catalog bundled offline. Use this skill for ANY task that touches three.js, 3D on the web, WebGL/WebGPU rendering in the browser, scenes, meshes, cameras, lights, shadows, materials, textures, glTF/GLB/FBX/OBJ loading, OrbitControls, raycasting/picking, animation mixers, BufferGeometry, render targets, CSS2D/3D labels, WebXR, or debugging a black/blank canvas. Trigger even when the user only says "3D", "three", "THREE.", "r3f", "scene", "mesh", "glb" or pastes three.js code without naming the library. For TSL shaders, node materials, compute or WebGPURenderer specifics also load threejs-tsl-webgpu; for FPS/memory problems load threejs-performance; for "make it look good/realistic/cinematic" load threejs-visual-quality.
---

# three.js r186 core skill

You know three.js inside out, but memory of three.js is the most version-sensitive knowledge on the web: APIs you remember from r120-r160 are often renamed or removed. This skill pins you to **r186 (npm `three@0.186.1`, Oct 2026)** and ships the full official documentation offline so you verify instead of guessing.

## Version facts (r186)

- Monthly releases; `0.186.x` is current stable, r187 in development. `import { REVISION } from 'three'` gives `'186'`.
- Package entry points (`package.json` exports): `three` (WebGL build `three.module.js`), `three/webgpu` (WebGPURenderer + node materials), `three/tsl` (shading language functions), `three/addons/*` = `three/examples/jsm/*`. Both renderer builds share `three.core.js`; never import from both `three` and `three/webgpu` in one app (duplicate class instances, `instanceof` breaks).
- No TypeScript types in the package: `npm i -D @types/three`.
- Color management is on by default: working space linear-sRGB, `renderer.outputColorSpace = SRGBColorSpace` default, color textures need `texture.colorSpace = THREE.SRGBColorSpace` (glTF loader does this for you). Light intensities are physical (candela/lux-ish); `useLegacyLights`, `physicallyCorrectLights`, `outputEncoding`, `sRGBEncoding`, `Geometry`, `examples/js` are gone. Full list: `references/versions-and-migration.md`.

## Renderer decision (first thing to decide)

| Need | Use |
|---|---|
| Plain scene, max compatibility, GLSL `ShaderMaterial`/`onBeforeCompile`, `EffectComposer` or the r186 `renderer.setEffects([...])` pass chain | `WebGLRenderer` from `three` |
| Custom shaders without GLSL strings, compute shaders, modern post-processing (SSGI, TRAA, DOF), MRT, many lights, future-proof | `WebGPURenderer` from `three/webgpu` (auto-falls back to a WebGL 2 backend; `forceWebGL: true` to test) |

WebGPURenderer rules: it initializes async. Use `renderer.setAnimationLoop(fn)` (waits for init automatically) or `await renderer.init()` before manual rendering. `ShaderMaterial`, `RawShaderMaterial`, `onBeforeCompile`, `EffectComposer` do not work there; use `*NodeMaterial` + TSL and the `RenderPipeline` class (named `PostProcessing` before r183) (see skill `threejs-tsl-webgpu`). The project's development focus is WebGPURenderer; WebGLRenderer is maintained but receives no large new features.

## Starter patterns

Import map (no bundler), pinned version:

```html
<script type="importmap">
{ "imports": {
  "three": "https://cdn.jsdelivr.net/npm/three@0.186.1/build/three.module.js",
  "three/webgpu": "https://cdn.jsdelivr.net/npm/three@0.186.1/build/three.webgpu.js",
  "three/tsl": "https://cdn.jsdelivr.net/npm/three@0.186.1/build/three.tsl.js",
  "three/addons/": "https://cdn.jsdelivr.net/npm/three@0.186.1/examples/jsm/"
} }
</script>
```

Minimal app (works for both renderers; swap the two marked lines):

```js
import * as THREE from 'three';                 // or 'three/webgpu'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

const renderer = new THREE.WebGLRenderer({ antialias: true }); // or THREE.WebGPURenderer
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.setSize(innerWidth, innerHeight);
renderer.toneMapping = THREE.ACESFilmicToneMapping;
document.body.append(renderer.domElement);

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(50, innerWidth / innerHeight, 0.1, 100);
camera.position.set(3, 2, 5);
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;

scene.add(new THREE.HemisphereLight(0xffffff, 0x444444, 2));
const sun = new THREE.DirectionalLight(0xffffff, 3);
sun.position.set(5, 10, 5);
scene.add(sun);
scene.add(new THREE.Mesh(new THREE.BoxGeometry(), new THREE.MeshStandardMaterial({ color: 0x4488ff })));

addEventListener('resize', () => {
  camera.aspect = innerWidth / innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight);
});

renderer.setAnimationLoop(() => { controls.update(); renderer.render(scene, camera); });
```

Vite: `npm i three` + `npm i -D @types/three vite`; same imports. Decoders (Draco, Basis/KTX2) live in `node_modules/three/examples/jsm/libs/`; copy to `public/` or point at the jsdelivr path.

## Working rules

1. **Verify before you write.** Any class, method or option you are not 100% sure exists in r186: run `python3 scripts/api.py <Name>` (full doc page) or `python3 scripts/api.py -s <keyword>` (search index). The index lists all 826 documented classes with category and one-line description. Prefer this over web fetches; threejs.org/docs is the same content.
2. **Imports**: core from `three`, everything in `examples/jsm` from `three/addons/...` (controls, loaders, post-processing, helpers, `Line2`, `Sky`, `Water`, CSM, `stats.module.js` in `three/addons/libs/`).
3. **Resource lifecycle**: everything that owns GPU memory has `.dispose()` (geometry, material, texture, render target, controls, renderer). Removing from scene does not free it. Check `renderer.info.memory`.
4. **needsUpdate matrix**: BufferAttribute data change → `attribute.needsUpdate = true` (size changes need a new attribute). Material defines/maps added after first render → `material.needsUpdate = true`. Texture image replaced → `texture.needsUpdate = true`. Transforms are automatic (`matrixAutoUpdate`).
5. **Units & conventions**: Y up, right-handed, meters, radians (`THREE.MathUtils.degToRad`), rotation order XYZ Euler, camera looks down -Z. Color hex/setters are sRGB; `Color` stores linear.
6. **Loop**: use `renderer.setAnimationLoop` (required for XR, handles WebGPU init). Use `THREE.Timer` (core class; `timer.update()` each frame, `getDelta()`, `timer.connect(document)` to pause on hidden tabs). `Clock` is deprecated since r183 and warns.
7. **Resize**: update `camera.aspect`, `camera.updateProjectionMatrix()`, `renderer.setSize(w, h)`; for post-processing also `composer.setSize`. Use `ResizeObserver` for non-fullscreen canvases.
8. **Shadows**: `renderer.shadowMap.enabled = true`, light `castShadow`, mesh `castShadow`/`receiveShadow`, fit `light.shadow.camera` tightly, `mapSize` 1024-2048, tune `bias`/`normalBias`. Types: `PCFShadowMap` (default), `VSMShadowMap`, `BasicShadowMap`; `PCFSoftShadowMap` was removed (the constant remains but WebGLRenderer logs a warning and uses PCF). Use `light.shadow.radius` with VSM for soft edges.
9. **glTF is the asset format.** `GLTFLoader` + `DRACOLoader` + `KTX2Loader` + `MeshoptDecoder`; result in `gltf.scene`, `gltf.animations`. Clone skinned meshes with `SkeletonUtils.clone`.
10. **Transparency** is the number one visual bug source: `transparent: true`, `depthWrite: false` for blended particles, `alphaTest`/`alphaHash` for cutouts, sort with `renderOrder`.

## Reference map (read what the task needs)

| Topic | File |
|---|---|
| App structure, scene graph, cameras, primitives, textures basics, fog, render targets, matrices, update rules | `references/fundamentals.md` |
| BufferGeometry, attributes, instancing buffers, curves/shapes/extrude/text, lines/points, fat lines | `references/geometry.md` |
| All materials and every map slot, PBR props, ShaderMaterial, NodeMaterial equivalence, transparency | `references/materials.md` |
| Lights, physical units, shadows (all types, CSM), environment maps, PMREM, light probes | `references/lighting-shadows.md` |
| Loaders (glTF canonical setup, Draco/KTX2/meshopt, HDR/EXR, OBJ/FBX, splats), exporters, LoadingManager, caching | `references/loaders-assets.md` |
| AnimationMixer, clips, blending, skinning, morph targets, IK, retargeting | `references/animation.md` |
| Controls (every class), raycasting/picking, GPU picking, CSS2D/CSS3D, input, TransformControls | `references/controls-interaction.md` |
| Backgrounds/skybox, transparency, multiple scenes/canvases, billboards, canvas textures, text, Shadertoy port, disposal, debugging, screenshots, common errors | `references/recipes.md` |
| WebXR (VR/AR, controllers, hands, hit test) and audio | `references/xr-audio.md` |
| Version facts, outdated → modern table, per-release changelog r150-r186, r187 preview | `references/versions-and-migration.md` |
| Every documented class, one line each (`category | Name (extends) | description`) | `references/api-index.txt` |
| Full doc page per class (826 files) | `references/api/<Name>.md` via `scripts/api.py` |
| All ~600 official examples by category (`https://threejs.org/examples/#<name>`) | `references/examples-index.md` |

Sibling skills in this repo (load when relevant):
- `threejs-tsl-webgpu`: TSL language cheat sheet, the full TSL function reference, official TSL guide (82 sections), node materials, WebGPURenderer API, compute shaders, node post-processing, WebGPU examples catalog.
- `threejs-performance`: draw calls (InstancedMesh/BatchedMesh/LOD/merge), textures & memory, rendering strategies (on-demand, OffscreenCanvas, shadows budget), shader/WebGPU perf, profiling.
- `threejs-visual-quality`: color/tone mapping pipeline, PBR materials + environment lighting, shadow quality & anti-aliasing, post-processing stacks and atmosphere for both renderers.

## Workflow for a three.js task

1. Decide renderer (table above) and state it. If the user has existing code, match their renderer; do not silently migrate.
2. Pull the relevant reference file(s) from the map; for any API detail run `scripts/api.py`.
3. Write complete, runnable code: imports, resize handler, animation loop, disposal where objects are created dynamically. Pin `three@0.186.1` in import maps.
4. For visual work, apply the lighting/color defaults (tone mapping, environment map, sRGB textures) before tweaking materials; most "looks flat/wrong" issues are pipeline issues.
5. Run the same scrutiny on the output as a code reviewer who knows r186: deprecated names, missing `needsUpdate`, missing `dispose`, WebGPU-only APIs used with WebGLRenderer (or `ShaderMaterial` with WebGPURenderer), `three` and `three/webgpu` mixed.

## Quick debugging checklist

- Blank canvas: camera inside/behind object (`near`/`far`, position), no light with lit material (`MeshStandardMaterial` is black without lights/environment), object not added to scene, renderer size 0 (canvas CSS), WebGPURenderer rendered before init.
- Texture not showing: path (404 in network tab), `colorSpace`, missing UVs, `material.needsUpdate` after assigning `map` post-compile, flipY for non-glTF data textures.
- Model too dark/too bright: no `scene.environment`, wrong tone mapping/exposure, light intensities from old tutorials (multiply by ~3 for directional/hemisphere, use ~`Math.PI` for old `1`).
- Shadows missing: `shadowMap.enabled`, `castShadow` on light and mesh, `receiveShadow` on ground, shadow camera frustum too small (`CameraHelper(light.shadow.camera)`).
- Blurry: `setPixelRatio`, `setSize(w, h, false)` when CSS controls size.
- Jank: see `threejs-performance`.
