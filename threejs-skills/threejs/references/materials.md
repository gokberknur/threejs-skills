# Materials and Textures (three.js r186)

When to read this: choosing a material, setting up PBR maps, fixing transparency/sorting problems, color-space (too dark / washed out) issues, writing ShaderMaterial or patching built-in shaders, or configuring Texture objects (transforms, UV channels, data/video/canvas/compressed/3D textures). For loading files into textures see `loaders-assets.md`. For TSL/node authoring depth see the `threejs-tsl-webgpu` skill.

## Contents
1. Material selection table
2. Common `Material` properties
3. Transparency and sorting
4. Standard / Physical PBR properties and map slots
5. Other mesh materials (Basic, Lambert, Phong, Toon, Matcap, Normal, Depth, Distance, Shadow)
6. Points, Sprite, Line materials
7. Textures: color space, UV channel, transforms, filtering
8. Texture subclasses (Video, Canvas, Data, Compressed, Cube, DataArray, Data3D, Depth)
9. ShaderMaterial / RawShaderMaterial, uniforms, defines, onBeforeCompile
10. NodeMaterial family (WebGPURenderer, also WebGL)
11. needsUpdate triggers and dispose
12. See also

---

## 1. Material selection table

Cost order (cheapest first): Basic < Lambert < Phong < Standard < Physical. Use the simplest that gives the look.

| Material | Lit | Model | Key props | Use for |
|---|---|---|---|---|
| `MeshBasicMaterial` | no | flat color/map | `color map alphaMap aoMap lightMap envMap combine reflectivity` | UI, unlit, baked textures, debug, backgrounds |
| `MeshLambertMaterial` | yes | diffuse only, no specular (per-fragment in r186) | `color emissive map normalMap bumpMap envMap` | matte, mobile, many objects |
| `MeshPhongMaterial` | yes | Blinn-Phong specular | `shininess(30) specular(0x111111) ...` | cheap shiny, legacy content |
| `MeshToonMaterial` | yes | banded by `gradientMap` | `gradientMap` (Nearest filters!) | cel shading |
| `MeshStandardMaterial` | yes | PBR metal/rough | `roughness(1) metalness(0) maps...` | default choice for realistic |
| `MeshPhysicalMaterial` | yes | PBR + extensions | clearcoat, sheen, transmission, iridescence, anisotropy, ior, dispersion | glass, car paint, fabric, gems |
| `MeshMatcapMaterial` | no (baked) | lookup by view-space normal | `matcap` | sculpt previews, cheap stylized, no lights needed |
| `MeshNormalMaterial` | no | view-space normals as RGB | `flatShading normalMap` | debug |
| `MeshDepthMaterial` | no | depth to color | `depthPacking` | depth effects, `scene.overrideMaterial` |
| `MeshDistanceMaterial` | no | point-light shadow distance | | internal; use as `customDistanceMaterial` |
| `ShadowMaterial` | no | transparent, shows only received shadows | `color opacity` | AR/ground shadow catcher |
| `PointsMaterial` | no | point sprites | `size sizeAttenuation map` | particles |
| `SpriteMaterial` | no | billboard | `map rotation sizeAttenuation` | labels, billboards (use with `Sprite`) |
| `LineBasicMaterial` / `LineDashedMaterial` | no | 1px lines | `color`, dash: `dashSize gapSize scale` | wire/helpers (call `line.computeLineDistances()` for dashes) |
| `ShaderMaterial` / `RawShaderMaterial` | custom | your GLSL | `uniforms vertexShader fragmentShader` | custom effects (WebGLRenderer only) |
| `*NodeMaterial` | per class | TSL node graph | `colorNode positionNode ...` | WebGPURenderer-first; custom without GLSL |

Notes:
- Manual says Lambert is per-vertex; the r186 API page says Lambert uses per-fragment shading. Trust the API page (doc gap in the manual).
- Phong/Basic `reflectivity` + `combine` (`MultiplyOperation | MixOperation | AddOperation`) control envMap blending; Standard uses `envMapIntensity` instead.
- Material properties can be set in the constructor (`new MeshStandardMaterial({ color: 0xff0000 })`), via `setValues({...})`, or directly. `color` accepts hex, CSS string, `Color`.
- `material.color.set('#ff8800')` / `setHex` / `setStyle` treat input as sRGB and convert to linear (ColorManagement enabled by default). `color.r/g/b` and `setRGB(r,g,b)` are raw linear working-space values.
- `MeshStandardMaterial.flatShading`, `wireframe`, `emissive`, `emissiveIntensity`, `envMapRotation` (Euler), `normalMapType` (`TangentSpaceNormalMap` default | `ObjectSpaceNormalMap`).

```js
import * as THREE from 'three';
const m = new THREE.MeshStandardMaterial({ color: '#c0c0c0', roughness: 0.4, metalness: 1 });
```

---

## 2. Common `Material` properties

All defaults per the Material API page.

