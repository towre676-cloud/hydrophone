// M04 integrated nominal assembly. M03 sources remain immutable.
include <../mechanics/generated/params.scad>
use <../mechanics/assembly.scad>
use <parts.scad>
use <retainers_guard/parts.scad>
$fn=48;
selection="assembly"; //orlead,bearing_housing,nut_bush,port_stud,cell_fork,catch_post,hollow_catch,turnbuckle
mode="read"; //read:writerparked+waterrod;write:writerengaged+flattarget,rodOUT
guard_angle=0;
show_sensor_keepout=true;
travel_y=0;
module m04_instrument_moving(){
 color([.64,.7,.74])translate(carrier_origin)difference(){carrier();
  for(x=[457,463])m04_hz([x-384,113.6-40,.99],5.02,1.6); //M2blindfromcarrierTOP;newRG04overlay
 }
 color([.7,.75,.78])translate([454,36,119])bridge_bar();
 color([.7,.74,.76])translate(clay_upper)plate("bottom");
 for(x=clay_mount_x)for(y=clay_mount_y)color([.65,.7,.73])translate([x,y,95])m04_spacer(18,5,3.2);
 color([.6,.67,.72])translate([447,40,87])m04_cell_fork(8);
 color([.6,.67,.72])translate([447,104,87])m04_cell_fork(6);
}
module m04_tank(){
 plane=154-.5-membrane_t;
 color([.45,.74,.82,.25])difference(){union(){
 translate([374,154,29])cube([172,112,6]);translate([374,154,35])cube([172,6,100]);
 translate([374,260,35])cube([172,6,100]);translate([374,160,35])cube([6,100,100]);translate([540,160,35])cube([6,100,100]);}
 m04_hy([460,153,92],14,40);for(i=[0:7])m04_hy([460+25*cos(i*45),153,92+25*sin(i*45)],14,3.4);}
 color([.13,.57,.76,.10])translate([380,160,35])cube([160,100,80]);
 color([.7,.75,.78])translate([460,plane-6.5,92])ring();
 color([.15,.15,.15])translate([460,plane-.5,92])gasket();
 color([.75,.78,.82,.65])translate([460,plane,92])coupon();
 color([.15,.15,.15])translate([460,plane+membrane_t,92])gasket();
 color([.7,.75,.78])translate([460,160,92])ring();
 color([.72,.75,.78])translate([460,plane-4,92])m04_dry_boss();
 color([.07,.08,.09])translate([500,215,57])cylinder(h=46,d=25);
 color([.1,.1,.1])translate([500,215,103])cylinder(h=40,d=4.5);
}
module m04_anchor_banks(){for(side=["left","right"]){
 x=side=="left"?45:570;
 color([.42,.48,.52])translate([x-30,22,12])anchorfoot();
 color([.46,.52,.55])difference(){translate([x-10,32,20])anchorweb();rg_web_machining(side);}
 }rg04_retainer_assembly(false);
 for(y=string_y){segment([60,y,124],[460,y,125],.5);segment([460,y,125],[560,y,124],.5);}
}
assert(mode=="read"||mode=="write","unknownofflineassemblymode");
if(selection=="assembly"){
 difference(){base();m04_base_overlay();}
 flexures();cartridge();m04_instrument_moving();m04_tank();m04_anchor_banks();
 m04_outrigger();m04_writer(mode=="read");m04_catches(mode=="write");
 if(mode=="read")m04_water_rod();
 rg04_guard(guard_angle);rg04_drive_mount(true);
}
else if(selection=="lead")m04_lead();
else if(selection=="bearing_housing")m04_bearing_housing();
else if(selection=="nut_bush")m04_nut_bush();
else if(selection=="port_stud")m04_port_stud();
else if(selection=="cell_fork")m04_cell_fork();
else if(selection=="catch_post")m04_catch_post();
else if(selection=="hollow_catch")m04_hollow_catch();
else if(selection=="turnbuckle")m04_turnbuckle();
else assert(false,"unknownpartselector");
