# Normal

(TSL Guide section: Accessors > Normal)

Normal nodes provide access to surface direction vectors at different transformation stages. In TSL, these values are mapped to specific [Coordinate Spaces](#coordinate-spaces) (Geometry, Local, World, or View) to allow precise control over lighting, reflections, and normal mapping.

<code name="xrayExample" default="true">X-Ray</code>
<code name="bumpMapExample">Bump Map</code>

::: api normalGeometry : vec3 - Normal attribute of geometry. :::

::: api normalLocal : vec3 - Local variable for normal. :::

::: api normalView : vec3 - Normalized transformed view normal. :::

::: api normalViewGeometry : vec3 - Normalized view normal. :::

::: api normalWorld : vec3 - Normalized transformed world normal. :::

::: api normalWorldGeometry : vec3 - Normalized world normal. :::

> Note: The transformed term here also includes following the correct orientation of the face, so that the normals are inverted inside the geometry.

> AI: The deprecated `transformedNormalView`, `transformedNormalWorld` and `transformedClearcoatNormalView` nodes were removed in r187. Use `normalView`, `normalWorld` and `clearcoatNormalView` instead.

### Normal Mapping

Normal mapping functions return a perturbed view-space normal that can be assigned to `material.normalNode`:

::: api normalMap( node, scaleNode? ) : vec3 - Perturbs the surface normal using tangent-space normal map data.
- **node**: `vec3` - The normal map data, e.g. `texture( normalTex )`.
- **scaleNode**: `vec2` - (Optional) Controls the intensity of the effect. Defaults to `null`.
:::

::: api bumpMap( textureNode, scaleNode?, normalNode? ) : vec3 - Perturbs the surface normal from height data using screen-space derivatives.
- **textureNode**: `float` - The height data, e.g. `texture( bumpTex ).r`. It must be texture-based, since the texture is sampled at offset UVs to compute the height derivatives.
- **scaleNode**: `float` - (Optional) Controls the intensity of the bump effect. Defaults to `1`.
- **normalNode**: `vec3` - (Optional) The view-space normal to perturb. Defaults to `normalView`.
:::

```js
// Bump details on top of the geometry normal
material.normalNode = bumpMap( texture( bumpTex ).r, 2 );

// Layer bump details on top of a normal map
material.normalNode = bumpMap( texture( bumpTex ).r, 2, normalMap( texture( normalTex ) ) );
```

```tsl xrayExample
import 'scenes/shaderball';
import * as THREE from 'three';
import { normalView, positionViewDirection, color } from 'three/tsl';

// Calculate X-ray factor (opaque at edges, transparent in the center)
const viewDot = normalView.dot( positionViewDirection ).clamp();
const xray = viewDot.oneMinus().pow( 2.0 );

// Assign glowing cyan color and map the X-ray factor to the opacity
model.material.colorNode = color( 0x00f3ff );
model.material.opacityNode = xray;
model.material.transparent = true;
model.material.side = THREE.DoubleSide;
```

```tsl bumpMapExample
import 'scenes/shaderball';
import * as THREE from 'three';
import { texture, uv, normalMap, bumpMap, color, time } from 'three/tsl';

// Load the height and normal textures with repeat wrapping
const loader = new THREE.TextureLoader();

const bumpTex = loader.load( '../examples/textures/brick_bump.jpg' );
bumpTex.wrapS = bumpTex.wrapT = THREE.RepeatWrapping;

const normalTex = loader.load( '../examples/textures/waternormals.jpg' );
normalTex.wrapS = normalTex.wrapT = THREE.RepeatWrapping;

// 1. Animated water ripples from the normal map
const ripples = normalMap( texture( normalTex, uv().mul( 2 ).add( time.mul( 0.05 ) ) ) );

// 2. Layer brick bump details on top of the ripples using the normalNode parameter
const height = texture( bumpTex, uv().mul( 3 ) ).r;

model.material.normalNode = bumpMap( height, 2, ripples );
model.material.colorNode = color( 0xb45f3c );
model.material.roughness = 0.4;
```
