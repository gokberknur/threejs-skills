# Recipes: scene starter, common errors, and how-to patterns

When to read this: you need a working minimal setup, a quick diagnosis for a blank/black/wrong render, or a self-contained pattern for backgrounds, transparency, multi-view rendering, billboards, canvas textures, text, lines, HTML labels, Shadertoy ports, basic post-processing, disposal, debugging, screenshots, game-loop structure, or the "what needs `needsUpdate`" matrix. Lighting/shadows/environment lives in `lighting-shadows.md`; deep post-processing, picking, rendering-on-demand and OffscreenCanvas have their own references (short cross-refs below).

Version: three r186 (npm `three@0.186.1`).

## Contents
1. Scene setup starter (Vite, import map CDN, WebGPURenderer)
2. Common errors table
3. Backgrounds and skyboxes
4. Transparency
5. Multiple scenes / multiple canvases
6. Billboards and facades
7. Canvas textures
8. Creating text
9. Drawing lines
10. Aligning HTML elements to 3D
11. Shadertoy shaders
12. Post-processing basics
13. Picking, rendering on demand, OffscreenCanvas (cross-refs)
14. Cleanup and disposal
15. Debugging JavaScript and GLSL
16. Tips: screenshot, no-clear, keyboard, transparent canvas, page background
17. Game structure
18. How to update things (needsUpdate matrix)
19. Uniform types
20. See also

---

## 1. Scene setup starter

### Vite (recommended)
```bash
npm install three && npm install -D vite && npx vite
```
`index.html`: `<body style="margin:0"><script type="module" src="/main.js"></script></body>`

```js
// main.js
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.setSize(innerWidth, innerHeight);
document.body.appendChild(renderer.domElement);

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(60, innerWidth / innerHeight, 0.1, 100);
camera.position.set(2, 2, 4);
const controls = new OrbitControls(camera, renderer.domElement);

scene.add(new THREE.Mesh(new THREE.BoxGeometry(), new THREE.MeshStandardMaterial({ color: 0x44aa88 })));
scene.add(new THREE.HemisphereLight(0xffffff, 0x444444, 2), new THREE.DirectionalLight(0xffffff, 3));

addEventListener('resize', () => {
  camera.aspect = innerWidth / innerHeight;
  camera.updateProjectionMatrix();          // required after changing aspect/fov/near/far
  renderer.setSize(innerWidth, innerHeight);
});
renderer.setAnimationLoop(() => { controls.update(); renderer.render(scene, camera); });
```

### Import map from CDN (no build step; needs a local server, e.g. `npx serve .`)
```html
<script type="importmap">
{ "imports": {
  "three": "https://cdn.jsdelivr.net/npm/three@0.186.1/build/three.module.js",
  "three/addons/": "https://cdn.jsdelivr.net/npm/three@0.186.1/examples/jsm/"
} }
</script>
<script type="module" src="main.js"></script>
```
Alternative CDN host: `https://unpkg.com/three@0.186.1/build/three.module.js` and `https://unpkg.com/three@0.186.1/examples/jsm/`. Use one version and one CDN for everything (mixing duplicates the library and breaks `instanceof`). For WebGPU/TSL import from `three/webgpu` and `three/tsl` (package exports map to `build/three.webgpu.js` and `build/three.tsl.js`); with an import map add `"three/webgpu": ".../build/three.webgpu.js"` and `"three/tsl": ".../build/three.tsl.js"`. Do not mix `three` and `three/webgpu` classes in one app: import everything from `three/webgpu` (it re-exports core).

### WebGPURenderer (async init)
```js
import * as THREE from 'three/webgpu';
const renderer = new THREE.WebGPURenderer({ antialias: true });   // WebGPU backend, falls back to WebGL2; forceWebGL: true to force fallback
await renderer.init();                    // REQUIRED before renderer.render(); else it throws
renderer.setAnimationLoop(() => renderer.render(scene, camera)); // setAnimationLoop awaits init itself
```
`render()` before init throws `THREE.Renderer: .render() called before the backend is initialized`. `renderAsync()` / `clearAsync()` are deprecated (r181): use `await renderer.init()` once, then sync `render()`. `PostProcessing` is renamed `RenderPipeline` (deprecated r183). `Clock` is deprecated (r183): use `THREE.Timer`.

### Resize helper (HiDPI-correct, avoids blur)
```js
function resize(renderer, camera) {
  const c = renderer.domElement, w = c.clientWidth, h = c.clientHeight;   // CSS pixels
  if (c.width !== w * renderer.getPixelRatio() || c.height !== h * renderer.getPixelRatio()) {
    renderer.setSize(w, h, false);        // false = do not touch canvas CSS size (let CSS drive it)
    camera.aspect = w / h; camera.updateProjectionMatrix();
  }
}
```
Set CSS `canvas{width:100%;height:100%;display:block}`; call from the loop. `setSize` multiplies by the pixel ratio internally; never pass `clientWidth*dpr`.

---

## 2. Common errors

