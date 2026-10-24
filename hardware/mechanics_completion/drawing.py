"""Deterministic M04 writer/cell/catch coordinate sheet (standard library).

This file draws nominal engineering dimensions. It never authenticates a part,
material property, installed operating envelope or physical qualification.
"""
from __future__ import annotations

import hashlib
import html
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "generated" / "M04_writer_section.svg"

DRAWING_GEOMETRY = {
    "force_axis_x_mm": 460,
    "force_axis_z_mm": 92,
    "lead_thread_y_mm": [-110, -55.5],
    "shoulder_y_mm": [-55.5, -53.5],
    "journal_y_mm": [-53.5, -38.5],
    "rear_bearing_y_mm": [-53.5, -49],
    "yoke_y_mm": [-49, -43],
    "front_bearing_y_mm": [-43, -38.5],
    "shaft_end_y_mm": -30,
    "fixed_nut_y_mm": [-100, -85],
    "journal_diameter_limits_mm": [5.990, 5.998],
    "cell_ports_y_mm": [5, 24.1],
    "rear_pin_y_mm": -18.9,
    "rear_mouth_y_mm": -0.4,
    "front_pin_y_mm": 48,
    "front_mouth_y_mm": 29.5,
    "rod_end_h1_mm": 18.5,
    "rod_end_d2_mm": 13,
    "rod_end_ball_width_mm": 6,
    "clevis_inside_width_mm": 10.2,
    "ball_spacer_length_mm": 2.1,
    "cell_thread_engagement_mm": 2.2,
    "stud_collar_length_mm": 2.4,
    "stud_outside_thread_length_mm": 8.5,
    "rod_end_thread_engagement_mm": 5.5,
    "catch_roller_centre_y_mm": 110,
    "catch_roller_diameter_mm": 6,
    "catch_post_front_y_mm": [93, 103],
    "catch_post_rear_y_mm": [120, 130],
    "catch_initial_gap_mm": 0.30,
    "catch_conditional_gap_mm": 0.55,
    "catch_screw_bore_mm": 3.5,
    "water_rod_diameter_mm": 3,
}

# Explicit source bindings: do not let different field names silently skip
# the dimensional check. Canonical maker/connector values supplement the
# drawing map where the full design has more detail than the sheet summary.
SOURCE_FIELDS = {
    "force_axis_x_mm": "drawing_geometry.axis_x",
    "force_axis_z_mm": "drawing_geometry.axis_z",
    "lead_thread_y_mm": "drawing_geometry.lead_thread_y",
    "shoulder_y_mm": "drawing_geometry.shoulder_y",
    "journal_y_mm": "drawing_geometry.journal_y",
    "rear_bearing_y_mm": "drawing_geometry.bearing_y.0",
    "yoke_y_mm": "drawing_geometry.yoke_y",
    "front_bearing_y_mm": "drawing_geometry.bearing_y.1",
    "shaft_end_y_mm": "lead.end_thread_y.1",
    "fixed_nut_y_mm": "drawing_geometry.fixed_nut_y",
    "journal_diameter_limits_mm": "drawing_geometry.journal_diameter_limits",
    "cell_ports_y_mm": "drawing_geometry.cell_y",
    "rear_pin_y_mm": "drawing_geometry.rear_pin_y",
    "rear_mouth_y_mm": "drawing_geometry.rear_mouth_y",
    "front_pin_y_mm": "drawing_geometry.front_pin_y",
    "front_mouth_y_mm": "drawing_geometry.front_mouth_y",
    "rod_end_h1_mm": "drawing_geometry.pin_to_mouth",
    "rod_end_d2_mm": "connectors.head_OD",
    "rod_end_ball_width_mm": "connectors.ball_width",
    "clevis_inside_width_mm": "connectors.clevis_inside_width",
    "ball_spacer_length_mm": "connectors.spacer_length_each",
    "cell_thread_engagement_mm": "drawing_geometry.stud_spigot",
    "stud_collar_length_mm": "drawing_geometry.stud_collar",
    "stud_outside_thread_length_mm": "drawing_geometry.stud_outer_thread",
    "rod_end_thread_engagement_mm": "drawing_geometry.rod_end_engagement",
    "catch_roller_centre_y_mm": "drawing_geometry.catch_centre_y",
    "catch_roller_diameter_mm": "drawing_geometry.catch_roller_OD",
    "catch_post_front_y_mm": "drawing_geometry.front_catch_post_y",
    "catch_post_rear_y_mm": "drawing_geometry.rear_catch_post_y",
    "catch_initial_gap_mm": "catches.initial_gap_each",
    "catch_conditional_gap_mm": "catches.conditional_gap_each",
    "catch_screw_bore_mm": "drawing_geometry.catch_hollow_bore",
    "water_rod_diameter_mm": "catches.water_rod_diameter",
}

