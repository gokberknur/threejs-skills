# NodeMaterial family (three.js r187)

When to read this: you are choosing a `*NodeMaterial`, wiring TSL nodes into material slots, overriding the material pipeline (`setupXXX`, custom lighting model), instancing/skinning/morphing with node materials, migrating `onBeforeCompile`/`ShaderMaterial` code, or you want a complete working material recipe. For TSL syntax and functions read `tsl-cheatsheet.md`. Verified against `src/materials/nodes/*.js`, `src/nodes/**`, the API pages, and `examples/webgpu_*.html` (r187).

## Table of contents

1. Class hierarchy
2. How slots are evaluated (pipeline order, stages)
3. Slot reference: NodeMaterial base
4. Slot reference: subclasses
5. Classic properties and nodes together (tint vs replace, auto-mapping of classic materials)
6. Override hooks (`setupXXX`)
7. Output, fog, MRT, fragmentNode/vertexNode
8. Instancing, BatchedMesh, morph, skinning
9. Custom lighting models
10. Using node materials with WebGLRenderer / WebGL backend
11. onBeforeCompile / ShaderMaterial to TSL
12. Invalidation, caching, serialization
13. Recipes (10)
14. See also

---

## 1. Class hierarchy

Import everything from `three/webgpu` (`import * as THREE from 'three/webgpu'`).

| Class | Extends | `lights` default | Lighting model | Extra slots / notes |
|---|---|---|---|---|
| `NodeMaterial` | `Material` | false | none (unlit: `diffuseColor.rgb`) | all common slots (section 3); the base for custom materials |
| `MeshBasicNodeMaterial` | `NodeMaterial` | true | `BasicLightingModel` (env/lightMap/AO only, no analytic lights) | `setupNormal` = `negateOnBackSide(normalViewGeometry)` |
| `MeshLambertNodeMaterial` | `NodeMaterial` | true | `PhongLightingModel(false)` (diffuse only) | |
| `MeshPhongNodeMaterial` | `NodeMaterial` | true | `PhongLightingModel` | `shininessNode`, `specularNode` |
| `MeshStandardNodeMaterial` | `NodeMaterial` | true | `PhysicalLightingModel` | `emissiveNode`, `metalnessNode`, `roughnessNode` |
| `MeshPhysicalNodeMaterial` | `MeshStandardNodeMaterial` | true | `PhysicalLightingModel` (+ enabled lobes) | clearcoat/sheen/iridescence/anisotropy/transmission/specular/ior/dispersion/retroreflectivity slots |
| `MeshSSSNodeMaterial` | `MeshPhysicalNodeMaterial` | true | `SSSLightingModel` (Physical + thickness scattering) | `thickness*Node` family |
| `MeshToonNodeMaterial` | `NodeMaterial` | true | `ToonLightingModel` (uses `gradientMap` or built-in 2-step) | |
| `MeshMatcapNodeMaterial` | `NodeMaterial` | false | none; multiplies `diffuseColor` by `matcap` via `matcapUV` | |
| `MeshNormalNodeMaterial` | `NodeMaterial` | false | none; color = `packNormalToRGB(normalView)` | |
| `LineBasicNodeMaterial` | `NodeMaterial` | false | none | |
| `LineDashedNodeMaterial` | `NodeMaterial` | false | none | `offsetNode`, `dashScaleNode`, `dashSizeNode`, `gapSizeNode`, `dashOffset` |
| `Line2NodeMaterial` | `NodeMaterial` | false | none | fat lines (`LineSegments2`); dash nodes as above, `lineColorNode` alias |
| `PointsNodeMaterial` | `SpriteNodeMaterial` | false | none | `sizeNode`, plus Sprite's `rotationNode`, `scaleNode`, `sizeAttenuation`; also usable on `Mesh`/instanced quads |
| `SpriteNodeMaterial` | `NodeMaterial` | false | none | `positionNode` (view-space anchor, see below), `rotationNode`, `scaleNode`, `sizeAttenuation`; `transparent = true` by default |
| `ShadowNodeMaterial` | `NodeMaterial` | true | `ShadowMaskModel` (renders received shadow as alpha) | `transparent = true`; classic `ShadowMaterial` equivalent |
| `VolumeNodeMaterial` | `NodeMaterial` | true | `VolumetricLightingModel` | `steps = 25`, `offsetNode`, `scatteringNode`; `side = BackSide`, `transparent`, no depthTest/depthWrite |
| `WoodNodeMaterial` | `MeshPhysicalMaterial` base in `examples/jsm/materials/WoodNodeMaterial.js` (addon) | | | `three/addons/materials/WoodNodeMaterial.js`; `WoodNodeMaterial.fromPreset('walnut', 'gloss')`; not exported from `three/webgpu` |

Class names also appear as `material.type`; `NodeMaterial` types map from classic ones through `renderer.library` (see section 5). Constructors take a parameters object that is applied with `setValues` (works for node slots too): `new THREE.MeshStandardNodeMaterial({ colorNode: ..., roughness: 0.4 })`.

There is no `shadowNode` or `shadowPositionNode` slot on any material (shadows are configured on the light/`LightShadow`, `shadow()`/`pointShadow()` nodes, and the material slots `receivedShadowNode`, `castShadowNode`, `castShadowPositionNode`, `receivedShadowPositionNode`, `maskShadowNode`). `emissiveNode`, `roughnessNode`, `metalnessNode` exist only from `MeshStandardNodeMaterial` down; `sizeNode` only on `PointsNodeMaterial`; `rotationNode`/`scaleNode` on `SpriteNodeMaterial` and `PointsNodeMaterial`.

---

## 2. How slots are evaluated

`NodeMaterial.setup(builder)` (r187) in order:

