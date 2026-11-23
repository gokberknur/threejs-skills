# three.js r187 WebGPU Example Catalog (243 examples)

## When to read this

Read to find a working reference for a technique (compute, MRT, post effect, volume, lighting model, XR) before writing code. Entries marked ★ are the 25 most instructive; read those first.

## How to open an example

- Live: `https://threejs.org/examples/#<name>` (e.g. `https://threejs.org/examples/#webgpu_postprocessing_ao`).
- Source: `examples/<name>.html` in the three.js GitHub repo (not in the npm package); addons ship in the package as `three/addons/*` (= `examples/jsm/*`).
- List source of truth: `examples/files.json`, key `"webgpu"` (243 entries). Names below omit nothing; each is `webgpu_<name>`.
- Standard imports: `import * as THREE from 'three/webgpu'; import { ... } from 'three/tsl';` Post effects: `three/addons/tsl/display/<Name>.js`. Many examples use `renderer.inspector = new Inspector()` and `node.toInspector('label')` for debugging; ignore these when copying.
- Note: in r187 the post-processing class is `THREE.RenderPipeline` (`PostProcessing` is the deprecated alias since r183).

## Table of contents

- 1. Post-processing (RenderPipeline) (49)
- 2. Compute and GPGPU (25)
- 3. Materials, shading and environment (34)
- 4. Lighting and shadows (30)
- 5. Instancing, batching and performance (9)
- 6. Loaders, animation and assets (17)
- 7. Textures and render targets (9)
- 8. Volumes and raymarching (7)
- 9. Backdrop, reflection, refraction, water, sky (12)
- 10. Lines, points, sprites, fog (9)
- 11. TSL showcase and procedural (18)
- 12. WebXR (4)
- 13. Cameras, canvas, misc (7)
- Top 25 index
- See also

## 1. Post-processing (RenderPipeline)

Node-based pipeline. Guide: `post-processing-webgpu.md`. All use `new THREE.RenderPipeline( renderer )` unless noted.

