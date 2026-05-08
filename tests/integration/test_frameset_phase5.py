"""Phase 5 of ADR 0001 — per-target adjustments tests.

Phase 5 ships:

- `FrameTargetAdjustments` Pydantic model (typed, ``extra="forbid"``)
  with three fields: ``font_scale`` (strictly positive multiplier),
  ``hide`` (list of layer/object ids to drop), ``padding_delta``
  (signed pixel inset on each axis of the projected canvas).
- `apply_target_adjustments(doc, adjustments)` mutates a projected
  single-doc dict per the three knobs in fixed order:
  font_scale → hide → padding_delta.
- `build_frame_doc` wires `target.adjustments` into the projection,
  so `render_frameset` automatically picks up adjustments at render
  time.

These tests pin:

1. Schema: `extra="forbid"`; `font_scale > 0`; `padding_delta` accepts
   negative / zero / positive; `hide` defaults to `[]`.
2. Application order: font_scale → hide → padding_delta.
3. font_scale: walks `visual.tokens.text_styles[*].size` and multiplies
   numeric values; preserves strings and other non-numeric shapes.
4. hide: drops layers by id; drops top-level objects by id within
   remaining layers; non-matching ids are silently ignored.
5. padding_delta: shrinks `scene.canvas.size` by `2 * delta` per axis;
   a positive delta shrinks; a negative delta expands; clamps at 1 px.
6. Backwards compatibility: `adjustments=None` produces a doc
   byte-identical to the pre-Phase-5 `build_frame_doc` output —
   pinned by Phase 1's render parity tests already.
7. Render integration: a Frame with `adjustments={padding_delta: 24}`
   produces an SVG with `width = canvas_w - 48`.
"""

from __future__ import annotations

import copy
import xml.etree.ElementTree as ET
from typing import Any

import pytest
from pydantic import ValidationError

from framegraph._frameset import (
    FrameTargetAdjustments,
    apply_target_adjustments,
    build_frame_doc,
    render_frameset,
    validate_frameset,
)

# ─────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────


def _doc_with_text_and_layers() -> dict[str, Any]:
    """A minimal projected single-doc dict for adjustment tests."""
    return {
        "dsl": "FrameGraph",
        "version": 2.0,
        "kind": "hybrid-semantic-visual-diagram",
        "scene": {
            "id": "demo",
            "canvas": {"size": [1920, 1080], "units": "px"},
        },
        "semantic": {},
        "visual": {
            "tokens": {
                "text_styles": {
                    "h1": {"size": 48, "weight": 700},
                    "body": {"size": 14},
                    "note": {"size": "14"},  # non-numeric — preserved
                    "decorative": {},  # no size — preserved
                },
                "colors": {"bg": "#fff"},
            },
            "layers": [
                {
                    "id": "main",
                    "objects": [
                        {"type": "rect", "id": "r1", "box": [0, 0, 100, 100], "fill": "#000"},
                        {"type": "rect", "id": "r2", "box": [100, 0, 100, 100], "fill": "#fff"},
                    ],
                },
                {
                    "id": "footer",
                    "objects": [{"type": "text", "id": "f1", "text": "footer"}],
                },
            ],
        },
    }


# ─────────────────────────────────────────────────────────────────
# Schema — FrameTargetAdjustments
# ─────────────────────────────────────────────────────────────────