| Property | Default | Notes |
|---|---|---|
| `side` | `FrontSide` | `BackSide`, `DoubleSide`. Open surfaces (planes, leaves) need `DoubleSide`. |
| `shadowSide` | `null` | null = opposite of `side` casts shadows (FrontSide material -> back faces cast). Fix acne/peter-panning by setting explicitly. |
| `transparent` | `false` | Puts object in the transparent queue (sorted back-to-front, drawn after opaque). |
| `opacity` | `1` | Only honored when `transparent: true` (or alphaHash). |
| `alphaTest` | `0` | Discard fragments with alpha below value. No sorting needed. Typical 0.5 for cutouts. |
| `alphaHash` | `false` | Stochastic (noisy) transparency, no sorting problems; best with TAA. |
| `alphaToCoverage` | `false` | Needs MSAA (`antialias: true`); smooths alphaTest/clipping edges. |
| `premultipliedAlpha` | `false` | Set true if texture/output is premultiplied. |
| `depthTest` / `depthWrite` | `true` / `true` | `depthFunc` default `LessEqualDepth`. Transparent overlays: `depthWrite=false`. Always-on-top: `depthTest=false` (+ `renderOrder`). |
| `colorWrite` | `true` | `false` = depth-only pre-pass / stencil masks. |
| `blending` | `NormalBlending` | `NoBlending, NormalBlending, AdditiveBlending, SubtractiveBlending, MultiplyBlending, CustomBlending`. |
| `blendSrc/blendDst/blendEquation` (+ `...Alpha`) | | Only used with `CustomBlending`. `blendColor`/`blendAlpha` for constant factors. |
| `polygonOffset` (+ `Factor`, `Units`) | `false` | Fix z-fighting for decals / outlined solids: `polygonOffset:true, polygonOffsetFactor:-1, polygonOffsetUnits:-1`. |
| `toneMapped` | `true` | WebGLRenderer: ignored when rendering to a render target or with post-processing. WebGPURenderer: all materials honor tone mapping (property ignored). Set false for UI/unlit materials that must keep exact colors. |
| `dithering` | `false` | Reduces banding in gradients (fog, dark scenes). |
| `vertexColors` | `false` | Multiplies `color` by `geometry.attributes.color` (RGB itemSize 3 or RGBA 4). Attribute data is linear working space. |
| `wireframe` | `false` | Not on base `Material`; exists on Basic/Lambert/Phong/Toon/Normal/Matcap/Depth/Standard/ShaderMaterial. `wireframeLinewidth` is SVGRenderer-only (WebGL/WebGPU always 1px). |
| `fog` | `true` (most) | Set false to ignore `scene.fog`. ShaderMaterial default false: set `fog:true` and `#include <fog_*>` chunks. |
| `clippingPlanes` | `null` | Array of `Plane`. Per-material planes need `renderer.localClippingEnabled = true`; global ones via `renderer.clippingPlanes`. `clipIntersection` (default false = union), `clipShadows` (false). |
| `forceSinglePass` | `false` | DoubleSide+transparent normally draws 2 passes (back, then front). `true` = one pass; use for grass/leaf cards to halve draw calls. |
| `stencilWrite` | `false` | With `stencilFunc stencilRef stencilFuncMask stencilWriteMask stencilFail stencilZFail stencilZPass`. Portals, outlines, masks. |
| `precision` | `null` | `'highp'|'mediump'|'lowp'` override of renderer precision. |
| `allowOverride` | `true` | `false` = `scene.overrideMaterial` skips this material. |
| `visible` | `true` | Hides objects using it. |
| `userData`, `name`, `uuid`, `id`, `type`, `version` | | |

Methods: `clone()`, `copy(src)`, `setValues(obj)`, `dispose()`, `toJSON()`, `onBeforeCompile(shader, renderer)`, `onBeforeRender(...)`, `customProgramCacheKey()`. Event: `dispose`.

```js
// Decal over a surface: no z-fight, doesn't write depth
const decal = new THREE.MeshBasicMaterial({
  map: tex, transparent: true, depthWrite: false,
  polygonOffset: true, polygonOffsetFactor: -4,
});

// Stencil mask (write 1 where this mesh is, then draw others only where stencil == 1)
const mask = new THREE.MeshBasicMaterial({
  colorWrite: false, depthWrite: false, stencilWrite: true,
  stencilRef: 1, stencilFunc: THREE.AlwaysStencilFunc, stencilZPass: THREE.ReplaceStencilOp,
});
const masked = new THREE.MeshStandardMaterial({
  stencilWrite: true, stencilRef: 1, stencilFunc: THREE.EqualStencilFunc,
});
// give mask a lower renderOrder than masked
```

WebGLRenderer ctor option `stencil` defaults to false in r186 source: pass `stencil: true` to get a stencil buffer.

---

## 3. Transparency and sorting

Why it is hard: depth buffer is per-pixel, triangles drawn in index order. A transparent triangle drawn first writes depth and blocks everything behind drawn later. three.js sorts whole objects (not triangles) back-to-front by distance of object origin, after opaque objects.

Choose by need:

| Need | Solution |
|---|---|
| Hard-edged cutout (leaves, fences, grass) | `alphaTest: 0.5` (+ `alphaToCoverage: true` with MSAA). No `transparent` needed; sorting-free. |
| Soft semi-transparent single convex object | `transparent: true, opacity` + `side: DoubleSide` (renders back then front automatically). |
| Many overlapping soft particles/sprites | `transparent:true, depthWrite:false` (+ `blending: AdditiveBlending` for glow). |
| Sorting-free stochastic alpha | `alphaHash: true` (noisy; add TAA). |
| Glass/liquid with refraction | `MeshPhysicalMaterial.transmission` (not `opacity`). |
| Hidden-triangle artefacts on concave transparent mesh | Split mesh in two (back-face copy `renderOrder` lower, front-face copy higher), or `depthWrite:false`. |
| Always on top (HUD, gizmo) | `depthTest:false, transparent:true`, high `renderOrder`. |

Control order manually:
- `object.renderOrder` (number, default 0): lower draws first. Sorted within opaque and transparent lists; group-level `Group.renderOrder` affects children (see Object3D docs).
- Per object: `mesh.frustumCulled`, `Object3D.onBeforeRender`.
- Different transparent objects intersecting each other cannot be fixed by sorting; split geometry or use alphaTest/alphaHash.

