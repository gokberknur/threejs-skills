# three.js r186 Fundamentals

## When to read this
Read before writing any three.js app: app skeleton (renderer/scene/camera/loop), responsive canvas and pixel ratio, scene graph and transforms, cameras, built-in primitives, texture basics, lights and shadows overview, fog, render targets, and the "what needs `needsUpdate`" rules. Geometry authoring is in `geometry.md`; materials/color management/loaders/animation are in their own reference files. Version: three@0.186.1 (r186).

## Table of contents
1. [Project setup and imports](#1-project-setup-and-imports)
2. [App skeleton and animation loop](#2-app-skeleton-and-animation-loop)
3. [Timer vs Clock](#3-timer-vs-clock)
4. [Responsive canvas and pixel ratio](#4-responsive-canvas-and-pixel-ratio)
5. [Scene graph and transforms](#5-scene-graph-and-transforms)
6. [Matrices and matrixAutoUpdate](#6-matrices-and-matrixautoupdate)
7. [Cameras](#7-cameras)
8. [Primitives](#8-primitives)
9. [Materials quick map](#9-materials-quick-map)
10. [Textures basics](#10-textures-basics)
11. [Lights overview](#11-lights-overview)
12. [Shadows](#12-shadows)
13. [Fog](#13-fog)
14. [Render targets](#14-render-targets)
15. [How to update things (needsUpdate rules)](#15-how-to-update-things)
16. [Layers and Raycaster](#16-layers-and-raycaster)
17. [Compatibility, FAQ, ecosystem](#17-compatibility-faq-ecosystem)
18. [See also](#see-also)

---

## 1. Project setup and imports

ES modules only (since r147 the only supported way to load three.js; no global `THREE` script build).

```bash
npm install --save three
npm install --save-dev vite
npx vite            # dev server, http://localhost:5173
npx vite build      # production build -> dist/
```

```js
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'; // = three/examples/jsm/*
import { WebGPURenderer } from 'three/webgpu';                          // WebGPU build (separate entry)
import { color, uniform } from 'three/tsl';                             // TSL node entry
```
`package.json` exports: `three`, `three/addons/*` -> `examples/jsm/*`, `three/addons` -> `examples/jsm/Addons.js`, `three/webgpu`, `three/tsl`, `three/examples/jsm/*`, `three/examples/fonts/*`.

No bundler: use an import map. Paths must start with `./` or `../` or be URLs.
```html
<script type="importmap">
{ "imports": {
  "three": "https://cdn.jsdelivr.net/npm/three@0.186.1/build/three.module.js",
  "three/addons/": "https://cdn.jsdelivr.net/npm/three@0.186.1/examples/jsm/"
} }
</script>
<script type="module" src="main.js"></script>
```
Gotchas:
- Opening `file://` HTML does not work (module CORS, texture loading). Always serve over HTTP (vite, `npx servez`, etc.).
- Pin the CDN version; addons must match the core version.
- Community TypeScript types: `@types/three` (three-types/three-ts-types).
- Typical layout: `index.html`, `main.js`, `public/` (static textures/models/audio served unchanged).

Minimal HTML:
```html
<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<style>html,body{margin:0;height:100%} #c{width:100%;height:100%;display:block}</style>
</head><body><canvas id="c"></canvas><script type="module" src="/main.js"></script></body></html>
```
Mobile viewport meta used by examples: `<meta name="viewport" content="width=device-width, user-scalable=no, minimum-scale=1.0, maximum-scale=1.0">`.

---

## 2. App skeleton and animation loop

Object relationships: `Renderer` draws (`Scene`, `Camera`). `Scene` is root of a tree of `Object3D` (`Mesh`, `Group`, `Light`, ...). `Mesh = Geometry + Material (+ transform)`. Geometry and Material can be shared by many Meshes. A `Camera` need not be in the scene graph (if it is a child of something, it follows it, and then that parent must be in the scene for world matrices to update).

```js
import * as THREE from 'three';

const canvas = document.querySelector('#c');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });

const camera = new THREE.PerspectiveCamera(75, 2, 0.1, 100); // fov DEG, aspect, near, far
camera.position.z = 3;                                       // looks down -Z, +Y up by default

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x202020);

const light = new THREE.DirectionalLight(0xffffff, 3);
light.position.set(-1, 2, 4);                                // target defaults to (0,0,0)
scene.add(light);

const mesh = new THREE.Mesh(
  new THREE.BoxGeometry(1, 1, 1),
  new THREE.MeshStandardMaterial({ color: 0x44aa88 }),       // MeshBasicMaterial ignores lights
);
scene.add(mesh);

function animate(timeMs) {                                   // setAnimationLoop passes ms timestamp
  const t = timeMs * 0.001;                                  // -> seconds
  mesh.rotation.x = t;                                       // radians
  mesh.rotation.y = t;
  renderer.render(scene, camera);
}
renderer.setAnimationLoop(animate);                          // start; setAnimationLoop(null) stops
```

Rules:
- Prefer `renderer.setAnimationLoop(cb)` over hand-written `requestAnimationFrame` (docs: "advised ... for best compatibility"; mandatory for WebXR since the XR session drives frames).
- Angles are radians everywhere except `PerspectiveCamera.fov` (degrees).
- Anything you want drawn must be (a descendant of) the object passed to `render()`. Passing a `Group`/`Object3D` as the first arg also works.
- `renderer.dispose()` when tearing down; `renderer.forceContextLoss()` simulates context loss (needs `WEBGL_lose_context`).
- Default render clears color/depth/stencil each call (`autoClear`, `autoClearColor`, `autoClearDepth`, `autoClearStencil` all `true`). Multi-pass overlays: set `renderer.autoClear = false` and call `renderer.clear()` / `clearDepth()` manually.
- Pre-warm shaders to avoid first-frame jank: `renderer.compile(scene, camera)` or `await renderer.compileAsync(scene, camera)`.

WebGLRenderer constructor options (all defaults from r186 docs): `canvas`, `context`, `precision='highp'`, `alpha=false`, `premultipliedAlpha=true`, `antialias=false`, `stencil=false`, `preserveDrawingBuffer=false`, `powerPreference='default'`, `failIfMajorPerformanceCaveat=false`, `depth=true`, `logarithmicDepthBuffer=false`, `reversedDepthBuffer=false` (needs `EXT_clip_control`), `outputBufferType=UnsignedByteType` (use `HalfFloatType` for HDR output).

Renderer state worth knowing: `outputColorSpace = SRGBColorSpace` (default), `toneMapping = NoToneMapping`, `toneMappingExposure = 1`, `sortObjects = true`, `shadowMap.{enabled=false, type=PCFShadowMap, autoUpdate=true, needsUpdate=false}`, `info.render` / `info.memory` (draw calls, triangles, geometries, textures; `info.autoReset=false` + manual `info.reset()` for multi-pass frames), `setClearColor(color, alpha)`, `getDrawingBufferSize(v2)`, `getSize(v2)`.

### WebGLRenderer vs WebGPURenderer
| | WebGLRenderer | WebGPURenderer (`three/webgpu`) |
|---|---|---|
| import | `three` | `import * as THREE from 'three/webgpu'` |
| init | synchronous | `await renderer.init()` before first sync `render`, or use `await renderer.renderAsync(scene, camera)` |
| default `alpha` | `false` | `true` |
| MSAA | `antialias: true` | `antialias: true` (4 samples by default) or `samples: n` |
| fallback | n/a | falls back to WebGL2 backend; `forceWebGL` option exists |
| materials | classic `Mesh*Material`, `ShaderMaterial` (GLSL) | classic materials work (mapped to node materials); custom shaders via TSL nodes (`*NodeMaterial`), no GLSL `ShaderMaterial` |
| `Object3D.static`, `Mesh.count`, `LightShadow.biasNode` | ignored / unavailable | WebGPU only |
`setAnimationLoop`, `render`, `setSize`, `setPixelRatio`, `setRenderTarget` have the same call shape. Details: manual page `webgpurenderer`.

---

## 3. Timer vs Clock

`THREE.Clock` is deprecated since r183 (constructing it logs: "Clock: This module has been deprecated. Please use THREE.Timer instead."). Use `THREE.Timer` (`src/core/Timer.js`).

Why: `Clock.getDelta()` mutates state on every call, so two calls per frame give different values. `Timer.update()` advances state once per frame; `getDelta()`/`getElapsed()` are then pure reads.

```js
const timer = new THREE.Timer();
timer.connect(document);              // Page Visibility API: no giant delta after tab was hidden

renderer.setAnimationLoop((timestamp) => {
  timer.update(timestamp);            // ms; omit -> performance.now()
  const dt = timer.getDelta();        // seconds, scaled by timescale
  const t  = timer.getElapsed();      // seconds
  mixer.update(dt);
  renderer.render(scene, camera);
});
```
API: `connect(document)`, `disconnect()`, `dispose()`, `update(timestamp?)`, `getDelta()`, `getElapsed()`, `getTimescale()`, `setTimescale(n)`, `reset()`.
Old API (deprecated): `new THREE.Clock()`, `getDelta()` (sec), `getElapsedTime()`, `start()`, `stop()`, props `autoStart`, `running`, `elapsedTime`, `startTime`, `oldTime`.
Gotcha: forgetting `timer.update()` every frame leaves delta at 0.

---

## 4. Responsive canvas and pixel ratio

A canvas has two sizes: CSS display size (`clientWidth/clientHeight`) and drawing-buffer size (`canvas.width/height`, default 300x150). Let CSS size the canvas; sync the buffer and camera to it.

```js
function resizeToDisplaySize(renderer, camera) {
  const canvas = renderer.domElement;
  const pr = Math.min(window.devicePixelRatio, 2);            // cap: GPU cost scales with pr^2
  const w = Math.floor(canvas.clientWidth  * pr);
  const h = Math.floor(canvas.clientHeight * pr);
  if (canvas.width !== w || canvas.height !== h) {            // don't resize when unchanged
    renderer.setSize(w, h, false);                            // false = DON'T touch canvas.style
    camera.aspect = canvas.clientWidth / canvas.clientHeight;
    camera.updateProjectionMatrix();                          // required after aspect/fov/near/far/zoom change
  }
}
// call at the top of animate()
```
Gotchas:
- `setSize(w, h)` writes inline CSS width/height by default (`updateStyle = true`) which fights your CSS layout. Pass `false`.
- `renderer.setPixelRatio(devicePixelRatio)` + `setSize(cssW, cssH)` is the shortcut (`setSize` multiplies by pixel ratio; `setPixelRatio` resizes the canvas if needed). The manual calls the first form strongly not recommended because the drawing-buffer size then differs from what you asked for, which bites post-processing, `gl_FragCoord`, and render-target sizing. If you use it, size render targets from `renderer.getDrawingBufferSize(v)`.
- HiDPI is expensive: a 3x phone renders 9x pixels. For heavy scenes use pixel ratio 1-2. With fractional OS scaling (150%) `width*dpr` may exceed the real resolution; cap pixel count, e.g. `renderScale = Math.sqrt(maxPixels / (w*h))` when `w*h > 3840*2160`.
- Canvas default `display: inline` adds whitespace: set `display:block`.
- Render targets sized to the canvas must be resized too: `renderTarget.setSize(canvas.width, canvas.height)`.
- Keep world scale constant on resize (FAQ): visible height at distance d = `2 * Math.tan(THREE.MathUtils.degToRad(camera.fov) / 2) * d`; to keep objects the same size when window height changes, change `fov`, not camera position.
- For resize detection outside the loop use `ResizeObserver` on the canvas; for render-on-demand see manual `rendering-on-demand`.

Camera helpers: `camera.getViewSize(distance, v2)`, `camera.getViewBounds(distance, minV2, maxV2)`.

---

## 5. Scene graph and transforms

`Object3D` is the node type (parent of `Scene`, `Group`, `Mesh`, `Line`, `Points`, `Light`, `Camera`, `Bone`, `Sprite`, `LOD`, ...). Each node has a **local space**; a child's transform is relative to its parent. `Group` is an `Object3D` with `isGroup` and no extra behavior: use it as a pure transform/organization node.

```js
const solarSystem = new THREE.Object3D(); scene.add(solarSystem);
const sun = new THREE.Mesh(sphereGeo, sunMat); sun.scale.set(5, 5, 5); solarSystem.add(sun);
const earthOrbit = new THREE.Object3D(); earthOrbit.position.x = 10; solarSystem.add(earthOrbit);
earthOrbit.add(earthMesh);                                    // NOT a child of sun: would inherit 5x scale
```
Classic trap: parenting a mesh to a scaled mesh scales its size AND offsets. Insert an empty `Object3D` pivot node instead.

### Transform properties (local space, relative to parent)
| prop | type | notes |
|---|---|---|
| `position` | Vector3 | `position.set(x,y,z)`, `.copy()`, `.x = ...` |
| `rotation` | Euler (radians, order default `'XYZ'`) | synced to `quaternion` (either can be edited) |
| `quaternion` | Quaternion | source of truth; no gimbal lock |
| `scale` | Vector3 | default (1,1,1) |
| `pivot` | Vector3 or `null` | new: rotation and scale are applied around this point instead of the origin |
| `up` | Vector3 | default `Object3D.DEFAULT_UP` = (0,1,0); `lookAt` uses it |

Methods: `rotateX/Y/Z(angle)`, `rotateOnAxis(axis, angle)` (local axis), `rotateOnWorldAxis(axis, angle)`, `translateX/Y/Z(dist)`, `translateOnAxis(axis, dist)`, `setRotationFromEuler/Quaternion/Matrix/AxisAngle`, `applyQuaternion`, `applyMatrix4` (uses `Matrix4.decompose`; fails with non-uniformly scaled parents), `lookAt(x|Vector3, y, z)`.

### lookAt, world vs local
```js
obj.lookAt(target);                       // target is WORLD space; "not supported with non-uniformly-scaled parents"
camera.lookAt(0, 0, 0);                   // cameras look down local -Z
// lights / cameras: +Z faces the target for ordinary Object3D, -Z for Camera and Light
const p = obj.getWorldPosition(new THREE.Vector3());      // target vector is REQUIRED (no allocation inside)
obj.getWorldQuaternion(q); obj.getWorldScale(s); obj.getWorldDirection(dir);
obj.localToWorld(v);                       // mutates v, local -> world
obj.worldToLocal(v);                       // mutates v, world -> local
```
Gotchas:
- `getWorldPosition` etc. call `updateWorldMatrix` first, but `localToWorld` uses the current `matrixWorld`; if transforms changed this frame and no render yet, call `obj.updateWorldMatrix(true, false)` first.
- `Camera.getWorldDirection` is overridden: it returns the -Z forward.
- `rotation` and `quaternion` are linked; setting `rotation.x` updates `quaternion`. Euler gimbal lock applies only to the Euler view. Animate with quaternions (slerp: `q.slerp(target, t)`) for large rotations.

### Reparenting
```js
parent.add(child);        // removes child from old parent; local transform is KEPT (world pose jumps)
parent.attach(child);     // keeps WORLD transform (recomputes local); no non-uniform-scale support
child.removeFromParent(); parent.remove(child); parent.clear();
```
Traversal / lookup: `traverse(fn)`, `traverseVisible(fn)`, `traverseAncestors(fn)`, `getObjectByName(name)`, `getObjectById(id)`, `getObjectByProperty(name, value)`, `getObjectsByProperty(name, value, resultArray)`. Events: `added`, `removed`, `childadded`, `childremoved`, `dispose`.

Other common Object3D props: `name`, `visible` (false = not rendered, children too), `castShadow`, `receiveShadow`, `frustumCulled=true`, `renderOrder=0` (sorting within opaque/transparent lists; on a Group it sorts all descendants together), `layers`, `userData` (JSON-serialized; no functions), `matrixAutoUpdate`, `matrixWorldAutoUpdate`, `static` (WebGPURenderer-only hint: object will not change after first render), `animations`. Hooks: `onBeforeRender/onAfterRender(renderer, object, camera, geometry, material, group)` (per `api/Object3D.md`), `onBeforeShadow/onAfterShadow`.

Cloning: `obj.clone(recursive = true)` shares geometry and material references; skinned meshes need `SkeletonUtils.clone` (`three/addons/utils/SkeletonUtils.js`). `obj.dispose()` (new in r186 docs) frees GPU resources allocated by the object itself and fires `dispose`; geometries, materials, textures are shared and must be disposed separately.

Debug helpers: `AxesHelper`, `GridHelper` (set `material.depthTest = false` and `renderOrder` to draw through meshes), `CameraHelper`, `DirectionalLightHelper`, `PointLightHelper`, `SpotLightHelper`, `Box3Helper`, `BoxHelper`. Helpers with an `update()` must be updated after the thing they watch changes.

---

## 6. Matrices and matrixAutoUpdate

Each `Object3D` has `matrix` (local, from position/quaternion/scale/pivot) and `matrixWorld` (= parent.matrixWorld * matrix). By default (`matrixAutoUpdate = true`) the renderer recomputes both every frame for everything under the rendered scene (`Object3D.DEFAULT_MATRIX_AUTO_UPDATE`, `DEFAULT_MATRIX_WORLD_AUTO_UPDATE`).

Two ways to transform:
```js
// 1. properties (default)
obj.position.copy(p); obj.quaternion.copy(q);

// 2. static object: freeze and update manually, only when changed
obj.matrixAutoUpdate = false;
obj.position.set(1, 2, 3);
obj.updateMatrix();                 // recompute local matrix from properties

// 3. direct matrix editing
obj.matrixAutoUpdate = false;       // MUST be false, and DON'T call updateMatrix() (it overwrites from position/scale/...)
obj.matrix.makeRotationFromQuaternion(q);
obj.matrix.setPosition(p);
obj.matrixWorldNeedsUpdate = true;  // or obj.updateMatrixWorld(true)
```
- `updateMatrixWorld(force)` recomputes world matrices for the subtree; `updateWorldMatrix(updateParents, updateChildren, force)` gives finer control (e.g. `(true, false)` to refresh just this node from its ancestors).
- `matrixWorldAutoUpdate = false`: you own `matrixWorld`.
- Non-uniform scale on a parent plus rotated children = shear; the world matrix can't be decomposed; `lookAt`, `attach`, `applyMatrix4` break.
- Quaternion is canonical; `useQuaternion` is long gone; use `setRotationFromEuler`.
- Static scenes with thousands of objects: set `matrixAutoUpdate = false` + one `updateMatrix()` (and `scene.matrixWorldAutoUpdate` consideration) for big CPU savings; for bulk copies use `InstancedMesh`/`BatchedMesh`.

---

## 7. Cameras

Base `Camera` (extends Object3D): `matrixWorldInverse`, `projectionMatrix`, `projectionMatrixInverse`, `coordinateSystem`, `reversedDepth`. Looks down local **-Z**, +Y up.

### PerspectiveCamera( fov = 50, aspect = 1, near = 0.1, far = 2000 )
- `fov`: **vertical**, degrees. `aspect = width / height`. `zoom = 1`, `focus = 10`, `filmGauge = 35`, `filmOffset = 0`, `view = null`.
- After changing `fov | aspect | near | far | zoom` call `camera.updateProjectionMatrix()`. Moving/rotating the camera needs nothing.
- Frustum = truncated pyramid between near and far. Anything outside is clipped.
- Depth precision: z-buffer is non-linear; ratio far/near large causes z-fighting. Keep `near` as large as possible (0.1 not 0.0001), far as small as possible. Options: `new WebGLRenderer({ logarithmicDepthBuffer: true })` (disables early-Z, slower) or `reversedDepthBuffer: true` (needs `EXT_clip_control`; faster and more accurate).
- Utilities: `getEffectiveFOV()`, `getFocalLength()`/`setFocalLength(mm)` (via `filmGauge`), `getFilmWidth()/getFilmHeight()`, `getViewSize(distance, target)`, `getViewBounds(distance, min, max)`, `setViewOffset(fullW, fullH, x, y, w, h)` / `clearViewOffset()` (multi-monitor / tiled rendering).

### OrthographicCamera( left = -1, right = 1, top = 1, bottom = -1, near = 0.1, far = 2000 )
No perspective; boxes stay the same size. Use for 2D/UI, CAD/editor orthographic views, shadow cameras. Keep aspect correct yourself:
```js
const frustumH = 10;                                   // world units visible vertically
function fitOrtho(cam, w, h) {
  const aspect = w / h;
  cam.left = -frustumH * aspect / 2; cam.right = frustumH * aspect / 2;
  cam.top = frustumH / 2;            cam.bottom = -frustumH / 2;
  cam.updateProjectionMatrix();
}
// 1 CSS px = 1 world unit, origin at centre, +Y up:
const cam2d = new THREE.OrthographicCamera(-w / 2, w / 2, h / 2, -h / 2, -1, 1);
// origin top-left like canvas 2D (+Y still up in world space): left=0, right=w, top=0, bottom=-h
```
`zoom` scales the visible box (OrbitControls zoom on an ortho camera changes `zoom`; call `updateProjectionMatrix()`).

Other cameras: `ArrayCamera` (multi-viewport), `CubeCamera` (+ `WebGLCubeRenderTarget`; env maps/reflections), `StereoCamera`. `CameraHelper(camera)` draws a frustum.

### Multiple views (scissor)
```js
renderer.setScissorTest(true);
renderer.setViewport(x, y, w, h);  renderer.setScissor(x, y, w, h);   // origin bottom-left, CSS-scaled by pixel ratio
renderer.render(scene, camera);
renderer.setScissorTest(false);
```
`setViewport/setScissor` take logical pixels (pixel ratio applied internally).

---

## 8. Primitives

All extend `BufferGeometry`; sizes in world units, angles in radians. Constructor signatures below are verified against `src/geometries/*.js` r186. Every geometry stores its constructor args in `.parameters` (read-only snapshot; editing it does nothing) and is built once at construction. To change shape, build a new one and dispose the old.

| Class | Constructor (defaults) |
|---|---|
| `BoxGeometry` | `(width=1, height=1, depth=1, widthSegments=1, heightSegments=1, depthSegments=1)` |
| `PlaneGeometry` | `(width=1, height=1, widthSegments=1, heightSegments=1)` (XY plane, faces +Z) |
| `CircleGeometry` | `(radius=1, segments=32, thetaStart=0, thetaLength=2PI)` |
| `RingGeometry` | `(innerRadius=0.5, outerRadius=1, thetaSegments=32, phiSegments=1, thetaStart=0, thetaLength=2PI)` |
| `SphereGeometry` | `(radius=1, widthSegments=32, heightSegments=16, phiStart=0, phiLength=2PI, thetaStart=0, thetaLength=PI)` |
| `CylinderGeometry` | `(radiusTop=1, radiusBottom=1, height=1, radialSegments=32, heightSegments=1, openEnded=false, thetaStart=0, thetaLength=2PI)` |
| `ConeGeometry` | `(radius=1, height=1, radialSegments=32, heightSegments=1, openEnded=false, thetaStart=0, thetaLength=2PI)` |
| `CapsuleGeometry` | `(radius=1, height=1, capSegments=4, radialSegments=8, heightSegments=1)` (`height` = length of the middle section) |
| `TorusGeometry` | `(radius=1, tube=0.4, radialSegments=12, tubularSegments=48, arc=2PI, thetaStart=0, thetaLength=2PI)` |
| `TorusKnotGeometry` | `(radius=1, tube=0.4, tubularSegments=64, radialSegments=8, p=2, q=3)` |
| `TetrahedronGeometry` / `OctahedronGeometry` / `DodecahedronGeometry` / `IcosahedronGeometry` | `(radius=1, detail=0)` (detail>0 subdivides; high detail on Icosahedron = geodesic sphere) |
| `PolyhedronGeometry` | `(vertices=[], indices=[], radius=1, detail=0)` (flat arrays; base of the 4 above) |
| `LatheGeometry` | `(points=[Vector2...], segments=12, phiStart=0, phiLength=2PI)` (revolves around Y; points x>=0) |
| `ExtrudeGeometry` | `(shapes=Shape|Shape[], options={})` |
| `ShapeGeometry` | `(shapes=Shape|Shape[], curveSegments=12)` |
| `TubeGeometry` | `(path=Curve3, tubularSegments=64, radius=1, radialSegments=8, closed=false)` |
| `EdgesGeometry` | `(geometry=null, thresholdAngle=1)` (degrees; edges between faces whose angle > threshold) |
| `WireframeGeometry` | `(geometry=null)` (every triangle edge) |

Addons geometries: `TextGeometry`, `RoundedBoxGeometry`, `ConvexGeometry`, `DecalGeometry`, `ParametricGeometry`, `LoftGeometry`, `TeapotGeometry`, `BoxLineGeometry`, etc.: see `geometry.md`.

Gotchas:
- Segment counts: sphere 32x16 = 1024 quads (~1k tris). More segments is not always visibly better; for many spheres use 12-24.
- `PlaneGeometry` default is vertical (XY); the ground needs `mesh.rotation.x = -Math.PI / 2`.
- Single-sided by default (`material.side = THREE.FrontSide`); planes/rings/circles/shapes vanish from behind: set `side: THREE.DoubleSide` (slower) or flip the camera. This is the FAQ "part of my object is invisible" cause.
- Multi-material groups: `BoxGeometry` has 6 groups, `CylinderGeometry` 3 (side, top, bottom), `ConeGeometry` 2; pass `material` as an array of that length. Texture atlases + UVs are faster than multiple materials.
- Text/other geometry origin: left-baseline for `TextGeometry`; center it with `geometry.center()` or `geometry.boundingBox.getCenter(mesh.position).multiplyScalar(-1)` after `computeBoundingBox()`.
- Points: `new THREE.Points(geometry, new THREE.PointsMaterial({ size: 0.2, sizeAttenuation: true }))`; `size` is world units when `sizeAttenuation` is true, pixels when false.
- Lines: `LineSegments(geometry, LineBasicMaterial)` takes 2 vertices per segment; `Line` is a connected strip; `LineLoop` closes it.
- Color from HSL: `material.color.setHSL(h, s, l)` with h, s, l in 0..1.

---

## 9. Materials quick map

Set at construction (`new MeshStandardMaterial({ color: 0xff8844 })`; hex number or CSS string) or later (`material.color.set('red')`, `.color.setRGB`, `.setHSL`). `Color` properties are objects: mutate, do not assign.

Cost ascending: `MeshBasicMaterial` (unlit) -> `MeshLambertMaterial` (manual: lighting computed at vertices; cheaper than Phong) -> `MeshPhongMaterial` (per-pixel, `shininess=30`, specular) -> `MeshStandardMaterial` (PBR: `roughness`, `metalness`) -> `MeshPhysicalMaterial` (Standard + `clearcoat`, `clearcoatRoughness`, transmission, etc.).
Specials: `MeshToonMaterial` (gradientMap), `MeshNormalMaterial` (view-space normals), `MeshDepthMaterial`, `ShadowMaterial` (only draws received shadow; transparent ground), `MeshMatcapMaterial`, `PointsMaterial`, `LineBasicMaterial`, `LineDashedMaterial` (call `line.computeLineDistances()`), `SpriteMaterial`, `ShaderMaterial` / `RawShaderMaterial` (WebGL GLSL only).

Common `Material` props: `side` (`FrontSide` default, `BackSide`, `DoubleSide`), `flatShading=false`, `transparent`, `opacity`, `alphaTest`, `depthTest`, `depthWrite`, `fog=true`, `wireframe`, `vertexColors`, `visible`.
Notes: `transparent: true` is needed for `opacity < 1` to blend; transparent objects are sorted back-to-front by object center (use `renderOrder`/`depthWrite=false` to resolve artifacts); `material.dispose()` when done.
A `RectAreaLight` only affects `MeshStandardMaterial` and `MeshPhysicalMaterial`.

---

## 10. Textures basics

```js
const loader = new THREE.TextureLoader();
const tex = loader.load('/wall.jpg');                    // returns immediately; transparent until loaded
tex.colorSpace = THREE.SRGBColorSpace;                   // REQUIRED for color/albedo/emissive images
material.map = tex;                                      // data maps (normal, roughness, ao, metalness, bump): leave NoColorSpace (default)
```
Color space rule: textures holding **color** (`map`, `emissiveMap`, `specularColorMap`, `sheenColorMap`, matcap) -> `SRGBColorSpace`. Data textures -> default `NoColorSpace` (treated as linear). Forgetting it makes colors washed out or too dark. `ColorManagement.enabled = true` by default; working space is linear-sRGB; `renderer.outputColorSpace = SRGBColorSpace` by default. Hex colors (`new Color(0xff8800)`) are converted from sRGB to linear automatically.

Loading patterns:
```js
// callback
loader.load(url, (t) => { t.colorSpace = THREE.SRGBColorSpace; /* use */ }, undefined, (err) => console.error(err));
// promise
const t = await loader.loadAsync(url);
// many assets + progress
const manager = new THREE.LoadingManager();
manager.onProgress = (url, loaded, total) => { /* loaded/total */ };
manager.onLoad = () => { /* all done */ };
const tl = new THREE.TextureLoader(manager);
```
Cross-origin images need CORS headers on the server (otherwise WebGL cannot use them; imgur/flickr/github send them).

Wrap / repeat / offset / rotation:
```js
tex.wrapS = tex.wrapT = THREE.RepeatWrapping;   // ClampToEdgeWrapping (default) | RepeatWrapping | MirroredRepeatWrapping
tex.repeat.set(4, 2);                           // times across the surface
tex.offset.set(0.5, 0.25);                      // units of texture size
tex.center.set(0.5, 0.5);                       // rotation pivot; default (0,0) = bottom-left
tex.rotation = THREE.MathUtils.degToRad(45);    // radians, CCW
tex.needsUpdate = true;                         // REQUIRED after changing wrapS/wrapT; repeat/offset/rotation/center apply automatically
```
Repeat >1 without `RepeatWrapping` just clamps. `Texture.matrixAutoUpdate=true` builds `texture.matrix` from offset/repeat/rotation/center; set false to supply `texture.matrix` (or call `updateMatrix()`). `texture.channel` picks the UV set (0 = `uv`, 1 = `uv1`, ...); `aoMap`/`lightMap` conventionally use `uv1`.

Filtering:
- `magFilter` (texel covers >1 pixel): `NearestFilter` (pixelated) or `LinearFilter` (default).
- `minFilter` (texel < 1 pixel), default `LinearMipmapLinearFilter` (best, trilinear): `NearestFilter`, `LinearFilter`, `NearestMipmapNearestFilter`, `NearestMipmapLinearFilter`, `LinearMipmapNearestFilter`, `LinearMipmapLinearFilter`. Non-mipmap filters flicker when minified.
- `generateMipmaps = true` default; set `false` when providing `mipmaps` manually or when using non-mip `minFilter` (saves memory). Render targets default `generateMipmaps=false`, `minFilter=LinearFilter`.
- `anisotropy` (default 1, `Texture.DEFAULT_ANISOTROPY`): sharper at grazing angles; `tex.anisotropy = renderer.capabilities.getMaxAnisotropy()`.
- `flipY = true` default (ignored for `ImageBitmap`: flip when creating the bitmap; compressed textures usually have `flipY=false`). `premultiplyAlpha=false`.

Memory: GPU textures are uncompressed: about `width * height * 4 * 1.33` bytes (with mips). A 3024x3761 JPG ~ 60 MB regardless of file size. Keep dimensions small and power-of-two friendly; for shipping, use KTX2/Basis compressed textures (KTX2Loader). JPG vs PNG only affects download size and alpha; use PNG/lossless for data maps.

Update rules: image/canvas/video/data textures -> set `texture.needsUpdate = true` after changing contents. `VideoTexture` self-updates per frame. Render target textures update automatically. `tex.dispose()` frees GPU memory. Partial uploads for `DataTexture`: `tex.addUpdateRange(start, count)`, `tex.clearUpdateRanges()`.
`texture.version` increments on each `needsUpdate = true`. Multiple Textures can share one `source` (`texture.source`) to avoid re-upload (spritesheets).

Other texture classes: `CanvasTexture`, `VideoTexture`, `DataTexture`, `Data3DTexture`, `DataArrayTexture`, `CubeTexture`, `CompressedTexture`, `DepthTexture`, `FramebufferTexture`. Env maps: `scene.environment = pmremTexture` (see `PMREMGenerator`, `RGBELoader`); `scene.background` accepts `Color`, `Texture`, `CubeTexture`; `backgroundBlurriness`, `backgroundIntensity`, `backgroundRotation`, `environmentIntensity`, `environmentRotation` also on `Scene`.

---

## 11. Lights overview

Every light adds per-fragment cost, and shadow-casting lights re-render the scene. Use as few as possible. Lights share `color`, `intensity`; `Light.dispose()`.

| Light | Constructor (defaults) | Notes |
|---|---|---|
| `AmbientLight` | `(color=0xffffff, intensity=1)` | uniform, no direction, no shadows; just lifts darks |
| `HemisphereLight` | `(skyColor, groundColor, intensity=1)` | tint by surface normal up/down; no shadows; position irrelevant |
| `DirectionalLight` | `(color, intensity=1)` | parallel rays, `position` -> `target` (default target at origin, `target.position`). Sun. Casts shadows (orthographic shadow camera) |
| `PointLight` | `(color, intensity=1, distance=0, decay=2)` | omni; `distance=0` = infinite; `decay=2` = physical inverse-square; `power` property in lumens; shadows cost 6 renders |
| `SpotLight` | `(color, intensity=1, distance=0, angle=PI/3, penumbra=0, decay=2)` | cone, `angle` radians (max PI/2), `penumbra` 0..1 soft edge; needs `target` like Directional; shadow camera fov tied to `angle` |
| `RectAreaLight` | `(color, intensity=1, width=10, height=10)` | no target, uses rotation; Standard/Physical materials only; needs `RectAreaLightUniformsLib.init()` (from `three/addons/lights/RectAreaLightUniformsLib.js`); no shadows |
| `LightProbe` | `(sh, intensity=1)` | spherical-harmonics ambient lighting |

Gotchas:
- A `DirectionalLight`/`SpotLight` `target` is an Object3D not in the scene by default: if you move `light.target.position`, do `scene.add(light.target)` so its matrix updates.
- Intensity units are physically-based (r155+ removed `useLegacyLights`): PointLight/SpotLight intensity in candela, falloff `decay=2`. Old scenes copied from pre-r155 look dark: raise intensity (often x PI or tens-hundreds for point lights at distance).
- `MeshBasicMaterial` ignores lights. Only `Standard/Physical/Phong/Lambert/Toon` react.
- Changing the **number or type** of lights after first render recompiles lit materials (hitch). Create lights up front and keep the count constant (manual: emulate toggling with zero-intensity lights).
- Image-based lighting (`scene.environment`) is usually the best base light for PBR; then add one directional light.
- Helpers: `DirectionalLightHelper(light, size)`, `PointLightHelper`, `SpotLightHelper`, `HemisphereLightHelper`, `RectAreaLightHelper` (addon, child of the light); call `helper.update()` after changing the light.

---

## 12. Shadows

Shadow maps: for each shadow-casting light, every `castShadow` object is rendered from the light's point of view into a depth map; then the main pass samples it. 20 casters x 5 shadow lights = 6 full-scene passes; a `PointLight` shadow = 6 passes by itself. Typical budget: one shadowing directional light.

Only `DirectionalLight`, `PointLight`, `SpotLight` cast shadows.

```js
renderer.shadowMap.enabled = true;                         // 1. renderer (default false)
renderer.shadowMap.type = THREE.PCFShadowMap;              //    BasicShadowMap | PCFShadowMap (default) | VSMShadowMap

light.castShadow = true;                                   // 2. light
light.shadow.mapSize.set(2048, 2048);                      //    default 512x512; powers of two
const sc = light.shadow.camera;                            //    DirectionalLight: OrthographicCamera
sc.left = -20; sc.right = 20; sc.top = 20; sc.bottom = -20; sc.near = 0.5; sc.far = 60;
sc.updateProjectionMatrix();                               //    after editing shadow camera
light.shadow.bias = -0.0005;                               //    tiny (1e-4 magnitude) values; fixes acne
light.shadow.normalBias = 0.02;                            //    offset along normal; fixes acne at grazing angles
light.shadow.radius = 4;                                   //    blur (PCF with >1, VSM); no effect for BasicShadowMap
// light.shadow.blurSamples = 8   (VSM), light.shadow.intensity = 1 (0..1)

mesh.castShadow = true;                                    // 3. per object
ground.receiveShadow = true;                               //    ground: receive only
scene.add(new THREE.CameraHelper(light.shadow.camera));    // debug the shadow frustum
```
`PCFSoftShadowMap` is **removed**: the constant still exists but WebGLShadowMap logs "PCFSoftShadowMap has been removed. Using PCFShadowMap instead." Use `PCFShadowMap` (soft with `radius`) or `VSMShadowMap`.

Tuning logic:
- Missing/cropped shadows = shadow camera box too small or `near/far` wrong; objects outside the box neither cast nor receive correctly. Visualize with `CameraHelper`.
- Blocky shadows = box too large for `mapSize`. Shrink the box to the area that matters; raise `mapSize` last (memory + time). Texel size ~ box width / mapSize.
- Shadow acne (stripes/moire on lit surfaces) = bias too small; peter-panning (shadow detached from the object) = bias/normalBias too large. Start `normalBias` ~0.01-0.05, bias ~ -0.0001 to -0.001.
- `SpotLight` shadow camera is a `PerspectiveCamera` driven by `angle` (fov), `aspect` auto from mapSize; you can set `shadow.camera.near/far`.
- `PointLight` shadow: only `near/far` matter (cube of 6 views).
- Static scene: `light.shadow.autoUpdate = false` then `light.shadow.needsUpdate = true` for one refresh; or `renderer.shadowMap.autoUpdate = false` + `renderer.shadowMap.needsUpdate = true`.
- Backfaces: `material.shadowSide` (inherited `Material`) controls which faces cast; thin single-sided planes may need `DoubleSide`.
- `Object3D.customDepthMaterial` / `customDistanceMaterial` for alpha-clipped or displaced casters (e.g. alphaTest leaves, vertex-displaced meshes need a matching depth material).
- `onBeforeShadow/onAfterShadow` hooks on Object3D.
- Cheap alternatives: fake blob shadows (a transparent plane with a gradient texture slightly above the ground, `depthWrite: false` to avoid z-fighting between shadow planes), baked `lightMap`/`aoMap`, `ShadowMaterial` on the ground, contact shadows.

WebGPURenderer: same `castShadow/receiveShadow/light.shadow.*` API, plus `shadow.biasNode`; shadow types handled by the node renderer.

---

## 13. Fog

```js
scene.fog = new THREE.Fog(0xcccccc, 10, 50);        // color, near, far (docs defaults near=1, far=1000): linear between near and far
scene.fog = new THREE.FogExp2(0xcccccc, 0.02);      // color, density (default 0.00025); exponential squared, no near/far
scene.background = new THREE.Color(0xcccccc);       // MUST match fog color or the horizon shows a seam
```
- Distances are from the **camera**, in world units. Fog is applied per rendered fragment; it does not affect `scene.background`, so match it yourself. Skybox backgrounds will not fade.
- `material.fog = false` opts a material out (cockpits, UI, skyboxes, sprites you want crisp). `SpriteMaterial`/`PointsMaterial` have their own `fog` flag.
- Keep `near < far`.
- `Fog`/`FogExp2` props: `color`, `name`, `near/far` or `density`; `clone()`, `toJSON()`; `isFog`/`isFogExp2`.
- Adding/removing fog on a live scene or toggling `material.fog` changes the shader program: use `material.needsUpdate = true`, or keep zero-density fog (e.g. `FogExp2(color, 0)`) to avoid recompiles.
- With `ShaderMaterial`, set `fog: true` and include fog uniforms/chunks yourself.

---

## 14. Render targets

A render target is a texture you can render into, then use as a texture.

```js
const rt = new THREE.WebGLRenderTarget(512, 512, {
  depthBuffer: true, stencilBuffer: false,
  samples: 4,                         // MSAA (default 0)
  type: THREE.HalfFloatType,          // HDR; default UnsignedByteType
  // generateMipmaps: false, minFilter: LinearFilter (defaults), colorSpace: default NoColorSpace
});
const rtCamera = new THREE.PerspectiveCamera(75, 1, 0.1, 5);     // aspect = render target's, not the canvas's
const rtScene = new THREE.Scene();

renderer.setRenderTarget(rt);
renderer.render(rtScene, rtCamera);
renderer.setRenderTarget(null);                                  // back to canvas
renderer.render(scene, camera);

material.map = rt.texture;                                       // use result
```
- `rt.texture` (single) or `rt.textures` (MRT via `count` option). `rt.setSize(w, h)` on resize; `rt.dispose()` when done. Options (`RenderTarget~Options`): `generateMipmaps`, `magFilter`, `minFilter`, `format`, `type`, `internalFormat`, `wrapS/T`, `anisotropy`, `colorSpace`, `depthBuffer`, `stencilBuffer`, `depthTexture`, `samples`, `count`, `depth`, `resolveColorBuffer/DepthBuffer/StencilBuffer`, `storeMultisampled*Buffer`, `multiview`, `useArrayDepthTexture`.
- Don't sample a render target's texture in a material while rendering into the same target (feedback loop). Skip `depthBuffer`/`stencilBuffer` if not needed.
- Background of the RT scene clears the RT: `rtScene.background = new Color('red')` makes the texture red; otherwise it clears to the renderer clear color/alpha.
- Rendering to a target happens in linear space with no tone mapping or sRGB output conversion unless you add it yourself (post-processing output pass does this). Textures read back from float targets are linear.
- Read back: `renderer.readRenderTargetPixels(rt, x, y, w, h, typedArray)`; `readRenderTargetPixelsAsync(...)` returns a Promise (preferred; avoids GPU stall).
- Variants: `WebGLCubeRenderTarget`, `WebGL3DRenderTarget`, `WebGLArrayRenderTarget`; `renderer.setRenderTarget(rt, activeCubeFace, activeMipmapLevel)`.
- Uses: shadows (internal), picking (GPU color id), mirrors/monitors, post-processing chains (see manual `how-to-use-post-processing`, `EffectComposer`), env map capture (`CubeCamera`).
- Viewport/scissor per target: `rt.viewport`, `rt.scissor`, `rt.scissorTest`.

---

## 15. How to update things

| Thing | Rule |
|---|---|
| Object transforms | Auto per frame when `matrixAutoUpdate` (default) and object is under the rendered scene. If `matrixAutoUpdate=false` call `updateMatrix()`. |
| Camera `fov/aspect/near/far/zoom/left/right/top/bottom` | `camera.updateProjectionMatrix()`. Position/rotation need nothing. |
| BufferGeometry attribute **values** | Edit the typed array / `setXYZ`, then `attribute.needsUpdate = true` (required after first render). |
| BufferGeometry attribute **size** (vertex count) | Cannot resize a buffer. Preallocate max size and use `geometry.setDrawRange(0, n)`; otherwise create a new geometry (and `dispose()` the old one). Adding/removing an attribute or switching index presence = new geometry. |
| Bounding volumes after moving vertices | `geometry.computeBoundingBox(); geometry.computeBoundingSphere();` (frustum culling and raycasting use them). |
| `InstancedMesh` | after `setMatrixAt/setColorAt`: `instanceMatrix.needsUpdate = true`, `instanceColor.needsUpdate = true`; `mesh.computeBoundingBox()` / `computeBoundingSphere()` (own bounding volumes supersede geometry's). `mesh.count` sets visible instance count (WebGL). |
| `SkinnedMesh` | has own `boundingBox`/`boundingSphere`; `computeBoundingBox()/computeBoundingSphere()` use the current bone pose. |
| Material uniforms-like values (`color`, `opacity`, `roughness`, `map` swapped for another texture of same kind, `emissive`, ...) | change freely; sent each frame. Render state (`depthTest`, `blending`, `polygonOffset`, `side`...) can change any time. |
| Material **shader-affecting** switches after first render: presence of a map (null <-> texture), fog, vertexColors, morph targets/skinning, shadow map, `alphaTest`, `transparent` (sometimes), number/type of lights | `material.needsUpdate = true`: recompiles the program (slow, hitch). Prefer dummy values: white 1x1 texture, zero-intensity light, zero-density fog. |
| Material per-face assignment | You can swap the material for a group, but not how geometry is divided into groups. Small number of variants: pre-split. Large: drive look from attributes/textures. |
| Textures (image/canvas/video/data) | `texture.needsUpdate = true` after content change; also after changing `wrapS/wrapT`. Render targets are automatic. `DataTexture` partial update: `addUpdateRange`. |
| Replace a texture's `image`/size | New size/format: dispose or create a new Texture; GPU storage is immutable per size. |
| Shadows (static scene) | `light.shadow.autoUpdate=false; light.shadow.needsUpdate=true`. |
| Helpers | call `helper.update()` after watched object changes. |
| Raycast against moved geometry | recompute bounding sphere; update `matrixWorld`. |

Dispose list (leaks otherwise): `geometry.dispose()`, `material.dispose()`, `texture.dispose()` (including each map on a material), `renderTarget.dispose()`, `renderer.dispose()`, `light.shadow.dispose()` / `object.dispose()`. Removing from the scene does not free GPU memory. See manual `cleanup` / `how-to-dispose-of-objects`.

Dynamic line example (preallocated, draw range):
```js
const MAX = 500;
const geo = new THREE.BufferGeometry();
geo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(MAX * 3), 3));
geo.setDrawRange(0, 2);
const line = new THREE.Line(geo, new THREE.LineBasicMaterial({ color: 0xff0000 }));
// per frame
const pos = line.geometry.getAttribute('position');
pos.setXYZ(i, x, y, z); pos.needsUpdate = true;
line.geometry.setDrawRange(0, n);
line.geometry.computeBoundingSphere();
```

---

## 16. Layers and Raycaster

### Layers
32 layers (0-31), bitmask `layers.mask`; every Object3D defaults to layer 0. An object renders for a camera if `object.layers.test(camera.layers)` (at least one common layer). Methods: `set(n)` (only n), `enable(n)`, `disable(n)`, `toggle(n)`, `enableAll()`, `disableAll()`, `isEnabled(n)`, `test(layers)`.
```js
mesh.layers.set(1);              // only visible to cameras with layer 1 enabled
camera.layers.enable(1);         // camera sees 0 and 1
raycaster.layers.set(1);         // raycaster only hits layer-1 objects
```
Gotcha: `object.layers.set(1)` removes layer 0, so a default camera stops seeing it; use `enable(1)` to add. Bloom-selective and "hide from main camera" tricks rely on this.

### Raycaster( origin, direction, near = 0, far = Infinity )
```js
const raycaster = new THREE.Raycaster();
const pointer = new THREE.Vector2();
canvas.addEventListener('pointermove', (e) => {
  const r = canvas.getBoundingClientRect();
  pointer.x = ((e.clientX - r.left) / r.width) * 2 - 1;        // NDC -1..1
  pointer.y = -((e.clientY - r.top) / r.height) * 2 + 1;       // Y flipped
});
// per frame / on click
raycaster.setFromCamera(pointer, camera);                      // also stores raycaster.camera (needed for Sprites)
const hits = raycaster.intersectObjects(scene.children, true); // recursive; sorted nearest first
if (hits[0]) { const { object, point, distance, face, faceIndex, uv, instanceId } = hits[0]; }
```
- API: `set(origin, dir)`, `setFromCamera(coords, camera)`, `setFromXRController(controller)`, `intersectObject(obj, recursive, target?)`, `intersectObjects(array, recursive, target?)`. Props: `ray`, `near`, `far`, `camera`, `layers`, `params = { Mesh: {}, Line: { threshold: 1 }, LOD: {}, Points: { threshold: 1 }, Sprite: {} }` (thresholds are world units; tune for thin lines/points).
- Intersection fields (from docs): `distance`, `distanceToRay` (Points), `point` (world), `face`, `faceIndex`, `object`, plus `uv`, `instanceId` etc. where applicable.
- Meshes are hit only from the front side unless `material.side = DoubleSide`.
- Uses `matrixWorld` and the geometry bounding sphere; moved vertices need recomputed bounds; `visible=false` objects are still tested unless layers exclude them.
- Slow for big meshes (no BVH built in): use `three-mesh-bvh` or GPU picking via a render target.
- Pointer coords must be relative to the canvas rect, not the window, when the canvas is not full-window.

---

## 17. Compatibility, FAQ, ecosystem

```js
import WebGL from 'three/addons/capabilities/WebGL.js';
if (WebGL.isWebGL2Available()) init(); else document.body.appendChild(WebGL.getWebGL2ErrorMessage());
// WebGPU: three/addons/capabilities/WebGPU.js (file exists) for feature detection
```
WebGLRenderer requires WebGL 2 in r186 (WebGL 1 support removed). `renderer.capabilities` exposes limits (`getMaxAnisotropy()`, etc.).

FAQ digest:
- Best format: **glTF/GLB** (`GLTFLoader`); FBX/Collada/OBJ exist but start with glTF.
- three.js does not validate inputs (NaN geometry, bad ranges): garbage in, garbage out; a NaN in a position gives an empty bounding sphere and a vanished object.
- Part of mesh invisible: face culling -> `material.side = THREE.DoubleSide`.
- Node.js: needs shims (headless-gl, jsdom-global) or swapping `TextureLoader`; most work is browser-only.
- Keep scale on resize: adjust `fov`, see section 4.

Ecosystem (community, unofficial): physics (cannon-es, rapier, Jolt, ammo.js, Oimo.js, enable3d), postprocessing (`postprocessing` by vanruesc), BVH raycasting (three-mesh-bvh), path tracing (three-gpu-pathtracer), 3D tiles (3d-tiles-renderer-js), fat lines (THREE.MeshLine; official Line2 in addons), text (troika-three-text, three-mesh-ui), particles (three.quarks, three-nebula), IK (THREE.IK, closed-chain-ik), game AI (yuka, three-pathfinding, recast-navigation-js), frameworks (react-three-fiber, Threlte for Svelte, TresJS for Vue, A-Frame, Lume, Needle Engine, threepipe, Giro3D). Learning: threejs-journey.com, discoverthreejs.com, discourse.threejs.org (official help), Stack Overflow `three.js`.

Common mistakes checklist:
1. Black screen: camera inside object / looking away / `near` > distance / no light for lit material / canvas has 0 CSS height / texture 404 / forgot `scene.add`.
2. Stretched objects: `camera.aspect` not updated or `updateProjectionMatrix()` forgotten.
3. Blurry/blocky: drawing buffer smaller than display (resize helper missing) or pixel ratio 1 on HiDPI.
4. Washed-out textures: missing `texture.colorSpace = SRGBColorSpace` on color maps.
5. Edits to buffer values not showing: missing `attribute.needsUpdate = true`.
6. Z-fighting: near too small / far too large / coplanar surfaces (offset or `polygonOffset`).
7. Memory growth: not disposing geometries/materials/textures/render targets.
8. Using `Clock` (deprecated) instead of `Timer`; hand-rolled rAF instead of `setAnimationLoop`.

---

## See also
- API: `references/api/Object3D.md`, `Scene.md`, `Camera.md`, `PerspectiveCamera.md`, `OrthographicCamera.md`, `WebGLRenderer.md`, `WebGPURenderer.md`, `Renderer.md`, `Mesh.md`, `Group.md`, `Texture.md`, `TextureLoader.md`, `LoadingManager.md`, `Fog.md`, `FogExp2.md`, `Timer.md`, `Clock.md`, `Layers.md`, `Raycaster.md`, `LightShadow.md`, `DirectionalLight.md`, `PointLight.md`, `SpotLight.md`, `RectAreaLight.md`, `RenderTarget.md`, `WebGLRenderTarget.md`, `InstancedMesh.md`
- Manual: https://threejs.org/manual/#fundamentals, #prerequisites, #setup, #installation, #creating-a-scene, #responsive, #scenegraph, #primitives, #materials, #textures, #lights, #cameras, #shadows, #fog, #rendertargets, #matrix-transformations, #how-to-update-things, #webgl-compatibility-check, #faq, #libraries-and-plugins, #useful-links
- Docs: https://threejs.org/docs/#Object3D, #Scene, #PerspectiveCamera, #OrthographicCamera, #WebGLRenderer, #Mesh, #Group, #Texture, #Fog, #FogExp2, #Timer, #Layers, #Raycaster
- Sibling references: `geometry.md` (BufferGeometry, lines, text, curves), `api-index.txt`
