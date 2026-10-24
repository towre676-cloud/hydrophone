"""M04 machining tables, load-path arithmetic and explicit clearance checks.

Standard library only. Millimetres in geometry; SI for load calculations.
Nothing in this file operates hardware or qualifies a manufactured part.
"""
from pathlib import Path
import csv
import hashlib
import json
import math

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"generated"


def box_separation(a,sa,b,sb):
    """Signed maximum axis gap; positive means disjoint closed AABBs."""
    return max(max(b[i]-(a[i]+sa[i]),a[i]-(b[i]+sb[i])) for i in range(3))


def receipt(p):
    lead=p["lead"]; c=p["connectors"]; stage=p["stage"]; cell=p["cell"]; catch=p["catches"]
    force=p["operating"]["conditional_force_abs_N"]
    # Static screening assumptions, not supplied minimum material strengths.
    pin=.002994; span=.0102
    pin_stress=32*(force*span/4)/(math.pi*pin**3)
    root=.00238
    m3_axial=force/(math.pi*root**2/4)
    stop_root=.00735; hollow=.0035
    stop_area=math.pi*(stop_root**2-hollow**2)/4
    m6_axial=force/stop_area
    angle=math.radians(p["operating"]["maximum_angle_from_nominal_deg"])
    # Full neck at the maximum pin-to-mouth distance is an intentionally
    # conservative projected-width envelope through a10.2mm clevis slot.
    neck_half=4*math.cos(angle)+c["pin_to_mouth"]*math.sin(angle)
    cell_collar_circ=c["stud_collar_AF"]/math.cos(math.pi/6)
    front_gap=c["front_mouth_y"]-cell["front_face_y"]
    rear_gap=cell["rear_face_y"]-c["rear_mouth_y"]
    overlap=c["stud_outer_thread_length"]-(front_gap-c["stud_collar_length"])
    park=stage["park_translation_y"]
    # Head/neck are commercial keepouts; body source revision still governs.
    minimum_park_head_gap=40-(c["front_pin_y"]+park+c["head_OD"]/2)
    fixed_bush_back=p["fixed_nut"]["bush_axis_y"][1]
    park_housing_front=lead["housing_origin"][1]+park
    front_stop_gap=(110-3)-catch["front_screw_y"][1]
    rear_stop_gap=catch["rear_screw_y"][0]-(110+3)
    wp=p["water_rod"]
    angular_step_um=1000/360 #RH/LH M3×0.5 turnbuckle:1mm/revolution
    stem_max_bore_error=.1 #alignment target; actual runout is measured
    tests={
      "cell_front_and_rear_external_gaps_match":abs(front_gap-rear_gap)<1e-9,
      "cell_spigot_with_tolerance_below_depth":c["stud_cell_spigot_length"]+.05<cell["thread_max_depth"],
      "rod_end_nominal_engagement_matches_geometry":abs(overlap-c["stud_rod_end_engagement"])<1e-9,
      "full_rod_end_engagement_including_chamfer_margin":overlap-.20>=c["minimum_internal_thread_engagement"],
      "rod_end_nose_clearance":c["internal_thread_available"]-overlap>=2,
      "ball_and_spacers_fill_clevis":abs(c["ball_width"]+2*c["spacer_length_each"]-c["clevis_inside_width"])<1e-9,
      "two_degree_neck_envelope_clears_slot":neck_half+.2<c["clevis_inside_width"]/2,
      "stud_collar_fits_6p7mm_load_face_width":cell_collar_circ<6.7,
      "EZO_shaft_abutment_at_least9p6":lead["shoulder_diameter"]>=9.6,
      "EZO_housing_hole_at_most8p4":lead["housing_through_bore"]<=8.4,
      "journal_clearance_to_bearing_nominal_ID":max(lead["journal_diameter_limits"])<lead["bearing_ID"],
      "shaft_washer_OD11p8_clear_of_well":lead["housing_well_diameter"]-11.8>=.2,
      "housing_bearing_wall_is6mm":abs(lead["bearing_y"][1][0]-lead["bearing_y"][0][1]-6)<1e-9,
      "parked_housing_clears_fixed_nut":park_housing_front-fixed_bush_back>=5,
      "parked_joint_clears_instrument_fork":minimum_park_head_gap>=.4,
      "rear_joint_does_not_hit_lead_end":c["rear_pin_y"]-c["head_OD"]/2-lead["end_thread_y"][1]>=4,
      "catch_initial_gaps_match":abs(front_stop_gap-.3)<1e-9 and abs(rear_stop_gap-.3)<1e-9,
      "initial_operating_window_inside_minimum_catch_gap":p["operating"]["initial_displacement_abs"]<.3-catch["gap_setting_tolerance"],
      "water_rod_has_radial_clearance_after_alignment_target":(catch["hollow_bore"]-catch["water_rod_diameter"])/2>stem_max_bore_error+.01,
      "stop_drive_holes_clear_bore_by0p5mm":catch["end_drive_hole_radius"]-.5-catch["hollow_bore"]/2>=.5,
      "stop_drive_holes_inside_minimum_root_by0p3mm":stop_root*500-(catch["end_drive_hole_radius"]+.5)>=.3,
      "M8_stop_clears_water_clevis_by0p9mm":catch["water_clevis_inside_width"]/2-catch["screw_outer_diameter"]/2-stem_max_bore_error>=.9,
      "turnbuckle_nut_fits_rear_post_bore_and_clears_stop":5/math.cos(math.pi/6)<7.5 and wp["front_locknut_y"][0]-catch["rear_screw_y"][1]>=3,
      "turnbuckle_rear_locknut_clears_dry_boss":wp["boss_front_y"]-wp["rear_locknut_y"][1]>=.9,
      "boss_blind_hole_leaves0p7mm_bond_land":wp["boss_back_y"]-wp["boss_front_y"]-wp["boss_bore_depth"]>=.7-1e-9,
      "turnbuckle_flat_bores_leave0p8mm_web":14-2*wp["turnbuckle_bore_depth"]>=.8-1e-9,
      "turnbuckle_thread_minimum_over_adjustment":wp["rod_end_engagement_nominal"]-wp["adjustment_range_abs"]/2-.2>=5,
      "pin_nominal_static_screen":pin_stress/1e6<p["assumed_materials"]["steel_static_stress_screen_MPa"],
      "stop_nominal_static_screen":m6_axial/1e6<p["assumed_materials"]["steel_static_stress_screen_MPa"],
    }
    if not all(tests.values()):raise ValueError({"failed_checks":[k for k,v in tests.items() if not v]})
    #Catch loads on ONE stop post; do not assume two simultaneous contacts.
    post_height=.080; width=.020; thickness=.010
    I=width*thickness**3/12; E=p["assumed_materials"]["aluminium_E_Pa"]
    post_stress=force*post_height*(thickness/2)/I
    post_deflection=force*post_height**3/(3*E*I)
    return {"schema":"fusion.m04-calculation/1","status":"NOMINAL_ANALYTICAL_GEOMETRY_AND_STATIC_SCREEN_ONLY",
      "checks":tests,
      "connector":{"cell_to_rod_end_gap_mm":front_gap,"nominal_rod_end_engagement_mm":overlap,
        "minimum_full_engagement_after0p20mm_margin":overlap-.2,
        "neck_side_clearance_at2deg_mm":c["clevis_inside_width"]/2-neck_half,
        "pin_bending_stress_at20N_MPa":pin_stress/1e6,
        "M3_stud_axial_stress_at20N_MPa":m3_axial/1e6,
        "pin_and_thread_fatigue_or_source_material_qualified":False},
      "lead":{"EZO_static_axial_rating_N":2220,"EZO_single_bearing_load_ratio_at30N":2220/30,
        "declared_no_preload_permission":True,"axial_play_acceptance_mm":.01,
        "park_fixed_bush_to_housing_gap_mm":park_housing_front-fixed_bush_back,
        "park_instrument_fork_to_joint_gap_mm":minimum_park_head_gap,
        "ideal20N_torque_at_assumed0p2_efficiency_Nm":force*.0005/(2*math.pi*.2),
        "interpretation":"hand torque is not a force limiter; local measured force and displacement remain required"},
      "catches":{"load_case_N":force,"load_axis_XZ":[460,92],"off_axis_stop_moment_Nm":0,
        "front_gap_mm":front_stop_gap,"rear_gap_mm":rear_stop_gap,
        "hollow_screw_axial_stress_MPa":m6_axial/1e6,
        "minimum_stop_root_diameter_assumption_mm":stop_root*1000,
        "drive_hole_inner_ligament_mm":catch["end_drive_hole_radius"]-.5-catch["hollow_bore"]/2,
        "drive_hole_outer_ligament_mm":stop_root*500-(catch["end_drive_hole_radius"]+.5),
        "one_post_bending_stress_MPa":post_stress/1e6,
        "one_post_bending_deflection_um":post_deflection*1e6,
        "one_post_base_bolt_tension_screen_N":force*post_height/.005,
        "impact_rating_or_force_limit":False},
      "water_rod":{"turnbuckle_nominal_change_um_per_degree":angular_step_um,
        "nominal_adjustment_range_abs_mm":wp["adjustment_range_abs"],
        "radial_alignment_target_mm":stem_max_bore_error,
        "displacement_conversion_qualified":False},
      "transition":{"mechanical_sequence_implemented_in_document":True,"duration_measured":False,
        "instantaneous_or_within2s_claim":False,"task_core_registration_enabled":False},
      "physical_readiness":False}


