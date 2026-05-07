"""Unit tests for `framegraph._uml` — the UML class-diagram ontology.

The ontology is the input contract for the UML composer (Phase A
and later). Every structural rule encoded as a Pydantic validator
gets one positive test and one negative test here. The bar is
"strict validation per the v2 architecture proposal" — no quietly
accepting wrong shapes.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from framegraph._uml import (
    Position,
    UMLAssociation,
    UMLAssociationEnd,
    UMLAttribute,
    UMLClass,
    UMLDependency,
    UMLEnumeration,
    UMLGeneralization,
    UMLInterface,
    UMLNote,
    UMLOperation,
    UMLPackage,
    UMLParameter,
    UMLRealization,
    validate_class_diagram,
)

# ─────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────


def _model(**overrides: Any) -> dict[str, Any]:
    """Build a minimal valid class-diagram dict for negative tests to mutate."""
    base: dict[str, Any] = {
        "classes": [{"id": "X", "name": "X"}],
    }
    base.update(overrides)
    return base


# ─────────────────────────────────────────────────────────────────
# Multiplicity literal validation
# ─────────────────────────────────────────────────────────────────


class TestMultiplicity:
    """The `Multiplicity` regex per UML 2.5 §7.5.4.1."""

    @pytest.mark.parametrize(
        "value",
        ["1", "0", "0..1", "1..*", "0..*", "*", "1..3", "12..99", "5..7"],
    )
    def test_valid_multiplicity_accepted(self, value: str) -> None:
        UMLAttribute(name="a", multiplicity=value)

    @pytest.mark.parametrize(
        "value",
        ["", "..", "..1", "1..", "1..a", "a..1", "-1", "1..-1", "many", "1.5"],
    )
    def test_invalid_multiplicity_rejected(self, value: str) -> None:
        with pytest.raises(ValidationError):
            UMLAttribute(name="a", multiplicity=value)


# ─────────────────────────────────────────────────────────────────
# Class-level invariants
# ─────────────────────────────────────────────────────────────────


class TestUMLClass:
    """Per-class invariants on `UMLClass`."""

    def test_minimal_class_validates(self) -> None:
        c = UMLClass(id="C", name="C")
        assert c.abstract is False
        assert c.final is False
        assert c.attributes == []
        assert c.operations == []

    def test_class_with_attributes_and_operations(self) -> None:
        c = UMLClass(
            id="Account",
            name="Account",
            attributes=[
                {"name": "balance", "type": "Money", "visibility": "private"},
            ],
            operations=[
                {"name": "deposit", "parameters": [{"name": "amount", "type": "Money"}]},
            ],
        )
        assert c.attributes[0].visibility == "private"
        assert c.operations[0].parameters[0].name == "amount"

    def test_abstract_and_final_mutually_exclusive(self) -> None:
        """UML 2.5 §11.4.4 — a final class cannot also be abstract."""
        with pytest.raises(ValidationError, match="abstract.*final"):
            UMLClass(id="C", name="C", abstract=True, final=True)

    def test_class_id_required(self) -> None:
        with pytest.raises(ValidationError):
            UMLClass(name="C")  # type: ignore[call-arg]

    def test_class_name_required(self) -> None:
        with pytest.raises(ValidationError):
            UMLClass(id="C")  # type: ignore[call-arg]

    def test_class_id_must_be_non_empty(self) -> None:
        """Empty-string ids would break edge resolution."""
        with pytest.raises(ValidationError):
            UMLClass(id="", name="C")

    def test_class_extra_fields_rejected(self) -> None:
        """`extra='forbid'` — typos in field names should fail loudly."""
        with pytest.raises(ValidationError):
            UMLClass(id="C", name="C", abstrct=True)  # type: ignore[call-arg]

    def test_class_with_position_hint(self) -> None:
        """Layout escape hatch: `position` pins the class for the composer."""
        c = UMLClass(id="C", name="C", position={"x": 100, "y": 200})
        assert c.position == Position(x=100, y=200)


# ─────────────────────────────────────────────────────────────────
# Operation invariants
# ─────────────────────────────────────────────────────────────────


class TestUMLOperation:
    """Per-operation invariants — primarily parameter-direction rules."""

    def test_operation_with_no_parameters(self) -> None:
        op = UMLOperation(name="ping")
        assert op.parameters == []

    def test_at_most_one_return_parameter(self) -> None:
        """UML 2.5 §9.6 — only one parameter may be `direction: return`."""
        with pytest.raises(ValidationError, match="direction='return'"):
            UMLOperation(
                name="op",
                parameters=[
                    {"name": "r1", "direction": "return"},
                    {"name": "r2", "direction": "return"},
                ],
            )

    def test_one_return_parameter_is_fine(self) -> None:
        op = UMLOperation(
            name="add",
            parameters=[
                {"name": "a", "direction": "in", "type": "int"},
                {"name": "b", "direction": "in", "type": "int"},
                {"name": "result", "direction": "return", "type": "int"},
            ],
        )
        assert sum(p.direction == "return" for p in op.parameters) == 1

    def test_invalid_direction_rejected(self) -> None:
        with pytest.raises(ValidationError):
            UMLParameter(name="p", direction="sideways")  # type: ignore[arg-type]


# ─────────────────────────────────────────────────────────────────
# Interface invariants
# ─────────────────────────────────────────────────────────────────


class TestUMLInterface:
    """Per-interface invariants — constants must be static + readonly."""

    def test_interface_with_constants_validates(self) -> None:
        iface = UMLInterface(
            id="Comparable",
            name="Comparable",
            operations=[{"name": "compareTo"}],
            constants=[
                {"name": "EPSILON", "type": "double", "static": True, "readonly": True},
            ],
        )
        assert iface.constants[0].static
        assert iface.constants[0].readonly

    def test_non_static_attribute_rejected(self) -> None:
        """UML 2.5 §10.4.1 — instance state belongs on classes, not interfaces."""
        with pytest.raises(ValidationError, match="static=True and readonly=True"):
            UMLInterface(
                id="I",
                name="I",
                constants=[{"name": "x", "static": False, "readonly": True}],
            )

    def test_non_readonly_attribute_rejected(self) -> None:
        with pytest.raises(ValidationError, match="static=True and readonly=True"):
            UMLInterface(
                id="I",
                name="I",
                constants=[{"name": "x", "static": True, "readonly": False}],
            )


# ─────────────────────────────────────────────────────────────────
# Enumeration invariants
# ─────────────────────────────────────────────────────────────────


class TestUMLEnumeration:
    """Per-enumeration invariants — at least one literal, all unique."""

    def test_enumeration_with_unique_literals(self) -> None:
        e = UMLEnumeration(id="Color", name="Color", literals=["RED", "GREEN", "BLUE"])
        assert len(e.literals) == 3

    def test_empty_literals_rejected(self) -> None:
        """An enumeration with no literals is meaningless."""
        with pytest.raises(ValidationError):
            UMLEnumeration(id="E", name="E", literals=[])

    def test_duplicate_literals_rejected(self) -> None:
        """UML 2.5 §10.5.4 — literals are distinct."""
        with pytest.raises(ValidationError, match="duplicate literals"):
            UMLEnumeration(id="E", name="E", literals=["A", "B", "A"])


# ─────────────────────────────────────────────────────────────────
# Edge endpoint invariants
# ─────────────────────────────────────────────────────────────────


class TestEdgeEndpoints:
    """Generalization, Realization, Dependency: from/to validators."""

    def test_generalization_self_loop_rejected(self) -> None:
        """UML 2.5 §9.9.4 — a classifier cannot generalize itself."""
        with pytest.raises(ValidationError, match="cannot generalize itself"):
            UMLGeneralization(id="g", **{"from": "X", "to": "X"})  # type: ignore[arg-type]

    def test_realization_self_loop_rejected(self) -> None:
        with pytest.raises(ValidationError, match="cannot realize itself"):
            UMLRealization(id="r", **{"from": "X", "to": "X"})  # type: ignore[arg-type]

    def test_dependency_self_loop_allowed(self) -> None:
        """Self-dependencies are unusual but legal (e.g. recursive use)."""
        d = UMLDependency(id="d", **{"from": "X", "to": "X"})  # type: ignore[arg-type]
        assert d.from_id == d.to_id


# ─────────────────────────────────────────────────────────────────
# Association invariants
# ─────────────────────────────────────────────────────────────────


class TestUMLAssociation:
    """Per-association invariants — ends and kind."""

    def test_minimal_association_validates(self) -> None:
        a = UMLAssociation(
            id="a",
            end1={"id_ref": "X"},
            end2={"id_ref": "Y"},
        )
        assert a.kind == "association"

    def test_aggregation_kind(self) -> None:
        a = UMLAssociation(
            id="a",
            end1={"id_ref": "X"},
            end2={"id_ref": "Y"},
            kind="aggregation",
        )
        assert a.kind == "aggregation"

    def test_invalid_kind_rejected(self) -> None:
        with pytest.raises(ValidationError):
            UMLAssociation(
                id="a",
                end1={"id_ref": "X"},
                end2={"id_ref": "Y"},
                kind="weird",  # type: ignore[arg-type]
            )

    def test_association_end_with_role_and_multiplicity(self) -> None:
        end = UMLAssociationEnd(id_ref="X", role="owner", multiplicity="0..*")
        assert end.role == "owner"
        assert end.multiplicity == "0..*"


# ─────────────────────────────────────────────────────────────────
# Diagram-level cross-reference validation
# ─────────────────────────────────────────────────────────────────


class TestDiagramLevelInvariants:
    """`UMLClassDiagramModel` cross-element rules."""

    def test_minimal_diagram_validates(self) -> None:
        m = validate_class_diagram(_model())
        assert len(m.classes) == 1

    def test_empty_diagram_validates(self) -> None:
        """A diagram with nothing in it is a valid (if useless) document."""
        m = validate_class_diagram({})
        assert m.classes == []
        assert m.generalizations == []

    def test_duplicate_id_across_categories_rejected(self) -> None:
        """A class and a package cannot share an id."""
        with pytest.raises(ValidationError, match="duplicate UML element id 'X'"):
            validate_class_diagram(
                {
                    "classes": [{"id": "X", "name": "C"}],
                    "packages": [{"id": "X", "name": "P"}],
                }
            )

    def test_duplicate_id_within_category_rejected(self) -> None:
        with pytest.raises(ValidationError, match="duplicate UML element id 'X'"):
            validate_class_diagram(
                {
                    "classes": [{"id": "X", "name": "C1"}, {"id": "X", "name": "C2"}],
                }
            )

    def test_unknown_generalization_endpoint_rejected(self) -> None:
        with pytest.raises(ValidationError, match="unknown classifier id 'Y'"):
            validate_class_diagram(
                {
                    "classes": [{"id": "X", "name": "X"}],
                    "generalizations": [{"id": "g", "from": "X", "to": "Y"}],
                }
            )

    def test_unknown_realization_endpoint_rejected(self) -> None:
        with pytest.raises(ValidationError, match="unknown classifier id"):
            validate_class_diagram(
                {
                    "classes": [{"id": "X", "name": "X"}],
                    "realizations": [{"id": "r", "from": "X", "to": "MissingI"}],
                }
            )

    def test_unknown_association_end_rejected(self) -> None:
        with pytest.raises(ValidationError, match="unknown classifier id"):
            validate_class_diagram(
                {
                    "classes": [{"id": "X", "name": "X"}],
                    "associations": [
                        {
                            "id": "a",
                            "end1": {"id_ref": "X"},
                            "end2": {"id_ref": "Phantom"},
                        }
                    ],
                }
            )

    def test_unknown_dependency_endpoint_rejected(self) -> None:
        with pytest.raises(ValidationError, match="unknown classifier id"):
            validate_class_diagram(
                {
                    "classes": [{"id": "X", "name": "X"}],
                    "dependencies": [{"id": "d", "from": "X", "to": "Phantom"}],
                }
            )

    def test_duplicate_generalization_pair_rejected(self) -> None:
        """The same (from, to) generalization pair twice is an authoring mistake."""
        with pytest.raises(ValidationError, match="duplicate generalization"):
            validate_class_diagram(
                {
                    "classes": [{"id": "C", "name": "C"}, {"id": "P", "name": "P"}],
                    "generalizations": [
                        {"id": "g1", "from": "C", "to": "P"},
                        {"id": "g2", "from": "C", "to": "P"},
                    ],
                }
            )

    def test_distinct_generalizations_to_different_parents_allowed(self) -> None:
        """Multiple inheritance is legal; different parents are fine."""
        m = validate_class_diagram(
            {
                "classes": [
                    {"id": "C", "name": "C"},
                    {"id": "P1", "name": "P1"},
                    {"id": "P2", "name": "P2"},
                ],
                "generalizations": [
                    {"id": "g1", "from": "C", "to": "P1"},
                    {"id": "g2", "from": "C", "to": "P2"},
                ],
            }
        )
        assert len(m.generalizations) == 2

    def test_package_contains_unknown_classifier_rejected(self) -> None:
        with pytest.raises(ValidationError, match="unknown classifier id"):
            validate_class_diagram(
                {
                    "classes": [{"id": "X", "name": "X"}],
                    "packages": [{"id": "P", "name": "P", "contains": ["X", "Y"]}],
                }
            )

    def test_interface_referenced_by_realization(self) -> None:
        """Realization's `to` may resolve to an interface, not just a class."""
        m = validate_class_diagram(
            {
                "classes": [{"id": "C", "name": "C"}],
                "interfaces": [{"id": "I", "name": "I"}],
                "realizations": [{"id": "r", "from": "C", "to": "I"}],
            }
        )
        assert m.realizations[0].to_id == "I"

    def test_enumeration_referenced_by_dependency(self) -> None:
        """Enumerations are valid edge endpoints."""
        m = validate_class_diagram(
            {
                "classes": [{"id": "C", "name": "C"}],
                "enumerations": [{"id": "E", "name": "E", "literals": ["A"]}],
                "dependencies": [{"id": "d", "from": "C", "to": "E"}],
            }
        )
        assert m.dependencies[0].to_id == "E"


