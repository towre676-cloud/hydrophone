"""Generate the M03 coordinate/drilling SVG with only the standard library.

Dimensions, rather than screen scale, govern the parts. The assembly CAD,
cut/drill tables and independent clearance/calculation receipt govern details
not visible in these two coordinate views. The drawing checks its fixed M03
detail templates against params.json and rejects unsupported geometry changes
rather than silently publishing a stale dimensioned drawing.
"""

from __future__ import annotations

import hashlib
import html
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULTS = {
    "revision": "M03",
    "base_x": 600.0, "base_y_min": -40.0, "base_y_max": 320.0,
    "base_t": 12.0, "nut_x": 60.0, "bridge_x": 460.0,
    "anchor_x": 560.0, "string_z": 125.0,
    "leaf_x": [400.0, 520.0], "leaf_y": [52.0, 92.0],
    "carrier_y_max": 120.0,
    "rod_z": 92.0, "rear_pin_y": 110.0,
    "diaphragm_y": 153.4,
}

# Detail templates below are intentionally a reviewed M03 manufacturing view.
# CAD can remain parametric while a changed shop drawing requires review.
EXPECTED_GEOMETRY = {
    "base.origin": [0, -40, 0], "base.size": [600, 360, 12],
    "leaf.x_centres": [400, 520], "leaf.y_centres": [52, 92],
    "leaf.width": 10, "leaf.thickness": .3048, "leaf.blank_length": 60,
    "leaf.free_length": 40, "leaf.blank_bottom_z": 45,
    "leaf.free_bottom_z": 55, "leaf.free_top_z": 95,
    "leaf.hole_z": [50, 100], "leaf.hole_diameter": 3.2,
    "carrier.origin": [384, 40, 113], "carrier.size": [152, 80, 6],
    "carrier.bridge_origin": [454, 36, 119], "carrier.bridge_size": [12, 72, 6],
    "carrier.front_port": [460, 48, 92], "carrier.rear_port": [460, 110, 92],
    "clay.lower_origin": [436, 56, 81], "clay.upper_origin": [436, 56, 92],
    "clay.plate_size": [48, 32, 3], "clay.pad_origin": [445, 57, 84],
    "clay.pad_size": [30, 30, 8], "clay.mount_x": [441, 479],
    "clay.mount_y": [61, 83], "clay.pedestal_origin": [432.5, 55, 12],
    "clay.pedestal_size": [55, 34, 69],
    "strings.nut_x": 60, "strings.bridge_x": 460, "strings.anchor_x": 560,
    "strings.end_z": 124, "strings.bridge_z": 125,
    "strings.y_centres": [54, 66, 78, 90],
    "tank.internal_origin": [380, 160, 35], "tank.internal_size": [160, 100, 100],
    "tank.wall": 6, "tank.fill_z": 115,
    "tank.hydrophone_centre": [500, 215, 80], "tank.hydrophone_diameter": 25,
    "tank.hydrophone_body_length": 46,
    "diaphragm.centre": [460, 153.4, 92], "diaphragm.clear_diameter": 40,
    "diaphragm.coupon_diameter": 60, "diaphragm.nominal_thickness": .1016,
    "diaphragm.comparator_thickness": .254, "diaphragm.bolt_circle_diameter": 50,
    "diaphragm.bolt_count": 8, "diaphragm.bolt_clearance": 3.4,
    "writer.guide_x": [450, 470], "writer.guide_z": 72,
    "writer.guide_y": [-30, 35], "writer.carriage_origin": [442, -5, 66],
    "writer.carriage_size": [36, 20, 18],
    "writer.sensor_keepout_origin": [450.5, 20.9, 88],
    "writer.sensor_keepout_size": [17.5, 19.1, 8],
}


def _check_geometry(params):
    for dotted, expected in EXPECTED_GEOMETRY.items():
        actual = params
        for key in dotted.split("."):
            if not isinstance(actual, dict) or key not in actual:
                raise ValueError(f"Drawing requires current params field {dotted}")
            actual = actual[key]
        if actual != expected:
            raise ValueError(f"Review M03 drawing template after changing {dotted}: {actual!r}")