- ★ `webgpu_postprocessing`: DotScreen + RGBShift chain on a scene pass. API: pass, dotScreen, rgbShift, RenderPipeline.render(). Why read: smallest RenderPipeline setup: pass() + effect nodes + outputNode.
- `webgpu_postprocessing_direct`: color grade without a scene pass or intermediate framebuffer. API: DirectRenderPipeline, saturation(output.rgb), render(scene, camera).
- `webgpu_postprocessing_bloom`: whole-image bloom with animated model; tweak strength/radius/threshold uniforms. API: bloom, ReinhardToneMapping.
- ★ `webgpu_postprocessing_bloom_emissive`: only emissive surfaces glow, via MRT. API: mrt({output, emissive}), setBlendMode, bloom. Why read: canonical emissive-MRT selective bloom incl. mrt blend mode + RGBA8 attachment.
- ★ `webgpu_postprocessing_bloom_selective`: random spheres toggle glow through a per-material mask attachment. API: material.mrtNode, mrt, renderOutput(). Why read: per-material material.mrtNode mask, outputColorTransform=false + .renderOutput().
- `webgpu_postprocessing_anamorphic`: horizontal streak bloom with custom high-pass. API: bloom.highPassFn, rtt, Loop, setResolutionScale.
- `webgpu_postprocessing_lensflare`: ghosts/halo derived from the bloom of emissive pixels. API: lensflare, bloom, gaussianBlur, MRT emissive.
- ★ `webgpu_postprocessing_ao`: GTAO or SSAO switchable, applied to indirect light. API: ao, ssao, builtinAOContext, sample, traa. Why read: opaque pre-pass (packed normals + velocity), GTAO vs SSAO, builtinAOContext, TRAA.
- `webgpu_postprocessing_ssr`: first-gen SSR with packed normals and metal/roughness attachment. API: ssr, packNormalToRGB, unpackRGBToNormal, smaa.
- ★ `webgpu_postprocessing_ssr_denoise`: stochastic SSR + temporal reprojection + recurrent denoise + multi-bounce history. API: ssr({stochastic}), temporalReproject, recurrentDenoise, sharpen. Why read: full stochastic SSR chain: MRT packing, temporalReproject, recurrentDenoise, setHistory feedback.
- ★ `webgpu_postprocessing_ssgi`: screen-space GI with AO/GI split composite. API: ssgi, getAONode/getGINode, traa. Why read: SSGI composite formula (ao * color + diffuse * gi) then TRAA.
- `webgpu_postprocessing_ssgi_ballpool`: SSGI stress test with thousands of instanced balls. API: ssgi, InstancedMesh, ACES tone mapping.
- `webgpu_postprocessing_sss`: screen-space contact shadows from the main directional light. API: sss, traa, builtinShadowContext.
- `webgpu_postprocessing_dof`: physical bokeh depth of field. API: dof, getViewZNode.
- `webgpu_postprocessing_dof_basic`: cheap DOF: boxBlur mixed by view-Z distance, then manual output transform and FXAA. API: boxBlur, getViewZNode, renderOutput, fxaa.
- `webgpu_postprocessing_fog`: full-screen volumetric fog at low resolution with blur and 3D noise. API: rtt, gaussianBlur, texture3D, interleavedGradientNoise, setResolutionScale.
- `webgpu_postprocessing_godrays`: screen-space light shafts for a shadow-casting light. API: godrays, bilateralBlur, depthAwareBlend.
- ★ `webgpu_postprocessing_motion_blur`: per-pixel velocity motion blur with vignette. API: motionBlur, velocity MRT. Why read: velocity MRT scaled as shutter, Fn-style motionBlur().
- ★ `webgpu_postprocessing_traa`: temporal reprojection AA. API: traa, velocity MRT. Why read: minimum TRAA setup: velocity MRT + depth + camera.
- ★ `webgpu_postprocessing_fxaa`: FXAA in display space. API: fxaa, renderOutput, outputColorTransform=false. Why read: color-order lesson: outputColorTransform=false, renderOutput, then FXAA (sRGB).
- `webgpu_postprocessing_smaa`: SMAA toggle. API: smaa.
- `webgpu_postprocessing_ssaa`: brute-force supersampling, selectable sample level. API: ssaaPass, sampleLevel.
- `webgpu_postprocessing_3dlut`: color grading with 3D LUT files (.cube/.3dl/image). API: lut3D, texture3D, LUTCubeLoader/LUT3dlLoader/LUTImageLoader.
- `webgpu_postprocessing_afterimage`: trailing frames. API: afterImage, damp.
- `webgpu_postprocessing_ca`: chromatic aberration in display space. API: chromaticAberration, renderOutput.
- `webgpu_postprocessing_difference`: frame-to-frame difference using previous-frame texture. API: pass.getPreviousTextureNode, luminance, saturation.
- `webgpu_postprocessing_masking`: mask two scenes with their alpha to composite textures. API: pass(...).a, mix, texture.
- `webgpu_postprocessing_outline`: outline selected objects, visible/hidden edge colors, pulse. API: outline, visibleEdge/hiddenEdge, oscSine.
- `webgpu_postprocessing_pixel`: pixel-art render with normal/depth edges. API: pixelationPass.
- `webgpu_postprocessing_radial_blur`: zoom/radial blur. API: radialBlur({weight, decay, count, exposure}).
- `webgpu_postprocessing_retro`: PS1-style render + CRT filters (dither, scanlines, barrel). API: retroPass, bayerDither, scanlines, vignette, barrelUV, colorBleeding.
- `webgpu_postprocessing_sobel`: Sobel edge detection on display-referred image. API: sobel, renderOutput.
- `webgpu_postprocessing_transition`: scene A/B transition with wipe textures. API: transition, two pass() with different scenes.
- `webgpu_upscaling_fsr1`: spatial upscaling from reduced-resolution scene pass. API: fsr1, pass.setResolutionScale.
- `webgpu_upscaling_taau`: temporal upscaling + RCAS sharpening. API: taau, sharpen, setResolutionScale, velocity MRT.
- ★ `webgpu_oit`: order-independent transparency toggle. API: oitPass. Why read: oitPass(): weighted-blended order-independent transparency.
- `webgpu_display_stereo`: stereo, anaglyph (algorithms/color modes) and parallax barrier views. API: stereoPass, anaglyphPass, parallaxBarrierPass.
- ★ `webgpu_deferred`: deferred rendering built from PassNodes. API: pass.setLayers, MRT, depthTexture sharing, overrideNodes, Lighting. Why read: multi-pass deferred shading with PassNode layers, shared depthTexture, overrideNodes, MRT G-buffer.
- ★ `webgpu_mrt`: visualize MRT attachments side by side. API: mrt, getTexture, outputColorTransform=false. Why read: MRT basics: output/normal/diffuse/emissive attachments and split-view debug.
- `webgpu_mrt_mask`: blur/mask driven by an MRT attachment. API: mrt, gaussianBlur.
- `webgpu_multiple_rendertargets`: render-target MRT without a pipeline: write several textures from one render. API: renderer.setMRT, RenderTarget(textures: n), mrt.
- `webgpu_multiple_rendertargets_readback`: same as above plus CPU readback of attachments. API: readRenderTargetPixels, setMRT.
- `webgpu_rtt`: render scene to a RenderTarget and show it on a quad. API: renderer.setRenderTarget, RenderTarget, saturation/hue.
- `webgpu_depth_texture`: sample a DepthTexture as a color. API: RenderTarget.depthTexture, DepthTexture(FloatType), texture().
- `webgpu_multisampled_renderbuffers`: MSAA on RenderTarget toggled via samples. API: RenderTarget.samples.
- `webgpu_layers`: Layers filtering objects per camera. API: camera.layers, object.layers.set.
- `webgpu_test_memory`: stress test of MRT + OutlineNode + GTAONode (resource leak test). API: mrt, outline, ao, context.
- ★ `webgpu_vxgi`: voxel cone-traced GI and AO. API: vxgi, builtinGIContext, traa. Why read: voxel GI with vxgi() + builtinGIContext + TRAA.
- `webgpu_vxgi_sponza`: VXGI on Sponza with sky and first-person controls. API: vxgi, SkyMesh, FirstPersonControls.
- `webgpu_color_grading` (r187): color grading node stack.

