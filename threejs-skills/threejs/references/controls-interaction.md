# Controls and interaction (three.js r186)

When to read this: camera controls (Orbit/Map/Trackball/Arcball/Fly/FirstPerson/PointerLock), moving objects (DragControls, TransformControls), picking (Raycaster, GPU picking), box selection, and HTML overlays/labels (CSS2D/CSS3D, projected DOM). All controls are addons (`three/addons/controls/...`) and work with both WebGLRenderer and WebGPURenderer (they only need a camera and a DOM element). Differences are called out where they exist (GPU picking readback).

## Table of contents
1. Controls base class and common rules
2. OrbitControls (+ MapControls)
3. TrackballControls, ArcballControls
4. FlyControls, FirstPersonControls, PointerLockControls
5. DragControls
6. TransformControls (getHelper change)
7. Raycaster picking
8. GPU picking
9. SelectionBox / SelectionHelper
10. HTML labels: projected DOM, CSS2DRenderer, CSS3DRenderer
11. HTMLMesh, InteractiveGroup, InteractionManager
12. Input plumbing: pointer vs mouse, touch, keyboard, resize, screenshots, transparent canvas
13. Gotchas
14. See also

## 1. Controls base class

`Controls` (abstract): `object`, `domElement`, `enabled`, `state`, `keys`, `mouseButtons`, `touches`, `connect(element)`, `disconnect()`, `update(delta)`, `dispose()`. Extended by Orbit, Map, Trackball, Arcball, Fly, FirstPerson, PointerLock, Drag, Transform.

- Always call `controls.dispose()` when tearing down: removes DOM listeners (OrbitControls also restores `touch-action`). `disconnect()`/`connect(el)` re-parent listeners without destroying.
- `controls.enabled = false` stops handling input (use it while another tool, e.g. TransformControls, is dragging).
- Pass the **canvas** (`renderer.domElement`) as `domElement`, not `document`/`window` (except `listenToKeyEvents`). If a CSS2D/CSS3D layer sits on top of the canvas, pass that layer's `domElement` instead, otherwise it swallows pointer events (see section 10).
- Orbit/Map use pointer events and set `touch-action: none` on the element; canvas needs a real size.
- Camera moved by controls: do not also set `camera.position` each frame. To change the view call `controls.target.set(...)` / `camera.position.set(...)` then `controls.update()`.

## 2. OrbitControls and MapControls

```js
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;      // inertia: REQUIRES controls.update() every frame
controls.dampingFactor = 0.05;      // default 0.05
controls.target.set(0, 1, 0);       // orbit pivot; call update() after changing
controls.minDistance = 2; controls.maxDistance = 50;       // PerspectiveCamera dolly limits
controls.minZoom = 0.5;   controls.maxZoom = 4;            // OrthographicCamera zoom limits
controls.minPolarAngle = 0; controls.maxPolarAngle = Math.PI / 2;   // 0=top, PI=bottom; PI/2 keeps camera above ground
controls.minAzimuthAngle = -Math.PI / 4; controls.maxAzimuthAngle = Math.PI / 4;  // default +-Infinity
controls.enablePan = true; controls.enableZoom = true; controls.enableRotate = true;
controls.screenSpacePanning = true;  // false: pan in plane orthogonal to camera.up (ground-plane panning)
controls.zoomToCursor = true;        // dolly toward pointer instead of target
controls.autoRotate = true; controls.autoRotateSpeed = 2.0;
controls.rotateSpeed = 1; controls.zoomSpeed = 1; controls.panSpeed = 1;
controls.minTargetRadius = 0; controls.maxTargetRadius = Infinity;   // clamp target around controls.cursor (Vector3)
controls.cursorStyle = 'grab';       // 'auto' | 'grab'

controls.mouseButtons = { LEFT: THREE.MOUSE.ROTATE, MIDDLE: THREE.MOUSE.DOLLY, RIGHT: THREE.MOUSE.PAN };
controls.touches = { ONE: THREE.TOUCH.ROTATE, TWO: THREE.TOUCH.DOLLY_PAN };

controls.listenToKeyEvents(window);  // arrow-key panning; remember stopListenToKeyEvents()
controls.keys = { LEFT: 'ArrowLeft', UP: 'ArrowUp', RIGHT: 'ArrowRight', BOTTOM: 'ArrowDown' };  // keyPanSpeed, keyRotateSpeed

renderer.setAnimationLoop(() => {
  controls.update();                 // or controls.update(deltaSeconds) for frame-rate independent autoRotate/damping
  renderer.render(scene, camera);
});
```

