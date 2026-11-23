# WebXR and audio (three.js r187)

When to read this: building VR/AR (WebXR) experiences with three.js (session buttons, controllers, hands, hit test, planes, lighting estimation, depth sensing, layers) or adding sound (Audio, PositionalAudio, AudioListener, AudioAnalyser). XR classes `WebXRManager` (WebGLRenderer) and `XRManager` (WebGPURenderer) are reached through `renderer.xr` and share most of the public API.

## Table of contents
1. Minimal VR/AR setup
2. Session buttons and sessionInit features
3. Render loop, camera, units, reference space
4. Controllers: ray, grip, events, models
5. Raycasting from controllers, haptics
6. Hand tracking
7. AR: hit test, planes, light estimation, camera access, depth sensing
8. Performance: foveation, framebuffer scale, layers
9. WebGPURenderer and XR
10. Look-to-select (no controller)
11. Audio
12. Gotchas
13. See also

## 1. Minimal setup

```js
import * as THREE from 'three';
import { VRButton } from 'three/addons/webxr/VRButton.js';

const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(devicePixelRatio);
renderer.setSize(innerWidth, innerHeight);
renderer.xr.enabled = true;                        // required: enables XR rendering path
document.body.appendChild(renderer.domElement);
document.body.appendChild(VRButton.createButton(renderer));   // creates "ENTER VR" button + requests the session on click

renderer.setAnimationLoop((time, frame) => {       // REQUIRED instead of requestAnimationFrame: the XR session owns the frame loop
  renderer.render(scene, camera);                  // frame = XRFrame (null outside a session)
});
```

- `requestAnimationFrame` does not fire in an immersive session; `renderer.setAnimationLoop(fn)` switches to `session.requestAnimationFrame` automatically. Call `setAnimationLoop(null)` to stop.
- The headset drives the camera. Do not set `camera.position/quaternion` expecting it to stick in-session (they are overridden by the pose). To move the user, put the camera (and controllers) in a parent `Group` ("dolly"/rig) and move that.
- Units are meters: 1 unit = 1 m. Eye height ~1.6. Default reference space is `local-floor` (VRButton), so y=0 is the floor; ARButton uses `local`.
- HTTPS (or `localhost`) is mandatory for WebXR. Test on device via a LAN https server or `adb reverse`; Immersive Web Emulator browser extension for desktop without hardware.
- Do not resize with `renderer.setSize` during a session; use `renderer.xr.isPresenting` to skip resize logic.
- The canvas/camera `aspect` is irrelevant in XR (per-eye projections come from the device); `renderer.xr.getCamera()` returns an `ArrayCamera` with one sub-camera per view (its `fov` is not meaningful).

## 2. Session buttons and sessionInit

```js
import { VRButton }  from 'three/addons/webxr/VRButton.js';    // immersive-vr
import { ARButton }  from 'three/addons/webxr/ARButton.js';    // immersive-ar
import { XRButton }  from 'three/addons/webxr/XRButton.js';    // immersive-ar if supported, else immersive-vr

document.body.appendChild(VRButton.createButton(renderer, {
  optionalFeatures: ['hand-tracking', 'layers'],   // request but don't fail without
  requiredFeatures: [],                            // session fails / button reports unsupported without these
}));
document.body.appendChild(ARButton.createButton(renderer, { requiredFeatures: ['hit-test'] }));
```

- All three: `createButton(renderer: WebGLRenderer | WebGPURenderer, sessionInit?)` returns an HTMLElement (an error message element if XR is unsupported). `sessionInit` is the standard `XRSessionInit` dict (`requiredFeatures`, `optionalFeatures`, `domOverlay`).
- VRButton/XRButton always prepend optional features `'local-floor'`, `'bounded-floor'`, `'layers'` to yours. ARButton uses reference space `'local'` and, when it creates its close-overlay, adds `'dom-overlay'` (`domOverlay: { root }`).
- Feature strings you will need: `'hit-test'`, `'plane-detection'`, `'light-estimation'`, `'depth-sensing'`, `'camera-access'`, `'hand-tracking'`, `'anchors'`, `'dom-overlay'`, `'layers'`, `'webgpu'` (WebGPU binding). Feature missing from `requiredFeatures` = API silently unavailable (e.g. `frame.getHitTestResults` / `requestHitTestSource` undefined).
- `VRButton.xrSessionIsGranted` / `registerSessionGrantedListener()` is for browsers that pre-grant sessions (auto-start); no app code needed.
- Custom start (no button): `const session = await navigator.xr.requestSession('immersive-vr', init); await renderer.xr.setSession(session);` Call from a user gesture. End with `session.end()`; listen via `renderer.xr.addEventListener('sessionstart' | 'sessionend', fn)`.
- Needs `isSessionSupported`: `navigator.xr.isSessionSupported('immersive-ar')`.

