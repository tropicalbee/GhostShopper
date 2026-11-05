"""Draw a price as SVG line segments (no <text>), so it is readable only as pixels."""

import hashlib

W, H, GAP, STROKE, PAD = 12, 22, 6, 3, 8

# Seven-segment layout: a top, b upper right, c lower right, d bottom, e lower left, f upper left, g middle.
SEGMENTS = {
    "a": ((0, 0), (W, 0)),
    "b": ((W, 0), (W, H / 2)),
    "c": ((W, H / 2), (W, H)),
    "d": ((0, H), (W, H)),
    "e": ((0, H / 2), (0, H)),
    "f": ((0, 0), (0, H / 2)),
    "g": ((0, H / 2), (W, H / 2)),
}
DIGITS = {
    "0": "abcdef", "1": "bc", "2": "abged", "3": "abgcd", "4": "fgbc",
    "5": "afgcd", "6": "afgedc", "7": "abc", "8": "abcdefg", "9": "abcdfg",
}


def token_for(sku: str, price: str) -> str:
    """Opaque file name, so the URL does not leak the price either."""
    return hashlib.sha256(f"{sku}:{price}".encode()).hexdigest()[:12]


def render_price_svg(amount: str) -> str:
    glyph = "$" + amount
    paths: list[str] = []
    x = PAD
    for ch in glyph:
        if ch == ".":
            paths.append(f'<circle cx="{x + 2}" cy="{PAD + H}" r="2.2"/>')
            x += 6 + GAP
            continue
        if ch == "$":
            segs = "afgcd"
            paths.append(f'<path d="M{x + W / 2} {PAD - 4} V{PAD + H + 4}"/>')
        else:
            segs = DIGITS[ch]
        for s in segs:
            (x1, y1), (x2, y2) = SEGMENTS[s]
            paths.append(f'<path d="M{x + x1} {PAD + y1} L{x + x2} {PAD + y2}"/>')
        x += W + GAP
    width = x - GAP + PAD
    height = H + PAD * 2
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
        f'<rect width="{width}" height="{height}" rx="4" fill="#fff3d6"/>'
        f'<g stroke="#8a3b12" stroke-width="{STROKE}" stroke-linecap="round" fill="#8a3b12">'
        + "".join(paths)
        + "</g></svg>"
    )