Gotchas:
- `opacity < 1` without `transparent: true` does nothing.
- `texture` with alpha channel + no `transparent`/`alphaTest` renders fully opaque (alpha ignored).
- `transparent: true` objects with `depthWrite:true` can occlude later-drawn objects: if background things vanish, set `depthWrite:false`.
- `transmission > 0` renders opaque scene to an internal buffer first; set `opacity: 1`. Resolution: `WebGLRenderer.transmissionResolutionScale`. Transmissive objects do not see other transmissive objects through themselves well; keep `thickness` meaningful.
- Switching `transparent` at runtime: set `material.needsUpdate = true`.
- Premultiplied alpha textures: `texture.premultiplyAlpha = true` and/or `material.premultipliedAlpha = true` (note premultiplyAlpha has no effect for ImageBitmap; configure at bitmap creation).

```js
const leaves = new THREE.MeshStandardMaterial({
  map: leafTex, alphaTest: 0.5, side: THREE.DoubleSide, alphaToCoverage: true, forceSinglePass: true,
});
const glow = new THREE.MeshBasicMaterial({
  color: 0x44aaff, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
});
```

---

## 4. MeshStandardMaterial / MeshPhysicalMaterial

### Scalars and maps (Standard)

| Property | Default | Texture channel / semantic | Color space |
|---|---|---|---|
| `color` | white | multiplied with `map` | |
| `map` | null | RGB(A) albedo | `SRGBColorSpace` |
| `roughness` | 1 | x `roughnessMap` | |
| `roughnessMap` | null | **G** channel | NoColorSpace |
| `metalness` | 0 | x `metalnessMap` | |
| `metalnessMap` | null | **B** channel | NoColorSpace |
| `normalMap` + `normalScale` (Vector2, default (1,1)) | null | tangent space (default) | NoColorSpace |
| `normalMapType` | `TangentSpaceNormalMap` | or `ObjectSpaceNormalMap` | |
| `bumpMap` + `bumpScale` | null | grayscale height; ignored if normalMap set | NoColorSpace |
| `displacementMap` + `displacementScale`, `displacementBias` | null | moves vertices (needs dense geometry); casts shadows | NoColorSpace |
| `aoMap` + `aoMapIntensity` | null | **R** channel; needs second UV set (`uv1`) unless you set `aoMap.channel = 0` | NoColorSpace |
| `lightMap` + `lightMapIntensity` | null | baked illuminance, second UV set | usually `LinearSRGBColorSpace` (EXR/HDR) |
| `emissive` (black) + `emissiveIntensity` (1) + `emissiveMap` | | emissive RGB; set `emissive` to white to see the map | `SRGBColorSpace` |
| `alphaMap` | null | **G** channel; needs `transparent` or `alphaTest` | NoColorSpace |
| `envMap` + `envMapIntensity` (1) + `envMapRotation` (Euler) | null | overrides `scene.environment` | float env: `LinearSRGBColorSpace` + PMREM |
| `flatShading`, `wireframe`, `fog` | false, false, true | | |

Per-channel packing: glTF ORM texture = AO in R, roughness in G, metalness in B, so assign the same texture to `aoMap`, `roughnessMap`, `metalnessMap`.

Environment: `scene.environment = envTex` supplies IBL to all Standard/Physical materials lacking `envMap`. `material.envMap` wins. `envMapIntensity` applies only to material envMap on r186-style materials; for `scene.environment` use `scene.environmentIntensity` and `scene.environmentRotation`.

```js
const mat = new THREE.MeshStandardMaterial({
  map: albedo,                 // SRGBColorSpace
  normalMap: normal,           // NoColorSpace
  roughnessMap: orm, metalnessMap: orm, aoMap: orm,
  roughness: 1, metalness: 1,  // multiplied with maps; keep 1 when using maps
  normalScale: new THREE.Vector2(1, 1),
});
// aoMap/lightMap read uv1: geometry.setAttribute('uv1', geometry.attributes.uv) or set aoMap.channel = 0
```

Gotchas:
- With maps, leave `roughness`/`metalness` at 1 (they multiply). Setting `metalness: 0` with a metalnessMap kills the map.
- No lights or environment -> Standard renders black. Add `scene.environment` or lights.
- `normalScale.y` negative flips green channel (DirectX vs OpenGL normal maps).
- Double-sided with normal maps is handled; mirrored UVs need correct tangents (computed in shader from derivatives).
- `displacementMap` on low-poly meshes does nothing visible; subdivide geometry.

### MeshPhysicalMaterial extras

Defaults in parentheses. All `*Map`s except color ones are NoColorSpace.

| Feature | Properties |
|---|---|
| Clearcoat | `clearcoat`(0), `clearcoatRoughness`(0), `clearcoatMap` (R), `clearcoatRoughnessMap` (G), `clearcoatNormalMap`, `clearcoatNormalScale`(1,1) |
| Sheen (fabric) | `sheen`(0), `sheenColor`(black), `sheenRoughness`(1), `sheenColorMap` (sRGB), `sheenRoughnessMap` (A) |
| Transmission (glass) | `transmission`(0), `transmissionMap` (R), `thickness`(0, mesh-local units), `thicknessMap` (G), `attenuationColor`(white), `attenuationDistance`(Infinity, world units, >0), `ior`(1.5, range 1..2.333), `dispersion`(0, needs transmission) |
| Iridescence | `iridescence`(0), `iridescenceIOR`(1.3), `iridescenceMap` (R), `iridescenceThicknessRange`([100,400]), `iridescenceThicknessMap` (G) |
| Anisotropy | `anisotropy`(0..1), `anisotropyRotation`(radians), `anisotropyMap` (RG direction, B strength) |
| Specular (non-metal F0) | `specularIntensity`(1), `specularColor`(white), `specularIntensityMap` (A), `specularColorMap` (sRGB), `reflectivity`(0.5 == ior 1.5, linked to `ior`) |
| Retroreflection (new) | `retroreflectivity`(0..1) |

