"""framegraph.uml — UML 2.5 composers.

Each composer reads a typed UML model from `framegraph._uml` and
produces a fully-laid-out `Visual` block ready for the renderer.

Currently provides:
    compose_class_diagram         — class-diagram composer (Phase A)
    compose_package_diagram       — package-diagram composer (Phase B.1)
    compose_use_case_diagram      — use-case-diagram composer (Phase B.2)
    compose_component_diagram     — component-diagram composer (Phase C.1)
    compose_deployment_diagram    — deployment-diagram composer (Phase C.2)
    compose_activity_diagram      — activity-diagram composer (Phase C.3)
    compose_state_machine         — state-machine composer (Phase C.4)
    compose_sequence_diagram      — sequence-diagram composer (Phase D)
    compose_timing_diagram        — timing-diagram composer (Phase E.1)
    compose_communication_diagram — communication-diagram composer (Phase E.2)
    compose_interaction_overview  — interaction-overview composer (Phase E.3)
    compose_profile_diagram       — profile-diagram composer (Phase E.4)
    compose_composite_structure   — composite-structure composer (Phase E.5)
    compose_object_diagram        — object-diagram composer (Phase E.6)

All 14 UML 2.5.1 diagram kinds are now supported.
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
from framegraph.uml.communication_diagram import (
    CommunicationDiagramOptions,
    compose_communication_diagram,
)
from framegraph.uml.component_diagram import (
    ComponentDiagramOptions,
    compose_component_diagram,
)
from framegraph.uml.composite_structure import (
    CompositeStructureOptions,
    compose_composite_structure,
)
from framegraph.uml.deployment_diagram import (
    DeploymentDiagramOptions,
    compose_deployment_diagram,
)
from framegraph.uml.interaction_overview import (
    InteractionOverviewOptions,
    compose_interaction_overview,
)
from framegraph.uml.object_diagram import (
    ObjectDiagramOptions,
    compose_object_diagram,
)
from framegraph.uml.package_diagram import (
    PackageDiagramOptions,
    compose_package_diagram,
)
from framegraph.uml.profile_diagram import (
    ProfileDiagramOptions,
    compose_profile_diagram,
)
from framegraph.uml.sequence_diagram import (
    SequenceDiagramOptions,
    compose_sequence_diagram,
)
from framegraph.uml.state_machine import (
    StateMachineOptions,
    compose_state_machine,
)
from framegraph.uml.timing_diagram import (
    TimingDiagramOptions,
    compose_timing_diagram,
)
from framegraph.uml.use_case_diagram import (
    UseCaseDiagramOptions,
    compose_use_case_diagram,
)

__all__ = [
    "ActivityDiagramOptions",
    "ClassDiagramOptions",
    "CommunicationDiagramOptions",
    "ComponentDiagramOptions",
    "ComposedDiagram",
    "CompositeStructureOptions",
    "DeploymentDiagramOptions",
    "HierarchicalComposer",
    "InteractionOverviewOptions",
    "ObjectDiagramOptions",
    "PackageDiagramOptions",
    "ProfileDiagramOptions",
    "SequenceDiagramOptions",
    "StateMachineOptions",
    "TimingDiagramOptions",
    "UseCaseDiagramOptions",
    "compose_activity_diagram",
    "compose_class_diagram",
    "compose_communication_diagram",
    "compose_component_diagram",
    "compose_composite_structure",
    "compose_deployment_diagram",
    "compose_interaction_overview",
    "compose_object_diagram",
    "compose_package_diagram",
    "compose_profile_diagram",
    "compose_sequence_diagram",
    "compose_state_machine",
    "compose_timing_diagram",
    "compose_use_case_diagram",
]
