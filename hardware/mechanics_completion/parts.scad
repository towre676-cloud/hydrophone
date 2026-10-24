// M04 custom completion parts. mm. Threads shown at envelope/pilot diameter;
// the machining tables specify thread and fit. No hardware is commanded.
$fn=64;
module m04_hx(p,l,d){translate(p)rotate([0,90,0])cylinder(h=l,d=d);}
module m04_hy(p,l,d){translate(p)rotate([-90,0,0])cylinder(h=l,d=d);}
module m04_hz(p,l,d){translate(p)cylinder(h=l,d=d);}
module m04_box(p,s,c=[.62,.67,.70]){color(c)translate(p)cube(s);}
module m04_hex_y(p,l,af,c=[.67,.7,.73]){color(c)translate(p)rotate([-90,0,0])cylinder(h=l,d=af/cos(30),$fn=6);}

module m04_lead(){ //partaxisY;localY0isglobal−125
 union(){m04_hy([0,0,0],15,6);m04_hy([0,15,0],54.5,6);
 m04_hy([0,69.5,0],2,10);m04_hy([0,71.5,0],15,5.994);
 m04_hy([0,86.5,0],8.5,6);}
}
module m04_knob(){difference(){m04_hy([13,0,13],15,26);m04_hy([13,-1,13],17,6.02);m04_hx([15,7.5,13],12,2.5);}}
module m04_bearing_housing(){difference(){cube([30,15,30]);
 m04_hy([15,-1,15],17,6.4);m04_hy([15,-.01,15],4.51,12.03);m04_hy([15,10.5,15],4.51,12.03);
 for(x=[5,25])m04_hz([x,7.5,23.99],6.02,2.5);
}}
module m04_thrust_bearing(){ //commercialEZOenvelope;orientationwashersdocumented
 difference(){m04_hy([0,0,0],4.5,12);m04_hy([0,-1,0],6.5,6);}
}
module m04_thrust_washer(){difference(){m04_hy([0,0,0],1,10);m04_hy([0,-1,0],3,6.1);}}
module m04_locknut(af=10,l=3.2,bore=5.5){difference(){rotate([-90,0,0])cylinder(h=l,d=af/cos(30),$fn=6);m04_hy([0,-1,0],l+2,bore);}}
module m04_nut_bush(){difference(){union(){m04_hy([0,0,0],2,14);m04_hy([0,2,0],15,10);m04_hy([0,17,0],5,10);}
 m04_hy([0,-1,0],24,5.5);translate([4.5,2,-6])cube([3,15,12]);
}}
module m04_nut_beam(){difference(){cube([50,15,20]);m04_hy([25,-1,10],17,10.02);
 for(x=[4,46])m04_hz([x,7.5,-1],22,3.4);
 for(y=[5,10])m04_hx([29.4,y,10],21,2.5);
}}
module m04_nut_leg(){difference(){cube([8,15,70]);m04_hz([4,7.5,-.01],10.02,2.5);m04_hz([4,7.5,61.99],8.02,2.5);}}
module m04_slider(){difference(){cube([36,20,18]);for(x=[8,28])m04_hy([x,-1,6],22,6.015);
 for(x=[14,22])for(y=[6,14])m04_hz([x,y,6.99],11.02,2.5);
}}
module m04_roof(){difference(){cube([52,70,6]);
 for(x=[22,30])for(y=[56,64])m04_hz([x,y,-1],8,3.4);
 for(x=[16,36])m04_hz([x,9,-1],8,3.4);
 for(x=[18,34])m04_hz([x,34.1,-1],8,3.4);
}}
module m04_spacer(length=29,od=6,id=3.2){difference(){cylinder(h=length,d=od);translate([0,0,-1])cylinder(h=length+2,d=id);}}
module m04_cell_fork(pin_y=8){difference(){cube([26,14,26]);
 translate([7.9,-1,-1])cube([10.2,16,14]);
 //Frontreliefforcellkeepout;waterforkalsoallowsM8stoptipthroughslot.
 translate([-1,-1,-1])cube([28,3,14]);
 m04_hx([-1,pin_y,5],28,3.1);
 for(x=[5,21])m04_hz([x,6,17.99],8.02,2.5);
}}
module m04_port_stud(){ //localY0isblindtip;13.1overall
 union(){m04_hy([0,0,0],2.2,3);m04_hex_y([0,2.2,0],2.4,5);m04_hy([0,4.6,0],8.5,3);}
}
module m04_spherical_end(){ //pincentre0, mouth18.5;sourceKBRM03commercialenvelope
 difference(){union(){m04_hx([-2.25,0,0],4.5,13);m04_hy([0,3,0],15.5,8);}
 m04_hx([-4,0,0],8,3);m04_hy([0,10.5,0],9,2.5);}
 color([.7,.73,.75])difference(){m04_hx([-3,0,0],6,6.5);m04_hx([-4,0,0],8,3);}
}
module m04_cross_pin(){union(){m04_hx([0,0,0],2,5);m04_hx([2,0,0],26.2,2.997);m04_hx([28.2,0,0],5,2);}}
module m04_ball_spacers(pin_y=48,water=false){for(xx=[452.9,463])color([.72,.74,.77])difference(){m04_hx([xx,pin_y,92],2.1,5.5);m04_hx([xx-.1,pin_y,92],2.3,3.1);}}
module m04_cell_link(){
 //Bothloadedcellportsarecontrolledshoulderinterfaces;bodycontactforbidden.
 color([.85,.27,.2,.42])translate([450.5,5,88])cube([17.5,19.1,8]);
 color([.75,.78,.8])translate([460,21.9,92])m04_port_stud();
 color([.75,.78,.8])translate([460,7.2,92])rotate([0,0,180])m04_port_stud();
 color([.25,.28,.31])translate([460,48,92])rotate([0,0,180])m04_spherical_end();
 color([.25,.28,.31])translate([460,-18.9,92])m04_spherical_end();
 color([.7,.72,.75])translate([460,27.1,92])m04_locknut(5,2.4,2.5);
 color([.7,.72,.75])translate([460,-.4,92])m04_locknut(5,2.4,2.5);
 m04_ball_spacers(-18.9);
 color([.72,.75,.78])translate([445,-18.9,92])m04_cross_pin();
}
module m04_writer(parked=true){
 //RetaininspectedM03guideposts/shafts;replacementsliderprovidesrealroofholes.
 for(x=[450,470])for(y=[-30,35])color([.46,.52,.56])translate([x-5,y-6,12])difference(){cube([10,12,65]);m04_hy([5,-1,60],14,6);m04_hz([5,6,-.1],12.1,2.5);}
 for(x=[450,470])color([.72,.75,.78])m04_hy([x,-30,72],65,6);
 for(x=[435,477])color([.5,.56,.6])translate([x,-100,12])m04_nut_leg();
 color([.6,.65,.68])translate([435,-100,82])m04_nut_beam();
 color([.67,.55,.24])translate([460,-102,92])m04_nut_bush();
 color([.65,.68,.7])translate([460,-85,92])m04_locknut(14,4,9.25);
 translate([0,parked?-15:0,0]){
 color([.65,.7,.74])translate([442,-5,66])m04_slider();
 for(x=[456,464])for(y=[1,9])color([.65,.69,.72])translate([x,y,84])m04_spacer(29);
 color([.62,.67,.72])translate([434,-55,113])m04_roof();
 color([.62,.67,.72])translate([447,-26.9,87])m04_cell_fork();
 for(x=[450,470])color([.65,.69,.72])translate([x,-46,107])m04_spacer(6);
 color([.55,.62,.67])translate([445,-53.5,77])m04_bearing_housing();
 color([.72,.75,.78])translate([460,-125,92])m04_lead();
 color([.28,.32,.36])translate([447,-125,79])m04_knob();
 for(y=[-53.5,-43])color([.7,.73,.76])translate([460,y,92])m04_thrust_bearing();
 color([.7,.73,.76])translate([460,-38.5,92])m04_thrust_washer();
 for(y=[-37.5,-34.3])color([.62,.65,.68])translate([460,y,92])m04_locknut();
 m04_cell_link();
 }
 if(!parked){m04_ball_spacers(48);color([.72,.75,.78])translate([445,48,92])m04_cross_pin();}
}
module m04_catch_post(){difference(){cube([20,10,86]);m04_hy([10,-1,80],12,7.5);
 m04_hz([10,5,-.01],18.02,4.2);m04_hz([16,5,-.01],8.02,2);
 m04_hx([-.01,5,80],6.52,2.5);
}}
module m04_hollow_catch(){difference(){m04_hy([4,0,4],12.7,8);m04_hy([4,-1,4],14.7,3.5);
 for(x=[1.2,6.8])m04_hy([x,-.01,4],1.52,1);
}}
module m04_catch_target(){difference(){cube([6,6,6]);m04_hx([-1,3,3],8,3.1);}}
module m04_catches(write_target=true){
 for(y=[93,120])color([.5,.57,.62])translate([450,y,12])m04_catch_post();
 color([.73,.75,.78])translate([456,94,88])m04_hollow_catch();
 color([.73,.75,.78])translate([464,126,88])rotate([0,0,180])m04_hollow_catch();
 if(write_target){color([.7,.73,.77])translate([457,107,89])m04_catch_target();m04_ball_spacers(110,true);color([.72,.75,.78])translate([445,110,92])m04_cross_pin();}
}
module m04_water_rod_head(){union(){difference(){cube([6,6,6]);m04_hx([-1,3,3],8,3.1);}m04_hy([3,6,3],24.5,3);}}
module m04_turnbuckle(){difference(){rotate([-90,0,0])cylinder(h=14,d=5/cos(30),$fn=6);
 m04_hy([0,-.01,0],6.62,2.5);m04_hy([0,7.39,0],6.62,2.5);
}}
module m04_dry_boss(){difference(){m04_hy([0,0,0],4,8);m04_hy([0,-.01,0],3.32,2.5);}}
module m04_water_rod(){
 color([.72,.75,.78])translate([457,107,89])m04_water_rod_head();
 color([.72,.75,.78])translate([460,132,92])m04_turnbuckle();
 color([.72,.75,.78])m04_hy([460,140.5,92],11.3984,3);
 for(y=[129.6,146])color([.68,.71,.74])translate([460,y,92])m04_locknut(5,2.4,2.5);
 m04_ball_spacers(110,true);color([.72,.75,.78])translate([445,110,92])m04_cross_pin();
}
module m04_outrigger_plate(){difference(){cube([80,75,12]);for(x=[10,70])for(y=[25,55])m04_hz([x,y,-1],14,5.5);
 for(x=[19,61])m04_hz([x,22.5,-1],14,3.4);
}}
module m04_outrigger_brace(){difference(){cube([80,95,6]);for(x=[10,70])for(y=[25,55,85])m04_hz([x,y,-1],8,5.5);
 for(x=[19,61])m04_hz([x,22.5,-1],8,3.4);
}}
module m04_foot(){difference(){cylinder(h=20,d=25);translate([0,0,9.99])cylinder(h=10.02,d=4.2);}}
module m04_outrigger(){
 color([.25,.3,.34])translate([420,-115,0])m04_outrigger_plate();
 color([.33,.39,.43])translate([420,-115,-6])m04_outrigger_brace();
 for(p=[[20,-20],[580,-20],[20,300],[580,300]])color([.35,.4,.44])translate([p[0],p[1],-20])m04_foot();
}
module m04_base_overlay(){ //negative spaces only;globalcoordinates
 for(x=[430,490])m04_hz([x,-30,-1],14,5.5);
 for(p=[[20,-20],[580,-20],[20,300],[580,300]])m04_hz([p[0],p[1],-1],14,5.5);
 for(y=[98,125]){m04_hz([460,y,-1],14,5.5);m04_hz([466,y,-.01],6.02,2);}
 for(x=[30,300,580])for(y=[8,154])m04_hz([x,y,-1],14,3.4); //RG04guardfootmounts
}
