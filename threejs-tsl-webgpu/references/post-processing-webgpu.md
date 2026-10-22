# Post-Processing with WebGPURenderer (three.js r186, node-based)

## When to read this

Read when building or debugging a post-processing chain on `WebGPURenderer`: scene pass, MRT (normals/velocity/emissive), tone mapping order, AA, AO/SSR/SSGI, bloom, DOF, motion blur, grading, stereo, OIT, VXGI, custom effects. Not for `WebGLRenderer` + `EffectComposer` (different, pass-based system).

## Table of contents

1. Mental model and naming (RenderPipeline vs deprecated PostProcessing)
2. RenderPipeline API
3. `pass()` and PassNode API
4. MRT: `mrt()`, builtins, packing, material-level MRT
5. Color pipeline: `renderOutput`, tone mapping, `outputColorTransform`
6. Effect catalog (import, signature, params, cost, gotchas)
7. Composing and custom effects (TSL math, masks, layers, Fn, rtt)
8. Temporal effects, resolution scaling, upscaling
9. Recommended stacks (cinematic, cheap/mobile) with rationale
10. Gotchas checklist
11. Doc gaps found

Conventions: `import * as THREE from 'three/webgpu'`, core TSL from `'three/tsl'`, effects from `'three/addons/tsl/display/<Name>.js'`.

---

## 1. Mental model and naming

- Post-processing is a node graph. `pass(scene, camera)` renders the scene to an internal render target (HalfFloat by default); effect functions (`bloom`, `ao`, `fxaa`, ...) take nodes and return nodes; the final node is assigned to `renderPipeline.outputNode`, which is drawn with a fullscreen quad.
- Effects are combined into as few GPU passes as possible; many effects (`dotScreen`, `rgbShift`, `film`, `lut3D`) are just inline shader code in the final quad. Heavier ones (`bloom`, `ao`, `ssr`, `dof`, `gaussianBlur`, `smaa`, `traa`) own internal render targets and render in `updateBefore` once per frame.
- **Naming (r186):** `THREE.RenderPipeline` is the class. `THREE.PostProcessing` is **deprecated since r183** (wrapper, will be removed). The official TSL examples and some older docs/snippets (`PassNode.md` code example still says `postProcessing = new RenderPipeline(...)`) mix names. Always write `new THREE.RenderPipeline( renderer )`.
- `WebGPURenderer` only (works with the WebGL2 fallback backend of `WebGPURenderer` too, except where noted: VXGI needs the WebGPU backend). Replaces `EffectComposer`.
- There is also `THREE.DirectRenderPipeline` (section 2).

Minimal:

```js
import * as THREE from 'three/webgpu';
import { pass } from 'three/tsl';
import { bloom } from 'three/addons/tsl/display/BloomNode.js';

const renderer = new THREE.WebGPURenderer();
await renderer.init();                       // or use setAnimationLoop (it awaits init)
renderer.toneMapping = THREE.ACESFilmicToneMapping;

const renderPipeline = new THREE.RenderPipeline( renderer );
const scenePass = pass( scene, camera );
const color = scenePass.getTextureNode( 'output' );
renderPipeline.outputNode = color.add( bloom( color ) );

renderer.setAnimationLoop( () => renderPipeline.render() );   // NOT renderer.render(scene, camera)
```

---

## 2. RenderPipeline API

Source: `src/renderers/common/RenderPipeline.js`.

| Member | Notes |
|---|---|
| `new RenderPipeline( renderer, outputNode? )` | one instance per renderer |
| `.outputNode` | final `vec4` node (usually last effect) |
| `.outputColorTransform` | default `true`: pipeline wraps `outputNode` in `renderOutput( outputNode, renderer.toneMapping, renderer.outputColorSpace )`. Set `false` to place `renderOutput()` manually (needed for FXAA, LUT, Sobel, CA, ...). |
| `.needsUpdate` | set `true` after **replacing `outputNode`** (or otherwise changing graph topology) at runtime. Internal `_update()` also sets it when `renderer.toneMapping` / `renderer.outputColorSpace` change. Changing uniform `.value`s needs nothing. |
| `.render()` | call in the animation loop instead of `renderer.render()` |
| `.renderAsync()` | **Deprecated (r181).** Use `render()` plus `await renderer.init()` |
| `.dispose()` | frees the quad material; dispose effect nodes (`bloomPass.dispose()`, `aoPass.dispose()`) yourself when swapping them |

- Tone mapping and exposure are read from the **renderer** (`renderer.toneMapping`, `renderer.toneMappingExposure`), not from the pipeline. With a pipeline, materials are not tone-mapped in their own shader; the transform is applied once at the end (or at `renderOutput`).
- Toggle patterns used in examples:

```js
renderPipeline.outputNode = enabled ? fxaaPass : outputPass;
renderPipeline.needsUpdate = true;
```

- Debug aid in official examples: `node.toInspector( 'Label', optionalFn )` (needs `renderer.inspector = new Inspector()` from `three/addons/inspector/Inspector.js`). Not required for production.

### DirectRenderPipeline

`new THREE.DirectRenderPipeline( renderer )`, `renderPipeline.render( scene, camera )`, `.outputNode = vec4( saturation( output.rgb, k ), output.a )` (example `webgpu_postprocessing_direct`). Applies output processing directly in material shaders: no intermediate framebuffer, no scene pass, so it is cheap, but only per-material color math (no screen-space sampling) and it changes blending; **not compatible with materials that sample the framebuffer (transmission)**. Use it for a cheap color-grade-only path (mobile).

---

## 3. `pass()` and PassNode

```js
import { pass, depthPass, passTexture } from 'three/tsl';
const scenePass = pass( scene, camera, options );    // PassNode (scope 'color')
const dPass     = depthPass( scene, camera, options ); // scope 'depth' (depth-only render)
```

`options` go to the internal `RenderTarget` (default `{ type: HalfFloatType }` plus yours): `type`, `minFilter`, `magFilter`, `depthBuffer` (false = no depth), `depthTexture` (share/reuse a depth texture, see deferred example), `samples` (MSAA; default = `renderer.samples`), and the clear flags `autoClear`, `autoClearColor`, `autoClearDepth`, `autoClearStencil` (all default `true`).

A PassNode is itself a node (its color output); `scenePass.rgb`, `.a`, `.mul()`, `.add()` etc. work directly. `passTexture( passNode, texture )` wraps an arbitrary texture as a pass-output node.

### Outputs

| Method | Returns | Notes |
|---|---|---|
| `getTextureNode( name = 'output' )` | `TextureNode` | `'output'`, `'depth'`, or any MRT key. Chain `.sample( uv )` for custom UV. |
| `getTexture( name )` | `Texture` | raw texture, e.g. to set `.type = THREE.UnsignedByteType` on MRT attachments |
| `getTextureNode( 'depth' )` | raw (non-linear, perspective) depth | what `ao`, `ssr`, `ssgi`, `traa`, `taau`, `sss`, `godrays`, `denoise` expect as `depthNode` |
| `getViewZNode( name='depth' )` | view-space Z (negative in front of camera) | what `dof()` expects. Built via `perspectiveDepthToViewZ` -> **perspective cameras** only |
| `getLinearDepthNode( name='depth' )` | linear depth 0..1 (`viewZToOrthographicDepth`) | for visualization / custom depth effects |
| `getPreviousTextureNode( name='output' )` | last frame's texture node | free frame history (see `webgpu_postprocessing_difference`) |
| `getPreviousTexture( name )`, `toggleTexture( name )` | | manual ping-pong |
| `getMRT()` | `MRTNode` | |

