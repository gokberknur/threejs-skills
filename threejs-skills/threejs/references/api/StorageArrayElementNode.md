StorageArrayElementNode - Three.js Docs

EventDispatcher → Node → ArrayElementNode →

# StorageArrayElementNode

This class enables element access on instances of StorageBufferNode. In most cases, it is indirectly used when accessing elements with the StorageBufferNode#element method.

## Code Example

```js
const position = positionStorage.element( instanceIndex );

```

## Constructor

### new StorageArrayElementNode( storageBufferNode : StorageBufferNode, indexNode : Node )

Constructs storage buffer element node.

 | **storageBufferNode**  |

The storage buffer node.  |
 | **indexNode**  |

The index node that defines the element access.  |

## Properties

### .isStorageArrayElementNode : boolean (readonly)

This flag can be used for type testing.

Default is `true`.

### .storageBufferNode : StorageBufferNode

The storage buffer node.

## Source

 src/nodes/utils/StorageArrayElementNode.js (https://github.com/mrdoob/three.js/blob/master/src/nodes/utils/StorageArrayElementNode.js)
