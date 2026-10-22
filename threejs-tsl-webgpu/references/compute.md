# GPGPU / compute shaders with TSL (three.js r186)

When to read this: writing or debugging compute shaders in three.js WebGPURenderer: particle systems, boids, simulations, procedural textures, geometry deformation, reductions, sorting, indirect draws, GPU->CPU readback, and how compute results feed rendering. For renderer setup/init/profiling see `webgpu-renderer.md`; for TSL syntax (`Fn`, `If`, `Loop`, structs, uniforms) see `tsl-reference.md` and `tsl-guide/`. Facts verified against r186 source (`src/nodes/gpgpu/*`, `src/nodes/accessors/Storage*.js`, `src/renderers/common/Renderer.js`, `WebGPUBackend.compute`, `WebGLBackend.compute`) and the `examples/webgpu_compute_*.html` files.

## Contents
1. Mental model: grid, workgroups, instanceIndex
2. Defining kernels: `.compute()`, `computeKernel`, `Fn` params
3. Dispatching: `renderer.compute` semantics, automatic execution, init, uniforms
4. Storage buffers (`instancedArray`, `attributeArray`, `storage`, structs, access)
5. Storage textures (2D, 3D, array; read/write; formats; mips)
6. Atomics
7. Workgroup memory, barriers, builtins, subgroups
8. Indirect draw and indirect dispatch
9. Reading results back to the CPU
10. Feeding compute results into rendering
11. Patterns: init, ping-pong, sorting
12. Worked examples (particles, rain, texture, geometry, boids, water)
13. Compute on the WebGL2 fallback
14. Performance
15. Debugging
16. Pitfalls checklist
17. See also

---

## 1. Mental model

```
dispatch  = grid of workgroups          (WebGPU: dispatchWorkgroups( x, y, z ))
workgroup = block of invocations        (default [64]; [x,y,z], product <= device limits)
invocation = one execution of the shader body
```

- `compute( count, [wgSize] )`: `count` = total invocations. Workgroups dispatched = `ceil( count / (wgX*wgY*wgZ) )`; if that exceeds `device.limits.maxComputeWorkgroupsPerDimension` it is folded into x and y automatically.
- `instanceIndex` (TSL builtin `uint`) is the **linearized global invocation index**, also for 2D/3D workgroups. It is the loop variable of GPGPU: `buffer.element( instanceIndex )`.
- Other builtins (`import { ... } from 'three/tsl'`): `globalId` (uvec3), `localId` (uvec3), `workgroupId` (uvec3), `numWorkgroups` (uvec3), `invocationLocalIndex` (index within workgroup), `subgroupSize`, `invocationSubgroupIndex`.
- Count not a multiple of workgroup size: the last workgroup has extra invocations. For a numeric `count` the compute node injects `if ( instanceIndex >= count ) { return; }` automatically (only when the WGSL builder allows early returns, see barriers, section 7).
- GPU state persists in buffers between dispatches; there is no CPU round trip unless you read back.

## 2. Defining kernels

```js
import * as THREE from 'three/webgpu';
import { Fn, instanceIndex, instancedArray, uniform, If, hash, vec3 } from 'three/tsl';

const count = 100000;
const pos = instancedArray( count, 'vec3' );

const kernel = Fn( () => {                     // body runs per invocation; side effects via assign()/addAssign()
  const p = pos.element( instanceIndex );
  p.addAssign( vec3( 0, 0.01, 0 ) );
} )().compute( count );                        // ComputeNode; default workgroupSize [ 64 ]

kernel.setName( 'Update Particles' );          // label in shader + Inspector (label() is deprecated r179)
```

Forms:
| API | Meaning |
|---|---|
| `fn().compute( count, wg? )` / `compute( node, count, wg? )` | `count` number -> invocation count + auto bounds check. `count` array/non-number -> stored as `dispatchSize` (workgroup counts, no bounds check). `wg` default `[ 64 ]`, 1-3 positive integers, padded to 3 with 1s. |
| `fn().computeKernel( wg? )` / `computeKernel( node, wg? )` | Same node but with **no count**: you must pass the dispatch to `renderer.compute( node, n \| [x,y,z] )`. Invalid sizes log a TSL error. |
| `kernel.setName( s )` | Debug name (shader identifiers, Inspector). |
| `kernel.onInit( ( { renderer } ) => {} )` | Runs once, the first time the node is dispatched, before that dispatch. |
| `Fn( ( { storageTexture } ) => ... )( { storageTexture } )` | Object params (texture example) or array params `Fn( ( [ readTex, writeTex ] ) => ... )( a, b )` (pingpong example) to reuse one kernel for several resources. |

Writing to storage elements: `node.element( i )` returns a proxy; use `.assign()`, `.addAssign()`, `.mulAssign()`, or property assignment on swizzles (`p.x = 1`, `velocity.y = velocity.y.negate().mul( bounce )`). Use `.toVar()` to copy a value into a local before modifying (`const pos = positionStorage.element( i ).toVar()`), `.toConst()` for read-only locals.

Fn `.once()` is **shader-build memoization** (used by `normalLocal`), not "dispatch once". For one-time GPU init use `onInit`, or call `renderer.compute( initNode )` after `await renderer.init()`.

## 3. Dispatching

```js
await renderer.init();                    // required before sync compute()
renderer.compute( kernel );               // one node
renderer.compute( [ kernelA, kernelB ] ); // same command encoder/pass, executed in order
renderer.compute( kernel, 50000 );        // override invocation count (bounds-check still uses kernel.count!)
renderer.compute( kernel, [ 8, 8, 1 ] );  // override WORKGROUP counts (water: 128*128 cells = 8*8 workgroups of 16x16)
renderer.compute( kernel, indirectAttr ); // IndirectStorageBufferAttribute holds x,y,z workgroup counts (WebGPU only)
await renderer.computeAsync( kernel );    // inits renderer first
await renderer.compileComputeAsync( kernel );   // pre-build pipeline to avoid first-dispatch hitch
```

Semantics (source):
- `compute()` before init: `warn` + returns `computeAsync()` Promise. After a device loss it silently returns.
- Each `renderer.compute()` call opens a compute pass, binds, dispatches and **submits its own command buffer** (arrays share one). Writes made by dispatch A are visible to dispatch B called after it; uniforms updated between calls take effect for the later call (`bindings.updateForCompute` per call).
- Order relative to rendering: GPU executes in submit order, so compute called before `renderer.render()` in the same frame feeds that frame's draw.
- `info.compute.calls / frameCalls` count dispatches; many micro-dispatches cost CPU, batch them in an array.
- A `ComputeNode` that is part of a material's node graph is executed automatically **once per frame** (`updateBeforeType = FRAME`, guarded against recursion). Two ways:
  1. Assign the compute node (or an expression derived from it) to a material slot: the Fn's returned value becomes the node's vertex/fragment-stage output.
     ```js
     const computeWave = Fn( () => { currentPos.assign( displaced ); return currentPositions.element( vertexIndex ); } )().compute( count );
     material.positionNode = computeWave;            // dispatches every frame, then reads back in the vertex stage
     material.geometryNode = jelly();                // NodeMaterial.geometryNode: dedicated spot for geometry compute (jelly example)
     ```
  2. Event hook inside a node function (tsl-guide `29-events.md`): `OnBeforeMaterialUpdate( ( { renderer } ) => renderer.compute( update ) )`.