| Symptom | Likely causes / fix |
|---|---|
| Black screen, no errors | Never called `render`; camera inside/behind object or `near/far` clip it; no lights with Standard/Phong/Lambert materials (use `MeshBasicMaterial` to test); canvas has 0 size (CSS height 0); NaN in transforms (check `matrixWorld`); object scale 0; `camera.lookAt` target == position. |
| Black screen with WebGPURenderer | `render()` before `await renderer.init()` (throws) ; or imported WebGL classes from `three` in a TSL/node setup (use `three/webgpu`); WebGPU unavailable and `forceWebGL` ignored by browser flags. |
| Texture not showing | Image not loaded yet (use loader callback or `await loadAsync`); wrong path (404 in network tab); no UVs on custom geometry; `colorSpace` not set (looks washed out, not missing); material `side` culls plane; needs lights (non-Basic material); `texture.needsUpdate = true` missing for Canvas/Data/Video textures changed at runtime; non-power-of-two with `repeat` needs `wrapS/T = RepeatWrapping`. |
| Texture looks washed-out / too dark | Color textures (`map`, `emissiveMap`, `matcap`) need `texture.colorSpace = THREE.SRGBColorSpace`; data textures (normal, roughness, metalness, AO, bump, displacement) stay `NoColorSpace`. |
| Shadow not appearing | `renderer.shadowMap.enabled = true`; `light.castShadow = true`; `mesh.castShadow` on casters and `mesh.receiveShadow` on receivers; shadow camera frustum doesn't cover the casters (see `lighting-shadows.md`); `MeshBasicMaterial` ignores lights/shadows; light type unsupported (AmbientLight/HemisphereLight/LightProbe/RectAreaLight cast no shadows). |
| GLTF too dark | No lights and no `scene.environment`: PBR needs light. Add an environment (`RoomEnvironment` via PMREM, or HDR) and/or lights; check `renderer.toneMapping`/`toneMappingExposure`. |
| GLTF too bright / blown out | Legacy-style light intensities (physical units since r155: `useLegacyLights` removed); environment plus several lights double-lit; remove duplicates; `scene.environmentIntensity`; set `toneMapping = THREE.ACESFilmicToneMapping`, lower `toneMappingExposure`. |
| Blurry canvas | Canvas drawing buffer size != display size or ignoring pixel ratio. Use the resize helper; `renderer.setPixelRatio(Math.min(devicePixelRatio, 2))`. |
| Stretched image after resize | Forgot `camera.aspect = w/h; camera.updateProjectionMatrix()`. |
| Z-fighting / flicker | Raise `near` (0.1 not 0.0001), reduce `far`; use `logarithmicDepthBuffer: true` in WebGLRenderer ctor for huge ranges (cost: no early-z); offset coplanar surfaces with `material.polygonOffset`. |
| Transparent object hides things / wrong order | See section 4 (`depthWrite`, sorting, `renderOrder`). |
| Memory climbs when swapping content | Removing from the scene does not free GPU memory: `dispose()` geometry/material/texture/render target (section 14). |
| Model appears but is invisible from inside | `side: THREE.BackSide`/`DoubleSide` for interior surfaces and skybox meshes. |
| Controls do nothing | `controls.update()` not called when `enableDamping`/`autoRotate`; controls bound to wrong element; overlay element catches pointer events. |
| Keyboard events dead on canvas | Canvas needs `tabindex="0"` (section 16). |

---

## 3. Backgrounds and skyboxes

`Scene` properties (all verified in `src/scenes/Scene.js`): `background` (Color | Texture | CubeTexture | null), `environment` (Texture | null), `backgroundBlurriness` (0..1), `backgroundIntensity` (1), `backgroundRotation` (Euler), `environmentIntensity` (1), `environmentRotation` (Euler).

`scene.background` is only what is *seen*; `scene.environment` is what *lights* PBR materials (IBL). They are independent: set both from the same HDR for a consistent look.

```js
scene.background = new THREE.Color('skyblue');                 // solid
// Plain image (stretched to viewport, drawn by three so post-processing affects it)
const tex = new THREE.TextureLoader().load('bg.jpg');
tex.colorSpace = THREE.SRGBColorSpace;
scene.background = tex;
// keep aspect: on each frame (and after load) set texture.repeat/offset:
const canvasAspect = canvas.clientWidth / canvas.clientHeight;
const imageAspect = tex.image ? tex.image.width / tex.image.height : 1;
const a = imageAspect / canvasAspect;
tex.offset.x = a > 1 ? (1 - 1 / a) / 2 : 0;  tex.repeat.x = a > 1 ? 1 / a : 1;
tex.offset.y = a > 1 ? 0 : (1 - a) / 2;      tex.repeat.y = a > 1 ? 1 : a;

// Cube map (6 images, order +x -x +y -y +z -z)
scene.background = new THREE.CubeTextureLoader().setPath('cm/')
  .load(['px.jpg', 'nx.jpg', 'py.jpg', 'ny.jpg', 'pz.jpg', 'nz.jpg']);

// Equirectangular (LDR jpg): mapping must be set, else it is drawn flat
const eq = new THREE.TextureLoader().load('pano.jpg', () => {
  eq.mapping = THREE.EquirectangularReflectionMapping;
  eq.colorSpace = THREE.SRGBColorSpace;
  scene.background = eq;
});
// HDR equirect (also lights the scene)
import { HDRLoader } from 'three/addons/loaders/HDRLoader.js';   // RGBELoader.js also exists
new HDRLoader().load('studio.hdr', (t) => {
  t.mapping = THREE.EquirectangularReflectionMapping;
  scene.background = scene.environment = t;
});
scene.backgroundBlurriness = 0.3;     // blur background only (needs a PMREM-able texture; applies to equirect/cube)
scene.backgroundIntensity = 0.8;
scene.backgroundRotation.y = Math.PI; // rotate the sky without touching lighting
scene.environmentRotation.y = Math.PI; // rotate the lighting; keep both equal to rotate "the world"
```
Gotchas:
- Background drawn by three is affected by tone mapping and post-processing; a CSS background is not. CSS route: canvas CSS `background: url(...) cover` + `new WebGLRenderer({ alpha: true })`.
- A background texture does not move with the camera position (it is infinitely far); rotate with `backgroundRotation`.
- Equirect HDR/EXR load as float/half-float; leave `colorSpace` as default linear for HDR files.
- For a ground-projected ("grounded") skybox use `GroundedSkybox` (`three/addons/objects/GroundedSkybox.js`; see `lighting-shadows.md`).
- Cheap convert for reuse: `PMREMGenerator.fromEquirectangular(tex).texture` then `tex.dispose()`.

---

## 4. Transparency

Why hard: per-pixel depth test makes the first-drawn triangle hide later farther ones. Three sorts *objects* back-to-front (by object origin distance, `renderer.sortObjects = true`), never individual triangles.