SOURCE_FIXED = {
    "lead.knob_y": [-125,-110], "lead.knob_diameter": 26,
    "lead.shoulder_diameter": 10,
    "lead.washer_y": [-38.5,-37.5], "lead.washer_od": 10,
    "lead.washer_id": 6.1, "lead.locknut_y": [[-37.5,-34.3],[-34.3,-31.1]],
    "lead.locknut_AF": 10,
    "lead.housing_origin": [445,-53.5,77], "lead.housing_size": [30,15,30],
    "lead.housing_through_bore": 6.4,
    "lead.housing_well_diameter": 12.03, "lead.housing_well_depth": 4.5,
    "lead.bearing_ID": 6, "lead.bearing_OD": 12, "lead.bearing_height": 4.5,
    "fixed_nut.beam_origin": [435,-100,82], "fixed_nut.beam_size": [50,15,20],
    "stage.roof_origin": [434,-55,113], "stage.roof_size": [52,70,6],
    "cell.keepout_origin": [450.5,5,88], "cell.keepout_size": [17.5,19.1,8],
    "cell.thread_max_depth": 2.8,
    "connectors.stud_collar_AF": 5, "connectors.rod_end_jamnut_thickness": 2.4,
    "catches.front_screw_y": [94,106.7], "catches.rear_screw_y": [113.3,126],
    "catches.post_size": [20,10,86],
    "catches.front_post_origin": [450,93,12], "catches.rear_post_origin": [450,120,12],
    "catches.roller_bore": 3.1,
    "catches.thread": "M8x0.5",
    "catches.target_shape": "6x6x6 flat target block, bore along X",
    "catches.screw_outer_diameter": 8,
    "catches.end_drive_hole_diameter": 1,
    "catches.end_drive_hole_radius": 2.8,
    "outrigger.extension_origin": [420,-115,0], "outrigger.extension_size": [80,75,12],
    "outrigger.brace_origin": [420,-115,-6], "outrigger.brace_size": [80,95,6],
}


def _get(obj, dotted):
    for key in dotted.split("."):
        obj = obj[int(key)] if isinstance(obj, list) else obj[key]
    return obj


def source_state():
    """Bind the drawing to the parent geometry without silently accepting drift.

    A changed or missing bound dimension fails instead of drawing stale
    geometry under a new source hash.
    """
    path = ROOT / "completion.json"
    raw = path.read_bytes()
    obj = json.loads(raw)
    for key, expected in DRAWING_GEOMETRY.items():
        actual = _get(obj, SOURCE_FIELDS[key])
        if actual != expected:
            raise ValueError(f"Drawing geometry changed: {key}; update sheet and source together")
    for dotted, expected in SOURCE_FIXED.items():
        if _get(obj, dotted) != expected:
            raise ValueError(f"Drawing geometry changed: {dotted}; update sheet and source together")
    basis = json.loads((ROOT.parent / "mechanics" / "params.json").read_text())
    for key, expected in {
        "guide_x": [450,470], "guide_y": [-30,35], "guide_z": 72,
        "guide_diameter": 6, "carriage_origin": [442,-5,66],
        "carriage_size": [36,20,18],
    }.items():
        if basis["writer"][key] != expected:
            raise ValueError(f"M03 basis geometry changed: writer.{key}")
    return hashlib.sha256(raw).hexdigest(), obj