- `update()` returns/does work only when needed, but must be called every frame when `enableDamping` or `autoRotate` is on. Without damping, call it after any programmatic change to camera/target.
- Events: `controls.addEventListener('change' | 'start' | 'end', fn)`. `change` is the hook for render-on-demand (`rendering-on-demand` manual): re-render only when it fires (with damping you still need the loop or keep calling `update()` until settled).
- State: `saveState()`, `reset()` (restores `target0/position0/zoom0`), `getDistance()`, `getPolarAngle()`, `getAzimuthalAngle()`; imperative moves: `rotateLeft(a)`, `rotateUp(a)`, `pan(dx,dy)`, `dollyIn(s)`, `dollyOut(s)`.
- Camera `up` other than +Y is supported (OrbitControls takes `camera.up` at construction time; set `camera.up` before constructing).
- `MapControls` (`import { MapControls } from 'three/addons/controls/MapControls.js'`) = OrbitControls with `mouseButtons {LEFT: PAN, MIDDLE: DOLLY, RIGHT: ROTATE}`, `touches {ONE: PAN, TWO: DOLLY_ROTATE}`, `screenSpacePanning = false`.
- `target` changes do not move the camera; both move together only when panning. `minDistance`/`maxDistance` apply to camera-to-target distance.
- Orthographic camera: zoom is `camera.zoom`; `controls.update()` calls `updateProjectionMatrix`.

## 3. TrackballControls and ArcballControls

```js
import { TrackballControls } from 'three/addons/controls/TrackballControls.js';
const c = new TrackballControls(camera, renderer.domElement);
c.rotateSpeed = 2; c.zoomSpeed = 1.2; c.panSpeed = 0.8;
c.noRotate = false; c.noZoom = false; c.noPan = false;
c.staticMoving = false;   // true = no inertia
c.dynamicDampingFactor = 0.2;
c.minDistance = 1; c.maxDistance = 100;
c.keys = ['KeyA', 'KeyS', 'KeyD'];   // rotate / zoom / pan modifier keys (Array<string>)
// loop: c.update();   on resize: c.handleResize();   c.reset();
```

TrackballControls: unconstrained rotation (no fixed up, camera can roll); `update()` required every frame (it does the inertia); call `handleResize()` after the canvas size changes. Events `start | change | end`.

```js
import { ArcballControls } from 'three/addons/controls/ArcballControls.js';
const arc = new ArcballControls(camera, renderer.domElement, scene);   // NOTE 3rd arg: scene (for gizmos)
arc.setGizmosVisible(false);
arc.enableAnimations = true; arc.dampingFactor = 25; arc.wMax = 20;   // inertia
arc.enableFocus = true; arc.enableGrid = false; arc.cursorZoom = false;
arc.minDistance = 0; arc.maxDistance = Infinity; arc.minFov = 5; arc.maxFov = 90;
arc.setMouseAction('ROTATE', 0, 'SHIFT');    // operation: 'PAN'|'ROTATE'|'ZOOM'|'FOV'; mouse: 0|1|2|'WHEEL'; key: 'CTRL'|'SHIFT'
arc.saveState(); arc.reset(); arc.copyState(); arc.pasteState();
arc.setCamera(otherCamera);
arc.update();   // call after programmatic camera changes
```

ArcballControls: virtual trackball with on-screen gizmo, full touch support, FOV zoom, double-click focus. Dispose it with `dispose()`; `disposeGrid()` for the grid helper. Example `misc_controls_arcball`.

## 4. FlyControls, FirstPersonControls, PointerLockControls

