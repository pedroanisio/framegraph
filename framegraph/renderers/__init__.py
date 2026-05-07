"""framegraph.renderers — Per-object-type renderer modules.

Each module exports a RENDERERS dict: {type_name: render_fn(r, obj) -> str}.
FrameGraphRenderer.register(type_name, fn) adds custom types at runtime.
"""

from . import charts, image, layout, lines, shapes, symbols, text_objects

# All built-in RENDERERS dicts in load order
ALL_MODULES = [shapes, symbols, image, lines, text_objects, charts, layout]