class TestFrameTargetAdjustmentsSchema:
    def test_default_construction(self) -> None:
        adj = FrameTargetAdjustments()
        assert adj.font_scale is None
        assert adj.hide == []
        assert adj.padding_delta is None

    def test_all_fields(self) -> None:
        adj = FrameTargetAdjustments(font_scale=0.85, hide=["x"], padding_delta=24)
        assert adj.font_scale == 0.85
        assert adj.hide == ["x"]
        assert adj.padding_delta == 24

    def test_font_scale_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            FrameTargetAdjustments(font_scale=0)
        with pytest.raises(ValidationError):
            FrameTargetAdjustments(font_scale=-0.5)

    def test_font_scale_one_is_valid(self) -> None:
        # Identity scale is allowed (and is a no-op).
        FrameTargetAdjustments(font_scale=1.0)

    def test_padding_delta_negative_allowed(self) -> None:
        # A negative delta expands the canvas — rare but legal.
        adj = FrameTargetAdjustments(padding_delta=-10)
        assert adj.padding_delta == -10

    def test_padding_delta_zero_allowed(self) -> None:
        adj = FrameTargetAdjustments(padding_delta=0)
        assert adj.padding_delta == 0

    def test_extra_keys_forbidden(self) -> None:
        with pytest.raises(ValidationError, match="forbidden"):
            FrameTargetAdjustments.model_validate({"unknown_key": 1})

    def test_validates_in_target_context(self) -> None:
        # Adjustments validates as a sub-field of FrameTarget when a
        # FrameSet is loaded.
        fs = validate_frameset(
            {
                "dsl": "FrameGraph",
                "version": 2.0,
                "kind": "frameset",
                "frames": [
                    {
                        "id": "f",
                        "targets": [
                            {
                                "name": "mobile",
                                "canvas": [375, 812],
                                "adjustments": {"font_scale": 0.85, "hide": ["x"]},
                            }
                        ],
                    }
                ],
            }
        )
        adj = fs.frames[0].targets[0].adjustments
        assert adj is not None
        assert adj.font_scale == 0.85
        assert adj.hide == ["x"]

    def test_invalid_font_scale_in_target_context_rejected(self) -> None:
        with pytest.raises(ValidationError):
            validate_frameset(
                {
                    "dsl": "FrameGraph",
                    "version": 2.0,
                    "kind": "frameset",
                    "frames": [
                        {
                            "id": "f",
                            "targets": [
                                {
                                    "name": "mobile",
                                    "canvas": [375, 812],
                                    "adjustments": {"font_scale": 0},
                                }
                            ],
                        }
                    ],
                }
            )


# ─────────────────────────────────────────────────────────────────
# apply_target_adjustments — font_scale
# ─────────────────────────────────────────────────────────────────


class TestApplyFontScale:
    def test_multiplies_numeric_sizes(self) -> None:
        doc = _doc_with_text_and_layers()
        apply_target_adjustments(doc, FrameTargetAdjustments(font_scale=2.0))
        styles = doc["visual"]["tokens"]["text_styles"]
        assert styles["h1"]["size"] == 96
        assert styles["body"]["size"] == 28

    def test_preserves_non_numeric_size(self) -> None:
        doc = _doc_with_text_and_layers()
        apply_target_adjustments(doc, FrameTargetAdjustments(font_scale=2.0))
        styles = doc["visual"]["tokens"]["text_styles"]
        # String size unchanged.
        assert styles["note"]["size"] == "14"
        # Style without `size` key: still has no `size` key.
        assert "size" not in styles["decorative"]

    def test_preserves_non_size_fields(self) -> None:
        doc = _doc_with_text_and_layers()
        apply_target_adjustments(doc, FrameTargetAdjustments(font_scale=2.0))
        styles = doc["visual"]["tokens"]["text_styles"]
        # `weight` survives unchanged.
        assert styles["h1"]["weight"] == 700

    def test_factor_one_is_noop(self) -> None:
        doc = _doc_with_text_and_layers()
        before = copy.deepcopy(doc)
        apply_target_adjustments(doc, FrameTargetAdjustments(font_scale=1.0))
        assert doc == before

    def test_none_factor_is_noop(self) -> None:
        doc = _doc_with_text_and_layers()
        before = copy.deepcopy(doc)
        apply_target_adjustments(doc, FrameTargetAdjustments())
        assert doc == before

    def test_no_tokens_block_safe(self) -> None:
        # Frame projected without any tokens should not raise.
        doc = {"scene": {"canvas": {"size": [100, 100]}}, "visual": {}}
        apply_target_adjustments(doc, FrameTargetAdjustments(font_scale=2.0))
        # Visual unchanged.
        assert doc["visual"] == {}

    def test_bool_size_not_scaled(self) -> None:
        # Defensive: `bool` is a subclass of int in Python; never
        # scale flag-shaped values.
        doc = _doc_with_text_and_layers()
        doc["visual"]["tokens"]["text_styles"]["weird"] = {"size": True}
        apply_target_adjustments(doc, FrameTargetAdjustments(font_scale=2.0))
        assert doc["visual"]["tokens"]["text_styles"]["weird"]["size"] is True