```js
const glass = new THREE.MeshPhysicalMaterial({
  transmission: 1, thickness: 0.5, ior: 1.5, roughness: 0.05,
  attenuationColor: 0x88ccff, attenuationDistance: 2, dispersion: 0.3,
});                       // opacity must stay 1; do not set transparent
const paint = new THREE.MeshPhysicalMaterial({ color: 0xaa0000, metalness: 0.9, roughness: 0.4, clearcoat: 1, clearcoatRoughness: 0.05 });
```

Gotchas:
- Physical is the most expensive built-in; each enabled feature adds shader cost and a distinct program variant. Leave unused features at 0.
- `ior` and `reflectivity` are coupled; set one.
- Transmission needs something to refract: set `scene.environment` or have objects behind.
- `thickness` 0 = thin-walled (no refraction offset).

---

## 5. Other mesh materials

```js
new THREE.MeshBasicMaterial({ color, map, alphaMap, aoMap, lightMap, envMap, combine: THREE.MultiplyOperation, reflectivity: 1, fog: true });
new THREE.MeshLambertMaterial({ color, emissive, map, normalMap, bumpMap, envMap /* ... */ });
new THREE.MeshPhongMaterial({ color, specular: 0x111111, shininess: 30, flatShading: false });
// Toon: gradientMap must have Nearest filters, NoColorSpace
const g = new THREE.DataTexture(new Uint8Array([60, 160, 255]), 3, 1, THREE.RedFormat);
g.minFilter = g.magFilter = THREE.NearestFilter; g.needsUpdate = true;
new THREE.MeshToonMaterial({ color: 0x44aa88, gradientMap: g });
new THREE.MeshMatcapMaterial({ matcap: matcapTex });          // matcap: SRGBColorSpace (png/jpg), Linear for EXR
new THREE.MeshNormalMaterial({ flatShading: true });
new THREE.MeshDepthMaterial({ depthPacking: THREE.RGBADepthPacking });  // BasicDepthPacking default
new THREE.ShadowMaterial({ color: 0x000000, opacity: 0.4 });  // ShadowMaterial sets transparent: true by default; mesh.receiveShadow = true
```

Shadow overrides: `mesh.customDepthMaterial` (directional/spot shadows) and `mesh.customDistanceMaterial` (point light) -- required when vertex displacement (ShaderMaterial / onBeforeCompile / `displacementMap` on custom) must also move the shadow caster. `MeshDepthMaterial`/`MeshDistanceMaterial` accept `map`, `alphaMap`, `displacementMap` so alpha-cutout and displacement shadows match.

---

## 6. Points, Sprite, Line materials

```js
const pts = new THREE.Points(geo, new THREE.PointsMaterial({
  size: 0.1, sizeAttenuation: true,   // size in world units if attenuated, else CSS-ish pixels
  map: spriteTex, alphaTest: 0.5, vertexColors: true, depthWrite: false,
}));
const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, color: 0xffffff, rotation: 0, sizeAttenuation: true }));
const line = new THREE.Line(geo, new THREE.LineDashedMaterial({ color: 0xffffff, dashSize: 1, gapSize: 0.5, scale: 1 }));
line.computeLineDistances();           // required for dashes
```

- `LineBasicMaterial.linewidth` is honored only by SVGRenderer; WebGL and WebGPU always draw 1px lines. Thick lines: `Line2` / `LineMaterial` (addons, WebGL) or `Line2NodeMaterial` (WebGPU, `worldUnits`, `dashed`, `lineColorNode`).
- `PointsMaterial.size` may be capped by `gl.ALIASED_POINT_SIZE_RANGE`. Sprites/points with a texture alpha: use `alphaTest` or `transparent`.
- `SpriteMaterial`: sprites are always camera-facing; `transparent` defaults true on SpriteMaterial.
- Points/Sprite/Line ignore lights.

---

## 7. Textures

### Color space rules (most common source of "too dark"/"washed out")

| Texture use | `texture.colorSpace` |
|---|---|
| `map`, `emissiveMap`, `sheenColorMap`, `specularColorMap`, `matcap` (png/jpg), `scene.background` image | `THREE.SRGBColorSpace` |
| `normalMap, roughnessMap, metalnessMap, aoMap, bumpMap, displacementMap, alphaMap, transmissionMap, thicknessMap, clearcoat*Map, gradientMap, anisotropyMap` | `THREE.NoColorSpace` (default) |
| HDR/EXR env, lightMap, float data | `THREE.LinearSRGBColorSpace` (HDRLoader/EXRLoader set it) |

- `Texture.colorSpace` defaults to `NoColorSpace`: a color map loaded without setting `SRGBColorSpace` renders too dark/contrasty. `TextureLoader` does NOT set it for you. GLTFLoader sets it per slot.
- Working space is linear (`LinearSRGBColorSpace`); `WebGLRenderer.outputColorSpace` defaults to `SRGBColorSpace`. `THREE.ColorManagement.enabled = true` by default: hex / CSS strings are converted from sRGB to linear automatically on set; `color.getHex()` converts back.
- Material colors, light colors, vertex color attributes are linear working space. Use `color.setRGB(r,g,b)` for raw linear, `.setHex(0x808080, LinearSRGBColorSpace)` to override.
- Post-processing: output conversion happens in `OutputPass`; missing it = dark, double = washed out.
- Custom `ShaderMaterial` does not convert output: add `#include <tonemapping_fragment>` and `#include <colorspace_fragment>` at end of fragment `main()`.
- Render targets: sRGB 8-bit is precise; linear needs half-float. Textures sampled from render targets are already in the target's space.
- WebGPURenderer VideoTexture: must set `colorSpace = SRGBColorSpace`.
- Prefer glTF 2.0; many legacy formats carry wrong/no color space info.

