MeshPhongNodeMaterial - Three.js Docs

EventDispatcher → Material → NodeMaterial →

# MeshPhongNodeMaterial

Node material version of MeshPhongMaterial.

## Constructor

### new MeshPhongNodeMaterial( parameters : Object )

Constructs a new mesh lambert node material.

 | **parameters**  |

The configuration parameter.  |

## Properties

### .isMeshPhongNodeMaterial : boolean (readonly)

This flag can be used for type testing.

Default is `true`.

### .lights : boolean

Set to `true` because phong materials react on lights.

Default is `true`.   **Overrides:** NodeMaterial#lights

### .shininessNode : Node.<float>

The shininess of phong materials is by default inferred from the `shininess` property. This node property allows to overwrite the default and define the shininess with a node instead.

If you don't want to overwrite the shininess but modify the existing value instead, use materialShininess.

Default is `null`.

### .specularNode : Node.<vec3>

The specular color of phong materials is by default inferred from the `specular` property. This node property allows to overwrite the default and define the specular color with a node instead.

If you don't want to overwrite the specular color but modify the existing value instead, use materialSpecular.

Default is `null`.

## Methods

### .setupEnvironment( builder : NodeBuilder ) : BasicEnvironmentNode.<vec3>

Overwritten since this type of material uses BasicEnvironmentNode to implement the default environment mapping.

 | **builder**  |

The current node builder.   | **Overrides:** NodeMaterial#setupEnvironment   **Returns:** The environment node.

### .setupLightingModel() : PhongLightingModel

Setups the lighting model.   **Overrides:** NodeMaterial#setupLightingModel   **Returns:** The lighting model.

### .setupVariants( builder : NodeBuilder )

Setups the phong specific node variables.

 | **builder**  |

The current node builder.   | **Overrides:** NodeMaterial#setupVariants

## Source

 src/materials/nodes/MeshPhongNodeMaterial.js (https://github.com/mrdoob/three.js/blob/master/src/materials/nodes/MeshPhongNodeMaterial.js)