- Manual loop (most common, explicit order):
```js
function animate() { renderer.compute( update ); renderer.render( scene, camera ); }
renderer.setAnimationLoop( animate );
```

Uniforms and time:
```js
const gravity = uniform( - 0.00098 );    // JS side: gravity.value = x (no needsUpdate)
const clickPos = uniform( new THREE.Vector3() );   // clickPos.value.copy( point ); renderer.compute( hit );
import { time, deltaTime } from 'three/tsl';   // frame-updated; deltaTime in seconds
```
- Prefer `deltaTime`/a `uniform` you set per frame (birds example computes dt in JS and clamps to 1 s) over `time` for physics; frame time nodes update once per frame, not per dispatch.
- Uniform values written from JS are applied at the next `renderer.compute()`; to vary a parameter per dispatch within one frame, write it between the calls or store it in a small storage buffer (bitonic sort's `infoStorage`).

Init pattern:
```js
await renderer.init();
renderer.compute( computeInit );                       // before first render; example particles
// or, when the compute node is only reachable through a material (no handle to init):
computeUpdate.onInit( ( { renderer } ) => renderer.compute( computeInit ) );   // geometry / points examples
```
`onInit` is invoked inside `renderer.compute()` when no pipeline exists for that node yet (also after `computeNode.dispose()`).

## 4. Storage buffers

Constructors:
| API | Backing attribute | Use |
|---|---|---|
| `instancedArray( count \| TypedArray, type = 'float' )` | `StorageInstancedBufferAttribute` | one element per instance: particles, instanced meshes, sprites, points |
| `attributeArray( count \| TypedArray, type = 'float' )` | `StorageBufferAttribute` | one element per vertex: geometry deformation, vertex-indexed data |
| `storage( attribute, type?, count? )` | any `BufferAttribute`/`StorageBufferAttribute`/`StorageInstancedBufferAttribute` | wrap an existing attribute (e.g. `geometry.attributes.position` as input) or struct buffers |

- `type`: TSL type string (`'float'`, `'vec2'`, `'vec3'`, `'vec4'`, `'uint'`, `'int'`, `'uvec2'`, `'uvec3'`, `'mat4'`...) or a `struct(...)` type. `instancedArray( new Float32Array(...) )` initializes from data (type defaults to `'float'`; typed array class chosen from `type`: pass `'uint'` with `Uint32Array`, etc.).
- `new THREE.StorageBufferAttribute( count \| TypedArray, itemSize, typeClass = Float32Array )`, `new THREE.StorageInstancedBufferAttribute( ... )`. If `storage()` gets a storage attribute and `type` is null the type is derived from `itemSize`.
- vec3 buffers: items are 3 floats in the CPU array (itemSize 3). WGSL array stride rules are handled by the builder, but **struct** buffers must be sized in multiples of 4 floats (water example comment: "for structs arrays must be enclosed in multiple of 4"; it uses 8 floats per `{ vec3 position, vec2 velocity }`). Non power-of-two buffer sizes are "not well supported" per the storage_buffer example comment; prefer sizes that are multiples of the workgroup size.
- Buffer memory lives on the GPU; the CPU `array` is only the initial upload. Initial data comes from the typed array / constructor; keep per-frame updates on the GPU.

Node methods (`StorageBufferNode`):
| method | effect |
|---|---|
| `.element( indexNode )` | element access (read & write in compute) |
| `.toReadOnly()` / `.setAccess( NodeAccess.READ_ONLY )` | `var<storage, read>`; `NodeAccess` is exported from `three/tsl` (`READ_ONLY`, `WRITE_ONLY`, `READ_WRITE`) |
| `.toAtomic()` / `.setAtomic( true )` | atomic element type (section 6) |
| `.toAttribute()` | `bufferAttribute( value )` + varying: use as a **vertex attribute** in render |
| `.setPBO( true )` | WebGL fallback only: expose as texture for read/readback (section 13) |
| `.setName( s )` | label |
| `.value` | the underlying attribute (pass to `renderer.getArrayBufferAsync`) |
| `.get( 'member' )` (on an element of a struct buffer) | struct member access |

Access in non-compute stages is forced **read-only** by the WGSL builder (atomics: read-write only in fragment; in vertex they warn and become read-only). You cannot write storage buffers from vertex/fragment shaders in this API.

Structs in storage:
```js
const Duck = struct( { position: 'vec3', velocity: 'vec2' } );
const ducks = instancedArray( data /* Float32Array, 8 floats per element */, Duck ).setName( 'DuckInstanceData' );
const p = ducks.element( instanceIndex ).get( 'position' ).toVar();
ducks.element( instanceIndex ).get( 'velocity' ).assign( v );
// atomic members: struct( { count: { type: 'uint', atomic: true } }, 'DrawBuffer' )
```

Typed-array size: element count * `itemSize`; `instancedArray( 64, 'vec3' )` allocates `64 * 3` floats.

## 5. Storage textures

```js
const tex = new THREE.StorageTexture( 512, 512 );          // 2D;  Storage3DTexture( w, h, d );  StorageArrayTexture( w, h, d )
tex.type = THREE.HalfFloatType;                            // pick before first use; default type/format -> rgba8unorm-like
// tex.mipmapsAutoUpdate = true (default): mips regenerated after compute writes; set false to write mips yourself
// tex.setSize( w, h ) disposes/recreates GPU texture when the size changes
```
Minification/magnification default `LinearFilter` (generateMipmaps off unless you set a mipmap `minFilter`; the texture example has a commented `LinearMipMapLinearFilter`).

Write / read:
```js
import { textureStore, storageTexture, storageTexture3D, texture, texture3D, uvec2, ivec2, vec4, NodeAccess } from 'three/tsl';

// write (statement)
textureStore( tex, uvec2( x, y ), vec4( r, g, b, 1 ) ).toWriteOnly();

// explicit access nodes (needed to read and write the same texture in different kernels)
const wr = storageTexture( pingTex ).setAccess( NodeAccess.WRITE_ONLY );
const rd = storageTexture( pingTex ).setAccess( NodeAccess.READ_ONLY );
const c  = rd.load( ivec2( x, y ) );                      // texel load (no filtering)
textureStore( wr, ivec2( x, y ), vec4( c.rgb.mul( 1.05 ), 1 ) );

// 3D: textureStore( storage3D, vec3( x, y, z ), value ); sample with texture3D( storage3D, null, 0 )
// sample for rendering like any texture:
material.colorNode = texture( tex );     // or MeshBasicMaterial({ map: tex })
```
- `StorageTextureNode` methods: `.toWriteOnly() .toReadOnly() .toReadWrite() .setAccess() .setMipLevel( l ) .store( uv, value ) .load()`. `textureStore( texOrNode, uv, value )` with a raw texture creates the node and adds it as a statement.
- WGSL type emitted is `texture_storage_2d[_array]|3d<format, access>`; format comes from the texture's `format`/`type`. Read-write storage textures are limited by WebGPU format support; the pingpong example avoids it by using two textures (one write-only, one read-only each) and alternating.
- Storage textures are WebGPU-backend-only (API docs: "can only be used with WebGPURenderer and a WebGPU backend").
- Index math for 2D images with 1D dispatch: `x = instanceIndex.mod( width ); y = instanceIndex.div( width );` and `.compute( width * height )` (texture example), or 2D workgroups `[ 16, 16 ]` with `localId`/`workgroupId`.

## 6. Atomics

```js
import { atomicAdd, atomicSub, atomicMax, atomicMin, atomicAnd, atomicOr, atomicXor, atomicLoad, atomicStore, uint, int } from 'three/tsl';

const counter = instancedArray( 1, 'uint' ).toAtomic();    // or storage( attr, 'uint', 1 ).toAtomic()
const prev = atomicAdd( counter.element( 0 ), 1 );          // returns the previous value
atomicStore( counter.element( 0 ), uint( 0 ) );             // reset (do it in a separate dispatch from accumulation)
const total = atomicLoad( counter.element( 0 ) );
```
- WebGPU atomics are **32-bit integer only** (`int`/`uint`). For floats use fixed point: scale by a large factor, `atomicAdd` the int, divide on read (fluid example `encodeFixedPoint/decodeFixedPoint`).
- Struct members: `struct( { x: { type: 'int', atomic: true }, mass: { type: 'int', atomic: true } } )`, access `cell.get( 'x' )`.
- Workgroup atomics: `workgroupArray( 'uint', n ).toAtomic()` (`WorkgroupInfoNode.toAtomic()`).
- Fragment stage may use atomics read-write; vertex stage cannot.
- Not available on WebGL fallback.
- Atomic functions: `atomicAdd, atomicSub, atomicMax, atomicMin, atomicAnd, atomicOr, atomicXor, atomicLoad, atomicStore` (plus generic `atomicFunc( method, pointer, value )`). See rasterizer examples (`atomicMax` for depth+payload packing, work queues with `atomicAdd` counters).

## 7. Workgroup memory, barriers, builtins, subgroups

```js
import { workgroupArray, workgroupBarrier, storageBarrier, textureBarrier, localId, workgroupId, invocationLocalIndex } from 'three/tsl';

const tile = workgroupArray( 'vec3', 256 );              // shared on-chip memory, per workgroup; 'float','uint','vec3',...
tile.element( invocationLocalIndex ).assign( value );
workgroupBarrier();                                      // all invocations of the workgroup reach here before any proceeds
const other = tile.element( uint( 255 ).sub( invocationLocalIndex ) );
```
- Barriers are **statements** (`.toStack()` already applied): `workgroupBarrier()`, `storageBarrier()` (storage buffers visible across the workgroup), `textureBarrier()`.
- **Gotcha**: any barrier in the kernel sets `builder.allowEarlyReturns = false` and `allowGlobalVariables = false`. WGSL needs uniform control flow around barriers, so the automatic `if ( instanceIndex >= count ) return;` guard is dropped. Make `count` a multiple of the workgroup size, or guard individual reads/writes with `If( instanceIndex.lessThan( count ), ... )` but keep barriers outside the `If`.
- Barriers only exist on the compute stage (error otherwise) and become comments on the WebGL backend (no effect).
- Typical reduction: each invocation loads into `workgroupArray`, loop `k = wg/2; k > 0; k /= 2` with `If( lid.lessThan( k ), ... ); workgroupBarrier();`, thread 0 writes `workgroupSums.element( workgroupId.x )` (webgpu_compute_reduce.html levels 2-4).

Subgroups (wave intrinsics; need device feature `subgroups`, check `renderer.hasFeature( 'subgroups' )`):
`subgroupElect, subgroupBallot, subgroupAdd, subgroupInclusiveAdd, subgroupExclusiveAdd, subgroupMul, subgroupInclusiveMul, subgroupExclusiveMul, subgroupAnd, subgroupOr, subgroupXor, subgroupMin, subgroupMax, subgroupAll, subgroupAny, subgroupBroadcastFirst, subgroupBroadcast( v, id ), subgroupShuffle( v, i ), subgroupShuffleXor, subgroupShuffleUp, subgroupShuffleDown, quadBroadcast, quadSwapX, quadSwapY, quadSwapDiagonal` plus builtins `subgroupSize`, `invocationSubgroupIndex`. Subgroup size is hardware dependent (do not assume 32); the reduce example derives workgroup/subgroup layouts and notes `subgroupAdd` implies sync among the subgroup lanes. Put `subgroupAdd(...)` results in a `.toVar()` before a conditional, so it executes in uniform control flow (reduce example comment).

## 8. Indirect draw and indirect dispatch

Indirect draw (GPU decides instance/vertex count): `IndirectStorageBufferAttribute` + `geometry.setIndirect( attr, byteOffset | byteOffsets[] )`.

```js
// non-indexed: 4 uint32 (vertexCount, instanceCount, firstVertex, firstInstance); example buffer uses 5 uints with a struct incl. trailing offset
// indexed (webgpu_particles.html comment): 5 uint32 = indexCount, instanceCount, firstIndex, baseVertex, firstInstance
const drawBuffer = new THREE.IndirectStorageBufferAttribute( new Uint32Array( 5 ), 5 );
geometry.setIndirect( drawBuffer );

const DrawStruct = struct( { vertexCount: 'uint', instanceCount: { type: 'uint', atomic: true }, firstVertex: 'uint', firstInstance: 'uint', offset: 'uint' }, 'DrawBuffer' );
const draw = storage( drawBuffer, DrawStruct, drawBuffer.count );

const computeDraw = Fn( () => { atomicStore( draw.get( 'instanceCount' ), visibleCount ); } )().compute( 1 );
renderer.compute( computeDraw );     // then renderer.render(): drawIndirect( buffer, offset ) per offset
```
Array offsets issue multiple indirect draws. Indirect dispatch: pass the attribute as 2nd arg to `renderer.compute( node, indirectAttr )` (`dispatchWorkgroupsIndirect( buffer, 0 )`). Both WebGPU only; WebGL fallback warns and uses `node.count`. Examples: webgpu_struct_drawindirect.html, webgpu_particles.html, webgpu_compute_rasterizer(.ibl).html.

## 9. Reading results back

```js
renderer.compute( kernel );
const buf = await renderer.getArrayBufferAsync( waveArray.value );       // ArrayBuffer; value = underlying attribute
const wave = new Float32Array( buf );                                    // choose the matching typed array yourself
// reusable mapped staging buffer (signature: getArrayBufferAsync( attribute, target?, offset = 0, count = -1 ))
const rb = new THREE.ReadbackBuffer( attr.array.byteLength );   // ctor arg = max byte length (number)
await renderer.getArrayBufferAsync( attr, rb );                 // resolves with rb itself; data in rb.buffer (mapped ArrayBuffer)
const u32 = new Uint32Array( rb.buffer );
rb.release();   // unmap: rb.buffer becomes null. MUST be called before rb is used for another readback (else it throws)
rb.dispose();   // when done (also removes it from renderer.info.memory.readbackBuffers)
// target as plain ArrayBuffer: data is copied into it (must be large enough)
// partial: offset/count are BYTES and multiples of 4
```
- Readback copies GPU->staging->CPU and awaits `mapAsync`: stalls; do it on demand (audio example computes once then plays), not each frame. For per-frame data prefer keeping the data on the GPU and rendering from it.
- Pass the attribute (`node.value`), not the node. The copy is queued after previously submitted compute work (submit order).
- Doc/example discrepancy: `webgpu_compute_reduce.html` calls `new THREE.ReadbackBuffer( selectedBuffer.value )` and `getArrayBufferAsync( readbackBuffer )` without the attribute argument; that does not match the r186 signature/doc (`ReadbackBuffer( maxByteLength: number )`). Follow the signature above.
- On WebGL fallback the storage node needs `.setPBO( true )` for this to work (audio/cloth/birds comments).
- Textures: `renderer.readRenderTargetPixelsAsync( renderTarget, ... )` is for RenderTargets; for StorageTextures copy into a RenderTarget texture first or sample them into a render pass.

## 10. Feeding compute results into rendering

Per-instance data (buffers from `instancedArray`):
```js
// Sprite / SpriteNodeMaterial: one sprite per particle
const material = new THREE.SpriteNodeMaterial();
material.positionNode = positions.toAttribute();      // vertex attribute path (no storage binding in vertex stage)
material.colorNode = uv().mul( colors.element( instanceIndex ) );   // storage read in fragment stage (read-only)
const sprite = new THREE.Sprite( material );
sprite.count = particleCount;                         // instance count lives on the object (Object3D.count for Sprite/Mesh/Points)
sprite.frustumCulled = false;                         // CPU bounding volume knows nothing of GPU-moved positions
scene.add( sprite );

// Mesh instanced via .count (rain, ripples): offset geometry by per-instance position
material.positionNode = positionGeometry.add( positionBuffer.toAttribute() );
mesh.count = N;

// Points: one vertex, drawn as N instances
geometry.setAttribute( 'position', new THREE.BufferAttribute( new Float32Array( 3 ), 3 ) );
geometry.drawRange.count = 1;
pointsMaterial.positionNode = particleArray.element( instanceIndex );   // PointsNodeMaterial
points.count = N;

// InstancedMesh with full vertex control (birds): override clip-space output
birdMaterial.vertexNode = birdVertexTSL();   // reads positionStorage.element( instanceIndex ) in the vertex stage
const m = new THREE.InstancedMesh( geometry, birdMaterial, BIRDS ); m.frustumCulled = false;

// Per-vertex data (attributeArray): deformation
geometry.setAttribute( 'storagePosition', positionStorageBufferAttribute );
material.positionNode = attribute( 'storagePosition' );
```
`.toAttribute()` binds the buffer as a vertex buffer (instance-stepped when it came from `instancedArray`/`StorageInstancedBufferAttribute`). `.element( instanceIndex )` in a vertex shader binds it as a read-only **storage buffer in the vertex stage**, which counts against `maxStorageBuffersInVertexStage`; the official examples that do this request it: birds 3, water 2, cloth/points/fluid 1 (`new WebGPURenderer( { requiredLimits: { maxStorageBuffersInVertexStage: N } } )`). `toAttribute()` examples (particles, rain) do not.

Other notes:
- `Mesh.count`/`Sprite.count`/`Points.count` is set manually; `InstancedMesh` takes count in the constructor and `.count` can be lowered to draw fewer.
- Lighting/normals from deformed geometry: recompute normals in `normalNode` (water example derives normals from neighbor heights).
- Dispatch compute before `render()` each frame; compute with embedded-in-material nodes runs automatically.
- Storage textures sample via `texture( storageTex )`; do not sample a storage texture in the same kernel that writes it.

## 11. Patterns

Double buffering / ping-pong:
```js
const A = instancedArray( data, 'float' ), B = instancedArray( new Float32Array( data ), 'float' );
const step = ( rd, wr ) => Fn( () => { wr.element( instanceIndex ).assign( f( rd.element( instanceIndex ) ) ); } )().compute( N, [ 16, 16 ] );
const AtoB = step( A, B ).setName( 'A->B' ), BtoA = step( B, A ).setName( 'B->A' );
const readFromA = uniform( 1 );                        // render side chooses the freshest buffer
material.positionNode = select( readFromA, A.element( vertexIndex ), B.element( vertexIndex ) );  // vec3(positionLocal.xy, h)
// per frame: renderer.compute( phase ? AtoB : BtoA ); readFromA.value = phase ? 0 : 1; phase = ! phase;
```
Never read and write the same element of the same buffer at neighboring indices in one dispatch (race): use two buffers (A->B) or a `prev` buffer (water keeps `PrevHeight` as third buffer). Textures: two `StorageTexture`s alternating, set `material.map = ...` each frame (pingpong example); read via `readTex.load(...)`.

Sorting (addons, `three/addons/gpgpu/*`):
```js
import { BitonicSort } from 'three/addons/gpgpu/BitonicSort.js';
const dataBuffer = storage( new THREE.StorageInstancedBufferAttribute( uint32Array, 1 ), 'uint', size ).setPBO( true );
const sorter = new BitonicSort( renderer, dataBuffer, { workgroupSize: 64 } );   // workgroupSize <= count/2
sorter.compute( renderer );        // full sort, stepCount dispatches
sorter.computeStep( renderer );    // one network step per call (visualize; bitonic example)
sorter.stepCount; sorter.infoStorage;   // debug: [ algo, swapSpan, maxSwapSpan ]
```
Bitonic uses local (workgroup shared) passes + global flip/disperse passes with a temp buffer, requires WebGPU (barriers) and in-place semantic on `dataBuffer`; the example sorts 16384 elements (bitonic networks are power-of-two by construction; this is not asserted in source). `getBitonicFlipIndices` / `getBitonicDisperseIndices` TSL helpers are exported for custom variants.

```js
import { CountingSort } from 'three/addons/gpgpu/CountingSort.js';
const sort = new CountingSort( count, { binCount: 4096, workgroupSize: 256 } );
sort.setBinNode( () => /* Node<uint> in [0,binCount) from instanceIndex, e.g. quantized depth */ );
sort.compute( renderer );              // reset, histogram (atomics), prefix sum, scatter
sort.orderRead;                         // StorageBufferNode: permutation of [0,count) ordered by bin (approximate within a bin)
sort.computeCPU( ( i ) => bin );        // CPU fallback for backends w/o compute; sort.enableWebGLBuffers() for WebGL path
```
Used by `examples/jsm/objects/GaussianSplat.js`. `SortUtils.radixSort( arr, opt )` (`three/addons/utils/SortUtils.js`) is a CPU radix sort of uint32 keys.

Reduction (sum/min/max): multi-level: per-workgroup partial sums into `workgroupSums`, then a second dispatch over the partials (reduce example: 6 variants from naive to subgroup-optimized, with `trackTimestamp` benchmarking).

## 12. Worked examples (condensed from official examples)

### 12.1 Particles with velocity, gravity, floor bounce, hit impulse (webgpu_compute_particles.html)
```js
import * as THREE from 'three/webgpu';
import { Fn, If, uniform, float, uv, vec3, hash, shapeCircle, instancedArray, instanceIndex } from 'three/tsl';

const N = 200000, gravity = uniform( - 0.00098 ), bounce = uniform( 0.8 ), friction = uniform( 0.99 ), size = uniform( 0.12 ), hitPos = uniform( new THREE.Vector3() );
const positions = instancedArray( N, 'vec3' ), velocities = instancedArray( N, 'vec3' ), colors = instancedArray( N, 'vec3' );

const side = Math.sqrt( N ), offset = float( side / 2 );
const init = Fn( () => {
  const p = positions.element( instanceIndex ), c = colors.element( instanceIndex );
  p.x = offset.sub( instanceIndex.mod( side ) ).mul( 0.2 );          // grid layout
  p.z = offset.sub( instanceIndex.div( side ) ).mul( 0.2 );
  c.x = hash( instanceIndex ); c.y = hash( instanceIndex.add( 2 ) );
} )().compute( N ).setName( 'Init Particles' );

const update = Fn( () => {
  const p = positions.element( instanceIndex ), v = velocities.element( instanceIndex );
  v.addAssign( vec3( 0, gravity, 0 ) ); p.addAssign( v ); v.mulAssign( friction );
  If( p.y.lessThan( 0 ), () => {                                      // floor
    p.y = 0; v.y = v.y.negate().mul( bounce ); v.x = v.x.mul( 0.9 ); v.z = v.z.mul( 0.9 );
    // reset-on-rest variant (tsl-guide compute-stage): If( v.y.abs().lessThan( 0.02 ), () => { respawn p, v with hash( instanceIndex.add( time ) ) } )
  } );
} )().compute( N ).setName( 'Update Particles' );

const hit = Fn( () => {                                               // pointer impulse, dispatched on pointermove
  const p = positions.element( instanceIndex ), v = velocities.element( instanceIndex );
  const d = p.distance( hitPos ), dir = p.sub( hitPos ).normalize();
  v.addAssign( dir.mul( float( 3 ).sub( d ).max( 0 ).mul( 0.01 ).mul( hash( instanceIndex ).mul( 1.5 ).add( 0.5 ) ) ) );
} )().compute( N ).setName( 'Hit Particles' );

const material = new THREE.SpriteNodeMaterial();
material.positionNode = positions.toAttribute(); material.scaleNode = size;
material.colorNode = uv().mul( colors.element( instanceIndex ) ); material.opacityNode = shapeCircle();
material.alphaToCoverage = true; material.transparent = true;
const sprite = new THREE.Sprite( material ); sprite.count = N; sprite.frustumCulled = false; scene.add( sprite );

await renderer.init(); renderer.compute( init );
renderer.setAnimationLoop( () => { renderer.compute( update ); renderer.render( scene, camera ); } );
// pointermove: hitPos.value.copy( raycastPoint ); renderer.compute( hit );
```
Notes: `hash( instanceIndex )` is the GPU RNG (deterministic per index; add `time` or a `uniform` seed to vary). Velocity integration is per-frame, not dt-scaled; multiply by `deltaTime` for frame-rate independence.

### 12.2 Rain with surface collision via top-down height map (webgpu_compute_particles_rain.html)
The example does not read scene depth; it renders the colliders' world positions from above into a float render target with an override material, then each drop samples that map.
```js
const collisionCamera = new THREE.OrthographicCamera( -50, 50, 50, -50, 0.1, 50 );
collisionCamera.position.y = 50; collisionCamera.lookAt( 0, 0, 0 );
collisionCamera.layers.disableAll(); collisionCamera.layers.enable( 1 );            // only objects on layer 1 are colliders
const collisionRT = new THREE.RenderTarget( 1024, 1024 );
collisionRT.texture.type = THREE.HalfFloatType;
collisionRT.texture.magFilter = collisionRT.texture.minFilter = THREE.NearestFilter; collisionRT.texture.generateMipmaps = false;
const collisionMat = new THREE.MeshBasicNodeMaterial(); collisionMat.colorNode = positionWorld;

const toCoord = ( xz ) => xz.add( 50 ).div( 100 );
const update = Fn( () => {
  const pos = positionBuffer.element( instanceIndex ), vel = velocityBuffer.element( instanceIndex );
  const ripplePos = ripplePositionBuffer.element( instanceIndex ), rippleTime = rippleTimeBuffer.element( instanceIndex );
  pos.addAssign( vel ); rippleTime.x = rippleTime.x.add( deltaTime.mul( 4 ) );
  const floorY = texture( collisionRT.texture, toCoord( pos.xz ) ).y.add( 0.05 );   // height under this drop
  If( pos.y.add( - 0.9 ).lessThan( floorY ), () => {
    pos.y = 25; ripplePos.xz = pos.xz; ripplePos.y = floorY; rippleTime.x = 1;      // spawn ripple, respawn drop elsewhere
    pos.x = hash( instanceIndex.add( time ) ).mul( 100 ).add( -50 );
    pos.z = hash( instanceIndex.add( time.add( randUint() ) ) ).mul( 100 ).add( -50 );
  } );
} )().compute( MAX ).setName( 'Particles' );

// per frame
scene.overrideMaterial = collisionMat; renderer.setRenderTarget( collisionRT ); renderer.render( scene, collisionCamera );
renderer.compute( update );
scene.overrideMaterial = null; renderer.setRenderTarget( null ); renderer.render( scene, camera );
```
Drops are a plane mesh with `rainMaterial.positionNode = positionGeometry.add( positionBuffer.toAttribute() )`, `vertexNode = billboarding( { horizontalRotation: true } )`, `mesh.count = N`. Sampling a render target texture inside compute uses the same `texture( rt.texture, uv )` node. The float height map needs `Nearest` filtering and no mips.

### 12.3 Procedural texture via storage texture (webgpu_compute_texture.html, ..._pingpong.html)
```js
const W = 512, H = 512;
const tex = new THREE.StorageTexture( W, H );                       // tex.type = THREE.HalfFloatType for HDR / negative values
const gen = Fn( ( { storageTexture } ) => {
  const x = float( instanceIndex.mod( W ) ).div( 50 ), y = float( instanceIndex.div( W ) ).div( 50 );
  const v = x.sin().add( y.sin(), x.add( y ).sin(), x.mul( x ).add( y.mul( y ) ).sqrt().add( 5 ).sin() );
  textureStore( storageTexture, uvec2( instanceIndex.mod( W ), instanceIndex.div( W ) ),
    vec4( v.sin(), v.add( Math.PI ).sin(), v.add( Math.PI ).sub( 0.5 ).sin(), 1 ) ).toWriteOnly();
} );
const node = gen( { storageTexture: tex } ).compute( W * H );
const mat = new THREE.MeshBasicNodeMaterial(); mat.colorNode = texture( tex );
await renderer.init(); renderer.compute( node );                    // static: once. Animated: dispatch per frame
```
Ping-pong blur (pingpong example): two textures, `writePing/readPing/writePong/readPong` nodes with explicit `NodeAccess`, `readTex.load( ivec2 )` for 5 taps, `compute( W * H )`, alternate nodes and `material.map` every frame; reseed with a `uniform( vec2 )` seed. 3D variant: `Storage3DTexture( s, s, s )`, `textureStore( tex3d, vec3( x, y, z ), v )`, render with `texture3D( tex3d, null, 0 )` (webgpu_compute_texture_3d.html).

### 12.4 Geometry deformation: jelly (webgpu_compute_geometry.html)
```js
const jelly = Fn( ( { renderer, geometry, object } ) => {              // build-time context: renderer, geometry, object
  const count = geometry.attributes.position.count;
  const posAttr = new THREE.StorageBufferAttribute( count, 3 ), speedAttr = new THREE.StorageBufferAttribute( count, 3 );
  geometry.setAttribute( 'storagePosition', posAttr );                 // render reads this attribute
  const base = storage( geometry.attributes.position, 'vec3', count ).element( instanceIndex );
  const cur = storage( posAttr, 'vec3', count ).element( instanceIndex ), speed = storage( speedAttr, 'vec3', count ).element( instanceIndex );

  const init = Fn( () => { cur.assign( base ); } )().compute( count );
  const update = Fn( () => {
    If( pointer.w.equal( 1 ), () => {                                   // brush: pull vertices toward the pointer
      const wp = objectWorldMatrix( object ).mul( cur );
      cur.addAssign( pointer.xyz.sub( wp ).normalize().mul( brushSize.sub( wp.distance( pointer.xyz ) ).max( 0 ).mul( brushStrength ) ) );
    } );
    const d = base.distance( cur );
    speed.addAssign( elasticity.mul( d ).mul( base.sub( cur ) ) );      // spring back to the base shape
    speed.mulAssign( damping ); cur.addAssign( speed );
  } )().compute( count ).setName( 'Update Jelly' );
  update.onInit( () => renderer.compute( init ) );                      // seed storage from base positions
  return update;
} );
const material = new THREE.MeshNormalNodeMaterial();
material.geometryNode = jelly();                                        // dispatched automatically each frame
material.positionNode = attribute( 'storagePosition' );
```
Key: `geometryNode` is the intended hook for geometry-modifying compute; it is attached through `.bypass()` so it runs before the vertex stage reads `storagePosition`. Normals are not recomputed here (`MeshNormalNodeMaterial`); add a `normalNode` if lit.

### 12.5 Boids with neighbor loops (webgpu_compute_birds.html, 8192 birds)
```js
const renderer = new THREE.WebGPURenderer( { antialias: true, requiredLimits: { maxStorageBuffersInVertexStage: 3 } } );
const pos = instancedArray( posArray, 'vec3' ).setName( 'positionStorage' ).setPBO( true );   // PBO only matters for WebGL fallback
const vel = instancedArray( velArray, 'vec3' ).setName( 'velocityStorage' ).setPBO( true );
const phase = instancedArray( phaseArray, 'float' ).setName( 'phaseStorage' ).setPBO( true );
const U = { separation: uniform( 15 ), alignment: uniform( 20 ), cohesion: uniform( 20 ), deltaTime: uniform( 0 ), rayOrigin: uniform( new THREE.Vector3() ), rayDirection: uniform( new THREE.Vector3() ) };

const computeVelocity = Fn( () => {
  const { separation, alignment, cohesion, deltaTime } = U;
  const zoneRadius = separation.add( alignment ).add( cohesion ).toConst();
  const sepThresh = separation.div( zoneRadius ).toConst(), alignThresh = separation.add( alignment ).div( zoneRadius ).toConst();
  const zoneSq = zoneRadius.mul( zoneRadius ).toConst();
  const me = instanceIndex.toConst( 'birdIndex' );
  const position = pos.element( me ).toVar(), velocity = vel.element( me ).toVar();   // cache outside the loop
  Loop( { start: uint( 0 ), end: uint( BIRDS ), type: 'uint', condition: '<' }, ( { i } ) => {   // O(N^2) all-pairs
    If( i.equal( me ), () => { Continue(); } );
    const dir = pos.element( i ).sub( position ), dist = length( dir );
    If( dist.lessThan( 0.0001 ), () => { Continue(); } );
    const dSq = dist.mul( dist );
    If( dSq.greaterThan( zoneSq ), () => { Continue(); } );
    const percent = dSq.div( zoneSq );
    If( percent.lessThan( sepThresh ), () => { velocity.subAssign( normalize( dir ).mul( sepThresh.div( percent ).sub( 1 ).mul( deltaTime ) ) ); } )
      .ElseIf( percent.lessThan( alignThresh ), () => { /* align: velocity += normalize( vel.element( i ) ) * w * dt */ } )
      .Else( () => { /* cohesion: velocity += normalize( dir ) * w * dt */ } );
  } );
  If( length( velocity ).greaterThan( limit ), () => { velocity.assign( normalize( velocity ).mul( limit ) ); } );
  vel.element( me ).assign( velocity );                                   // single write at the end
} )().compute( BIRDS ).setName( 'Birds Velocity' );

const computePosition = Fn( () => {
  pos.element( instanceIndex ).addAssign( vel.element( instanceIndex ).mul( U.deltaTime ).mul( 15 ) );
  // phase.element( instanceIndex ).assign( phase.add( dt ... ).mod( 62.83 ) )
} )().compute( BIRDS ).setName( 'Birds Position' );

// render: InstancedMesh + NodeMaterial.vertexNode reads pos/vel/phase with element( instanceIndex ) in the vertex stage
birdMaterial.vertexNode = birdVertexTSL();           // returns cameraProjectionMatrix * cameraViewMatrix * finalVert
// loop: renderer.compute( computeVelocity ); renderer.compute( computePosition ); renderer.render( scene, camera );
```
Gotchas from the source comments: negate TSL nodes with `.negate()` / `negate()` (JS unary `-` yields NaN); the all-pairs loop reads `pos` while other invocations in the same dispatch are not writing it (positions are only written by the second kernel), which is why two kernels are used. Example is marked `TODO: Fix example with WebGL backend`. For > ~10-20k agents replace all-pairs with a spatial grid built with atomics (see fluid example) or sort.

### 12.6 Water heightfield with ping-pong buffers and 2D workgroups (webgpu_compute_water.html)
```js
const W = 128;
const A = instancedArray( heightArray ).setName( 'HeightA' ), B = instancedArray( new Float32Array( heightArray ) ).setName( 'HeightB' );
const prev = instancedArray( prevArray ).setName( 'PrevHeight' );
const readFromA = uniform( 1 );

const neighbors = ( index, store ) => {                                   // clamp-to-edge emulation, cast to int before subtraction
  const x = int( index.mod( W ) ), y = int( index.div( W ) );
  const iW = max( 0, x.sub( 1 ) ), iE = min( x.add( 1 ), W - 1 ), iS = max( 0, y.sub( 1 ) ), iN = min( y.add( 1 ), W - 1 );
  return [ y.mul( W ).add( iW ), y.mul( W ).add( iE ), iS.mul( W ).add( x ), iN.mul( W ).add( x ) ].map( i => store.element( i ) );
};
const makeStep = ( rd, wr ) => Fn( () => {
  const h = rd.element( instanceIndex ).toVar(), ph = prev.element( instanceIndex ).toVar();
  const [ w, e, s, n ] = neighbors( instanceIndex, rd );
  const nh = n.add( s ).add( e ).add( w ).mul( 0.5 ).sub( ph ).mul( viscosity );        // wave equation
  // + mouse ripple using globalId.x / globalId.y -> uv, cos( clamp( dist * PI / size ) ) * deep * speed
  prev.element( instanceIndex ).assign( h ); wr.element( instanceIndex ).assign( nh );
} )().compute( W * W, [ 16, 16 ] );
const AtoB = makeStep( A, B ).setName( 'Update Height A->B' ), BtoA = makeStep( B, A ).setName( 'Update Height B->A' );

// render: positionNode = vec3( positionLocal.x, positionLocal.y, select( readFromA, A.element( vertexIndex ), B.element( vertexIndex ) ) )
// frame: renderer.compute( pingPong === 0 ? AtoB : BtoA, [ 8, 8, 1 ] ); readFromA.value = pingPong === 0 ? 0 : 1; pingPong = 1 - pingPong;
// extra kernel: 100 floating "ducks" in a struct storage buffer sample the freshest height & normals; compute( NUM_DUCKS )
```
Notes: `[8,8,1]` here is a dispatch of 8x8 **workgroups** of 16x16 (=128x128). Because the nodes are `compute( W*W, [16,16] )`, the shader still contains the numeric-count guard. `vertexIndex` doubles as the cell index because the plane has `WIDTH x WIDTH` vertices. Requested limit: `maxStorageBuffersInVertexStage: 2`.

## 13. Compute on the WebGL2 fallback

Supported via emulation in `WebGLBackend.compute`: the kernel is compiled as a vertex shader, drawn as `POINTS` under `RASTERIZER_DISCARD` with transform feedback writing output buffers, then buffers are swapped (ping-pong inside the backend; texture PBOs refreshed by `copyBufferToTexture`).

Works: 1D numeric `count` kernels over storage buffers, `instanceIndex`, uniforms, `setPBO( true )` reads, `getArrayBufferAsync`, `trackTimestamp` (disjoint timer query).
Does not work / ignored:
- Array dispatch and `IndirectStorageBufferAttribute` (warn once; uses `node.count`).
- Storage textures (`StorageTexture`, `Storage3DTexture`, `StorageArrayTexture`, `textureStore`).
- Atomics (no GLSL path), `workgroupArray` shared memory, barriers (emitted as comments, so algorithms relying on them are wrong), subgroup ops, 
- `IndirectStorageBufferAttribute`, `geometry.setIndirect`.
- Several official compute examples are explicitly flagged `TODO: Fix example with WebGL backend` (birds, water); others call `WebGPU.isAvailable()` and bail out (texture, bitonic, reduce).

Practical rules: feature-detect with `renderer.backend.isWebGPUBackend`; give storage nodes read by other stages or by readback `.setPBO( true )` (harmless on WebGPU); keep a CPU fallback (`CountingSort.computeCPU( binFn )` ships one); or refuse to start compute-heavy features on the fallback.

## 14. Performance

- Workgroup size: default 64 is a safe 1D choice; use 128-256 for large 1D kernels (counting sort default 256; rasterizer clears use 256); use 2D tiles (8x8, 16x16) for image/grid kernels. Product must satisfy `device.limits.maxComputeInvocationsPerWorkgroup` and per-axis size limits.
- Match `count` to real data size; unused invocations still cost.
- Cache storage reads in locals (`.toVar()`) before loops (`position`/`velocity` in birds), write back once.
- Avoid divergent branches and heavy `hash` chains per invocation when a precomputed buffer works.
- Coalescing: index with `instanceIndex` linearly; structure-of-arrays (separate `positions`/`velocities`) is what every official example uses.
- Don't read back per frame; keep data on the GPU. If needed, throttle (every N frames), read the minimum bytes (offset/count), reuse a `ReadbackBuffer`.
- Batch: `renderer.compute( [ a, b, c ] )` shares one encoder/pass and one timestamp entry; many tiny dispatches have CPU overhead (each submits).
- `compileComputeAsync( node )` once at load to avoid first-dispatch stutter; changing a uniform `.value` never rebuilds the pipeline.
- Dispatch limits: `maxComputeWorkgroupsPerDimension` is folded automatically for number dispatches; extremely large counts still hit `maxStorageBufferBindingSize`/`maxBufferSize`: request larger via `requiredLimits` if the adapter allows.
- Prefer `.toReadOnly()` on inputs that a kernel never writes (declares `var<storage, read>`); avoid binding more storage buffers than `maxStorageBuffersPerShaderStage`.
- Frame-rate independent physics: pass dt (`deltaTime` or your own `uniform`).
- Profile: `new WebGPURenderer( { trackTimestamp: true } )`, `renderer.resolveTimestampsAsync( THREE.TimestampQuery.COMPUTE )` then `renderer.info.compute.timestamp` (ms) and `renderer.info.compute.frameCalls` (webgpu_storage_buffer / compute_reduce examples).

## 15. Debugging

- `.setName()` on kernels, storage nodes and uniforms: names appear in generated WGSL and in the Inspector (`renderer.inspector = new Inspector()`), making `GPUValidationError` messages readable.
- Print generated source: attach `.debug()` to a node inside the kernel (prints compute-stage code up to that node), or `renderer.debug.onNodeBuilderCreated = ( builder ) => {}` to hook the builder. `renderer.debug.getShaderAsync( scene, camera, object )` only returns vertex/fragment sources of a render object (no compute equivalent in r186).
- Errors: `renderer.onError`, `renderer.onDeviceLost`, `renderer.debug.checkShaderErrors = true` (default).
- Verify data by reading back a small slice (`getArrayBufferAsync( attr, null, 0, 64 )`, byte counts) and logging it; `webgpu_compute_reduce.html` has a "Log Left/Right Side" button doing this with `ReadbackBuffer`.
- Inspector `Memory` tab / `renderer.info.memory.storageAttributes(Size)`, `readbackBuffers`, `indirectStorageAttributes` show buffer budgets.
- Timestamp profiling: section 14. `info.compute.timestamp` is 0 unless `trackTimestamp` is true and the device has `timestamp-query`.
- Typical symptoms: all zeros -> kernel not dispatched (forgot `renderer.compute`), wrong `count`, or output node never used; flicker/race -> read/write same buffer neighbors (use ping-pong) or missing barrier; NaN -> JS `-` on nodes (use `.negate()`), division by zero, uninitialized buffers; WebGPU validation "storage buffers in vertex stage" -> raise `requiredLimits.maxStorageBuffersInVertexStage`.

## 16. Pitfalls checklist

1. `renderer.compute()` before `await renderer.init()` returns a Promise (warns); do init first or use `computeAsync`.
2. Numeric `count` adds a bounds guard, but kernels with any barrier lose it (`allowEarlyReturns = false`).
3. `renderer.compute( node, [x,y,z] )` are workgroups; `renderer.compute( node, n )` is invocations; the guard still uses `node.count`.
4. Vertex/fragment stages see storage buffers read-only; write only in compute.
5. `toAttribute()` vs `.element( instanceIndex )` in vertex shader: only the latter needs `requiredLimits.maxStorageBuffersInVertexStage`.
6. Set `object.count` (Sprite/Mesh/Points) or InstancedMesh count manually; set `frustumCulled = false` for GPU-moved geometry.
7. Atomics: int/uint only; reset counters in a separate dispatch; not in vertex stage.
8. Struct buffers: pad to multiples of 4 floats; use `.get( 'name' )`.
9. `onInit`/`renderer.compute( init )` ordering: init buffers before first render; compute nodes embedded in materials dispatch automatically each frame.
10. JS operators on nodes (`-x`, `a * b`) do not work; use `.negate()`, `.mul()`, `.add()`.
11. Storage textures: WebGPU only; pick `type` before first use; separate read-only/write-only nodes for ping-pong; don't sample while writing.
12. Readback offset/count multiples of 4 bytes; `ReadbackBuffer.release()` invalidates the previous ArrayBuffer.
13. WebGL fallback: no atomics/barriers/storage textures/indirect/array dispatch; use `.setPBO( true )`.
14. `uniform().value` changes need no rebuild; changing which node is assigned to a material slot needs `material.needsUpdate = true`.
15. `time` updates once per frame, not per dispatch; use your own uniform if you need per-dispatch variation.
16. `ComputeNode.label()` deprecated (r179), use `setName()`.

## 17. See also

API (sibling `threejs` skill, `references/api/`): `ComputeNode.md`, `ComputeBuiltinNode.md`, `WorkgroupInfoNode.md`, `BarrierNode.md`, `AtomicFunctionNode.md`, `SubgroupFunctionNode.md`, `StorageBufferNode.md`, `StorageTextureNode.md`, `StorageBufferAttribute.md`, `StorageInstancedBufferAttribute.md`, `IndirectStorageBufferAttribute.md`, `StorageTexture.md`, `Storage3DTexture.md`, `StorageArrayTexture.md`, `ReadbackBuffer.md`, `BitonicSort_BitonicSort.md`, `CountingSort.md`, `module-SortUtils.md`, `Renderer.md` (`compute`, `computeAsync`, `compileComputeAsync`, `getArrayBufferAsync`), `Info.md`, `TimestampQueryPool.md`, `InspectorBase.md`.

Local guides: `tsl-guide/28-compute-stage.md`, `29-events.md`, `30-atomic.md`, `36-storage.md`, `37-storage-texture.md`, `38-storage-array.md`, `22-struct.md`, `26-loop.md`, `66-debug.md`, `73-setname.md`; `webgpu-renderer.md` (init, limits, timestamps).

Examples (three.js r186 `examples/`): webgpu_compute_particles, webgpu_compute_particles_rain, webgpu_compute_particles_snow, webgpu_compute_particles_fluid (atomics, fixed point, structs), webgpu_compute_points, webgpu_compute_texture, webgpu_compute_texture_pingpong, webgpu_compute_texture_3d, webgpu_compute_geometry, webgpu_compute_birds, webgpu_compute_water, webgpu_compute_cloth (verlet, spring lists, PBO), webgpu_compute_audio (readback), webgpu_compute_reduce (workgroup + subgroup reductions, timestamps), webgpu_compute_sort_bitonic, webgpu_compute_rasterizer(.ibl) (atomics, indirect), webgpu_storage_buffer (WebGPU vs WebGL side-by-side), webgpu_struct_drawindirect, webgpu_particles (indirect), webgpu_tsl_compute_attractors_particles, webgpu_instance_*.

Official: https://threejs.org/docs/#ComputeNode, https://threejs.org/docs/#StorageBufferNode, https://threejs.org/manual/#en/webgpurenderer, https://github.com/mrdoob/three.js/wiki/Three.js-Shading-Language