### Generic Texture properties

| Property | Default | Notes |
|---|---|---|
| `colorSpace` | `NoColorSpace` | see above |
| `wrapS`, `wrapT` | `ClampToEdgeWrapping` | `RepeatWrapping`/`MirroredRepeatWrapping` needed for tiling. Non-power-of-two OK in WebGL2/WebGPU. |
| `magFilter` / `minFilter` | `LinearFilter` / `LinearMipmapLinearFilter` | Data textures: use `NearestFilter` and `generateMipmaps = false`. |
| `generateMipmaps` | `true` | Set false if filter has no mipmaps or you provide `mipmaps`. |
| `anisotropy` | `Texture.DEFAULT_ANISOTROPY` (1) | Set to `renderer.capabilities.getMaxAnisotropy()` (WebGL) for floors seen at grazing angles. |
| `flipY` | `true` | Ignored for ImageBitmap (configure at bitmap creation). glTF textures need `flipY = false` (GLTFLoader handles it; set manually if you reuse glTF-convention textures). Compressed/Data/render target textures: false. |
| `premultiplyAlpha` | `false` | |
| `unpackAlignment` | 4 | Use 1 for tightly packed odd-width R/RGB data. |
| `mapping` | `UVMapping` | `EquirectangularReflectionMapping` for env HDRs; `CubeReflectionMapping` etc. for cubes. |
| `channel` | 0 | UV set used: 0 `uv`, 1 `uv1`, 2 `uv2`, 3 `uv3`. |
| `format`, `type`, `internalFormat` | RGBA, UnsignedByte | change before first upload only. |
| `needsUpdate` | | set true after changing image data or (WebGL) format/type; bumps `version`. |
| `source` | | `TextureSource`; shared by `clone()`d textures so one upload serves many transforms. |
| `onUpdate` | | callback after upload |
| `userData`, `name`, `uuid` | | |

Methods: `clone()`, `copy()`, `dispose()`, `updateMatrix()`, `transformUv(uv)`, `addUpdateRange(start,count)`/`clearUpdateRanges()` (partial upload for DataTexture), `toJSON()`.

After first use, texture width/height/format/type cannot change: call `dispose()` and create a new texture.

### Per-map UV channel and transforms

Each texture has its own transform; materials sample each map with that map's matrix, so different maps on one material can tile differently.

```js
tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
tex.repeat.set(4, 4);          // tiles 4x4
tex.offset.set(0.25, 0);       // UV shift
tex.center.set(0.5, 0.5);      // rotation pivot (default 0,0 = lower left)
tex.rotation = Math.PI / 4;    // radians CCW
tex.matrixAutoUpdate = true;   // default: matrix rebuilt from offset/repeat/rotation/center
// manual: tex.matrixAutoUpdate = false; tex.matrix.set(...)  (Matrix3)

aoMap.channel = 1;             // sample from geometry 'uv1'
geometry.setAttribute('uv1', geometry.attributes.uv.clone());
```

Gotcha: shared texture with different repeat per material -> `tex.clone()` (sets `needsUpdate` for you in r186; `source` is shared so GPU upload is not duplicated), or give each its own.

Animate scrolling: `tex.offset.x += dt * speed;` with `RepeatWrapping`.

### Environment textures

```js
import { HDRLoader } from 'three/addons/loaders/HDRLoader.js';
const env = await new HDRLoader().loadAsync('sky.hdr');
env.mapping = THREE.EquirectangularReflectionMapping;
scene.environment = env; scene.background = env;
```
`scene.environment` / material `envMap` equirects and cubes are PMREM-processed automatically by WebGLRenderer; for explicit control use `PMREMGenerator.fromEquirectangular(tex).texture` (call `.dispose()` on generator). Details in `loaders-assets.md`.

---

## 8. Texture subclasses

| Class | Construct | Notes |
|---|---|---|
| `CanvasTexture(canvas, ...)` | `new CanvasTexture(canvas)` | `needsUpdate` auto-true on creation; set `tex.needsUpdate = true` after each redraw. Set `colorSpace = SRGBColorSpace`. Good for text labels (sharp: draw at 2x, use mipmaps+anisotropy). |
| `VideoTexture(video, ...)` | `new VideoTexture(videoEl)` | Auto-updates each frame via `requestVideoFrameCallback` when available (otherwise per render); `generateMipmaps=false`, `LinearFilter`. Video needs `muted`/`playsInline`/user gesture to autoplay, `crossOrigin='anonymous'`. `colorSpace = SRGBColorSpace` (mandatory on WebGPURenderer). `update()` method exists for manual. |
| `DataTexture(data, w, h, format, type, ...)` | `new DataTexture(new Uint8Array(w*h*4), w, h)` | Raw typed array; `needsUpdate = true` after write. `flipY` false, no mipmaps by default. `RedFormat`/`RGFormat` + `FloatType` / `HalfFloatType` for data, `unpackAlignment=1` for odd widths. Partial updates: `addUpdateRange(start,count)`. |
| `CompressedTexture(mipmaps, w, h, format, type, ...)` | produced by `KTX2Loader`, `DDSLoader`, `KTXLoader`, `PVRLoader` | Contains GPU block-compressed mipmaps (`tex.mipmaps`); `flipY`/`generateMipmaps` read-only false. Pre-flipped at encode time. |
| `CubeTexture(images, ...)` | `CubeTextureLoader` | 6 images order +x -x +y -y +z -z; `colorSpace = SRGBColorSpace` for LDR; `flipY=false`; used for `scene.background`/`envMap`. |
| `DataArrayTexture(data, w, h, depth)` | `sampler2DArray` | `wrapR`, `layerUpdates` set + `addLayerUpdate(i)` for partial layer upload. WebGL2/WebGPU only. |
| `Data3DTexture(data, w, h, depth)` | `sampler3D` | volumes/LUTs; `wrapR`; set filters (Linear needs float-linear support for float types). |
| `DepthTexture(w, h, type, ...)` | attach to a render target: `rt.depthTexture = new DepthTexture(w,h)` | `compareFunction` for shadow-style samplers; sample for SSAO/depth effects. `CubeDepthTexture` for cube. |

