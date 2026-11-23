# Operators

(TSL Guide section: Syntax > Operators)

TSL nodes support all standard mathematical, logical, and bitwise operators as chainable methods:

::: api .add( ...value ) : Node - Return the addition of two or more values.
- **...value**: `Node | number`
:::

::: api .sub( value ) : Node - Return the subtraction of two or more values.
- **value**: `Node | number`
:::

::: api .mul( value ) : Node - Return the multiplication of two or more values.
- **value**: `Node | number`
:::

::: api .div( value ) : Node - Return the division of two or more values.
- **value**: `Node | number`
:::

::: api .mod( value ) : Node - Computes the remainder of dividing the first node by the second.
- **value**: `Node | number`
:::

::: api .equal( value ) : bool - Checks if two nodes are equal.
- **value**: `Node | number | boolean`
:::

::: api .notEqual( value ) : bool - Checks if two nodes are not equal.
- **value**: `Node | number | boolean`
:::

::: api .lessThan( value ) : bool - Checks if the first node is less than the second.
- **value**: `Node | number | boolean`
:::

::: api .greaterThan( value ) : bool - Checks if the first node is greater than the second.
- **value**: `Node | number | boolean`
:::

::: api .lessThanEqual( value ) : bool - Checks if the first node is less than or equal to the second.
- **value**: `Node | number | boolean`
:::

::: api .greaterThanEqual( value ) : bool - Checks if the first node is greater than or equal to the second.
- **value**: `Node | number | boolean`
:::

::: api .and( value ) : bool - Performs logical AND on two nodes.
- **value**: `Node | boolean`
:::

::: api .or( value ) : bool - Performs logical OR on two nodes.
- **value**: `Node | boolean`
:::

::: api .not( value ) : bool - Performs logical NOT on a node.
- **value**: `Node | boolean`
:::

::: api .xor( value ) : bool - Performs logical XOR on two nodes.
- **value**: `Node | boolean`
:::

::: api .bitAnd( value ) : Node - Performs bitwise AND on two nodes.
- **value**: `Node | number`
:::

::: api .bitNot( value ) : Node - Performs bitwise NOT on a node.
- **value**: `Node | number`
:::

::: api .bitOr( value ) : Node - Performs bitwise OR on two nodes.
- **value**: `Node | number`
:::

::: api .bitXor( value ) : Node - Performs bitwise XOR on two nodes.
- **value**: `Node | number`
:::

::: api .shiftLeft( value ) : Node - Shifts a node to the left.
- **value**: `Node | number`
:::

::: api .shiftRight( value ) : Node - Shifts a node to the right.
- **value**: `Node | number`
:::

```tsl
import 'scenes/shaderball';
import { color } from 'three/tsl';

// simple color manipulation using operators
const red = color( 1.0, 0.0, 0.0 );
const blue = color( 0.0, 0.0, 1.0 );

// Mix the two colors using add and mul operators
const mixedColor = red.mul( 0.5 ).add( blue.mul( 0.5 ) ); // results in purple!

model.material.colorNode = mixedColor;
```

### Type Promotion

Operators and math functions resolve a common component type for all their inputs:

- **Explicit types** promote to the broader component type, in either operand order: `bool` < `uint` < `int` < `float`. For example, `int( 1 ).mul( float( 0.5 ) )` and `float( 0.5 ).mul( int( 1 ) )` are both `float`.
- **Plain JavaScript numbers** are *weak* constants: they adopt the type of the other operand instead of forcing `float`. For example, `int( 2 ).add( 1 )` stays `int` and `instanceIndex.div( 64 )` performs an unsigned integer division.
- Weak numbers are truncated like other integer constants when they adopt an integer type. Only values out of the integer range promote it, e.g. `uint( 1 ).add( - 1 )` is `int`.
- Inputs consisting only of weak numbers default to `float`, e.g. `mul( 1, 2 )`.
- Float-only math functions such as `pow()` or `sin()` promote integer arguments to `float`, while integer-compatible functions such as `max()` or `clamp()` keep them as integers.

```js
import { float, instanceIndex, uint } from 'three/tsl';

const row = instanceIndex.div( 64 ); // uint: integer division
const half = uint( 1 ).mul( 0.5 ); // uint: 0.5 is truncated to 0u
const ratio = instanceIndex.toFloat().mul( 0.5 ); // float
const mixed = instanceIndex.mul( float( 0.5 ) ); // float: explicit float promotes the integer
```

> AI: Before r187, any plain number in an operation with an integer node promoted the result to `float`. Since r187, plain numbers adopt the integer type, so fractional literals are truncated: `instanceIndex.mul( 0.5 )` is `instanceIndex * 0u`. When migrating, convert integer nodes with `.toFloat()` or wrap fractional literals with `float()` whenever floating-point math is intended, and remove manual conversions that only existed to force integer math.
