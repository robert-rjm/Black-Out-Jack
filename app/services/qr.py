"""
app/services/qr.py
===================
QR-code rendering shared by the room invite (routes/lobby.py) and the tip
link (routes/static_pages.py).
"""

import io
import re

import segno


def qr_svg(text: str) -> str:
    buf = io.BytesIO()
    segno.make(text, error="m").save(
        buf, kind="svg", scale=8, border=4, xmldecl=False, nl=False,
        dark="#000000", light="#ffffff",
    )
    svg = buf.getvalue().decode("utf-8")
    # segno emits width/height but no viewBox, so CSS-resizing the SVG crops it
    # instead of scaling it. Add one so it scales to its container.
    m = re.search(r'<svg[^>]*?width="(\d+)"[^>]*?height="(\d+)"', svg)
    if m and "viewBox" not in svg:
        svg = svg.replace("<svg ", f'<svg viewBox="0 0 {m.group(1)} {m.group(2)}" ', 1)
    return svg
