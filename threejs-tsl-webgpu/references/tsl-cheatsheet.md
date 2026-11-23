# TSL Cheat Sheet (three.js r187)

When to read this: any time you write or review TSL (Three.js Shading Language) code. It is the dense syntax and semantics reference: the mental model, every type/operator/math/control-flow/stage/input/accessor family, and the gotchas. For material slots (`colorNode`, `positionNode`, ...) read `node-materials.md`; for the full alphabetical function list read `tsl-reference.md`. Every name below was checked against `tsl-reference.md` or `src/nodes` (r187). Deprecated names are marked **[deprecated]**.

Setup used by all snippets:

```js
import * as THREE from 'three/webgpu';            // WebGPURenderer + all *NodeMaterial classes
import { Fn, vec3, float, uniform, uv, time } from 'three/tsl';   // TSL functions/constants
// addons: import { bloom } from 'three/addons/tsl/display/BloomNode.js';
```

## Table of contents

1. Mental model
2. Types, constructors, conversions
3. Constants
4. Swizzle and component assignment
5. Operators
6. Math functions
7. Fn(): functions, layouts, overloads, once
8. Variables and assignment
9. Properties and material property nodes
10. Arrays and structs
11. Control flow
12. Stages: vertex, varying, fragment
13. Compute
14. Inputs: attributes, textures, uniforms, storage, buffers, references
15. Accessors (positions, normals, camera, model, screen, viewport, time)
16. Lighting hooks, shadows, scene (fog, background)
17. Display: blend, color, tone mapping, color space, normal/bump, env
18. Utilities: UV, random, noise, MaterialX, remap, oscillators, packing, shapes
19. Context, naming, caching, sub-builds, events
20. Native code: wgslFn, glslFn, code, transpiler
21. Debugging
22. Top 15 mistakes
23. See also

---

## 1. Mental model

```
JS (build time, runs on CPU once per material build)      GPU (run time, every vertex/fragment/invocation)
------------------------------------------------------    ------------------------------------------------
const a = uv().mul(2)      -> creates Node objects        generated WGSL (WebGPU) or GLSL (WebGL2 backend)
if (flag) {...}            -> JS branch, decided NOW      If(cond, ...) -> real shader branch, decided per pixel
for (let i...) {...}       -> unrolls into the graph      Loop(n, ...) -> real shader loop
uniform.value = 3          -> uploads data, NO recompile  
material.needsUpdate=true  -> forces graph rebuild
```

- A TSL expression is a **graph of Node objects**, not a computation. `a.add(b)` returns a new `Node`; nothing runs until `NodeBuilder` compiles the material: **setup** (nodes expand into child nodes via `node.setup(builder)`), **analyze** (reference counts, cache decisions), **generate** (emits WGSL/GLSL). Compile happens lazily at first render of an object with that material, and again when the cache key changes (`material.needsUpdate = true`, changed node graph, changed render state).
- **JS values vs shader values.** `5`, `Math.sin(x)`, `Color`, `Vector3` are JS. `float(5)`, `sin(x)`, `uniform(new Color())` are shader values. `Math.sin(time)` is a bug (`time` is a Node); use `time.sin()`. A JS `if` on a Node is always truthy (objects) -> use `If(...)`, `select(...)`, or `.select()`.
- **Constants are baked, uniforms are live.** `float(0.5)` is literal in shader source: changing it means rebuilding. `uniform(0.5)` is a GPU uniform: change `u.value` at runtime, no recompile. Put anything that animates or is tweaked into a `uniform`.
- **Evaluation stage is inferred.** Slots `positionNode`, `vertexNode`, `geometryNode` (and `castShadowPositionNode`) run in the vertex stage. Everything else runs in the fragment stage. Attribute-derived values (`uv()`, `positionWorld`, `normalView`) are computed per-vertex and interpolated automatically via varyings; derived math on them (`uv().mul(2)`) is recomputed per-fragment unless you force vertex stage with `.toVertexStage()` / `varying()` / `vertexStage()`.
- **Type promotion.** Binary operators pick the wider type: `float op vec3 -> vec3`; `mat4 * vec4 -> vec4`; `mat * float -> mat`; comparisons return `bool` (or `bvecN` for vectors, so `If(a.equal(b))` on a vec needs `.all()`); bitwise ops return integer types; `%` returns the left operand type. JS numbers are auto-wrapped as nodes in function args (`sin(1)`, `mul(uv(), 10)`), but you must wrap to start a chain: `float(1).div(x)`, not `1.div(x)`. **r187 change:** plain JS numbers now adopt the other operand's type, so with integer nodes fractional literals are TRUNCATED: `instanceIndex.mul( 0.5 )` is `instanceIndex * 0u`, and `int( 1.5 )` is `1` (truncated, not rounded). Write `instanceIndex.toFloat().mul( 0.5 )` or `instanceIndex.mul( float( 0.5 ) )` for float math. Float-only functions (`sin`, `pow`) still promote ints to float; `max`/`clamp` keep ints.
- **Auto-dedup.** Using the same Node instance twice builds it once and reuses the generated variable. Two separately created but identical expressions are two nodes (still often merged by the cache hash). `positionWorld`, `normalWorld`, `modelViewMatrix` are singletons: cheap to reference everywhere.
- **`Fn` vs plain JS function.** A plain JS function (`(t = time) => t.sin()`) is an inline macro: pure expression building, no statements, can be called anywhere, even outside `Fn`. `Fn()` creates a *stack* (statement list) so `.assign`, `If`, `Switch`, `Loop`, `.toVar()`, `Return`, `Discard`, `OnFrameUpdate` work **only inside an Fn body** (error: "No stack defined for assign operation"). An `Fn` must be **invoked**: `Fn(() => ...)()`; an un-invoked Fn logs an error at build.
- **Caching keys.** Program cache key = material type + hash of every `*Node` slot's node cache key + render state. Same node graph on two meshes = same program. Node graphs that differ only in uniform values share one program.
- **Fn body is JS that may run more than once** (once per call site, per sub-build such as POSITION/NORMAL/VERTEX, per builder). Keep side effects (creating textures/uniforms, `TextureLoader.load`) outside it or guard with a module variable, or use `.once()`.

---

## 2. Types, constructors, conversions

| Type | Constructors | Notes |
|---|---|---|
| float, int, uint, bool | `float(1)`, `int(2)`, `uint(3)`, `bool(true)` | literals 0,1,-1,0.5... are cached constants |
| vec2/3/4 | `vec3(1,2,3)`, `vec3(0)`, `vec3(v2, 1)`, `vec4(v3, 1)`, `vec3(new THREE.Vector3())` | join/truncate: `vec2(positionWorld)` takes `.xy` |
| ivec / uvec / bvec 2-4 | `ivec2(1,2)`, `uvec3(...)`, `bvec2(true,false)` | |
| mat2/3/4 | `mat3(...9 numbers)`, `mat4(new THREE.Matrix4())` | column-major; `mat * vec` via `.mul` |
| color | `color(0xff0000)`, `color('#ff0000')`, `color(r,g,b)`, `color(new THREE.Color())` | type `color` is a vec3 treated as working color space (linear); hex ints are converted from sRGB to linear by `THREE.Color` |

Method conversions (chainable): `.toFloat() .toInt() .toUint() .toBool() .toColor() .toVec2/3/4() .toIVec2/3/4() .toUVec2/3/4() .toBVec2/3/4() .toMat2/3/4()`. Also `convert(node, 'vec3')`, `bitcast(x, 'uint')`, `floatBitsToInt/Uint`, `intBitsToFloat`, `uintBitsToFloat`.