`getDepthNode()` appears in the TSL Guide `54-pass.md` but is **not in the PassNode API or source r186**; use `getTextureNode( 'depth' )`. Likewise there is no `getTextureDepthNode`.

### Configuration

| Method / property | Notes |
|---|---|
| `setMRT( mrtNode )` -> PassNode | call before first render / before `getTextureNode` consumers compile |
| `setResolutionScale( s )` | pass renders at `s * renderer size` (honors pixel ratio). `setResolution`/`getResolution` **deprecated r181** |
| `setSize( w, h )`, `setViewport(...)`, `setScissor(...)` | `null` = back to auto |
| `setLayers( layers )` / `getLayers()` | render only objects on given `THREE.Layers`; default is the camera's layers (layer 0 style). Use to split opaque/transparent/mask passes (example `webgpu_deferred`). |
| `transparent` (default `false`), `opaque` (default `true`) | set `pass.transparent = false` for a pre-pass that must ignore transparents (AO pre-pass); `pass.opaque = false` for a transparent-only pass |
| `overrideMaterial` | render the whole scene with one material (normals/depth/id passes) |
| `contextNode` | node `ContextNode` applied to the pass, e.g. `scenePass.contextNode = builtinAOContext( aoTex.sample( screenUV ).r )` |
| `name` | for debugging |
| `compileAsync( renderer )` | precompile after `setMRT`/`getTextureNode` are done |
| `dispose()` | |

Multiple passes of the same scene are legal and common (pre-pass with normals+velocity, then beauty pass). Each re-renders the scene: cost = full scene draw.

---

## 4. MRT

MRT = several color attachments in one scene render. Needed for: normals (AO/SSR/SSGI), velocity (TRAA/TAAU/motion blur/temporal denoise), emissive (selective bloom), diffuse/metalness/roughness (SSR, SSGI composite), custom masks.

```js
import { pass, mrt, output, normalView, velocity, emissive, diffuseColor } from 'three/tsl';

scenePass.setMRT( mrt( {
  output: output,           // the normal beauty output; name 'output' is the default attachment
  normal: normalView,
  velocity: velocity,
} ) );
const n = scenePass.getTextureNode( 'normal' );
```

Rules:
- Keys are arbitrary names, except `output` (beauty) and `depth` (free: returned by `getTextureNode('depth')` whenever requested, never declare it).
- An MRT key that is never consumed (`getTextureNode`/`getTexture` never called) is skipped by the shader (`MRTNode.setup` ignores unused outputs).
- All attachments default to **RGBA16F**. Downgrade where precision is irrelevant:

```js
scenePass.getTexture( 'normal' ).type = THREE.UnsignedByteType;       // RGBA8, half the bandwidth
scenePass.getTexture( 'diffuseColor' ).type = THREE.UnsignedByteType;
```

  Do not downgrade `velocity` (needs float) or HDR `emissive`/`output`. Packing normals to RGBA8 requires `packNormalToRGB`.
- Builtins seen in official examples (all exported from `three/tsl`): `output`, `normalView`, `velocity`, `emissive`, `diffuseColor`, `materialMetalness`, `materialRoughness`, `metalness`, `roughness`, `positionView`, `positionWorld`, `normalWorld`, `packNormalToRGB`, `unpackRGBToNormal`.
- `mrt` object API: `.setBlendMode( name, new THREE.BlendMode( THREE.NormalBlending ) )` (emissive needs normal blending so alpha-composited transparents do not additively corrupt it; only `output` defaults to material blending), `.getBlendMode(name)`, `.setClearColor( name, color, alpha )`, `.has( name )`, `.get( name )`, `.merge( otherMrt )`.
- `output.a` carries alpha; to keep alpha in a custom channel use `vec4( emissive, output.a )`.
- Packing extra scalars: put roughness in normal's alpha (`vec4( packNormalToRGB( normalView ).rgb, materialRoughness )`), metalness in `diffuseColor.a` (`vec4( diffuseColor.rgb, materialMetalness )`). Avoids a `metalrough` attachment.
- **Unpacking** with `sample()`: you cannot just pass a packed texture to an effect; wrap it so effects see decoded normals:

```js
import { sample, packNormalToRGB, unpackRGBToNormal } from 'three/tsl';
const sceneNormal = sample( ( uv ) => unpackRGBToNormal( scenePassNormal.sample( uv ) ) );
```

  Use `sceneNormal` for `ao`, `ssr`, `ssgi`. Use the raw `scenePassNormal` for `temporalReproject` (it reads the packed attachment, see SSR denoise example).
- **Material-level MRT** (per-object value into a shared attachment): `material.mrtNode = mrt( { bloomIntensity: uniform( 1 ) } )`; the pass's own `mrt` must declare the same key with a default (`bloomIntensity: float( 0 )`) for objects without the material override. Read back with `material.mrtNode.get( 'bloomIntensity' ).value`.
- OIT passes: custom MRT applies to the opaque default pass only.
- Renderer-level: `renderer.setMRT( mrtNode )` / `getMRT()` exist for manual render-target work; with `pass()` use `passNode.setMRT`.

### Reading velocity

`velocity` (TSL builtin, `VelocityNode`) stores per-pixel screen-space motion from previous/current model+camera matrices (updated per object after render). Required MRT input for `traa`, `taau`, `motionBlur`, `temporalReproject`, `ssr().setHistory(...)`. 

---

## 5. Color pipeline

```
scene pass (linear, HDR, half float)
  -> [linear-space effects: AO, SSR add, SSGI, bloom add, DOF, motion blur, TRAA, godrays, fog]
  -> renderOutput():  tone mapping (renderer.toneMapping + exposure) -> output color space (sRGB)
  -> [display-space effects: FXAA, LUT, Sobel, chromatic aberration, film grain/vignette (taste)]
  -> screen
```

Default (`outputColorTransform = true`): the pipeline appends `renderOutput` after your `outputNode`. Everything in your graph is then linear HDR: correct for bloom, DOF, SSR, AO, TRAA, SMAA.

Manual:

```js
import { pass, renderOutput } from 'three/tsl';
renderPipeline.outputColorTransform = false;
const out = renderOutput( scenePass );            // or scenePass.renderOutput() (method chaining exists)
renderPipeline.outputNode = fxaa( out );
```

`renderOutput( color, toneMapping = null, outputColorSpace = null )` -> `RenderOutputNode`; `null` = use renderer values. Pass explicit `THREE.NoToneMapping` / `THREE.ACESFilmicToneMapping` etc. to override. `.setToneMapping( v )` exists on the node.

Which effects need what:

| Needs sRGB / display-referred input (after `renderOutput`) | Needs linear/HDR input (before) |
|---|---|
| `fxaa` (doc: "requires sRGB input"), `sobel`, `lut3D` (LUTs are authored for display-referred), `chromaticAberration` (example), `retro/CRT` style filters | `smaa` (doc: "applied before converting to sRGB"), `bloom` (HDR threshold), `dof`, `ssr`, `ao`, `ssgi`, `traa`, `taau`, `motionBlur`, `godrays`, `fsr1` (works on color; use anti-aliased source) |