```
VERTEX stage (builder.addStack)
  setupVertex -> setupPosition:
      morphReference(object)           if geometry has morph position/normal/color
      skinning(object)                 if SkinnedMesh
      displacementMap                  positionLocal += normalLocal * (map * scale + bias)
      batch(object)                    if BatchedMesh
      instancedMesh(object)            if InstancedMesh (with instanceMatrix attribute)
      positionNode                     positionLocal.assign(positionNode)   [sub-build 'POSITION']
    -> modelViewProjection  (or vertexNode, which replaces everything above)
  hardware clipping, geometryNode (bypass: built for side effects)

FRAGMENT stage
  clipping, depth (depthNode / logarithmic depth)
  if fragmentNode === null:
    setupDiffuseColor    maskNode discard; colorNode (or materialColor) x vertexColor x instanceColor x batchColor;
                         opacityNode (or materialOpacity); alphaTestNode/alphaTest (+alphaToCoverage); alphaHash; opaque -> a = 1
    setupAmbientOcclusion  aoNode (or materialAO if aoMap), context.getAO
    setupVariants        subclass-specific: roughness/metalness/clearcoat/... -> property nodes
    setupLighting        lightsNode (or scene lights), envNode / scene env, lightMap, AO, backdropNode/backdropAlphaNode,
                         lighting model (setupLightingModel), + emissive (emissiveNode or materialEmissive)
    basicOutput = vec4(outgoingLight, diffuseColor.a).max(0)
    setupOutput          fog (if material.fog) then premultipliedAlpha
    output.assign(result);   result = outputNode (if set, REPLACES fogged result); context.getOutput; MRT (renderer MRT merged with mrtNode)
  else:
    result = setupOutput(fragmentNode.convert(vec4))   // fog/premultiply still applied; lighting skipped
```

Stage rules:
- Run on the **vertex** stage: `positionNode`, `vertexNode`, `geometryNode`, `castShadowPositionNode` (shadow pass vertex), the vertex part of `Fn`s used there.
- Everything else runs per **fragment**. Attribute-based leaf nodes (`uv()`, `positionLocal`, `normalLocal`, `attribute()`) used in fragment slots are auto-varying.
- `positionWorld` and similar `.once([...sub-builds])` nodes are compiled separately for the `POSITION` (vertex), `NORMAL`, `VERTEX` layers and for fragment, so using `positionWorld` in `positionNode` and `colorNode` is fine.
- `normalNode`, `clearcoatNormalNode` are built in a `NORMAL` sub-build (once per stage) and exposed to lighting as `normalView`.

---

## 3. Slot reference: NodeMaterial base

All `null` by default (`null` = use the classic property / default behavior). Types as documented (the node is converted with `float()/vec3()/vec4()` where noted).

| Slot | Type | Stage | Effect / replaces | Notes |
|---|---|---|---|---|
| `colorNode` | vec3 or vec4 | fragment | replaces `color` x `map` (default `materialColor`) | converted with `vec4()`, so alpha from a vec4 is multiplied with opacity; `vertexColors`/instance color/batch color are still multiplied afterwards |
| `opacityNode` | float | fragment | replaces `opacity` x `alphaMap` (default `materialOpacity`) | multiplied into `diffuseColor.a`; set `material.transparent = true` for blending |
| `alphaTestNode` | float | fragment | threshold; discards when `a <= node` | classic `alphaTest` used when null and > 0; works with `alphaToCoverage` (smoothed) |
| `maskNode` | bool | fragment | `bool(maskNode).not().discard()` runs FIRST | discards when `false`; does not touch alpha; shadow equivalent: `maskShadowNode` |
| `normalNode` | vec3 (view space) | fragment | replaces `normalMap`/`bumpMap` (default `materialNormal`) | must be a view-space normal: `normalMap(...)`, `bumpMap(height, scale, baseNormal?)` (third arg since r187 layers bump on top of e.g. a `normalMap(...)`), `normalView`, `normalFlat`, `modelNormalMatrix.mul(n)`; for world-space use `transformNormalByViewMatrix(n)` |
| `emissiveNode` | vec3 | fragment | added to outgoing light; replaces `emissive` x `emissiveMap` | declared on `MeshStandardNodeMaterial` and, since r187, on `MeshLambertNodeMaterial`, `MeshPhongNodeMaterial`, `MeshToonNodeMaterial`; also honored on any NodeMaterial subclass (`MeshBasicNodeMaterial` example: `webgpu_instance_uniform`); not tone-clamped, HDR values bloom |
| `aoNode` | float | fragment | ambient occlusion: multiplies indirect diffuse/specular | default `materialAO` when `aoMap` present |
| `envNode` | vec3 / lighting node | fragment | replaces env map / `scene.environment` IBL | wrapped in `EnvironmentNode` (Standard/Physical) or `BasicEnvironmentNode` |
| `lightsNode` | `LightsNode` | fragment | selective lights; `lights([])` = no lights; with `.context({ lightingModel })` custom model | when set, lighting runs even if `material.lights === false` |
| `backdropNode` | vec3 | fragment | color visible "behind" the surface; blended into outgoing light | refraction: `viewportSharedTexture(uv)` |
| `backdropAlphaNode` | float | fragment | mix factor of `backdropNode` into outgoing light | `mix(outgoing, backdrop, alpha)`; without it backdrop replaces outgoing |
| `positionNode` | vec3 (local) | VERTEX | replaces `positionLocal` AFTER morph/skin/instance/batch (so it displaces the animated, instanced position) | default none |
| `vertexNode` | vec4 (clip space) | VERTEX | replaces the whole `modelViewProjection` | bypasses positionNode/instancing; you own the clip-space position |
| `geometryNode` | function/node | VERTEX | executed via `bypass` (side effects, e.g. compute dispatch) | rarely needed |
| `depthNode` | float | fragment | custom fragment depth (`depth.assign`) | needs depth buffer; breaks early-Z |
| `fragmentNode` | vec4 | fragment | replaces the entire fragment path (diffuse, lighting) | fog/premultipliedAlpha still applied via `setupOutput`; MRT handling differs |
| `outputNode` | vec4 | fragment | final composite AFTER lighting+fog | replaces the fogged result; the `output` property node still holds the original |
| `mrtNode` | `MRTNode` | fragment | extra MRT attachments for this material | merged with the pass MRT (`pass.setMRT(mrt({...}))`) |
| `contextNode` | `ContextNode` | both | material-wide context: `getUV`, `getAO`, `getShadow`, `overrideNode(s)` | `material.contextNode = overrideNode(positionLocal, () => ...)` |
| `castShadowNode` | vec4 | fragment (shadow pass) | color+opacity of cast (transmitted) shadow | needs `renderer.shadowMap.transmitted = true` |
| `castShadowPositionNode` | vec3 | VERTEX (shadow pass) | position used when rendering the shadow map | keep identical to `positionNode` for displaced meshes |
| `receivedShadowNode` | `Fn(([shadow]) => vec4)` | fragment | custom shading of received shadow | |
| `receivedShadowPositionNode` | vec3 (world) | fragment | position used to sample shadow maps | |
| `maskShadowNode` | bool | fragment (shadow pass) | discard in shadow map pass when `false` | pair with `maskNode` for dissolve |

