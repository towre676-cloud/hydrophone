"""Regenerate M03 machining tables and nominal analytical screening receipt.

Only Python's standard library is required. No hardware operation is performed.
"""
from pathlib import Path
import csv
import hashlib
import json
import math

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "generated"


def calculations(p):
    m, s, leaf, op = p["assumed_materials"], p["strings"], p["leaf"], p["operating_declarations"]
    E, L, b, t = m["leaf_E_Pa"], leaf["free_length"] / 1000, leaf["width"] / 1000, leaf["thickness"] / 1000
    count = len(leaf["x_centres"]) * len(leaf["y_centres"])
    weak_I, strong_I = b * t**3 / 12, t * b**3 / 12
    weak_k, strong_k = count * 12 * E * weak_I / L**3, count * 12 * E * strong_I / L**3
    # K=2 is a conservative cantilever effective-length comparison, not a
    # coupled flexure buckling eigenanalysis or validated end fixity.
    pcr = math.pi**2 * E * weak_I / (2 * L)**2
    front, after = (s["bridge_x"] - s["nut_x"]) / 1000, (s["anchor_x"] - s["bridge_x"]) / 1000
    drop = (s["bridge_z"] - s["end_z"]) / 1000
    f_angle, a_angle = math.atan2(drop, front), math.atan2(drop, after)
    speak = math.hypot(front, drop)
    mu = s["assumed_density_kg_m3"] * math.pi * (s["diameter"] / 1000)**2 / 4
    tensions = [mu * (2 * speak * f)**2 for f in s["illustrative_Hz"]]
    nominal_total = sum(tensions)
    max_tension = op["total_string_tension_cap_N"]
    nominal_fz = -nominal_total * (math.sin(f_angle) + math.sin(a_angle))
    nominal_fx = nominal_total * (math.cos(a_angle) - math.cos(f_angle))
    vertical = op["moving_mass_cap_kg"] * m["g_m_s2"] + max_tension * (math.sin(f_angle) + math.sin(a_angle))
    # Explicit mismatch envelope; equal-leg tension is not guaranteed by
    # friction over a saddle. Inspect/measuring this mismatch is a gate.
    fx_screen = .1 * max_tension + max_tension * abs(math.cos(a_angle) - math.cos(f_angle))
    y_spacing = (max(leaf["y_centres"]) - min(leaf["y_centres"])) / 1000
    cases = {}
    for name, force, stroke in [
        ("initial", op["initial_write_force_abs_N"], op["initial_write_displacement_abs_mm"] / 1000),
        ("conditional_upper", op["conditional_write_force_abs_N"], op["conditional_write_displacement_abs_mm"] / 1000),
    ]:
        guided_tip_moment = count * 6 * E * weak_I * stroke / L**2
        alignment_moment = force * .0005  # declared maximum0.5mm axis error
        per_leaf_compression = vertical / count + (guided_tip_moment + alignment_moment) / (2 * y_spacing)
        sigma_y = 3 * E * t * stroke / L**2
        sigma_x = (fx_screen / count) * L / 2 * (b / 2) / strong_I
        sigma_axial = per_leaf_compression / (b * t)
        combined = sigma_y + sigma_x + sigma_axial
        ratio = pcr / per_leaf_compression
        cases[name] = {
            "force_abs_N": force, "stroke_abs_mm": stroke * 1000,
            "ideal_Y_restoring_force_N": weak_k * stroke,
            "ideal_guided_tip_moment_total_Nm": guided_tip_moment,
            "assumed_force_axis_error_max_mm": .5,
            "maximum_compression_per_leaf_N": per_leaf_compression,
            "cantilever_Euler_comparison_ratio": ratio,
            "conservative_sum_bending_and_axial_stress_MPa": combined / 1e6,
            "nominal_screen_passes": ratio >= op["minimum_buckling_ratio_screen"]
            and combined / 1e6 <= op["leaf_bending_stress_screen_MPa"],
            "qualified_operating_permission": False,
        }
    diaphragm_rows = []
    d = p["diaphragm"]
    a = d["clear_diameter"] / 2000
    pressure = m["water_density_kg_m3"] * m["g_m_s2"] * (p["tank"]["fill_z"] - d["centre"][2]) / 1000
    for thick in [d["nominal_thickness"], d["comparator_thickness"]]:
        thick_m = thick / 1000
        D = m["diaphragm_E_Pa"] * thick_m**3 / (12 * (1 - m["diaphragm_poisson"]**2))
        stiffness = 16 * math.pi * D / a**2
        preload = pressure * a**4 / (64 * D)
        diaphragm_rows.append({"thickness_mm": thick, "bending_rigidity_Nm": D,
            "ideal_central_point_stiffness_N_per_m": stiffness,
            "linear_hydrostatic_centre_deflection_um": preload * 1e6,
            "linear_deflection_over_thickness": preload / thick_m,
            "ideal_force_at_10um_N": stiffness * .00001,
            "wet_tangent_stiffness_measured": False})
    # Solid6061 end bank screening with an independent two-row base joint.
    height, web_x, web_y = .104, .020, .080
    bank_I = web_y * web_x**3 / 12
    bank_force = max_tension
    bank_moment = bank_force * height
    # Machined pockets in carrier reduce moving mass; weigh complete installed
    # carrier including transducers, wiring, fasteners and moving clay share.
    carrier_volume = 152*80*6 - 2*20*40*6
    gross_known_moving_volume_mm3 = carrier_volume + 12*72*6 + 48*32*3 + 4*(16*6*18+16*6*10) + 2*(26*14*26-8.2*14*13)
    estimate_mass = gross_known_moving_volume_mm3 * m["aluminium_density_kg_m3"] / 1e9
    return {
        "status": "ASSUMED_MATERIAL_NOMINAL_ANALYTICAL_SCREEN_NOT_PHYSICAL_QUALIFICATION",
        "illustrative_strings": {"linear_density_kg_m": mu, "actual_straight_speaking_length_m": speak,
            "tensions_N": tensions, "total_N": nominal_total, "front_break_angle_deg": math.degrees(f_angle),
            "after_break_angle_deg": math.degrees(a_angle), "bridge_nominal_force_X_N": nominal_fx,
            "bridge_nominal_force_Z_N": nominal_fz, "end_bank_longitudinal_load_N": nominal_total},
        "flexures": {"count": count, "nominal_E_Pa": E, "Y_stiffness_N_per_m": weak_k,
            "X_stiffness_N_per_m": strong_k, "cantilever_comparison_Pcr_per_leaf_N": pcr,
            "vertical_load_screen_total_N": vertical, "X_tension_mismatch_screen_N": fx_screen,
            "screening_cases": cases,
            "omitted": ["clamp slip and root concentration", "fatigue", "dynamic resonance", "coupled nonlinear buckling", "fluid and rod mismatch loads", "material/thickness tolerance enclosure"]},
        "moving_mass": {"known_machined_aluminium_estimate_kg": estimate_mass,
            "installed_mass_cap_kg": op["moving_mass_cap_kg"],
            "remaining_allowance_kg": op["moving_mass_cap_kg"] - estimate_mass,
            "must_include": "spacers, nuts, bolts, drive puck, transducers, cable traction and moving clay share; weigh assembled"},
        "anchor_bank": {"screen_force_N": bank_force, "overturning_moment_Nm": bank_moment,
            "web_bending_stress_MPa": bank_moment * (web_x/2) / bank_I / 1e6,
            "web_tip_deflection_um": bank_force * height**3 / (3 * m["aluminium_E_Pa"] * bank_I) * 1e6,
            "nominal_tension_per_base_bolt_N": bank_moment / .040 / 2,
            "nominal_web_to_foot_bolt_tension_with_10mm_contact_lever_N": bank_moment / .010 / 2,
            "nominal_direct_shear_per_base_bolt_N": bank_force / 4,
            "joint_strength_or_base_stiffness_qualified": False},
        "diaphragm": {"centre_hydrostatic_pressure_Pa": pressure, "rows": diaphragm_rows,
            "limitation": "small-deflection static plate model; wet tangent, boss footprint, fluid inertia, gasket and residual stress omitted"},
        "force_cell": {"source_item": "FSH00103", "rated_load_N": 22.2,
            "nominal_rated_deflection_um": 127, "nominal_deflection_at_5N_um": 127*5/22.2,
            "nominal_deflection_at_20N_um": 127*20/22.2,
            "interpretation": "cell compliance alone defeats treating hand-screw travel as specimen displacement"},
        "physical_readiness": False,
    }