## 2. Compute and GPGPU

`renderer.compute( node )` / `.compute( count )`, `instancedArray`, `storage`, `Fn`, atomics. See TSL guide 28, 30, 36-38.

- `webgpu_compute_points`: minimal compute updating point positions. API: instancedArray, instanceIndex, compute().
- ★ `webgpu_compute_particles`: GPU particles with respawn. API: instancedArray, hash, If, SpriteNodeMaterial. Why read: minimal compute() + instancedArray + SpriteNodeMaterial particle system.
- `webgpu_compute_particles_fluid`: fluid particles using a grid, atomics and indirect draw. API: struct, atomicAdd/Load/Store, Loop, IndirectStorageBufferAttribute.
- `webgpu_compute_particles_rain`: rain with collision against a height RT rendered from a layer camera. API: compute, RenderTarget, layers, billboarding.
- `webgpu_compute_particles_snow`: snow with collision RT, blurred background. API: compute, RenderTarget, gaussianBlur.
- `webgpu_compute_birds`: boids flocking, positions/velocities in storage buffers. API: instancedArray, InstancedMesh, compute, varying.
- `webgpu_compute_cloth`: verlet cloth with spring constraints and sphere collision. API: instancedArray, Loop, compute, SpriteNodeMaterial, triNoise3D.
- `webgpu_compute_geometry`: compute shader modifies geometry attribute in place and raycasts. API: storage, StorageBufferAttribute, objectWorldMatrix.
- `webgpu_compute_water`: heightfield water simulation with interactive ripples. API: instancedArray, struct, compute, workgroup.
- `webgpu_compute_texture`: compute writes a StorageTexture displayed on a mesh. API: StorageTexture, textureStore, instanceIndex.
- `webgpu_compute_texture_3d`: compute generates 3D noise in Storage3DTexture and raymarches it. API: Storage3DTexture, textureStore, mx_noise_vec3, RaymarchingBox.
- ★ `webgpu_compute_texture_pingpong`: two storage textures swapped each frame. API: storageTexture, NodeAccess, textureStore. Why read: storageTexture + textureStore with NodeAccess read/write ping-pong.
- ★ `webgpu_compute_reduce`: parallel reduction variants. API: workgroup memory, subgroupAdd, wgsl. Why read: workgroup/subgroup parallel reduction kernels (subgroupAdd, workgroup memory).
- `webgpu_compute_sort_bitonic`: bitonic sort step-by-step, with storage reads. API: BitonicSort (addons), StorageInstancedBufferAttribute, workgroup.
- `webgpu_meshlets`, `webgpu_meshlets_ibl`, `webgpu_meshlets_city`, `webgpu_meshlets_instanced`, `webgpu_meshlets_materials`, `webgpu_meshlets_meshes` (r187; replace `webgpu_compute_rasterizer(_ibl)`, removed in r187): GPU-driven meshlet rendering. API: `MeshletDrawingPipeline`, `VisibilityBufferDrawingPipeline`, `MeshletGeometryUtils`, renderer `drawingPipeline`.
- `webgpu_compute_audio`: audio synthesis/processing in compute, readback to AudioContext. API: compute, getArrayBufferAsync, AudioContext.
- `webgpu_storage_buffer`: fetching an external element from a StorageBuffer (PBO path) vs. storage node. API: storage().setPBO, workgroupBarrier.
- ★ `webgpu_struct_drawindirect`: indirect draw args written by compute. API: struct, IndirectStorageBufferAttribute, geometry.setIndirect, atomicStore. Why read: struct() + IndirectStorageBufferAttribute + geometry.setIndirect: GPU-driven draw counts.
- `webgpu_tsl_compute_attractors_particles`: particles attracted by gravity wells in compute. API: uniformArray, Loop, instancedArray, TransformControls.
- `webgpu_skinning_points`: GPU skinning to points via computeSkinning. API: computeSkinning, instancedArray, PointsNodeMaterial.
- `webgpu_skinning_instancing_individual`: individually animated skinned instances with storage buffers. API: attributeArray, storage, compute.
- `webgpu_particles`: particles drawn with indirect args from compute. API: StorageBufferAttribute, IndirectStorageBufferAttribute, SpriteNodeMaterial, range.
- `webgpu_instance_points`: compute moves instanced points (storage instanced attribute). API: StorageInstancedBufferAttribute, storage, shapeCircle.
- `webgpu_tsl_vfx_linkedparticles`: particles linked by lines, bloom, mouse interaction. API: compute, mx_fractal_noise, BloomNode.