Gotchas:
- If you forget `outputColorTransform = false` and also call `renderOutput`, tone mapping applies twice (washed out).
- A `vec4` custom `outputNode` you build from `.rgb` loses alpha; rebuild `vec4( rgb, a )`.
- Bloom after tone mapping loses HDR energy (only values <= 1 bloom). Bloom with `renderer.toneMapping = ReinhardToneMapping` + default transform is the standard (example `webgpu_postprocessing_bloom`).
- `selective bloom` example sets `outputColorTransform = false` and ends with `.renderOutput()` on the sum; equivalent to default but explicit.
- Exposure animation: `renderer.toneMappingExposure = x`. Examples bind to GUI directly; no `needsUpdate` needed.
- Tone mapping constants: `NoToneMapping, LinearToneMapping, ReinhardToneMapping, CineonToneMapping, ACESFilmicToneMapping, AgXToneMapping (6), NeutralToneMapping (7), CustomToneMapping`. Core TSL also offers `toneMapping( mapping, exposure, color )` / `.toneMapping()` chain (ToneMappingNode) for a manual tone map independent of the renderer value.
- `scene.background`: it is rendered inside the pass, in the beauty buffer. Anything that blurs/blooms/thresholds the beauty (bloom, DOF, godrays, SSR color, AfterImage) also processes the background. Bright HDR backgrounds will bloom; use emissive-only bloom (section 6.1) to avoid. Transparent clear (`alpha`) works through `pass().a` (see masking example: `pass( maskScene, camera ).a`).

---

## 6. Effect catalog

Cost scale: S = a few texture taps in the final quad; M = one or two extra fullscreen passes; L = multiple passes / many taps; XL = scene re-render or heavy raymarch.

Common conventions:
- Most effects call `convertToTexture( node )` internally, so you can feed a `PassNode`, a `TextureNode`, or any node expression (it is rendered to a temp RTT, extra cost + resolution coupling).
- Parameters listed as `UniformNode` are tweakable at runtime: `effect.strength.value = 2`. Parameters marked "compile-time" rebuild shaders when assigned.
- Effect nodes with an internal render target expose `getTextureNode()` (result as texture node) and `setSize( w, h )` (called automatically on resize), `dispose()`.
- Most are addons: `import { x } from 'three/addons/tsl/display/XNode.js'`.

### 6.1 Bloom (`BloomNode.js`) M

```js
import { bloom } from 'three/addons/tsl/display/BloomNode.js';
const b = bloom( inputNode, strength = 1, radius = 0, threshold = 0 );
renderPipeline.outputNode = scenePassColor.add( b );   // effect returns ONLY the glow; you add it
```

- Props (uniforms): `strength`, `radius` (0..1), `threshold`, `smoothWidth`. Also `bloomTintColors: Vector3[]` (per-mip tint), `highPassFn` (replace the high-pass; used by the anamorphic example), `setResolutionScale( s )`.
- Whole-image bloom (above) works with Reinhard/ACES; tune `threshold` ~0.8-1 in HDR.
- **Selective bloom via emissive MRT** (`webgpu_postprocessing_bloom_emissive`):

```js
const scenePass = pass( scene, camera );
const m = mrt( { output, emissive: vec4( emissive, output.a ) } );
m.setBlendMode( 'emissive', new THREE.BlendMode( THREE.NormalBlending ) );
scenePass.setMRT( m );
scenePass.getTexture( 'emissive' ).type = THREE.UnsignedByteType;   // optional bandwidth cut (clamps emissive to 0..1)
const outputPass = scenePass.getTextureNode();
const bloomPass  = bloom( scenePass.getTextureNode( 'emissive' ), 2.5, 0.5 );
renderPipeline.outputNode = outputPass.add( bloomPass );
```

  Only `material.emissive * emissiveIntensity` glows. Use RGBA8 only if emissive <= 1; otherwise keep half-float.
- **Selective via per-material mask** (`webgpu_postprocessing_bloom_selective`): `material.mrtNode = mrt( { bloomIntensity: uniform( 1 ) } )`, pass default `bloomIntensity: float( 0 )`, then `bloom( outputPass.mul( bloomIntensityPass ) )`, `outputColorTransform = false`, `outputNode = outputPass.add( bloomPass ).renderOutput()`.
- **Layer-based selective (no MRT):** second pass restricted by layers, then add: see section 7.3.
- Anamorphic: custom `highPassFn` with `Fn( ({ input, threshold, smoothWidth }) => ... )` and a horizontal `Loop` blur over an `rtt()` bright-pass, `bloomPass.setResolutionScale( 0.25 )` (example `webgpu_postprocessing_anamorphic`).

### 6.2 AO: GTAO `ao()` and SSAO `ssao()` M

```js
import { ao }   from 'three/addons/tsl/display/GTAONode.js';
import { ssao } from 'three/addons/tsl/display/SSAONode.js';
const aoPass = ao( depthNode, normalNode, camera );     // normalNode may be omitted => reconstructed from depth
const aoPass2 = ssao( depthNode, normalNode, camera );
```

- GTAO props: `radius` (0.25), `thickness` (1), `scale` (1), `samples` (16, **assignment recompiles**), `resolutionScale` (default 1; `0.5` is fine), `useTemporalFiltering` (needs TRAA downstream, adds ghosting; if false you may need `denoise()`). `distanceExponent`, `distanceFallOff` **deprecated r186**.
- SSAO props: `radius`, `samples`, `intensity`, `bias`, `blurEnabled`, `blurSharpness`, `resolutionScale`. Built-in depth-aware blur: self-denoised, cheaper, no TRAA needed. Pairs well with MSAA.
- `aoPass.getTextureNode()`; AO is in `.r`.
- **Apply to lighting, not as a multiply on the final image** (official approach, `webgpu_postprocessing_ao`):

```js
const prePass = pass( scene, camera );
prePass.transparent = false;                       // transparents must not write AO depth/normal
prePass.setMRT( mrt( { output: packNormalToRGB( normalView ), velocity } ) );
prePass.getTexture( 'output' ).type = THREE.UnsignedByteType;
const prePassNormal = sample( ( uv ) => unpackRGBToNormal( prePass.getTextureNode().sample( uv ) ) );
const prePassDepth  = prePass.getTextureNode( 'depth' );

const aoPass = ao( prePassDepth, prePassNormal, camera );
const scenePass = pass( scene, camera );
scenePass.contextNode = builtinAOContext( aoPass.getTextureNode().sample( screenUV ).r );   // AO applied to indirect/ambient light
renderPipeline.outputNode = traa( scenePass, prePassDepth, prePass.getTextureNode( 'velocity' ), camera );
```

  `builtinAOContext( aoNode )` multiplies only indirect lighting, so direct light is not darkened. Cheaper variant: composite `scenePass.mul( aoTex )` (darkens everything, incl. direct).
- **GTAO + denoise** (non-temporal): `import { denoise } from '.../DenoiseNode.js'; const d = denoise( aoPass.getTextureNode(), depthNode, normalNode, camera )`. Props `depthPhi`, `lumaPhi`, `normalPhi`, `radius`, `index`. Takes raw AO texture (not beauty), depth node, normal node. Expensive; prefer `ssao` blur or GTAO + TRAA.
- Stage order: AO must see depth+normals of opaque geometry only.

