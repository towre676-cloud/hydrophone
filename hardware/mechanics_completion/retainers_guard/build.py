"""RG04 dimensional tables and conditional static screens. No lab claims."""
from pathlib import Path
import csv, hashlib, json, math

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'generated'


def data():
    cuts=[]; holes=[]
    def part(code,n,material,x,y,z,notes):cuts.append([code,n,material,x,y,z,notes])
    def hole(code,axis,x,y,z,d,op,depth,notes=''):holes.append([code,axis,x,y,z,d,op,depth,notes])
    part('RG01L',2,'6061-T6',15,16,24,'leftbarholder;pincentreX7/Z13;0.6slitfrompinZ13totop24')
    part('RG01R',2,'6061-T6',15,16,24,'rightbarholder;pincentreX10/Z13;0.6pinchslit')
    for code,px in [('RG01L',7),('RG01R',10)]:
        hole(code,'Y',px,0,13,6.05,'REAM',16)
        hole(code,'X',0,8,4,4.5,'THRU',15,'M4mount')
        hole(code,'X',0,13,4,2,'REAM',15,'locatingdowel')
        hole(code,'X',0,8,19,3.2,'CLEARANCE',px,'pinchbolt entry')
        hole(code,'X',px,8,19,2.5,'TAP M3x0.5',15-px,'opposingjaw')
    part('RG02',2,'polished304orcertifiedsteel',6,76,6,'nut/saddlebar;radius3;endR0.5;Ra<=0.8um requested')
    part('RG03',4,'6061-T6',18,11.5,12,'leftfixedclamp;originX17,Yyc-5.75,Z104')
    part('RG04',4,'6061-T6',18,11.5,18,'rightmovingclamp;originX588+tune,Yyc-5.75,Z98;tune0..8')
    hole('RG03','Z',8,2.75,12,2.5,'TAP M3x0.5',4,'topdowncapstan')
    for y in [3.75,7.75]:hole('RG03','X',0,y,4,2.4,'THRU',18,'M2fixedwebmount')
    hole('RG04','Z',8,2.75,18,2.5,'TAP M3x0.5',4,'topdowncapstan')
    hole('RG04','X',0,5.75,6,3.3,'TAP M4x0.7',10,'tensionstud;10engagement')
    hole('RG04','X',0,5.75,12,3,'REAMH7',8,'3m6guidepin;8pressengagement')
    for code,z in [('RG03',12),('RG04',18)]:
        for y in [2.75,8.75]:hole(code,'Z',15,y,z,1.25,'TAP M1.6x0.35',5,'shoe')
    part('RG05',8,'certified17-4PHH900ormin600MPayield',8,8,14,'turnM3x0.5stem4long;D6barrel9long;D8flange1;R0.5lineedges')
    part('RG06',8,'POM',6,10,2,'tailshoe;alllinecontactedgesR0.5')
    for y in [2,8]:hole('RG06','Z',3,y,0,1.8,'THRU',2)
    part('RG07',16,'stainlessshim',6,2,.35,'twostops/shoe;0.35gapcompressesnominal0.50lineby0.15;actualgriptest')
    part('RG08',4,'M4x0.7steelstud',50,4,4,'axisX;10mmengagedinmovingbody;8mmmanualtuningstroke')
    part('RG09',4,'3m6groundsteelpin',48,3,3,'axisX;8mmbodyengagement;20mmwebguideengagementthroughtravel')
    part('RG10',8,'standardsteelM4nutAF7',3.2,8.083,8.083,'twojamnuts/string;washerOD9ID4.3x0.8;turnfixednutnotbody')
    # Modifications to existingwebs are full nominal machining instructions.
    for side,web in [('left','M03_A02_left'),('right','M03_A02_right')]:
        for yc in [54,66,78,90]:
            hole(web,'X',0,yc-32,100,4.5,'VERTICALSLOT',20,'centreslocalZ100/104;tailpassglobalZ120/124;4.5wide8.5high')
            if side=='left':
                for y in [yc-2,yc+2]:hole(web,'X',0,y-32,88,1.6,'TAP M2x0.4',7,'entryglobalX35')
            else:
                hole(web,'X',0,yc-32,84,4.5,'THRU',20,'globalZ104tensionstud')
                hole(web,'X',0,yc-32,90,3.1,'REAM',20,'globalZ110guide')
        for yc in [42,102]:
            hole(web,'X',18 if side=='left' else 5,yc-32,92,3.3,'TAP M4x0.7',10,'afterholderpocket;leftdrilltoward-X,righttoward+X')
            hole(web,'X',18 if side=='left' else 5,yc+5-32,92,2,'REAM',6,'locatingdowel')
    part('RG11',6,'6061-T6',20,20,6,'guardfoot;globalcentresX30/300/580,Y8/154,Z12')
    hole('RG11','Z',10,10,0,3.4,'THRU',6)
    part('RG12',6,'6061-T6',10,10,147,'guardpost;globalZ18..165')
    for z in [0,147]:hole('RG12','Z',5,5,z,2.5,'TAP M3x0.5',12,'bottomup/topdown')
    for z in [99,139]:hole('RG12','Y',5,0,z,2.5,'TAP M3x0.5',10,'throughpanelmount')
    part('RG13',2,'6061-T6',605,10,5,'guardrailX20..625;frontY3,rearY149,Z165')
    for x in [10,280,560]:hole('RG13','Z',x,5,0,3.4,'THRU',5)
    for x in [84,106,484,506]:hole('RG13-rear','Z',x,5,5,2.5,'TAP M3x0.5',5,'topdownthroughhingemount')
    part('RG14F',1,'solidpolycarbonate',625,3,65,'frontpanelX0,Y18,Z105;loweredgeaccessnotchX576..590,Z0..5for7AFspanner')
    part('RG14R',1,'solidpolycarbonate',625,3,65,'rearpanelX0,Y140,Z105')
    for code in ['RG14F','RG14R']:
        for x in [30,300,580]:
            for z in [12,52]:hole(code,'Y',x,0,z,4.2,'THRU',3,'sleeveOD4ID3.2L3;washerOD9')
        for x in [10,615]:
            for z in [10,55]:hole(code,'Y',x,0,z,3.2,'THRU',3,'cornerangle')
    for x in [105,115,505,515]:hole('RG14F','Y',x,0,50,3.2,'THRU',3,'latchbracket')
    part('RG15',2,'solidpolycarbonate',3,119,65,'endpanelsX0/622,Y21,Z105')
    for y in [7,112]:
        for z in [10,55]:hole('RG15','X',0,y,z,3.2,'THRU',3)
    part('RG16',1,'solidpolycarbonate',625,125,3,'lidX0,Y18,Z170;frontlatchslots4.5x6.5')
    for x in [104,126,504,526]:hole('RG16','Z',x,118,0,3.4,'THRU',3,'upperhingeleaf')
    for x in [110,510]:hole('RG16','Z',x,13,0,4.5,'SLOTY6.5',3,'Ycentres12/14')
    part('RG17',4,'aluminiumangle15x15x2',15,15,65,'insidecorner;mirrorX/Yasdrawing')
    for z in [10,55]:
        hole('RG17','Y',7,0,z,3.2,'THRU',2)
        hole('RG17','X',0,7,z,3.2,'THRU',2)
    part('RG18',2,'6061-T6',34,20,18,'fixedhingefork;base4;earsX5..10/24..29,Y4..16,Z4..18')
    for x in [6,28]:hole('RG18','Z',x,14,0,3.2,'THRU',4,'M3into rearrail')
    hole('RG18','X',5,10,11,4.05,'REAM',24,'bothforkears')
    part('RG19',2,'6061-T6',30,30,14,'lidhingebase3;earX9..21,Y17..27,Z2..14')
    for x in [4,26]:hole('RG19','Z',x,8,0,3.2,'THRU',3)
    hole('RG19','X',9,22,8,4.05,'REAM',12)
    part('RG20',2,'groundsteelpin4h6',30,4,4,'hingepin;crossholesD1.5at1.5/28.5forretainers')
    for x in [1.5,28.5]:hole('RG20','Z',x,2,0,1.5,'THRU',4,'keeper')
    part('RG21',2,'6061-T6',20,20,20,'latchangle4thick;M4screw8longwithwasher')
    for x in [5,15]:hole('RG21','Y',x,0,5,2.5,'TAP M3x0.5',4)
    hole('RG21','Z',10,10,20,3.3,'TAP M4x0.7',4,'topdown;through4flange')
    part('RG22',1,'6061-T6',32,10,46,'footX4..28Y0..10Z0..3;vaneX4..28Y7..10;gussets3wideX4/25;cableearsX0..4/28..32Y7..10Z38..46;D6.2throughfrontedgereliefsatX8/24Y0')
    for x in [8,24]:hole('RG22','Z',x,0,0,6.2,'EDGE_RELIEF_THRU',46,'semicircularfrontedgeclearanceforM3rearclevishead;intentionalY0edgecentre;clipslowerfrontgussetonly')
    for x in [13,19]:hole('RG22','Z',x,3.6,0,2.4,'THRU',3,'M2headOD<=3.8;M2x6screw;nowasher')
    for x in [2,30]:hole('RG22','Y',x,7,42,2,'THRU',3,'cableearoutsideentiremotorbody')
    for x in [457,463]:
        hole('M03_C01','Z',x-384,113.6-40,6,1.6,'FLAT-BOTTOM BORE MAX',5,'topdown;totaldepth<=5;>=1mmbottomland')
        hole('M03_C01','Z',x-384,113.6-40,6,1.6,'BOTTOM TAP M2x0.4 FULLTHREAD',3.5,'>=3.5fullthread;M2x6engagement3;1.5mmrunoutreserve;M3centresep6.16mm')
    for x in [30,300,580]:
        for y in [8,154]:hole('M03_B01','Z',x,y+40,0,3.4,'THRU',12,'newguardpostcentres')
    return cuts,holes