## 3. Materials, shading and environment

Node materials, TSL material slots (colorNode, positionNode, normalNode...), env maps, tone mapping.

- ★ `webgpu_materials`: showcase of NodeMaterial inputs, wgslFn custom function, triplanar. API: NodeMaterial, wgslFn, triplanarTexture. Why read: tour of NodeMaterial customization: wgslFn, triplanar, positionNode/colorNode patterns.
- `webgpu_materials_basic`: MeshBasicNodeMaterial.
- `webgpu_materials_arrays`: material arrays with geometry groups.
- `webgpu_materials_alphahash`: alpha hashing (stochastic transparency) with SSAA to resolve noise. API: material.alphaHash, ssaaPass.
- `webgpu_materials_cubemap_mipmaps`: custom cube map mip chain.
- `webgpu_materials_displacementmap`: displacement map on MeshStandardNodeMaterial. API: displacementMap.
- `webgpu_materials_envmaps`: equirect/cube env maps on materials.
- `webgpu_materials_envmaps_bpcem`: box-projected cube env mapping. API: getParallaxCorrectNormal, pmremTexture, CubeCamera.
- `webgpu_materials_envmaps_groundprojected`: ground projected skybox. API: GroundedSkybox, cubeTexture.
- `webgpu_materials_lightmap`: lightMap on a material.
- `webgpu_materials_matcap`: matcap material. API: MeshMatcapNodeMaterial.
- `webgpu_materials_retroreflection`: retroreflective surface (road signs) with bloom and blurred reflector. API: reflector, hashBlur, BloomNode, MeshPhysicalNodeMaterial.
- `webgpu_materials_sss`: subsurface scattering material. API: MeshSSSNodeMaterial.
- `webgpu_materials_toon`: toon material and outline pass. API: MeshToonNodeMaterial, toonOutlinePass.
- `webgpu_materials_transmission`: transmission (refractive glass). API: MeshPhysicalMaterial.transmission.
- `webgpu_materials_video`: video as material map. API: VideoTexture.
- `webgpu_materials_texture_html`: HTML element rendered as a texture on a mesh with interaction. API: HTMLTexture, InteractionManager.
- `webgpu_materials_texture_manualmipmap`: hand-authored mip levels. API: texture.mipmaps.
- `webgpu_materialx_noise`: MaterialX noise nodes on geometry. API: mx_noise_*, mx_worley_noise_*, mx_unifiednoise2d/3d, MaterialXHextile.
- `webgpu_clearcoat`: clearcoat with normal flakes. API: clearcoat, FlakesTexture.
- `webgpu_parallax_uv`: parallax occlusion mapping. API: parallaxUV, normalMap.
- `webgpu_cubemap_adjustments`: hue/saturation of env map through nodes. API: pmremTexture, scene.environmentNode.
- `webgpu_cubemap_dynamic`: real-time cube reflections. API: CubeCamera, CubeRenderTarget.
- `webgpu_cubemap_mix`: mix two env maps over time. API: pmremTexture, oscSine.
- `webgpu_pmrem_cubemap`: PMREM from cube texture used in node. API: pmremTexture, normalWorldGeometry.
- `webgpu_pmrem_equirectangular`: PMREM from equirect. API: pmremTexture.
- `webgpu_pmrem_scene`: PMREM from a scene. API: PMREMGenerator.fromScene.
- `webgpu_pmrem_test`: PMREM with directional light test. API: PMREMGenerator.
- `webgpu_equirectangular`: equirect panorama via node. API: equirectUV.
- `webgpu_tonemapping`: tone-mapping operators compared on glTF. API: renderer.toneMapping.
- `webgpu_hdr`: HDR output on HDR displays (drawing with half-float canvas). API: WebGPURenderer({ outputType: HalfFloatType }), ColorSpaces.
- `webgpu_furnace_test`: white furnace test for energy conservation. API: PMREMGenerator.
- `webgpu_centroid_sampling`: centroid interpolation on varyings. API: varying(), centroid.
- `webgpu_compile_async`: compileAsync of node materials to avoid hitching. API: renderer.compileAsync.
- `webgpu_materials_node_instance` (r187): `NodeMaterialInstance`, many variants sharing one shader.
- `webgpu_loader_gltf_diffuse_roughness` (r187): glTF with EON `diffuseRoughness`.
- `webgpu_tsl_occlusion_dither` (r187): dither objects that occlude the view.