### 6.3 SSR `ssr()` L (stochastic mode: XL + denoise)

```js
import { ssr } from 'three/addons/tsl/display/SSRNode.js';
const r = ssr( colorNode, depthNode, normalNode, options );
renderPipeline.outputNode = scenePassColor.add( r.rgb );   // SSR outputs premultiplied color: ADD, do not mix
```

`options` (SSRNodeOptions): `stochastic=false`, `metalnessNode`, `roughnessNode`, `reflectNonMetals=false` (non-stochastic only), `environmentNode` (equirect HDR `Texture` with CPU `image.data`, e.g. from HDRLoader; **not** a PMREM cubemap), `envImportanceSampling=false`, `diffuseNode`, `binaryRefine=false`, `camera` (inferred from color pass).

Uniforms: `quality` (0..1, 0.5 typical, keep low), `maxDistance`, `thickness`, `intensity`, `mirrorBias`, `maxLuminance`, `environmentIntensity` (default pi), `resolutionScale`. Compile-time (assignment recompiles): `binaryRefine`, `blurQuality` (1..3), `reflectNonMetals`, `stepExponent`, `screenEdgeFadeBlack`.

First-gen (basic) setup, from `webgpu_postprocessing_ssr`:

```js
scenePass.setMRT( mrt( { output, normal: packNormalToRGB( normalView ), metalrough: vec2( metalness, roughness ) } ) );
scenePass.getTexture( 'normal' ).type = scenePass.getTexture( 'metalrough' ).type = THREE.UnsignedByteType;
const mr = scenePass.getTextureNode( 'metalrough' );
const ssrPass = ssr( scenePass.getTextureNode( 'output' ), scenePass.getTextureNode( 'depth' ), sceneNormal,
                     { metalnessNode: mr.r, roughnessNode: mr.g } );
renderPipeline.outputNode = smaa( scenePassColor.add( ssrPass.rgb ) );
```

Second-gen (stochastic GGX + temporal + denoise), from `webgpu_postprocessing_ssr_denoise`: MRT `output`, `diffuseColor: vec4(diffuseColor.rgb, materialMetalness)`, `normal: vec4(packNormalToRGB(normalView).rgb, materialRoughness)`, `velocity`; then

```js
ssrNode = ssr( color, depth, sceneNormal, { stochastic: true, diffuseNode, metalnessNode: diffuse.a, roughnessNode: normal.a, environmentNode: hdr } );
temporalReprojectNode = temporalReproject( ssrNode, depth, normalTex, velocityTex, camera, { mode: 'specular', accumulate: false } );
denoiseNode = recurrentDenoise( temporalReprojectNode, camera, { depth, normal: normalTex, raw: ssrNode, metalRoughness, mode: 'specular', accumulate: true } );
denoiseNode.alphaSource = 'raylength';             // 'raylength' | 'ao' | 'none'
ssrNode.setHistory( denoiseNode, velocityTex );    // multi-bounce reflections
temporalReprojectNode.setHistoryTexture( denoiseNode );
final = scenePassColor.rgb.add( denoiseNode.rgb );
```

  Feedback loop: history texture feeds the same chain; do not forget both `setHistory` / `setHistoryTexture`.
- Needs `diffuseNode` for metals (f0 = albedo); do not pre-multiply by `(1 - metalness)` (comment in example).
- Gotchas: SSR only reflects what is on screen; `screenEdgeFadeBlack` for indoor; transparents are not in depth.

### 6.4 SSGI `ssgi()` XL

```js
import { ssgi } from 'three/addons/tsl/display/SSGINode.js';
const gi = ssgi( beautyNode, depthNode, normalNode, camera );     // PerspectiveCamera
gi.sliceCount.value = 2; gi.stepCount.value = 8;                  // samples/pixel = slice * step * 2
const ao = gi.getAONode(), g = gi.getGINode();
const composite = vec4( add( scenePassColor.rgb.mul( ao ), scenePassDiffuse.rgb.mul( g.rgb ) ), scenePassColor.a );
renderPipeline.outputNode = traa( composite, depth, velocity, camera );
```

- MRT: `output`, `diffuseColor` (RGBA8), `normal: packNormalToRGB(normalView)` (RGBA8), `velocity`. Composite formula above is the official one: AO multiplies beauty, GI is multiplied by diffuse albedo.
- Uniforms: `sliceCount` (1..4), `stepCount` (1..32), `radius` (1..25), `thickness`, `giIntensity` (0..100), `aoIntensity` (0..4), `expFactor` (1..3), `backfaceLighting`, `useLinearThickness`, `useScreenSpaceSampling`. `useTemporalFiltering` (needs TRAA; otherwise needs manual denoise).
- Newer denoise route: `temporalReproject` (`mode: 'diffuse'`) + `recurrentDenoise` (`mode: 'diffuse'`, `alphaSource: 'ao'`).
- Disable MSAA on the pass when using TRAA (`scenePass.options.samples = 0`? see 8.1).

### 6.5 Screen-space shadows `sss()` M

`import { sss } from '.../SSSNode.js'; sss( depthNode, camera, directionalLight )`; props `maxDistance` (0.1), `quality` (0.5), `thickness`, `shadowIntensity`, `resolutionScale`, `useTemporalFiltering`. Contact shadows; complement shadow maps. Official pre-pass renders only `velocity` as output (`mrt({ output: velocity })`), then composites with scene pass and `traa`. Soften with box/gaussian/hash blur. Single main `DirectionalLight` only; max shadow length ~1 m (cost); only on-screen casters. `builtinShadowContext` is used in the example.

### 6.6 Depth of field

**`dof()` (physical bokeh, `DepthOfFieldNode.js`) L**

```js
import { dof } from 'three/addons/tsl/display/DepthOfFieldNode.js';
dof( colorTextureNode, scenePass.getViewZNode(), focusDistance = 1, focalLength = 1, bokehScale = 1 );
```
`focusDistance`: world units along view direction; `focalLength`: world-unit range before fully blurred; `bokehScale`: unitless. Pass `uniform( x )` for live control; do not pass plain numbers if you want to animate (properties `focusDistanceNode`, `focalLengthNode`, `bokehScaleNode`). Linear space, before tone mapping.

**Cheap DOF** (`webgpu_postprocessing_dof_basic`): blur + view-Z mask, then manual `renderOutput` + FXAA:

```js
renderPipeline.outputColorTransform = false;
const blurred = boxBlur( color, { size: blurSize, separation: blurSpread } );   // boxBlur.js
const blur = smoothstep( minDistance, maxDistance, scenePass.getViewZNode().sub( focusPointView.z ).abs() );
renderPipeline.outputNode = fxaa( renderOutput( mix( color, blurred, blur ) ) );
```
(`focusPointView` is an example-local uniform node.)

### 6.7 Anti-aliasing