```js
import { FlyControls } from 'three/addons/controls/FlyControls.js';
const fly = new FlyControls(camera, renderer.domElement);
fly.movementSpeed = 10; fly.rollSpeed = Math.PI / 24; fly.dragToLook = true; fly.autoForward = false;
// loop: fly.update(deltaSeconds);       // delta is required: speed is units/second
```
Default keys: WASD move, R/F up/down, Q/E roll, arrows pitch/yaw (KeyW etc. in source). Event: `change`.

```js
import { FirstPersonControls } from 'three/addons/controls/FirstPersonControls.js';
const fp = new FirstPersonControls(camera, renderer.domElement);
fp.movementSpeed = 5; fp.lookSpeed = 0.1; fp.lookVertical = true; fp.constrainVertical = true;
fp.verticalMin = 1.0; fp.verticalMax = 2.0; fp.autoForward = false; fp.heightSpeed = false;
fp.lookAt(0, 0, 0);       // sets orientation (x|Vector3,y,z)
// loop: fp.update(deltaSeconds);  on resize: fp.handleResize();
```
Look is driven by pointer drag (`mouseDragOn` is true while a pointer is down); WASD/arrows/R/F move.

```js
import { PointerLockControls } from 'three/addons/controls/PointerLockControls.js';
const pl = new PointerLockControls(camera, document.body);
button.addEventListener('click', () => pl.lock());      // MUST originate from a user gesture; lock(unadjustedMovement?) optional raw input
pl.addEventListener('lock', () => hideMenu());
pl.addEventListener('unlock', () => showMenu());        // Esc exits lock; browser enforces it
pl.pointerSpeed = 1; pl.minPolarAngle = 0; pl.maxPolarAngle = Math.PI;
// movement is yours: read keys, then
pl.moveForward(dist); pl.moveRight(dist);   // moves camera along XZ plane (not pitch-dependent)
pl.getDirection(new THREE.Vector3());        // look direction; pl.isLocked boolean
```
PointerLockControls has no `update()` and no movement/physics; build velocity/gravity yourself (example `misc_controls_pointerlock`).

## 5. DragControls

```js
import { DragControls } from 'three/addons/controls/DragControls.js';
const drag = new DragControls(draggableObjects, camera, renderer.domElement);   // objects = Array<Object3D>
drag.recursive = true;        // include descendants in hit tests
drag.transformGroup = false;  // true: drag the parent Group of the hit object
drag.rotateSpeed = 1;         // rotate mode speed
drag.addEventListener('dragstart', (e) => { orbit.enabled = false; });
drag.addEventListener('drag',      (e) => e.object);
drag.addEventListener('dragend',   (e) => { orbit.enabled = true; });
drag.addEventListener('hoveron',  (e) => {}); drag.addEventListener('hoveroff', (e) => {});
drag.raycaster;               // customizable (layers, params)
```
Drags in a plane facing the camera. The `objects` array is read live: mutate it to add/remove draggable items. Disable OrbitControls during drag or both fire. `drag.dispose()`.

## 6. TransformControls

```js
import { TransformControls } from 'three/addons/controls/TransformControls.js';

const tc = new TransformControls(camera, renderer.domElement);
scene.add(tc.getHelper());          // r169+: TransformControls is NO LONGER an Object3D. Add getHelper() to the scene, never tc.
tc.attach(mesh);                    // mesh must be in the scene graph
tc.setMode('translate');            // 'translate' | 'rotate' | 'scale'  (tc.mode)
tc.setSpace('local');               // 'world' | 'local'
tc.setSize(1);                      // gizmo size
tc.setTranslationSnap(0.5); tc.setRotationSnap(THREE.MathUtils.degToRad(15)); tc.setScaleSnap(0.25);
tc.showX = tc.showY = tc.showZ = true;   // per-axis visibility (also showXY/XZ/YZ/XYZE/E)
tc.minX = -5; tc.maxX = 5;   // translation limits (minY.. maxZ)
tc.setColors(0xff0000, 0x00ff00, 0x0000ff, 0xffff00);

tc.addEventListener('dragging-changed', (e) => { orbit.enabled = !e.value; });   // property-change event "<prop>-changed"
tc.addEventListener('objectChange', () => {});     // object transformed
tc.addEventListener('mouseDown' | 'mouseUp' | 'change', fn);
tc.detach();  tc.reset();  tc.dragging /* readonly */;
tc.getRaycaster();
```

