MeshToonNodeMaterial - Three.js Docs

EventDispatcher → Material → NodeMaterial →

# MeshToonNodeMaterial

Node material version of MeshToonMaterial.

## Constructor

### new MeshToonNodeMaterial( parameters : Object )

Constructs a new mesh toon node material.

 | **parameters**  |

The configuration parameter.  |

## Properties

### .isMeshToonNodeMaterial : boolean (readonly)

This flag can be used for type testing.

Default is `true`.

### .lights : boolean

Set to `true` because toon materials react on lights.

Default is `true`.   **Overrides:** NodeMaterial#lights

## Methods

### .setupLightingModel() : ToonLightingModel

Setups the lighting model.   **Overrides:** NodeMaterial#setupLightingModel   **Returns:** The lighting model.

## Source

 src/materials/nodes/MeshToonNodeMaterial.js (https://github.com/mrdoob/three.js/blob/master/src/materials/nodes/MeshToonNodeMaterial.js)