## 3. Render loop, reference space, camera

```js
renderer.xr.setReferenceSpaceType('local-floor');   // before session start; 'local' | 'local-floor' | 'bounded-floor' | 'unbounded' | 'viewer'
renderer.xr.setReferenceSpace(space);                // custom XRReferenceSpace (e.g. offset: teleport via space.getOffsetReferenceSpace)
renderer.xr.getReferenceSpace(); renderer.xr.getSession(); renderer.xr.getFrame();   // null outside a session
renderer.xr.isPresenting;                            // readonly
renderer.xr.cameraAutoUpdate = false;                // then call renderer.xr.updateCamera(camera) yourself (WebGL: setting requires manual call)
renderer.xr.getEnvironmentBlendMode();               // 'opaque' | 'additive' | 'alpha-blend' | undefined (passthrough AR on headsets)
```

- `setReferenceSpaceType` and `setFramebufferScaleFactor` throw/do nothing during a session; call before the button is pressed.
- Teleport/locomotion: move the rig Group, or offset the reference space (`webxr_vr_teleport`). Moving only the camera is overwritten per frame.
- AR on passthrough headsets: `scene.background = null` and a transparent renderer (`alpha: true` or default clear) so the camera feed shows; set `renderer.setClearAlpha(0)`.
- Animation-loop timestamp is the XR frame time (ms). Use `Timer`/delta as usual for logic.
- `renderer.xr.getBaseLayer()`, `getBinding()` give WebXR layers objects for advanced use.

## 4. Controllers

```js
const c0 = renderer.xr.getController(0);        // target-ray space (pointing direction); a Group
const g0 = renderer.xr.getControllerGrip(0);    // grip space (where the hand holds it); a Group
scene.add(c0, g0);                              // MUST be added to the scene: they are plain Groups updated by the manager

c0.addEventListener('connected', (e) => {       // e.data = XRInputSource
  const src = e.data;                           // src.targetRayMode: 'gaze' | 'tracked-pointer' | 'screen' | 'transient-pointer'; src.handedness; src.gamepad
  c0.add(new THREE.Line(lineGeometry));         // attach a pointer line to the ray space
});
c0.addEventListener('disconnected', () => c0.clear());
c0.addEventListener('selectstart', fn);  c0.addEventListener('select', fn);  c0.addEventListener('selectend', fn);     // primary: trigger / pinch / screen tap
c0.addEventListener('squeezestart', fn); c0.addEventListener('squeeze', fn); c0.addEventListener('squeezeend', fn);     // grip button
```

- Index (0,1) is assigned in order the input sources connect, not by handedness: use `connected` + `e.data.handedness` to identify left/right.
- Two spaces per controller: put pointers/rays under `getController(i)`; put the 3D model under `getControllerGrip(i)`. Models in ray space look offset.
- `select` = full press-release; `selectstart`/`selectend` for hold. In handheld AR (phone), a screen tap is a `transient-pointer` input and arrives as `select` on a controller.
- Controller models:

```js
import { XRControllerModelFactory } from 'three/addons/webxr/XRControllerModelFactory.js';
const factory = new XRControllerModelFactory();                     // fetches models from the WebXR input-profiles CDN (setPath(url) for self-hosting; optional gltfLoader ctor arg for Draco etc.)
g0.add(factory.createControllerModel(g0));                          // XRControllerModel animates buttons/thumbstick from the Gamepad; setEnvironmentMap(tex) for lighting
```
- Reading the gamepad: `e.data.gamepad.axes` / `.buttons[i].pressed` from the `connected` event's input source, poll per frame. Thumbstick locomotion examples: `webxr_vr_rollercoaster`, `webxr_vr_teleport`.

## 5. Raycasting from controllers, haptics

