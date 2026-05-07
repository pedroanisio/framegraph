"""framegraph.uml — UML 2.5 composers.

Each composer reads a typed UML model from `framegraph._uml` and
produces a fully-laid-out `Visual` block ready for the renderer.

Currently provides:
    compose_class_diagram — class-diagram composer using Sugiyama
                             hierarchical layout from `framegraph.layout`
                             on the generalization/realization graph.

Future composers (per the v2 architecture proposal):
    package_diagram, component_diagram, deployment_diagram,
    use_case_diagram, activity_diagram, state_machine,
    sequence_diagram (custom temporal layout), …
"""

from framegraph.uml.class_diagram import (
    ClassDiagramOptions,
    ComposedDiagram,
    compose_class_diagram,
)

__all__ = ["ClassDiagramOptions", "ComposedDiagram", "compose_class_diagram"]