def render():
    source_hash, _ = source_state()
    s = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1400" height="2300" viewBox="0 0 1400 2300">',
        '<defs>',
        '<marker id="arrow" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="4" markerHeight="4" orient="auto-start-reverse"><path d="M0 0L10 5L0 10Z" fill="#425269"/></marker>',
        '<pattern id="hatch" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="7" stroke="#64748b" stroke-width="1"/></pattern>',
        '<style>text{font-family:DejaVu Sans,Arial,sans-serif;fill:#15283f}.title{font-size:30px;font-weight:700;fill:white}.sub{font-size:16px;fill:#cbd5e1}.panel{font-size:21px;font-weight:700}.label{font-size:16px}.small{font-size:14px}.tiny{font-size:12px}.mono{font-family:DejaVu Sans Mono,monospace;font-size:14px}.dim{font-size:14px;font-weight:600}.axis{stroke:#2b788c;stroke-width:1.3;stroke-dasharray:9 4 2 4}.measure{stroke:#425269;stroke-width:1;fill:none}.part{stroke:#263d52;stroke-width:1.3}.lead{stroke:#455973;stroke-width:1;fill:none}</style>',
        '</defs>',
        '<rect width="1400" height="2300" fill="#f5f7fa"/>',
        '<rect x="0" y="0" width="1400" height="112" fill="#14283f"/>',
        '<text x="44" y="48" class="title">M04 · manual writer and aligned catches</text>',
        '<text x="46" y="80" class="sub">Machining coordinate sheet · dimensions in mm · nominal design, no fabricated validation</text>',
    ]

    def text(x, y, value, cls="label", anchor=None, fill=None):
        attrs = f' class="{cls}"'
        if anchor:
            attrs += f' text-anchor="{anchor}"'
        if fill:
            attrs += f' fill="{fill}"'
        s.append(f'<text x="{x:.3f}" y="{y:.3f}"{attrs}>{html.escape(str(value))}</text>')

    def rect(x, y, w, h, fill, stroke="#263d52", dash=None, radius=0):
        extra = f' stroke-dasharray="{dash}"' if dash else ""
        s.append(f'<rect x="{x:.3f}" y="{y:.3f}" width="{w:.3f}" height="{h:.3f}" rx="{radius}" fill="{fill}" stroke="{stroke}" stroke-width="1.3"{extra}/>')

    def line(x1, y1, x2, y2, cls="measure", arrows=False):
        extra = ' marker-start="url(#arrow)" marker-end="url(#arrow)"' if arrows else ""
        s.append(f'<line x1="{x1:.3f}" y1="{y1:.3f}" x2="{x2:.3f}" y2="{y2:.3f}" class="{cls}"{extra}/>')

    def circle(cx, cy, r, fill="#fff", stroke="#263d52", width=1.3):
        s.append(f'<circle cx="{cx:.3f}" cy="{cy:.3f}" r="{r:.3f}" fill="{fill}" stroke="{stroke}" stroke-width="{width}"/>')

    def panel(x, y, w, h, title):
        rect(x, y, w, h, "white", "#d3dce6", radius=10)
        text(x+20, y+34, title, "panel")
        line(x+20, y+47, x+w-20, y+47)

    def hdim(x1, x2, y, value, from_y=None):
        if from_y is not None:
            line(x1, from_y, x1, y+5)
            line(x2, from_y, x2, y+5)
        line(x1, y, x2, y, arrows=True)
        width = max(32, len(str(value))*8.5)
        rect((x1+x2-width)/2, y-18, width, 20, "white", "white")
        text((x1+x2)/2, y-3, value, "dim", "middle")

    def callout(label_x, label_y, value, point_x, point_y, anchor="start", cls="small"):
        text(label_x, label_y, value, cls, anchor)
        begin_x = label_x if anchor != "end" else label_x-5
        line(begin_x, label_y+5, point_x, point_y, "lead")
        circle(point_x, point_y, 2, "#425269", "#425269", 0.5)

    def coords_mapper(y_min, scale, left, z_max, top):
        return lambda yy: left+(yy-y_min)*scale, lambda zz: top+(z_max-zz)*scale

    def yz_box(Y, Z, ya, yb, za, zb, color, dash=None):
        rect(Y(ya), Z(zb), Y(yb)-Y(ya), Z(za)-Z(zb), color, dash=dash)

    def bearing(Y, Z, ya, yb):
        yz_box(Y,Z,ya,yb,86,98,"#f6d889")
        yz_box(Y,Z,ya,yb,89,95,"white")
        # Symbolic ball mark only; purchased component's maker drawing governs.
        circle((Y(ya)+Y(yb))/2,Z(96.5),min((Y(yb)-Y(ya))/3,5),"#fff6da")
        circle((Y(ya)+Y(yb))/2,Z(87.5),min((Y(yb)-Y(ya))/3,5),"#fff6da")

    def thrust_housing(Y,Z):
        yz_box(Y,Z,-53.5,-38.5,77,107,"#adb9c7")
        yz_box(Y,Z,-53.5,-38.5,88.8,95.2,"white")
        for ya,yb in [(-53.5,-49),(-43,-38.5)]:
            yz_box(Y,Z,ya,yb,85.985,98.015,"white")
            bearing(Y,Z,ya,yb)
        # Continuous turned shaft through both bearing sets and the wall bore.
        yz_box(Y,Z,-53.5,-30,89.003,94.997,"#87c4cf")

    def rodend(Y,Z,pin,mouth):
        # KBRM-03 catalogue envelope: h1=18.5, d2=13, neck d4=6.5.
        lo, hi = sorted([mouth, pin + (-6.5 if mouth < pin else 6.5)])
        yz_box(Y,Z,lo,hi,88.75,95.25,"#d7e6ee")
        circle(Y(pin),Z(92),abs(Y(pin+6.5)-Y(pin)),"#d7e6ee")
        circle(Y(pin),Z(92),abs(Y(pin+4)-Y(pin)),"#a7c4d4")
        circle(Y(pin),Z(92),abs(Y(pin+1.5)-Y(pin)),"white")

    # A: actual global Y/Z station section, with posts continuing down to base.
    panel(30,132,1340,610,"A  Global Y/Z section · force line X = 460, Z = 92")
    Y,Z=coords_mapper(-135,3.6,185,140,158)
    for yy in [-125,-100,-75,-50,-25,0,25,50,75,100,125]:
        line(Y(yy),Z(0),Y(yy),Z(132),"lead")
        text(Y(yy),Z(0)+38,str(yy),"tiny","middle")
    for zz in [0,40,80,120]:
        line(Y(-130),Z(zz),Y(140),Z(zz),"lead")
        text(Y(-130)-10,Z(zz)+4,str(zz),"tiny","end")
    # Relevant base fragment; added front support is detailed in the cut table.
    yz_box(Y,Z,-40,140,0,12,"#d6dce3")
    yz_box(Y,Z,-115,-40,0,12,"#d6dce3")
    yz_box(Y,Z,-115,-20,-6,0,"#aebbc9")
    line(Y(-130),Z(92),Y(140),Z(92),"axis")
    text(Y(140)-2,Z(92)-10,"Y →","small","end")
    yz_box(Y,Z,-125,-110,79,105,"#62788a")
    yz_box(Y,Z,-110,-55.5,89,95,"#87c4cf")
    yz_box(Y,Z,-55.5,-53.5,87,97,"#56a8b8")
    yz_box(Y,Z,-53.5,-38.5,89,95,"#87c4cf")
    yz_box(Y,Z,-38.5,-30,89,95,"#87c4cf")
    thrust_housing(Y,Z)
    yz_box(Y,Z,-38.5,-37.5,87,97,"#e1bd79")
    yz_box(Y,Z,-37.5,-34.3,87,97,"#a993b8")
    yz_box(Y,Z,-34.3,-31.1,87,97,"#a993b8")
    yz_box(Y,Z,-100,-85,82,102,"#e0c499")
    # Envelope only; the final detailed frame dimensions remain in the parts.
    yz_box(Y,Z,-55,15,113,119,"#c1cbd6",dash="5 3")
    yz_box(Y,Z,-5,15,66,84,"#b1becd")
    for zrod in [72]: yz_box(Y,Z,-30,35,zrod-3,zrod+3,"#8eabb9")
    # Sensor with its two real, mirrored spherical links.
    yz_box(Y,Z,5,24.1,88,96,"#fee2e2",dash="4 2")
    yz_box(Y,Z,-5.9,7.2,90.5,93.5,"#b7cbd9")
    yz_box(Y,Z,21.9,35.0,90.5,93.5,"#b7cbd9")
    rodend(Y,Z,-18.9,-.4)
    rodend(Y,Z,48,29.5)
    # Central stop posts and flat target in the write configuration.
    for ya,yb in [(93,103),(120,130)]:
        yz_box(Y,Z,ya,yb,12,98,"#aebbc9")
        yz_box(Y,Z,ya,yb,88.25,95.75,"white")
    yz_box(Y,Z,94,106.7,88,96,"#e1bd79")
    yz_box(Y,Z,94,106.7,90.25,93.75,"white")
    yz_box(Y,Z,113.3,126,88,96,"#e1bd79")
    yz_box(Y,Z,113.3,126,90.25,93.75,"white")
    yz_box(Y,Z,107,113,89,95,"#dca96d")
    circle(Y(110),Z(92),Y(111.55)-Y(110),"white")
    text(Y(-125),Z(111),"hand knob", "tiny")
    callout(Y(-108),Z(108),"M6 × 0.5 lead",Y(-96),Z(95))
    callout(Y(-67),Z(126),"opposed thrust stack",Y(-46),Z(101))
    callout(Y(22),Z(121),"FSH00103 body keepout · no clamping",Y(14),Z(96),"middle")
    callout(Y(64),Z(108),"front pin Y48",Y(48),Z(98.5))
    callout(Y(83),Z(54),"aligned catch pair",Y(98),Z(70))
    text(Y(-130),Z(0)+63,"Global Y stations; Z increases upward. Parked knob reaches Y−140. Commercial outlines are envelopes.","small")
    hdim(Y(-18.9),Y(48),Z(48),"pin-to-pin 66.9",Z(85))

    # B: enlarged thrust load path.
    panel(30,768,650,542,"B  Captive lead: opposed axial bearings")
    Yb,Zb=coords_mapper(-60,8.5,225,105,853)
    line(Yb(-60),Zb(92),Yb(-26),Zb(92),"axis")
    yz_box(Yb,Zb,-60,-55.5,89,95,"#87c4cf")
    yz_box(Yb,Zb,-55.5,-53.5,87,97,"#56a8b8")
    yz_box(Yb,Zb,-53.5,-38.5,89,95,"#87c4cf")
    yz_box(Yb,Zb,-38.5,-30,89,95,"#87c4cf")
    thrust_housing(Yb,Zb)
    yz_box(Yb,Zb,-38.5,-37.5,87,97,"#e1bd79")
    yz_box(Yb,Zb,-37.5,-34.3,87,97,"#a993b8")
    yz_box(Yb,Zb,-34.3,-31.1,87,97,"#a993b8")
    hdim(Yb(-53.5),Yb(-49),Zb(74),"4.5",Zb(86))
    hdim(Yb(-49),Yb(-43),Zb(70),"6.0 wall",Zb(80))
    hdim(Yb(-43),Yb(-38.5),Zb(74),"4.5",Zb(86))
    hdim(Yb(-53.5),Yb(-38.5),Zb(66),"journal length 15.0",Zb(89))
    text(58,1220,"Purchased: 2 × EZO F6-12M, Ø6 / Ø12 × 4.5.","small")
    text(58,1244,"Ø10 shoulder ≥ maker 9.6 abutment; fillet ≤0.2.","small")
    text(58,1268,"Journal Ø5.990–5.998; Ø6.4 bore; Ø12.03 wells.","small")
    text(58,1292,"Screw rotates; housing washers and carriage do not.","small")

    # C: cell engagement and a real commercial spherical end.
    panel(704,768,666,542,"C  Cell stud and spherical end · front")
    Yc,Zc=coords_mapper(19,14,750,102,865)
    line(Yc(19),Zc(92),Yc(58),Zc(92),"axis")
    yz_box(Yc,Zc,19,24.1,88,96,"#fee2e2",dash="4 2")
    yz_box(Yc,Zc,21.9,24.1,90.5,93.5,"#87c4cf")
    yz_box(Yc,Zc,24.1,26.5,89.5,94.5,"#56a8b8")
    yz_box(Yc,Zc,26.5,35.0,90.5,93.5,"#87c4cf")
    rodend(Yc,Zc,48,29.5)
    # Show thread within the female mouth, not an invisible gap.
    yz_box(Yc,Zc,29.5,35.0,90.5,93.5,"#87c4cf")
    yz_box(Yc,Zc,27.1,29.5,89.25,94.75,"#a993b8")
    hdim(Yc(24.1),Yc(29.5),Zc(104),"external gap 5.4",Zc(96))
    hdim(Yc(21.9),Yc(24.1),Zc(82),"2.2",Zc(90.5))
    hdim(Yc(29.5),Yc(35.0),Zc(82),"5.5 nominal",Zc(90.5))
    hdim(Yc(29.5),Yc(48),Zc(78),"h1 = 18.5",Zc(85.5))
    text(730,1220,"Cell blind thread: M3 × 0.5, maximum depth 2.8.","small")
    text(730,1244,"Stud: 2.2 tip + 2.4 collar + 8.5 thread = 13.1.","small")
    text(730,1268,"Rear mirrors this: face 5.0 / mouth −0.4 / pin −18.9.","small")
    text(730,1292,"Cell clevis: ball 6 + 2 × spacer 2.1 = gap 10.2.","small")

    # D: one force line prevents off-centre catches from twisting the carrier.
    panel(30,1336,1340,506,"D  Central catches at the rear port · all axes X460, Z92")
    Yd,Zd=coords_mapper(87,11.5,340,103,1432)
    line(Yd(87),Zd(92),Yd(138),Zd(92),"axis")
    for ya,yb in [(93,103),(120,130)]:
        yz_box(Yd,Zd,ya,yb,83,98,"#adb9c7")
        yz_box(Yd,Zd,ya,yb,88.25,95.75,"white")
        # Broken post below the local section crop.
        line(Yd(ya),Zd(83),Yd(ya+2),Zd(82),"lead")
        line(Yd(ya+2),Zd(82),Yd(ya+4),Zd(83),"lead")
    yz_box(Yd,Zd,94,106.7,88,96,"#e1bd79")
    yz_box(Yd,Zd,94,106.7,90.25,93.75,"white")
    yz_box(Yd,Zd,113.3,126,88,96,"#e1bd79")
    yz_box(Yd,Zd,113.3,126,90.25,93.75,"white")
    yz_box(Yd,Zd,113,138,90.5,93.5,"#87c4cf")
    yz_box(Yd,Zd,107,113,89,95,"#dca96d")
    circle(Yd(110),Zd(92),Yd(111.55)-Yd(110),"white")
    text(1010,1485,"6 × 6 flat catch target", "small", "end")
    line(1010,1492,Yd(110),Zd(95),"lead")
    text(1152,1540,"M8 × 0.5 end drive", "small", "middle")
    circle(1152,1620,60,"#e1bd79")
    circle(1152,1620,26.25,"white")
    for dx in [-42,42]: circle(1152+dx,1620,7.5,"white")
    text(1152,1710,"Ø8 / Ø3.5 bore", "small", "middle")
    text(1152,1733,"2 × Ø1 at R2.8", "small", "middle")
    callout(560,1453,"0.30 initial gap",Yd(106.85),Zd(92),"middle")
    callout(675,1453,"0.30 initial gap",Yd(113.15),Zd(92),"middle")
    hdim(Yd(93),Yd(103),Zd(80),"front post10",Zd(83))
    hdim(Yd(120),Yd(130),Zd(80),"rear post10",Zd(83))
    hdim(Yd(106.7),Yd(113.3),Zd(77),"tip spacing6.6",Zd(89))
    text(62,1752,"Initial tips: Y106.70 / Y113.30. Conditional 0.55 gaps: Y106.45 / Y113.55.","small")
    text(62,1776,"Hollow M8 × 0.5 stops: Ø3.5 bore for Ø3 water rod; post tap drill Ø7.5. Qualify installed clearance.","small")
    text(62,1800,"Catches are overtravel stops; any contact ends the run. They do not enforce the ±5 N force limit.","small")
    text(62,1824,"No claim of impact rating, side-load allowance, calibration or completed physical operation.","small")

    # E: turning stations and assembly constraints in a compact workshop table.
    panel(30,1868,1340,346,"E  Turning stations and release checks")
    columns=[62,370,670]
    for x,value in zip(columns,["Feature","Global Y interval / station","Nominal machining or assembly value"]):
        text(x,1940,value,"small")
    line(60,1952,1335,1952)
    rows=[
        ("Lead working thread","−110 … −55.5","M6 × 0.5; match fixed brass nut"),
        ("Shoulder / journal","−55.5 … −53.5 / −53.5 … −38.5","Ø10 × 2.0 / Ø5.990–5.998 × 15.0"),
        ("Retaining thread / end","−38.5 … −30.0","M6 × 0.5; washer1.0 + 2 × nut3.2"),
        ("Cell load ports","5.0 / 24.1","M3 × 0.5; 2.2 engagement; never bottom"),
        ("Spherical pins","−18.9 / 48.0","Ø3; clamp ball through two 2.1 spacers"),
        ("Catch centre / tips","110.0 / 106.7 and113.3","6mm flat target; 0.30 gaps; contacts axial"),
        ("Operating evidence","after-cell displacement and live force","10µm diaphragm limit needs high-rate qualification"),
    ]
    for i,row in enumerate(rows):
        yy=1980+i*29
        for x,value in zip(columns,row):text(x,yy,value,"small")
    text(45,2242,"M04 drawing source: "+str(source_hash),"tiny")
    text(45,2264,"Purchased-part internal geometry is governed by EZO F6-12M, FUTEK FI1041-G and igus KBRM-03 source drawings.","tiny")
    text(45,2286,"This section sheet accompanies the complete cut/drill table and assembly notes; it is not a standalone operating authorization.","tiny")
    s.append('</svg>')
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text("\n".join(s)+"\n",encoding="utf-8")
    return OUT


if __name__=="__main__":
    print(render())