```js
const raycaster = new THREE.Raycaster();
raycaster.setFromXRController(c0);                              // uses controller matrixWorld: origin + -Z direction
const hits = raycaster.intersectObjects(pickables, false);
// older manual way: tempMatrix.identity().extractRotation(c0.matrixWorld); ray.origin.setFromMatrixPosition(c0.matrixWorld); ray.direction.set(0,0,-1).applyMatrix4(tempMatrix)
line.scale.z = hits.length ? hits[0].distance : 5;             // line stretches to the hit (pointer line geometry from (0,0,0) to (0,0,-1))
```
- Keep the pointer line out of the pickable set (separate `pickRoot` group, as the manual does), or the ray hits its own line.
- Controller matrices update before your animation callback; raycast inside it.
- Haptics: `const gp = event.data.gamepad; gp.hapticActuators?.[0]?.pulse(intensity, ms)` (`webxr_xr_haptics`).
- Drag with controllers: `webxr_xr_dragging` (attach picked object to controller on `selectstart`, `attach` back to scene on `selectend`). UI in VR: `HTMLMesh` + `InteractiveGroup` (`listenToXRControllerEvents(controller)`), see controls-interaction.md.
- TransformControls in XR: `webxr_xr_controls_transform`.

## 6. Hand tracking

```js
import { XRHandModelFactory } from 'three/addons/webxr/XRHandModelFactory.js';

VRButton.createButton(renderer, { optionalFeatures: ['hand-tracking'] });   // or requiredFeatures
const handFactory = new XRHandModelFactory();                               // .setPath('./models/fbx/') for local mesh assets
const hand = renderer.xr.getHand(0);
hand.add(handFactory.createHandModel(hand, 'mesh'));                        // profile: 'spheres' | 'boxes' | 'mesh'
scene.add(hand);

hand.addEventListener('pinchstart', (e) => {});    hand.addEventListener('pinchend', () => {});
const tip = hand.joints['index-finger-tip'];       // Object3D per XRHand joint name; tip.position / jointRadius; only populated while tracking
```
- A physical hand appears as a hand input source; controllers disappear while hands are tracked (and vice versa), so register both `getControllerGrip` model and `getHand` model per index.
- Oculus helpers: `OculusHandModel(controller)` (`getPointerPosition()` = index tip, `intersectBoxObject(mesh)`, `checkButton(btn)`), `OculusHandPointerModel(hand, controller)` (`pointerObject`, `pinched`/`isPinched()`, `checkIntersections(objects, recursive)`, `setCursor(distance)`; add the pointer to the hand and set `renderer.xr.cameraAutoUpdate = false` as the pointer click example does). Examples `webxr_vr_handinput*`.
- `XRHandModel` exposes `.mesh`, `.motionController`, `.controller`; models load via GLTF/FBX from the input-profiles repo.

## 7. AR features

### Hit test (place objects on real surfaces)
```js
document.body.appendChild(ARButton.createButton(renderer, { requiredFeatures: ['hit-test'] }));
let hitTestSource = null, requested = false;
const reticle = new THREE.Mesh(new THREE.RingGeometry(0.15, 0.2, 32).rotateX(-Math.PI / 2), new THREE.MeshBasicMaterial());
reticle.matrixAutoUpdate = false; reticle.visible = false; scene.add(reticle);

renderer.setAnimationLoop((t, frame) => {
  if (frame) {
    const space = renderer.xr.getReferenceSpace(), session = renderer.xr.getSession();
    if (!requested) {
      session.requestReferenceSpace('viewer').then((viewer) =>
        session.requestHitTestSource({ space: viewer }).then((src) => (hitTestSource = src)));
      session.addEventListener('end', () => { requested = false; hitTestSource = null; });
      requested = true;
    }
    if (hitTestSource) {
      const results = frame.getHitTestResults(hitTestSource);
      reticle.visible = results.length > 0;
      if (results.length) reticle.matrix.fromArray(results[0].getPose(space).transform.matrix);
    }
  }
  renderer.render(scene, camera);
});
// on controller 'select': reticle.matrix.decompose(mesh.position, mesh.quaternion, mesh.scale);
```
Example `webxr_ar_hittest`. The renderer needs `alpha: true` in the example (transparent background for camera feed).

### Plane detection
`import { XRPlanes } from 'three/addons/webxr/XRPlanes.js'; ARButton.createButton(renderer, { requiredFeatures: ['plane-detection'] }); scene.add(new XRPlanes(renderer));` renders detected planes as thin boxes; the manager emits `planesdetected` (`data: frame`) on `renderer.xr`. Example `webxr_ar_plane_detection`.