def parts_and_drills(p):
    # Local coordinates use stock X/Y/Z orientations as installed. Hole axis
    # and clearance/thread/depth are explicit; positions repeat only forqty.
    parts = [
        ["B01",1,"6061-T6 plate",600,360,12,"base;Ydatum=-40; underside clearance for heads"],
        ["F01",4,"qualified full-hard302 stainless",10,p["leaf"]["thickness"],60,"ordered0.012in leaf;free40;measure thickness;deburr without reducing root width"],
        ["F02",4,"6061-T6",32,24,6,"lower clamp foot"],
        ["F03",4,"6061-T6",16,12,37,f"fixed post;upper10mm front notch{6+p['leaf']['thickness']/2:.4f}deep"],
        ["F04",8,"6061-T6",16,6,10,"loose front clamp jaw;4lower4upper"],
        ["F05",4,"6061-T6",16,6,18,"upper rear jaw;top tapped mount clear of leaf bolt"],
        ["C01",1,"6061-T6",152,80,6,"carrier;2throughpockets20x40 atlocal26/106,20;20mm minimum bridges"],
        ["C02",1,"6061-T6",12,72,6,"string bridge;4rounded0.5mm seating grooves"],
        ["C03",2,"6061-T6",48,32,3,"keyed CONTACTface:3grooves30x0.8x0.3parallelX atlocalY8/16/24;toplower,bottomupper"],
        ["C04",1,"6061-T6",55,34,69,"fixed clay pedestal"],
        ["C05",4,"6061 tube",5,5,18,"spacer OD5 ID3.2;length matched"],
        ["C06F",1,"6061-T6",26,14,26,"frontclevis;central slot8.2wide fullY and13high;relievefront2mm acrosslower13mm forcellclearance"],
        ["C06R",1,"6061-T6",26,14,26,"rearclevis;sameblank;differentpin/topmountYlocations"],
        ["T01",1,"compatible tank polymer",172,112,6,"bottom;bond/joint process qualification required"],
        ["T02",2,"compatible tank polymer",172,6,100,"long walls;nearwall aperture/bolt circle;installedXYZ"],
        ["T03",2,"compatible tank polymer",6,100,100,"inset ends;installedXYZ"],
        ["T04",2,"corrosion-compatible metal",60,6,60,"diaphragm annular ring OD60 ID40;8holesPCD50"],
        ["T05",2,"gasket compatible with water/polymer",60,.5,60,"annular gasket OD60 ID40;compressed thickness mustbe measured"],
        ["T06",1,"stainless foil qualified coupon",60,p["diaphragm"]["nominal_thickness"],60,"ordered0.004in;diaphragm solid;do not drill centre;8PCD50clearanceholes"],
        ["T07",1,"stainless foil comparator",60,p["diaphragm"]["comparator_thickness"],60,"ordered0.010in;separate geometry/calibrationID"],
        ["T08",1,"corrosion-compatible metal",8,1,8,"dry boss;bond to dry diaphragm centre;bond process coupon"],
        ["W01",2,"ground steel shaft",6,65,6,"manualwriter guide rods alongY"],
        ["W02",4,"6061-T6",10,12,65,"guide posts;rod centre60 abovebottom;M3radial clamp"],
        ["W03",1,"6061-T6",36,20,18,"guided carriage;2reamed boresX8/28 Z6 alongY;front thrust yoke and rear M3adapter"],
        ["W04",1,"machined steel",6,70,6,"M6x0.5lead;rotating captive thrust journal;nut onlyoutside sensor"],
        ["W05",1,"6061-T6",50,15,20,"fixed topnutbeam;M6x0.5or replaceable nut bush;axisZ92"],
        ["W06",2,"6061-T6",8,15,72,"fixednutbeam legs outside guide shafts;anchor tobase"],
        ["W07",2,"steel M3x0.5",3,12,3,"cellportstuds;2.2engagementeach;jamnut;NO bottoming beyond2.8"],
        ["W08",1,"steel shoulder pin",30,3,3,"frontclevisremovablepin alongX;retainer;no threaded shank bearing"],
        ["R01",1,"steel rod",3,40,3,"adjustable zero-load rear coupler;actual length fittedwet;indexed collar"],
        ["A01",2,"6061-T6",60,100,8,"anchorfoot;4M5base;independent longitudinalloadpath"],
        ["A02",2,"6061-T6",20,80,110,"anchorweb;4M4eye/retainer axes localZ104;measure actualbearingpoints"],
    ]
    drills = []
    def add(part, axis, xyz, diameter, operation, depth, note=""):
        drills.append([part,axis,*xyz,diameter,operation,depth,note])
    # Actual globalbaseXY coordinates are intentionally distinct from the
    # part-local coordinate columns everywhere else.
    for x in p["leaf"]["x_centres"]:
        for y in p["leaf"]["y_centres"]:
            for dx in (-8,8): add("B01","Z",[x+dx,y+40,0],4.5,"THRU",12,"globalX;localY=globalY+40;clampfoot")
    for x in p["clay"]["mount_x"]:
        for y in p["clay"]["mount_y"]: add("B01","Z",[x,y+40,0],4.5,"THRU",12,"claypedestal;counterbore underside7.5x4")
    for x in [25,65,550,590]:
        for y in [36,108]: add("B01","Z",[x,y+40,0],5.5,"THRU",12,"anchorfoot;M5throughnut")
    for x in [450,470]:
        for y in [-30,35]: add("B01","Z",[x,y+40,0],3.4,"THRU",12,"guidepost;undersidecounterbore6x3.2")
    for z in [5,55]: add("F01","Y",[5,0,z],3.2,"THRU",p["leaf"]["thickness"],"hole within10mm clampedzone;notfree root")
    for x in [8,24]: add("F02","Z",[x,12,0],4.5,"THRU",6,"basebolt")
    add("F02","Z",[16,12,0],3.4,"THRU",6,"fixedpost;M3bolt into bottomtap")
    add("F03","Z",[8,6,0],2.5,"TAP M3x0.5",12,"bottom;leave15mm solid beforetopcrosshole")
    add("F03","Y",[8,0,32],3.2,"THRU",12,"clampbolt;globalZ50")
    add("F04","Y",[8,0,5],3.2,"THRU",6,"M3jawbolt")
    add("F05","Y",[8,0,5],3.2,"THRU",6,"globalZ100")
    add("F05","Z",[8,3,18],2.5,"TAP M3x0.5",6,"topmount;bottomof tap global107 clearscrossbolt100")
    for x in [16,136]:
        for y in [15+p["leaf"]["thickness"]/2,55+p["leaf"]["thickness"]/2]: add("C01","Z",[x,y,0],3.4,"THRU",6,"upperrearjawmount")
    for x in [57,95]:
        for y in [21,43]: add("C01","Z",[x,y,0],3.4,"THRU",6,"cartridgespacer")
    for x in [68,84]:
        for y in [6,70]: add("C01","Z",[x,y,0],3.4,"THRU",6,"front/rearclevistopmount")
    for y in [12,60]: add("C01","Z",[76,y,0],3.4,"THRU",6,"bridgebar mount;exclude stringcontact grooves")
    for y in [16,64]: add("C02","Z",[6,y,0],2.5,"TAP M3x0.5",4,"blindto4mm;do notbreak saddle contact surface")
    for x in [5,43]:
        for y in [5,27]: add("C03","Z",[x,y,0],3.2,"THRU",3,"upperflushhead outsideclay footprint;lowerclearance")
    for x in [8.5,46.5]:
        for y in [6,28]:
            add("C04","Z",[x,y,69],2.5,"TAP M3x0.5",8,"topplate")
            add("C04","Z",[x,y,0],3.3,"TAP M4x0.7",12,"bottomtobase;oppositeendstopdoesnotintersect")
    for code,mount_y,pin_y in [("C06F",6,8),("C06R",6,6)]:
        for x in [5,21]: add(code,"Z",[x,mount_y,26],2.5,"TAP M3x0.5",8,"topcarrier mount")
        add(code,"X",[0,pin_y,5],3.1,"REAM",26,"clevispin;frontglobalY48,rearglobalY110")
    for part in ["T04","T05","T06","T07"]:
        for i in range(8):
            theta=2*math.pi*i/8
            add(part,"Y",[30+25*math.cos(theta),0,30+25*math.sin(theta)],3.4,"THRU","stock","centrelocal30,30;PCD50")
    for i in range(8):
        theta=2*math.pi*i/8
        add("T02-near","Y",[86+25*math.cos(theta),0,57+25*math.sin(theta)],3.4,"THRU",6,"wall originX374 Z35")
    add("T02-near","Y",[86,0,57],40,"BORE/ROUTE",6,"clearaperture")
    add("W02","Y",[5,0,60],6,"REAM",12,"guide rod;secureM3radialclampafteralignment")
    add("W02","Z",[5,6,0],2.5,"TAP M3x0.5",12,"bottommount")
    for x in [8,28]: add("W03","Y",[x,0,6],6.05,"REAM/LINEBORE",20,"matchedguidebores;fitcheckandlubeoutside specimen")
    add("W05","Y",[25,0,8],5.5,"TAP M6x0.5",15,"actualscrewfit;replaceablenutbush preferred")
    for part in ["A01"]:
        for x in [10,50]:
            for y in [14,86]: add(part,"Z",[x,y,0],5.5,"THRU",8,"basejoint")
        for y in [22,78]: add(part,"Z",[30,y,0],4.5,"THRU",8,"webmount;undersideCB7.5x4.5")
    for y in [12,68]: add("A02","Z",[10,y,0],3.3,"TAP M4x0.7",16,"webtobasefoot")
    for y in [22,34,46,58]: add("A02","X",[0,y,104],4.5,"THRU",20,"M4eyeorlineclamp;actualbearingpointmustmeasure")
    return parts, drills