```js
new THREE.MeshStandardMaterial({ color, transparent: true, opacity: 0.5 }); // opacity alone does nothing without transparent
```
Fixes, pick per case:
1. **Convex closed mesh, see both faces:** two meshes sharing geometry: `BackSide` first, then `FrontSide`. Order relies on stable sort; set `renderOrder` to be safe. (`side: DoubleSide` alone shows missing backs from some angles for non-convex/sorted-by-triangle reasons; three already renders double-sided transparent objects in two passes back-then-front unless `material.forceSinglePass = true`.)
```js
for (const side of [THREE.BackSide, THREE.FrontSide]) {
  const m = new THREE.Mesh(geo, new THREE.MeshPhongMaterial({ color, opacity: .5, transparent: true, side }));
  m.renderOrder = side === THREE.BackSide ? 0 : 1; scene.add(m);
}
```
2. **Intersecting planes:** split them geometrically so they do not intersect (no automatic fix).
3. **Cutout textures (leaves, fences, grass):** `alphaTest: 0.5` with `transparent: false` (pixels below threshold are discarded, no sorting problem; edges hard/aliased).
4. **Order control:** `object.renderOrder` (higher draws later within same list; transparent list is sorted after opaque), `material.depthWrite = false` for particles/glows/overlays (avoids self-occlusion artifacts, but then ordering is whatever sort gives).
5. **Alpha hashing:** `material.alphaHash = true`: stochastic dithered discard, order-independent, no sorting needed; noisy unless using TAA/high resolution. Do not combine with `transparent`.
6. **Alpha to coverage:** `material.alphaToCoverage = true` (needs MSAA, `antialias: true`): smooth alphaTest edges via multisample coverage. Example: `examples/webgl_clipping_intersection.html`.
7. **Per-window objects:** a car with glass on four sides should be separate meshes so each sorts independently.

Gotchas: changing `transparent`/`alphaTest`/`alphaHash` at runtime needs `material.needsUpdate = true` (shader rebuild). `premultipliedAlpha` on the material defaults false; canvas premultiplication is separate (section 16). Sprites and particles: `depthWrite: false` + `transparent: true` (+ `blending: THREE.AdditiveBlending` for glows). Large transparent surfaces vs. sorting: sort by origin, so a big plane origin may sort wrong against small objects in front; split or tweak `renderOrder`.

---

## 5. Multiple scenes / multiple canvases

Problem: many canvases = many WebGL contexts (about 8 per page; oldest is lost) and no resource sharing across contexts (a model/textures load once per context).

### Solution A (WebGLRenderer or WebGPURenderer): one full-page canvas behind the page, one scene+camera per placeholder element
```html
<canvas id="c"></canvas>
<span data-diagram="box" class="left"></span>
```
```css
#c { position: absolute; left: 0; top: 0; width: 100%; height: 100%; display: block; z-index: -1; }
[data-diagram] { display: inline-block; width: 5em; height: 3em; }  /* placeholders need explicit size */
```
```js
const sceneElements = [];                       // { elem, fn }
function render(time) {
  resizeRendererToDisplaySize(renderer);
  renderer.setScissorTest(false);
  renderer.setClearColor(0xffffff, 0);
  renderer.clear(true, true);                   // clear whole canvas once
  renderer.setScissorTest(true);
  renderer.domElement.style.transform = `translateY(${window.scrollY}px)`; // canvas scrolls with page => no lag
  for (const { elem, fn } of sceneElements) {
    const rect = elem.getBoundingClientRect();
    const { left, right, top, bottom, width, height } = rect;
    const off = bottom < 0 || top > renderer.domElement.clientHeight ||
                right < 0 || left > renderer.domElement.clientWidth;
    if (off) continue;                          // skip rendering invisible views
    const yUp = renderer.domElement.clientHeight - bottom;   // GL origin is bottom-left
    renderer.setScissor(left, yUp, width, height);
    renderer.setViewport(left, yUp, width, height);
    fn(time * 0.001, rect);                     // inside: camera.aspect = w/h; updateProjectionMatrix(); renderer.render(scene, camera)
  }
  requestAnimationFrame(render);
}
```
Controls per view: `new TrackballControls(camera, elem)` (bind to the placeholder element, not the canvas, since the canvas is behind the page).

Gotchas:
- `position: fixed` canvas lags behind scrolling; `position: absolute` + `translateY(scrollY)` per frame syncs better.
- Scissor/viewport are in CSS pixels (renderer multiplies by pixel ratio).
- Set each scene's `background` (opaque) or clear color per view; with scissor test the scene background only fills the scissor area.
- Share geometries/materials/textures freely across scenes (one context).
- Not in r186: `Scene.autoUpdate` does not exist (grep of `src/` finds none). `Object3D.matrixWorldAutoUpdate`/`matrixAutoUpdate` and `shadowMap.autoUpdate` are the real auto-update flags.

### Solution B (WebGPURenderer): `CanvasTarget`
One renderer drawing to several canvases: `const target = new THREE.CanvasTarget(canvas); renderer.setCanvasTarget(target); renderer.render(scene, camera);` (see `examples/webgpu_multiple_canvas.html`, `api/CanvasTarget.md`, `api/Renderer.md` `setCanvasTarget`/`getCanvasTarget`). Call `target.dispose()` when done.

---

## 6. Billboards and facades

### Camera-facing quads: `Sprite`
```js
const mat = new THREE.SpriteMaterial({ map: texture, transparent: true });  // sizeAttenuation: true default (false = constant pixel-ish size)
const sprite = new THREE.Sprite(mat);
sprite.center.set(0.5, 0);              // pivot (default 0.5,0.5): use (0.5,0) so labels stand on their anchor
sprite.scale.set(canvas.width * 0.01, canvas.height * 0.01, 1);  // world units; 0.01 -> centimeters if 1 unit = 1 m
sprite.position.y = headTop + margin;    // lift above head so it doesn't intersect geometry
```
Sprites always face the camera (rotation around view axis comes from `material.rotation`). Shared geometry is internal. Sprite raycasts via `Raycaster` with `camera` set.
WebGPU: `SpriteNodeMaterial` (node material) is the TSL equivalent; plain `SpriteMaterial` also works.