### Light estimation
```js
import { XREstimatedLight } from 'three/addons/webxr/XREstimatedLight.js';
ARButton.createButton(renderer, { optionalFeatures: ['light-estimation'] });
const xrLight = new XREstimatedLight(renderer /*, environmentEstimation = true */);   // Group: .directionalLight, .lightProbe, .environment (cube map)
xrLight.addEventListener('estimationstart', () => { scene.add(xrLight); if (xrLight.environment) scene.environment = xrLight.environment; });
xrLight.addEventListener('estimationend',   () => { scene.remove(xrLight); scene.environment = defaultEnv; });
```
Add the light only after `estimationstart` fires (some devices never provide it); fall back to your own lights. `xrLight.dispose()`. Example `webxr_ar_lighting`. WebGLRenderer only (`XREstimatedLight( renderer : WebGLRenderer, ...)`).

### Camera access
`requiredFeatures: ['camera-access']`; per frame: `const view = frame.getViewerPose(renderer.xr.getReferenceSpace()).views[0]; const tex = renderer.xr.getCameraTexture(view.camera);` (opaque texture valid only inside that frame's animation callback). Example `webxr_ar_camera_access`.

### Depth sensing
`optionalFeatures: ['depth-sensing']` (XRButton in `webxr_xr_cubes`/`ballshooter`) lets the manager build occlusion data: `renderer.xr.hasDepthSensing()`, `getDepthTexture()`, `getDepthSensingMesh()` (a plane mesh that writes depth to hide virtual objects behind real ones; `WebXRDepthSensing` with `depthNear`, `depthFar`, `texture`, `mesh`, internal). `webxr_xr_dragging_custom_depth` shows custom depth materials.

## 8. Performance

```js
renderer.xr.setFoveation(1);                  // 0..1; 0 = full res, 1 = max foveation (edges lower res); the value is stored and re-applied when a session starts
renderer.xr.setFramebufferScaleFactor(1.2);   // before session; >1 supersamples (costly), <1 saves GPU
renderer.xr.getFoveation();                   // XRManager (WebGPU) also has getFramebufferScaleFactor()
renderer.setPixelRatio(1);                    // pixelRatio does not drive XR resolution; framebufferScaleFactor does
```
- Budget: 72-120 Hz targets. Cut draw calls (instancing, merged geometry), avoid post-processing and large shadow maps, keep MSAA modest (`antialias: true` on the XR layer is the cheapest AA), prefer baked lighting.
- WebXR Layers (`'layers'` optional feature already requested by VRButton/XRButton): render a quad/cylinder (video, UI, text) at native resolution and compositor-reprojected. WebGPURenderer API: `renderer.xr.createQuadLayer(width, height, translation, quaternion, pixelwidth, pixelheight, renderCall, attributes)` and `createCylinderLayer(radius, centralAngle, aspect, translation, quaternion, pixelwidth, pixelheight, renderCall, attributes)` return a Mesh to add to the scene; call `renderer.xr.renderLayers()` in the loop before `renderer.render` (`webgpu_xr_native_layers`). On WebGLRenderer use the raw `XRWebGLBinding` via `renderer.xr.getBinding()` (`webxr_vr_layers`).
- Enable `multiview: true` in the WebGPURenderer constructor (as the XR examples do) to render both eyes in one pass where supported.

## 9. WebGPURenderer and XR

- Official WebGPU XR examples exist: `webgpu_xr_cubes`, `webgpu_xr_rollercoaster`, `webgpu_xr_shadows`, `webgpu_xr_native_layers` (all `import * as THREE from 'three/webgpu'`).
- Browser support for the WebXR/WebGPU binding (`XRGPUBinding`, session feature `'webgpu'`) is not universal. The examples request `optionalFeatures: ['webgpu']` and use `setupWebGLXRFallback(renderer, () => createRenderer(true), setRenderer)` from `three/addons/webxr/WebGLXRFallback.js`: when the session starts and `XRGPUBinding` is undefined, they swap to a second `WebGPURenderer` created with `forceWebGL: true` (WebGL2 backend) and re-bind the animation loop/controllers. Reproduce this pattern for production.
- `new THREE.WebGPURenderer({ antialias: true, outputBufferType: THREE.UnsignedByteType, multiview: true })` is what the examples use for XR. Requires `await renderer.init()` implicitly via `setAnimationLoop` (async).
- `renderer.xr` is `XRManager` here: same getController/getControllerGrip/getHand/getCamera/setFoveation/setFramebufferScaleFactor/setReferenceSpaceType/getSession/getFrame; plus `createQuadLayer/createCylinderLayer/renderLayers`, `getWebGPUBinding()`, `useMultiview()`, `foveateBoundTexture(rt)`, `getReferenceSpaceType()`, `getFramebufferScaleFactor()`. No `getDepthTexture/hasDepthSensing/getCameraTexture` documented on XRManager; those are WebXRManager (WebGL). Light estimation (`XREstimatedLight`) is typed for WebGLRenderer. `XRPlanes` accepts either renderer.
- Because controllers are recreated when the renderer swaps, the XR examples remove and re-add controllers in `setRenderer()`.
- All other webxr_* examples (VR/AR) still use WebGLRenderer; prefer WebGLRenderer unless you need TSL/WebGPU features.

## 10. Look-to-select (no controller, Cardboard-style)

Raycast from the center of the view every frame, require a dwell time with a gauge:

```js
raycaster.setFromCamera({ x: 0, y: 0 }, camera);     // center in NDC; in-session use renderer.xr.getCamera() if camera pose matters
const hit = raycaster.intersectObjects(pickRoot.children)[0];
if (hit?.object === current) dwell += delta; else { current = hit?.object; dwell = 0; }
if (dwell > 1.5) select(current);                    // show progress with a texture-offset ring (manual: webxr-look-to-select)
```
Manual pages `webxr-basics`, `webxr-look-to-select`, `webxr-point-to-select` (3DOF controller: `getController(i)`, a Line child, ray from controller matrix; emit your own `select` event).

## 11. Audio

```js
import * as THREE from 'three';

const listener = new THREE.AudioListener();       // one per app; creates/uses the shared AudioContext
camera.add(listener);                              // listener follows the camera pose (in XR, add it to the rig/camera that moves)

const sound = new THREE.Audio(listener);           // non-positional (music, UI)
new THREE.AudioLoader().load('sounds/ambient.ogg', (buffer) => {
  sound.setBuffer(buffer).setLoop(true).setVolume(0.5);
});

// startup requires a user gesture (autoplay policy)
startButton.addEventListener('click', () => {
  if (listener.context.state === 'suspended') listener.context.resume();   // THREE.AudioContext.getContext()
  sound.play();
});
```

- **Autoplay gotcha**: browsers keep the AudioContext `suspended` until a user gesture. Call `play()` (or `context.resume()`) inside a click/pointer/`selectstart`/button handler; examples use a "Play" overlay button. `play()` with no buffer set creates a source with a null buffer, i.e. silence; `setBuffer` first (or `autoplay = true`). `play()` while already playing only warns. `autoplay = true` only starts when the buffer is set and the context is running.
- iOS Safari: media elements via `setMediaElementSource` have no usable playback control and analyser support is weak; the official visualizer example switches to `AudioLoader` buffers on iOS.
- API: `play(delay)`, `pause()`, `stop(delay)`, `setVolume(v)` (gain), `setLoop(bool)`, `loopStart/loopEnd`, `offset`, `duration`, `setPlaybackRate(v)`, `setDetune(cents)`, `setFilter(node)` / `setFilters([nodes])` (BiquadFilterNode etc.), `isPlaying`, `getOutput()` (GainNode), `connect()/disconnect()`, `onEnded()` hook. Sources: `setBuffer(AudioBuffer)` (full control), `setMediaElementSource(HTMLMediaElement)`, `setMediaStreamSource(MediaStream)` (mic), `setNodeSource(AudioNode)` (oscillator) - the last three have `hasPlaybackControl = false` (use the element/node to control them; `play()` is a no-op).
- `AudioListener`: `setMasterVolume(v)`, `getMasterVolume()`, `setFilter/removeFilter`, `context`, `gain`. `AudioContext.getContext()/setContext(ctx)` static to share/replace the context.
- Loading: `AudioLoader.load(url, onLoad(AudioBuffer))` or `await loader.loadAsync(url)`; decodes with the shared context. Reuse one buffer across many Audio objects.

### Positional audio
```js
const s = new THREE.PositionalAudio(listener);     // Object3D: add to the mesh that emits
s.setBuffer(buffer);
s.setRefDistance(1);                               // distance at which attenuation starts (default 1)
s.setRolloffFactor(1);                             // falloff speed
s.setDistanceModel('inverse');                     // 'linear' | 'inverse' (default) | 'exponential'
s.setMaxDistance(100);                             // used by 'linear' only (attenuation stops growing)
s.setDirectionalCone(180, 230, 0.1);               // innerAngle, outerAngle (degrees), outerGain (0 = silent outside); visualize with PositionalAudioHelper
mesh.add(s); s.play();
import { PositionalAudioHelper } from 'three/addons/helpers/PositionalAudioHelper.js';
s.add(new PositionalAudioHelper(s, 1));            // add as CHILD of the audio; call helper.update() after changing the cone; helper.dispose()
```
- Pan/distance come from the PannerNode (`s.panner`) using the audio object's world transform vs the listener's world transform, updated every render via `updateMatrixWorld`. If you freeze `matrixWorldAutoUpdate` the sound stops moving.
- Units are world units; match `refDistance` to your scene scale (a 1000-unit world with refDistance 1 is inaudible beyond a few units).
- Remember to `stop()` and `disconnect()` + remove audio when disposing a scene; buffers are GC'd with references.

### Analyser
```js
const analyser = new THREE.AudioAnalyser(sound, 128);          // fftSize (power of 2); frequencyBinCount = fftSize / 2
function tick() {
  const data = analyser.getFrequencyData();                    // Uint8Array 0..255, linear 0..sampleRate/2; also analyser.data
  const avg = analyser.getAverageFrequency();                  // quick "loudness" scalar
  tex.needsUpdate = true;                                      // when data feeds a DataTexture: new THREE.DataTexture(analyser.data, fftSize/2, 1, THREE.RedFormat)
}
```
`analyser.analyser` is the native `AnalyserNode` (set `smoothingTimeConstant`, `minDecibels`). Examples `webaudio_visualizer`, `webaudio_orientation`, `webaudio_sandbox`, `webaudio_timing`.

## 12. Gotchas

- Forgot `renderer.xr.enabled = true` or used `requestAnimationFrame`: black/frozen headset view.
- Controller Groups not added to the scene: events fire (on the group) but nothing is positioned; models invisible.
- Moving `camera` instead of a parent rig; not resetting rig on `sessionend`.
- Requesting features after session start (impossible) or missing `requiredFeatures` -> undefined WebXR APIs.
- Large near-plane differences: use `near ~0.01-0.1`, far small (10-100) for AR; depth precision.
- `setFramebufferScaleFactor` / `setReferenceSpaceType` called mid-session.
- Avoid post-processing in XR: the headset layer is the renderer's XR framebuffer; plain `renderer.render(scene, camera)` is the supported path.
- Shadows: expensive; `webgpu_xr_shadows` demonstrates WebGPU shadows in XR.
- Audio started without a gesture stays silent; `PositionalAudio` not parented to a scene-attached object stays at the origin.

## 13. See also

- api: `WebXRManager.md`, `XRManager.md`, `WebXRDepthSensing.md`, `XRButton.md`, `VRButton.md`, `ARButton.md`, `XRControllerModelFactory.md`, `XRControllerModel.md`, `XRHandModelFactory.md`, `XRHandModel.md`, `XRPlanes.md`, `XREstimatedLight.md`, `OculusHandModel.md`, `OculusHandPointerModel.md`, `Raycaster.md`, `ArrayCamera.md`, `Audio.md`, `PositionalAudio.md`, `AudioListener.md`, `AudioLoader.md`, `AudioAnalyser.md`, `AudioContext.md`, `PositionalAudioHelper.md`
- https://threejs.org/manual/#how-to-create-vr-content , #webxr-basics , #webxr-look-to-select , #webxr-point-to-select
- https://threejs.org/docs/#WebXRManager , #XRManager , #PositionalAudio , #AudioListener
- examples: `webxr_xr_cubes`, `webxr_xr_ballshooter`, `webxr_xr_dragging`, `webxr_xr_haptics`, `webxr_xr_paint`, `webxr_vr_handinput`, `webxr_vr_handinput_pointerclick`, `webxr_vr_layers`, `webxr_vr_teleport`, `webxr_ar_hittest`, `webxr_ar_plane_detection`, `webxr_ar_lighting`, `webxr_ar_camera_access`, `webgpu_xr_cubes`, `webgpu_xr_native_layers`, `webaudio_visualizer`, `webaudio_orientation`