## 4. Lighting and shadows

`THREE.Lighting` strategies, light types, shadow nodes, light probes.

- `webgpu_lights_physical`: physical light units (intensity in candela/lux).
- `webgpu_lights_phong`: Phong shading with node colors and fog. API: MeshPhongNodeMaterial, lights().
- `webgpu_lights_pointlights`: many point lights over a model. API: PointLight.
- `webgpu_lights_spotlight`: spot light with map/penumbra.
- `webgpu_lights_rectarealight`: RectAreaLight with textures lib. API: RectAreaLightTexturesLib.
- `webgpu_lights_ies_spotlight`: IES profile spotlights. API: IESSpotLight, IESLoader.
- `webgpu_lights_projector`: projected texture/video from a light. API: ProjectorLight.
- `webgpu_lights_selective`: assign subsets of lights to materials. API: material.lightsNode = lights([...]).
- ★ `webgpu_lights_custom`: custom lighting model on top of node lights. API: LightingModel, lights().context. Why read: LightingModel subclass + lights([...]).context({ lightingModel }).
- `webgpu_lights_dynamic`: dynamic lights count without recompiles. API: DynamicLighting (addons/lighting).
- ★ `webgpu_lights_clustered`: clustered forward lighting for thousands of lights. API: ClusteredLighting, renderer.lighting. Why read: renderer.lighting = new ClusteredLighting() for thousands of lights.
- `webgpu_lights_sunlight`: physically placed sun with sky and fog. API: SunLight, SunLightNode, SkyMesh.
- `webgpu_lightprobe`: spherical-harmonics light probe from env. API: LightProbeGenerator, LightProbeHelperGPU.
- `webgpu_lightprobe_cubecamera`: probe baked from a cube camera. API: CubeCamera, LightProbe.
- `webgpu_lightprobes`: probe volume (grid). API: LightProbeGrid, LightProbeGridHelper.
- `webgpu_lightprobes_complex`: multi-room probe volume.
- `webgpu_lightprobes_sponza`: probe volume on Sponza.
- `webgpu_shadowmap`: shadow map basics with noise-displaced geometry.
- `webgpu_shadowmap_array`: tiled shadow map arrays for many lights. API: TileShadowNode, BatchedMesh.
- ★ `webgpu_shadowmap_csm`: cascaded shadow maps. API: CSMShadowNode. Why read: CSMShadowNode on a DirectionalLight (cascades, maxFar, mode).
- `webgpu_shadowmap_opacity`: opacity-aware shadows.
- `webgpu_shadowmap_pointlight`: point light shadow.
- `webgpu_shadowmap_progressive`: progressive lightmap accumulation baked on GPU. API: ProgressiveLightMapGPU.
- `webgpu_shadowmap_vsm`: variance shadow maps. API: shadow.type = VSMShadowMap.
- `webgpu_shadow_contact`: contact shadows via depth render + blur. API: RenderTarget, depthMaterial, gaussianBlur.
- `webgpu_lensflares`: sprite-style lens flares attached to a light. API: LensflareMesh.
- `webgpu_caustics`: refraction caustics shader. API: refract, ShadowNode, MeshPhysicalNodeMaterial.
- `webgpu_occlusion`: occlusion queries driving a custom node. API: mesh.occlusionTest, custom Node.
- `webgpu_clipping`: clipping planes via ClippingGroup. API: ClippingGroup.
- `webgpu_clipping_stencil`: capped clipping with stencil. API: ClippingGroup, stencilWrite.
- `webgpu_lightmap_baking` (r187): bake GI into light maps with `LightMapper`.
- `webgpu_unwrap` (r187): generate `uv1` light-map UVs.
- `webgpu_lights_clustered_city` (r187): clustered lighting at city scale.

## 5. Instancing, batching and performance

- `webgpu_instance_mesh`: InstancedMesh with per-instance nodes. API: range(), InstancedMesh.
- `webgpu_instance_uniform`: per-instance uniform values. API: instance attribute, cubeTexture.
- `webgpu_instance_path`: instances along a path with instanced attributes. API: instancedBufferAttribute.
- `webgpu_instance_sprites`: instanced sprites. API: SpriteNodeMaterial, instancedBufferAttribute.
- `webgpu_instancing_morph`: instanced meshes with morph target animation. API: InstancedMesh.morphTexture.
- `webgpu_skinning_instancing`: many skinned instances. API: InstancedMesh, range.
- `webgpu_mesh_batch`: BatchedMesh with sorting/culling. API: BatchedMesh, perObjectFrustumCulled, sortObjects.
- `webgpu_performance`: scene performance stress with glTF clones. API: compileAsync.
- `webgpu_performance_renderbundle`: render bundles (record draw commands once). API: BundleGroup.