```js
vec3(1, 0, 0)                     // constant
vec2(positionWorld)               // truncate
positionWorld.toVec2()            // same
int(time.mul(1.5).mod(3))         // float -> int (truncates), used for array indices
uint(instanceIndex).toFloat()
vec3(0).toArray(2)                // array of 2 copies  (see Arrays)
```

`vec3(a)` / `float(a)` etc. return a **var-intent** node: it becomes a real mutable variable automatically if you later `.assign()` to it. A bare expression like `a.mul(2)` is not assignable without `.toVar()`.

```js
const c = vec3(1, 0, 0);           // OK: assignable inside Fn
c.y = 0.5;                         // swizzle setter -> assign
const d = x.mul(2);                // NOT assignable; use x.mul(2).toVar()
```

---

## 3. Constants

| Name | Value |
|---|---|
| `PI`, `TWO_PI`, `HALF_PI` | pi, 2pi, pi/2 |
| `PI2` | **[deprecated]** use `TWO_PI` |
| `EPSILON` | 1e-6 |
| `INFINITY` | +inf |

JS `Math.PI` is fine inside `.mul(Math.PI * 2)` (JS number auto-wrapped).

---

## 4. Swizzle and component assignment

```js
const v = vec3(1, 2, 3);
v.zyx;  v.xxy;  v.rgb;  v.bgr;  v.stp;      // xyzw | rgba | stpq sets, 1-4 letters, can repeat
v.x;  v.r;  v.s;                             // scalar
v[0]; v[1]                                   // constant index 0..31 (ArrayElementNode); dynamic index -> v.element(i)
// writes (inside Fn): setter or assign
v.y = 0.5;                                   // calls v.y.assign(0.5)
v.xz.assign(vec2(1, 2));
v.x.addAssign(1);                            // x += 1
// pure functional write: returns a new vec, original unchanged (works outside Fn)
v.setX(1); v.setYZ(vec2(0)); v.flipXY();     // setXYZW combos (any swizzle, also set R/G/B/A, S/T/P/Q), flip<Swizzle>
```

Mixed sets are not allowed (`v.xg` is invalid). Writing to a non-var requires `.toVar()` first.

---

## 5. Operators

All are chainable (`a.add(b)`) and exist as functions (`add(a, b, c...)` accept variadic for add/sub/mul/div).

| Group | Methods |
|---|---|
| Arithmetic | `.add(...v) .sub(v) .mul(v) .div(v) .mod(v)` (variadic for add/sub/mul/div in the function form) |
| Unary | `.negate() .oneMinus()` (1 - x) `.reciprocal()` (1 / x) |
| Compare | `.equal(v) .notEqual(v) .lessThan(v) .greaterThan(v) .lessThanEqual(v) .greaterThanEqual(v)` -> `bool` / `bvecN` |
| Logic | `.and(v) .or(v) .not() .xor(v)`; `.all()`, `.any()` collapse a bvec |
| Bitwise (int/uint) | `.bitAnd(v) .bitOr(v) .bitXor(v) .bitNot() .shiftLeft(v) .shiftRight(v)` |
| In-place (need var) | `.assign(v) .addAssign .subAssign .mulAssign .divAssign .modAssign .bitAndAssign .bitOrAssign .bitXorAssign .shiftLeftAssign .shiftRightAssign` and `Assign` form for every chainable fn (e.g. `.mixAssign`) |
| Increment | `increment(a)`, `decrement(a)`, `incrementBefore(a)`, `decrementBefore(a)` (also chainable) |
| Select | `cond.select(a, b)` = `select(cond, a, b)` |

```js
const t = uv().x.mul(2).add(0.5);                 // ((x * 2) + 0.5)
const mask = positionLocal.y.greaterThan(0).and(uv().x.lessThan(0.5));
vec3(1).equal(v).all();                           // vector equality -> single bool
mat4Node.mul(vec4(p, 1)).xyz                       // matrix * vector
```

Order matters in `.mix`, `.smoothstep`, `.step` method forms (see section 6).

---

## 6. Math functions

All exist as `fn(x)` and as `x.fn()` unless noted. Args accept `Node | number`.

| Group | Functions |
|---|---|
| Trig | `sin cos tan asin acos atan asinh acosh atanh sinh cosh tanh radians degrees`; **`atan(y, x)`** is the two-argument atan2 (no `atan2` in TSL core; `mx_atan2` exists in MaterialX) |
| Exp/log | `exp exp2 log log2 pow(x, y) pow2 pow3 pow4 sqrt inverseSqrt cbrt` |
| Rounding | `abs sign floor ceil fract round trunc` |
| Range | `min(a, b, ...) max(a, b, ...) clamp(x, lo, hi) saturate(x)` (clamp 0..1), `difference(a, b)` = abs(a-b) |
| Interpolation | `mix(a, b, t)`, `step(edge, x)`, `smoothstep(lo, hi, x)`; element-wise variants `mixElement(t, e1, e2)`, `stepElement`, `smoothstepElement` |
| Vector | `length lengthSq distance(a, b) dot(a, b) cross(a, b) normalize reflect(I, N) refract(I, N, eta) faceForward(N, I, Nref)` |
| Matrix | `transpose determinant inverse` (mat2/3/4); transform: `transformDirection(dir, mat4)` (normalized), `transformNormal(n, m)`, `transformNormalByViewMatrix`, `transformNormalByInverseViewMatrix` |
| Derivatives (fragment only) | `dFdx dFdy fwidth` |
| Logic | `all(x) any(x)` |
| Remap | `remap(x, inLo, inHi, outLo=0, outHi=1)`, `remapClamp(...)` (same, clamped) |
| Bits | `bitcast countLeadingZeros countTrailingZeros countOneBits` |
| Shaping | `parabola(x, k)`, `gain(x, k)`, `pcurve(x, a, b)`, `sinc(x, k)` (from MathUtils) |

**Method-chaining argument order exceptions** (calling node is the *last* parameter in the math signature):

```js
t.mix(a, b)            // = mix(a, b, t)         t is the factor
x.smoothstep(lo, hi)   // = smoothstep(lo, hi, x)
x.step(edge)           // = step(edge, x)        NOTE: edge is the arg, x is the receiver
a.clamp(lo, hi)  a.pow(2)  a.max(b)  a.dot(b)  a.cross(b)  v.reflect(n)  // receiver is first
```

```js
const rim = normalView.dot(positionViewDirection).saturate().oneMinus().pow(3);
const col = rim.mix(baseColor, glowColor);                  // rim = factor
const edge = distanceToCenter.smoothstep(0.45, 0.5).oneMinus(); // keep lo < hi: WGSL smoothstep with lo >= hi is undefined/an error
const e = x.remap(-1, 1);                                   // -1..1 -> 0..1
```

`mod` in WGSL/GLSL semantics: `x.mod(y)` is `x - y*floor(x/y)` for floats.

---

## 7. Fn(): functions, layouts, overloads, once

```js
const oscSine = Fn(([t = time]) => t.add(0.75).mul(Math.PI * 2).sin().mul(0.5).add(0.5)); // array params + defaults
const col = Fn(({ r, g, b }) => vec3(r, g, b));                                               // object params
col(0, 1, 0);  col({ r: 0, g: 1, b: 0 });                                                     // positional OR named
const useBuilder = Fn(({ material, geometry, object, camera, scene, renderer }) => {...});    // no declared params -> builder fields
const both = Fn(([a, b], builder) => ...);                                                    // builder is passed last
export const f = /*@__PURE__*/ Fn(...);                                                       // tree-shaking annotation
```

- Call it: `fn(args)`. `fn` is itself a Node (a Proxy); `Fn(...)` alone never returns a value.
- **No layout (default):** inlined at the call site; can return any JS value (even objects), adapt to material/geometry, and use `.assign` on its params (params are mutable vars: `color.addAssign(...)`).
- **Layout:** becomes a real WGSL/GLSL function, compiled once and cached across materials. All param and return types must be declared.