def validate_drill_bounds(cuts,holes):
    stocks={row[0]:row[3:6] for row in cuts}
    checked=0
    for row in holes:
        code,axis,*_=row
        stock=stocks.get(code.replace('-rear',''))
        if stock is None:continue # explicitlyidentifiedmachiningonoldM03parts
        centre=row[2:5]; diameter=row[5]
        for index,label in enumerate('XYZ'):
            if label==axis:continue
            if row[6]=='EDGE_RELIEF_THRU' and label=='Y':
                if code!='RG22' or axis!='Z' or centre[1]!=0 or diameter!=6.2:
                    raise ValueError(f'undeclared edge relief:{row}')
                continue # deliberate semicircular cut centred on the front edge
            extra=1 if row[6]=='SLOTY6.5' and label=='Y' else 0
            radius=diameter/2+extra
            if not radius<=centre[index]<=stock[index]-radius:
                raise ValueError(f'out-of-stock transverseholecentre:{row}')
        checked+=1
    return checked


def receipts():
    T=25; proof=37.5; steel_E=193e9; d=.006;I=math.pi*d**4/64
    force_per_bank=4*T
    left=force_per_bank*(math.sin(math.atan2(4,35))-math.sin(math.atan2(1,400)))
    right=force_per_bank*(math.sin(math.atan2(4,36))-math.sin(math.atan2(1,100)))
    def pin(T):
        root=.0023865;Mb=T*.004;Mt=T*.003
        sig=32*Mb/(math.pi*root**3);tau=16*Mt/(math.pi*root**3)
        return math.sqrt(sig**2+3*tau**2)/1e6
    bracket_vol=(24*10*3+24*3*46-24*3*3+2*.5*7*35*3+2*4*3*8)
    checks={
      'right_body_gap_between_12mm_string_centres_mm':12-11.5,
      'right_min_jamnut_to_body_clearance_mm':588-(580+.8+2*3.2),
      'right_max_body_x_mm':588+8+18,
      'guard_right_end_inside_x_mm':622,
      'guard_to_motor_clearance_mm':140-(120+9),
      'motor_land_width_clearance_each_mm':(24-20.2)/2,
      'motor_land_height_clearance_each_mm':(46-41)/2,
      'drive_M2_head_to_gusset_clearance_mm':6-1.9,
      'drive_M2_head_to_M3_relief_clearance_mm':math.hypot(5,3.6)-3.1-1.9,
      'drive_M2_hole_to_M3_relief_ligament_mm':math.hypot(5,3.6)-3.1-1.2,
      'drive_adjacent_M2_head_clearance_mm':6-3.8,
      'drive_continuous_foot_and_gusset_depth_before_vane_mm':7-3.1,
      'cable_ear_hole_to_motor_keepout_clearance_mm':449.9-(446+1),
      'guide_min_web_engagement_through_stroke_mm':20,
      'guard_corner_mounts_clear_post_mounts_mm':min(30-10,615-580),
    }
    assert checks['right_max_body_x_mm']<checks['guard_right_end_inside_x_mm']
    assert all(checks[k]>0 for k in ['right_body_gap_between_12mm_string_centres_mm','right_min_jamnut_to_body_clearance_mm','guard_to_motor_clearance_mm','motor_land_width_clearance_each_mm','motor_land_height_clearance_each_mm','drive_M2_head_to_gusset_clearance_mm','drive_M2_head_to_M3_relief_clearance_mm','drive_M2_hole_to_M3_relief_ligament_mm','drive_adjacent_M2_head_clearance_mm','drive_continuous_foot_and_gusset_depth_before_vane_mm'])
    return {
      'schema':'fusion.RG04.screen/1','status':'NOMINAL_DIMENSIONAL_AND_STATIC_SCREEN_NOT_FABRICATED',
      'caps':{'tension_per_string_N':T,'total_tension_N':force_per_bank,'retainer_coupon_proof_target_N':proof},
      'fixed_bar_assumed_simply_supported_span_mm':60,
      'fixed_bar_nominal_downward_load_N':{'left':left,'right':right},
      'fixed_bar_deflection_um_conservative_centre_force':max(left,right)*.060**3/(48*steel_E*I)*1e6,
      'fixed_bar_bending_stress_MPa':max(left,right)*.060/4*(d/2)/I/1e6,
      'capstan_stem_von_mises_MPa':{'25N':pin(T),'37p5N_proof':pin(proof)},
      'capstan_stem_material_required_minimum_yield_MPa':600,
      'capstan_retention_not_identified_from_torque':True,
      'illustrative_two_turn_tail_force_N':{str(mu):T*math.exp(-mu*4*math.pi) for mu in [.05,.1,.15]},
      'friction_values_are_assumptions_not_validated_bounds':True,
      'retainer_strength_and_slip_qualified':False,
      'nylon_candidate':{'manufacturer':'Sufix/Rapala','item':'SUFML30100C','nominal_diameter_mm':.50,'label_strength_lb':30,'label_force_N':30*4.4482216152605,'label_is_not_installed_assembly_rating':True},
      'moving_drive_addition':{'bracket_upper_geometry_mass_g':bracket_vol*2.7/1000,'motor_budget_g':10,'screws_washers_cable_budget_g':2,'total_budget_g':bracket_vol*2.7/1000+12,'installed_moving_mass_must_be_weighed':True},
      'exciter':{'model':'DAEX-13-4SM','nominal_impedance_ohm':4,'catalogue_RMS_rating_W':3,'manufacturer_drawing_max_body_mm':[20.2,41,9],'free_Fs_Hz':950,'useful_low_note_force_or_displacement_not_established':True},
      'checks':checks,
      'guard':{'material':'3mm solid polycarbonate','closed_max_z_mm':188,'approx_90deg_open_front_max_z_mm':313,'interlock':False,'impact_or_reach_compliance_tested':False,'purpose':'projectile/splashhood;stoppedserviceonly;nohandsduringtension/excitation'},
      'physical_readiness':False,
    }


def main():
    OUT.mkdir(exist_ok=True)
    cuts,holes=data()
    for name,header,rows in [('cut_list.csv',['part','qty','material','stock_X_mm','stock_Y_mm','stock_Z_mm','machining'],cuts),('drill_table.csv',['part','axis','local_X_mm','local_Y_mm','local_Z_mm','diameter_or_tap_drill_mm','operation','depth_mm','notes'],holes)]:
        with (OUT/name).open('w',newline='') as f:
            w=csv.writer(f,lineterminator='\n');w.writerow(header);w.writerows(rows)
    result=receipts();result['own_part_hole_operations_checked_in_stock']=validate_drill_bounds(cuts,holes);result['parts_scad_sha256']=hashlib.sha256((ROOT/'parts.scad').read_bytes()).hexdigest()
    (OUT/'screening_receipt.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'parts':len(cuts),'hole_operations':len(holes),'nominal_checks':'PASS','physical_readiness':False}))


if __name__=='__main__':main()