def checks(p,r):
    leaf=p["leaf"]; clay=p["clay"]; t=p["tank"]; d=p["diaphragm"]
    centre=t["hydrophone_centre"]; origin=t["internal_origin"]; size=t["internal_size"]
    results={
      "leaf_free_span_matches_clamp_edges":leaf["free_top_z"]-leaf["free_bottom_z"]==leaf["free_length"],
      "leaf_hole_edge_distance_at_least_1p5diameters":min(5,leaf["width"]/2)>=1.5*leaf["hole_diameter"],
      "pad_fits_plate_with_registered_bolt_lands":clay["pad_size"][0]<clay["plate_size"][0] and clay["pad_size"][1]<clay["plate_size"][1] and max(clay["mount_x"])-1.6>clay["pad_origin"][0]+clay["pad_size"][0],
      "clay_height_stack_consistent":clay["lower_origin"][2]+clay["plate_size"][2]==clay["pad_origin"][2] and clay["pad_origin"][2]+clay["pad_size"][2]==clay["upper_origin"][2],
      "writer_force_axis_matches_upper_clay_contact":p["writer"]["force_axis_z"]==clay["upper_origin"][2],
      "sensor_engagement_below_maximum":0<p["writer"]["sensor_thread_target_engagement"]<p["writer"]["sensor_thread_max_depth"],
      "hydrophone_body_submerged_clear_floor":centre[2]-t["hydrophone_body_length"]/2>origin[2] and centre[2]+t["hydrophone_body_length"]/2<t["fill_z"],
      "hydrophone_clear_sidewalls":all(origin[i]+t["hydrophone_diameter"]/2<centre[i]<origin[i]+size[i]-t["hydrophone_diameter"]/2 for i in [0,1]),
      "diaphragm_clear_aperture_submerged":d["centre"][2]+d["clear_diameter"]/2<t["fill_z"],
      "initial_nominal_load_screen":r["flexures"]["screening_cases"]["initial"]["nominal_screen_passes"],
      "conditional_upper_nominal_load_screen":r["flexures"]["screening_cases"]["conditional_upper"]["nominal_screen_passes"],
    }
    if not all(results.values()): raise ValueError(f"M03 geometry/load screen failed: {results}")
    return results


