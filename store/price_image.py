"""Draw a price as SVG strokes (no <text>), so it is readable only as pixels.

The glyphs are hand-drawn monoline outlines in the store's ink colour, so the image looks like the kind of
price graphic a real shop might upload, while staying unreadable to anything that only reads text.
"""

import hashlib

W, H, GAP, STROKE, PAD = 14, 24, 3.5, 2.6, 4
INK = "#1c2226"

# Each glyph is drawn in a W x H box (y grows downward); paths are stroked, not filled.
GLYPHS = {
    "0": "M7 0C2.6 0 1 4.6 1 12S2.6 24 7 24 13 19.4 13 12 11.4 0 7 0Z",
    "1": "M3.2 4.2L8 0V24",
    "2": "M1.6 5.4C2.2 2.1 4.3 0 7.1 0 10.3 0 12.6 2.3 12.6 5.7 12.6 9.3 10.2 11.8 1.4 24H13.2",
    "3": "M1.8 3C3 1 4.9 0 7 0 10.1 0 12.3 2.1 12.3 5.6 12.3 9 10 11 6.4 11 10.6 11 13 13.5 13 17.5 13 21.5 10.4 24 7 24 4.6 24 2.6 23 1.3 21",
    "4": "M10.2 24V0L1 16.6H13.6",
    "5": "M12.2 0H3.2L2.2 11C3.6 9.8 5.4 9.2 7.3 9.2 10.9 9.2 13.1 12 13.1 16.4 13.1 21 10.5 24 6.8 24 4.4 24 2.5 23 1.2 21",
    "6": "M11.6 2.2C10.4 0.8 8.9 0 7.2 0 3.2 0 1 4.6 1 12.6 1 20.1 3.3 24 7.2 24 10.8 24 13 21.2 13 17 13 12.8 10.7 10.3 7.3 10.3 4.5 10.3 2.2 12 1.2 14.6",
    "7": "M1 0H13L5 24",
    "8": "M7 11C4.1 11 2 9.1 2 5.6 2 2.2 4.2 0 7 0S12 2.2 12 5.6C12 9.1 9.9 11 7 11 3.6 11 1 13.3 1 17.4 1 21.4 3.6 24 7 24S13 21.4 13 17.4C13 13.3 10.4 11 7 11Z",
    "9": "M2.4 21.8C3.6 23.2 5.1 24 6.8 24 10.8 24 13 19.4 13 11.4 13 3.9 10.7 0 6.8 0 3.2 0 1 2.8 1 7 1 11.2 3.3 13.7 6.7 13.7 9.5 13.7 11.8 12 12.8 9.4",
    "$": "M12 5C11 2.6 9.2 1.6 7 1.6 4.1 1.6 2.1 3.3 2.1 6.1 2.1 12.2 12.6 9.6 12.6 16.9 12.6 20.1 10.3 22.4 7 22.4 4.3 22.4 2.4 21.3 1.4 18.8M7 -1.8V25.8",
}


def token_for(sku: str, price: str) -> str:
    """Opaque file name, so the URL does not leak the price either."""
    return hashlib.sha256(f"{sku}:{price}".encode()).hexdigest()[:12]


def render_price_svg(amount: str) -> str:
    paths: list[str] = []
    x = PAD
    for ch in "$" + amount:
        if ch == ".":
            paths.append(f'<circle cx="{x + 1.6:.1f}" cy="{PAD + H - 1.4:.1f}" r="1.8" stroke="none"/>')
            x += 3.2 + GAP
            continue
        paths.append(f'<path transform="translate({x:.1f} {PAD})" d="{GLYPHS[ch]}"/>')
        x += W + GAP
    width = round(x - GAP + PAD)
    height = H + PAD * 2
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 -2 {width} {height + 4}">'
        f'<g stroke="{INK}" stroke-width="{STROKE}" stroke-linecap="round" stroke-linejoin="round" fill="none">'
        + "".join(paths).replace('stroke="none"/>', f'stroke="none" fill="{INK}"/>')
        + "</g></svg>"
    )
