# three.js r186 Geometry

## When to read this
Read when you build, modify, merge, or optimize geometry: custom `BufferGeometry`, attributes and typed arrays, indexed vs non-indexed, groups/multi-material, dynamic updates, lines/points (incl. fat lines), shapes/curves/extrusion, text, procedural voxel meshes, morph targets, and geometry utilities/modifiers. For the built-in primitive constructors table see `fundamentals.md` section 8; this file adds the shape-based ones and everything else.

## Table of contents
1. [BufferGeometry model](#1-buffergeometry-model)
2. [Custom geometry from scratch](#2-custom-geometry-from-scratch)
3. [Attributes, typed arrays, itemSize](#3-attributes-typed-arrays-itemsize)
4. [Index vs non-indexed, normals, tangents](#4-index-vs-non-indexed-normals-tangents)
5. [Dynamic updates](#5-dynamic-updates)
6. [Draw range, groups, multi-material](#6-draw-range-groups-multi-material)
7. [Bounding volumes, transforms, dispose](#7-bounding-volumes-transforms-dispose)
8. [Interleaved and instanced attributes](#8-interleaved-and-instanced-attributes)
9. [Morph attributes](#9-morph-attributes)
10. [BufferGeometryUtils and GeometryUtils](#10-buffergeometryutils-and-geometryutils)
11. [Lines and points](#11-lines-and-points)
12. [Fat lines (Line2, LineSegments2, Wireframe)](#12-fat-lines)
13. [Edges and wireframe geometry](#13-edges-and-wireframe-geometry)
14. [Shape, Path, ShapePath](#14-shape-path-shapepath)
15. [ExtrudeGeometry, ShapeGeometry, Lathe, Tube, Loft](#15-extrude-shape-lathe-tube-loft)
16. [Curves](#16-curves)
17. [Text](#17-text)
18. [Other addon geometries and modifiers](#18-other-addon-geometries-and-modifiers)
19. [Voxel / procedural chunk geometry pattern](#19-voxel-procedural-chunk-geometry-pattern)
20. [Gotchas checklist](#20-gotchas-checklist)
21. [See also](#see-also)

---

## 1. BufferGeometry model
A `BufferGeometry` is a dictionary of named, **parallel** `BufferAttribute`s (item N of every attribute describes vertex N), plus an optional `index`, `groups`, `drawRange`, `morphAttributes`, and bounds. If any part of a vertex differs (position, normal, uv, color...), it is a different vertex. A cube therefore needs 24 vertices (4 per face, because normals/UVs differ per face), 36 indices; non-indexed it needs 36 vertices.

Attribute names are significant to built-in materials:
| name | itemSize | consumer |
|---|---|---|
| `position` | 3 | required for everything |
| `normal` | 3 | lit materials |
| `uv` | 2 | `map`, normal/roughness maps etc. (channel 0) |
| `uv1`, `uv2`, `uv3` | 2 | `Texture.channel` 1-3 (e.g. `aoMap`, `lightMap`) |
| `color` | 3 or 4 | needs `material.vertexColors = true` |
| `tangent` | 4 | anisotropy / some normal-map setups |
| `skinIndex`, `skinWeight` | 4 | `SkinnedMesh` |
| any custom name | 1-4 | your own `ShaderMaterial` / TSL |

Props: `attributes`, `index`, `groups`, `drawRange` (`{start, count: Infinity}`), `boundingBox`, `boundingSphere` (both `null` until computed), `morphAttributes`, `morphTargetsRelative`, `name`, `userData`, `uuid`, `id`, `indirect`/`indirectOffset` (WebGPURenderer only).
Methods: `setAttribute(name, attr)`, `getAttribute(name)`, `hasAttribute(name)`, `deleteAttribute(name)`, `setIndex(arrayOrAttr)`, `getIndex()`, `setFromPoints(points)`, `addGroup(start, count, materialIndex)`, `clearGroups()`, `setDrawRange(start, count)`, `computeVertexNormals()`, `computeTangents()`, `computeBoundingBox()`, `computeBoundingSphere()`, `normalizeNormals()`, `toNonIndexed()`, `applyMatrix4(m)`, `applyQuaternion(q)`, `translate(x,y,z)`, `rotateX/Y/Z(angle)`, `scale(x,y,z)`, `lookAt(v)`, `center()`, `clone()`, `copy(src)`, `toJSON()`, `dispose()`.

---

## 2. Custom geometry from scratch
Indexed quad with normals and UVs:
```js
import * as THREE from 'three';

const positions = new Float32Array([
  -1, -1, 0,   1, -1, 0,   -1, 1, 0,   1, 1, 0,
]);
const normals = new Float32Array([0,0,1,  0,0,1,  0,0,1,  0,0,1]);
const uvs     = new Float32Array([0,0,  1,0,  0,1,  1,1]);

const geometry = new THREE.BufferGeometry();
geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
geometry.setAttribute('normal',   new THREE.BufferAttribute(normals, 3));
geometry.setAttribute('uv',       new THREE.BufferAttribute(uvs, 2));
geometry.setIndex([0, 1, 2,  2, 1, 3]);          // CCW winding = front face (seen from +Z here)

const mesh = new THREE.Mesh(geometry, new THREE.MeshStandardMaterial({ side: THREE.FrontSide }));
```
Shortcuts:
```js
new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(-10,0,0), new THREE.Vector3(0,10,0), new THREE.Vector3(10,0,0)]); // position only; Vector2 -> z=0
geometry.setAttribute('position', new THREE.Float32BufferAttribute(jsArrayOrTyped, 3));  // converts plain arrays
```
Winding: counter-clockwise (viewed from the front) = front face. Wrong winding looks inside-out / vanishes with `FrontSide`; flip index order or use `DoubleSide`.

Builder pattern with JS arrays when size is unknown (convert once at the end):
```js
const pos = [], nrm = [], uv = [];
for (const v of verts) { pos.push(...v.pos); nrm.push(...v.norm); uv.push(...v.uv); }
geometry.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
```
Typed arrays require size up front but are needed for later in-place updates.

---

## 3. Attributes, typed arrays, itemSize
`new BufferAttribute(array: TypedArray, itemSize, normalized = false)`. A plain JS array is NOT accepted by `BufferAttribute` (use `Float32BufferAttribute` etc., which wrap arrays). `array.length` must equal `itemSize * vertexCount`; `attribute.count = array.length / itemSize`.

Typed attribute classes: `Float32BufferAttribute`, `Float16BufferAttribute`, `Int8/Int16/Int32BufferAttribute`, `Uint8/Uint8Clamped/Uint16/Uint32BufferAttribute`.
- `normalized: true` maps integer ranges to 0..1 (unsigned) or -1..1 (signed) in the shader: pack colors as `new Uint8BufferAttribute(rgbaBytes, 4, true)` -> 4x smaller than floats; pack normals as `Int8` normalized.
- `gpuType` only matters for integer arrays (`FloatType`/`IntType`).
- Element accessors: `getX/Y/Z/W(i)`, `setX/Y/Z/W(i, v)`, `setXY`, `setXYZ(i, x, y, z)`, `setXYZW`, `getComponent(i, c)`, `setComponent(i, c, v)`, `set(arrayOrTyped, offset)`, `copyAt(i1, attr, i2)`, `copyArray(arr)`, `applyMatrix3/4`, `applyNormalMatrix`, `transformDirection`.
- `version` increments each time `needsUpdate = true`. `name` optional.
- Index type: `geometry.setIndex(plainArray)` auto-selects `Uint16BufferAttribute` or `Uint32BufferAttribute` (if any index > 65535). If you pass your own attribute, pick `Uint32` for >65535 vertices (WebGL2 supports it). Index arrays are not `Float32`.
- Vertex colors: attribute `color` + `material.vertexColors = true`; floats are interpreted as **linear** working-space (not sRGB). Convert with `new THREE.Color('#ff8800')` (auto-converted from sRGB to linear) then `color.toArray(arr, i*3)`. Raw `Uint8` normalized colors are treated as linear numbers too; convert yourself if authored in sRGB.
- Max attributes per geometry/program: WebGL limit ~16 vertex attributes (`renderer.capabilities.maxAttributes`).

---

## 4. Index vs non-indexed, normals, tangents
- **Indexed**: shared vertices -> less memory, better vertex cache. `computeVertexNormals()` averages face normals at shared vertices (smooth shading). Vertices on UV seams / hard edges must be duplicated, so computed normals show seams there (e.g. cylinder/sphere seam).
- **Non-indexed**: every 3 consecutive vertices = a triangle. `computeVertexNormals()` gives each vertex its face normal (flat shading). `geometry.toNonIndexed()` returns a **new** non-indexed copy (no-op if already non-indexed).
- Smooth shading with hard edges only where angle exceeds a threshold: `BufferGeometryUtils.toCreasedNormals(geometry, creaseAngle = Math.PI / 3)` (returns non-indexed). `mergeVertices` first to restore sharing: `mergeVertices(geometry, tolerance = 1e-4)` merges vertices whose attributes all match within tolerance (returns a new geometry; delete `normal`/`uv` first if you want to merge purely by position).
- `EdgeSplitModifier().modify(geometry, cutOffAngle, tryKeepNormals)` splits vertices at sharp edges (result is always indexed).
- `computeTangents()` (indexed only; requires `position`, `normal`, `uv`) is a custom algorithm; for normal-mapped assets baked elsewhere use `BufferGeometryUtils.computeMikkTSpaceTangents(geometry, MikkTSpace, negateSign = true)` (needs a MikkTSpace WASM module you pass in; de-indexes the geometry; needs position/normal/uv).
- If you animate vertices, recompute normals yourself (`computeVertexNormals()` after update) or set normals from math. `normalizeNormals()` fixes non-unit normals.
- Flat-shaded look without a normal attribute: `material.flatShading = true` (derivative-based).

---

## 5. Dynamic updates
Rules (from "How to update things"):
1. Buffers cannot be resized after first render. Preallocate the maximum size and draw a subset with `setDrawRange`, or build a new geometry (and `dispose()` the old).
2. Changing values requires `attribute.needsUpdate = true` (required after first render).
3. Hint frequent updates: `attribute.setUsage(THREE.DynamicDrawUsage)` **before** the first render (usage cannot change after the buffer is first used). Others: `StaticDrawUsage` (default), `StreamDrawUsage`, plus `*ReadUsage`/`*CopyUsage`.
4. After moving vertices recompute bounds (`computeBoundingSphere()`, `computeBoundingBox()`) or frustum culling/raycast use stale data; or set `mesh.frustumCulled = false` for always-visible dynamic meshes.
5. Index changes: `geometry.index.needsUpdate = true` (same size only).
6. `morphAttributes` data cannot change after the first render; dispose and rebuild.

```js
const MAX = 1000;
const pos = new THREE.BufferAttribute(new Float32Array(MAX * 3), 3);
pos.setUsage(THREE.DynamicDrawUsage);
const geo = new THREE.BufferGeometry().setAttribute('position', pos);
geo.setDrawRange(0, 0);
const points = new THREE.Points(geo, new THREE.PointsMaterial({ size: 4, sizeAttenuation: false }));

function addPoint(x, y, z) {
  const i = geo.drawRange.count;
  pos.setXYZ(i, x, y, z);
  geo.setDrawRange(0, i + 1);
  pos.needsUpdate = true;
  geo.computeBoundingSphere();
}
```
Partial upload (large buffers, few changes):
```js
pos.clearUpdateRanges();
pos.addUpdateRange(start, count);   // start/count are in ARRAY ELEMENTS (floats), not vertices: vertex i -> start = i*3, count = 3
pos.needsUpdate = true;
```
`updateRanges` are merged by the renderer and **cleared automatically after upload**; with an empty list the whole buffer is re-sent. Same API on `InterleavedBuffer` and `Texture`. `attribute.onUpload(cb)` runs after the GPU upload (hook to drop CPU-side copies of static data).

---

## 6. Draw range, groups, multi-material
```js
geometry.setDrawRange(start, count);   // in indices if indexed, else vertices; default (0, Infinity)
```
Groups split one geometry into several draw calls, each with its own material:
```js
geometry.clearGroups();
geometry.addGroup(0, 6, 0);            // start, count (indices if indexed else vertices), materialIndex
geometry.addGroup(6, 6, 1);
const mesh = new THREE.Mesh(geometry, [matA, matB]);   // array order = materialIndex
```
- r186 docs: every vertex/index must belong to exactly one group (no overlaps, no gaps) when groups are used.
- Built-in groups: `BoxGeometry` 6, `CylinderGeometry` 3 (side, top, bottom), `ConeGeometry` 2; `mergeGeometries(list, true)` creates one group per input geometry.
- Each group = one draw call; prefer texture atlas + UVs, vertex colors, or `BatchedMesh` for many looks.
- An out-of-range `materialIndex` renders nothing for that group (no error).
- `BufferGeometryUtils.mergeGroups(geometry)` merges adjacent groups with the same material index.
- `Line`/`Points` accept `material` arrays too.

---

## 7. Bounding volumes, transforms, dispose
- `boundingSphere` is computed automatically when needed (culling, raycasting) but **not recomputed** when vertices change; call `computeBoundingSphere()`. `boundingBox` is never automatic (`computeBoundingBox()`).
- `InstancedMesh` and `SkinnedMesh` have their own bounds (see `fundamentals.md` sec. 15).
- Bake transforms into vertices for one-off edits: `geometry.translate(x,y,z)`, `rotateX/Y/Z(rad)`, `scale(x,y,z)`, `applyMatrix4(m)`, `applyQuaternion(q)`, `center()`, `lookAt(v)`. Do NOT use in a render loop (O(vertices), uploads each time); use `mesh.position/rotation/scale`.
- Center text or imported geometry: `geometry.center()`.
- Reuse geometries across meshes; `geometry.clone()` deep-copies attributes.
- `geometry.dispose()` frees GPU buffers (fires `dispose` event); required when discarding geometry, otherwise GPU memory leaks. Disposing a shared geometry breaks the others (re-uploaded on next use, but it is wasted work).
- Serialization: `toJSON()` / `BufferGeometryLoader`.
- Memory estimate: `BufferGeometryUtils.estimateBytesUsed(geometry)`.

---

## 8. Interleaved and instanced attributes
### InterleavedBuffer / InterleavedBufferAttribute
Store several attributes in one buffer (better cache locality, fewer buffer binds).
```js
// vertex: x y z  u v  (stride 5 floats)
const ib = new THREE.InterleavedBuffer(new Float32Array([ /* xyzuv ... */ ]), 5);
geometry.setAttribute('position', new THREE.InterleavedBufferAttribute(ib, 3, 0));  // (buffer, itemSize, offset, normalized)
geometry.setAttribute('uv',       new THREE.InterleavedBufferAttribute(ib, 2, 3));
ib.setUsage(THREE.DynamicDrawUsage); ib.needsUpdate = true;                          // update the buffer, not the attributes
```
- `needsUpdate`/`updateRanges`/`usage`/`stride`/`count` live on `InterleavedBuffer`; `InterleavedBufferAttribute` has `data`, `offset`, `itemSize`, `normalized`, and the same getX/setXYZ accessors.
- Helpers: `BufferGeometryUtils.interleaveAttributes([attrs])` (returns `null` on failure), `deinterleaveAttribute(attr)`, `deinterleaveGeometry(geometry)`. `mergeAttributes` does NOT support interleaved attributes.
- `InstancedInterleavedBuffer(array, stride, meshPerAttribute)` for instanced interleaved data.

### InstancedBufferGeometry / InstancedBufferAttribute (custom instancing)
```js
const base = new THREE.PlaneGeometry(1, 1);
const geo = new THREE.InstancedBufferGeometry().copy(base);     // copies attributes/index
geo.instanceCount = 1000;                                       // how many instances to draw
geo.setAttribute('offset', new THREE.InstancedBufferAttribute(new Float32Array(1000 * 3), 3));   // (array, itemSize, normalized, meshPerAttribute = 1)
```
`meshPerAttribute` = how many instances share one value (1 = per instance). Consume `offset` in a custom `ShaderMaterial`/`RawShaderMaterial` (WebGL) or TSL `attribute('offset')` (WebGPU). For plain transforms prefer `InstancedMesh(geometry, material, count)` + `setMatrixAt(i, matrix)` + `setColorAt(i, color)` + `instanceMatrix.needsUpdate = true`; for many different geometries `BatchedMesh(maxInstanceCount, maxVertexCount, maxIndexCount, material)`.
`GLBufferAttribute` wraps an existing WebGLBuffer (advanced, WebGL only). `StorageBufferAttribute` / `StorageInstancedBufferAttribute` / `IndirectStorageBufferAttribute` are for WebGPURenderer compute.

---

## 9. Morph attributes
Blend shapes for position (and optionally normal/color) on `Mesh`, `Line`, `Points`.
```js
geometry.morphAttributes.position = [
  new THREE.Float32BufferAttribute(targetAPositions, 3),   // same vertex count as base
  new THREE.Float32BufferAttribute(targetBPositions, 3),
];
geometry.morphAttributes.normal = [ /* optional, same length */ ];
geometry.morphTargetsRelative = false;     // false: targets are absolute positions; true: offsets from base

const mesh = new THREE.Mesh(geometry, material);
mesh.updateMorphTargets();                 // builds morphTargetInfluences + morphTargetDictionary
mesh.morphTargetInfluences[0] = 0.5;       // 0..1 (can exceed)
mesh.morphTargetDictionary;                // name -> index (set attribute.name on each morph attr for names)
```
- `Mesh.getVertexPosition(index, target)` returns the morphed/skinned local position.
- Do not change morph data after first render: `dispose()` and rebuild.
- glTF morph targets work out of the box (GLTFLoader fills `morphAttributes`).
- Needs morph support compiled into the program: adding morph targets to a mesh after first render requires `material.needsUpdate = true`.
- Use `BufferGeometryUtils.computeMorphedAttributes(object)` to bake the current morphed/skinned state (for decals, raytracing).

---

## 10. BufferGeometryUtils and GeometryUtils
```js
import * as BufferGeometryUtils from 'three/addons/utils/BufferGeometryUtils.js';
import * as GeometryUtils from 'three/addons/utils/GeometryUtils.js';
```
| function | purpose / gotcha |
|---|---|
| `mergeGeometries(geometries, useGroups = false)` | One geometry (one draw call). All inputs must have the same attribute set and all indexed or all non-indexed; otherwise returns `null` (console error). Bake each mesh's transform first: `g.clone().applyMatrix4(mesh.matrixWorld)`. `useGroups: true` -> one group per source (use with a material array). Renamed from the old `mergeBufferGeometries`. |
| `mergeAttributes(attributes)` | merge compatible `BufferAttribute`s; `null` on mismatch; no interleaved |
| `mergeVertices(geometry, tolerance = 1e-4)` | weld duplicates -> indexed, smoother `computeVertexNormals` |
| `mergeGroups(geometry)` | merge adjacent same-material groups |
| `toCreasedNormals(geometry, creaseAngle = PI/3)` | smooth except sharp edges |
| `toTrianglesDrawMode(geometry, drawMode)` | convert `TriangleStripDrawMode`/`TriangleFanDrawMode` to triangles (in place) |
| `computeMikkTSpaceTangents(geometry, MikkTSpace, negateSign)` | MikkTSpace tangents (matches baker tools); de-indexes |
| `computeMorphedAttributes(object)` | bake morph/skin pose |
| `deepCloneAttribute(attr)` | deep copy incl. interleaved |
| `interleaveAttributes` / `deinterleaveAttribute` / `deinterleaveGeometry` | see sec. 8 |
| `estimateBytesUsed(geometry)` | attribute byte count |

Merge example (static scenery, 1 draw call instead of N):
```js
const geos = [];
scene.traverse((o) => {
  if (!o.isMesh) return;
  const g = o.geometry.clone().applyMatrix4(o.matrixWorld);
  for (const k of Object.keys(g.attributes)) if (!['position','normal','uv'].includes(k)) g.deleteAttribute(k); // normalize attribute sets
  geos.push(g);
});
const merged = BufferGeometryUtils.mergeGeometries(geos);   // null if incompatible
```
Merging loses per-object culling/picking/transform: for many copies of one geometry use `InstancedMesh`; for static distinct meshes with one material use merge.

`GeometryUtils`: `hilbert2D(center, size, iterations, v0..v3)`, `hilbert3D(center, size, iterations, v0..v7)` -> `Vector3[]` points of a Hilbert curve; `gosper(size)` -> flat number array in XY plane. Feed to `BufferGeometry.setFromPoints` / `Line`.

---

## 11. Lines and points
```js
const geometry = new THREE.BufferGeometry().setFromPoints(points);      // Vector3[]
new THREE.Line(geometry, new THREE.LineBasicMaterial({ color: 0x0000ff }));     // open strip: v0-v1-v2...
new THREE.LineLoop(geometry, material);                                          // closes last->first
new THREE.LineSegments(geometry, material);                                      // pairs: (v0,v1) (v2,v3) ...
new THREE.Points(geometry, new THREE.PointsMaterial({ color: 0xff0000, size: 0.2 })); // size: world units (sizeAttenuation true) or px (false)
```
- Materials: `LineBasicMaterial`, `LineDashedMaterial` (needs `line.computeLineDistances()` after geometry changes; props `dashSize`, `gapSize`, `scale`), `PointsMaterial`. Mesh materials do not work on lines.
- **`linewidth` is ignored by WebGL line materials (always 1px)** on virtually all platforms. For thick lines use `Line2` (sec. 12) or a mesh/tube.
- Lines/Points/LineSegments can use `vertexColors: true` with a `color` attribute.
- Raycasting: `raycaster.params.Line.threshold` and `.Points.threshold` (default 1 world unit each) control pick tolerance. Hit has `distanceToRay` for Points.
- Points as particles: update positions with `needsUpdate`, sprite texture via `PointsMaterial.map` + `alphaTest`/`transparent`, `depthWrite: false` for additive blends. Per-point size needs custom shader (or `Sprite`s/`InstancedMesh`).
- Lines have no lighting or shadows; `Line`/`Points` support `morphTargetInfluences`.
- Geometry from curves: `new THREE.BufferGeometry().setFromPoints(curve.getPoints(50))`.
- Closed curve: either `LineLoop` or repeat the first point.

---

## 12. Fat lines
Screen-space triangle-strip lines with real width. Addons; WebGLRenderer versions in `three/addons/lines/*.js` (WebGPU versions live in `lines/webgpu/`, e.g. `Wireframe`).
```js
import { Line2 } from 'three/addons/lines/Line2.js';
import { LineGeometry } from 'three/addons/lines/LineGeometry.js';   // note: the api doc's import line contains a typo; the export is `LineGeometry`
import { LineMaterial } from 'three/addons/lines/LineMaterial.js';
import { LineSegments2 } from 'three/addons/lines/LineSegments2.js';
import { LineSegmentsGeometry } from 'three/addons/lines/LineSegmentsGeometry.js';
import { Wireframe } from 'three/addons/lines/Wireframe.js';
import { WireframeGeometry2 } from 'three/addons/lines/WireframeGeometry2.js';

const geometry = new LineGeometry();
geometry.setPositions([0,0,0, 1,1,0, 2,0,0]);       // flat xyz (Float32Array | number[])
geometry.setColors([1,0,0, 0,1,0, 0,0,1]);          // optional rgb per vertex; needs material.vertexColors = true
// geometry.setFromPoints(vector3s); geometry.fromLine(line)

const material = new LineMaterial({ color: 0xffffff, linewidth: 5, vertexColors: true });
const line = new Line2(geometry, material);
line.computeLineDistances();                         // only needed for dashed
scene.add(line);
```
`LineMaterial` props: `linewidth` (CSS px by default; world units if `worldUnits: true`), `worldUnits`, `dashed`, `dashSize`, `gapSize`, `dashScale`, `dashOffset`, `resolution` (Vector2, viewport px), `alphaToCoverage` (smoother edges with MSAA), `color`, `opacity`.
Gotchas:
- `resolution` must match the viewport; `LineSegments2.onBeforeRender` updates it for visible objects, but if lines look wrong after a resize/pixel-ratio change, set `material.resolution.set(w, h)` yourself.
- `LineSegments2` + `LineSegmentsGeometry`: pairs of vertices (`setPositions` flat array of segment endpoints); converters: `fromEdgesGeometry(g)`, `fromWireframeGeometry(g)`, `fromMesh(mesh)`, `fromLineSegments(ls)`.
- Thick wireframe/edges: `new Wireframe(new WireframeGeometry2(geo), lineMaterial)` (`Wireframe.computeLineDistances()`); `LineSegments2.raycast` supported.
- Fat lines cost more per vertex (instanced quads); they ignore `LineBasicMaterial`.
- Alternative community option: THREE.MeshLine.

---

## 13. Edges and wireframe geometry
```js
new THREE.LineSegments(new THREE.EdgesGeometry(geometry, 15), new THREE.LineBasicMaterial({ color: 0x000000 })); // thresholdAngle in DEGREES (default 1): only edges where adjacent faces differ by > angle
new THREE.LineSegments(new THREE.WireframeGeometry(geometry), material);                                          // every triangle edge, ignores sharing
mesh.material.wireframe = true;                                                                                    // built-in, no extra geometry; 1px lines
```
`EdgesGeometry` of a geometry with duplicated vertices (non-indexed) needs `mergeVertices` first or it will draw all duplicates as edges. Add the line object as a child of the mesh to share its transform. Use `material.polygonOffset` on the solid mesh to avoid z-fighting with overlaid edges.

---

## 14. Shape, Path, ShapePath
2D path system in the XY plane. `Shape extends Path extends CurvePath`.
```js
const shape = new THREE.Shape();
shape.moveTo(0, 0);
shape.lineTo(0, 4);
shape.bezierCurveTo(0, 6, 4, 6, 4, 4);   // (cp1x, cp1y, cp2x, cp2y, x, y)
shape.quadraticCurveTo(x1, y1, x, y);
shape.absarc(2, 2, 1, 0, Math.PI * 2, false);
shape.lineTo(4, 0);

const hole = new THREE.Path();
hole.absarc(2, 2, 0.5, 0, Math.PI * 2, true);   // holes wind opposite
shape.holes.push(hole);
```
- `Shape(points?)`, `Path(points?)`, `Path` methods: `moveTo`, `lineTo`, `quadraticCurveTo`, `bezierCurveTo`, `splineThru(pts)`, `arc/absarc(x, y, r, a0, a1, clockwise)`, `ellipse/absellipse(x, y, xr, yr, a0, a1, clockwise, rotation)`, `setFromPoints`, `currentPoint`.
- `Shape.holes: Path[]`, `shape.extractPoints(divisions)` -> `{shape: Vector2[], holes: Vector2[][]}`, `getPointsHoles(divisions)`.
- `ShapePath` (what `SVGLoader` produces): `moveTo/lineTo/quadraticCurveTo/bezierCurveTo/splineThru`, `subPaths`, `currentPath`, `color`, `toShapes()` -> `Shape[]` (auto-detects holes from winding). Typical: `SVGLoader.parse(svgText).paths` -> `path.toShapes()`; SVG's Y axis points down, so `mesh.scale.y = -1` or flip.
- `ShapeUtils`: `area(contour)`, `isClockWise(pts)`, `triangulateShape(contour, holes)` -> triangle index triples (uses `Earcut`); `Earcut.triangulate(data, holeIndices, dim)` low-level.
- Self-intersecting or duplicate-point contours fail triangulation silently (missing faces).
- Winding: outer contour counter-clockwise, holes clockwise (ExtrudeGeometry/ShapeGeometry reverse automatically when needed, but correct input avoids inverted normals).

---

## 15. Extrude, Shape, Lathe, Tube, Loft
```js
// ExtrudeGeometry(shapes, options): depth default 1 (units along +Z), bevelEnabled DEFAULT TRUE
new THREE.ExtrudeGeometry(shape, {
  depth: 2,                // extrusion depth
  steps: 1,                // subdivisions along depth
  curveSegments: 12,       // points per curve
  bevelEnabled: true,      // default true in r186 (bevelThickness 0.2, bevelSize bevelThickness-0.1, bevelOffset 0, bevelSegments 3)
  bevelThickness: 0.2, bevelSize: 0.1, bevelOffset: 0, bevelSegments: 3,
  extrudePath: curve3,     // extrude along a 3D curve; bevels NOT supported then
  UVGenerator: customUV,   // object with generateTopUV / generateSideWallUV
});
new THREE.ShapeGeometry(shape, curveSegments = 12);      // flat triangulated fill, in XY plane, UV = xy
new THREE.LatheGeometry(points2D, segments = 12, phiStart = 0, phiLength = 2*Math.PI);  // revolve around Y; x >= 0; order points bottom->top for outward normals
new THREE.TubeGeometry(curve3, tubularSegments = 64, radius = 1, radialSegments = 8, closed = false);  // has .tangents/.normals/.binormals (Frenet frames)
```
- Extrude groups: group 0 = caps (front/back), group 1 = sides. Use `[capMat, sideMat]`.
- Extrusion grows along **+Z** from the shape plane; rotate the mesh to lay flat. Bevels extend the geometry beyond the shape: `bevelSize` positive grows outline, `bevelOffset` shifts start; set `bevelEnabled: false` for exact sizes (common surprise: default bevel grows model by ~0.1 and adds 0.4 thickness).
- `Curve.computeFrenetFrames(segments, closed)` -> `{tangents, normals, binormals}`; Frenet frames flip on straight/inflected paths (twists in TubeGeometry/extrudePath); use a custom frame or Loft sections.
- `TubeGeometry.parameters.path`; tube normals point outward.

### LoftGeometry (addon, new)
```js
import { LoftGeometry } from 'three/addons/geometries/LoftGeometry.js';
// sections: Vector3[][] each with the same point count (>= 2 sections). Counter-clockwise looking back from the end gives outward normals; reverse point order if inside out.
new LoftGeometry(sections, { closed: true /*ring vs open strip*/, capStart: false, capEnd: false });
```
Generalizes Lathe (fixed profile revolved) and Tube (circle swept along a path).

---

## 16. Curves
`Curve` (abstract): `getPoint(t)` t in 0..1 by parameter; `getPointAt(u)` by arc length; `getPoints(divisions = 5)` (divisions+1 points, parametric spacing); `getSpacedPoints(divisions = 5)` (equal arc length); `getTangent(t)`, `getTangentAt(u)`, `getLength()`, `getLengths(divisions)`, `computeFrenetFrames(segments, closed)`, `updateArcLengths()`, `arcLengthDivisions` (default 200), `clone/copy/toJSON/fromJSON`.
**If you mutate a curve's control points call `curve.updateArcLengths()` (or set `curve.needsUpdate = true`)** so `getPointAt/getLength` recompute.

2D curves (return `Vector2`): `LineCurve`, `QuadraticBezierCurve`, `CubicBezierCurve`, `SplineCurve`, `EllipseCurve`, `ArcCurve`.
3D curves (return `Vector3`): `LineCurve3`, `QuadraticBezierCurve3`, `CubicBezierCurve3(v0, v1, v2, v3)`, `CatmullRomCurve3(points, closed = false, curveType = 'centripetal', tension = 0.5)`; `curveType`: `'centripetal'` (no cusps/self-intersections, default), `'chordal'`, `'catmullrom'` (uses `tension`). Addon curves: `NURBSCurve`, `NURBSSurface` (+ `module-NURBSUtils`) from `three/addons/curves/NURBS*.js`; `HelixCurve`, `KnotCurve`, `VivianiCurve`, `HeartCurve` etc. from `three/addons/curves/CurveExtras.js`.
`CurvePath`: `add(curve)`, `curves[]`, `closePath()`, `autoClose`, `getCurveLengths()`, `getPoint(t)`; `Path`/`Shape` extend it.

```js
const curve = new THREE.CatmullRomCurve3([
  new THREE.Vector3(-10, 0, 10), new THREE.Vector3(-5, 5, 5),
  new THREE.Vector3(0, 0, 0),    new THREE.Vector3(5, -5, 5),
], false, 'centripetal');

const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints(curve.getPoints(100)), new THREE.LineBasicMaterial({ color: 0xff0000 }));
const tube = new THREE.Mesh(new THREE.TubeGeometry(curve, 100, 0.4, 8, false), new THREE.MeshStandardMaterial());

// move an object along it (loop)
const p = new THREE.Vector3(), tan = new THREE.Vector3();
function follow(obj, u /*0..1*/) { curve.getPointAt(u % 1, p); obj.position.copy(p); obj.lookAt(p.clone().add(curve.getTangentAt(u % 1, tan))); }
```
`getPoints` with parametric spacing gives uneven spacing on non-uniform control point spacing; use `getSpacedPoints` for even distribution. `CurveModifier`/`CurveModifierGPU` (addons/modifiers) bend meshes along a curve.

---

## 17. Text
Options (pick by use case): DOM overlay + CSS (easiest, sharp, accessible); `CSS2DRenderer`/`CSS3DRenderer` (DOM labels tracking 3D positions); canvas-drawn `CanvasTexture` on a plane (cheap labels, resolution-limited); troika-three-text (community, SDF, best for lots of text); modeled/exported meshes; procedural `TextGeometry`.

```js
import { FontLoader } from 'three/addons/loaders/FontLoader.js';
import { TextGeometry } from 'three/addons/geometries/TextGeometry.js';

const font = await new FontLoader().loadAsync('three/examples/fonts/helvetiker_regular.typeface.json'); // or serve the json yourself
const geometry = new TextGeometry('three.js', {
  font,                 // Font instance (required)
  size: 100,            // default 100 !
  depth: 50,            // default 50
  curveSegments: 12,    // default 12
  steps: 1,
  bevelEnabled: false,  // default false for TextGeometry (true for ExtrudeGeometry)
  bevelThickness: 10, bevelSize: 8, bevelOffset: 0, bevelSegments: 3,   // defaults
  direction: 'ltr',     // 'ltr' | 'rtl' | 'tb'
});
geometry.center();      // origin is left baseline; center for rotation/pivot (or computeBoundingBox + getCenter)
```
- Defaults are huge (`size: 100`, `depth: 50`): pass explicit small values like `size: 1, depth: 0.2` for world-unit scenes. Manual example uses `size: 3.0, depth: .2, bevelThickness: .15, bevelSize: .3, bevelSegments: 5`.
- Bundled fonts (`examples/fonts/`, import path `three/examples/fonts/...` via package exports): `helvetiker_regular/bold`, `optimer_regular/bold`, `gentilis_regular/bold`, `droid/` set. Custom fonts: convert TTF to typeface.js JSON (facetype.js) -> `FontLoader.parse(json)` returns `Font`.
- `FontLoader.load(url, onLoad, onProgress, onError)` / `loadAsync` / `parse(json)`. `Font.generateShapes(text, size, direction)` -> `Shape[]` for use with `ShapeGeometry`/`ExtrudeGeometry` (flat text: `new ShapeGeometry(font.generateShapes('Hi', 1))`).
- Glyph triangulation is heavy for long strings; cache geometry; flat text via `ShapeGeometry` is much cheaper than extruded + bevelled.
- Only glyphs in the JSON font are available (Latin subset in bundled fonts).

---

## 18. Other addon geometries and modifiers
| Class | Import | Use |
|---|---|---|
| `RoundedBoxGeometry(width=1, height=1, depth=1, segments=2, radius=0.1)` | `three/addons/geometries/RoundedBoxGeometry.js` | box with rounded edges |
| `ConvexGeometry(points: Vector3[])` | `.../ConvexGeometry.js` | convex hull of a point set |
| `DecalGeometry(mesh, position, orientation: Euler, size: Vector3)` | `.../DecalGeometry.js` | projected decal mesh clipped to `mesh`; add as new Mesh with `polygonOffset` material (`transparent`, `depthTest`); distorts around corners; uses the mesh's base (non-morphed) geometry (use `computeMorphedAttributes` for skinned) |
| `ParametricGeometry(func(u, v, target: Vector3), slices, stacks)` | `.../ParametricGeometry.js` | surface from function; `ParametricFunctions` has presets |
| `LoftGeometry(sections, options)` | `.../LoftGeometry.js` | see sec. 15 |
| `TeapotGeometry`, `BoxLineGeometry`, `TextGeometry` | `.../geometries/` | utah teapot; box-grid lines; text |
| `MeshSurfaceSampler(mesh)` | `three/addons/math/MeshSurfaceSampler.js` | weighted random points on a mesh surface |
| `SimplifyModifier().modify(geometry, count)` | `three/addons/modifiers/SimplifyModifier.js` | **async (returns Promise)**; `count` = approximate number of vertices to remove; result contains only referenced vertices; needs indexed/merged vertices to be effective |
| `TessellateModifier(maxEdgeLength = 0.1, maxIterations = 6).modify(geometry)` | `.../TessellateModifier.js` | subdivides long triangles (returns geometry; non-indexed result) |
| `EdgeSplitModifier().modify(geometry, cutOffAngle, tryKeepNormals)` | `.../EdgeSplitModifier.js` | split at sharp edges (sec. 4) |

```js
// scatter 200 instances on a surface
const sampler = new MeshSurfaceSampler(surfaceMesh).setWeightAttribute('color').build();   // weight attribute optional; config BEFORE build()
const inst = new THREE.InstancedMesh(smallGeo, smallMat, 200);
const p = new THREE.Vector3(), n = new THREE.Vector3(), m = new THREE.Matrix4();
for (let i = 0; i < 200; i++) { sampler.sample(p, n); m.makeTranslation(p.x, p.y, p.z); inst.setMatrixAt(i, m); }   // sample(position, normal?, color?, uv?)
inst.instanceMatrix.needsUpdate = true;
```
`MeshSurfaceSampler`: `setWeightAttribute(name)`, `setRandomGenerator(fn)`, `build()` O(n), `sample()` O(log n); sampled positions are in the mesh's local space.
Other GeometryCompression: `module-GeometryCompressionUtils` (quantize normals/positions/UVs).
Also in `three/addons/objects/`: `MarchingCubes`, `Sky`, `Water`, `Reflector`, `Lensflare`; in `three/addons/math/`: `ConvexHull`, `Octree`, `OBB`.

---

## 19. Voxel / procedural chunk geometry pattern
Minecraft-like worlds: do not create one mesh per voxel (too many draw calls) and do not just merge cube geometries (hidden faces between neighbors double the triangles). Build the geometry yourself:
1. Store voxels in a typed array; divide space into **cells/chunks** (e.g. 32x32x32), allocate only non-empty ones, key by `"cx,cy,cz"`.
2. For each solid voxel, for each of 6 neighbors: emit a face (4 vertices + 6 indices, with position/normal/uv) only if the neighbor is empty (`getVoxel(x+dx, y+dy, z+dz)` may look into the adjacent cell).
3. UVs from a texture atlas: tile size / atlas size (one column per voxel type, rows for top/side/bottom); set `texture.magFilter = NearestFilter` for the pixel look.
4. One `Mesh` per cell; build with typed/dynamic arrays then:
```js
geometry.setAttribute('position', new THREE.BufferAttribute(new Float32Array(positions), 3));
geometry.setAttribute('normal',   new THREE.BufferAttribute(new Float32Array(normals), 3));
geometry.setAttribute('uv',       new THREE.BufferAttribute(new Float32Array(uvs), 2));
geometry.setIndex(indices);
geometry.computeBoundingSphere();   // or set the sphere to the cell bounds manually (cheaper)
```
5. On edit (`setVoxel`) regenerate the affected cell and any neighbor cells touched by an edge voxel; reuse the Mesh, replace attributes (new arrays since sizes change) and `dispose()` the old geometry; delete empty cells.
6. Picking: custom voxel ray traversal (fast DDA) returns position and face normal; raycasting meshes is slower.
Same pattern applies to marching cubes, terrain tiles, heightfields (use `PlaneGeometry` + edit `position.z` + `computeVertexNormals()`).

---

## 20. Gotchas checklist
- "Float32Array length not a multiple of itemSize" or NaN bounding sphere warning: array length mismatch or NaN in positions (`Computed radius is NaN / min/max have NaN values`). Validate inputs; three.js does not.
- Passing a plain `Array` to `new BufferAttribute` fails; use typed array or `Float32BufferAttribute`.
- Names must match (`position`, `normal`, `uv`, `color`); typos give a flat/blank render with no error.
- Triangles invisible: winding order or missing `side: DoubleSide`.
- Black/flat lighting: missing `normal` attribute (call `computeVertexNormals()`).
- Changed attribute but nothing happens: forgot `attribute.needsUpdate = true`; changed index/size: rebuild geometry.
- Culled when visible: stale `boundingSphere`; recompute or `frustumCulled = false`.
- `mergeGeometries` returned `null`: attribute names/itemSize/index presence differ; delete extras or `toNonIndexed()` consistently.
- `linewidth > 1` does nothing on `LineBasicMaterial`: use `Line2`.
- Memory leaks: `geometry.dispose()` for every discarded geometry (incl. from loaders/primitives rebuilt each frame).
- Do not rebuild primitives each frame (e.g. `new BoxGeometry` per update); scale the mesh or modify attributes.
- `geometry.parameters` is a snapshot; editing it changes nothing.
- Primitive UV layouts differ (Box: per face 0..1; Sphere: equirect; Cylinder: side wraps once); regenerate `uv1` if you need lightmaps.
- Large index buffers: arrays > 65535 vertices need Uint32 (auto when using `setIndex(array)`).

---

## See also
- API pages: `references/api/BufferGeometry.md`, `BufferAttribute.md`, `Float32BufferAttribute.md`, `InterleavedBuffer.md`, `InterleavedBufferAttribute.md`, `InstancedBufferGeometry.md`, `InstancedBufferAttribute.md`, `BoxGeometry.md`, `CapsuleGeometry.md`, `CircleGeometry.md`, `ConeGeometry.md`, `CylinderGeometry.md`, `DodecahedronGeometry.md`, `EdgesGeometry.md`, `ExtrudeGeometry.md`, `IcosahedronGeometry.md`, `LatheGeometry.md`, `OctahedronGeometry.md`, `PlaneGeometry.md`, `PolyhedronGeometry.md`, `RingGeometry.md`, `ShapeGeometry.md`, `SphereGeometry.md`, `TetrahedronGeometry.md`, `TorusGeometry.md`, `TorusKnotGeometry.md`, `TubeGeometry.md`, `WireframeGeometry.md`, `Shape.md`, `Path.md`, `ShapePath.md`, `Curve.md`, `CurvePath.md`, `CatmullRomCurve3.md`, `CubicBezierCurve3.md`, `module-BufferGeometryUtils.md`, `module-GeometryUtils.md`, `TextGeometry.md`, `FontLoader.md`, `Font.md`, `Line.md`, `LineSegments.md`, `LineLoop.md`, `Points.md`, `Line2.md`, `LineGeometry.md`, `LineMaterial.md`, `LineSegments2.md`, `LineSegmentsGeometry.md`, `Wireframe.md`, `WireframeGeometry2.md`, `MeshSurfaceSampler.md`, `SimplifyModifier.md`, `TessellateModifier.md`, `EdgeSplitModifier.md`, `ConvexGeometry.md`, `DecalGeometry.md`, `RoundedBoxGeometry.md`, `ParametricGeometry.md`, `LoftGeometry.md`, `Earcut.md`, `ShapeUtils.md`, `InstancedMesh.md`, `BatchedMesh.md`
- Manual: https://threejs.org/manual/#custom-buffergeometry, #drawing-lines, #creating-text, #voxel-geometry, #primitives, #how-to-update-things, #optimize-lots-of-objects
- Docs: https://threejs.org/docs/#BufferGeometry, #BufferAttribute, #ExtrudeGeometry, #TextGeometry, #Line2, #CatmullRomCurve3, #module-BufferGeometryUtils
- Sibling: `fundamentals.md` (primitives table, update rules), `api-index.txt`
