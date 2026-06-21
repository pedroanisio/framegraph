"""Unit tests for the normalized render-intent layer."""

from __future__ import annotations

import pytest

from framegraph.render_intent import (
    ExportIntent,
    RenderIntent,
    collect_render_intents,
)


def _deck() -> dict:
    return {
        "dsl": "FrameGraph",
        "version": 1.5,
        "kind": "presentation-deck",
        "$theme": "mckinsey",
        "stylesheet": "default",
        "deck": {"canvas": {"size": [1280, 720]}},
        "slides": [
            {"slide": 1, "id": "cover", "title": "Cover"},
            {"slide": 2, "id": "summary", "title": "Summary"},
        ],
    }


def test_collect_render_intents_lifts_deck_to_default_target() -> None:
    intents = collect_render_intents(_deck())

    assert [intent.frame.id for intent in intents] == ["cover", "summary"]
    assert [intent.target_name for intent in intents] == ["default", "default"]
    assert [intent.canvas.size for intent in intents] == [(1280.0, 720.0), (1280.0, 720.0)]
    assert all(intent.canvas.units == "px" for intent in intents)
    assert all(intent.stylesheet_ref == "default" for intent in intents)
    assert all(intent.theme == "mckinsey" for intent in intents)
    assert all(intent.export == ExportIntent() for intent in intents)
    assert all(isinstance(intent, RenderIntent) for intent in intents)


def test_collect_render_intents_resolves_per_frame_target_before_defaults() -> None:
    data = {
        "dsl": "FrameGraph",
        "version": 2.0,
        "kind": "frameset",
        "frameset": {
            "defaults": {
                "targets": [
                    {"name": "landscape", "canvas": [1920, 1080]},
                    {"name": "portrait", "canvas": [1080, 1920]},
                ]
            }
        },
        "frames": [
            {
                "id": "custom",
                "targets": [{"name": "portrait", "canvas": [800, 1200]}],
                "visual": {"layers": []},
            },
            {"id": "inherited", "visual": {"layers": []}},
        ],
    }

    intents = collect_render_intents(data, target_name="portrait")

    assert [(intent.frame.id, intent.canvas.size) for intent in intents] == [
        ("custom", (800.0, 1200.0)),
        ("inherited", (1080.0, 1920.0)),
    ]


def test_collect_render_intents_supports_all_targets_cross_product() -> None:
    data = {
        "dsl": "FrameGraph",
        "version": 2.0,
        "kind": "frameset",
        "frameset": {
            "defaults": {
                "targets": [
                    {"name": "landscape", "canvas": [1920, 1080]},
                    {"name": "mobile", "canvas": [390, 844]},
                ]
            }
        },
        "frames": [
            {"id": "a", "visual": {"layers": []}},
            {"id": "b", "visual": {"layers": []}},
        ],
    }

    intents = collect_render_intents(data, all_targets=True)

    assert [(intent.frame.id, intent.target_name, intent.canvas.size) for intent in intents] == [
        ("a", "landscape", (1920.0, 1080.0)),
        ("b", "landscape", (1920.0, 1080.0)),
        ("a", "mobile", (390.0, 844.0)),
        ("b", "mobile", (390.0, 844.0)),
    ]


def test_collect_render_intents_filters_requested_frames_and_carries_export() -> None:
    export = ExportIntent(format="pdf", raster_dpi=150, vector=True)

    intents = collect_render_intents(_deck(), frame_ids=["summary"], export=export)

    assert [intent.frame.id for intent in intents] == ["summary"]
    assert intents[0].export is export


def test_collect_render_intents_rejects_unknown_frame_id() -> None:
    with pytest.raises(KeyError, match="unknown frame id"):
        collect_render_intents(_deck(), frame_ids=["missing"])


def test_collect_render_intents_rejects_target_and_all_targets_together() -> None:
    with pytest.raises(ValueError, match="mutually exclusive"):
        collect_render_intents(_deck(), target_name="default", all_targets=True)