Non-node flags with node-relevant behavior: `fog` (default true), `lights`, `transparent`, `side`, `blending`, `depthWrite/depthTest`, `alphaToCoverage`, `alphaHash`, `premultipliedAlpha`, `vertexColors`, `flatShading`, `clippingPlanes`.

Gotchas:
- `colorNode` replaces `map`. To modulate: `materialColor.mul(...)`.
- Setting `opacityNode` has no visual effect on an opaque material (`transparent=false`): `diffuseColor.a` is forced to 1 for opaque pass. Set `transparent = true` (and consider `depthWrite = false`).
- Setting `alphaTestNode` alone with `transparent=false` works; `alphaToCoverage` needs MSAA.
- `outputNode` is applied after fog; if you need fog, include it manually or use `fragmentNode`/`colorNode`.
- Assigning a new node to a slot after first render requires `material.needsUpdate = true` (section 12).

---

## 4. Slot reference: subclasses

### MeshStandardNodeMaterial

| Slot | Type | Replaces |
|---|---|---|
| `roughnessNode` | float | `roughness` x `roughnessMap.g` (value passes through `getRoughness`: clamps and adds geometric roughness) |
| `metalnessNode` | float | `metalness` x `metalnessMap.b` |
| `emissiveNode` | vec3 | `emissive` x `emissiveMap` |

### MeshPhysicalNodeMaterial (adds)

A lobe is only compiled in if the classic value is `> 0` **or its node is set** (`useClearcoat`, `useSheen`, `useIridescence`, `useAnisotropy`, `useTransmission`, `useDispersion`, `useRetroreflection`). Setting `clearcoatNode` later to a node when it was null, or toggling `clearcoat` from 0, needs `needsUpdate = true`.

| Slot | Type | Slot | Type |
|---|---|---|---|
| `clearcoatNode` | float | `iridescenceNode` | float |
| `clearcoatRoughnessNode` | float | `iridescenceIORNode` | float |
| `clearcoatNormalNode` | vec3 (view) | `iridescenceThicknessNode` | float (nm) |
| `sheenNode` | vec3 (color) | `anisotropyNode` | vec2 (direction x strength) |
| `sheenRoughnessNode` | float | `transmissionNode` | float |
| `specularIntensityNode` | float | `thicknessNode` | float |
| `specularColorNode` | vec3 | `attenuationDistanceNode` | float |
| `iorNode` | float | `attenuationColorNode` | vec3 |
| `dispersionNode` | float (needs transmission) | `retroreflectivityNode` | float |

### MeshSSSNodeMaterial (adds; SSS enabled only when `thicknessColorNode !== null`)

`thicknessColorNode` (vec3, default null), `thicknessDistortionNode` (0.1), `thicknessAmbientNode` (0.0), `thicknessAttenuationNode` (0.1), `thicknessPowerNode` (2.0), `thicknessScaleNode` (10.0); all `float` except the color.

### MeshPhongNodeMaterial: `shininessNode` (float, clamped >= 1e-4), `specularNode` (vec3).

### PointsNodeMaterial / SpriteNodeMaterial