def main():
    raw=(ROOT/"params.json").read_bytes(); p=json.loads(raw); OUT.mkdir(exist_ok=True)
    r=calculations(p); r["geometry_revision"]=p["revision"];r["params_sha256"]=hashlib.sha256(raw).hexdigest();r["checks"]=checks(p,r)
    (OUT/"calculation_receipt.json").write_text(json.dumps(r,indent=2)+"\n")
    (OUT/"params.scad").write_text("// Generated fromparams.json; millimetres;M03\n"+"\n".join(
       f"{key}={json.dumps(value)};" for key,value in {
       "base_origin":p["base"]["origin"],"base_size":p["base"]["size"],
       "leaf_x":p["leaf"]["x_centres"],"leaf_y":p["leaf"]["y_centres"],"leaf_t":p["leaf"]["thickness"],
       "carrier_origin":p["carrier"]["origin"],"carrier_size":p["carrier"]["size"],
       "clay_lower":p["clay"]["lower_origin"],"clay_upper":p["clay"]["upper_origin"],"clay_plate":p["clay"]["plate_size"],
       "clay_mount_x":p["clay"]["mount_x"],"clay_mount_y":p["clay"]["mount_y"],
       "string_y":p["strings"]["y_centres"],"membrane_t":p["diaphragm"]["nominal_thickness"]}.items())+"\n")
    parts,drills=parts_and_drills(p)
    with (OUT/"cut_list.csv").open("w",newline="") as f:
        w=csv.writer(f,lineterminator='\n');w.writerow(["part","qty","material","stock_X_mm","stock_Y_mm","stock_Z_mm","operation_notes"]);w.writerows(parts)
    with (OUT/"drill_table.csv").open("w",newline="") as f:
        w=csv.writer(f,lineterminator='\n');w.writerow(["part","hole_axis","local_X_mm","local_Y_mm","local_Z_mm","diameter_or_tap_drill_mm","operation","depth_mm","notes"]);w.writerows(drills)
    print(json.dumps({"revision":p["revision"],"checks":r["checks"],"files_written":4,"physical_readiness":False},indent=2))


if __name__=="__main__":main()