## 6. Loaders, animation and assets

- `webgpu_loader_gltf`: glTF with env and compile. API: GLTFLoader, UltraHDRLoader, compileAsync.
- `webgpu_loader_gltf_anisotropy`: KHR_materials_anisotropy.
- `webgpu_loader_gltf_compressed`: KTX2 + meshopt compressed glTF. API: KTX2Loader, meshopt_decoder.
- `webgpu_loader_gltf_dispersion`: KHR_materials_dispersion.
- `webgpu_loader_gltf_iridescence`: KHR_materials_iridescence.
- `webgpu_loader_gltf_sheen`: KHR_materials_sheen.
- `webgpu_loader_gltf_transmission`: KHR_materials_transmission.
- `webgpu_loader_materialx`: MaterialX files to node materials. API: MaterialXLoader.
- `webgpu_loader_texture_ktx2`: KTX2 compressed textures. API: KTX2Loader.
- `webgpu_tsl_graph`: load TSL graph JSON into materials. API: TSLGraphLoader (addons/inspector).
- `webgpu_animation_retargeting`: retarget animation between skeletons. API: SkeletonUtils.retarget.
- `webgpu_animation_retargeting_readyplayer`: retarget FBX Mixamo clips onto Ready Player Me. API: FBXLoader, SkeletonUtils.
- `webgpu_skinning`: skinned mesh with reflector floor. API: SkinnedMesh, reflector.
- `webgpu_morphtargets`: morph targets.
- `webgpu_morphtargets_face`: face blendshapes (ARKit) with KTX2. API: morphTargetInfluences.
- `webgpu_gaussian_splat`: Gaussian splat rendering (SPLAT, SPZ). API: GaussianSplat, SPLATLoader, SPZLoader.
- `webgpu_sculpt`: GPU sculpting + glTF export. API: Sculptor, GLTFExporter.
- `webgpu_loader_jpegxl` (r187): HDR JPEG XL via `JXLLoader`.

## 7. Textures and render targets

- `webgpu_textures_2d-array`: texture array layers. API: DataArrayTexture, oscTriangle.
- `webgpu_textures_2d-array_compressed`: compressed array. API: KTX2Loader.
- `webgpu_textures_anisotropy`: anisotropic filtering.
- `webgpu_textures_partialupdate`: copyTextureToTexture sub-rect updates. API: copyTextureToTexture.
- `webgpu_texturegather`: textureGather. API: textureGather (WebGPU only).
- `webgpu_texturegrad`: explicit gradients sampling. API: textureGrad.
- `webgpu_rendertarget_2d-array_3d`: RenderTarget array/3D. API: RenderTarget depth layers.
- `webgpu_video_frame`: WebCodecs video frames to texture. API: demuxer_mp4, VideoFrame.
- `webgpu_video_panorama`: 360 video. API: VideoTexture.

## 8. Volumes and raymarching

`VolumeNodeMaterial`, `Raymarching` utilities in `three/addons/tsl/utils/Raymarching.js`.

- ★ `webgpu_volume_cloud`: raymarched cloud from 3D noise. API: RaymarchingBox, texture3D. Why read: RaymarchingBox + texture3D noise (addons/tsl/utils/Raymarching).
- `webgpu_volume_perlin`: raymarched Perlin volume. API: RaymarchingBox, Loop, Break.
- `webgpu_volume_fire`: compute-driven 3D fire simulation, bloom. API: Storage3DTexture, compute, VolumeNodeMaterial, curlNoise.
- ★ `webgpu_volume_lighting`: light shafts in volume from spotlight shadows. API: VolumeNodeMaterial, scatteringNode. Why read: VolumeNodeMaterial.scatteringNode, spotlight shadow sampling, Bayer jitter + blur.
- `webgpu_volume_lighting_rectarea`: volumetric lighting from RectAreaLight. API: RectAreaLightTexturesLib, Bayer.
- `webgpu_volume_lighting_traa`: volumetric lighting resolved by TRAA. API: depthPass, mrt, traa, interleavedGradientNoise.
- `webgpu_volume_caustics`: caustics in volume, refracted light. API: refract, VolumeNodeMaterial, ShadowNode, Bayer.

## 9. Backdrop, reflection, refraction, water, sky

Node materials that read the opaque framebuffer or reflect scene.