- Pre-r169 code did `scene.add(transformControls)`; in r186 that throws or silently shows nothing. Use `scene.add(tc.getHelper())`.
- Re-render on `change` if you render on demand. The gizmo must be rendered by the same camera as `tc.camera`; if you swap cameras set `tc.camera = newCamera`.
- Must disable your OrbitControls while `dragging` (`dragging-changed` handler above) or the camera also orbits.
- Does not transform the camera. Keyboard shortcuts (W/E/R, Shift snap) are demo code in `misc_controls_transform`, not part of the class.
- XR variant: `webxr_xr_controls_transform` example.
- `tc.dispose()` when done; remove `getHelper()` from the scene.

## 7. Raycaster picking

```js
const raycaster = new THREE.Raycaster();
const pointer = new THREE.Vector2();

renderer.domElement.addEventListener('pointerdown', (e) => {
  const r = renderer.domElement.getBoundingClientRect();         // NOT window.innerWidth: canvas may be offset/resized
  pointer.x = ((e.clientX - r.left) / r.width)  *  2 - 1;       // NDC: -1 left .. +1 right
  pointer.y = -((e.clientY - r.top)  / r.height) *  2 + 1;       // -1 bottom .. +1 top (Y flipped)
  raycaster.setFromCamera(pointer, camera);
  const hits = raycaster.intersectObjects(scene.children, true);   // recursive default is true; sorted nearest first
  if (hits.length) { const { object, point, distance, face, faceIndex, uv, uv1, normal, instanceId } = hits[0]; }
});
```

- `setFromCamera(coords: Vector2 NDC, camera)` works for perspective and orthographic cameras. The camera's `matrixWorld` must be current (call `camera.updateMatrixWorld()` if you moved it this frame before rendering).
- `intersectObject(obj, recursive=true, target=[])`, `intersectObjects(arr, recursive=true, target=[])` - recursive defaults to TRUE in r186 docs. Hidden objects (`visible=false`) are still tested unless you filter; use layers to exclude.
- Manual-style picking tip: pick only the objects you need (`pickables` array), not `scene.children`, to skip helpers/lights/gizmos.
- Back faces: meshes are hit only through front faces. For double-sided picking set `material.side = THREE.DoubleSide` (raycast respects material.side). Edge-on hits can return two coincident intersections.
- Layers: `raycaster.layers.set(1); object.layers.enable(1);` Only objects whose layers overlap raycaster.layers are tested. Camera layers do not matter for raycasting.
- `raycaster.near/far` (default 0/Infinity) clip along the ray. `raycaster.set(origin, normalizedDirection)` for arbitrary rays (direction MUST be normalized); `setFromXRController(controller)` for WebXR.
- `raycaster.params`: `{ Mesh:{}, Line:{threshold:1}, LOD:{}, Points:{threshold:1}, Sprite:{} }`. Thresholds are in world units; set `raycaster.params.Points.threshold = 0.1` for small point clouds and `params.Line.threshold` for thin lines (Line2/fat lines use their own `linewidth`-based raycast, see `webgl_lines_fat_raycasting`).
- Intersection fields: `distance`, `distanceToRay` (Points/Lines), `point` (world), `object`, `face`, `faceIndex`, `uv`, `uv1`, `normal` (interpolated, local-space face normal data), `instanceId` (InstancedMesh). BatchedMesh hits carry `batchId` (set in source) in addition to `instanceId` semantics - read it from the intersection.
- InstancedMesh: hit per instance via `instanceId`; transform = `mesh.getMatrixAt(instanceId, m)`. Raycast cost scales with instance count (bounding sphere of geometry per instance); `webgl_instancing_raycast`.
- SkinnedMesh: `SkinnedMesh.raycast` applies bone transforms per vertex (`applyBoneTransform`) after a bounding-sphere test using `boundingSphere`; it is slow (CPU skinning of every vertex) and the bounding sphere is computed ONCE (see animation.md): recompute `computeBoundingSphere()` if the pose moves far, else rays miss. Prefer a simplified proxy mesh or GPU picking for characters.
- Morph targets / vertex-shader displacement / alpha-tested textures / `PointsMaterial` sizeAttenuation shaders: CPU raycasting does not see them. Use GPU picking.
- Speed: Raycaster is brute force (bounding sphere, then all triangles). For large meshes use `three-mesh-bvh` (external package, `webgl_raycaster_bvh`): `BufferGeometry.prototype.computeBoundsTree = computeBoundsTree; Mesh.prototype.raycast = acceleratedRaycast; geometry.computeBoundsTree(); raycaster.firstHitOnly = true;` `firstHitOnly` is a three-mesh-bvh property, not a core r186 property.
- Hover: raycast in the animation loop from the last pointermove, not inside the move handler (avoids work between frames); clear pointer on `pointerleave`.
- `Sprite.raycast`, `Points.raycast`, `Line.raycast`, `Mesh.raycast` are the per-type hooks; override `object.raycast = () => {}` to make an object unpickable.

