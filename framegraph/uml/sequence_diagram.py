"""Sequence-diagram composer — Phase D of the UML support architecture.

Reads a `UMLSequenceDiagramModel` (from framegraph._uml) and produces
a fully-laid-out FrameGraph `visual` block.

Unlike the Phase A–C composers, this composer does NOT use Sugiyama
hierarchical layout. Sequence diagrams use a custom *temporal* layout:

  - Lifelines are placed in evenly-spaced columns along the x-axis,
    in the order they appear in the model.
  - Time flows top-to-bottom along the y-axis. Each message's `step`
    field determines its y-coordinate.
  - Activation bars (execution specifications) are emitted on the
    target lifeline of each sync/async message and span the gap
    until the matching reply (or the end of the diagram if no reply
    exists).
  - Combined fragments wrap a vertical band determined by their
    `from_step` / `to_step`. Multi-operand operators (alt, par)
    split the band into equal sub-bands and emit dashed dividers.

This is the only Phase A–D composer that emits its visual directly
(no HierarchicalComposer base). The result is still a `ComposedDiagram`
so callers see a consistent return type.

Conventions
-----------
- sync message: solid line, filled-triangle arrow.
- async message: solid line, open-arrow head.
- reply: dashed line, open-arrow head.
- create: dashed line, open-arrow head; target lifeline's head box
  shifts down to the message's y instead of sitting at the diagram top.
- destroy: solid line, open-arrow head; an `X` glyph terminates the
  target lifeline at the message's y.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from framegraph._uml import (
    UMLLifeline,
    UMLMessage,
    UMLSequenceDiagramModel,
)
from framegraph.uml._composer_base import ComposedDiagram, str_width


@dataclass(frozen=True)
class SequenceDiagramOptions:
    """Tunable parameters for the sequence-diagram composer.

    Attributes:
        margin: Outer page margin (px).
        lifeline_pitch: Horizontal distance between adjacent lifelines.
        lifeline_min_width: Minimum width of a lifeline head box.
        lifeline_padding: Horizontal padding inside the head box.
        head_height: Height of the lifeline head rectangle.
        timeline_top: y-offset from canvas top to first message.
        step_pitch: Vertical distance between adjacent message steps.
        timeline_bottom_pad: Extra y-space below the last message.
        activation_bar_width: Width of the execution-specification
            bar centered on the target lifeline.
        message_label_size: Font size for message labels.
        head_name_size: Font size for the lifeline head label.
        fragment_padding: Horizontal padding around the band a frame
            covers (the frame extends past the leftmost / rightmost
            participating lifeline by this amount).
        fragment_y_pad: Vertical padding inside a fragment frame.
    """

    margin: float = 60.0
    lifeline_pitch: float = 180.0
    lifeline_min_width: float = 120.0
    lifeline_padding: float = 14.0
    head_height: float = 36.0
    timeline_top: float = 100.0
    step_pitch: float = 60.0
    timeline_bottom_pad: float = 60.0
    activation_bar_width: float = 12.0
    message_label_size: float = 11.0
    head_name_size: float = 12.0
    fragment_padding: float = 30.0
    fragment_y_pad: float = 14.0


def _arrow_kind_for(message_kind: str) -> tuple[str, bool]:
    """Return the `(arrow_end_kind, dashed)` pair for a UML message kind."""
    if message_kind == "sync":
        return ("filled_triangle", False)
    if message_kind == "async":
        return ("open_arrow", False)
    if message_kind == "reply":
        return ("open_arrow", True)
    if message_kind == "create":
        return ("open_arrow", True)
    # destroy
    return ("open_arrow", False)


class _SequenceDiagramComposer:
    """Custom temporal-layout composer for sequence diagrams.

    Distinct from `HierarchicalComposer`: produces the visual block
    directly. Layout strategy:

      1. Lifelines occupy evenly-spaced columns; widths sized from
         participant labels.
      2. Messages place at y = timeline_top + step_pitch * (step-1).
      3. Activations span from a sync/async message until the
         matching reply (best-effort — pairs by name when both
         `from`/`to` flip and same name; falls back to a single-step
         span when no pair found).
      4. Fragment frames bound a vertical band per their step range,
         expanded horizontally to cover all participating lifelines
         in the model.
    """

    def __init__(
        self,
        model: UMLSequenceDiagramModel,
        opts: SequenceDiagramOptions,
        canvas_size: tuple[float, float],
    ) -> None:
        self.model = model
        self.opts = opts
        self.canvas_size = canvas_size
        self._lifelines_by_id: dict[str, UMLLifeline] = {ll.id: ll for ll in model.lifelines}
        self._sorted_messages: list[UMLMessage] = sorted(model.messages, key=lambda m: m.step)

    # ── Layout helpers ──────────────────────────────────────────

    def _lifeline_widths(self) -> dict[str, float]:
        """Compute one width per lifeline, large enough to host the head label."""
        widths: dict[str, float] = {}
        for ll in self.model.lifelines:
            label = f"{ll.name}:{ll.type_name}" if ll.type_name else ll.name
            label_w = str_width(label, self.opts.head_name_size, bold=True)
            widths[ll.id] = max(
                self.opts.lifeline_min_width,
                label_w + 2 * self.opts.lifeline_padding,
            )
        return widths

    def _lifeline_columns(self) -> dict[str, float]:
        """Compute one center-x per lifeline.

        Lifelines pinned via `position.x` keep that x; the rest are
        spaced uniformly starting from the page margin.
        """
        columns: dict[str, float] = {}
        for i, ll in enumerate(self.model.lifelines):
            if ll.position is not None:
                columns[ll.id] = ll.position.x
            else:
                cx = self.opts.margin + self.opts.lifeline_pitch / 2 + i * self.opts.lifeline_pitch
                columns[ll.id] = cx
        return columns

    def _message_y(self, step: int) -> float:
        return self.opts.timeline_top + (step - 1) * self.opts.step_pitch

    def _diagram_height(self) -> float:
        if not self._sorted_messages:
            return self.opts.timeline_top + self.opts.timeline_bottom_pad + 40
        last_step = self._sorted_messages[-1].step
        return self._message_y(last_step) + self.opts.step_pitch + self.opts.timeline_bottom_pad

    def _lifeline_initial_y(self, ll: UMLLifeline) -> float:
        """Where the head of a lifeline sits.

        Created lifelines (those that are the target of a `create`
        message) have their head shifted to the message's y; others
        sit at the diagram top margin.
        """
        for m in self._sorted_messages:
            if m.kind == "create" and m.to_id == ll.id:
                return self._message_y(m.step) - self.opts.head_height / 2
        return self.opts.margin

    def _lifeline_terminate_y(self, ll: UMLLifeline, diagram_bottom: float) -> float:
        """Where the lifeline ends.

        A lifeline destroyed by a `destroy` message terminates at
        the message's y; otherwise it extends to the diagram bottom.
        """
        for m in self._sorted_messages:
            if m.kind == "destroy" and m.to_id == ll.id:
                return self._message_y(m.step)
        return diagram_bottom

    # ── Activation pairing ──────────────────────────────────────

    def _activation_spans(self, columns: dict[str, float]) -> list[tuple[str, float, float]]:
        """Pair sync messages with their replies to derive activation spans.

        Returns a list of `(lifeline_id, y_start, y_end)` tuples.
        Pairing strategy: a `sync` message starts an activation on
        its target; the next `reply` from that target back to the
        sync's source closes it. Unpaired activations span one step.
        """
        spans: list[tuple[str, float, float]] = []
        open_calls: list[tuple[UMLMessage, float]] = []  # (call, y)
        for m in self._sorted_messages:
            y = self._message_y(m.step)
            if m.kind == "sync":
                open_calls.append((m, y))
            elif m.kind == "reply":
                # Match against the most-recently-opened sync where
                # source/target swap.
                for i in range(len(open_calls) - 1, -1, -1):
                    call, call_y = open_calls[i]
                    if call.from_id == m.to_id and call.to_id == m.from_id:
                        spans.append((call.to_id, call_y, y))
                        del open_calls[i]
                        break
        # Unmatched calls: span until diagram bottom.
        diagram_bottom = self._diagram_height() - self.opts.timeline_bottom_pad
        for call, call_y in open_calls:
            spans.append((call.to_id, call_y, diagram_bottom))
        # Filter spans where the target lifeline doesn't have a column
        # (defensive — should never happen given validated input).
        return [(lid, ys, ye) for (lid, ys, ye) in spans if lid in columns]

    # ── Visual emission ─────────────────────────────────────────

    def compose(self) -> ComposedDiagram:
        widths = self._lifeline_widths()
        columns = self._lifeline_columns()
        diagram_bottom = self._diagram_height()

        layers: list[dict[str, Any]] = []

        # Lifelines layer (z=10): heads + dashed timelines + destroy X.
        lifeline_objs: list[dict[str, Any]] = []
        for ll in self.model.lifelines:
            cx = columns[ll.id]
            w = widths[ll.id]
            head_y = self._lifeline_initial_y(ll)
            term_y = self._lifeline_terminate_y(ll, diagram_bottom)
            obj: dict[str, Any] = {
                "type": "uml.lifeline",
                "id": ll.id,
                "box": [cx - w / 2, head_y, w, term_y - head_y],
                "name": ll.name,
                "head_height": self.opts.head_height,
            }
            if ll.type_name:
                obj["type_name"] = ll.type_name
            if ll.actor:
                obj["actor"] = True
            lifeline_objs.append(obj)
            # Destroy X glyph (drawn in the messages layer below so
            # it sits on top of the dashed line).
        layers.append({"id": "uml.lifelines", "z": 10, "objects": lifeline_objs})

        # Activation bars layer (z=15).
        spans = self._activation_spans(columns)
        bar_objs: list[dict[str, Any]] = []
        for lid, ys, ye in spans:
            cx = columns[lid]
            bar_objs.append(
                {
                    "type": "uml.activation_bar",
                    "id": f"act__{lid}__{ys:.0f}",
                    "box": [
                        cx - self.opts.activation_bar_width / 2,
                        ys,
                        self.opts.activation_bar_width,
                        ye - ys,
                    ],
                }
            )
        if bar_objs:
            layers.append({"id": "uml.activations", "z": 15, "objects": bar_objs})

        # Messages layer (z=20).
        message_objs = self._emit_messages(columns)
        layers.append({"id": "uml.messages", "z": 20, "objects": message_objs})

        # Fragments layer (z=8 — behind everything else).
        fragment_objs = self._emit_fragments(columns, widths)
        if fragment_objs:
            layers.insert(0, {"id": "uml.fragments", "z": 8, "objects": fragment_objs})

        # Notes layer.
        notes_layer = self._emit_notes_layer()
        if notes_layer is not None:
            layers.append(notes_layer)

        visual: dict[str, Any] = {"tokens": {}, "layers": layers}
        return ComposedDiagram(
            visual=visual,
            layout_result=None,
            node_dimensions={lid: (widths[lid], self.opts.head_height) for lid in widths},
        )

    def _emit_messages(self, columns: dict[str, float]) -> list[dict[str, Any]]:
        objs: list[dict[str, Any]] = []
        for m in self._sorted_messages:
            x_from = columns[m.from_id]
            x_to = columns[m.to_id]
            y = self._message_y(m.step)
            arrow_kind, dashed = _arrow_kind_for(m.kind)

            # The message itself: a horizontal line with an arrow.
            stroke: dict[str, Any] = {
                "color": "#1A1A1A",
                "width": 1.0,
                "arrow_end": True,
                "arrow_end_kind": arrow_kind,
            }
            if dashed:
                stroke["dash"] = [5, 4]

            # Self-message: a U-shape that loops back to the same
            # lifeline. Implemented as a polyline.
            if m.from_id == m.to_id:
                self_loop_w = 40.0
                pts = [
                    [x_from, y],
                    [x_from + self_loop_w, y],
                    [x_from + self_loop_w, y + self.opts.step_pitch * 0.4],
                    [x_from, y + self.opts.step_pitch * 0.4],
                ]
                objs.append(
                    {
                        "type": "polyline",
                        "id": m.id,
                        "points": pts,
                        "stroke": stroke,
                    }
                )
            else:
                objs.append(
                    {
                        "type": "line",
                        "id": m.id,
                        "from": [x_from, y],
                        "to": [x_to, y],
                        "stroke": stroke,
                    }
                )

            # Label sits above the line, near the source side.
            if m.name:
                label_x = (x_from + x_to) / 2 if m.from_id != m.to_id else x_from + 20
                objs.append(
                    {
                        "type": "text",
                        "id": f"{m.id}__label",
                        "decorative": True,
                        "box": [
                            label_x - 80,
                            y - self.opts.message_label_size - 4,
                            160,
                            self.opts.message_label_size + 4,
                        ],
                        "text": m.name,
                        "style": {
                            "size": self.opts.message_label_size,
                            "color": "#1A1A1A",
                            "align": "center",
                        },
                    }
                )

            # Destroy: draw an X on the target lifeline at this y.
            if m.kind == "destroy":
                size = 10.0
                objs.append(
                    {
                        "type": "line",
                        "id": f"{m.id}__destroyX1",
                        "decorative": True,
                        "from": [x_to - size, y - size],
                        "to": [x_to + size, y + size],
                        "stroke": {"color": "#1A1A1A", "width": 2.0},
                    }
                )
                objs.append(
                    {
                        "type": "line",
                        "id": f"{m.id}__destroyX2",
                        "decorative": True,
                        "from": [x_to + size, y - size],
                        "to": [x_to - size, y + size],
                        "stroke": {"color": "#1A1A1A", "width": 2.0},
                    }
                )
        return objs

    def _emit_fragments(
        self,
        columns: dict[str, float],
        widths: dict[str, float],
    ) -> list[dict[str, Any]]:
        if not self.model.fragments:
            return []
        # Frames span horizontally across all participating lifelines —
        # for simplicity, each frame covers all lifelines (UML
        # convention is "covered" lifelines explicitly; we widen
        # rather than narrow when ambiguous).
        if not columns:
            return []
        min_cx = min(columns.values())
        max_cx = max(columns.values())
        # Account for lifeline head widths in the frame extent.
        leftmost_w = min(widths.values()) if widths else self.opts.lifeline_min_width
        rightmost_w = leftmost_w
        x_left = min_cx - leftmost_w / 2 - self.opts.fragment_padding
        x_right = max_cx + rightmost_w / 2 + self.opts.fragment_padding

        objs: list[dict[str, Any]] = []
        for f in self.model.fragments:
            y_top = self._message_y(f.from_step) - self.opts.fragment_y_pad
            y_bot = self._message_y(f.to_step) + self.opts.fragment_y_pad
            height = y_bot - y_top
            obj = {
                "type": "uml.fragment_frame",
                "id": f.id,
                "box": [x_left, y_top, x_right - x_left, height],
                "kind": f.kind,
            }
            if f.operands:
                obj["operands"] = list(f.operands)
            # Multi-operand operators get equal-band dividers.
            if f.kind in ("alt", "par") and len(f.operands) >= 2:
                n = len(f.operands)
                band_h = height / n
                obj["dividers"] = [y_top + i * band_h for i in range(1, n)]
            objs.append(obj)
        return objs

    def _emit_notes_layer(self) -> dict[str, Any] | None:
        if not self.model.notes:
            return None
        objs: list[dict[str, Any]] = []
        for n in self.model.notes:
            if n.position is not None:
                nx, ny = n.position.x, n.position.y
            else:
                nx, ny = self.canvas_size[0] / 2, self.canvas_size[1] - 100
            nw, nh = 220.0, 60.0
            objs.append(
                {
                    "type": "rect",
                    "id": f"{n.id}.bg",
                    "decorative": True,
                    "box": [nx, ny, nw, nh],
                    "fill": "#FFF8DC",
                    "stroke": {"color": "#999999", "width": 0.5},
                }
            )
            objs.append(
                {
                    "type": "text",
                    "id": f"{n.id}.text",
                    "decorative": True,
                    "box": [nx + 8, ny + 8, nw - 16, nh - 16],
                    "text": n.text,
                    "style": {"size": 10, "color": "#1A1A1A", "wrap": True},
                }
            )
        return {"id": "uml.notes", "z": 30, "objects": objs}


def compose_sequence_diagram(
    model: UMLSequenceDiagramModel,
    *,
    canvas_size: tuple[float, float] = (1280.0, 720.0),
    options: SequenceDiagramOptions | None = None,
) -> ComposedDiagram:
    """Compose a sequence diagram from a typed UML model.

    Args:
        model: A validated `UMLSequenceDiagramModel`.
        canvas_size: Target canvas size (w, h) in pixels. The
            composer will exceed canvas_size[1] when the timeline
            requires more vertical room than the canvas provides;
            callers should size the canvas accordingly.
        options: Tunables; defaults to `SequenceDiagramOptions()`.

    Returns:
        A `ComposedDiagram` with the laid-out visual block. Unlike
        Phase A–C composers, `layout_result` is always `None`
        because no Sugiyama pass runs.
    """
    opts = options or SequenceDiagramOptions()
    composer = _SequenceDiagramComposer(model, opts, canvas_size)
    return composer.compose()