```js
// canvas label
const c = document.createElement('canvas'); c.width = 512; c.height = 128;
const ctx = c.getContext('2d'); ctx.fillStyle = '#fff'; ctx.font = '64px sans-serif'; ctx.fillText('Hi', 10, 80);
const label = new THREE.CanvasTexture(c); label.colorSpace = THREE.SRGBColorSpace;

// video
const video = Object.assign(document.createElement('video'), { src: 'a.mp4', crossOrigin: 'anonymous', loop: true, muted: true, playsInline: true });
video.play();
const vtex = new THREE.VideoTexture(video); vtex.colorSpace = THREE.SRGBColorSpace;

// data texture (random noise)
const size = 256, data = new Uint8Array(size * size * 4).map(() => Math.random() * 255);
const dt = new THREE.DataTexture(data, size, size); dt.needsUpdate = true;
```

---

## 9. ShaderMaterial / RawShaderMaterial

WebGLRenderer only (for WebGPURenderer use NodeMaterial/TSL; `ShaderMaterial` is not supported there).

```js
const mat = new THREE.ShaderMaterial({
  uniforms: {
    uTime: { value: 0 },
    uColor: { value: new THREE.Color(0xff8800) },   // linear working space
    uMap: { value: tex },
  },
  defines: { USE_FOO: '', STEPS: 8 },   // -> #define USE_FOO ; #define STEPS 8 (changing needs material.needsUpdate)
  vertexShader: /* glsl */`
    varying vec2 vUv;
    void main() {
      vUv = uv;
      gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
    }`,
  fragmentShader: /* glsl */`
    uniform float uTime; uniform vec3 uColor; uniform sampler2D uMap;
    varying vec2 vUv;
    void main() {
      gl_FragColor = vec4(uColor * texture2D(uMap, vUv).rgb, 1.0);
      #include <tonemapping_fragment>
      #include <colorspace_fragment>
    }`,
  transparent: false, side: THREE.FrontSide,
});
mat.uniforms.uTime.value = t;     // just mutate .value each frame; no needsUpdate
```

Facts (verified in `WebGLProgram.js` prefix and ShaderMaterial API):
- ShaderMaterial prepends built-ins: uniforms `modelMatrix, modelViewMatrix, projectionMatrix, viewMatrix, normalMatrix, cameraPosition, isOrthographic`; attributes `position, normal, uv` (GLSL1/WebGL1 style `attribute`/`varying`, `texture2D`, `gl_FragColor` are translated in WebGL2). RawShaderMaterial gets none of this: you declare `precision`, uniforms, attributes yourself.
- Defaults `lights:false, fog:false, clipping:false, wireframe:false`. Turn on `lights: true` and merge `THREE.UniformsLib.lights` + `UniformsUtils.merge([...])` for lit custom shaders; `fog: true` + `UniformsLib.fog`; `clipping: true` for clippingPlanes.
- `glslVersion: THREE.GLSL3` to write `in/out` GLSL ES 3.00; then declare `out vec4 fragColor;` yourself, use `texture()`.
- `uniformsGroups: [UniformsGroup]` for UBOs; `uniformsNeedUpdate` forces upload when changing uniforms inside `onBeforeRender`.
- `defaultAttributeValues`: fallbacks (`color [1,1,1]`, `uv [0,0]`, `uv1 [0,0]`) when geometry lacks the attribute.
- `extensions: { clipCullDistance, multiDraw }`.
- Output of ShaderMaterial is NOT color-managed; include chunks or convert manually (`LinearTosRGB` equivalents live in the chunks). `toneMapped` has effect only if you include `tonemapping_fragment`.
- Uniform types (manual `uniform-types`): `float/int/uint/bool` -> Number/Boolean; `vec2` Vector2; `vec3` Vector3 or Color; `vec4` Vector4 or Quaternion; `mat3` Matrix3; `mat4` Matrix4; `sampler2D` Texture; `samplerCube` CubeTexture; arrays of GLSL primitives as arrays of the THREE objects or one flat number/Float32Array (an array of vec2s is `[Vector2, ...]` or `[x,y,x,y,...]`, never nested number arrays); `ivec3/bvec3` Int32Array, `ivec4/bvec4` Int32Array; `ivec2/bvec2` Float32Array/Array.
- Structs: `uniforms = { data: { value: { position: new Vector3(), direction: new Vector3(0,0,1) } } }` maps to `uniform Data data;`. Struct arrays: `value: [entry1, entry2]` maps to `uniform Data data[2];`.
- Unroll loops with `#pragma unroll_loop_start` / `#pragma unroll_loop_end` (normalized loop, variable `i`, `UNROLLED_LOOP_INDEX`).
- Clone with `material.clone()`: uniforms are cloned (new objects), shaders copied.
- Changing `vertexShader`/`fragmentShader`/`defines`/`lights` at runtime requires `material.needsUpdate = true`.