| Method | Import | Space | Cost | Notes |
|---|---|---|---|---|
| MSAA | `new WebGPURenderer({ antialias: true })` / `pass(..., { samples: 4 })` | linear | M | renderer `samples` is the default for passes; disable for TRAA/TAAU |
| FXAA `fxaa( node )` | `FXAANode.js` | **sRGB** (after `renderOutput`) | S | blurry, fastest post AA |
| SMAA `smaa( node )` | `SMAANode.js` | **linear/before** sRGB | M | SMAA 1x Medium with color edge detection; better than FXAA; no velocity needed |
| TRAA `traa( beauty, depth, velocity, camera )` | `TRAANode.js` | linear | M | temporal, jitters camera (`setViewOffset`/`clearViewOffset` managed internally), needs velocity MRT; **MSAA must be off** |
| TAAU `taau( beauty, depth, velocity, camera )` | `TAAUNode.js` | linear | M | TRAA that also upscales: inputs at lower res than output (see 8.3); `getTextureNode()` |
| SSAA `ssaaPass( scene, camera )` | `SSAAPassNode.js` | linear | XL | **replaces `pass()`**; `sampleLevel` n => 2^n scene renders (default 4 = 16); `unbiased`, `sampleWeight` |

TRAA props: `depthThreshold` (0.0005), `edgeDepthDiff` (0.001), `maxVelocityLength` (128), `useSubpixelCorrection` (less blur under motion, may cause square pattern; AO example sets `false`). TAAU props: `currentFrameWeight` (0.025), same thresholds.

```js
scenePass.setMRT( mrt( { output, velocity } ) );
const t = traa( scenePass.getTextureNode( 'output' ), scenePass.getTextureNode( 'depth' ), scenePass.getTextureNode( 'velocity' ), camera );
renderPipeline.outputNode = t;       // tone mapping appended after TRAA (default transform)
```

FXAA chain: `outputColorTransform = false; outputNode = fxaa( renderOutput( scenePass ) )`.

### 6.8 Upscaling

- `fsr1( node, sharpness = 0.2, denoise = false )` (`FSR1Node.js`): spatial upscaler (EASU + RCAS). Render the pass at lower scale (`scenePass.setResolutionScale( 0.5 )`) and feed `fsr1( scenePass )`. Source should be anti-aliased; only worth it if fragment-bound. `sharpness`: 0 = max, 2 = none.
- `taau` (temporal): `scenePass.setResolutionScale( s )` + velocity MRT + `taau(...)`, then optional `sharpen( taauNode.getTextureNode(), sharpness )`.
- `sharpen( node, sharpness = 0.2, denoise = false )` (`SharpenNode.js`, RCAS): 0 = maximum, 2 = none. (The TSL Guide page says default 0.5; the API doc says 0.2.)

### 6.9 Film / grading / stylization (all S)

| Effect | Import / signature | Notes |
|---|---|---|
| Film grain | `film( input, intensity = null, uvNode = null )` (`FilmNode.js`) | use animated `uvNode` / time is built in via `time` |
| 3D LUT | `lut3D( input, lutNode, size, intensity )` (`Lut3DNode.js`) | `lutNode = texture3D( data3dTexture )`, `size = tex.image.width`; feed after `renderOutput`. `intensity` uniform 0..1 |
| Vignette | `vignette( color, intensity = 0.4, smoothness = 0.5, coord = uv() )` (`CRT.js`) | or hand-rolled `screenUV.distance( 0.5 )...` |
| CRT helpers | `barrelUV`, `barrelMask`, `colorBleeding`, `scanlines` (`CRT.js`); `circle` (`Shape.js`) | |
| Grading | `bleach( color, opacity )` (`BleachBypass.js`), `sepia( color )` (`Sepia.js`); core TSL: `saturation`, `vibrance`, `hue`, `grayscale`, `luminance`, `cdl`, `posterize` | |
| Dot screen | `dotScreen( input, angle = 1.57, scale = 1 )` | |
| RGB shift | `rgbShift( input, amount = 0.005, angle = 0 )` | |
| Chromatic aberration | `chromaticAberration( input, strength = 1.0, center = null, scale = 1.1 )` (`ChromaticAberrationNode.js`) | radial lens fringing; do after `renderOutput` |
| Sobel | `sobel( renderOutput( scenePass ) )` | edges on display-referred color |
| Bayer dither | `bayerDither( color, steps = 32 )`, `bayer16( uv )` from `three/addons/tsl/math/Bayer.js` | |
| Pixelation | `pixelationPass( scene, camera, pixelSize = 6, normalEdgeStrength = 0.3, depthEdgeStrength = 0.4 )` | replaces `pass()`; example uses an orthographic camera; `pixelSize` is a node (pass `uniform()` to animate) |
| After image | `afterImage( input, damp = 0.96 )` | trails; `damp` uniform; keeps its own history RT |
| Transition | `transition( passA, passB, mixTextureNode, mixRatio, threshold, useTexture )` | two `pass()` of two scenes; `mixRatio` uniform 0..1 |
| Radial blur | `radialBlur( tex, { center, weight=0.9, decay=0.95, count=32, exposure=5 } )` | god-ray style zoom |
| Retro PS1 | `retroPass( scene, camera, { affineDistortion } )` | PS1 look: vertex snapping, affine texture mapping, 0.25 default scale, nearest filtering; replaces `pass()`; combine with `bayerDither`, `scanlines`, `vignette`, `colorBleeding`, `barrelUV` |
| Anaglyph / stereo | see 6.12 | |

### 6.10 Blur family

| Function | Import | Signature | Notes |
|---|---|---|---|
| `gaussianBlur` | `GaussianBlurNode.js` | `( input, directionNode = null, sigma = 4, { premultipliedAlpha = false, resolutionScale = 1 } )` | two-pass separable; `directionNode` float/vec2 = radius scale. `premultipliedGaussianBlur()` helper exists. `.resolution` **deprecated**: use `resolutionScale` |
| `bilateralBlur` | `BilateralBlurNode.js` | `( input, directionNode, sigma = 4, sigmaColor = 0.1 )` | edge-preserving |
| `boxBlur` | `boxBlur.js` | `( tex, { size = 1, separation = 1, premultipliedAlpha } )` | cheap; Fn-style (returns node, no RT) |
| `hashBlur` | `hashBlur.js` | `( tex, bluramount = 0.1, { repeats = 45, premultipliedAlpha } )` | stochastic, single pass; used for backdrop blur |
| `depthAwareBlur` | `depthAwareBlur.js` | `( inputNode(red channel), depthNode, directionNode, camera, sharpness = 2, radius = 1 )` | one-axis; call twice for H+V |
| `depthAwareBlend` | `depthAwareBlend.js` | `( base, blend, depthNode, camera, { blendColor, edgeRadius = 2, edgeStrength = 2 } )` | composite of godrays/bloom without edge leaking |

Blur at low resolution when possible: `gaussianBlur( node, 8, 4, { resolutionScale: 0.5 } )`.

### 6.11 Outline

- **`outline( scene, camera, { selectedObjects, edgeThickness = float(1), edgeGlow = float(0), downSampleRatio = 2 } )`** (`OutlineNode.js`) M. Returns node with `visibleEdge` and `hiddenEdge` masks; compose yourself:

```js
const o = outline( scene, camera, { selectedObjects, edgeGlow, edgeThickness } );
const { visibleEdge, hiddenEdge } = o;
const edges = visibleEdge.mul( visibleColor ).add( hiddenEdge.mul( hiddenColor ) ).mul( edgeStrength );
renderPipeline.outputNode = edges.add( scenePass );
```
  `o.selectedObjects` is the live array (mutate it or reassign). Pulse via `oscSine( time.div( period ).mul( 2 ) )`.
- **`toonOutlinePass( scene, camera, color = black, thickness = 0.003, alpha = 1 )`** from `three/tsl` (core, no addon). Only `MeshToonMaterial`/`MeshToonNodeMaterial` get the (inverted-hull) outline. `renderPipeline.outputNode = toonOutlinePass( scene, camera )` (example `webgpu_materials_toon`). It is a PassNode subclass: replaces `pass()`.
- `sobel` (6.9) for image-space edges.

### 6.12 Stereo

All replace `pass()` and are imported by name: `stereoPass( scene, camera )` (`StereoPassNode.js`, side-by-side, `.stereo` StereoCamera), `anaglyphPass( scene, camera )` (`AnaglyphPassNode.js`; `eyeSep` 0.064, `planeDistance` 0.5, `algorithm`, `colorMode`; exports `AnaglyphAlgorithm`, `AnaglyphColorMode`), `parallaxBarrierPass( scene, camera )` (`ParallaxBarrierPassNode.js`; `.stereo.eyeSep`). `StereoCompositePassNode` is the abstract base. Cost: 2 scene renders.

### 6.13 Godrays `godrays()` L

```js
import { godrays } from 'three/addons/tsl/display/GodraysNode.js';
import { bilateralBlur } from 'three/addons/tsl/display/BilateralBlurNode.js';
import { depthAwareBlend } from 'three/addons/tsl/display/depthAwareBlend.js';
const g = godrays( scenePass.getTextureNode( 'depth' ), camera, pointOrDirectionalLight );
const blurred = bilateralBlur( g.getTextureNode() );
renderPipeline.outputNode = depthAwareBlend( scenePassColor, blurred, scenePassDepth, camera, { blendColor, edgeRadius, edgeStrength } );
```
Uniforms: `raymarchSteps` (60), `density` (0.7), `maxDensity` (0.5), `distanceAttenuation` (2); `resolutionScale`. Only point/directional lights; needs a full shadow setup (`renderer.shadowMap.enabled`, objects cast+receive, light casts). Always blur: raw output is noisy.

### 6.14 Lens flare `lensflare()` and `LensflareMesh`

`lensflare( bloomTextureNode, { ghostTint = vec3(1), threshold = 0.5, ghostSamples = 4, ghostSpacing = 0.25, ghostAttenuationFactor = 25, downSampleRatio = 4 } )()`; the example passes `{ threshold, ghostAttenuationFactor, ghostSpacing }` and **calls the returned node** (`lensflare(...)()`) - follow the example. Requires a bloom pass (best on emissive MRT), then `outputPass.add( bloomPass ).add( gaussianBlur( flarePass, 8 ) )`. Distinct from the object `LensflareMesh` (`three/addons/objects/LensflareMesh.js`, example `webgpu_lensflares`), which is an in-scene mesh.

### 6.15 Motion blur

```js
import { motionBlur } from 'three/addons/tsl/display/MotionBlur.js';
scenePass.setMRT( mrt( { output, velocity } ) );
const vel = scenePass.getTextureNode( 'velocity' ).mul( blurAmount );   // scale velocity = shutter
renderPipeline.outputNode = motionBlur( scenePass.getTextureNode(), vel, int( 16 ) );   // numSamples default 16
```
Fn-style (no RT). Linear space. Place after DOF/TRAA, before tone map. With TRAA both read the same velocity attachment. Only moving objects/camera blur.

### 6.16 Order-independent transparency `oitPass()` L

`oitPass( scene, camera, options? )` (`OITPassNode.js`), replaces `pass()`; weighted-blended OIT (McGuire/Bavoil). Only transparent materials with `NormalBlending` and no transmission qualify; `weightNode` assignable before first render; custom `setMRT` does not capture OIT objects; MSAA only on the WebGPU backend.

### 6.17 VXGI (voxel GI) XL, WebGPU backend only

`three/addons/lighting/vxgi/VXGINode.js` (`VXGINode( depthNode, normalNode, scene, camera, resolution = 128 )`, max 256) + `VXGIVolume( resolution )` (`bounds`, `bounces` 0..2, `bounceConeAngle` 60, `directionalRadiance`). Voxelizes the scene, picks up lights and shadow maps automatically (direct lights only). Props on the node: `aoIntensity`, `aoDistance`, `aoMinVisibility`, `bounces`. Examples: `webgpu_vxgi`, `webgpu_vxgi_sponza`. Factory `vxgi( depthNode, normalNode, scene, camera, resolution )` (exported from `VXGINode.js`; not on the API page). `normalNode` = view-space normals. Official composition (`webgpu_vxgi`): pre-pass (normals+velocity) -> `giPass = vxgi( prePassDepth, prePassNormal, scene, camera, 64 )` -> feed AO+GI **into the lighting** of the beauty pass, then TRAA:

```js
const ao = giPass.getAONode(), gi = giPass.getGINode();
scenePass.contextNode = builtinGIContext( ao.sample( screenUV ).r, gi.sample( screenUV ).rgb );
renderPipeline.outputNode = traa( scenePass, prePassDepth, prePassVelocity, camera );
```

`giPass.volume.stepScale` / `.maxDistance` uniforms, `giPass.bounces` (0..2), `useTemporalFiltering`. `builtinGIContext( aoNode, giNode )` is the GI counterpart of `builtinAOContext`.

### 6.18 Other nodes in `tsl/display`

`ImportanceSampledEnvironment.js` (CDF-sampled env for SSR), `TemporalReprojectNode.js` (`temporalReproject( beauty, depth, normal, velocity, camera, { mode='diffuse'|'specular', accumulate=false, hitPointReprojection } )`, `.setHistoryTexture()`), `RecurrentDenoiseNode.js` (`recurrentDenoise( input, camera, { depth, normal, metalRoughness, diffuse, raw, mode, accumulate=true } )`, `.alphaSource`, `.getRenderTarget()`).

---

## 7. Composing and custom effects

### 7.1 TSL math on pass outputs

A pass or effect is a node: use the usual operators.

```js
import { mix, blendScreen, blendOverlay, saturation, luminance, screenUV, vec4, float, step } from 'three/tsl';
const out = scenePassColor.add( bloomPass.mul( 0.2 ) );                  // additive glow
const out2 = blendScreen( scenePassColor, bloomPass );                  // screen blend (less blown out)
const graded = saturation( out, 1.1 );
const split = mix( left, right, step( 0.5, screenUV.x ) );              // compare view
const withAlpha = vec4( graded.rgb, scenePassColor.a );
```

Core TSL blend helpers (`three/tsl`): `blendBurn`, `blendDodge`, `blendScreen`, `blendOverlay`, `blendColor`.

### 7.2 Custom effect with `Fn`

```js
import { Fn, vec4, screenUV, float } from 'three/tsl';
const myEffect = ( input, amount ) => Fn( () => {
  const c = input.sample( screenUV );                       // TextureNode.sample( uv ): custom UV
  const d = input.sample( screenUV.add( vec2( 0.002, 0 ).mul( amount ) ) );
  return vec4( c.r, d.g, c.b, c.a );
} )();
renderPipeline.outputNode = myEffect( scenePass.getTextureNode(), uniform( 1 ) );
```