def build(destination=None):
    values = dict(DEFAULTS)
    params_path = ROOT / "params.json"
    provenance = "Geometry defaults; compare the current assembly CAD and cut/drill table."
    if params_path.exists():
        raw = params_path.read_bytes()
        params = json.loads(raw)
        _check_geometry(params)
        provenance = "params.json SHA256 " + hashlib.sha256(raw).hexdigest()[:20]
    output = Path(destination) if destination else ROOT / "generated" / "fabrication.svg"
    output.parent.mkdir(parents=True, exist_ok=True)
    svg = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="1740" viewBox="0 0 1200 1740">',
        '<defs><marker id="arrow" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M0 0L10 5L0 10Z" fill="#334155"/></marker></defs>',
        '<rect width="1200" height="1740" fill="#fff"/>',
        '<style>text{font-family:Arial,Helvetica,sans-serif;fill:#142b3c} .small{font-size:12px}.note{font-size:14px}.label{font-size:15px;font-weight:bold}.title{font-size:25px;font-weight:bold}.dim{font-size:13px;fill:#334155}.grid{stroke:#e2e8f0;stroke-width:1}.thin{stroke:#475569;stroke-width:1;fill:none}.dimension{stroke:#334155;stroke-width:1;fill:none;marker-start:url(#arrow);marker-end:url(#arrow)}.hidden{stroke-dasharray:5 4}</style>',
    ]

    def text(x, y, value, cls="note", anchor="start", color=None):
        fill = f' style="fill:{color}"' if color else ""
        svg.append(f'<text x="{x:g}" y="{y:g}" class="{cls}" text-anchor="{anchor}"{fill}>{html.escape(str(value))}</text>')

    def line(x1, y1, x2, y2, color="#475569", width=1, dashed=False):
        dash = ' stroke-dasharray="5 4"' if dashed else ""
        svg.append(f'<line x1="{x1:g}" y1="{y1:g}" x2="{x2:g}" y2="{y2:g}" stroke="{color}" stroke-width="{width:g}"{dash}/>')

    def rect(x, y, w, h, fill, stroke="#475569", dashed=False, opacity=1):
        dash = ' stroke-dasharray="5 4"' if dashed else ""
        svg.append(f'<rect x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}" fill="{fill}" stroke="{stroke}" opacity="{opacity:g}"{dash}/>')

    def circle(x, y, r, fill="white", stroke="#475569", dashed=False):
        dash = ' stroke-dasharray="5 4"' if dashed else ""
        svg.append(f'<circle cx="{x:g}" cy="{y:g}" r="{r:g}" fill="{fill}" stroke="{stroke}"{dash}/>')

    def dim(x1, y1, x2, y2, label, tx=None, ty=None):
        svg.append(f'<path d="M{x1:g},{y1:g} L{x2:g},{y2:g}" class="dimension"/>')
        text((x1+x2)/2 if tx is None else tx,
             (y1+y2)/2-7 if ty is None else ty, label, "dim", "middle")

    text(45, 40, f'{values["revision"]} · FUSION INSTRUMENT — FABRICATION COORDINATES', "title")
    text(45, 67, "Preliminary manufacturing revision. No fabricated, calibrated or load-tested validation is asserted.", "note", color="#a33221")
    text(45, 88, "All dimensions mm. Coordinates are assembly datums; displayed views are not full-size templates.", "note")

    # Top view. X to the right, Y upward; the new front writer shelf is Y<0.
    sx, origin_x, origin_y = 1.5, 100.0, 620.0
    X = lambda x: origin_x + sx*x
    Y = lambda y: origin_y - sx*y
    text(45, 116, "A  TOP VIEW · X/Y", "label")
    for x in range(0, 601, 50):
        line(X(x), Y(320), X(x), Y(-40), "#e2e8f0")
        text(X(x), Y(320)-8, x, "small", "middle")
    for y in range(-40, 321, 40):
        line(X(0), Y(y), X(600), Y(y), "#e2e8f0")
        text(X(0)-10, Y(y)+4, y, "small", "end")
    rect(X(0), Y(values["base_y_max"]), sx*values["base_x"],
         sx*(values["base_y_max"]-values["base_y_min"]), "none", "#142b3c")
    line(X(0), Y(0), X(600), Y(0), "#94a3b8", 1, True)
    text(X(5), Y(0)-8, "Original core datum Y=0; writer shelf extends to −40", "small")
    rect(X(380), Y(260), sx*160, sx*100, "#dff5ff", "#1680a6")
    rect(X(374), Y(266), sx*172, sx*112, "none", "#1680a6")
    text(X(385), Y(248), "WATER CELL", "label")
    text(X(385), Y(233), "160 × 100 interior; fill depth 80", "small")
    circle(X(500), Y(215), 12.5*sx, "#23485d")
    text(X(500), Y(190), "H1", "small", "middle")
    line(X(460), Y(140), X(460), Y(166), "#b45309", 4)
    text(X(460)+10, Y(145), "D1 Ø40 aperture", "small")
    rect(X(384), Y(values["carrier_y_max"]), sx*152,
         sx*(values["carrier_y_max"]-40), "#e6e9ef", "#475569")
    for pocket_x in (410, 490):
        rect(X(pocket_x), Y(100), sx*20, sx*40, "white", "#94a3b8")
    rect(X(436), Y(88), sx*48, sx*32, "#fff8ee", "#b45309", True)
    rect(X(445), Y(87), sx*30, sx*30, "#efb28a", "#a45428", True)
    for lx in values["leaf_x"]:
        for ly in values["leaf_y"]:
            rect(X(lx-8), Y(ly+6), sx*16, sx*12, "#64748b")
            circle(X(lx), Y(ly), 2, "#fff")
    rect(X(454), Y(108), sx*12, sx*72, "#d8b45a", "#665119")
    for y in (54, 66, 78, 90):
        line(X(values["nut_x"]), Y(y), X(values["anchor_x"]), Y(y), "#ad7426", 1.6)
        circle(X(values["nut_x"]), Y(y), 2, "#ad7426")
        circle(X(values["anchor_x"]), Y(y), 2, "#ad7426")
    line(X(60), Y(38), X(60), Y(106), "#475569", 3)
    line(X(560), Y(38), X(560), Y(106), "#475569", 3)
    line(X(460), Y(values["rear_pin_y"]), X(460), Y(values["diaphragm_y"]), "#475569", 3)
    for gx in (450, 470):
        line(X(gx), Y(-30), X(gx), Y(35), "#6b7280", 4)
    rect(X(442), Y(15), sx*36, sx*20, "#cbd5e1")
    rect(X(450.5), Y(40), sx*17.5, sx*19.1, "#f3e8ff", "#7e22ce", True)
    line(X(460), Y(-30), X(460), Y(20.9), "#64748b", 3)
    circle(X(460), Y(48), 3, "#6d28d9")
    text(1040, 170, "Top-view keys", "label")
    for i, label in enumerate([
        "Grey: moving carrier", "Orange dash: clay", "Purple dash: sensor", "Blue: water cell",
        "H1: hydrophone", "D1: diaphragm", "Dark dots: leaf axes", "Writer: front shelf",
        "Screw/rod axes Y", "Bridge motion ±Y",
    ]):
        text(1040, 194+20*i, label, "small")
    dim(X(0), 699, X(600), 699, "BASE 600")
    line(X(0), 663, X(0), 705, "#94a3b8")
    line(X(600), 663, X(600), 705, "#94a3b8")
    dim(1030, Y(320), 1030, Y(-40), "360", tx=1064, ty=Y(140))
    dim(X(60), 735, X(460), 735, "SPEAKING DATUM 400")
    dim(X(460), 735, X(560), 735, "AFTERLENGTH 100")
    text(100, 765, "Leaf centres X=400,520; Y=52,92. String Y=54,66,78,90. Bearing heights: ends Z124; bridge Z125.", "small")
    text(100, 784, "Carrier through-windows: 20 × 40 at X410–430 / X490–510, Y60–100. See drill table for remaining holes.", "small")

    # YZ section at bridge X460, with explicitly projected leaves/hydrophone.
    text(45, 811, "B  Y/Z SECTION AT X=460 · projected parts dashed", "label")
    U = lambda y: 100.0 + 2.0*(y+40)
    V = lambda z: 1200.0 - 2.5*z
    for z in (0, 35, 55, 81, 92, 113, 125, 135):
        line(U(-40), V(z), U(320), V(z), "#e2e8f0")
        text(U(-40)-10, V(z)+4, z, "small", "end")
    rect(U(-40), V(12), 720, 30, "#eef2f6", "#142b3c")
    rect(U(55), V(81), 68, 2.5*69, "#cbd5e1")
    rect(U(56), V(84), 64, 7.5, "#94a3b8")
    rect(U(57), V(92), 60, 20, "#efb28a", "#a45428")
    rect(U(56), V(95), 64, 7.5, "#94a3b8")
    rect(U(40), V(119), 2*(values["carrier_y_max"]-40), 15, "#e6e9ef")
    rect(U(36), V(125), 144, 15, "#d8b45a", "#665119")
    for y in (61, 83):
        line(U(y), V(95), U(y), V(113), "#64748b", 2, True)
    for y in values["leaf_y"]:
        line(U(y), V(55), U(y), V(95), "#c2410c", 2, True)
        rect(U(y-6), V(55), 24, 25, "none", "#64748b", True)
    rect(U(154), V(135), 224, 265, "none", "#1680a6")
    rect(U(160), V(115), 200, 200, "#dff5ff", "#1680a6")
    rect(U(154), V(112), 12, 100, "#dff5ff", "#1680a6")
    line(U(values["diaphragm_y"]), V(72), U(values["diaphragm_y"]), V(112), "#b45309", 3)
    line(U(values["rear_pin_y"]), V(92), U(values["diaphragm_y"]), V(92), "#475569", 3)
    circle(U(values["rear_pin_y"]), V(92), 4, "#fff")
    rect(U(202.5), V(103), 50, 115, "none", "#23485d", True)
    line(U(215), V(103), U(215), V(140), "#23485d", 2, True)
    rect(U(-5), V(84), 40, 45, "#cbd5e1")
    line(U(-30), V(92), U(20.9), V(92), "#64748b", 3)
    rect(U(20.9), V(96), 38.2, 20, "#f3e8ff", "#7e22ce", True)
    line(U(40), V(92), U(48), V(92), "#7e22ce", 2)
    circle(U(48), V(92), 3, "#fff", "#7e22ce")
    text(870, 864, "Load and datum stack", "label")
    for i, label in enumerate([
        "String bearing: Z125", "Carrier: Z113–119", "Leaf free: Z55–95", "Upper plate: Z92–95",
        "Clay: Z84–92 (8)", "Lower plate: Z81–84", "Rod/write axis: Z92", "Tank floor: Z35",
        "Water surface: Z115", "Sensor is keep-out only", "Leaves X400/520 projected", "H1 X500 projected",
    ]):
        text(870, 888+21*i, label, "small")
    dim(U(-40), 1237, U(320), 1237, "BASE Y −40 TO +320")
    dim(58, V(0), 58, V(125), "125", tx=39, ty=V(62.5))
    text(100, 1270, "Writer disconnects for reads; dry rod disconnects for writes. Verify actual diaphragm motion ≤10 µm about wet equilibrium.", "small", color="#a33221")
    text(100, 1288, "Seal datum Y153.4 is rounded; measure gasket compression and wet zero before adjusting or reconnecting the rod.", "small")

    # Local production details, local origins explicit.
    text(45, 1314, "C  LOCAL DRILL DETAILS · hole locations from part lower-left datum", "label")
    rect(45, 1330, 300, 345, "none", "#cbd5e1")
    text(60, 1353, "LEAF · 4 identical", "label")
    rect(105, 1380, 40, 240, "#f8fafc")
    rect(105, 1380, 40, 40, "#fef3c7")
    rect(105, 1580, 40, 40, "#fef3c7")
    circle(125, 1400, 6.4)
    circle(125, 1600, 6.4)
    dim(85, 1380, 85, 1620, "60", tx=70, ty=1505)
    dim(170, 1420, 170, 1580, "40 FREE", tx=215, ty=1505)
    text(60, 1644, '10 × 60 × 0.3048 thick (0.012 in stock)', "small")
    text(60, 1662, "Ø3.2: (5,5), (5,55); clamp 10 each end", "small")

    rect(365, 1330, 365, 345, "none", "#cbd5e1")
    text(380, 1353, "CARTRIDGE PLATE · 2 identical blanks", "label")
    px, py = 440, 1410
    rect(px, py, 192, 128, "#f8fafc")
    for hx in (5, 43):
        for hy in (5, 27):
            circle(px+4*hx, py+128-4*hy, 6.4)
    rect(px+4*9, py+4, 120, 120, "none", "#a45428", True)
    dim(px, py-23, px+192, py-23, "48")
    dim(px-25, py, px-25, py+128, "32", tx=px-43, ty=py+68)
    text(380, 1570, "48 × 32 × 3. Hole Ø3.2 at:", "small")
    text(380, 1590, "(5,5), (43,5), (5,27), (43,27).", "small")
    text(380, 1610, "Active clay 30 × 30; plate centre datum (24,16).", "small")
    text(380, 1630, "Dashed: contact footprint; source/CAD governs keys.", "small")
    text(380, 1650, "Record pad slip and actual thickness independently.", "small")

    rect(750, 1330, 405, 345, "none", "#cbd5e1")
    text(765, 1353, "DIAPHRAGM / CLAMP · local centre datum", "label")
    cx, cy, scale = 940, 1508, 3.5
    circle(cx, cy, 30*scale, "#f8fafc")
    circle(cx, cy, 25*scale, "none", "#94a3b8", True)
    circle(cx, cy, 20*scale, "#dff5ff", "#1680a6")
    for degrees in range(0, 360, 45):
        a = math.radians(degrees)
        circle(cx+25*scale*math.cos(a), cy-25*scale*math.sin(a), 1.7*scale)
    line(cx-115, cy, cx+115, cy, "#94a3b8", 1, True)
    line(cx, cy-115, cx, cy+115, "#94a3b8", 1, True)
    text(765, 1638, "OD60; clear Ø40; 8 × Ø3.4 on Ø50 PCD, 45° steps.", "small")
    text(765, 1658, "Coupon 0.1016 / 0.2540; verify seal/wet zero.", "small")
    text(45, 1710, provenance, "small")
    text(45, 1728, "Original design packet remains immutable. M03 changes are explicit; fabrication and commissioning acceptance remain required.", "small")
    svg.append("</svg>\n")
    output.write_text("\n".join(svg), encoding="utf-8")
    return output


if __name__ == "__main__":
    print(build())
