# Animation (three.js r186)

When to read this: playing glTF/FBX clips, crossfading or additively blending animations, building clips from keyframes in code, cloning/retargeting skinned characters, driving morph targets, IK, or optimizing many animated objects. Animation is renderer-agnostic: `AnimationMixer` runs on the CPU and writes to Object3D properties, so everything here is identical for WebGLRenderer and WebGPURenderer.

## Table of contents
1. Mental model
2. Mixer / action lifecycle and render-loop wiring
3. Action control: play, stop, reset, loop, clamp, timeScale, weight
4. Fading, crossfading, warping, syncing
5. Events (finished / loop)
6. Additive blending, subclip
7. Building clips from KeyframeTracks
8. PropertyBinding track-name syntax
9. Skinning, Skeleton, cloning (SkeletonUtils.clone), shared skeletons
10. Retargeting
11. Morph targets
12. Inverse kinematics (CCDIKSolver)
13. Performance: AnimationObjectGroup, GPU skinning, caching, cleanup
14. Other helpers
15. Gotchas
16. See also

## 1. Mental model

```
Loader result (gltf.animations: AnimationClip[])
  AnimationClip   = name + duration + KeyframeTrack[]      (data, reusable, shareable between mixers)
  KeyframeTrack   = one property path + times[] + values[] (e.g. 'Hips.quaternion')
  AnimationMixer  = player bound to ONE root Object3D; owns time; resolves track names against root
  AnimationAction = clip scheduled on a mixer (weight, timeScale, loop, fade)
```

Loaders producing clips: GLTFLoader, FBXLoader, ColladaLoader, BVHLoader, ObjectLoader. OBJ has no animation.

## 2. Lifecycle and render loop

```js
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';

const timer = new THREE.Timer();
timer.connect(document);               // pauses on tab hidden; examples in r186 use Timer
let mixer;

new GLTFLoader().load('Soldier.glb', (gltf) => {
  scene.add(gltf.scene);
  mixer = new THREE.AnimationMixer(gltf.scene);       // root = object whose descendants the tracks name
  const clip = THREE.AnimationClip.findByName(gltf.animations, 'Run');
  mixer.clipAction(clip).play();                      // or mixer.clipAction('Run') by name
});

renderer.setAnimationLoop(() => {
  timer.update();
  mixer?.update(timer.getDelta());                    // seconds, NOT ms
  renderer.render(scene, camera);
});
```

- `Clock` is deprecated since r183 (see api/Clock.md); use `Timer` (`update()` then `getDelta()`; `connect(document)` handles visibility). Any delta in seconds works.
- `mixer.update(dt)` must run every frame, before `render`. Nothing moves otherwise; `play()` only schedules.
- `mixer.clipAction(clip | name, optionalRoot?, blendMode?)` is a cache: same clip+root returns the same action. `existingAction()` returns `null` if none.
- One mixer per independently animated root. Mixer props: `time`, `timeScale` (0 pauses all actions; global speed), `setTime(t)` (seek), `stopAllAction()`, `getRoot()`.
- Track names are matched by node `name` under the mixer root. A clip applied to a differently-named hierarchy silently does nothing (PropertyBinding warns "Can not bind to bones/..." in the console).
- Mixer root can be a `SkinnedMesh` or a bone (see shared skeleton, retarget).

## 3. Action control

```js
const a = mixer.clipAction(clip);
a.setLoop(THREE.LoopOnce, 1);   // LoopRepeat (default, Infinity reps) | LoopOnce | LoopPingPong
a.clampWhenFinished = true;     // hold last frame; otherwise the action is disabled at the end (enabled=false) and pose snaps back
a.timeScale = -1;               // negative = reverse; 0 = pause (a.paused = true also pauses)
a.setEffectiveTimeScale(1);     // sets timeScale AND clears paused effect; use when re-enabling after crossFade
a.setEffectiveWeight(1);        // sets weight 0..1 (also disables fading)
a.setDuration(2);               // retime one loop to 2s (changes timeScale)
a.startAt(mixer.time + 1);      // delayed start, in mixer.time
a.time = 0;                     // local time, clamped/wrapped to [0, clip.duration]
a.play();  a.stop();  a.reset();
a.isRunning(); a.isScheduled(); a.halt(1);   // halt: decelerate to timeScale 0 over 1s
```