- Multi-tap filters need a *texture*: if your input is an expression, wrap it with `rtt( expr )` or `convertToTexture( expr )` first, then `.sample( offsetUV )`.
- Viewport size: `viewportSize`, `screenSize`, `screenUV`, `viewportUV`.
- Depth-based effect: `const z = scenePass.getViewZNode()` (view Z), `scenePass.getLinearDepthNode()` (0..1), raw `getTextureNode('depth')`. Reconstruct world position with `perspectiveDepthToViewZ` etc. (`three/tsl`: `viewZToOrthographicDepth`, `orthographicDepthToViewZ`, `viewZToPerspectiveDepth`, `perspectiveDepthToViewZ`, logarithmic variants). Fog by depth: `mix( color, fogColor, smoothstep( n, f, viewZ.negate() ) )`; see `webgpu_postprocessing_fog`.
- `.discard()`, `.select()`, `Loop`, `If` all work inside `Fn`.
- For material-level screen effects (refraction/backdrop) use `viewportSharedTexture()` / `viewportTexture()` / `viewportMipTexture()` / `viewportLinearDepth` in the material graph (not the pipeline); they read the opaque framebuffer already rendered.

### 7.3 Masking and selective effects

- **Separate scenes as masks** (`webgpu_postprocessing_masking`): `const mask = pass( maskScene, camera ).a; out = mask.mix( base, texture( tex ) )`. Each `pass()` renders its own scene.
- **Layers**: render a second pass with only chosen layers, then combine.

```js
const glowLayers = new THREE.Layers(); glowLayers.set( 1 );     // objects: obj.layers.enable( 1 )
const glowPass = pass( scene, camera ).setLayers( glowLayers );  // setLayers returns the PassNode
const out = scenePass.add( bloom( glowPass ) );
```

  `setLayers` is verified API (used in `webgpu_deferred` with `new THREE.Layers()`); the selective-bloom use is a composition of it, not an official example. Cost: full extra scene render; prefer emissive MRT (1 render).
- **Per-object MRT mask** (bloom_selective example) for dynamic on/off without layers.
- **Pass-through flags**: `scenePass.transparent = false` / `scenePass.opaque = false` to separate transparent geometry (see deferred example: opaque pass with `depthTexture` shared via `pass( scene, camera, { depthTexture: opaquePass.getTexture( 'depth' ), autoClearDepth: false } )`).

### 7.4 Feedback and render-to-texture

- `rtt( node, width = null, height = null, { type = HalfFloatType, autoUpdate = true, resolutionScale = 1, wrapS, wrapT, minFilter, magFilter, generateMipmaps, depthBuffer = true } )` -> `RTTNode` (a TextureNode). Use to cache a heavy expression once and sample it many times (anamorphic example), or to feed a downscaled pass. `.autoUpdate = false` + `.textureNeedsUpdate = true` for on-demand baking. `convertToTexture( node )` returns the node itself if already a texture/pass.
- Frame feedback: `scenePass.getPreviousTextureNode()` (previous beauty), or `afterImage`. Temporal denoisers use `getRenderTarget()` / `setHistoryTexture`.
- Do not sample an RTT inside the same graph that renders it without a ping-pong (`PassNode.toggleTexture`, `getPreviousTexture`).

---

## 8. Temporal effects, resolution scaling

### 8.1 Temporal checklist (TRAA, TAAU, SSGI/GTAO temporal, SSR denoise, motion blur)

1. `velocity` in the pass MRT. 2. Pass depth node via `getTextureNode( 'depth' )`. 3. Pass the **same camera** as the scene pass. 4. **No MSAA** on that pass: `pass( scene, camera, { samples: 0 } )`. `samples` is applied in PassNode `setup` (`options.samples ?? renderer.samples`); the AO example switches at runtime with `scenePass.options.samples = useTRAA ? 0 : 4; renderPipeline.needsUpdate = true; scenePass.needsUpdate = true`. 5. Disocclusion/ghosting: keep `maxVelocityLength` default, avoid changing materials per-frame without velocity. 6. Camera jumps (teleport) produce ghost frames; consider disabling for a frame. 7. Do not apply FXAA after TRAA.

### 8.2 Resolution scaling

- Pass: `scenePass.setResolutionScale( 0.5 )` (replaces deprecated `setResolution`). Output of effects fed from it is still sized to the drawing buffer by the final quad (bilinear), or use `fsr1`/`taau`.
- Effect-level: `bloom.setResolutionScale( 0.25..0.5 )`, `ao.resolutionScale = 0.5`, `ssao.resolutionScale = 0.5`, `sss.resolutionScale`, `ssr resolutionScale`, `gaussianBlur(..., { resolutionScale })`, `godrays.resolutionScale`, `rtt( ..., { resolutionScale } )`, `lensflare downSampleRatio`, `outline downSampleRatio`.
- Pixel ratio: `renderer.setPixelRatio( Math.min( devicePixelRatio, 2 ) )`; all passes follow `renderer.getSize() * pixelRatio`. `screenDPR` available in TSL.

### 8.3 Upscale recipes

```js
// spatial
scenePass.setResolutionScale( 0.6 ); renderPipeline.outputNode = fsr1( scenePass );
// temporal
scenePass.setResolutionScale( 0.6 );
scenePass.setMRT( mrt( { output, velocity } ) );
const t = taau( scenePass.getTextureNode( 'output' ), scenePass.getTextureNode( 'depth' ), scenePass.getTextureNode( 'velocity' ), camera );
renderPipeline.outputNode = sharpen( t.getTextureNode(), 0.5 );
```

---

## 9. Recommended stacks

### 9.1 Cinematic stack (desktop)

```
[A] pre-pass (opaque only): normal (RGBA8) + velocity          -> depth/normal/velocity for AO, SSR, TRAA
[B] beauty pass: output (+ emissive MRT), contextNode = builtinAOContext( GTAO )
[C] SSR add          [D] bloom (emissive) add       [E] DOF
[F] motion blur      [G] TRAA (resolves GTAO/SSR/SSGI noise)
-- renderOutput (tone map + sRGB) --
[H] lut3D grade      [I] film grain + vignette      [J] (FXAA only if TRAA is not used)
```

Rationale:
- AO and SSR need depth/normals of opaque geometry only; an opaque pre-pass (`transparent = false`) keeps transparents out of G-buffer. AO feeds the beauty pass's lighting through `contextNode` so it only darkens ambient light.
- SSR/SSGI/AO outputs are noisy; TRAA after them is the cheapest denoiser (uses velocity). Everything up to TRAA stays linear HDR.
- Bloom on HDR linear before tone mapping so highlights >1 bloom; use emissive MRT so the sky/background does not bloom.
- DOF before bloom is also valid (bokeh of bright lights then bloom); official examples keep them separate. Pick DOF first if you want bloom to follow the blur, bloom first if you want physically bright bokeh discs. Do both on linear color.
- Motion blur is a plain velocity-directed blur (no history): run it on linear color before TRAA (as in the stack) or just before tone mapping if TRAA is not used.
- Tone map once, at the end of the linear section. Then display-referred steps: LUT (needs graded sRGB-ish input), grain (grain over tone-mapped image looks right, not scaled by exposure), vignette.
- FXAA/SMAA are alternatives to TRAA: SMAA before tone map (linear), FXAA after (sRGB). Do not stack TRAA + FXAA.