| Slot | Type | Meaning |
|---|---|---|
| `sizeNode` (Points) | float or vec2 | point size in px (x DPR, attenuated by distance if `sizeAttenuation`); default `materialPointSize` |
| `scaleNode` | float or vec2 | extra scale on size (Points) or on sprite scale (Sprite: multiplies the object's world scale) |
| `rotationNode` | float | rotation (radians) of the quad |
| `positionNode` (Sprite/Points) | vec3 | for `Sprite` and instanced quads the *anchor* position (transformed by `modelViewMatrix`), not a vertex displacement; for `Points` it is the point position (default `positionLocal`) |
| `sizeAttenuation` | boolean | getter/setter, setting recompiles |

`Points` object: `PointsNodeMaterial` runs as sprite billboards (size from `sizeNode`). For a plain `Mesh`/`Sprite` with `count`, GPU-driven particles: `positionNode = positions.element(instanceIndex)`, `mesh.count = N`, `mesh.frustumCulled = false` (guide example).

### Line materials

`LineDashedNodeMaterial` / `Line2NodeMaterial`: `offsetNode`, `dashScaleNode`, `dashSizeNode`, `gapSizeNode` (floats, fall back to material fields via `materialLineDashOffset/Scale/DashSize/GapSize`). Line2: `lineColorNode`, `materialLineWidth`; world units via `worldUnits`, `dashed`, `alphaToCoverage`.

### VolumeNodeMaterial: `steps` (25), `offsetNode`, `scatteringNode`; used with `Box`/`Sphere` mesh, see `RaymarchingBox` (guide 79).

---

## 5. Classic properties and nodes together

Every `*Node` has a classic counterpart that is read through **material accessor nodes**. When the slot is `null`, the accessor is used; when you set the slot, you replace it:

| Accessor node | Composes |
|---|---|
| `materialColor` | `color` x `map` (vec3) |
| `materialOpacity` | `opacity` x `alphaMap` |
| `materialEmissive` | `emissive` x `emissiveIntensity` x `emissiveMap` |
| `materialNormal` | `normalMap` / `bumpMap` / `normalView` |
| `materialRoughness` | `roughness` x `roughnessMap.g` |
| `materialMetalness` | `metalness` x `metalnessMap.b` |
| `materialAO` | `aoMap.r` blend with `aoMapIntensity` |
| `materialLightMap`, `materialEnvIntensity`, `materialEnvRotation` | |
| `materialClearcoat*`, `materialSheen*`, `materialTransmission`, `materialThickness`, `materialIOR`, `materialIridescence*`, `materialAnisotropy`, `materialDispersion`, `materialSpecular*`, `materialAlphaTest`, `materialRotation`, `materialPointSize`, `materialLine*`, `materialShininess` | |
| `materialReference(name, type, material?)` | live uniform on any material property (change `material[name]` freely, no recompile) |

```js
material.colorNode = materialColor.mul(tintUniform);          // keep the map, tint it
material.roughnessNode = materialRoughness.mul(0.5).add(0.1); // keep roughnessMap
material.normalNode = materialNormal;                          // identity (useful to read the evaluated normal)
```

Classic values still work when the slot is `null`: `material.color`, `material.roughness`, `material.map` etc. are uniforms updated each frame without recompile. `material.map = tex` assigned after first render may need `material.needsUpdate = true` (adds/removes the sampler).

Auto-mapping of classic materials: with `WebGPURenderer`, `new THREE.MeshStandardMaterial()` is converted at render time by `renderer.library.fromMaterial` into a `MeshStandardNodeMaterial` (own properties copied). Prefer explicit `*NodeMaterial` classes when you use `*Node` slots, to avoid the copy and for correct `needsUpdate`. The guide also states node slots can be set on classic classes; it works through that copy but changes to the original classic object after conversion are not guaranteed to propagate.

MRT / post-processing should capture **property nodes** (`output`, `diffuseColor`, `roughness`, `metalness`, `emissive`, `normalView`) instead of `material*` accessors, because those hold the evaluated per-pixel values after the variants stage.

---

## 6. Override hooks (`setupXXX`)

Subclass `NodeMaterial` (or any subclass) and override; call `super` where sensible. All receive `builder` (`NodeBuilder`; gives `builder.material`, `.object`, `.geometry`, `.camera`, `.renderer`, `.context`).

| Hook | Returns | Default behavior |
|---|---|---|
| `setup(builder)` | | full pipeline of section 2 |
| `setupVertex(builder)` | clip-space vec4 | runs `setupPosition`, returns `modelViewProjection` |
| `setupPosition(builder)` | `positionLocal` | morph, skinning, displacement, batch, instance, `positionNode` |
| `setupPositionView()` | view-space vec3 | `modelViewMatrix * positionLocal` (Sprite/Points override for billboards) |
| `setupModelViewProjection()` | vec4 | `cameraProjectionMatrix * positionView` |
| `setupDiffuseColor(builder)` | | fills `diffuseColor` (mask, color, opacity, alphaTest) |
| `setupVariants(builder)` | | subclass fills `roughness`, `metalness`, `specularColor`, ... (abstract on base) |
| `setupNormal()` | vec3 | `normalNode` or `materialNormal` |
| `setupEnvironment(builder)` | lighting node | `envNode` / `envMap` / scene env |
| `setupLightMap(builder)` / `setupMaterialLightings` / `setupAmbientOcclusion` | | |
| `setupLightingModel(builder)` | `LightingModel` | subclass choice (abstract on base) |
| `setupLighting(builder)` | outgoing light vec3 | builds `lightingContext(...)`, backdrop, emissive |
| `setupOutgoingLight()` | vec3 | `lights ? vec3(0) : diffuseColor.rgb` |
| `setupOutput(builder, outputNode)` | vec4 | fog then premultiplied alpha |
| `setupFog(builder, outputNode)` / `setupPremultipliedAlpha` | vec4 | |
| `setupDepth`, `setupClipping`, `setupHardwareClipping`, `setupObserver` | | |
| `customProgramCacheKey()` | string | type + hash of all `*Node` slot cache keys |

```js
class GlowMaterial extends THREE.MeshStandardNodeMaterial {
  constructor( params ) { super(); this._glow = uniform( 1 ); this.setValues( params ); }   // plain fields are fine
  setupVariants( builder ) {
    super.setupVariants( builder );                   // sets roughness/metalness/specular
    roughness.assign( roughness.mul( 0.5 ) );         // import { roughness } from 'three/tsl'; edit the evaluated value
  }
  setupOutput( builder, outputNode ) {
    return super.setupOutput( builder, outputNode ).add( vec4( this._glow.mul( 0.1 ), 0 ) );
  }
}
```

Instance-level override works too: `material.setupLightingModel = () => new MyModel();`. Every own property of the material that holds a Node is auto-included in `customProgramCacheKey` and `toJSON` (the key uses the property name minus its last 4 chars, so name Node-valued fields `fooNode`); prefix a Node-valued field with `_` (as `_glow` above) to keep it out of both.

---

## 7. Output, fog, MRT, fragment/vertex overrides

```js
material.fog = false;                              // opt out of scene.fog / scene.fogNode
material.outputNode = vec4(output.rgb.mul(2), output.a);    // tweak the final lit color (output = property node, pre-outputNode)
material.fragmentNode = vec4(uv(), 0, 1);          // bypass lighting entirely
material.vertexNode = cameraProjectionMatrix.mul(modelViewMatrix).mul(vec4(positionLocal, 1));  // full manual clip-space
material.mrtNode = mrt({ mask: float(1) });        // extra attachment for this material
scene.fogNode = fog(color(0x99aabb), rangeFogFactor(5, 40));
```

`renderer.toneMapping`/`outputColorSpace` apply to the final frame (direct render) or, with a `RenderPipeline`, via `renderOutput()` (see cheat sheet 17). Node materials render in linear working space; `color(0xff0000)` and `THREE.Color` hex are already converted.

---

## 8. Instancing, BatchedMesh, morph, skinning

All applied **automatically** by `NodeMaterial.setupPosition` (before `positionNode`), no extra nodes needed:

```js
const mesh = new THREE.InstancedMesh(geometry, new THREE.MeshStandardNodeMaterial(), count);
mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);   // then edit matrices; mesh.instanceMatrix.needsUpdate = true
mesh.setColorAt(i, new THREE.Color());                  // instanceColor is multiplied into colorNode (instanceColor varying)
mesh.count = 500;                                       // draw fewer instances at runtime (no recompile)
```

- Per-instance random data: `range(min, max)` (attribute), `hash(instanceIndex)`; per-instance value from JS: `instancedBufferAttribute(attr)` or a custom `Node` with `updateType = NodeUpdateType.OBJECT` (see `webgpu_instance_uniform`: `update(frame){ this.uniformNode.value.copy(frame.object.color) }`, `setup(){ return this.uniformNode }`).
- GPU-driven matrices: `Instance.js` reads the matrix from a storage buffer when `mesh.instanceMatrix.isStorageInstancedBufferAttribute`; otherwise from a UBO (`buffer(...)`, when the matrices fit the uniform limit) or an `InstancedInterleavedBuffer` attribute.
- Manual: `instance(matricesAttr, colorsAttr?)` (r187 signature; the old `instance(count, matrix, color)` no longer exists) and `instancedMesh(mesh)` are the building blocks; the material calls `instancedMesh(object)` itself.
- `BatchedMesh`: handled by `batch(object)`; per-geometry colors via `batchColor`, multiplied into `colorNode`; `batchIndirectIndex` available. Example: `webgpu_mesh_batch`.
- Morph targets: `morphReference(mesh)` applied when geometry has `morphAttributes.position|normal|color`. `mesh.morphTargetInfluences` update at runtime. Instanced + morph: `webgpu_instancing_morph` (`mesh.morphTexture`).
- Skinning: `skinning(skinnedMesh)` applied for `SkinnedMesh`; `computeSkinning(skinnedMesh, toPosition)` writes skinned positions in a compute pass (see `webgpu_skinning_points`). Instanced skinning: `webgpu_skinning_instancing`.
- `positionLocal` seen by `positionNode` is the already-instanced/skinned/morphed position; `positionGeometry` is the raw attribute.
- Frustum culling uses the original geometry bounds: for GPU-displaced or compute-driven geometry set `mesh.frustumCulled = false`.

---

## 9. Custom lighting models

`THREE.LightingModel` (exported from `three/webgpu`): override `direct(lightData, builder)`, `indirect(builder)`, `directRectArea`, `ambientOcclusion`, `start`, `finish`. `lightData` includes `lightDirection`, `lightColor`, `lightNode`, `reflectedLight` (`directDiffuse`, `directSpecular`, `indirectDiffuse`, `indirectSpecular`). `builder.context` holds `irradiance`, `ambientOcclusion`, `reflectedLight`, `outgoingLight`.

```js
import * as THREE from 'three/webgpu';
import { Fn, normalView, diffuseColor, BRDF_Lambert } from 'three/tsl';

class BandedLighting extends THREE.LightingModel {
  direct( { lightDirection, lightColor, reflectedLight } ) {
    const nl = normalView.dot( lightDirection ).saturate();
    const banded = nl.mul( 3 ).ceil().div( 3 );                       // 3 flat bands
    reflectedLight.directDiffuse.addAssign( banded.mul( lightColor ).mul( BRDF_Lambert( { diffuseColor: diffuseColor.rgb } ) ) );
  }
  indirect( builder ) {                                              // ambient/hemisphere/IBL
    const { irradiance, reflectedLight, ambientOcclusion } = builder.context;
    reflectedLight.indirectDiffuse.addAssign( irradiance.mul( BRDF_Lambert( { diffuseColor: diffuseColor.rgb } ) ).mul( ambientOcclusion ) );
  }
}

class BandedMaterial extends THREE.NodeMaterial {
  constructor( params ) { super(); this.lights = true; this.setValues( params ); }
  setupLightingModel() { return new BandedLighting(); }
}
const m = new BandedMaterial(); m.colorNode = color( 0xff8844 );
```

Also supported without subclassing (`webgpu_lights_custom`): `material.lightsNode = lights([a, b]).context({ lightingModel: new BandedLighting() })`. Model-level built-ins: `BasicLightingModel`, `PhongLightingModel(specular=true)`, `PhysicalLightingModel(clearcoat, sheen, iridescence, anisotropy, transmission, dispersion, retroreflection)`, `ToonLightingModel`, `VolumetricLightingModel`, `ShadowMaskModel`, `SSSLightingModel` (in MeshSSSNodeMaterial). `PhysicalLightingModel.prototype.indirectSpecular` can be monkey-patched (see `webgpu_postprocessing_ssr_denoise`).

---

## 10. WebGLRenderer and the WebGL backend

- `WebGPURenderer` (from `three/webgpu`) picks the WebGPU backend when available and falls back to a WebGL2 backend automatically (`new WebGPURenderer({ forceWebGL: true })` forces it). The same node materials compile to WGSL or GLSL. WebGPU-only features: `wgslFn`, storage textures, atomics, subgroup ops, full compute (the WebGL2 backend emulates storage buffers via attribute/transform feedback with limits), `renderer.compute` semantics.
- Classic `WebGLRenderer` can run node materials through the addon `WebGLNodesHandler`:

```js
import * as THREE from 'three/webgpu';
import { WebGLRenderer } from 'three';
import { WebGLNodesHandler } from 'three/addons/tsl/WebGLNodesHandler.js';

const renderer = new WebGLRenderer({ antialias: true });
renderer.setNodesHandler(new WebGLNodesHandler());      // examples: webgl_tsl_clearcoat, webgl_tsl_instancing, webgl_tsl_shadowmap
const m = new THREE.MeshPhysicalNodeMaterial({ colorNode: ... });
```

Limitations (from the addon source header): VSM shadows, MRT, transmission, the WebGPU post-processing stack (`RenderPipeline`, `pass()`), and storage textures are not supported; fog/environment changes do not auto-update (call `dispose`); an `InstancedMesh` geometry cannot be shared between meshes.

---

## 11. onBeforeCompile / ShaderMaterial to TSL

| Classic chunk / GLSL | TSL slot / node |
|---|---|
| `#include <begin_vertex>` + `transformed += ...` | `material.positionNode = positionLocal.add(...)` |
| `<displacementmap_vertex>` | `displacementMap` (built in) or `positionNode` |
| `<project_vertex>` / `gl_Position = ...` | `material.vertexNode` (rare) |
| `diffuseColor *= texture2D(...)` after `<map_fragment>` | `material.colorNode = materialColor.mul(texture(...))` |
| `diffuseColor.a *= ...`, `<alphamap_fragment>` | `opacityNode` |
| `if (a < t) discard;` / `<alphatest_fragment>` | `alphaTestNode` or `maskNode` (bool, false = discard) |
| `<normal_fragment_maps>` / `normal = ...` | `normalNode` (view space) |
| `<roughnessmap_fragment>`, `<metalnessmap_fragment>` | `roughnessNode`, `metalnessNode` |
| `totalEmissiveRadiance += ...` | `emissiveNode` |
| `<lights_fragment_*>` | custom `LightingModel` / `lightsNode` |
| `gl_FragColor = vec4(...)` at the end of main | `outputNode` (post-lighting) or `fragmentNode` (replaces all) |
| `<fog_fragment>` | `scene.fogNode` / `material.fog` |
| uniform `shader.uniforms.x = { value }` | `uniform(value)`; update `.value` |
| `varying vUv` | `uv()` / `.toVarying()` |

Side by side:

```js
// BEFORE: onBeforeCompile (detail map)
material.onBeforeCompile = (shader) => {
  shader.uniforms.detailMap = { value: detailMap };
  shader.fragmentShader = shader.fragmentShader
    .replace('#define STANDARD', '#define STANDARD\nuniform sampler2D detailMap;')
    .replace('#include <map_fragment>', '#include <map_fragment>\n diffuseColor *= texture2D( detailMap, vMapUv * 10.0 );');
};
// AFTER
const material = new THREE.MeshStandardNodeMaterial({ map: colorMap });
material.colorNode = materialColor.mul(texture(detailMap, uv().mul(10)));
```

```js
// BEFORE: ShaderMaterial wave
new THREE.ShaderMaterial({
  uniforms: { uTime: { value: 0 }, uAmp: { value: 0.2 } },
  vertexShader: `uniform float uTime, uAmp; varying vec2 vUv;
    void main(){ vUv = uv; vec3 p = position; p.z += sin(p.x*4.0 + uTime) * uAmp;
      gl_Position = projectionMatrix * modelViewMatrix * vec4(p,1.0); }`,
  fragmentShader: `varying vec2 vUv; void main(){ gl_FragColor = vec4(vUv, 0.5, 1.0); }`
});
// AFTER (uTime -> built-in `time`, uAmp -> uniform)
const uAmp = uniform(0.2);
const m = new THREE.MeshBasicNodeMaterial();
m.positionNode = positionLocal.add(vec3(0, 0, positionLocal.x.mul(4).add(time).sin().mul(uAmp)));
m.colorNode = vec3(uv(), 0.5);
```

`ShaderMaterial`, `RawShaderMaterial` and `onBeforeCompile` are not handled by `WebGPURenderer` (no code path in `renderers/common`); migrate to node materials (or `wgslFn`/`glslFn`). `glslFn`/`wgslFn` allow reusing GLSL/WGSL function bodies (cheat sheet 20; transpiler in guide 80).

---

## 12. Invalidation, caching, serialization

- A render object's program is keyed by `material.customProgramCacheKey()` (type + hash of all node slots) and material state. **Rebuild triggers**: `material.needsUpdate = true`; changing which nodes are in the slots (assigning a slot after first render, swapping `map`, toggling a feature flag like `transparent`, `fog`, `flatShading`, `vertexColors`, `alphaToCoverage`); changes of light count/shadow state. Cheap path: change `uniform.value`, `material.opacity/color/roughness/...` (observed by `NodeMaterialObserver` and uploaded), textures' `.needsUpdate`. Never recreate nodes per frame.
- `node.needsUpdate = true` bumps the node version (rarely needed).
- `NodeMaterialObserver` (per render object) decides when GPU state refresh is required: tracks material property values/texture versions, geometry attribute versions, instance matrix/color versions, morph/batch textures, object matrix when animated.
- Shared nodes: one node instance can sit in several materials; one `uniform` shared across them updates all. Same graph on two materials = one compiled program only if state also matches.
- `NodeMaterialInstance` (r187, `three/webgpu`, renamed from `ProxyNodeMaterial`): `new THREE.NodeMaterialInstance( nodeMaterial )` reuses the base material's single shader build with its own property values; read per-instance values in the shared graph with `materialReference( 'myColor', 'color' )` and set `inst.myColor = new THREE.Color(...)`. Configure the base material first: node slots like `colorNode` are read-only on instances. Use it for many color/param variants without extra compiles.
- Serialization: `material.toJSON()` writes `inputNodes` (slot -> node uuid) plus a `nodes` table; load with `THREE.NodeMaterialLoader` (materials only) or `THREE.NodeObjectLoader` (whole scenes) from `three/webgpu`; custom Node classes must be registered (`loader.nodes[Type] = Class`, `loader.nodeMaterials[Type] = Class`) and implement `serialize/deserialize`. `ObjectLoader`/`MaterialLoader` from `three` do not know node types.
- Disposal: `material.dispose()` frees programs; `renderer.dispose()` is async in r187.

---

## 13. Recipes

Common header: `import * as THREE from 'three/webgpu';` plus the named `three/tsl` imports shown. Lights assumed present for lit materials.

### 1. Gradient

```js
import { uv, color, mx_ramptb } from 'three/tsl';
const m = new THREE.MeshStandardNodeMaterial({ roughness: 0.5 });
m.colorNode = uv().y.mix(color(0x0b1d51), color(0xff7a59));      // t.mix(a, b): y=0 -> a, y=1 -> b
// equivalent: m.colorNode = mx_ramptb(color(0x0b1d51), color(0xff7a59));   // bottom -> top
// world-space gradient, independent of UV:  positionWorld.y.remapClamp(0, 2).mix(c1, c2)
```

### 2. Fresnel rim light

```js
import { normalView, positionViewDirection, uniform, color, float } from 'three/tsl';
const rimColor = uniform(new THREE.Color(0x66ccff)), rimPower = uniform(3), rimStrength = uniform(1.5);
const m = new THREE.MeshStandardNodeMaterial({ color: 0x223355, roughness: 0.4 });
const fresnel = float(1).sub(normalView.dot(positionViewDirection).saturate()).pow(rimPower);
m.emissiveNode = rimColor.mul(fresnel).mul(rimStrength);        // added after lighting, HDR-friendly
```

### 3. Triplanar (world-space, no UVs)

```js
import { texture, triplanarTexture, positionWorld, normalWorld, float } from 'three/tsl';
map.wrapS = map.wrapT = THREE.RepeatWrapping; map.colorSpace = THREE.SRGBColorSpace;
const m = new THREE.MeshStandardNodeMaterial();
// (texX, texY?, texZ?, scale, position, normal); defaults: position = positionLocal, normal = normalLocal
m.colorNode = triplanarTexture(texture(map), null, null, float(0.5), positionWorld, normalWorld);
// pass three different texture nodes for X/Y/Z to vary per axis. Use positionLocal/normalLocal for object-attached mapping.
```

### 4. Dissolve (mask + glowing edge, shadow-correct)

```js
import { mx_noise_float, positionLocal, uniform, color, smoothstep } from 'three/tsl';
const progress = uniform(0);                                        // 0..1 animate in JS: progress.value = ...
const edgeColor = color(0xff6a00);
const n = mx_noise_float(positionLocal.mul(4)).mul(0.5).add(0.5);  // 0..1
const d = n.sub(progress);                                          // > 0 = still visible
const m = new THREE.MeshStandardNodeMaterial({ color: 0x888888 });
m.maskNode = d.greaterThan(0);                                      // discard when false
m.maskShadowNode = d.greaterThan(0);                                // dissolved parts cast no shadow
m.emissiveNode = edgeColor.mul(smoothstep(0, 0.08, d).oneMinus()).mul(4);   // WGSL: edge0 < edge1 required, so use oneMinus()
m.side = THREE.DoubleSide;
```

### 5. Animated vertex noise (displacement)

```js
import { Fn, positionLocal, normalLocal, normalFlat, mx_noise_float, time, uniform, vec3 } from 'three/tsl';
const amp = uniform(0.15), freq = uniform(2.5);
const displaced = Fn(() => {
  const n = mx_noise_float(positionLocal.mul(freq).add(vec3(0, time.mul(0.6), 0)));
  return positionLocal.add(normalLocal.mul(n.mul(amp)));
})();
const m = new THREE.MeshStandardNodeMaterial({ roughness: 0.35 });
m.positionNode = displaced;                  // vertex stage; sees the instanced/skinned position
m.castShadowPositionNode = displaced;        // keep shadows matching the displacement
m.normalNode = normalFlat;                   // lighting from displaced geometry (faceted); smooth normals would need finite differences
// geometry needs enough subdivisions (e.g. IcosahedronGeometry(1, 32)); set mesh.frustumCulled = false if displacement is large
```

### 6. Toon with outline

```js
import { positionLocal, normalLocal, color } from 'three/tsl';
const toon = new THREE.MeshToonNodeMaterial({ color: 0x4488ff });          // optional gradientMap: DataTexture (NearestFilter) for N bands
const outline = new THREE.MeshBasicNodeMaterial({ side: THREE.BackSide });   // inverted hull
outline.colorNode = color(0x000000);
outline.positionNode = positionLocal.add(normalLocal.mul(0.03));            // thickness in local units; for screen-constant width scale by distance
const group = new THREE.Group();
group.add(new THREE.Mesh(geometry, toon), new THREE.Mesh(geometry, outline));
// post-process alternative: toonOutlinePass(scene, camera, color, thickness, alpha) from 'three/tsl' (ToonOutlinePassNode)
```

### 7. Hologram

```js
import { normalView, positionViewDirection, positionLocal, time, color, mix, vec3, float } from 'three/tsl';
const fres = normalView.dot(positionViewDirection).saturate().oneMinus().pow(2);
const scan = positionLocal.y.mul(40).sub(time.mul(2.5)).sin().mul(0.5).add(0.5);
const flicker = time.mul(25).sin().mul(0.03).add(0.97);
const base = mix(color(0x00d4ff), color(0xff00ff), positionLocal.y.mul(0.5).add(0.5));
const m = new THREE.MeshBasicNodeMaterial({ transparent: true, side: THREE.DoubleSide, depthWrite: false, blending: THREE.AdditiveBlending });
m.colorNode = base.mul(scan.mul(0.5).add(0.5)).mul(flicker);
m.opacityNode = fres.mul(0.7).add(scan.mul(0.2)).add(0.15);
```

### 8. Water surface (refraction + ripples)

```js
import { positionWorld, positionLocal, normalLocal, time, mx_noise_float, vec2, vec3, screenUV, viewportSharedTexture, viewportSafeUV, color, float } from 'three/tsl';
const t = time.mul(0.5);
const p = positionWorld.xz;
const ripple = mx_noise_float(vec3(p.mul(1.5), t)).add(mx_noise_float(vec3(p.mul(4).add(10), t.mul(1.8))).mul(0.5));
const uvR = viewportSafeUV(screenUV.add(vec2(ripple.mul(0.02), ripple.mul(0.02))));   // depth-aware: no foreground leaking
const water = new THREE.MeshBasicNodeMaterial({ transparent: true });
water.colorNode = color(0x2d9cdb).mul(ripple.mul(0.25).add(0.75));                   // surface tint + highlights
water.backdropNode = viewportSharedTexture(uvR).mul(color(0xbfe6ff));                // what is behind, distorted
water.backdropAlphaNode = float(0.8);                                                // blend ratio of backdrop into outgoing light
water.positionNode = positionLocal.add(normalLocal.mul(ripple.mul(0.05)));            // gentle waves along the surface normal (plane mesh rotated flat)
// full depth-faded version: three.js example webgpu_backdrop_water (viewportLinearDepth, linearDepth(), viewportDepthTexture)
```

`backdropNode` needs `transparent = true` so the scene behind is already rendered.

### 9. Detail map

```js
import { texture, uv, materialColor, materialRoughness } from 'three/tsl';
detailMap.wrapS = detailMap.wrapT = THREE.RepeatWrapping;
const m = new THREE.MeshStandardNodeMaterial({ map: colorMap });
const detail = texture(detailMap, uv().mul(10));
m.colorNode = materialColor.mul(detail.rgb.mul(2));      // grey-neutral detail around 0.5 keeps overall brightness
m.roughnessNode = materialRoughness.mul(detail.g);
// per-material UV animation / scale for ALL textures of the material: m.contextNode = uv().context({ getUV: () => uv().mul(2) })
```

### 10. Screen-space effect with `viewportSharedTexture` (chromatic glass)

```js
import { viewportSharedTexture, screenUV, normalView, vec3, float } from 'three/tsl';
const m = new THREE.MeshBasicNodeMaterial({ transparent: true });       // transparent => drawn after opaques, so the scene is already in the buffer
const off = normalView.xy.mul(0.03);                                     // refract along view-space normal
const r = viewportSharedTexture(screenUV.add(off)).r;
const g = viewportSharedTexture(screenUV).g;
const b = viewportSharedTexture(screenUV.sub(off)).b;
m.colorNode = vec3(r, g, b).mul(1.05);
// pixelation instead:  const blocks = vec2(80, 45); viewportSharedTexture(screenUV.mul(blocks).floor().div(blocks))
// invert: viewportSharedTexture().rgb.oneMinus()
```

`viewportSharedTexture` shares one framebuffer copy across all uses in a frame and preserves render order (objects drawn before the material appear in it, later ones do not). Use `viewportMipTexture`/`hashBlur` for blurred refraction. Do not combine with `renderer.shadowMap` transmission assumptions; keep such materials last (`mesh.renderOrder`).

### Bonus: per-object value via custom Node

```js
class ObjectColor extends THREE.Node {
  constructor() { super('vec3'); this.updateType = THREE.NodeUpdateType.OBJECT; this.u = uniform(new THREE.Color()); }
  update(frame) { this.u.value.copy(frame.object.color); }     // mesh.color set by user
  setup() { return this.u; }
}
material.colorNode = new ObjectColor();
```

---

## 14. See also

- `tsl-guide/11-node-material.md`, `69-material-inputs.md`, `20-properties.md`, `50-shadows.md`, `48-lights.md`, `49-light-functions.md`, `55-mrt.md`, `72-context.md`, `76-override-node.md`, `78-sub-builds.md`, `79-raymarching.md`, `17-function.md`, `31-attributes.md`, `47-viewport.md`, `61-rotate.md`, `63-random.md`.
- `tsl-reference.md` (material accessors `material*`, property nodes, `instance`, `batch`, `morphReference`, `skinning`).
- API pages: `NodeMaterial.md`, `MeshStandardNodeMaterial.md`, `MeshPhysicalNodeMaterial.md`, `MeshSSSNodeMaterial.md`, `PointsNodeMaterial.md`, `SpriteNodeMaterial.md`, `VolumeNodeMaterial.md`, `Line2NodeMaterial.md`, `ShadowNodeMaterial.md`, `WoodNodeMaterial.md`, `LightingModel.md`, `PhysicalLightingModel.md`, `NodeMaterialObserver.md`, `NodeMaterialLoader.md`, `NodeObjectLoader.md`, `RenderPipeline.md`.
- `tsl-cheatsheet.md` (syntax and semantics).
- https://threejs.org/tsl/ and https://threejs.org/docs/#TSL