- `stop()` = deactivate on mixer + `reset()`; `reset()` sets `paused=false, enabled=true, time=0`, forgets loop count/start time, stops fading/warping (it does NOT reset `weight`/`timeScale`). Replay a finished `LoopOnce` clip with `action.reset().play()`.
- `a.enabled = false` removes its influence but keeps time; `a.paused = true` freezes at current pose (still contributes at its weight).
- `weight` is not auto-normalized. Two Normal-mode actions at weight 1 each overwrite in order of creation/play; to blend, weights should sum to 1 (crossFade does this for you).
- `zeroSlopeAtStart/End` (default true) smooth the interpolation at clip boundaries used for fades; rarely touched.
- `a.blendMode` is set by `clipAction(clip, root, blendMode)` or `clip.blendMode`.
- Constants: `LoopOnce`, `LoopRepeat`, `LoopPingPong`, `NormalAnimationBlendMode`, `AdditiveAnimationBlendMode`, `InterpolateDiscrete|Linear|Smooth|Bezier` (all exported from `three`).

## 4. Fading, crossfading, warping

```js
idle.play();
// later:
walk.reset().play();                         // reset() clears weight/time leftovers
idle.crossFadeTo(walk, 0.4, false);          // idle fades out, walk fades in (symmetrical: walk.crossFadeFrom(idle, 0.4))
walk.fadeIn(0.3); walk.fadeOut(0.3);         // single action, weight 0->1 or 1->0
```