### Facades (impostors): render a heavy object to a texture once, draw many sprites
```js
function makeSpriteTexture(size, obj, renderer, scene, lightsOnlyScene) {
  const rt = new THREE.WebGLRenderTarget(size, size);   // WebGPU: THREE.RenderTarget
  const cam = new THREE.PerspectiveCamera(fov, 1, near, far);
  scene.add(obj);                                       // scene must have lights, no background
  const box = new THREE.Box3().setFromObject(obj);
  const sz = box.getSize(new THREE.Vector3()), c = box.getCenter(new THREE.Vector3());
  const fudge = 1.1, s = Math.max(sz.x, sz.y, sz.z) * fudge;
  cam.position.copy(c); cam.position.z += (s / 2) / Math.tan(THREE.MathUtils.degToRad(fov / 2));
  renderer.setRenderTarget(rt);
  renderer.render(scene, cam);
  renderer.setRenderTarget(null);
  scene.remove(obj);
  return { texture: rt.texture, scale: s, offset: c.multiplyScalar(fudge) };
}
// transparent background: render target must clear to alpha 0 (renderer.setClearColor(0x000000, 0) while rendering)
```
Use in the far distance only; one view direction (render 8 angles and pick by camera direction to improve). Clear the target with alpha 0 or sprites get a solid background. Dispose `rt` when done.

---

## 7. Canvas textures

```js
const ctx = document.createElement('canvas').getContext('2d');
ctx.canvas.width = 256; ctx.canvas.height = 256;
const texture = new THREE.CanvasTexture(ctx.canvas);
texture.colorSpace = THREE.SRGBColorSpace;      // canvas is sRGB
// after drawing again:
texture.needsUpdate = true;                     // upload on next render
```
Dynamic text label:
```js
function makeLabelCanvas(size, text) {
  const pad = 2, ctx = document.createElement('canvas').getContext('2d');
  const font = `bold ${size}px sans-serif`;
  ctx.font = font;
  ctx.canvas.width = Math.ceil(ctx.measureText(text).width) + pad * 2;
  ctx.canvas.height = size + pad * 2;
  ctx.font = font;                              // font resets when canvas is resized!
  ctx.textBaseline = 'top';
  ctx.fillStyle = 'blue'; ctx.fillRect(0, 0, ctx.canvas.width, ctx.canvas.height);
  ctx.fillStyle = 'white'; ctx.fillText(text, pad, pad);
  return ctx.canvas;
}
const tex = new THREE.CanvasTexture(makeLabelCanvas(32, 'Name'));
tex.minFilter = THREE.LinearFilter;             // no mipmaps for non-POT label canvases
tex.generateMipmaps = false;
tex.wrapS = tex.wrapT = THREE.ClampToEdgeWrapping;
```
Gotchas: resizing the canvas resets 2D state (font); `CanvasTexture` sets `needsUpdate` once at construction, so you must set it again after every redraw; world scale label = `canvas.width * unitPerPixel`; for 3D content drawn into a texture use a `RenderTarget` instead; high-DPI crispness: draw at 2x and scale down; dispose with `texture.dispose()`.

---

## 8. Creating text

Ranked by effort:
1. **DOM + CSS overlay**: simplest; `position:absolute; z-index:100` over the canvas.
2. **`CSS2DRenderer` / `CSS3DRenderer`** (`three/addons/renderers/CSS2DRenderer.js`): HTML elements as scene objects (see section 10).
3. **Canvas texture on a plane/sprite** (section 7).
4. **Modelled text** exported from DCC (GLTF).
5. **`TextGeometry`** (`three/addons/geometries/TextGeometry.js`) needs a `Font` from `FontLoader` (`three/addons/loaders/FontLoader.js`), JSON fonts in `examples/fonts/` (helvetiker, optimer, gentilis, droid, MPLUSRounded1c):
```js
import { FontLoader } from 'three/addons/loaders/FontLoader.js';
import { TextGeometry } from 'three/addons/geometries/TextGeometry.js';
new FontLoader().load('fonts/helvetiker_regular.typeface.json', (font) => {
  const geo = new TextGeometry('Hello', { font, size: 1, depth: 0.2, curveSegments: 8,
                                          bevelEnabled: true, bevelThickness: 0.02, bevelSize: 0.02 });
  geo.center();                               // origin is at baseline-left; center for rotation
  scene.add(new THREE.Mesh(geo, new THREE.MeshStandardMaterial()));
});
```
Parameter is `depth` (extrusion thickness; older docs say `height`). Heavy geometry for long strings: limit `curveSegments`; unique glyph counts matter. Example: `webgl_geometry_text`.
6. **Bitmap/MSDF fonts** (BMFont): batch glyphs in one BufferGeometry with SDF/MSDF shading; word wrap, kerning; tools: msdf-bmfont-web, msdf-bmfont-xml, hiero (from the manual).
7. **troika-three-text** (third-party npm `troika-three-text`, listed in the manual): SDF text from any TTF/WOFF at runtime, web-worker layout, strokes, shadows, curvature, any three Material (including ShaderMaterial), ligatures, RTL. Best default for dynamic text in WebGL.

---

## 9. Drawing lines

```js
const material = new THREE.LineBasicMaterial({ color: 0x0000ff });       // or LineDashedMaterial
const points = [new THREE.Vector3(-10, 0, 0), new THREE.Vector3(0, 10, 0), new THREE.Vector3(10, 0, 0)];
const geometry = new THREE.BufferGeometry().setFromPoints(points);
const line = new THREE.Line(geometry, material);     // open strip; LineLoop closes; LineSegments = pairs
scene.add(line);
```
- Not closed by default (`LineLoop` closes it). `LineSegments` draws pairs.
- `linewidth` is ignored on most platforms (always 1 px). For thick lines use `Line2`/`LineMaterial`/`LineGeometry` from `three/addons/lines/` (WebGPU: `three/addons/lines/webgpu/Line2.js` with `Line2NodeMaterial`); `LineMaterial` needs `material.resolution.set(w, h)` updated on resize.
- `LineDashedMaterial` needs `line.computeLineDistances()` after building geometry.
- Growing line: pre-allocate (section 18) and use `setDrawRange`.

