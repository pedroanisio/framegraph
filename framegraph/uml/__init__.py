"""framegraph.uml — UML 2.5 composers.

Each composer reads a typed UML model from `framegraph._uml` and
produces a fully-laid-out `Visual` block ready for the renderer.

Currently provides:
    compose_class_diagram       — class-diagram composer (Phase A)
    compose_package_diagram     — package-diagram composer (Phase B.1)
    compose_use_case_diagram    — use-case-diagram composer (Phase B.2)
    compose_component_diagram   — component-diagram composer (Phase C.1)
    compose_deployment_diagram  — deployment-diagram composer (Phase C.2)
    compose_activity_diagram    — activity-diagram composer (Phase C.3)

Future composers (per the v2 architecture proposal):
    state_machine, sequence_diagram (custom temporal layout), …
"""

from framegraph.uml._composer_base import ComposedDiagram, HierarchicalComposer
from framegraph.uml.activity_diagram import (
    ActivityDiagramOptions,
    compose_activity_diagram,
)
from framegraph.uml.class_diagram import (
    ClassDiagramOptions,
    compose_class_diagram,
)
from framegraph.uml.component_diagram import (
    ComponentDiagramOptions,
    compose_component_diagram,
)
from framegraph.uml.deployment_diagram import (
    DeploymentDiagramOptions,
    compose_deployment_diagram,
)
from framegraph.uml.package_diagram import (
    PackageDiagramOptions,
    compose_package_diagram,
)
from framegraph.uml.use_case_diagram import (
    UseCaseDiagramOptions,
    compose_use_case_diagram,
)

__all__ = [
    "ActivityDiagramOptions",
    "ClassDiagramOptions",
    "ComponentDiagramOptions",
    "ComposedDiagram",
    "DeploymentDiagramOptions",
    "HierarchicalComposer",
    "PackageDiagramOptions",
    "UseCaseDiagramOptions",
    "compose_activity_diagram",
    "compose_class_diagram",
    "compose_component_diagram",
    "compose_deployment_diagram",
    "compose_package_diagram",
    "compose_use_case_diagram",
]