# ─────────────────────────────────────────────────────────────────
# apply_target_adjustments — hide
# ─────────────────────────────────────────────────────────────────


class TestApplyHide:
    def test_drops_named_layer(self) -> None:
        doc = _doc_with_text_and_layers()
        apply_target_adjustments(doc, FrameTargetAdjustments(hide=["footer"]))
        layer_ids = [layer["id"] for layer in doc["visual"]["layers"]]
        assert "footer" not in layer_ids
        assert "main" in layer_ids

    def test_drops_top_level_object_in_remaining_layer(self) -> None:
        doc = _doc_with_text_and_layers()
        apply_target_adjustments(doc, FrameTargetAdjustments(hide=["r2"]))
        main = next(layer for layer in doc["visual"]["layers"] if layer["id"] == "main")
        ids = [obj["id"] for obj in main["objects"]]
        assert ids == ["r1"]

    def test_unknown_id_silently_ignored(self) -> None:
        doc = _doc_with_text_and_layers()
        before = copy.deepcopy(doc)
        apply_target_adjustments(doc, FrameTargetAdjustments(hide=["nonexistent"]))
        assert doc == before

    def test_hide_layer_and_object_in_one_call(self) -> None:
        doc = _doc_with_text_and_layers()
        apply_target_adjustments(doc, FrameTargetAdjustments(hide=["footer", "r1"]))
        layer_ids = [layer["id"] for layer in doc["visual"]["layers"]]
        assert layer_ids == ["main"]
        main = doc["visual"]["layers"][0]
        assert [obj["id"] for obj in main["objects"]] == ["r2"]

    def test_empty_hide_list_is_noop(self) -> None:
        doc = _doc_with_text_and_layers()
        before = copy.deepcopy(doc)
        apply_target_adjustments(doc, FrameTargetAdjustments(hide=[]))
        assert doc == before

    def test_order_preserved_among_kept(self) -> None:
        doc = _doc_with_text_and_layers()
        # Add a third layer between main and footer.
        doc["visual"]["layers"].insert(1, {"id": "middle", "objects": []})
        apply_target_adjustments(doc, FrameTargetAdjustments(hide=["middle"]))
        layer_ids = [layer["id"] for layer in doc["visual"]["layers"]]
        assert layer_ids == ["main", "footer"]


# ─────────────────────────────────────────────────────────────────
# apply_target_adjustments — padding_delta
# ─────────────────────────────────────────────────────────────────


class TestApplyPaddingDelta:
    def test_positive_delta_shrinks_canvas(self) -> None:
        doc = _doc_with_text_and_layers()
        apply_target_adjustments(doc, FrameTargetAdjustments(padding_delta=24))
        assert doc["scene"]["canvas"]["size"] == [1920 - 48, 1080 - 48]

    def test_negative_delta_expands_canvas(self) -> None:
        doc = _doc_with_text_and_layers()
        apply_target_adjustments(doc, FrameTargetAdjustments(padding_delta=-12))
        assert doc["scene"]["canvas"]["size"] == [1920 + 24, 1080 + 24]

    def test_zero_delta_is_noop(self) -> None:
        doc = _doc_with_text_and_layers()
        before = copy.deepcopy(doc)
        apply_target_adjustments(doc, FrameTargetAdjustments(padding_delta=0))
        assert doc == before

    def test_none_delta_is_noop(self) -> None:
        doc = _doc_with_text_and_layers()
        before = copy.deepcopy(doc)
        apply_target_adjustments(doc, FrameTargetAdjustments())
        assert doc == before

    def test_delta_clamped_at_1px(self) -> None:
        # Aggressive delta would zero out the canvas; clamp at 1px.
        doc = _doc_with_text_and_layers()
        apply_target_adjustments(doc, FrameTargetAdjustments(padding_delta=10000))
        size = doc["scene"]["canvas"]["size"]
        assert size[0] >= 1.0
        assert size[1] >= 1.0

    def test_no_canvas_safe(self) -> None:
        doc = {"scene": {}, "visual": {}}
        # Should not raise.
        apply_target_adjustments(doc, FrameTargetAdjustments(padding_delta=24))

    def test_malformed_canvas_size_safe(self) -> None:
        # Three-element size — implementation skips silently rather
        # than corrupting the doc.
        doc = {
            "scene": {"canvas": {"size": [100, 100, 100]}},
            "visual": {},
        }
        before = copy.deepcopy(doc)
        apply_target_adjustments(doc, FrameTargetAdjustments(padding_delta=24))
        assert doc == before