```js
// shorthand layout: param types + return
const clampOne = Fn(({ val }) => {
  If(val.greaterThan(1), () => { return float(1); });   // `return` inside If only works with a layout (real native function)
  return val;
}, { val: 'float', return: 'float' });

// long form
const f2 = Fn(([a, b]) => a.add(b)).setLayout({
  name: 'f2', type: 'float', inputs: [{ name: 'a', type: 'float' }, { name: 'b', type: 'float' }]
});
// string layout = return type only:  Fn(() => ..., 'vec3')
```

Guide example uses `return 1.0;` inside an `If` for a layout Fn; with a layout the body is emitted as a native function, so `return` branches work. Without layout, use `.assign` to a result var and return at the end.

| API | Meaning |
|---|---|
| `.once()` | build the Fn body once per build and reuse the result (singleton, e.g. `positionWorld` is `Fn(...).once(['POSITION'])()`) |
| `.once(['POSITION'])` | one cached result per named sub-build (see 19) |
| `overloadingFn([fnA, fnB])` | picks the overload by argument count/type at build time |
| `Fn(...).compute(count, wgSize)` | wraps as a compute node (see 13) |
| `.call(...)` | explicit invoke |
| `Return()` | emits a bare `return;` (void Fn / compute bodies); to return a value from a layout Fn use JS `return` |
| Closures | nested `Fn` captures outer params/vars; each inner Fn is a new instance, not cache-shared |

Void Fn (`Fn(() => { ...statements... }, 'void')`) pushes itself to the stack when invoked (use for compute bodies).

---

## 8. Variables and assignment

```js
const v = expr.toVar();            // declare mutable `var` in current stack (evaluated NOW, in statement order)
const v = expr.toVar('name');      // named
const k = expr.toConst('name');    // `const`/`let`, immutable, must be deterministic or read-only
Var(expr, 'name');  Const(expr, 'name');     // function forms (capitalized)
v.assign(x);  v.addAssign(x);  ...           // writes; only inside Fn
```

**Why `.toVar()`:** a plain expression node is *inlined at every use* (or cached once if the analyzer decides). That is correct for pure math, but wrong if (a) you want to mutate it, (b) you want a fixed evaluation point (e.g. before a loop/`If` that changes inputs), (c) a noisy expression is used many times and you want it computed once, (d) you want a readable name when debugging. `.toVar()` also snapshots: later changes of its source do not affect it (it is a copy).

```js
const f = Fn(() => {
  const p = positionLocal.toVar();          // copy
  p.y.addAssign(time.sin());                // mutate the copy
  const acc = float(0).toVar();             // accumulator
  Loop(4, ({ i }) => { acc.addAssign(p.x.mul(i.toFloat())); });
  return acc;
});
```

- `x = y` (JS assignment) just rebinds the JS variable; it never writes to the shader var. Use `x.assign(y)`. Exception: swizzle properties `v.x = y` have setters that call assign.
- `let` JS variables holding nodes are fine, but reassigning them does not create shader state.
- `.assign()` outside an `Fn` throws.
- `varyingProperty`/`property` nodes are assigned the same way (see 9).

---

## 9. Properties and material property nodes

```js
property('vec3', 'myProp')                                // declared shader var, assign inside Fn, read anywhere after
varyingProperty('vec3', 'vCustom')                        // varying placeholder; assign it in the vertex stage, read in fragment
```

```js
const vC = varyingProperty('vec3', 'vCustom');
material.positionNode = Fn(() => { const p = positionLocal.add(vec3(0, time.sin(), 0)); vC.assign(p); return p; })();
material.colorNode = vC;                                  // positionNode runs in vertex stage -> fragment reads the varying
```

Built-in property nodes (values computed inside the lighting/material pipeline; use for MRT and post-processing, not as inputs to `colorNode` of the same material):

`output (vec4) diffuseColor (vec4) diffuseContribution (vec3) roughness metalness (float) emissive (vec3) specularColor specularColorBlended (color) specularF90 clearcoat clearcoatRoughness sheen sheenRoughness iridescence iridescenceIOR iridescenceThickness transmission thickness ior dispersion attenuationColor attenuationDistance anisotropy anisotropyT anisotropyB alphaT retroreflectivity shininess ambientOcclusion (default 1) dashSize gapSize pointWidth`.