---

## 10. Aligning HTML elements to 3D

### Manual projection (any renderer)
```js
const v = new THREE.Vector3();
function place(obj, elem) {
  obj.updateWorldMatrix(true, false);
  obj.getWorldPosition(v);
  v.project(camera);                                         // NDC: x,y in [-1,1], z in [-1,1] (near..far)
  const x = (v.x *  0.5 + 0.5) * canvas.clientWidth;
  const y = (v.y * -0.5 + 0.5) * canvas.clientHeight;
  elem.style.transform = `translate(-50%, -50%) translate(${x}px,${y}px)`;
  elem.style.zIndex = ((-v.z * 0.5 + 0.5) * 100000) | 0;     // nearer = on top
  elem.style.display = Math.abs(v.z) > 1 ? 'none' : '';      // origin outside near/far (also hides behind camera)
}
```
Markup: container `position:relative; overflow:hidden` holding the canvas and a `#labels{position:absolute;left:0;top:0;z-index:0}` div (z-index 0 creates a stacking context so label z-indices do not leak into the page); label `div{position:absolute;white-space:nowrap;user-select:none;pointer-events:none}`.
Occlusion hiding: `raycaster.setFromCamera(v, camera); const hit = raycaster.intersectObjects(scene.children)[0]; show = hit && hit.object === mesh;` (costly; fine for a few labels). Frustum test that handles big objects: `new THREE.Frustum().setFromProjectionMatrix(proj.multiplyMatrices(camera.projectionMatrix, camera.matrixWorldInverse)).intersectsObject(mesh)`.

### Built-in: `CSS2DRenderer`
```js
import { CSS2DRenderer, CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js';
const labelRenderer = new CSS2DRenderer();
labelRenderer.setSize(innerWidth, innerHeight);
Object.assign(labelRenderer.domElement.style, { position: 'absolute', top: 0, pointerEvents: 'none' });
document.body.appendChild(labelRenderer.domElement);
const div = document.createElement('div'); div.textContent = 'Earth';
const label = new CSS2DObject(div); label.position.set(0, 1, 0); mesh.add(label);
// loop: renderer.render(scene, camera); labelRenderer.render(scene, camera);
// resize: labelRenderer.setSize(w, h)
```
`CSS2DRenderer.sortObjects` (default true) assigns z-index from `renderOrder` then camera distance. Only supports 100% browser zoom. `CSS3DRenderer`/`CSS3DObject` apply full 3D CSS transforms (example `css3d_sprites`, `css3d_mixed`); no depth integration with WebGL except via the mixed-technique masking in `css3d_mixed`. Examples: `css2d_label.html`.

---

## 11. Shadertoy shaders

Shadertoy shaders are fragment-only: `void mainImage(out vec4 fragColor, in vec2 fragCoord)` with globals `iResolution`, `iTime`, `iChannel0..3`, `iMouse`. They are puzzles, not production style.