Ray helper (math only): `Ray.intersectPlane(plane, target)` for dragging on a plane / ground placement:

```js
const plane = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);
const p = new THREE.Vector3();
raycaster.setFromCamera(pointer, camera);
if (raycaster.ray.intersectPlane(plane, p)) marker.position.copy(p);   // returns null on miss
```

## 8. GPU picking

When CPU raycasting is wrong or too slow: render ids to a 1x1 target under the cursor, read one pixel (manual `picking`).

```js
const target = new THREE.WebGLRenderTarget(1, 1);          // RGBA8; or the r186 example: type IntType, format RGBAIntegerFormat, internalFormat 'RGBA32I'
const pixel = new Uint8Array(4);

async function pick(clientX, clientY) {
  const r = renderer.domElement.getBoundingClientRect();
  const x = (clientX - r.left) * renderer.domElement.width  / r.width;     // device pixels
  const y = (clientY - r.top)  * renderer.domElement.height / r.height;
  camera.setViewOffset(renderer.domElement.width, renderer.domElement.height, x | 0, y | 0, 1, 1);   // render only that pixel
  renderer.setRenderTarget(target);
  renderer.render(pickingScene, camera);                    // pickingScene: same transforms, flat-id materials
  renderer.setRenderTarget(null);
  camera.clearViewOffset();
  await renderer.readRenderTargetPixelsAsync(target, 0, 0, 1, 1, pixel);   // WebGLRenderer: non-blocking, preferred over sync readRenderTargetPixels(...)
  return (pixel[0] << 16) | (pixel[1] << 8) | pixel[2];     // id (0 = background)
}
```

- Id material: unlit, `blending: NoBlending`, `color` set via `new THREE.Color().setHex(id, THREE.NoColorSpace)` so no sRGB conversion mangles the id (manual uses an abused `MeshPhongMaterial` emissive; a `MeshBasicMaterial` with `toneMapped: false`, no fog is simpler). Match `alphaTest` of the visible material to pick through transparent holes. Antialiasing off (render-target default is non-MSAA, keep it so).
- Instances: id per instance via instanced attribute/color; example `webgl_interactive_cubes_gpu` uses an `IntType`/`RGBAIntegerFormat` target and an `int` id.
- Indexed textures: for regions (countries) bake an id-per-region texture (`NearestFilter`, no mipmaps, `NoColorSpace`) and render the globe with it to the 1x1 target; the same id texture can drive color lookup (see manual `indexed-textures`).
- Readback API: `WebGLRenderer.readRenderTargetPixels(rt, x, y, w, h, buffer, activeCubeFaceIndex?, textureIndex?)` (sync, stalls GPU) and `readRenderTargetPixelsAsync(...)` (same args, returns Promise). **WebGPURenderer** (`Renderer`): only the async form, and it allocates for you: `const data = await renderer.readRenderTargetPixelsAsync(rt, x, y, w, h, textureIndex?, faceIndex?)` returning a TypedArray (no buffer argument). Readback in WebGPU is always async; do not call it every frame for every pointermove, throttle to one in-flight read.