# ─────────────────────────────────────────────────────────────────
# Combined ordering — font_scale → hide → padding_delta
# ─────────────────────────────────────────────────────────────────


class TestApplyOrdering:
    def test_all_three_combined(self) -> None:
        doc = _doc_with_text_and_layers()
        apply_target_adjustments(
            doc,
            FrameTargetAdjustments(font_scale=0.5, hide=["footer"], padding_delta=10),
        )
        assert doc["visual"]["tokens"]["text_styles"]["h1"]["size"] == 24
        assert [layer["id"] for layer in doc["visual"]["layers"]] == ["main"]
        assert doc["scene"]["canvas"]["size"] == [1900, 1060]

    def test_returned_doc_is_input_doc(self) -> None:
        # Mutate-and-return: the function returns the same dict object.
        doc = _doc_with_text_and_layers()
        result = apply_target_adjustments(doc, FrameTargetAdjustments(font_scale=2.0))
        assert result is doc


# ─────────────────────────────────────────────────────────────────
# Integration — build_frame_doc + render_frameset
# ─────────────────────────────────────────────────────────────────


class TestBuildFrameDocIntegration:
    def _frameset(self, adjustments: dict[str, Any] | None) -> Any:
        target_spec: dict[str, Any] = {"name": "t", "canvas": [1920, 1080]}
        if adjustments is not None:
            target_spec["adjustments"] = adjustments
        return validate_frameset(
            {
                "dsl": "FrameGraph",
                "version": 2.0,
                "kind": "frameset",
                "frames": [
                    {
                        "id": "demo",
                        "targets": [target_spec],
                        "scene": {
                            "id": "demo",
                            "canvas": {"size": [1920, 1080]},
                        },
                        "visual": {
                            "tokens": {"text_styles": {"h1": {"size": 48}}},
                            "layers": [
                                {
                                    "id": "main",
                                    "objects": [
                                        {
                                            "type": "rect",
                                            "id": "r",
                                            "decorative": True,
                                            "box": [0, 0, 1920, 1080],
                                            "fill": "#000",
                                        }
                                    ],
                                },
                                {"id": "footer", "objects": []},
                            ],
                        },
                    }
                ],
            }
        )

    def test_no_adjustments_unchanged(self) -> None:
        # build_frame_doc is byte-identical when adjustments is None.
        # Pinned by every Phase 1 render parity test; this is a
        # sanity check for the new wiring.
        fs_a = self._frameset(None)
        fs_b = self._frameset({})
        doc_a = build_frame_doc(fs_a, fs_a.frames[0], fs_a.frames[0].targets[0])
        doc_b = build_frame_doc(fs_b, fs_b.frames[0], fs_b.frames[0].targets[0])
        # Both should produce the same canvas; empty adjustments
        # are no-ops on every knob.
        assert doc_a["scene"]["canvas"]["size"] == doc_b["scene"]["canvas"]["size"]
        assert doc_a["visual"]["tokens"] == doc_b["visual"]["tokens"]
        assert len(doc_a["visual"]["layers"]) == len(doc_b["visual"]["layers"])

    def test_font_scale_through_projection(self) -> None:
        fs = self._frameset({"font_scale": 0.5})
        doc = build_frame_doc(fs, fs.frames[0], fs.frames[0].targets[0])
        assert doc["visual"]["tokens"]["text_styles"]["h1"]["size"] == 24

    def test_hide_through_projection(self) -> None:
        fs = self._frameset({"hide": ["footer"]})
        doc = build_frame_doc(fs, fs.frames[0], fs.frames[0].targets[0])
        layer_ids = [layer["id"] for layer in doc["visual"]["layers"]]
        assert layer_ids == ["main"]

    def test_padding_delta_through_projection(self) -> None:
        fs = self._frameset({"padding_delta": 24})
        doc = build_frame_doc(fs, fs.frames[0], fs.frames[0].targets[0])
        assert doc["scene"]["canvas"]["size"] == [1872, 1032]


