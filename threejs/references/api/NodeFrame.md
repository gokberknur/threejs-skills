NodeFrame - Three.js Docs

# NodeFrame

Management class for updating nodes. The module tracks metrics like the elapsed time, delta time, the render and frame ID to correctly call the node update methods Node#updateBefore, Node#update and Node#updateAfter depending on the node's configuration.

## Constructor

### new NodeFrame()

Constructs a new node fame.

## Properties

### .camera : Camera

A reference to the current camera.

Default is `null`.

### .compute : ComputeNode

A reference to the current compute node.

Default is `null`.

### .deltaTime : number

The delta time in seconds.

Default is `0`.

### .frameId : number

The frame ID.

Default is `0`.

### .material : Material

A reference to the current material.

Default is `null`.

### .object : Object3D

A reference to the current 3D object.

Default is `null`.

### .renderId : number

The render ID.

Default is `0`.

### .renderer : Renderer

A reference to the current renderer.

Default is `null`.

### .scene : Scene

A reference to the current scene.

Default is `null`.

### .time : number

The elapsed time in seconds.

Default is `0`.

### .updateAfterMap : WeakMap.<Node, Object>

Used to control the Node#updateAfter call.

### .updateBeforeMap : WeakMap.<Node, Object>

Used to control the Node#updateBefore call.

### .updateMap : WeakMap.<Node, Object>

Used to control the Node#update call.

## Methods

### .update()

Updates the internal state of the node frame. This method is called by the renderer in its internal animation loop.

### .updateAfterNode( node : Node )

This method executes the Node#updateAfter for the given node. It makes sure Node#updateAfterType is honored meaning the update is only executed once per frame, render or object depending on the update type.

 | **node**  |

The node that should be updated.  |

### .updateBeforeNode( node : Node )

This method executes the Node#updateBefore for the given node. It makes sure Node#updateBeforeType is honored meaning the update is only executed once per frame, render or object depending on the update type.

 | **node**  |

The node that should be updated.  |

### .updateNode( node : Node )

This method executes the Node#update for the given node. It makes sure Node#updateType is honored meaning the update is only executed once per frame, render or object depending on the update type.

 | **node**  |

The node that should be updated.  |

## Source

 src/nodes/core/NodeFrame.js (https://github.com/mrdoob/three.js/blob/master/src/nodes/core/NodeFrame.js)