```js
const prePass = pass( scene, camera ); prePass.transparent = false;
prePass.setMRT( mrt( { output: packNormalToRGB( normalView ), velocity } ) );
prePass.getTexture( 'output' ).type = THREE.UnsignedByteType;
const normal = sample( uv => unpackRGBToNormal( prePass.getTextureNode().sample( uv ) ) );
const depth = prePass.getTextureNode( 'depth' ), vel = prePass.getTextureNode( 'velocity' );

const aoPass = ao( depth, normal, camera ); aoPass.resolutionScale = 0.5;

const scenePass = pass( scene, camera, { samples: 0 } );
scenePass.contextNode = builtinAOContext( aoPass.getTextureNode().sample( screenUV ).r );
scenePass.setMRT( mrt( { output, emissive: vec4( emissive, output.a ) } ) );
const color = scenePass.getTextureNode( 'output' );

let c = color.add( bloom( scenePass.getTextureNode( 'emissive' ), 1.5, 0.5 ) );
c = dof( c, scenePass.getViewZNode(), focus, focal, bokeh );
c = motionBlur( c, vel.mul( shutter ) );
c = traa( c, depth, vel, camera );

renderPipeline.outputColorTransform = false;
let out = renderOutput( c );
out = lut3D( out, texture3D( lut ), lut.image.width, uniform( 1 ) );
out = film( out, uniform( 0.15 ) );
out = vignette( out, 0.4, 0.5 );          // from CRT.js
renderPipeline.outputNode = out;
```

Keep one velocity+depth source (the pre-pass) for TRAA/motion blur and take DOF viewZ from the same pass family (`getViewZNode()` of the pass whose depth you use); the beauty pass above does not need a `velocity` attachment.

Cost control: AO `resolutionScale 0.5`; SSR `quality 0.25`, `maxDistance` small, gate by roughness; bloom `setResolutionScale( 0.5 )`; downgrade MRT attachments to RGBA8; disable SSR/DOF on idle/low-tier.

### 9.2 Cheap / mobile stack

1. Prefer **no pipeline** (`renderer.render`, MSAA via `antialias: true`) if only tone mapping is needed: renderer applies tone mapping itself.
2. Color-grade only: `DirectRenderPipeline` (no extra framebuffer).
3. Light stack: `pass( scene, camera, { samples: 4 } )` (MSAA) -> bloom on `emissive` MRT at `setResolutionScale( 0.25 )` -> add -> default `outputColorTransform` -> done. No FXAA needed with MSAA.
4. If fragment-bound: `scenePass.setResolutionScale( 0.5..0.75 )` + `fsr1` (source needs AA: use MSAA at the lower res) and `renderer.setPixelRatio( 1..1.5 )`.
5. Avoid: SSR, SSGI, SSAA, godrays, DOF (`dof_basic` boxBlur variant at 0.5 res if needed), stochastic anything, TAAU on weak GPUs, multiple scene passes (pre-pass doubles draw calls), RGBA16 MRT attachments (use RGBA8).
6. AO at `ssao` `resolutionScale 0.5`, `samples 8`, or bake AO.

---

## 10. Gotchas checklist

- Use `renderPipeline.render()`; calling `renderer.render()` bypasses everything.
- `outputNode` replaced at runtime -> `renderPipeline.needsUpdate = true`.
- `outputColorTransform = false` + forgot `renderOutput` => no tone mapping, wrong gamma (too dark/linear look). Both => double tone mapping.
- FXAA needs sRGB input; SMAA/TRAA/bloom/DOF need linear. Sobel/LUT/CA after `renderOutput`.
- `getTextureNode( 'depth' )` is not linear. Use `getViewZNode()` for `dof()`, `getLinearDepthNode()` for visualization.
- MRT order: call `setMRT` before building consumers (and before `compileAsync`). Unused keys are skipped.
- Packed normals (`packNormalToRGB`) must be unpacked with `sample( uv => unpackRGBToNormal( tex.sample( uv ) ) )` before feeding AO/SSR/SSGI.
- `scenePass.getTexture( 'x' ).type = UnsignedByteType` must be set before first render.
- Transparents are not in depth/normals; AO/SSR/SSGI ignore them. Set pre-pass `transparent = false`. Use `oitPass` for correct blending.
- MSAA + TRAA/TAAU conflict; with FSR1 use MSAA or SMAA on the low-res source.
- `ssr`: add `.rgb` to beauty; environment must be equirect with CPU data, not PMREM.
- `ssgi`/`ao` `useTemporalFiltering = true` requires TRAA in the chain.
- Changing `samples` on GTAO or compile-time SSR flags recompiles shaders (hitch); do not animate them.
- `bloom()` returns glow only; add it. Bloom of whole beauty also blooms `scene.background`.
- `lensflare( ... )()` is called once more in the example; copy the example's usage.
- Cleanup: dispose effects (`node.dispose()`), `renderPipeline.dispose()`, and the pass (`scenePass.dispose()`) when tearing down; effect swapping leaks RTs otherwise.
- Deprecated in r186: `PostProcessing` (use `RenderPipeline`), `renderAsync()`, `PassNode.setResolution/getResolution`, `GaussianBlurNode.resolution`, `GTAONode.distanceExponent/distanceFallOff`.
- `getViewZNode`/`getLinearDepthNode` are built with perspective-depth formulas (source has a TODO for ortho); assume perspective cameras.

## 11. Doc gaps found

- TSL Guide `54-pass.md` lists `pass.getDepthNode()` which does not exist in r186 PassNode.
- TSL Guide `56-post-processing.md` shows `sharpen` default 0.5 vs API/source 0.2; `smaa(node)` documented with an `options` param that the source does not have; `afterImage` damp shown default 0.96 (consistent), `film( node, intensity, uvNode )` OK.
- `vxgi()` factory exists in source (`examples/jsm/lighting/vxgi/VXGINode.js`) but is absent from the VXGINode API page.
- No example for `film`, `bleach`, `sepia`, `denoise` (non-temporal), `depthAwareBlur`, `bilateralBlur` standalone, `ImportanceSampledEnvironment`.
- `LensflareNode` API page does not mention the trailing call `lensflare(...)()` used in the example.
- `PassNode.md` code example still names the variable `postProcessing = new RenderPipeline(...)`.
- Selective bloom by layers is not an official example (derived from `setLayers`).

## See also

- `tsl-guide/54-pass.md`, `55-mrt.md`, `56-post-processing.md`, `57-output-color-transform.md`, `58-rtt.md`, `67-blend-modes.md`, `68-color-adjustments.md`, `47-viewport.md`, `65-packing.md`
- `tsl-reference.md` (function-level reference)
- `examples-webgpu.md` (catalog of all webgpu examples, postprocessing group)
- API pages: `RenderPipeline.md`, `PassNode.md`, `MRTNode.md`, `RenderOutputNode.md`, `BloomNode.md`, `GTAONode.md`, `SSRNode.md`, `SSGINode.md`, `TRAANode.md`