```js
import * as THREE from 'three';
const renderer = new THREE.WebGLRenderer({ antialias: true, canvas });
renderer.autoClearColor = false;
const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, -1, 1);   // with a 2x2 plane = fullscreen quad
const scene = new THREE.Scene();

const fragmentShader = /* glsl */`
#include <common>
uniform vec3 iResolution;
uniform float iTime;
uniform sampler2D iChannel0;
void mainImage(out vec4 fragColor, in vec2 fragCoord) {
  vec2 uv = fragCoord / iResolution.xy;
  fragColor = vec4(0.5 + 0.5 * cos(iTime + uv.xyx + vec3(0, 2, 4)), 1.0);
}
void main() { mainImage(gl_FragColor, gl_FragCoord.xy); }
`;
const uniforms = {
  iTime: { value: 0 },
  iResolution: { value: new THREE.Vector3() },
  iChannel0: { value: texture },     // set Nearest/Linear filter + RepeatWrapping as the shader expects
};
scene.add(new THREE.Mesh(new THREE.PlaneGeometry(2, 2), new THREE.ShaderMaterial({ fragmentShader, uniforms })));

function render(t) {
  uniforms.iResolution.value.set(canvas.width, canvas.height, 1);   // drawing-buffer pixels, not CSS
  uniforms.iTime.value = t * 0.001;
  renderer.render(scene, camera);
  requestAnimationFrame(render);
}
```
Notes:
- `ShaderMaterial` default vertex shader works with built-in `position`, `uv`, `projectionMatrix`, etc. `gl_FragColor` is mapped for GLSL1-style code (three converts to GLSL3 internally). For a custom vertex shader, pass `vUv` varying and call `mainImage(gl_FragColor, vUv * iResolution.xy)` to use it on any mesh (set `iResolution` to the quad's size, no per-frame update).
- Use `#include <common>` to get helpers like `PI`.
- Output color space: `ShaderMaterial` does not auto-convert; add `#include <colorspace_fragment>` at the end of `main()` (after writing `gl_FragColor`) if you want renderer output colorspace/tone mapping applied.
- Shadertoy multi-pass (buffers A-D) needs `WebGLRenderTarget` ping-pong, one `ShaderMaterial` per pass.
- WebGPURenderer does not run GLSL `ShaderMaterial`. TSL equivalent: build `colorNode` from nodes: `import { Fn, uv, time, vec3, vec4, cos } from 'three/tsl'; material.colorNode = Fn(() => vec4(vec3(0.5).add(cos(time.add(uv().xyx).add(vec3(0,2,4))).mul(0.5)), 1))();` on `MeshBasicNodeMaterial`. Screen-space helpers: `screenUV`, `screenSize`, `screenCoordinate`, `viewportSize`, `viewportCoordinate` (all exported by `three/tsl`, verified in `src/nodes/display/ScreenNode.js`). Use `time` (seconds). Also `RawShaderMaterial` / `NodeMaterial.wgsl`-style raw WGSL is out of scope here.

---

## 12. Post-processing basics (WebGL)

```js
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';

const composer = new EffectComposer(renderer);
composer.addPass(new RenderPass(scene, camera));                       // renders scene into rtA
composer.addPass(new UnrealBloomPass(new THREE.Vector2(innerWidth, innerHeight), 0.8, 0.4, 0.85)); // strength, radius, threshold
composer.addPass(new OutputPass());                                   // tone mapping + sRGB conversion; keep LAST
// loop: composer.render(deltaSeconds)   (replaces renderer.render)
// resize: composer.setSize(w, h)  and  composer.setPixelRatio(dpr)
```
- Composer ping-pongs two render targets; each `Pass` has `enabled`, `needsSwap`, `clear`, `renderToScreen` (last enabled pass renders to screen automatically).
- Working buffers are linear half-float; `OutputPass` is what applies `renderer.toneMapping`/`outputColorSpace`. Without it, output looks dark/flat. The renderer's own tone mapping is skipped when rendering to a render target.
- `composer.dispose()` frees render targets; also dispose passes that have `dispose()`.
- Tune effects through their `uniforms`/properties (e.g. `bloomPass.strength`, `filmPass.uniforms.intensity.value`). Available passes in r186 examples: AfterimagePass, BloomPass, BokehPass, DotScreenPass, FilmPass, FXAAPass, GlitchPass, GTAOPass, HalftonePass, LUTPass, OutlinePass, OutputPass, RenderPixelatedPass, RenderTransitionPass, SAOPass, SMAAPass, SSAARenderPass, SSAOPass, SSRPass, TAARenderPass, UnrealBloomPass, ShaderPass, TexturePass, SavePass, MaskPass, ClearPass, CubeTexturePass.
- Antialiasing: MSAA from `antialias: true` does not apply to the composer's targets; add `FXAAPass`/`SMAAPass` or give the composer a multisampled target (`new WebGLRenderTarget(w, h, { samples: 4 })`).
- **WebGPU:** `EffectComposer` does not apply. Use `THREE.RenderPipeline` (renamed from `PostProcessing` in r183) with TSL: `const rp = new THREE.RenderPipeline(renderer); const scenePass = pass(scene, camera); rp.outputNode = scenePass.getTextureNode('output').add(bloom(...))`; render with `rp.render()`. See `examples/webgpu_postprocessing_bloom.html` and the dedicated post-processing reference.

---

## 13. Cross-refs

- **Picking** (raycasting `Raycaster.setFromCamera(ndc, camera)` + `intersectObjects`; GPU picking with a 1x1 `WebGLRenderTarget` and `readRenderTargetPixels`; WebGPU async `readRenderTargetPixelsAsync`): manual `picking`; see the interaction reference.
- **Rendering on demand**: render once, then only on change (controls `change` event, texture load, resize). With damping call `controls.update()` in a loop only while moving; use `renderer.setAnimationLoop(null)` to pause. Manual `rendering-on-demand`.
- **OffscreenCanvas**: pass `canvas.transferControlToOffscreen()` to a worker, create the renderer there with the OffscreenCanvas; the worker handles resize/input via `postMessage`. `renderer.setSize(w, h, false)` (no style on offscreen canvas). Manual `offscreencanvas`; examples `webgl_worker_offscreencanvas`.

---

## 14. Cleanup and disposal

three never frees GPU resources automatically. Removing a mesh from the scene does NOT dispose its geometry/material/textures. Always dispose what you created when done:

| Object | Call | Notes |
|---|---|---|
| `BufferGeometry` | `geometry.dispose()` | frees all attribute buffers |
| `Material` | `material.dispose()` | frees shader program; does NOT dispose textures |
| `Texture` | `texture.dispose()` | each map separately; for `ImageBitmap` sources call `bitmap.close()` yourself |
| `WebGLRenderTarget` / `RenderTarget` | `rt.dispose()` | texture + framebuffers + depth |
| `SkinnedMesh` skeleton | `skeleton.dispose()` | only if not shared |
| `EffectComposer`, controls, passes, helpers | `.dispose()` if present | removes listeners / targets |
| `WebGLRenderer` | `renderer.dispose()` | then optionally `renderer.forceContextLoss()`; remove `domElement` |
| `PMREMGenerator` | `pmrem.dispose()` | after generating env maps |

Using a disposed object again re-creates resources (no error, but a perf hit and possible shader recompile).
```js
function disposeObject(root) {
  root.traverse((o) => {
    if (o.geometry) o.geometry.dispose();
    const mats = o.material ? [].concat(o.material) : [];
    for (const m of mats) {
      for (const v of Object.values(m)) if (v && v.isTexture) v.dispose();   // maps (also uniforms of ShaderMaterial: check m.uniforms)
      m.dispose();
    }
  });
  root.removeFromParent();
}
```
Verify with `renderer.info`: `renderer.info.memory.geometries / textures`, `renderer.info.render.calls / triangles`; programs in `renderer.info.programs` (WebGL). Some internally cached textures/geometries (e.g. PMREM, background) remain reported after a full scene cleanup; that is expected, not a leak. WebGPURenderer: `renderer.info` is an `Info` object (`api/Info.md`); `info.autoReset` is true (set false and call `info.reset()` yourself when rendering several times per frame, e.g. composers or multi-view).
Shared resources: dispose once; don't dispose a shared material/geometry still used elsewhere. A game with fixed levels often should not dispose at all. A `ResourceTracker` pattern (track(obj) returns obj; `dispose()` disposes all and removes Object3Ds from parents) is the manual's helper for dynamic loading; for GLTF just `traverse`. Disposing a texture before its image loaded is a no-op.

---

## 15. Debugging

JavaScript:
- Console first (typos in imports, 404s). Disable browser cache while developing.
- Black screen: check for `NaN`/`Infinity` in `object.matrixWorld`, `camera.projectionMatrix`, `position`; put a breakpoint after `render()` and inspect.
- Swap to `MeshBasicMaterial`; check `near/far`; check the object is actually in front of the camera; put a known-good object (a box at the origin) in front.
- Units: rotations are radians, `camera.fov` is degrees (vertical), `MathUtils.degToRad`. `renderer.setSize` is CSS pixels.
- Put `requestAnimationFrame`/`setAnimationLoop` registration at the start of the render function or inside try/catch so an exception does not silently stop the loop.
- Put debug state on screen (a `<pre>` updated per frame); use query params (`?debug`) to toggle features; use `console.log(object)` and expand in devtools. Make a minimal reproducible example (canvas + script only) before asking for help.
- Helpers: `AxesHelper`, `GridHelper`, `BoxHelper`, `Box3Helper`, `CameraHelper`, light helpers (see `lighting-shadows.md`).

GLSL:
- Output a solid color at the end of the fragment shader: `gl_FragColor = vec4(1,0,0,1);` Visible -> fragment/uniform/texture problem; invisible -> vertex/matrices/attributes problem.
- Visualize values: normals `vec4(vNormal * 0.5 + 0.5, 1)`; UVs `vec4(fract(vUv), 0, 1)`; scale any scalar into 0..1.
- Test textures with a known-good `CanvasTexture`/`DataTexture`; test geometry with the simplest vertex shader `gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);`.
- `material.onBeforeCompile` shows/patches built-in shader: log `shader.vertexShader`. `renderer.debug.checkShaderErrors` (WebGL, default true) prints compile/link logs; `renderer.debug.onShaderError(gl, program, vs, fs)` hook exists. Browser extension: Shader Editor / Spector.js.
- WebGPU: WGSL/TSL errors are in console; `renderer.inspector` (`three/addons/inspector/Inspector.js`, used in the webgpu examples) can show node graphs and timing; verify availability in your version before use.

---

## 16. Tips

### Screenshot / toBlob
The drawing buffer is cleared after compositing, so `canvas.toBlob` after the frame returns black. Render immediately before capture:
```js
button.onclick = () => {
  renderer.render(scene, camera);            // same task as toBlob
  canvas.toBlob((blob) => { const a = document.createElement('a');
    a.href = URL.createObjectURL(blob); a.download = 'shot.png'; a.click(); });
};
```
Or construct with `preserveDrawingBuffer: true` (costs performance; WebGL only). For a bigger/offscreen shot render to a `WebGLRenderTarget` and `readRenderTargetPixels` (WebGPU: `readRenderTargetPixelsAsync`).

### Prevent clear (paint trails)
```js
const renderer = new THREE.WebGLRenderer({ canvas, preserveDrawingBuffer: true, alpha: true });
renderer.autoClearColor = false;     // also autoClear / autoClearDepth available
```
Browser still clears on canvas resize; real drawing apps should render into a render target.

### Keyboard input on canvas
`<canvas tabindex="0">` plus `canvas:focus{outline:none}`. Without tabindex the canvas never receives key events.

### Transparent canvas
```js
new THREE.WebGLRenderer({ alpha: true, premultipliedAlpha: false });   // see HTML behind; premultipliedAlpha default true
renderer.setClearColor(0x000000, 0);
```
Remove `scene.background`, since it paints an opaque color. `pointer-events: none` on the canvas lets clicks pass through to HTML. WebGPURenderer: `alpha` option (default true in `Renderer`; verify canvas compositing in your browser).

### three.js as page background
Canvas `position:fixed; inset:0; z-index:-1; pointer-events:none`, or an `<iframe>` with the same CSS plus `border:none` (isolates the page's JS from the demo).

---

## 17. Game structure

Pattern from the manual's game article: entity-component.
```js
class GameObject {
  constructor(parent, name) { this.name = name; this.components = []; this.transform = new THREE.Object3D(); parent.add(this.transform); }
  addComponent(Ctor, ...args) { const c = new Ctor(this, ...args); this.components.push(c); return c; }
  removeComponent(c) { const i = this.components.indexOf(c); if (i >= 0) this.components.splice(i, 1); }
  getComponent(Ctor) { return this.components.find((c) => c instanceof Ctor); }
  update() { for (const c of this.components) c.update(); }
}
class Component { constructor(gameObject) { this.gameObject = gameObject; } update() {} }
```
- **SafeArray / manager:** add/remove during iteration is deferred (queue adds/removes, apply after the loop) so a component can delete itself in `update()`.
- **Input manager:** components read abstract `inputManager.keys.left.down` rather than raw events; map keyboard + touch buttons to the same state.
- **Delta time clamp:** `globals.deltaTime = Math.min(now - then, 1 / 20)` so a tab switch/hitch doesn't teleport entities or explode physics (`position += velocity * dt`). Prefer `THREE.Timer`: `timer.update(); const dt = Math.min(timer.getDelta(), 0.05);` (call `timer.connect(document)` to pause on hidden tabs). `Clock` is deprecated.
- Animation: `mixer.update(dt)` each frame; `AnimationMixer` clips for state transitions (finite-state machine for NPC behavior).
- Loading: `LoadingManager` `onProgress` for a progress bar; `SkeletonUtils.clone` (`three/addons/utils/SkeletonUtils.js`) to instance skinned models.
- Camera follow, offscreen indicators: `Frustum.containsPoint` and `project()` for HUD.

---

## 18. How to update things (needsUpdate matrix)

| Thing | What you changed | Required |
|---|---|---|
| Object transform | `position/rotation/scale` of an object in the scene | nothing (auto `updateMatrix` unless `matrixAutoUpdate = false`) |
| Static object | `matrixAutoUpdate = false` | call `object.updateMatrix()` after each change; `matrixWorldAutoUpdate` also exists |
| BufferGeometry attribute **values** | `attr.array[i] = ...` / `setXYZ` | `attr.needsUpdate = true`; then `geometry.computeBoundingSphere()/computeBoundingBox()` for culling/helpers/raycast; `computeVertexNormals()` if lit |
| BufferGeometry **size** | more vertices than allocated | not possible; pre-allocate max and use `geometry.setDrawRange(0, n)`, or create a new geometry (dispose old) |
| Index buffer | changed | `geometry.index.needsUpdate = true` |
| Material uniforms/color/opacity/maps values | change `.value`, `.color`, `.opacity`, `.map = otherTexture` | nothing (uploaded each frame) |
| Material features | `transparent`, `alphaTest`, `alphaHash`, adding/removing a map (null <-> texture), fog, vertexColors, flatShading, morph targets, shadows toggle, side-related program keys | `material.needsUpdate = true` (shader recompile; may hitch). Use dummy values (white texture, zero-intensity light) to avoid it |
| Material GL state | `depthTest`, `depthWrite`, `blending`, `polygonOffset`, `side` | free at runtime |
| Image/Canvas/Video/Data texture | pixels changed | `texture.needsUpdate = true` (VideoTexture auto-updates per frame; `VideoFrameTexture` / `requestVideoFrameCallback`) |
| Texture parameters | `wrapS/T`, `minFilter`, `colorSpace`, `anisotropy`, `format`, `generateMipmaps` after first upload | `texture.needsUpdate = true` |
| Render targets | rendered into | automatic |
| Camera | `fov`, `aspect`, `near`, `far`, `zoom`, ortho bounds | `camera.updateProjectionMatrix()` |
| InstancedMesh | `setMatrixAt` / `setColorAt` | `instancedMesh.instanceMatrix.needsUpdate = true` / `instanceColor.needsUpdate = true`; `computeBoundingBox()/computeBoundingSphere()` for culling & raycast |
| SkinnedMesh | animated bones | `computeBoundingBox()/computeBoundingSphere()` account for skeleton |
| Lights / shadow | light property values | automatic; shadow map re-renders each frame unless `renderer.shadowMap.autoUpdate = false` then `renderer.shadowMap.needsUpdate = true`; changing `castShadow` or shadow type needs `material.needsUpdate` |
| Renderer size | window resize | `renderer.setSize`, then camera update |
| Lights added/removed | count change | triggers shader rebuild (WebGL): avoid per-frame; use intensity 0 instead |

---

## 19. Uniform types (ShaderMaterial / RawShaderMaterial)

Each uniform is `{ value }`; JS type must match GLSL type.

| GLSL | JS value |
|---|---|
| `int`, `uint`, `float` | Number |
| `bool` | Boolean or Number |
| `vec2` | Vector2, or Float32Array/Array (flattened) |
| `vec3` | Vector3, Color, or flat array |
| `vec4` | Vector4, Quaternion, or flat array |
| `mat2` / `mat3` / `mat4` | flat array / Matrix3 / Matrix4 |
| `ivec2/3/4`, `bvec2/3/4` | Int32Array or Array |
| `sampler2D` / `samplerCube` | Texture / CubeTexture |

Structs and arrays of structs:
```js
uniforms = { data: { value: { position: new THREE.Vector3(), direction: new THREE.Vector3(0, 0, 1) } } };   // struct Data {...}; uniform Data data;
uniforms = { data: { value: [entry1, entry2] } };                                                          // uniform Data data[2];
```
Arrays of primitives: GLSL array length must match, flat typed array for vectors (`vec3 v[4]` -> `Float32Array(12)` or array of Vector3). Update by mutating `uniforms.x.value`; replacing the uniform object after first render breaks references. Colors in uniforms are linear working-space values (no sRGB conversion); `Color` goes in as linear floats. Renderer chunks and built-in uniform names (`projectionMatrix`, `modelViewMatrix`, `normalMatrix`, `cameraPosition`, `position`, `uv`) are auto-provided by `ShaderMaterial` but not by `RawShaderMaterial`. WebGPURenderer: use TSL `uniform(value)` instead (`.value` is still how you update it).

---

## 20. See also

API pages (`references/api/`): `Scene.md`, `WebGLRenderer.md`, `WebGPURenderer.md`, `Renderer.md`, `Info.md`, `CanvasTarget.md`, `Sprite.md`, `SpriteMaterial.md`, `CanvasTexture.md`, `TextGeometry.md`, `FontLoader.md`, `CSS2DRenderer.md`, `CSS3DRenderer.md`, `Line.md`, `LineBasicMaterial.md`, `LineDashedMaterial.md`, `Line2.md`, `LineMaterial.md`, `ShaderMaterial.md`, `RawShaderMaterial.md`, `Material.md`, `Texture.md`, `BufferGeometry.md`, `EffectComposer.md`, `RenderPass.md`, `OutputPass.md`, `UnrealBloomPass.md`, `RenderPipeline.md`, `WebGLRenderTarget.md`, `Timer.md`, `Frustum.md`, `Vector3.md`, `Raycaster.md`, `PMREMGenerator.md`.

Official: https://threejs.org/manual/#backgrounds, #transparency, #multiple-scenes, #billboards, #canvas-textures, #creating-text, #drawing-lines, #align-html-elements-to-3d, #shadertoy, #post-processing, #picking, #cleanup, #how-to-dispose-of-objects, #rendering-on-demand, #debugging-javascript, #debugging-glsl, #tips, #game, #offscreencanvas, #how-to-update-things, #uniform-types, #installation; docs https://threejs.org/docs/#Scene, https://threejs.org/docs/#Sprite, https://threejs.org/docs/#CSS2DRenderer, https://threejs.org/docs/#Material, https://threejs.org/docs/#Timer.
