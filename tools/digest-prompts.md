# Digest prompts

The written reference files were produced by subagents from the local corpus.
Reuse these briefs when a release changes an area enough that hand-editing is
slower than regenerating. Replace `<CORPUS>` with the absolute path of this
folder; the corpus lives in `threejs/references/api/`, `tools/corpus/manual/`,
`threejs-tsl-webgpu/references/tsl-guide/` and `tsl-reference.md`, and a shallow
checkout of the release tag (`git clone --depth 1 --branch r<N>
https://github.com/mrdoob/three.js`) for source and examples.

## Common preamble (prepend to every brief)

> You are writing reference files for a Claude Code skill about three.js r<N>
> (npm three@0.<N>.x). Source of truth = local offline copies of the official
> docs: manual pages `<CORPUS>/tools/corpus/manual/<slug>.md`; API pages
> `<CORPUS>/threejs/references/api/<ClassName>.md`; API index
> `<CORPUS>/threejs/references/api-index.txt`; TSL guide
> `<CORPUS>/threejs-tsl-webgpu/references/tsl-guide/`; TSL reference
> `<CORPUS>/threejs-tsl-webgpu/references/tsl-reference.md`; source checkout
> `<SRC>` (src/, examples/*.html, examples/jsm/).
> RULES: (1) Only state APIs that exist in the local docs/source; verify every
> class/method/property name by grepping before writing; never invent.
> (2) Dense, terse, technical; code over prose; complete-but-minimal snippets
> with modern ESM imports. (3) Note where WebGLRenderer and WebGPURenderer
> differ; mark deprecated/removed things with the revision. (4) Explain the why
> and the gotchas. (5) Start with `# Title`, a "When to read this" paragraph and
> a table of contents; end with "See also" pointing to `references/api/<Name>.md`
> and official URLs. (6) Markdown, no emojis, no fluff. Report back only: file
> paths, line counts, 3-line coverage summary, doc gaps noticed.

## Briefs (file → scope)

**threejs/references/fundamentals.md** (~500 lines): manual fundamentals,
prerequisites, setup, installation, creating-a-scene, responsive, scenegraph,
primitives, materials, textures, lights, cameras, shadows, fog, rendertargets,
matrix-transformations, how-to-update-things, webgl-compatibility-check, faq,
libraries-and-plugins; API Object3D, Scene, cameras, WebGLRenderer, Mesh, Group,
Texture, Fog, Timer, Layers, Raycaster.

**threejs/references/geometry.md** (~450 lines): custom-buffergeometry,
drawing-lines, creating-text, voxel-geometry; BufferGeometry/BufferAttribute,
interleaved and instanced buffers, every core geometry, Shape/Path/Curve
family, BufferGeometryUtils, Line/Points, fat lines (Line2), TextGeometry,
modifiers, MeshSurfaceSampler.

**threejs/references/materials.md** (~550 lines): material-table, materials,
transparency, color-management; Material and every Core/Materials class incl.
*NodeMaterial; all map slots, colorSpace rules, texture transforms/channels,
ShaderMaterial/onBeforeCompile, NodeMaterial equivalence, needsUpdate, dispose.

**threejs/references/loaders-assets.md** (~450 lines): loading-3d-models,
load-gltf, load-obj, textures, canvas-textures, cleanup; Loader/LoadingManager,
GLTFLoader + DRACO/KTX2/meshopt canonical setup and extension list, HDR/EXR,
all other loaders, splat loaders, exporters, Cache, decoder paths, disposal.

**threejs/references/animation.md** (~350 lines): animation-system; mixer/
action/clip/tracks, blending, additive, skinning, SkeletonUtils, retargeting,
morph targets, IK, AnimationObjectGroup.

**threejs/references/controls-interaction.md** (~400 lines): picking,
align-html-elements-to-3d, indexed-textures, tips; every Controls class,
TransformControls getHelper, Raycaster details, GPU picking, CSS2D/CSS3D,
SelectionBox, input handling.

**threejs/references/xr-audio.md** (~300 lines): VR/AR manual pages; WebXRManager/
XRManager, buttons, controllers, hands, hit test, planes, light estimation,
WebGPU XR status; Audio classes.

**threejs/references/recipes.md** (~600 lines): every manual "Solutions" and
"Tips" page as a recipe, scene setup starters (Vite, import map, WebGPU),
common-errors table, needsUpdate matrix, uniform-types.

**threejs/references/lighting-shadows.md** (~450 lines): lights, shadows,
backgrounds (environment), color-management; every Light/Shadow class, physical
units, shadow tuning, CSM/CSMShadowNode/TileShadowNode, PMREM/RoomEnvironment,
light probes, RectAreaLight init, clustered lighting, helpers, mistakes.

**threejs/references/versions-and-migration.md** (~550 lines): migration guide
(wiki), docs/llms.txt, package.json exports, build files, outdated→modern
table with revisions, per-revision changelog r150→current, upcoming section.

**threejs-tsl-webgpu/references/tsl-cheatsheet.md** (~750 lines): the whole TSL
guide + reference distilled: mental model, types, swizzle, operators, math,
Fn, variables, control flow, stages, compute, inputs, accessors, lighting,
scene, display, utilities, context, native, debug, top mistakes.

**threejs-tsl-webgpu/references/node-materials.md** (~500 lines): NodeMaterial
family and every slot, setup hooks, classic props vs nodes, instancing/
batching, lighting models, WebGL fallback, GLSL→TSL side by side,
serialization, 10 recipes.

**threejs-tsl-webgpu/references/webgpu-renderer.md** (~500 lines): manual
webgpurenderer; Renderer/WebGPURenderer options (verify in
src/renderers/common/Renderer.js), init, backends, limitations, render targets/
MRT, readback, timestamps, Inspector, clipping, XR, pitfalls.

**threejs-tsl-webgpu/references/compute.md** (~600 lines): TSL compute guide
sections + webgpu_compute_* examples: storage, atomics, barriers, indirect,
readback, feeding render, ping-pong, sorting, WebGL fallback, 6 worked
examples, perf, debugging.

**threejs-tsl-webgpu/references/post-processing-webgpu.md** (~650 lines):
manual webgpu-postprocessing + guide pass/mrt/post-processing sections +
examples/jsm/tsl/display/*: RenderPipeline, PassNode, MRT, every effect with
signature/params/cost, composition, masking, custom effects, stacks.

**threejs-tsl-webgpu/references/examples-webgpu.md** (~350 lines): annotated
catalog of all webgpu_* examples from files.json, grouped, 25 starred.

**threejs-performance/references/** (4 files, ~400-600 lines each):
draw-calls-and-geometry (renderer.info, InstancedMesh, BatchedMesh,
SceneOptimizer, merge, LOD, culling, matrix updates, compileAsync);
textures-and-memory (memory math, KTX2, upload hitches, render targets,
disposal, allocation-free loops); rendering-strategies (on demand, pixel
ratio, OffscreenCanvas, shadow/light budgets, overdraw, post cost, mobile,
measuring); shader-and-webgpu-perf (shader cost, recompiles, UBOs, TSL/WebGPU
perf, compute, picking, particles).

**threejs-visual-quality/references/** (4 files, ~300-500 lines each):
color-and-tone-mapping (pipeline, all tone mapping modes, exposure, LUT, HDR
output, debugging); pbr-materials-and-environment (value ranges, every
MeshPhysicalMaterial feature, PMREM/HDRI/RoomEnvironment, light setups with
numbers, glTF practices, starters); shadows-and-antialiasing (shadow types,
CSM, contact/baked, AA comparison table); post-processing-and-atmosphere
(both pipelines side by side, per-effect defaults, fog/sky/water/reflections/
refraction/particles/volumes, checklist, 3 stacks).
