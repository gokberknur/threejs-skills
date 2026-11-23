# Constants and Conversions

(TSL Guide section: Syntax > Constants and Conversions)

Input functions can be used to create constants and do explicit conversions.

> Note: Conversions are also performed automatically if the output and input are of different types.

::: api float( value ) : float - Convert or create a float node.
- **value**: `Node | number`
:::

::: api int( value ) : int - Convert or create an integer node.
- **value**: `Node | number`
:::

::: api uint( value ) : uint - Convert or create an unsigned integer node.
- **value**: `Node | number`
:::

::: api bool( value ) : bool - Convert or create a boolean node.
- **value**: `Node | boolean`
:::

::: api color( ...value ) : color - Convert or create a color node.
- **...value**: `Node | Color | string | number`
:::

::: api vec2( ...value ) : vec2 - Convert or create a Vector2 node.
- **...value**: `Node | Vector2 | number`
:::

::: api vec3( ...value ) : vec3 - Convert or create a Vector3 node.
- **...value**: `Node | Vector3 | number`
:::

::: api vec4( ...value ) : vec4 - Convert or create a Vector4 node.
- **...value**: `Node | Vector4 | number`
:::

::: api mat2( ...value ) : mat2 - Convert or create a Matrix2 node.
- **...value**: `Node | Matrix2 | number`
:::

::: api mat3( ...value ) : mat3 - Convert or create a Matrix3 node.
- **...value**: `Node | Matrix3 | number`
:::

::: api mat4( ...value ) : mat4 - Convert or create a Matrix4 node.
- **...value**: `Node | Matrix4 | number`
:::

::: api ivec2( ...value ) : ivec2 - Convert or create an integer Vector2 node.
- **...value**: `Node | number`
:::

::: api ivec3( ...value ) : ivec3 - Convert or create an integer Vector3 node.
- **...value**: `Node | number`
:::

::: api ivec4( ...value ) : ivec4 - Convert or create an integer Vector4 node.
- **...value**: `Node | number`
:::

::: api uvec2( ...value ) : uvec2 - Convert or create an unsigned integer Vector2 node.
- **...value**: `Node | number`
:::

::: api uvec3( ...value ) : uvec3 - Convert or create an unsigned integer Vector3 node.
- **...value**: `Node | number`
:::

::: api uvec4( ...value ) : uvec4 - Convert or create an unsigned integer Vector4 node.
- **...value**: `Node | number`
:::

::: api bvec2( ...value ) : bvec2 - Convert or create a boolean Vector2 node.
- **...value**: `Node | boolean`
:::

::: api bvec3( ...value ) : bvec3 - Convert or create a boolean Vector3 node.
- **...value**: `Node | boolean`
:::

::: api bvec4( ...value ) : bvec4 - Convert or create a boolean Vector4 node.
- **...value**: `Node | boolean`
:::

Example:

```js
import { vec2, positionWorld } from 'three/tsl';

// constant
material.colorNode = vec2( 0.5, 0.5 );

// three.js object
material.colorNode = vec2( new THREE.Vector2( 0.5, 0.5 ) );

// conversion
material.colorNode = vec2( positionWorld ); // result positionWorld.xy
```

### Method chaining conversions

It is also possible to perform conversions using the **method chaining**:

::: api .toFloat() : float - Convert the node value to float. :::

::: api .toInt() : int - Convert the node value to integer. :::

::: api .toUint() : uint - Convert the node value to unsigned integer. :::

::: api .toBool() : bool - Convert the node value to boolean. :::

::: api .toColor() : color - Convert the node value to color. :::

::: api .toVec2() : vec2 - Convert the node value to Vector2. :::

::: api .toVec3() : vec3 - Convert the node value to Vector3. :::

::: api .toVec4() : vec4 - Convert the node value to Vector4. :::

::: api .toMat2() : mat2 - Convert the node value to Matrix2. :::

::: api .toMat3() : mat3 - Convert the node value to Matrix3. :::

::: api .toMat4() : mat4 - Convert the node value to Matrix4. :::

::: api .toIVec2() : ivec2 - Convert the node value to integer Vector2. :::

::: api .toIVec3() : ivec3 - Convert the node value to integer Vector3. :::

::: api .toIVec4() : ivec4 - Convert the node value to integer Vector4. :::

::: api .toUVec2() : uvec2 - Convert the node value to unsigned integer Vector2. :::

::: api .toUVec3() : uvec3 - Convert the node value to unsigned integer Vector3. :::

::: api .toUVec4() : uvec4 - Convert the node value to unsigned integer Vector4. :::

::: api .toBVec2() : bvec2 - Convert the node value to boolean Vector2. :::

::: api .toBVec3() : bvec3 - Convert the node value to boolean Vector3. :::

::: api .toBVec4() : bvec4 - Convert the node value to boolean Vector4. :::

Example:

```js
import { positionWorld } from 'three/tsl';

// conversion
material.colorNode = positionWorld.toVec2(); // result positionWorld.xy
```

```tsl
import 'scenes/shaderball';
import { color } from 'three/tsl';

// cornflower blue
model.material.colorNode = color( 0x1e90ff );
```

> IA: In TSL, wrapping numeric literals with `float( 1.0 )` is only necessary when using **method chaining** (e.g., `float( 1 ).div( ... )`) or when assigning directly as material node inputs (such as `material.colorNode = float( 1 )`). For function parameters like `sin( 1 )`, `cos( 0.5 )`, or `mul( uv(), 10 )`, primitive numbers are automatically converted into nodes.

> AI: Since r187, explicit integer constants are truncated instead of rounded: `int( 1.5 )` is `1`, `int( - 1.5 )` is `-1` and `uint( 0.6 )` is `0u`. See the Type Promotion section of [Operators](#operators) for how plain JavaScript numbers adapt to the other operand.