## 9. SelectionBox / SelectionHelper

```js
import { SelectionBox } from 'three/addons/interactive/SelectionBox.js';
import { SelectionHelper } from 'three/addons/interactive/SelectionHelper.js';

const box = new SelectionBox(camera, scene /*, deep = Number.MAX_VALUE */);
const helper = new SelectionHelper(renderer, 'selectBox');     // CSS class for the rubber-band div; helper.enabled, helper.isDown
const ndc = (e) => { const r = renderer.domElement.getBoundingClientRect();
  return [((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1, 0.5]; };

addEventListener('pointerdown', (e) => box.startPoint.set(...ndc(e)));
addEventListener('pointermove', (e) => { if (helper.isDown) { box.endPoint.set(...ndc(e)); const sel = box.select(); } });
addEventListener('pointerup',   (e) => { box.endPoint.set(...ndc(e)); const sel = box.select(); });   // Array<Object3D>
```
`select(start?, end?)` uses `box.startPoint/endPoint` if omitted. Selects by object (and InstancedMesh/BatchedMesh via `box.instances` / `box.batches`). Selection is bounding-based, not per-triangle. Disable camera controls while helper is down. `helper.dispose()`. Example `misc_boxselection`.

## 10. HTML labels and overlays

### a) Projected DOM (no addon)
```js
const v = new THREE.Vector3();
function placeLabel(obj3d, el) {
  obj3d.updateWorldMatrix(true, false);
  obj3d.getWorldPosition(v);
  v.project(camera);                                       // NDC; v.z in [-1,1], > 1 beyond far, < -1 before near
  const hidden = Math.abs(v.z) > 1;                        // out of frustum depth; also check |x|,|y| > 1 if you want
  el.style.display = hidden ? 'none' : '';
  el.style.transform = `translate(-50%, -50%) translate(${(v.x * .5 + .5) * canvas.clientWidth}px, ${(-v.y * .5 + .5) * canvas.clientHeight}px)`;
}
```
Container: `position:relative; overflow:hidden` with canvas + `position:absolute; left:0; top:0` label children. Use `clientWidth/Height` (CSS pixels), not canvas.width (device pixels). Occlusion: raycast from the camera toward the object, hide if first hit is not the object (`raycaster.setFromCamera(v, camera)` after `project`). Z-order: sort labels by `v.z` and set `zIndex`. Frustum check on the object uses `THREE.Frustum.setFromProjectionMatrix(proj * matrixWorldInverse)` + `frustum.intersectsObject(mesh)`.

### b) CSS2DRenderer (labels that follow objects, always screen-aligned)
```js
import { CSS2DRenderer, CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js';

const labelRenderer = new CSS2DRenderer();                         // optional {element}
labelRenderer.setSize(innerWidth, innerHeight);
Object.assign(labelRenderer.domElement.style, { position: 'absolute', top: '0px', pointerEvents: 'none' });
document.body.appendChild(labelRenderer.domElement);

const div = document.createElement('div'); div.className = 'label'; div.textContent = 'Earth';
div.style.pointerEvents = 'auto';                                   // re-enable on label itself if clickable
const label = new CSS2DObject(div);
label.position.set(0, 1, 0);          // local offset
label.center.set(0.5, 1);             // anchor (default 0.5,0.5); rotation2D in radians
earth.add(label);                     // moves/hides with the parent (visible=false hides the element)

// loop
renderer.render(scene, camera);
labelRenderer.render(scene, camera);  // second render call, same scene+camera
// resize: renderer.setSize(w,h); labelRenderer.setSize(w,h);
```
- `labelRenderer.sortObjects` (default true) assigns z-index by `renderOrder` then distance.
- If the overlay covers the canvas, either `pointer-events:none` on the overlay (then OrbitControls on `renderer.domElement` works) or pass `labelRenderer.domElement` to the controls (official example does this).
- No occlusion, no depth: labels always draw above the canvas. Only 100% browser zoom is supported (warned in docs).
- `CSS2DObject` also exists as `isCSS2DObject`; `labelRenderer.getSize()`.