- `webgpu_backdrop`: backdropNode with color ops on the opaque scene. API: viewportSharedTexture, hue, posterize, blendOverlay.
- `webgpu_backdrop_area`: depth-limited backdrop blur region. API: hashBlur, viewportLinearDepth, linearDepth.
- ★ `webgpu_backdrop_water`: water with depth fade and refraction. API: viewportSharedTexture, viewportDepthTexture, triplanarTexture. Why read: viewportSharedTexture + viewportLinearDepth + backdropNode refraction and depth fade.
- `webgpu_mirror`: planar mirror. API: reflector().
- `webgpu_reflection`: reflector with blurred recursion and tweens. API: reflector, gaussianBlur.
- `webgpu_reflection_blurred`: blurred reflector. API: reflector, hashBlur.
- `webgpu_reflection_roughness`: roughness-driven reflection blur. API: reflector, textureBicubic.
- `webgpu_refraction`: refraction via viewport sample. API: viewportSharedTexture, viewportSafeUV.
- `webgpu_portal`: render another scene through a portal surface. API: pass(), scene.backgroundNode, mx_worley_noise_float.
- `webgpu_water`: Water2Mesh with bloom/FXAA. API: Water2Mesh, mrt, bloom, fxaa.
- `webgpu_ocean`: WaterMesh + SkyMesh ocean. API: WaterMesh, SkyMesh, PMREM.
- `webgpu_sky`: Sky model + cube camera env. API: SkyMesh, CubeCamera.

## 10. Lines, points, sprites, fog

- `webgpu_lines_fat`: thick lines. API: Line2, Line2NodeMaterial.
- `webgpu_lines_fat_raycasting`: raycasting thick lines. API: Line2, LineSegments2, Raycaster.
- `webgpu_lines_fat_wireframe`: thick wireframe. API: Wireframe, WireframeGeometry2.
- `webgpu_sprites`: sprites with fog and userData. API: SpriteNodeMaterial.
- `webgpu_particles_soft`: soft particles using depth. API: softParticles (addons/tsl/utils).
- `webgpu_custom_fog`: custom fog nodes on terrain with fly camera. API: fog(), densityFogFactor, triNoise3D.
- `webgpu_custom_fog_background`: fog applied to background. API: rangeFogFactor.
- `webgpu_custom_fog_scattering`: scattering fog with blur. API: densityFogFactor, gaussianBlur.
- `webgpu_fog_height`: exponential height fog. API: exponentialHeightFogFactor.

## 11. TSL showcase and procedural

- `webgpu_tsl_earth`: planet with day/night, clouds, atmosphere. API: bumpMap, normalWorldGeometry, cameraPosition.
- `webgpu_tsl_galaxy`: spiral galaxy sprites. API: range, SpriteNodeMaterial.
- `webgpu_tsl_halftone`: halftone stylization in material. API: screenCoordinate, rotate.
- `webgpu_tsl_angular_slicing`: slice a mesh by angle with discard-like logic. API: atan, frontFacing, If.
- `webgpu_tsl_procedural_terrain`: terrain from noise with normals. API: mx_noise_float, Loop.
- ★ `webgpu_tsl_raging_sea`: animated ocean in vertex shader. API: mx_noise_float, Loop. Why read: vertex displacement with mx_noise_float + Loop, normals via transformNormalToView.
- `webgpu_tsl_vfx_flames`: billboard flame sprites. API: billboarding, spherizeUV.
- `webgpu_tsl_vfx_tornado`: tornado effect with bloom. API: BloomNode, atan, luminance.
- `webgpu_tsl_wood`: procedural wood node material. API: WoodNodeMaterial (addons).
- `webgpu_tsl_interoperability`: mix wgslFn with TSL and ShaderMaterial. API: wgslFn, varyingProperty, sampler.
- `webgpu_tsl_editor`: live TSL editor/compile view. API: TSL, wgsl output.
- `webgpu_tsl_transpiler`: GLSL to TSL/WGSL transpiler. API: Transpiler, GLSLDecoder, TSLEncoder, WGSLEncoder.
- `webgpu_shadertoy`: Shadertoy GLSL transpiled to TSL. API: Transpiler, ShaderToyDecoder.
- `webgpu_generator_building`: procedural skyscraper. API: SkyscraperGenerator.
- `webgpu_generator_city`: procedural city with probe grid lighting and bloom. API: CityGenerator, LightProbeGrid, BloomNode.
- `webgpu_geometry_loft`: loft geometry with bump from noise. API: LoftGeometry, bumpMap.
- `webgpu_modifier_curve`: bend text/geometry along a curve on GPU. API: CurveModifierGPU.
- `webgpu_procedural_texture`: rtt-based procedural texture. API: convertToTexture, gaussianBlur.

## 12. WebXR

Use `renderer.xr`; fallback uses `WebGLXRFallback` where WebGPU XR is unavailable.