- `warp=true` additionally blends the timeScales so differing-length clips (walk 1.0s vs run 0.7s) keep foot phase roughly in sync. It rewrites timeScale of the outgoing action: afterwards reset with `setEffectiveTimeScale(1)` + `setEffectiveWeight(1)` before reusing it (the official example's `setWeight()` helper does exactly this, plus `action.enabled = true`).
- `crossFadeTo` disables the outgoing action at the end of the fade (`enabled=false`), so re-fading it later needs `enabled = true`/`reset()`.
- Fade state machine: `stopFading()`, `stopWarping()`, `warp(startTimeScale, endTimeScale, duration)`.
- `a.syncWith(other)` locks `a` to `other`'s time and timeScale (phase-locked walk/run blending).
- Read live weights for UI/state: `getEffectiveWeight()`, `getEffectiveTimeScale()`.
- Typical state machine: finish current loop then crossfade (official examples):

```js
mixer.addEventListener('loop', function onLoop(e) {
  if (e.action === startAction) {
    mixer.removeEventListener('loop', onLoop);
    endAction.setEffectiveWeight(1); endAction.time = 0;
    startAction.crossFadeTo(endAction, duration, true);
  }
});
```

## 5. Events

Dispatched on the **mixer** (not the action):

```js
mixer.addEventListener('finished', (e) => { e.action; e.direction; });  // LoopOnce ended or LoopRepeat repetitions exhausted
mixer.addEventListener('loop',     (e) => { e.action; e.loopDelta; });  // each completed loop
```

`finished` fires only when the action truly ends; a fade-out or `stop()` does not fire it. Remove listeners you add per transition (see above) or they accumulate.

## 6. Additive blending and subclip

```js
import * as THREE from 'three';
const base = mixer.clipAction(idleClip); base.play();

// Convert a clip so its values are relative to a reference frame, then layer it
THREE.AnimationUtils.makeClipAdditive(headShakeClip);          // refFrame 0, reference = itself, fps 30; mutates the clip
let pose = THREE.AnimationUtils.makeClipAdditive(sadClip);
pose = THREE.AnimationUtils.subclip(pose, 'sad_pose', 2, 3, 30); // frames [2,3) at 30 fps -> a 1-frame pose
const add = mixer.clipAction(pose);   // blendMode is already AdditiveAnimationBlendMode after makeClipAdditive
add.setEffectiveWeight(0.7).play();   // weight scales the additive contribution
```

- Signatures: `makeClipAdditive(targetClip, referenceFrame=0, referenceClip=targetClip, fps=30)`, `subclip(sourceClip, name, startFrame, endFrame, fps=30)`. Both return a clip; `makeClipAdditive` converts in place.
- Pass a separate `referenceClip` (e.g. the T-pose/idle) when the additive clip has no neutral frame.
- Additive actions are layered over whatever Normal actions are running; don't crossfade them, just set weight.
- Official example: `webgl_animation_skinning_additive_blending.html` (Xbot.glb: idle/walk/run base + sneak_pose/sad_pose/agree/headShake additive).
- Other utils: `AnimationUtils.convertArray`, `flattenJSON`, `getKeyframeOrder`, `sortedArray`, `hasTangents`, `isTypedArray` (parsing helpers).

## 7. Building clips from KeyframeTracks

```js
import * as THREE from 'three';
const q0 = new THREE.Quaternion(), q1 = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0,1,0), Math.PI);

const tracks = [
  new THREE.VectorKeyframeTrack('.position', [0, 1, 2], [0,0,0,  30,0,0,  0,0,0]),
  new THREE.VectorKeyframeTrack('.scale',    [0, 1, 2], [1,1,1,  2,2,2,  1,1,1]),
  new THREE.QuaternionKeyframeTrack('.quaternion', [0,1,2], [...q0, ...q1, ...q0]),   // never animate .rotation (Euler) - interpolation breaks
  new THREE.ColorKeyframeTrack('.material.color', [0,1,2], [1,0,0, 0,1,0, 0,0,1], THREE.InterpolateDiscrete),
  new THREE.NumberKeyframeTrack('.material.opacity', [0,1,2], [1,0,1]),
  new THREE.BooleanKeyframeTrack('.visible', [0, 1], [true, false]),
  new THREE.StringKeyframeTrack('.name', [0, 1], ['a', 'b']),   // discrete only
];
const clip = new THREE.AnimationClip('Action', 3 /* -1 = derive from tracks */, tracks);
const mixer = new THREE.AnimationMixer(mesh);
mixer.clipAction(clip).play();
```

- Times: seconds, ascending, `times.length * valueSize === values.length`. Flat value arrays (Vector 3/quat 4/color 3/number 1). `clip.validate()` / `track.validate()` check this; `clip.optimize()` removes duplicate keys; `clip.resetDuration()`, `clip.trim()`.
- Track name begins with `.` when it targets the mixer root itself (`'.position'`); otherwise `nodeName.property`.
- Interpolation: `InterpolateLinear` (default; quaternion tracks use slerp via QuaternionLinearInterpolant), `InterpolateDiscrete` (step), `InterpolateSmooth` (cubic, CubicInterpolant), `InterpolateBezier` (BezierInterpolant; requires `track.settings = { inTangents, outTangents }` Float32Arrays of [time,value] pairs; check `AnimationUtils.hasTangents`). Change via `track.setInterpolation()` or ctor arg. Boolean/String tracks are discrete only.
- Track utilities: `scale(timeScale)`, `shift(offset)`, `trim(start,end)`, `clone()`, `getValueSize()`, `KeyframeTrack.toJSON(track)`. Clip: `clone()`, `toJSON()`, `AnimationClip.parse(json)`.
- Morph target sequences to clips: `AnimationClip.CreateFromMorphTargetSequence(name, morphTargets, fps, noLoop)` and `CreateClipsFromMorphTargetSequences(morphTargets, fps, noLoop)`.
- Ready-made clips (addon): `import { AnimationClipCreator } from 'three/addons/animation/AnimationClipCreator.js'` with `CreateRotationAnimation(period, 'x'|'y'|'z')`, `CreateScaleAxisAnimation`, `CreateShakeAnimation(duration, Vector3)`, `CreatePulsationAnimation(duration, pulseScale)`, `CreateVisibilityAnimation(duration)`, `CreateMaterialColorAnimation(duration, Color[])`.
- Example: `misc_animation_keys.html`.

## 8. Track-name / PropertyBinding syntax

Forms accepted by `PropertyBinding.parseTrackName` (source: api/PropertyBinding.md):

```
nodeName.property                 'Hips.position'
nodeName.property[accessor]       'Arm.rotation[x]'
nodeName.material.property[acc]   'Cube.material.color'  /  '.material.opacity'
uuid.property[accessor]
uuid.objectName[objectIndex].propertyName[propertyIndex]   'Mesh.morphTargetInfluences[Smile]'
parentName/nodeName.property      disambiguate duplicate names
.bone[Armature.DEF_cog].position  bone lookup by name on a skeleton
```

- `PropertyBinding.sanitizeNodeName(name)` replaces spaces with `_` and strips unsupported characters; GLTFLoader already sanitizes names, so look up nodes by the sanitized name (`'Left_Hand'`, not `'Left Hand'`).
- Morph influences: `'MeshName.morphTargetInfluences'` (all) or `'MeshName.morphTargetInfluences[targetName]'` (one, by `morphTargetDictionary` key).
- `PropertyBinding.findNode(root, nameOrUuid)` is the lookup. PropertyBinding is internal; you rarely construct it.

## 9. Skinning, skeleton, cloning

Pieces: `Bone` (an Object3D, `isBone`), `Skeleton` (`bones[]`, `boneInverses[]`, `boneTexture`, `getBoneByName(n)`, `pose()`, `calculateInverses()`, `dispose()`), `SkinnedMesh` (geometry needs `skinIndex` + `skinWeight` attributes; `bind(skeleton, bindMatrix)`, `bindMode`, `pose()`, `normalizeSkinWeights()`, `applyBoneTransform(index, target)`, `computeBoundingBox/Sphere()`).

```js
const helper = new THREE.SkeletonHelper(gltf.scene);   // draws bones; helper.bones; setColors(c1,c2); dispose()
scene.add(helper);
const hand = skinnedMesh.skeleton.getBoneByName('mixamorigRightHand');
```

Cloning a skinned model: plain `object.clone()` makes the clone share the original skeleton/bones, so both move together or the clone is broken. Use SkeletonUtils:

```js
import * as SkeletonUtils from 'three/addons/utils/SkeletonUtils.js';
const a = SkeletonUtils.clone(gltf.scene);   // clones bones and rebinds SkinnedMeshes; geometry/materials stay shared
scene.add(a);
const mixerA = new THREE.AnimationMixer(a);  // one mixer per clone, share the same clips
```

Shared skeleton (all instances pose identically, one mixer, cheaper) - from `webgl_animation_multiple.html`:

```js
const shared = SkeletonUtils.clone(gltf.scene);
const skin = shared.getObjectByName('vanguard_Mesh');
const rootBone = shared.getObjectByName('mixamorigHips');
scene.add(rootBone);                                   // bones MUST be in the scene graph to be updated
const identity = new THREE.Matrix4();
for (const x of [-2, 0, 2]) {
  const m = skin.clone();
  m.bindMode = THREE.DetachedBindMode;                 // mesh no longer shares world space with bones
  m.bind(skin.skeleton, identity);
  m.position.x = x;
  m.scale.setScalar(0.01); m.rotation.x = -Math.PI / 2;   // reapply the asset's own transform
  scene.add(m);
}
const mixer = new THREE.AnimationMixer(rootBone);      // mixer root = the bone hierarchy
mixer.clipAction(clips[1]).play();
```

Dispose per skinned mesh: `mesh.skeleton.dispose()` (frees bone texture) in addition to geometry/material.

## 10. Retargeting

Apply a clip authored for skeleton A onto skeleton B with different bone names/rest poses (`webgpu_animation_retargeting.html`, Mixamo -> ReadyPlayer):

```js
import * as SkeletonUtils from 'three/addons/utils/SkeletonUtils.js';

const sourceSkeleton = new THREE.Skeleton(new THREE.SkeletonHelper(sourceScene).bones);
const targetSkin = targetScene.getObjectByProperty('isSkinnedMesh', true);

const clip = SkeletonUtils.retargetClip(targetSkin, sourceSkeleton, sourceClip, {
  hip: 'mixamorigHips',             // source hip bone name (default 'hip')
  names: { targetBone: 'sourceBone' },   // OR getBoneName: (bone) => string
  scale: 1,                          // compensate unit/scale differences
  hipInfluence: new THREE.Vector3(1, 1, 1),   // (0,1,0) = drop XZ root motion
  localOffsets: { LeftArm: new THREE.Matrix4().makeRotationY(Math.PI / 4) },   // per-target-bone rest-pose fixups
  trim: [3, 4],                      // seconds, [start,end]
  fps: 30, useFirstFramePosition: false, preserveBoneMatrix: true, preserveBonePositions: true, useTargetMatrix: false, hipPosition: new THREE.Vector3(),
});
const mixer = new THREE.AnimationMixer(targetSkin);   // mixer on the SkinnedMesh, not the scene
mixer.clipAction(clip).play();
```

- `SkeletonUtils.retarget(target, source, options)` is the live variant: call each frame after the source mixer updated (poses target bones from source skeleton).
- Both source/target can be an Object3D with `.skeleton` or a `Skeleton`. Rest poses differing (A-pose vs T-pose) is the usual failure: tune `localOffsets`.

## 11. Morph targets

```js
// BufferGeometry side
geometry.morphAttributes.position = [new THREE.Float32BufferAttribute(arrA, 3), ...];
geometry.morphTargetsRelative = false;   // absolute positions (glTF loaders set relative=true)
const mesh = new THREE.Mesh(geometry, material);   // Mesh builds morphTargetInfluences / morphTargetDictionary
mesh.morphTargetInfluences[0] = 0.5;               // 0..1 (can exceed); Array<number>
mesh.morphTargetDictionary;                         // { Smile: 0, ... } name -> index (glTF target names)
mesh.updateMorphTargets();                          // re-sync after changing geometry.morphAttributes
```

- Animate via clip: `NumberKeyframeTrack('Head.morphTargetInfluences[Smile]', times, values)`, or a glTF clip does it for you. SkinnedMesh and Mesh both work. A glTF with several primitives per mesh may split into several meshes: set influences on every mesh sharing the target names (face examples loop over `head`/`teeth`).
- WebGLRenderer stores morph deltas in a `DataArrayTexture` (WebGLMorphtargets), so target count is not capped by attribute slots, but each extra target costs memory and per-vertex work; keep targets and active influences sparse.
- Addons: `MorphAnimMesh` (`three/addons/misc/MorphAnimMesh.js`: `playAnimation(label, fps)`, `updateAnimation(delta)`, `mixer`, `activeAction`) for legacy morph-sequence geometry; `MorphBlendMesh` also exists (api/MorphBlendMesh.md).
- Examples: `webgl_morphtargets.html`, `webgl_morphtargets_face.html`, `webgpu_morphtargets.html`, `webgpu_morphtargets_face.html`.

## 12. Inverse kinematics (CCD)

```js
import { CCDIKSolver, CCDIKHelper } from 'three/addons/animation/CCDIKSolver.js';

const iks = [{
  target: 22,                         // index into skinnedMesh.skeleton.bones (the goal bone)
  effector: 6,                        // end bone that should reach the target
  links: [{ index: 5, rotationMin: new THREE.Vector3(1.2,-1.8,-.4), rotationMax: new THREE.Vector3(1.7,-1.1,.3) }],  // chain, effector side first
  iteration: 10, minAngle, maxAngle, blendFactor,   // optional
}];
const ik = new CCDIKSolver(skinnedMesh, iks);
scene.add(new CCDIKHelper(skinnedMesh, iks, 0.01));   // or ik.createHelper(0.01)

// loop: AFTER mixer.update(), BEFORE render
mixer?.update(dt);
ik.update();                // optional globalBlendFactor arg; ik.updateOne(iksEntry, blend)
```

The IK bones must be part of the scene graph (example does `skinnedMesh.add(skeleton.bones[0])`). `rotationMin/Max` are Vector3 in the example even though the doc types say number. Example: `webgl_animation_skinning_ik.html`.

## 13. Performance

- Skinning is done on the GPU in the vertex shader (bone matrices in `skeleton.boneTexture`, `SkinnedMesh` -> `skinning` program flag). CPU cost per frame = mixer update + bone matrix recompute (`skeleton.update()` runs automatically on render). Cost scales with bones x animated clones; cull offscreen characters and skip `mixer.update` for them.
- `SkinnedMesh` frustum culling uses `boundingSphere` computed once. If animation moves vertices far from the bind pose, call `skinnedMesh.computeBoundingSphere()` / `computeBoundingBox()` yourself or set `frustumCulled = false`.
- Many identical objects with the same animation state: `AnimationObjectGroup` - one mixer drives all.

```js
const group = new THREE.AnimationObjectGroup(meshA, meshB);   // add()/remove()/uncache() later
const mixer = new THREE.AnimationMixer(group);               // group acts as the root
mixer.clipAction(clip).play();                                // all members animate in lockstep
// remember: tracks must be compatible across members; a property is driven via the group OR directly, not both
```
  Example: `misc_animation_groups.html`.
- Cache control: `mixer.uncacheAction(clip, root)`, `uncacheClip(clip)`, `uncacheRoot(root)` (call `action.stop()` / `stopAllAction()` first); for groups call `group.uncache(obj)`.
- Reuse clips across mixers; clips are immutable data (except `makeClipAdditive`, which mutates).
- Very large crowds: WebGPU examples `webgpu_skinning_instancing.html`, `webgpu_skinning_instancing_individual.html` (WebGPU/TSL examples; check them for instanced skinning); `webgpu_skinning.html` uses `WebGPURenderer` with the same `AnimationMixer` API.

## 14. Other helpers

- `SkeletonHelper(object)`: debug lines per bone; add it to the scene; `helper.bones`.
- `AnimationClip.findByName(clipsOrObject, name)`: returns `null` if missing.
- glTF `KHR_animation_pointer`: `webgl_loader_gltf_animation_pointer.html`.

## 15. Gotchas

- Moving the root model in code while a clip animates the same root node (`.position`) fights the clip: animate a parent group instead.
- `clampWhenFinished` needs `LoopOnce` (or finite repetitions) to matter.
- Reusing the same clip on an object with different node names -> no-op; check console warnings.
- Mixer `timeScale = 0` then `1` pauses/unpauses everything without touching actions.
- Don't forget `timer.update()` before `getDelta()`; first delta after tab switch can be large unless `timer.connect(document)` is used.
- Do not use Euler `.rotation` in tracks; use `.quaternion`.
- Scene scale for glTF Mixamo exports is often 100x (cm); remember it for `retarget` `scale` and shared-skeleton clones.

## 16. See also

- api: `AnimationMixer.md`, `AnimationAction.md`, `AnimationClip.md`, `KeyframeTrack.md`, `VectorKeyframeTrack.md`, `QuaternionKeyframeTrack.md`, `NumberKeyframeTrack.md`, `ColorKeyframeTrack.md`, `BooleanKeyframeTrack.md`, `StringKeyframeTrack.md`, `AnimationObjectGroup.md`, `AnimationUtils.md`, `PropertyBinding.md`, `SkinnedMesh.md`, `Skeleton.md`, `Bone.md`, `SkeletonHelper.md`, `module-SkeletonUtils.md`, `CCDIKSolver.md`, `CCDIKHelper.md`, `MorphAnimMesh.md`, `AnimationClipCreator.md`, `Interpolant.md`, `LinearInterpolant.md`, `CubicInterpolant.md`, `DiscreteInterpolant.md`, `BezierInterpolant.md`, `QuaternionLinearInterpolant.md`, `Timer.md`, `Clock.md`
- https://threejs.org/manual/#animation-system
- https://threejs.org/docs/#AnimationMixer , #AnimationAction , #AnimationClip , #KeyframeTrack , #SkinnedMesh , #Skeleton
- examples: `webgl_animation_skinning_blending`, `webgl_animation_skinning_additive_blending`, `webgl_animation_multiple`, `webgl_animation_skinning_ik`, `webgpu_animation_retargeting`, `misc_animation_keys`, `misc_animation_groups`
