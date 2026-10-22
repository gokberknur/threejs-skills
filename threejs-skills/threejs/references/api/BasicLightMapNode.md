BasicLightMapNode - Three.js Docs

EventDispatcher → Node → LightingNode →

# BasicLightMapNode

A specific version of IrradianceNode that is only relevant for MeshBasicNodeMaterial. Since the material is unlit, it requires a special scaling factor for the light map.

## Constructor

### new BasicLightMapNode( lightMapNode : Node.<vec3> )

Constructs a new basic light map node.

 | **lightMapNode**  |

The light map node.

Default is `null`.  |

## Properties

### .lightMapNode : Node.<vec3>

The light map node.

## Source

 src/nodes/lighting/BasicLightMapNode.js (https://github.com/mrdoob/three.js/blob/master/src/nodes/lighting/BasicLightMapNode.js)