- `webgpu_xr_cubes`: interactive cubes with controllers. API: XRButton, XRControllerModelFactory, Raycaster.
- `webgpu_xr_rollercoaster`: VR rollercoaster. API: VRButton, multiview.
- `webgpu_xr_native_layers`: XR native layers with interactive UI. API: InteractiveGroup, RollerCoaster, VRButton.
- `webgpu_xr_shadows`: VR with shadows. API: VRButton.

## 13. Cameras, canvas, misc

- `webgpu_camera`: two viewports with different cameras. API: renderer.setViewport.
- `webgpu_camera_array`: ArrayCamera for multi-view (WebGL fallback noted). API: ArrayCamera.
- `webgpu_camera_logarithmicdepthbuffer`: logarithmic depth for huge scale ranges. API: logarithmicDepthBuffer: true.
- `webgpu_reversed_depth_buffer`: reverse-Z depth. API: reversedDepthBuffer: true.
- `webgpu_multiple_canvas`: several renderers/canvases. API: WebGPU.isAvailable.
- `webgpu_multiple_elements`: one renderer, several DOM elements scissor/viewport.
- `webgpu_sandbox`: mixed materials sandbox. API: NodeMaterial variants, KTX2Loader.
- `webgpu_renderer_pathtracer` (r187; was `webgl_renderer_pathtracer`): three-gpu-pathtracer on WebGPU.

## Top 25 index

1. ★ `webgpu_postprocessing`: smallest RenderPipeline setup: pass() + effect nodes + outputNode
1. ★ `webgpu_postprocessing_bloom_emissive`: canonical emissive-MRT selective bloom incl. mrt blend mode + RGBA8 attachment
1. ★ `webgpu_postprocessing_bloom_selective`: per-material material.mrtNode mask, outputColorTransform=false + .renderOutput()
1. ★ `webgpu_postprocessing_ao`: opaque pre-pass (packed normals + velocity), GTAO vs SSAO, builtinAOContext, TRAA
1. ★ `webgpu_postprocessing_ssr_denoise`: full stochastic SSR chain: MRT packing, temporalReproject, recurrentDenoise, setHistory feedback
1. ★ `webgpu_postprocessing_ssgi`: SSGI composite formula (ao * color + diffuse * gi) then TRAA
1. ★ `webgpu_postprocessing_traa`: minimum TRAA setup: velocity MRT + depth + camera
1. ★ `webgpu_postprocessing_fxaa`: color-order lesson: outputColorTransform=false, renderOutput, then FXAA (sRGB)
1. ★ `webgpu_postprocessing_motion_blur`: velocity MRT scaled as shutter, Fn-style motionBlur()
1. ★ `webgpu_deferred`: multi-pass deferred shading with PassNode layers, shared depthTexture, overrideNodes, MRT G-buffer
1. ★ `webgpu_mrt`: MRT basics: output/normal/diffuse/emissive attachments and split-view debug
1. ★ `webgpu_compute_particles`: minimal compute() + instancedArray + SpriteNodeMaterial particle system
1. ★ `webgpu_compute_texture_pingpong`: storageTexture + textureStore with NodeAccess read/write ping-pong
1. ★ `webgpu_compute_reduce`: workgroup/subgroup parallel reduction kernels (subgroupAdd, workgroup memory)
1. ★ `webgpu_struct_drawindirect`: struct() + IndirectStorageBufferAttribute + geometry.setIndirect: GPU-driven draw counts
1. ★ `webgpu_materials`: tour of NodeMaterial customization: wgslFn, triplanar, positionNode/colorNode patterns
1. ★ `webgpu_backdrop_water`: viewportSharedTexture + viewportLinearDepth + backdropNode refraction and depth fade
1. ★ `webgpu_tsl_raging_sea`: vertex displacement with mx_noise_float + Loop, normals via transformNormalToView
1. ★ `webgpu_lights_custom`: LightingModel subclass + lights([...]).context({ lightingModel })
1. ★ `webgpu_shadowmap_csm`: CSMShadowNode on a DirectionalLight (cascades, maxFar, mode)
1. ★ `webgpu_volume_lighting`: VolumeNodeMaterial.scatteringNode, spotlight shadow sampling, Bayer jitter + blur
1. ★ `webgpu_volume_cloud`: RaymarchingBox + texture3D noise (addons/tsl/utils/Raymarching)
1. ★ `webgpu_vxgi`: voxel GI with vxgi() + builtinGIContext + TRAA
1. ★ `webgpu_oit`: oitPass(): weighted-blended order-independent transparency
1. ★ `webgpu_lights_clustered`: renderer.lighting = new ClusteredLighting() for thousands of lights

## See also

- `post-processing-webgpu.md` (effects, MRT, color pipeline)
- `tsl-reference.md`, `tsl-guide/` (functions and concepts)
- `https://threejs.org/examples/?q=webgpu` (searchable index)