def machining(p):
    #Stock XYZ are the installed part axes; a round part uses its boundingbox.
    parts=[]; drills=[]; turns=[]
    def P(code,qty,mat,size,note):parts.append([code,qty,mat,*size,note])
    def D(code,axis,direction,xyz,dia,op,depth,note=""):
        drills.append([code,axis,direction,*xyz,dia,op,depth,note])
    P("L01",1,"303stainless;certify",[12,95,12],"turnedshaft;localY0=global−125;allstations inturningtable")
    stations=[(0,15,"6h9","knobseat;mill0.5deepflatunderM3clamp"),(15,69.5,"M6x0.5-6g","finelead;2mmrunoutbeforeintegralshoulder"),(69.5,71.5,"10h9","integralshaftabutment;Ra0.4face;fillet≤0.15"),(71.5,86.5,"5.990..5.998","bearingjournal;Ra0.4;coaxial≤0.01"),(86.5,95,"M6x0.5-6g","twojamnutretainerthread")]
    for start,end,dia,note in stations:turns.append(["L01",start,end,dia,note])
    P("L02",1,"6061T6",[26,15,26],"knobOD26;6.02bore;radialM3setonshaftflat")
    D("L02","Y",1,[13,0,13],6.02,"REAM",15)
    D("L02","X",-1,[26,7.5,13],2.5,"TAP M3x0.5",10,"doesnotdrivetheforcecell")
    P("L03",1,"6061T6",[30,15,30],"opposedbearinghousing;notadummyblock;flat6mmwebbetweenwells")
    D("L03","Y",1,[15,0,15],6.4,"THRU",15)
    D("L03","Y",1,[15,0,15],12.03,"BORE12.03..12.05",4.5,"leftbearingwell")
    D("L03","Y",-1,[15,15,15],12.03,"BORE12.03..12.05",4.5,"rightbearingwell")
    for x in [5,25]:D("L03","Z",-1,[x,7.5,30],2.5,"TAP M3x0.5",6)
    P("L04",1,"hardened/groundsteel",[10,1,10],"rotatingabutmentwasherOD10;ID6.1;parallelwithin0.01")
    D("L04","Y",1,[5,0,5],6.1,"THRU",1)
    P("L05",2,"steel",[11.547,3.2,11.547],"hexAF10;M6x0.5through;customthinjamnuts")
    D("L05","Y",1,[5.7735,0,5.7735],5.5,"TAP M6x0.5",3.2)
    P("L06",1,"bearingbronze",[14,22,14],"nutbushOD10L15,frontflange14x2,rearthreadM10x.75L5;localY0global−102")
    turns +=[["L06",0,2,"14","frontflange"],["L06",2,17,"10.000..10.010","mainbody;indexflat0.5deep"],["L06",17,22,"M10x0.75","rearretainer"]]
    D("L06","Y",1,[7,0,7],5.5,"TAP M6x0.5",22,"6H;pitchgauge;deburrfirst/lastthread")
    P("L07",1,"steel",[16.166,4,16.166],"AF14M10x.75retainingnut")
    D("L07","Y",1,[8.083,0,8.083],9.25,"TAP M10x0.75",4)
    P("L08",1,"6061T6",[50,15,20],"fixednutbeam;noanalogueofblindball-endmicrometer")
    D("L08","Y",1,[25,0,10],10.02,"REAM10.02..10.04",15)
    for x in [4,46]:D("L08","Z",1,[x,7.5,0],3.4,"THRU",20,"legbolt")
    for y in [5,10]:D("L08","X",-1,[50,y,10],2.5,"TAP M3x0.5",20.5,"softpadagainstnutindexflat")
    P("L09",2,"6061T6",[8,15,70],"fixednutlegs;M3topandbottom")
    D("L09","Z",1,[4,7.5,0],2.5,"TAP M3x0.5",10)
    D("L09","Z",-1,[4,7.5,70],2.5,"TAP M3x0.5",8)
    P("S01",1,"6061T6",[36,20,18],"replacementslider;guides5.994..6.000;linebores6.010..6.020")
    for x in [8,28]:D("S01","Y",1,[x,0,6],6.015,"LINE REAM6.010..6.020",20)
    for x in [14,22]:
        for y in [6,14]:D("S01","Z",-1,[x,y,18],2.5,"TAP M3x0.5",11,"clearshaftboresbyXseparation")
    P("S02",1,"6061T6",[52,70,6],"writerroof;origin434,−55,113;detachfrominstrumentreadmode")
    for x in [22,30]:
        for y in [56,64]:D("S02","Z",1,[x,y,0],3.4,"THRU",6,"29mmspacerM3x45")
    for x in [16,36]:D("S02","Z",1,[x,9,0],3.4,"THRU",6,"6mmspacerM3x16tohousing")
    for x in [18,34]:D("S02","Z",1,[x,34.1,0],3.4,"THRU",6,"rearforkM3x12")
    for code,qty,length in [("S03",4,29),("S04",2,6)]:
        P(code,qty,"6061tube",[6,6,length],f"OD6 ID3.2 spacerL{length};axisZ;match±0.02")
        D(code,"Z",1,[3,3,0],3.2,"THRU",length)
    P("S05",2,"6061T6",[26,14,26],"cellclevisfrontreplacement+rearfork;10.2slotcenteredX;low13mm;front2mmrelief")
    D("S05","X",1,[0,8,5],3.1,"REAM",26,"Ø3pin;ballB6+2×2.1spacers")
    for x in [5,21]:D("S05","Z",-1,[x,6,26],2.5,"TAP M3x0.5",8)
    P("C01",2,"303stainless;certify",[6,13.1,6],"customcontrolledengagementstud;cellspigot2.2,hexAF5x2.4,externalM3x8.5")
    turns +=[["C01",0,2.2,"M3x0.5-6g","cellspigot;tipchamfer0.10max;2.20±0.05"],["C01",2.2,4.6,"hexAF5","shoulder;loadfaceonly"],["C01",4.6,13.1,"M3x0.5-6g","rodend;tipchamfer0.15max;5.5nominalengagement"]]
    P("C02",4,"groundsteel",[5.5,5.5,2.1],"ballspacers;axisXonassembly;ID3.1;length2.10±0.01")
    D("C02","Z",1,[2.75,2.75,0],3.1,"THRU",2.1,"stockaxisZ;rotateXaftermanufacture")
    P("C03",2,"groundsteel;certify",[33.2,5,5],"pinaxisX;head5x2,Ø2.994..3.000shoulder26.2,M2x.4tip5")
    turns +=[["C03",0,2,"5","head"],["C03",2,28.2,"2.994..3.000","fullclevisshoulder"],["C03",28.2,33.2,"M2x0.4","locknuts;washerID3.2clearsbeginningofthread"]]
    P("C04",2,"steel",[5.5,.5,5.5],"pinwasherOD5.5ID3.2;axisXassembled")
    D("C04","Y",1,[2.75,0,2.75],3.2,"THRU",.5)
    P("C05R",3,"steel",[5.774,2.4,5.774],"M3RHhexAF5jamnut;2celllinks+waterrodfront")
    P("C05L",1,"steel",[5.774,2.4,5.774],"M3LHhexAF5jamnut;waterrodrear")
    D("C05R","Y",1,[2.887,0,2.887],2.5,"TAP M3x0.5 RH",2.4)
    D("C05L","Y",1,[2.887,0,2.887],2.5,"TAP M3x0.5 LH",2.4)
    P("T01",2,"6061T6",[20,10,86],"catchposts;front450,93,12;rear450,120,12")
    D("T01","Y",1,[10,0,80],7.5,"TAP M8x0.5",10)
    D("T01","Z",1,[10,5,0],4.2,"TAP M5x0.8",18,"basebolt")
    D("T01","Z",1,[16,5,0],2,"REAM2H7",8,"antiyawdowel")
    D("T01","X",1,[0,5,80],2.5,"TAP M3x0.5",6.5,"retainedsofttipgrub;inspectboreafterlocking")
    P("T02",2,"303stainless;certify",[8,12.7,8],"headlessM8x.5hollowcatch;bore3.5;front/rearmirror;twoaxial1mmpinspannerholesr2.8")
    D("T02","Y",1,[4,0,4],3.5,"THRU",12.7,"deburrinside;3.3gaugeafterlocking")
    for x in [1.2,6.8]:D("T02","Y",1,[x,0,4],1,"DRILL",1.5,"pinspannerinputface;nodrivepinleftinstalled")
    P("T03",1,"steel",[6,6,6],"flatwritecatchtarget;centre460,110,92;replaceswaterrodeyeduringwrite")
    D("T03","X",1,[0,3,3],3.1,"REAM",6)
    P("T04",2,"steel+retainedbrassnose",[3,8,3],"M3grubL8;retainednoseØ2.45x1onØ2.00x2pressstem;bodyblindØ1.98x2")
    P("T05",1,"springsteel",[40,1,8],"Lpinspannerstrap;two1mmpinscentrespacing4.6;tips1.5long;removebeforeoperation")
    for x in [17.2,22.8]:D("T05","Y",1,[x,0,4],.98,"REAM0.980..0.985",1,"presspinsØ0.994..1.000,L2.5,1.5protrusion;removebeforeoperation")
    P("R01",1,"303stainless;certify",[6,30.5,6],"waterrodeye6cube atY107..113;stemØ3to137.5;RHthread129.6..137.5;headfaceclampedforzerobacklash")
    D("R01","X",1,[0,3,3],3.1,"REAM",6,"headcrosspin")
    P("R02",1,"303stainless;certify",[5.774,14,5.774],"turnbuckleAF5atY132..146;RHtap6mmfromfront;LHtap6mmfromrear;2mmcentralweb")
    D("R02","Y",1,[2.887,0,2.887],2.5,"FLAT-BOTTOM BORE",6.6,"0.6runoutbeyond6mmfullthread;solidweb0.8")
    D("R02","Y",-1,[2.887,14,2.887],2.5,"FLAT-BOTTOM BORE",6.6,"noextraunrecordeddrillpoint")
    D("R02","Y",1,[2.887,0,2.887],2.5,"BOTTOM TAP M3x0.5 RH FULLTHREAD",6)
    D("R02","Y",-1,[2.887,14,2.887],2.5,"BOTTOM TAP M3x0.5 LH FULLTHREAD",6)
    P("R03",1,"303stainless;certify",[3,11.3984,3],"M3x.5LHdoubleendstud;Y140.5..151.8984;turnfrom4mmstock;slot0.5x0.5atoneend")
    P("R04",1,"aluminium;bondqualified",[8,4,8],"drybossOD8t4;LH M3fullthread2.5;flatbottomhole3.3;solidbondland≥0.7")
    D("R04","Y",1,[4,0,4],2.5,"FLAT-BOTTOM BORE",3.3,"doNOTusetwistdrillpointasextraunrecordeddepth")
    D("R04","Y",1,[4,0,4],2.5,"BOTTOM TAP M3x0.5 LH FULLTHREAD",2.5,"0.8runoutallowancebeyondfullthread")
    P("R05",2,"groundsteel",[5.5,5.5,2.1],"waterhead/catchtargetspacersinM04replacement10.2waterclevis")
    D("R05","Z",1,[2.75,2.75,0],3.1,"THRU",2.1)
    P("S06",1,"6061T6",[26,14,26],"replacementwaterclevis;10.2slot;pinlocalY6;topmountlocalY6")
    D("S06","X",1,[0,6,5],3.1,"REAM",26)
    for x in [5,21]:D("S06","Z",-1,[x,6,26],2.5,"TAP M3x0.5",8)
    P("O01",1,"6061T6",[80,75,12],"frontbaseextension;origin420,−115,0")
    P("O02",1,"6061T6",[80,95,6],"underlapbrace;origin420,−115,−6")
    for code,ys in [("O01",[25,55]),("O02",[25,55,85])]:
        for x in [10,70]:
            for y in ys:D(code,"Z",1,[x,y,0],5.5,"THRU",12 if code=="O01" else 6,"M5x30washer/nut")
    for code in ["O01","O02"]:
        for x in [19,61]:D(code,"Z",1,[x,22.5,0],3.4,"THRU",12 if code=="O01" else 6,"fixednutlegM3x25")
    P("O03",4,"6061orcompatiblefoot",[25,25,20],"footOD25H20;topM5tap10;feltpad1mmoptionalbutrecord")
    D("O03","Z",-1,[12.5,12.5,20],4.2,"TAP M5x0.8",10)
    #All holes into original retained base are a NEW overlay, no sourceedit.
    P("BASE-OVERLAY",1,"retainedM03base",[600,360,12],"newholesonly;localY=globalY+40;M03itselfunchanged")
    for x in [430,490]:D("BASE-OVERLAY","Z",1,[x,10,0],5.5,"THRU",12,"braceglobalY−30")
    for x,y in p["outrigger"]["feet_centres"]:D("BASE-OVERLAY","Z",1,[x,y+40,0],5.5,"THRU",12,"footM5x20")
    for y in [98,125]:
        D("BASE-OVERLAY","Z",1,[460,y+40,0],5.5,"THRU",12,"catchM5x25")
        D("BASE-OVERLAY","Z",1,[466,y+40,0],2,"REAM2H7",6,"catchantiyawdowel")
    return parts,drills,turns


def main():
    raw=(ROOT/"completion.json").read_bytes();p=json.loads(raw);OUT.mkdir(exist_ok=True)
    r=receipt(p);r["completion_sha256"]=hashlib.sha256(raw).hexdigest()
    parts,drills,turns=machining(p)
    for filename,header,data in [
      ("cut_list.csv",["part","qty","material","stock_X_mm","stock_Y_mm","stock_Z_mm","operation"],parts),
      ("drill_table.csv",["part","axis","direction","local_X","local_Y","local_Z","diameter_mm","operation","depth_mm","notes"],drills),
      ("turning_table.csv",["part","local_axis_start_mm","local_axis_end_mm","diameter_or_thread","notes"],turns)]:
        with (OUT/filename).open("w",newline="") as f:w=csv.writer(f,lineterminator="\n");w.writerow(header);w.writerows(data)
    (OUT/"calculation_receipt.json").write_text(json.dumps(r,indent=2)+"\n")
    print(json.dumps({"revision":p["revision"],"checks_passed":len(r["checks"]),"physical_readiness":False},indent=2))


if __name__=="__main__":main()