### c) CSS3DRenderer (DOM with real 3D transforms)
```js
import { CSS3DRenderer, CSS3DObject, CSS3DSprite } from 'three/addons/renderers/CSS3DRenderer.js';
const r3 = new CSS3DRenderer(); r3.setSize(w, h); container.appendChild(r3.domElement);
const panel = new CSS3DObject(iframeOrDiv); panel.position.set(0, 0, -500); scene.add(panel);   // 1 world unit = 1 CSS px: use large coordinates, scale for smaller
const billboard = new CSS3DSprite(div);   // always faces camera; rotation2D
r3.render(scene, camera);
```
No materials/geometries/lighting, no depth interplay with WebGL. To composite with a WebGL canvas, stack two renderers (see `css3d_mixed`, `css3d_youtube`) and use a `MeshBasicMaterial({ opacity:0, blending: NoBlending, side: DoubleSide })` "hole" plane in the WebGL scene to reveal the DOM element behind. Pointer events work natively on the DOM elements.

## 11. HTMLMesh, InteractiveGroup, InteractionManager

- `HTMLMesh` (`three/addons/interactive/HTMLMesh.js`): `new HTMLMesh(domElement)` renders a DOM subtree (limited subset: inputs/sliders/text) to a canvas texture on a plane; it re-renders itself on DOM `input`/mutation events (e.g. lil-gui changes). `mesh.dispose()`. Used for in-VR GUI (lil-gui in XR).
- `InteractiveGroup` (`three/addons/interactive/InteractiveGroup.js`): `const g = new InteractiveGroup(); g.listenToPointerEvents(renderer, camera); g.listenToXRControllerEvents(controller);` then `g.add(htmlMesh)`. Raycasts (non-recursive: `intersectObjects(this.children, false)`, so add HTMLMesh directly) and dispatches `mousedown`/`mousemove`/`mouseup`/`click` events (carrying hit `uv` in `event.data`) to the hit child; XR `selectstart/selectend/select/move` map to these. Cleanup: `disconnect()`, `disconnectXrControllerEvents()`, `disconnectionPointerEvents()` (sic).
- `InteractionManager` (`three/addons/interaction/InteractionManager.js`) exists in r186, but it is about `HTMLTexture` elements: `connect(renderer, camera)`, `add(...meshes)`, `remove`, `update()` each frame; computes CSS `matrix3d` for the HTML elements backing `HTMLTexture` meshes so they receive native pointer events. It is NOT a general pointer/raycast event manager; use Raycaster for that.

## 12. Input plumbing

