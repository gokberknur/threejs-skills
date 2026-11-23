# Assignments

(TSL Guide section: Syntax > Assignments)

TSL variables and parameters inside a custom function `Fn` can be updated dynamically using assignment methods:
::: api .assign( value ) : Node - Assigns a value and returns the node.
- **value**: `Node | number`
:::

::: api .addAssign( value ) : Node - Adds a value and assigns the result.
- **value**: `Node | number`
:::

::: api .subAssign( value ) : Node - Subtracts a value and assigns the result.
- **value**: `Node | number`
:::

::: api .mulAssign( value ) : Node - Multiplies a value and assigns the result.
- **value**: `Node | number`
:::

::: api .divAssign( value ) : Node - Divides a value and assigns the result.
- **value**: `Node | number`
:::

::: api .modAssign( value ) : Node - Computes the remainder and assigns the result.
- **value**: `Node | number`
:::

::: api .bitAndAssign( value ) : Node - Performs bitwise AND and assigns the result.
- **value**: `Node | number`
:::

::: api .bitOrAssign( value ) : Node - Performs bitwise OR and assigns the result.
- **value**: `Node | number`
:::

::: api .bitXorAssign( value ) : Node - Performs bitwise XOR and assigns the result.
- **value**: `Node | number`
:::

::: api .shiftLeftAssign( value ) : Node - Shifts left and assigns the result.
- **value**: `Node | number`
:::

::: api .shiftRightAssign( value ) : Node - Shifts right and assigns the result.
- **value**: `Node | number`
:::

```tsl
import 'scenes/shaderball';
import { Fn, vec3 } from 'three/tsl';

// A TSL Fn where arguments act as mutable variables
const modifyColor = Fn( ( [ color ] ) => {

	// Add blue to the incoming color node directly
	color.addAssign( vec3( 0.0, 0.0, 1.0 ) );

	return color;

} );

const baseColor = vec3( 0.0, 1.0, 0.0 ); // Green

model.material.colorNode = modifyColor( baseColor ); // Becomes Cyan
```