### Extending a built-in material (`onBeforeCompile`)

```js
const mat = new THREE.MeshStandardMaterial({ color: 0x44aa88 });
const uTime = { value: 0 };
mat.onBeforeCompile = (shader) => {          // shader: { uniforms, vertexShader, fragmentShader }
  shader.uniforms.uTime = uTime;
  shader.vertexShader = shader.vertexShader
    .replace('#include <common>', '#include <common>\nuniform float uTime;')
    .replace('#include <begin_vertex>', '#include <begin_vertex>\ntransformed.y += sin(position.x * 4.0 + uTime) * 0.1;');
};
mat.customProgramCacheKey = () => 'wavy-v1';   // distinct key if variants differ, else programs are shared by material type
// shadows must follow: mesh.customDepthMaterial = new THREE.MeshDepthMaterial({ depthPacking: THREE.RGBADepthPacking }) with same patch
```

- Only for WebGLRenderer. In WebGPURenderer use `positionNode`, `colorNode`, etc.
- Chunk names are in `src/renderers/shaders/ShaderChunk/`; replace by exact `#include <chunk>` string.
- Set `customProgramCacheKey` whenever the patch varies per material instance, otherwise three.js reuses one compiled program.

---

## 10. NodeMaterial family

Import from `three/webgpu` (re-exports everything in `three` plus node materials) with TSL from `three/tsl`. Works with `WebGPURenderer` (WebGPU backend and WebGL2 fallback). Classic materials are also converted automatically when used by WebGPURenderer, but custom behavior needs node materials. Full TSL reference: `threejs-tsl-webgpu` skill.

```js
import * as THREE from 'three/webgpu';
import { texture, uv, color, time, sin, positionLocal, vec3 } from 'three/tsl';

const m = new THREE.MeshStandardNodeMaterial({ roughness: 0.4 });
m.colorNode = texture(map, uv().mul(2)).mul(color(0xff8800));
m.positionNode = positionLocal.add(vec3(0, sin(time).mul(0.1), 0));
```

### Equivalence table (classic -> node)

| Classic | Node material |
|---|---|
| `MeshBasicMaterial` | `MeshBasicNodeMaterial` |
| `MeshLambertMaterial` | `MeshLambertNodeMaterial` |
| `MeshPhongMaterial` | `MeshPhongNodeMaterial` |
| `MeshToonMaterial` | `MeshToonNodeMaterial` |
| `MeshMatcapMaterial` | `MeshMatcapNodeMaterial` |
| `MeshNormalMaterial` | `MeshNormalNodeMaterial` |
| `MeshStandardMaterial` | `MeshStandardNodeMaterial` |
| `MeshPhysicalMaterial` | `MeshPhysicalNodeMaterial` (and `MeshSSSNodeMaterial` for subsurface) |
| `PointsMaterial` | `PointsNodeMaterial` (extends `SpriteNodeMaterial`) |
| `SpriteMaterial` | `SpriteNodeMaterial` |
| `LineBasicMaterial` / `LineDashedMaterial` | `LineBasicNodeMaterial` / `LineDashedNodeMaterial` |
| `Line2` `LineMaterial` (addons) | `Line2NodeMaterial` |
| `ShadowMaterial` | `ShadowNodeMaterial` |
| `ShaderMaterial` | none; use `NodeMaterial` with `fragmentNode`/`vertexNode`/`outputNode` |
| (none) | `VolumeNodeMaterial` (raymarched volumes: `steps`, `scatteringNode`, `offsetNode`) |
| (none, addon) | `WoodNodeMaterial` (`three/addons/materials/WoodNodeMaterial.js`; `fromPreset('walnut','gloss')`; genera teak, walnut, white_oak, pine, poplar, maple, red_oak, cherry, cedar, mahogany; finishes raw, matte, semigloss, gloss). In r186 source it extends `MeshPhysicalMaterial` and uses TSL internally (API page lists only an empty constructor). |

### Node slots (verified on `NodeMaterial.md`)

| Slot | Type | Replaces |
|---|---|---|
| `colorNode` | vec3/vec4 | diffuse color (`color * map`) |
| `opacityNode` | float | alpha |
| `alphaTestNode` | float | alphaTest threshold |
| `maskNode` | bool | discard mask |
| `normalNode` | vec3 | shading normal (view space) |
| `positionNode` | vec3 | local vertex position (displacement, instancing, skinning order) |
| `emissiveNode` (Standard+) | vec3 | emissive |
| `roughnessNode`, `metalnessNode` (Standard+) | float | roughness/metalness |
| `aoNode`, `envNode`, `lightsNode`, `backdropNode`, `backdropAlphaNode` | | AO, environment, light set, refraction backdrop |
| `depthNode` | float | fragment depth |
| `castShadowNode`, `castShadowPositionNode`, `receivedShadowNode`, `receivedShadowPositionNode`, `maskShadowNode` | | shadow customization |
| `mrtNode`, `contextNode` | | multi render target outputs, node context |
| `vertexNode` (vec4) / `fragmentNode` (vec4) / `outputNode` (vec4) | | take over whole stage; `outputNode` is final color before tone map/colorspace |
| `geometryNode` | function | geometry stage |
| Physical: `clearcoatNode, clearcoatRoughnessNode, clearcoatNormalNode, sheenNode, sheenRoughnessNode, transmissionNode, thicknessNode, attenuationColorNode, attenuationDistanceNode, iorNode, iridescenceNode, iridescenceIORNode, iridescenceThicknessNode, anisotropyNode, dispersionNode, specularColorNode, specularIntensityNode, retroreflectivityNode` | | and flags `useClearcoat, useSheen, useTransmission, useIridescence, useAnisotropy, useDispersion, useRetroreflection` (set automatically from values) |
| SSS: `thicknessColorNode, thicknessDistortionNode, thicknessAmbientNode, thicknessAttenuationNode, thicknessPowerNode, thicknessScaleNode` | | `MeshSSSNodeMaterial` |
| Sprite/Points: `positionNode (vec2)`, `rotationNode`, `scaleNode`, `sizeNode`, `sizeAttenuation` | | |

