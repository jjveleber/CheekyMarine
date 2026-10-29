"""Checks that a generated style only uses what the tiles, sprite and glyphs provide."""

from chartpack.enc.schema import LayerSpec

_COMMON_ATTRIBUTES = ("class", "cell", "band")
_EXPRESSION_KEYS = ("filter", "layout", "paint")


def _attribute_refs(node):
    """Yield every attribute name read by an expression, filter or property map (literal data is skipped)."""
    if isinstance(node, dict):
        for value in node.values():
            yield from _attribute_refs(value)
    elif isinstance(node, list):
        if node and node[0] == "literal":
            return
        if len(node) >= 2 and node[0] in ("get", "has", "!has") and isinstance(node[1], str):
            yield node[1]
        for item in node:
            yield from _attribute_refs(item)


def check_style_against_schema(style: dict, layers: tuple[LayerSpec, ...]) -> list[str]:
    by_name = {spec.name: spec for spec in layers}
    errors = []
    for layer in style["layers"]:
        source_layer = layer.get("source-layer")
        if source_layer is None:
            continue
        spec = by_name.get(source_layer)
        if spec is None:
            errors.append(f"{layer['id']}: unknown source-layer {source_layer!r}")
            continue
        allowed = set(spec.attributes) | set(_COMMON_ATTRIBUTES)
        for key in _EXPRESSION_KEYS:
            for name in _attribute_refs(layer.get(key, [])):
                if name not in allowed:
                    errors.append(f"{layer['id']}: {key} reads unknown attribute {name!r} of {source_layer}")
    return errors


def _outputs(expr) -> list:
    """Every value an expression can evaluate to; None marks a branch that cannot be resolved statically."""
    if isinstance(expr, str):
        return [expr]
    if not isinstance(expr, list) or not expr:
        return [None]
    op, args = expr[0], expr[1:]
    if op == "literal" and len(args) == 1 and isinstance(args[0], str):
        return [args[0]]
    if op == "match":  # input, (label, output)*, fallback
        branches = args[2:-1:2] + [args[-1]]
    elif op == "case":  # (condition, output)*, fallback
        branches = args[1:-1:2] + [args[-1]]
    elif op == "step":  # input, output0, (stop, output)*
        branches = [args[1]] + args[3::2]
    elif op == "coalesce":
        branches = args
    else:
        return [None]
    return [out for branch in branches for out in _outputs(branch)]


def check_style_sprites_glyphs(style: dict, sprite_json: dict, glyph_fonts: set[str]) -> list[str]:
    errors = []
    for layer in style["layers"]:
        layout = layer.get("layout", {})
        if "icon-image" in layout:
            for icon in _outputs(layout["icon-image"]):
                if icon is None:
                    errors.append(f"{layer['id']}: icon-image has a branch that cannot be resolved")
                elif icon not in sprite_json:
                    errors.append(f"{layer['id']}: icon {icon!r} not in sprite")
        for font in layout.get("text-font", []):
            if font not in glyph_fonts:
                errors.append(f"{layer['id']}: font {font!r} not in glyphs")
    return errors