Material *input* accessors (read the material's own `color`/`map`/etc.; use to modulate instead of replace): `materialColor materialOpacity materialEmissive materialNormal materialRoughness materialMetalness materialSpecular* materialClearcoat* materialSheen* materialTransmission materialThickness materialIOR materialIridescence* materialAnisotropy materialDispersion materialAO materialLightMap materialAlphaTest materialEnvIntensity materialEnvRotation materialRotation materialPointSize materialLine*` plus `materialReference(name, type, material?)`.

```js
material.colorNode = materialColor.mul(color(0xff5500));      // tint existing map*color
material.roughnessNode = materialRoughness.mul(0.5);
material.colorNode = color(0xff5500);                          // REPLACES color and map entirely
```

`materialReference('opacity', 'float')` live-links a JS material property to a GPU uniform: changing `material.opacity` updates with no recompile.

---

## 10. Arrays and structs

```js
const a = array([vec3(1,0,0), vec3(0,1,0), vec3(0,0,1)]);   // constant array
a.element(i)                         // dynamic index (Node); a[1] only for JS constants
array([0, 1, 2], 'uint');            // explicit type
array('vec3', 4);                    // fixed size, zero-initialised
vec3(0, 0, 1).toArray(2);            // [vec3, vec3] filled
a.element(i).assign(...)             // write (inside Fn)
uniformArray([new THREE.Color(1,0,0), ...])            // uniform array (see 14)
```

```js
const BBox = struct({ min: 'vec3', max: 'vec3' }, 'BBox');   // optional shader type name
const bb = BBox(vec3(0), vec3(1));            // or BBox({ min:..., max:... })
bb.get('min');                                // member node (MemberNode)
bb.get('min').assign(vec3(-1));
const Cell = struct({ x: { type: 'int', atomic: true }, mass: { type: 'int', atomic: true } });
storage(attr, Cell, count);                   // buffer of structs; storage(...).element(i).get('mass')
// r187: struct storage buffers are always arrays, even with one element: storage(attr, Cell).element(0).get('mass'), never storage(...).get('mass')
outputStruct(a, b, c)                         // multi-output (MRT) node
```

---

## 11. Control flow

All of these must run inside an `Fn()` body (except `select`).

```js
If(cond, () => { ... })
  .ElseIf(cond2, () => { ... })
  .Else(() => { ... });

Switch(sel).Case(0, () => {...}).Case(1, 2, () => {...}).Default(() => {...});   // no fallthrough; multi-value Case

const r = select(cond, a, b);       // ternary, a value, usable outside Fn.  also cond.select(a, b)

Loop(10, ({ i }) => { ... });                          // i = 0..9, int
Loop(10, 5, ({ i, j }) => { ... });                    // nested
Loop({ start: int(0), end: int(10), type: 'int', condition: '<', name: 'k', update: '+= 2' }, ({ k }) => {});
Loop({ start: 10 }, ({ i }) => {});                    // counts down from 9 to 0 when `end` omitted
Loop(value.lessThan(10), () => { value.addAssign(1); });   // while loop (bool node)
Break();  Continue();                                  // inside Loop
Discard();                 // `discard;` fragment kill; Discard(cond) conditional; also cond.discard()
Return();                  // return from void/layout Fn
```

Gotchas:
- JS `if/for` run at build time. `if (material.map)` is fine (build-time specialisation); `if (u.value > 1)` is a bug (value read once at build).
- Assign inside branches to a pre-declared var; the branch body itself cannot `return` a value in a no-layout Fn.
- A `Loop` count that is a JS number is a compile-time constant; use `Loop(someUniformInt, ...)` for runtime counts.
- `Loop` index `i` is an int node; `.toFloat()` before float math.
- Derivative functions (`dFdx/dFdy/fwidth`, implicit-LOD `texture()`) inside divergent branches are undefined in WGSL: wrap the whole `select` with `.uniformFlow()` (see 19) or sample with `.level()` / `.grad()`.
- `Discard()` in compute shaders is invalid.

---

## 12. Stages: vertex, varying, fragment

```js
vertexStage(node)          // compute per-vertex, interpolate to fragment (unnamed varying)
node.toVertexStage()
varying(node, 'vName')     // same + explicit varying name
node.toVarying('vName')
```

- Per-vertex then interpolated = cheaper but not exact for non-linear functions (`normalize`, `pow`). The guide idiom: do the linear part per-vertex, nonlinear part per-fragment:

```js
const nv = modelNormalMatrix.mul(normalLocal).toVertexStage();   // linear -> vertex
material.colorNode = nv.normalize();                              // nonlinear -> fragment
```
- Anything inside `positionNode`, `vertexNode`, `geometryNode`, `castShadowPositionNode` is already vertex stage; `varying()` there is a no-op (no varying generated).
- Nodes that read vertex attributes in the fragment slot (`uv()`, `attribute('x')`, `positionLocal`) auto-create varyings.
- `Fn` running in `positionNode` is vertex; in `colorNode`/`opacityNode`/`normalNode`/`emissiveNode`/... fragment.
- **A node shared between both stages is evaluated per stage separately** (via sub-builds): `positionWorld` used in `positionNode` and `colorNode` compiles twice. Use `.toVarying()`/`varyingProperty` to carry a *vertex-computed* value to fragment.
- Compute stage: see 13.

---

## 13. Compute

```js
const count = 1024;
const positions = instancedArray(count, 'vec3');         // StorageInstancedBufferAttribute-backed
const velocities = attributeArray(count, 'vec3');        // StorageBufferAttribute-backed

const update = Fn(() => {
  const p = positions.element(instanceIndex);            // instanceIndex = global linear invocation id (uint)
  const v = velocities.element(instanceIndex);
  v.y.subAssign(0.01);
  p.addAssign(v);
})().compute(count);            // .compute(count, [wgX, wgY, wgZ]) ; default workgroup [64]
// also compute(node, count, workgroupSize), computeKernel(node, workgroupSize)

renderer.compute(update);                 // dispatch (call each frame to simulate)
await renderer.computeAsync(update);     // use if renderer may be uninitialised; or `await renderer.init()` first
// OnBeforeMaterialUpdate / OnBeforeFrameUpdate(() => renderer.compute(update))  also works (see 19)

material.positionNode = positions.toAttribute();   // read buffer as vertex attribute (per-vertex)
// instanced sprites: positions.element(instanceIndex)  in positionNode for Sprite/Points with `.count = n`
```

Built-ins: `instanceIndex globalId(uvec3) localId workgroupId numWorkgroups invocationLocalIndex invocationSubgroupIndex subgroupIndex subgroupSize`; `builtin(name)`, `computeBuiltin(name, type)`.

Workgroup memory and barriers:

```js
const shared = workgroupArray('vec3', 256);
shared.element(localId.x).assign(v);
workgroupBarrier();                    // also storageBarrier(), textureBarrier(), barrier(scope)
const w = shared.element(other);
```

Atomics (WebGPU): create `storage(attr, 'uint', n).toAtomic()`, then `atomicAdd(buf.element(i), 1)` (returns previous), `atomicSub atomicMax atomicMin atomicAnd atomicOr atomicXor atomicLoad(ptr) atomicStore(ptr, v)`; `atomicFunc(method, ptr, v)`. Struct members opt in with `{ type: 'int', atomic: true }`.

Subgroup (wave) ops: `subgroupElect subgroupAdd subgroupInclusiveAdd subgroupExclusiveAdd subgroupMul subgroupMin subgroupMax subgroupAll subgroupAny subgroupBroadcast subgroupBroadcastFirst subgroupShuffle(+Up/Down/Xor) subgroupBallot subgroupAnd/Or/Xor quadBroadcast quadSwapX/Y/Diagonal`.

Storage textures:

```js
const tex = new THREE.StorageTexture(256, 256);
Fn(() => {
  const x = instanceIndex.mod(256), y = instanceIndex.div(256);
  textureStore(tex, uvec2(x, y), vec4(1, 0, 0, 1)).toWriteOnly();
})().compute(256 * 256);
material.colorNode = texture(tex);                    // sample; storageTexture(tex, uv) for read/write node
// storageTexture3D / THREE.Storage3DTexture ; .toReadOnly() .toReadWrite() .setMipLevel(n) on storage texture nodes
```

Caveats: `storage().toWriteOnly()/.toReadWrite()` are documented in the guide but `StorageBufferNode` in r187 only implements `.toReadOnly()`, `.toAtomic()`, `.setAccess(NodeAccess.*)` (see Doc gaps). On the WebGL2 backend storage buffers fall back to attribute/transform feedback (limited), storage textures and atomics are unsupported.

Dispatch: `renderer.compute(node)` for `.compute(count)` nodes. `renderer.compute(node, dispatchSize)` (`dispatchSize` = number | `[x,y,z]` workgroups | `IndirectStorageBufferAttribute`) only for `.computeKernel(wg)` nodes; since r187 it throws for count nodes. Workgroup size must match what the shader assumes (`localId` math).

---

## 14. Inputs

### Attributes

```js
attribute('aRandom', 'float')            // geometry attribute by name (type optional)
uv(), uv(1)                              // uv / uv1 / uv2 ... (vec2)
vertexColor(0)                           // `color` attribute (needs material.vertexColors for auto-apply)
instanceIndex  vertexIndex  drawIndex    // IndexNodes
bufferAttribute(attr, 'vec3'), instancedBufferAttribute(attr, 'vec3'), dynamicBufferAttribute(...), instancedDynamicBufferAttribute(...)
node.toAttribute()                       // BufferAttributeNode/storage -> vertex attribute
range(minNode, maxNode)                  // random value per instance (an instanced attribute filled randomly at build)
```

### Texture

```js
texture(map)                         // default uv(); returns vec4 TextureNode
texture(map, uvNode, levelNode, biasNode)
tex.sample(uvNode)                   // preferred: independent sample (does NOT mutate tex)
tex.uv(uvNode)                       // MUTATES tex's uv (avoid when reusing the node)
tex.level(n)  tex.bias(b)  tex.grad(dx, dy)  tex.offset(ivec2)   // LOD controls (use .level in non-uniform control flow)
tex.compare(refFloat)                // depth compare (shadow sampler); tex.depth(layerInt) for texture arrays
tex.gather(channelInt)  tex.blur(amount)  tex.load(uvec2)  tex.size(level?) // load = textureLoad, unfiltered
textureLoad(map, uvec2/ivec2, level)  textureSize(tex, level)
tex.setSampler(false)                // sample without sampler (texelFetch-like use)  ;  sampler(tex)  samplerComparison(tex)
texture3D(data3DTexture, vec3)  texture3DLoad  texture3DLevel
cubeTexture(cubeTex, dirVec3, level?, bias?)           // default direction reflectVector
pmremTexture(tex, dirVec3, roughness?)                     // prefiltered env (PMREM); 3rd arg is roughness 0..1, mapped to mip via roughnessToMip()
uniformTexture(tex)  uniformCubeTexture(tex)           // texture swapped via .value without recompile
textureBicubic(tex, strength)  textureBicubicLevel(tex, lod)  maxMipLevel(tex)
tex.rgb  tex.r  tex.a ...            // swizzle like any vec4
```

Texture color space matters: set `map.colorSpace = THREE.SRGBColorSpace` for color maps; data maps (normal, roughness, noise) stay `NoColorSpace`/linear. Wrap modes set on the `THREE.Texture` (`wrapS/T = RepeatWrapping`), not in TSL. `flipY` default for loaded textures; for screen-space use `map.flipY = false`.

### Uniform

```js
const u = uniform(1.0);                           // float; uniform(new THREE.Color()) -> color; Vector2/3/4, Matrix3/4, boolean, Texture
uniform(0, 'float'); uniform('vec3')              // explicit type / typed default
u.value = 2.0;                                    // update at any time, no recompile
u.setName('uSpeed');                              // readable name in shader  (label() is deprecated since r179)
u.setGroup(renderGroup);                          // objectGroup (default) | renderGroup | frameGroup | uniformGroup('name') | sharedUniformGroup('name')

// auto-updating (callback return value, if not undefined, is assigned to .value)
u.onFrameUpdate(({ time, deltaTime, renderer, camera, scene }) => time % 1);   // once per frame
u.onRenderUpdate(({ renderer, camera }) => ...);                                 // once per renderer.render() call
u.onObjectUpdate(({ object, material, camera }) => ...);                         // once per drawn object (per-mesh values)
u.onUpdate(cb, 'frame');                        // generic ('frame'|'render'|'object'); `this` is the node. onFrame/Render/ObjectUpdate exist on ANY node
```

- `renderGroup` = shared, updated per render call (matrices/lights/fog); `frameGroup` = once per frame (time); `objectGroup` = per object. A custom `uniformGroup('cfg')` is a UBO; after changing members set `group.needsUpdate = true`.
- Bool uniforms are stored as uint and cached into a bool var.
- Share one uniform instance across materials and post-processing freely.

### uniformArray, buffer, userData, reference

```js
const cols = uniformArray([new THREE.Color(1,0,0), new THREE.Color(0,1,0)]);  // or (values, 'vec3')
cols.element(int(time.mod(2)));              // dynamic index
buffer(typedArray, 'vec4', count)            // uniform buffer (UBO) node, .element(i)
userData('myKey', 'float')                   // reads object.userData.myKey as a uniform (per object)
userData('myKey', 'float', someObject.userData)
reference('intensity', 'float', light)       // live-link ANY JS object property to a uniform; reference(name, type, object)
referenceBuffer('weights', 'float', 8, obj)  // array property
materialReference('roughness', 'float')      // property of the material currently rendering (no recompile when it changes)
rendererReference('toneMappingExposure', 'float', renderer)
```

### Storage

```js
storage(attr, 'vec3', count)             // attr: StorageBufferAttribute | StorageInstancedBufferAttribute | BufferAttribute
instancedArray(count | typedArray, 'vec3')    // = storage(new StorageInstancedBufferAttribute(...))
attributeArray(count | typedArray, 'float')   // = storage(new StorageBufferAttribute(...))
node.element(index)                      // element node (read/write); also storageElement(buf, idx)
node.toReadOnly()  node.toAtomic()  node.setAccess(NodeAccess.WRITE_ONLY | READ_ONLY | READ_WRITE)
node.toAttribute()                       // use as vertex/instance attribute
```

```js
const attr = new THREE.StorageBufferAttribute(new Float32Array(300), 3);   // itemSize 3
const buf = storage(attr, 'vec3', 100);
// struct element:  storage(attr, MyStruct, count).element(i).get('field')
// InstancedMesh with GPU-driven matrices: mesh.instanceMatrix = new THREE.StorageInstancedBufferAttribute(count, 16) (see node-materials.md)
```

---

## 15. Accessors

Coordinate pipeline: `positionGeometry` (raw attribute) -> `positionLocal` (after skinning, morph, batching, instancing, `positionNode`) -> `positionWorld` -> `positionView` -> clip (`modelViewProjection`, `clipSpace`).

| Family | Names |
|---|---|
| Position | `positionGeometry positionLocal positionPrevious positionWorld positionWorldDirection positionView positionViewDirection` (`positionViewDirection` = normalized surface-to-camera vector, the `V` for fresnel; `positionWorldDirection` = normalized world-space direction of the local vertex position, used for skyboxes/`scene.backgroundNode`) |
| Normal | `normalGeometry normalLocal normalView normalViewGeometry normalWorld normalWorldGeometry normalFlat`; `transformedNormalView/World` **[removed in r187 (deprecated r177) -> use `normalView`/`normalWorld`]**, `transformedClearcoatNormalView` **[removed in r187 -> `clearcoatNormalView`]**; `negateOnBackSide(v)`, `faceDirection` (+1/-1), `frontFacing` (bool) |
| Tangent | `tangentGeometry (vec4) tangentLocal tangentView tangentWorld tangentViewFrame` |
| Bitangent | `bitangentGeometry bitangentLocal bitangentView bitangentWorld bitangentViewFrame`; `TBNViewMatrix`, `parallaxDirection`, `parallaxUV(uv, scale)`, `bentNormalView()` |
| Camera (uniforms) | `cameraPosition cameraNear cameraFar cameraProjectionMatrix cameraProjectionMatrixInverse cameraViewMatrix cameraWorldMatrix cameraNormalMatrix cameraViewport cameraIndex` |
| Model (current object) | `modelWorldMatrix modelViewMatrix modelNormalMatrix modelWorldMatrixInverse modelPosition modelScale modelDirection modelViewPosition modelRadius modelViewProjection`; `highpModelViewMatrix`, `highpModelNormalViewMatrix` (CPU 64-bit, no jitter for huge worlds), `mediumpModelViewMatrix` |
| Other objects | `objectPosition(obj) objectScale(obj) objectDirection(obj) objectViewPosition(obj) objectWorldMatrix(obj) objectRadius(obj)` (uniforms tracking any Object3D) |
| Screen | `screenUV` (0..1 framebuffer) `screenCoordinate` (px) `screenSize` (px) `screenDPR` |
| Viewport | `viewport (vec4) viewportUV viewportCoordinate viewportSize`: relative to the active viewport region (differs from screen when `renderer.setViewport` is used) |
| Viewport textures | `viewportSharedTexture(uv?, level?)` already-rendered color, shared, preserves order (best default); `viewportTexture(uv, level, fb)`; `viewportMipTexture(...)`; `viewportOpaqueMipTexture(uv, level)`; `viewportDepthTexture(uv?, level?)`; `viewportLinearDepth` (scene depth behind, 0..1 linear); `linearDepth()` (this fragment's linear depth); `depth` (writable fragment depth); `viewportSafeUV(uv)` |
| Depth utils | `viewZToPerspectiveDepth orthographicDepthToViewZ perspectiveDepthToViewZ viewZToOrthographicDepth viewZToLogarithmicDepth logarithmicDepthToViewZ viewZToReversed*` |
| Reflection | `reflectVector reflectView refractVector refractView` (world/view; `cubeTexture` default uv is `reflectVector`) |
| Indices | `vertexIndex instanceIndex drawIndex` |
| Time | `time` (s, float uniform, frame group), `deltaTime`, `frameId` (uint). No `timer*` family exists |
| Velocity | `velocity` (motion vectors, for TRAA/motion blur), `positionPrevious` |
| Scene | `backgroundBlurriness backgroundIntensity backgroundRotation` (read scene settings) |
| Point/sprite | `pointUV` (gl_PointCoord) |

```js
const fresnel = normalView.dot(positionViewDirection).saturate().oneMinus().pow(3);
const toCam = cameraPosition.sub(positionWorld).normalize();
const distToCam = cameraPosition.distance(positionWorld);
const pixel = screenCoordinate.floor();
const uvAspect = screenUV.sub(0.5).mul(vec2(screenSize.x.div(screenSize.y), 1));
const thickness = viewportLinearDepth.sub(linearDepth()).mul(cameraFar.sub(cameraNear));
```

Local vs world: `positionLocal` moves with the object (procedural textures stick to mesh); `positionWorld` stays fixed in space (triplanar world mapping, height fog).

Animation oscillators and rotation: `oscSine(t=time) oscSquare oscTriangle oscSawtooth` (0..1 output); `rotate(posNode, angleOrEuler, order='XYZ')` (2D: float angle; 3D: vec3 euler) and `node.rotate(...)`; `rotateUV(uv, rad, center=0.5)`; `spherizeUV(uv, strength, center)`; `billboarding({...})`; `spritesheetUV(countVec2, uv, frame)`; `matcapUV` (constant node, not a function call); `equirectUV(dir)`, `equirectDirection(uv)`; `barrelUV`, `parallaxUV`.

---

## 16. Lighting hooks, shadows, scene

Lights in the scene are converted to nodes automatically. Per-material control:

```js
material.lightsNode = lights([keyLight, rimLight]);     // only these lights illuminate (lights() = no lights; used to ignore scene lights)
material.lightsNode = lights([a]).context({ lightingModel: new MyModel() });   // custom model (webgpu_lights_custom)
lightingContext(lightsNode, lightingModel?, ...)         // wrapper node used internally by NodeMaterial.setupLighting
```

Custom lighting model (see `node-materials.md` for a full example): extend `THREE.LightingModel` and override `direct({ lightDirection, lightColor, reflectedLight, lightNode }, builder)`, `indirect(builder)`, `directRectArea`, `ambientOcclusion`, `start`, `finish`. Accumulate into `reflectedLight.directDiffuse/directSpecular/indirectDiffuse/indirectSpecular`. Shipped: `BasicLightingModel PhongLightingModel PhysicalLightingModel ToonLightingModel VolumetricLightingModel ShadowMaskModel`; BSDF building blocks exported from TSL: `BRDF_Lambert BRDF_GGX BRDF_Sheen D_GGX V_GGX_SmithCorrelated F_Schlick EnvironmentBRDF getDistanceAttenuation ...`.

Light data accessors (uniform nodes that follow the Light): `lightPosition(light) lightTargetPosition(light) lightViewPosition(light) lightTargetDirection(light) lightShadowMatrix(light) lightProjectionUV(light, positionWorld?)`.

```js
spotLight.colorNode = Fn(() => lightProjectionUV(spotLight).xy.sub(0.5).length().mul(30).sin())();   // procedural gobo
const projector = new THREE.ProjectorLight(0xffffff, 500);   // rectangular frustum
projector.colorNode = Fn(([projectorUV]) => texture(map, projectorUV.xy));
```

Shadows: `shadow(light, lightShadow?)`, `pointShadow(light, shadow?)`, `sunShadow(light, shadow)`; `shadowPositionWorld`; material slots `castShadowNode` (needs `renderer.shadowMap.transmitted = true`), `receivedShadowNode`, `castShadowPositionNode`, `receivedShadowPositionNode`, `maskShadowNode`. `builtinShadowContext(shadowNode, light, node?)` and `builtinAOContext(aoNode, node?)`, `builtinGIContext(ao, gi, node)` wrap a node/material context to modulate shadow/AO/GI.

Scene nodes:

```js
scene.fogNode = fog(color(0x88aaff), rangeFogFactor(10, 50));                 // linear
scene.fogNode = fog(color(0x88aaff), densityFogFactor(0.02));                 // exp2
scene.fogNode = fog(color(0x88aaff), exponentialHeightFogFactor(0.1, 0));     // height
// classic scene.fog = new THREE.Fog()/FogExp2() still works. There is no `rangeFog()`/`densityFog()` function.
scene.backgroundNode = positionWorldDirection.y.mix(color(0x000010), color(0x3366ff));
scene.environmentNode, scene.backgroundBlurriness / backgroundIntensity / backgroundRotation   // plain Scene properties; TSL nodes backgroundBlurriness etc. read them
```

Fog applies to the lit result via `material.fog` (default true); `outputNode` replaces the result **after** fog.

---

## 17. Display

**Blend modes** (vec3 unless noted): `blendBurn blendDodge blendScreen blendOverlay` (base, blend), `blendColor(base: vec4, blend: vec4)` (normal alpha blend).

**Color adjustment:** `grayscale(c, lumCoeffs?)` (returns float since r187; wrap in `vec3()` for a color) `luminance(c, coeffs?) saturation(c, k=1) vibrance(c, k=0) hue(c, radians) posterize(src, steps) cdl(color, slope, offset, power, saturation, lumCoeffs) sepia bleach vignette(color, intensity, smoothness, coord) scanlines(...) colorBleeding`. Alpha: `premultiplyAlpha(c) unpremultiplyAlpha(c)`.

**Tone mapping** (node forms; exposure second): `linearToneMapping reinhardToneMapping cineonToneMapping acesFilmicToneMapping agxToneMapping neutralToneMapping`; generic `toneMapping(THREE.ACESFilmicToneMapping, exposure, color)` / `color.toneMapping(...)`; `toneMappingExposure` (renderer reference). The renderer applies tone mapping at output (`renderer.toneMapping`); materials are rendered in linear HDR and converted in the final output pass.

**Color space:** `workingToColorSpace(node, THREE.SRGBColorSpace)`, `colorSpaceToWorking(node, srcSpace)`, `convertColorSpace(node, src, dst)`, `sRGBTransferEOTF(c)`, `sRGBTransferOETF(c)`. Working space is linear-sRGB by default.

**Output chain:** `renderOutput(colorNode, toneMapping?, outputColorSpace?)` applies renderer tone mapping + output color space. With `RenderPipeline`: `renderPipeline.outputColorTransform = false` and call `renderOutput()` yourself before sRGB-expecting effects (FXAA, sobel). `PostProcessing` is **[deprecated since r183]** -> `new THREE.RenderPipeline(renderer)`; set `renderPipeline.needsUpdate = true` after replacing `outputNode`.

**Normal/bump/env:**

```js
material.normalNode = normalMap(texture(normalTex), vec2(1));        // tangent-space map -> view normal (scale vec2)
material.normalNode = bumpMap(texture(heightTex), float(2));         // height -> perturbed normal
unpackNormal(xy) ; packNormalToRGB(n) ; unpackRGBToNormal(rgb)       // MRT / G-buffer packing
// deprecated since r185: directionToColor -> packNormalToRGB, colorToDirection -> unpackRGBToNormal, directionToFaceDirection -> negateOnBackSide
material.envNode = pmremTexture(envTex, reflectVector, roughness)    // IBL override
```

Environment-related: `reflectView` / `refractView` (for matcap-like or fake refraction), `refract(I, N, eta)`, `getParallaxCorrectNormal(normal, cubeSize, cubePos)`, `triplanarTexture(texX, texY?, texZ?, scale=1, pos=positionLocal, normal=normalLocal)`.

---

## 18. Utilities

**Random / hash:** `hash(seed)` (PCG, input converted to uint, output [0,1)); `rand(uv)` (fract-sin, vec2 -> float); `interleavedGradientNoise(pos)`; `range(min, max)` per-instance random attribute; `vogelDiskSample(i, n, phi)`.

```js
hash(instanceIndex.toFloat())                               // per-instance randomness (stable); hash() takes a float seed
hash(instanceIndex.toFloat().add(7))                        // decorrelated second value
range(vec3(-1), vec3(1))                          // per-instance vec3, e.g. on InstancedMesh/Mesh.count
```

**Noise** (built-in, all in `three/tsl`): Perlin `mx_noise_float(p, amp=1, pivot=0)`, `mx_noise_vec3`, `mx_noise_vec4`; fractal `mx_fractal_noise_float(p, octaves=3, lacunarity=2, diminish=0.5, amp=1)`, `_vec2`, `_vec3`, `_vec4`; cell `mx_cell_noise_float(p)`, `_vec3`; Worley `mx_worley_noise_float(p, jitter=1, style=0)`, `_vec2`, `_vec3(p, jitter, metric)`; `mx_unifiednoise2d/3d(type, ...)`; `triNoise3D(pos, speed, time)` (cheap); `checker(coord)`; `snoise`, `snoiseVec3`, `permute`. Addons: `curlNoise` from `three/addons/tsl/math/curlNoise.js`, `voronoi2d/3d` from `three/addons/tsl/math/voronoiNoise.js`, `bayer` from `.../Bayer.js`.

**MaterialX helpers:** `mx_hsvtorgb mx_rgbtohsv mx_srgb_texture_to_lin_rec709 mx_aastep mx_ramplr mx_ramptb mx_ramp4 mx_splitlr mx_splittb mx_transform_uv(scale, offset, uv) mx_place2d mx_rotate2d(deg) mx_rotate3d(deg, axis) mx_heighttonormal(height, scale, uv) mx_safepower mx_contrast mx_smoothstep mx_add/subtract/multiply/divide/modulo/power mx_atan2 mx_timer mx_frame mx_invert mx_ifgreater/ifgreatereq/ifequal mx_separate`. Rotation units here are degrees, unlike `rotate`/`rotateUV` (radians).

**Shapes / procedural:** `shapeCircle(coord)`, `circle(scale, softness, coord)`, `checker`, `parabola`, `barrelMask`, `scanlines`, `triplanarTexture`.

**Remap, packing:** `remap`, `remapClamp`, `packSnorm2x16 unpackSnorm2x16 packUnorm2x16 unpackUnorm2x16 packHalf2x16 unpackHalf2x16 packSnorm4x8 unpackSnorm4x8 packUnorm4x8 unpackUnorm4x8 pack4xI8 pack4xU8 (+Clamp) unpack4xI8 unpack4xU8 dot4I8Packed dot4U8Packed`.

**Render-to-texture:** `rtt(node, w?, h?, { type, autoUpdate, resolutionScale, wrapS, wrapT, minFilter, magFilter, generateMipmaps, depthBuffer })` returns a TextureNode; `.sample(uv)`; `autoUpdate: false` bakes once; `convertToTexture(node)`; `passTexture(pass, tex)`.

**Post-processing nodes** (`three/addons/tsl/display/*`, each file exports its function): `bloom gaussianBlur boxBlur hashBlur radialBlur bilateralBlur depthAwareBlur dof film dotScreen rgbShift sobel sharpen afterImage lut3D lensflare chromaticAberration fxaa smaa taau traa fsr1 ao ssr ssgi sss vxgi godrays motionBlur outline transition denoise ssaaPass pixelationPass retroPass anaglyphPass stereoPass parallaxBarrierPass toonOutlinePass oitPass`; `premultipliedGaussianBlur` is **[deprecated since r180]** (use `gaussianBlur(..., { premultipliedAlpha: true })`). Core in `three/tsl`: `pass(scene, camera, opts)`, `depthPass`, `mrt({...})`, `renderOutput`, `viewportSharedTexture`. Example:

```js
const rp = new THREE.RenderPipeline(renderer);
const scenePass = pass(scene, camera);
scenePass.setMRT(mrt({ output, normal: normalView }));          // optional
rp.outputNode = scenePass.add(bloom(scenePass, 0.8, 0.2, 0.9)); // render with rp.render() instead of renderer.render()
```

`PassNode` helpers: `getTextureNode(name?) getDepthNode() getLinearDepthNode() getViewZNode() setResolutionScale(s) setMRT(mrt)`.

---

## 19. Context, naming, caching, sub-builds, events

```js
node.setName('wavePattern')      // readable shader var / uniform name (setName(node, name)). label() is deprecated since r179
node.context({ getUV: () => myUV })     // cascade config down the sub-graph
material.contextNode = ...              // material-wide; also pass.contextNode, renderer.contextNode
```

Context keys: `getUV(builder)` (redirect default UV of all textures in the subtree), `getShadow({ light, shadowColorNode })`, `getAO(inputNode, { material })`, `lightingModel`, `getGI`, `getOutput`. Shortcut: `replaceDefaultUV(uvNode | (texNode) => uvNode, node?)`.

```js
material.colorNode = replaceDefaultUV(rotateUV(uv().mul(2), time), materialColor);   // animate the map's UV
```

| API | Purpose |
|---|---|
| `isolate(node)` / `.isolate()` | build the node in a fresh cache scope (needed to evaluate the same node under two different `.context()`s; `cache()` is **[deprecated]** -> `isolate`) |
| `overrideNode(target, replacementOrFn)` / `overrideNodes([[a, b], ...])` | substitute a built-in node (`positionLocal`, `normalView`, `positionView`...) across the subtree/material (dependency injection, e.g. deferred resolve) |
| `uniformFlow(node)` / `.uniformFlow()` | evaluate everything in uniform control flow (needed when derivatives/mip sampling occur inside a branch/`select`); evaluates both branches |
| `Fn(...).once(['POSITION'])`, `subBuild(node, 'POSITION', 'vec3')` | cache per named sub-build layer (VERTEX, POSITION, NORMAL...) |
| `bypass(outputNode, callNode)` / `.bypass(n)` | build `callNode` for its side effects, return `outputNode` (used by `geometryNode`) |
| `expression('discard')`, `.toStack()` | raw snippet / push a node into the current stack |
| `inspect(node, name, cb)` / `.toInspector(name, cb)` | tag for the Inspector panel (WebGPU only) |

Events (register **inside an Fn**, executed on the CPU; the callback receives the `NodeFrame`: `{ time, deltaTime, frameId, renderId, renderer, scene, camera, material, object }` (fields valid for that event's scope)):

```js
OnFrameUpdate(cb)  OnBeforeFrameUpdate(cb)          // per animation frame
OnMaterialUpdate(cb)  OnBeforeMaterialUpdate(cb)    // when a material using this graph is rendered
OnObjectUpdate(cb)  OnBeforeObjectUpdate(cb)  OnAfterObjectUpdate(cb)   // per object draw
OnBeforeRenderPipeline(cb)  OnAfterRenderPipeline(cb)
const main = Fn(() => {
  const k = uniform(0);
  OnMaterialUpdate(({ time }) => { k.value = Math.sin(time); });
  return k;
});
```

Node-level update types (`NodeUpdateType.NONE | FRAME | RENDER | OBJECT`) are what `onFrameUpdate/onRenderUpdate/onObjectUpdate` set; `updateBefore / update / updateAfter` are the lifecycle methods on custom Node subclasses.

---

## 20. Native code

```js
const wavy = wgslFn(`
  fn wavy( pos: vec3<f32>, t: f32 ) -> vec3<f32> { return vec3<f32>( sin( pos.x + t ) ); }
`);                                   // WebGPU only
material.colorNode = wavy({ pos: positionLocal, t: time });   // named OR positional: wavy(positionLocal, time)
const g = glslFn(`vec3 wavy( vec3 pos, float t ) { return vec3( sin( pos.x + t ) ); }`);   // WebGL backend only
wgslFn(code, [includedFnNodes])       // dependencies; helper fns are injected once
// texture + sampler params:  fn f( tex: texture_2d<f32>, s: sampler, uv: vec2<f32> ) ...   call f({ tex: texNode, s: texNode, uv: uv() })
code(src, includes, 'wgsl'|'glsl'|'js')   wgsl(src, includes)  glsl(src, includes)  js(src, includes)   // raw CodeNode, call via .call()
expression('discard' | 'ivec2(1,2)', 'ivec2')                                                        // inline snippet
```

- Function signature parsing: arg names become object keys; type names must match WGSL/GLSL types exactly.
- `wgslFn`/`glslFn` code is backend-specific; cross-backend options: write the TSL equivalent, or use the `glslTFn` pattern from the guide (Fn that checks `builder.renderer.backend.isWebGPUBackend` and transpiles GLSL -> WGSL via `three/addons/transpiler/{Transpiler,GLSLDecoder,WGSLEncoder,TSLEncoder}.js`).
- Transpile GLSL -> TSL source text: `new Transpiler(new GLSLDecoder(), new TSLEncoder()).parse(glslCode)`.

GLSL -> TSL map: `gl_Position` -> `modelViewProjection` or `material.vertexNode`; `position` -> `positionLocal`; `normal` -> `normalLocal`; `uv` -> `uv()`; `modelMatrix` -> `modelWorldMatrix`; `modelViewMatrix` -> same name; `projectionMatrix` -> `cameraProjectionMatrix`; `normalMatrix` -> `modelNormalMatrix`; `varying` -> `varying()`/`.toVarying()`; `gl_FragColor` -> `material.colorNode`/`outputNode`/`fragmentNode`; `uniform T u` -> `uniform(v)`; `texture2D(m, uv)` -> `texture(m, uv)`; `discard` -> `Discard()`; `cameraPosition` -> `cameraPosition`; `gl_FragCoord` -> `screenCoordinate`; `gl_PointCoord` -> `pointUV`.

---

## 21. Debugging

```js
const wave = sin(uv().x.mul(10).add(time)).debug();                    // logs generated shader flow up to this node
node.debug((builder, snippet) => console.log(builder.shaderStage, snippet));
const nameIt = expr.toVar('debugVal');                                 // find it in the generated source
expr.setName('foo');                                                   // named var/uniform
await renderer.debug.getShaderAsync(scene, camera, mesh)               // -> { vertexShader, fragmentShader } (WGSL/GLSL source strings); also renderer.debug.checkShaderErrors / onShaderError / onNodeBuilderCreated
renderer.inspector = new Inspector();                                  // import { Inspector } from 'three/addons/inspector/Inspector.js'
node.toInspector('Water / Depth', n => n.oneMinus());                  // show in Inspector panel
material.fragmentNode = vec4(debugValue.rgb, 1);                       // visualise any value: bypass lighting
renderer.compute / material.needsUpdate = true                         // when edits are not picked up
```

Tips:
- Errors with `TSL:` prefix carry a JS stack trace of where the offending node was created (`captureStackTrace`).
- Visualise a scalar: `material.colorNode = vec3(x)` on `MeshBasicNodeMaterial`.
- WebGPU shader compile failures show WGSL line numbers; use `.toVar('name')` to anchor.
- Chrome WebGPU DevTools / Spector.js / RenderDoc benefit from `setName`.

---

## 22. Top 15 mistakes

1. **Using `Math.*` / JS operators on Nodes.** `Math.sin(time)`, `a + b`, `a > b` do not build shader code. Use `time.sin()`, `a.add(b)`, `a.greaterThan(b)`.
2. **JS `if`/ternary on a Node or `uniform.value`.** Decided once at build. Use `If`, `select`, or a uniform that the shader branches on.
3. **`If/Loop/Switch/.assign/.toVar/Discard` outside `Fn`.** "No stack defined". Wrap in `Fn(() => {...})()` and assign the result to the slot.
4. **Forgetting to invoke the Fn.** `material.colorNode = Fn(() => ...)` is wrong; must be `Fn(...)()`.
5. **Mutating without `.toVar()`.** `const p = positionLocal; p.y.addAssign(1)` mutates a shared singleton / errors. `positionLocal.toVar()` first. (`vec3(...)`/`float(...)` constructor results are assignable.)
6. **`x = y` instead of `x.assign(y)`.** JS reassignment rebinds the JS name only.
7. **Baking values that should be uniforms.** `float(speed)` frozen at build; use `uniform(speed)` and update `.value`. Conversely do not recreate `uniform()` every frame.
8. **Recreating materials/nodes every frame.** New nodes trigger recompiles. Create the graph once, drive it with uniforms/`time`.
9. **Wrong argument order in chained `mix/smoothstep/step`.** `t.mix(a, b)`, `x.smoothstep(lo, hi)`, `x.step(edge)`; the receiver is the factor/value.
10. **Starting a chain on a JS number.** `1.div(x)` fails; write `float(1).div(x)` (or `x.reciprocal()`).
11. **Reading/replacing the wrong slot.** `colorNode` replaces `color`+`map`; to modulate use `materialColor.mul(...)`. `normalNode` replaces `normalMap`/`bumpMap`. Physical slots (`clearcoatNode`, `sheenNode`...) only act if the feature is enabled (`clearcoat > 0` or the node set).
12. **Derivatives / implicit-LOD texture sampling in branches.** Use `.level()`, `.grad()`, or `.uniformFlow()`. Also `dFdx` in the vertex stage is invalid.
13. **Sampling the same TextureNode with new UVs through `.uv()`.** It mutates the node. Use `tex.sample(uvNode)`. For another context for the same node use `.isolate()`.
14. **Using WebGL-only or WebGPU-only code unknowingly.** `wgslFn`, storage buffers writes in vertex/fragment, atomics, storage textures, `subgroup*` need the WebGPU backend; `glslFn` needs the WebGL backend. `three/webgpu` falls back to WebGL2 when WebGPU is unavailable (`new WebGPURenderer({ forceWebGL: true })` forces it).
15. **Forgetting init for compute / using removed APIs.** `renderer.compute()` before init returns a Promise (warns); `await renderer.init()` first or `computeAsync`. `renderAsync`/`clearAsync` are deprecated since r181. `PostProcessing` -> `RenderPipeline`. Old `instance(count, matrix, color)` signature is gone: `instance(matricesAttr, colorsAttr?)`, and `InstancedMesh` is handled automatically by the material.

---

## 23. See also

- tsl-guide: `11-node-material.md`, `12-method-chaining.md`, `13-swizzle.md`, `14-constants-and-conversions.md`, `15-operators.md`, `16-math.md`, `17-function.md`, `18-assignments.md`, `19-variables.md`, `20-properties.md`, `21-array.md`, `22-struct.md`, `23-if-else.md`, `24-switch-case.md`, `25-ternary.md`, `26-loop.md`, `27-vertex-stage-and-varying.md`, `28-compute-stage.md`, `29-events.md`, `30-atomic.md`, `31-attributes.md` to `38-storage-array.md`, `39-coordinate-spaces.md` to `47-viewport.md`, `48-lights.md` to `51-projector-light.md`, `52-fog.md`, `53-background.md`, `54-pass.md` to `58-rtt.md`, `59-timer.md` to `66-debug.md`, `67-blend-modes.md`, `68-color-adjustments.md`, `69-material-inputs.md`, `70-noise.md`, `71-functions.md`, `72-context.md` to `78-sub-builds.md`, `80-transpiler.md`, `81-wgsl.md`, `82-glsl.md` (all in `tsl-guide/`).
- `tsl-reference.md` (every exported function and constant with signatures).
- `node-materials.md` (material slots, lighting models, instancing, recipes).
- https://threejs.org/tsl/ and https://threejs.org/docs/#TSL