Differences vs classic worth knowing:
- Constructor params accept classic property names too (`color`, `map`, `roughness`...) and node materials use them when the matching `*Node` slot is unset.
- `material.toneMapped` ignored; tone mapping applies to all materials and is configured via renderer/`renderOutput`.
- `onBeforeCompile` / `ShaderMaterial` / `customProgramCacheKey` are WebGL-only concepts; node graph changes rebuild automatically (NodeMaterialObserver tracks changes). Mutate uniforms via `uniform(...).value`.
- `NodeMaterial.fog`, `lights` booleans control fog/lighting participation.
- Node materials loaded/serialized via `NodeMaterialLoader`.

---

## 11. `needsUpdate` triggers and `dispose`

`material.needsUpdate = true` forces program re-selection/recompile on next use. Required after changing:
- `flatShading`
- adding or removing a texture slot (null <-> texture). Swapping one texture for another is free. Prefer a 1x1 white texture over removing a map.
- `transparent` in some cases, `side` between Double and others for transparent objects, `vertexColors`, `fog`, `alphaTest` crossing 0, `alphaHash`, `defines`, `lights`, shader strings, `envMap` null <-> texture, `normalMapType`.
- Physical feature toggles from 0 to non-zero (e.g. `transmission`, `clearcoat`, `sheen`, `iridescence`, `anisotropy`) change the compiled program; flip once up-front rather than at runtime to avoid a hitch. Changing only the numeric value between non-zero values is free.
- Not needed: `color`, `opacity`, `roughness`, `metalness`, `emissive`, `*Intensity`, `uniforms[x].value`, `map` replacement, `map.offset/repeat/rotation` (texture matrix auto-updates).

Texture: `texture.needsUpdate = true` after mutating `image` / `data` / canvas content / new image; not after changing transforms.

Dispose (GPU resources are not garbage collected):
- `material.dispose()` frees program refs/uniform buffers only; it does NOT dispose textures. Dispose each texture (`tex.dispose()`) and geometry (`geometry.dispose()`) yourself. Dispose fires the `dispose` event; the renderer subscribes.
- Textures from `GLTFLoader` etc.: traverse the scene and dispose every material's map properties:
```js
scene.traverse((o) => {
  if (!o.isMesh) return;
  o.geometry.dispose();
  const mats = Array.isArray(o.material) ? o.material : [o.material];
  for (const m of mats) {
    for (const k in m) if (m[k] && m[k].isTexture) m[k].dispose();
    m.dispose();
  }
});
```
- `renderer.info.memory` / `renderer.info.programs` show leaks.
- A disposed texture/material is re-uploaded transparently if used again (but wasteful).
- `PMREM`-generated env: `pmrem.dispose()` and dispose the result when swapping environments.
- Material arrays: `Mesh.material` can be an array indexed by geometry `groups[i].materialIndex`.

---

## See also

API pages (`references/api/`): `Material.md`, `MeshBasicMaterial.md`, `MeshLambertMaterial.md`, `MeshPhongMaterial.md`, `MeshToonMaterial.md`, `MeshStandardMaterial.md`, `MeshPhysicalMaterial.md`, `MeshMatcapMaterial.md`, `MeshNormalMaterial.md`, `MeshDepthMaterial.md`, `MeshDistanceMaterial.md`, `ShadowMaterial.md`, `ShaderMaterial.md`, `RawShaderMaterial.md`, `PointsMaterial.md`, `SpriteMaterial.md`, `LineBasicMaterial.md`, `LineDashedMaterial.md`, `NodeMaterial.md`, `MeshStandardNodeMaterial.md`, `MeshPhysicalNodeMaterial.md`, `MeshBasicNodeMaterial.md`, `MeshSSSNodeMaterial.md`, `SpriteNodeMaterial.md`, `PointsNodeMaterial.md`, `Line2NodeMaterial.md`, `VolumeNodeMaterial.md`, `WoodNodeMaterial.md`, `ShadowNodeMaterial.md`, `Texture.md`, `VideoTexture.md`, `CanvasTexture.md`, `DataTexture.md`, `CompressedTexture.md`, `CubeTexture.md`, `DataArrayTexture.md`, `Data3DTexture.md`, `DepthTexture.md`, `Color.md`, `PMREMGenerator.md`, `UniformsGroup.md`, `Scene.md` (environment, environmentIntensity, environmentRotation).

Sibling references: `loaders-assets.md` (TextureLoader, KTX2, HDR, disposal of loaded assets).

Official: https://threejs.org/docs/#Material, https://threejs.org/docs/#MeshStandardMaterial, https://threejs.org/docs/#MeshPhysicalMaterial, https://threejs.org/docs/#ShaderMaterial, https://threejs.org/docs/#NodeMaterial, https://threejs.org/docs/#Texture, https://threejs.org/manual/#en/materials, https://threejs.org/manual/#en/transparency, https://threejs.org/manual/#en/color-management, https://threejs.org/manual/#en/uniform-types, https://threejs.org/manual/#en/material-table