class TestRenderIntegration:
    def _frameset_for_render(self, adjustments: dict[str, Any] | None) -> Any:
        target_spec: dict[str, Any] = {"name": "t", "canvas": [1920, 1080]}
        if adjustments is not None:
            target_spec["adjustments"] = adjustments
        return validate_frameset(
            {
                "dsl": "FrameGraph",
                "version": 2.0,
                "kind": "frameset",
                "frames": [
                    {
                        "id": "demo",
                        "targets": [target_spec],
                        "scene": {
                            "id": "demo",
                            "canvas": {"size": [1920, 1080]},
                        },
                        "visual": {
                            "layers": [
                                {
                                    "id": "main",
                                    "objects": [
                                        {
                                            "type": "rect",
                                            "id": "r",
                                            "decorative": True,
                                            "box": [0, 0, 100, 100],
                                            "fill": "#000",
                                        }
                                    ],
                                }
                            ]
                        },
                    }
                ],
            }
        )

    def test_padding_delta_observable_in_svg(self) -> None:
        fs = self._frameset_for_render({"padding_delta": 24})
        rendered = render_frameset(fs)[0]
        root = ET.fromstring(rendered.svg)
        # canvas shrunk by 2*24 per axis.
        assert root.attrib.get("width") == "1872"
        assert root.attrib.get("height") == "1032"

    def test_no_adjustments_canvas_matches_target(self) -> None:
        fs = self._frameset_for_render(None)
        rendered = render_frameset(fs)[0]
        root = ET.fromstring(rendered.svg)
        assert root.attrib.get("width") == "1920"
        assert root.attrib.get("height") == "1080"

    def test_hide_drops_layer_in_rendered_svg(self) -> None:
        fs = validate_frameset(
            {
                "dsl": "FrameGraph",
                "version": 2.0,
                "kind": "frameset",
                "frames": [
                    {
                        "id": "demo",
                        "targets": [
                            {
                                "name": "t",
                                "canvas": [400, 200],
                                "adjustments": {"hide": ["decorations"]},
                            }
                        ],
                        "scene": {"id": "demo", "canvas": {"size": [400, 200]}},
                        "visual": {
                            "layers": [
                                {
                                    "id": "decorations",
                                    "objects": [
                                        {
                                            "type": "rect",
                                            "id": "deco-rect",
                                            "decorative": True,
                                            "box": [0, 0, 400, 200],
                                            "fill": "#ff00ff",
                                        }
                                    ],
                                },
                                {
                                    "id": "content",
                                    "objects": [
                                        {
                                            "type": "rect",
                                            "id": "content-rect",
                                            "decorative": True,
                                            "box": [0, 0, 200, 100],
                                            "fill": "#000000",
                                        }
                                    ],
                                },
                            ]
                        },
                    }
                ],
            }
        )
        rendered = render_frameset(fs)[0]
        # The decorations layer's magenta fill must not appear.
        assert "#ff00ff" not in rendered.svg.lower()
        # The content rect's id is still present.
        assert "content-rect" in rendered.svg