- Use **pointer events** (`pointerdown/move/up/leave/cancel`) for mouse+touch+pen with one code path; `mousemove` + separate `touchstart` (manual `picking`) works but pointer events are the modern default. OrbitControls uses pointer events and sets `touch-action: none`; set the same on your own canvas (`canvas.style.touchAction = 'none'`) or the page scrolls while dragging. Use `e.pointerType`, `e.isPrimary`; multi-touch needs `pointerId` tracking.
- Distinguish click vs drag: store `pointerdown` position, treat `pointerup` within ~4px as a click, otherwise orbit drag will also "click" objects.
- Coordinates: always relative to the canvas via `getBoundingClientRect()`; pixel-ratio is irrelevant for NDC, relevant for GPU-picking pixel coordinates (`canvas.width / rect.width`).
- Keyboard on a canvas needs focus: `<canvas tabindex="0">` plus `canvas:focus { outline: none }` (tabindex 0+ makes it focusable; default canvas ignores key events). Or listen on `window`. `OrbitControls.listenToKeyEvents(window)`.
- Resize: on `resize` (or ResizeObserver) update `camera.aspect`, `camera.updateProjectionMatrix()`, `renderer.setSize(w, h, false)` when CSS sizes the canvas, `labelRenderer.setSize`, and `trackball.handleResize()` / `firstPerson.handleResize()` where applicable. OrbitControls needs nothing.
- Screenshot: `canvas.toBlob(...)` returns a black image because the drawing buffer is cleared after presentation. Fix: call `renderer.render(scene, camera)` immediately before `toBlob/toDataURL` in the same task, or create the renderer with `preserveDrawingBuffer: true` (WebGL only, costs performance). For WebGPURenderer render then read the canvas the same way or use `readRenderTargetPixelsAsync` on a render target.
- Paint-style accumulation: `new WebGLRenderer({ canvas, preserveDrawingBuffer: true, alpha: true })` and `renderer.autoClearColor = false`; resizing still clears.
- Transparent canvas over page content: `new WebGLRenderer({ alpha: true, premultipliedAlpha: false })` (three.js defaults canvas to premultipliedAlpha true while materials output non-premultiplied) and do not set `scene.background`; `renderer.setClearColor(0x000000, 0)`. Page element behind the canvas: `canvas { position: fixed; z-index: -1 }` for a live-animation page background (manual `tips`).
- Game loops (manual `game`): keep input state in a map updated by key/pointer events and consume it once per frame; do not move objects inside event handlers.

## 13. Gotchas

- OrbitControls with `enableDamping` and no `update()` in the loop: camera never settles / drifts or does nothing.
- TransformControls: forgot `getHelper()` -> invisible gizmo (r169+); forgot to disable orbit during drag.
- Raycaster NDC Y not flipped -> picks mirrored vertically. Using `window.innerWidth` instead of canvas rect -> offset picks when canvas is not full-window.
- Raycast against `scene.children` hits helpers/gizmos (TransformControls helper, GridHelper); filter with layers or a pickable list.
- Controls created before the canvas is attached or with `document` as element -> broken coordinates (and `touch-action` applied to document).
- CSS2D overlay blocks controls: forgetting `pointer-events: none` or passing the wrong domElement.
- Stale `boundingSphere` on animated SkinnedMesh/morph/InstancedMesh with moved instances produces missed hits.
- PointerLockControls `lock()` outside a user gesture is rejected by browsers.
- Dispose controls and remove DOM listeners when unmounting a component (React/Svelte/Angular): `controls.dispose()`, `tc.dispose()`, `drag.dispose()`, `helper.dispose()`.

## 14. See also

- api: `Controls.md`, `OrbitControls.md`, `MapControls.md`, `TrackballControls.md`, `ArcballControls.md`, `FlyControls.md`, `FirstPersonControls.md`, `PointerLockControls.md`, `DragControls.md`, `TransformControls.md`, `Raycaster.md`, `Ray.md`, `CSS2DRenderer.md`, `CSS2DObject.md`, `CSS3DRenderer.md`, `CSS3DObject.md`, `CSS3DSprite.md`, `SelectionBox.md`, `SelectionHelper.md`, `InteractionManager.md`, `InteractiveGroup.md`, `HTMLMesh.md`, `HTMLTexture.md`, `Sprite.md`, `module-CameraUtils.md`, `Layers.md`, `WebGLRenderTarget.md`, `WebGLRenderer.md` (readRenderTargetPixels), `Renderer.md` (readRenderTargetPixelsAsync)
- https://threejs.org/manual/#picking , #align-html-elements-to-3d , #indexed-textures , #tips , #game
- https://threejs.org/docs/#OrbitControls , #TransformControls , #Raycaster , #CSS2DRenderer , #CSS3DRenderer
- examples: `misc_controls_orbit|map|trackball|arcball|fly|pointerlock|drag|transform`, `webgl_interactive_cubes`, `webgl_interactive_cubes_gpu`, `webgl_raycaster_bvh`, `webgl_raycaster_sprite`, `webgl_instancing_raycast`, `css2d_label`, `css3d_mixed`, `webxr_xr_controls_transform`