# ─────────────────────────────────────────────────────────────────
# Position hint
# ─────────────────────────────────────────────────────────────────


class TestPositionHint:
    """Layout-hint escape hatch is the production-grade nudge mechanism."""

    def test_position_on_class(self) -> None:
        c = UMLClass(id="C", name="C", position={"x": 50, "y": 100})
        assert c.position is not None
        assert c.position.x == 50
        assert c.position.y == 100

    def test_position_on_package(self) -> None:
        p = UMLPackage(id="P", name="P", position={"x": 0, "y": 0})
        assert p.position is not None

    def test_position_on_note(self) -> None:
        n = UMLNote(id="n", text="hi", position={"x": 10, "y": 20})
        assert n.position is not None

    def test_position_omitted_is_none(self) -> None:
        c = UMLClass(id="C", name="C")
        assert c.position is None

    def test_position_extra_fields_rejected(self) -> None:
        """Position is a strict 2-coordinate type; no z, no rotation."""
        with pytest.raises(ValidationError):
            Position(x=0, y=0, z=10)  # type: ignore[call-arg]


# ─────────────────────────────────────────────────────────────────
# Realistic end-to-end model
# ─────────────────────────────────────────────────────────────────


class TestRealisticModel:
    """A model with the full vocabulary should validate cleanly."""

    def test_full_vocabulary_validates(self) -> None:
        """Animal kingdom: classes, interface, enum, all four edge kinds, package, note."""
        m = validate_class_diagram(
            {
                "classes": [
                    {
                        "id": "Animal",
                        "name": "Animal",
                        "abstract": True,
                        "stereotype": "abstract",
                        "attributes": [
                            {
                                "name": "name",
                                "type": "String",
                                "visibility": "protected",
                            },
                            {
                                "name": "age",
                                "type": "int",
                                "visibility": "private",
                                "multiplicity": "0..1",
                            },
                        ],
                        "operations": [
                            {
                                "name": "speak",
                                "abstract": True,
                                "return_type": "String",
                            },
                        ],
                    },
                    {
                        "id": "Dog",
                        "name": "Dog",
                        "operations": [{"name": "speak", "return_type": "String"}],
                    },
                    {
                        "id": "Cat",
                        "name": "Cat",
                        "operations": [{"name": "speak", "return_type": "String"}],
                    },
                    {"id": "Owner", "name": "Owner"},
                ],
                "interfaces": [
                    {
                        "id": "Trainable",
                        "name": "Trainable",
                        "operations": [
                            {
                                "name": "train",
                                "parameters": [
                                    {"name": "trick", "type": "String"},
                                ],
                                "return_type": "boolean",
                            }
                        ],
                    },
                ],
                "enumerations": [
                    {
                        "id": "Mood",
                        "name": "Mood",
                        "literals": ["HAPPY", "GRUMPY", "TIRED"],
                    },
                ],
                "generalizations": [
                    {"id": "g1", "from": "Dog", "to": "Animal"},
                    {"id": "g2", "from": "Cat", "to": "Animal"},
                ],
                "realizations": [
                    {"id": "r1", "from": "Dog", "to": "Trainable"},
                ],
                "associations": [
                    {
                        "id": "a1",
                        "end1": {"id_ref": "Owner", "multiplicity": "1"},
                        "end2": {"id_ref": "Dog", "multiplicity": "0..*", "role": "pets"},
                        "kind": "aggregation",
                        "name": "owns",
                    },
                ],
                "dependencies": [
                    {"id": "d1", "from": "Animal", "to": "Mood", "stereotype": "uses"},
                ],
                "packages": [
                    {
                        "id": "kingdom",
                        "name": "kingdom",
                        "contains": ["Animal", "Dog", "Cat"],
                    },
                ],
                "notes": [
                    {
                        "id": "n1",
                        "text": "Animals must implement speak() in their own way.",
                        "anchor_ids": ["Animal"],
                    },
                ],
            }
        )

        assert len(m.classes) == 4
        assert len(m.interfaces) == 1
        assert len(m.enumerations) == 1
        assert len(m.generalizations) == 2
        assert len(m.realizations) == 1
        assert len(m.associations) == 1
        assert len(m.dependencies) == 1
        assert len(m.packages) == 1
        assert len(m.notes) == 1

        # Spot-check a few derived properties
        animal = next(c for c in m.classes if c.id == "Animal")
        assert animal.abstract is True
        assert animal.stereotype == "abstract"
        assert animal.attributes[1].multiplicity == "0..1"
        assert m.associations[0].kind == "aggregation"
