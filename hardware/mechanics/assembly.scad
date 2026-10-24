// M03 dimensioned manual prototype, mm. NOT physical qualification.
// Run build.py first. Commercial sensor is a keepout, not fabricated vendor CAD.
include <generated/params.scad>
$fn=48;
part="assembly"; // assembly,base,leaf,clay_plate,carrier,diaphragm_ring,writer
show_water=true;
show_sensor_keepout=true;
writer_parked=false;
rod_connected=true;
travel_y=0; // display only; do not treat this as an actuator command
module box(p,s,c=[.6,.65,.68]){color(c)translate(p)cube(s);}
module hole_z(p,l,d){translate(p)cylinder(h=l,d=d);}
module hole_y(p,l,d){translate(p)rotate([-90,0,0])cylinder(h=l,d=d);}
module hole_x(p,l,d){translate(p)rotate([0,90,0])cylinder(h=l,d=d);}
module rod_y(p,l,d,c=[.75,.78,.80]){color(c)hole_y(p,l,d);}
module rod_x(p,l,d,c=[.8,.8,.65]){color(c)hole_x(p,l,d);}
module segment(p,q,d,c=[.93,.73,.36]){v=q-p;n=norm(v);color(c)translate(p)rotate(a=acos(v[2]/n),v=[-v[1],v[0],0])cylinder(h=n,d=d);}

module base(){color([.17,.22,.26])difference(){
 translate(base_origin)cube(base_size);
 for(x=leaf_x)for(y=leaf_y)for(dx=[-8,8])hole_z([x+dx,y,-1],14,4.5);
 for(x=clay_mount_x)for(y=clay_mount_y){hole_z([x,y,-1],14,4.5);hole_z([x,y,-.1],4.1,7.5);}
 for(x=[25,65,550,590])for(y=[36,108])hole_z([x,y,-1],14,5.5);
 for(x=[450,470])for(y=[-30,35]){hole_z([x,y,-1],14,3.4);hole_z([x,y,-.1],3.3,6);}
}}
module leaf_blank(){difference(){cube([10,leaf_t,60]);for(z=[5,55])hole_y([5,-1,z],leaf_t+2,3.2);}}
module foot(){difference(){cube([32,24,6]);for(x=[8,24])hole_z([x,12,-1],8,4.5);hole_z([16,12,-1],8,3.4);}}
// Fixedpost top10mm front notch; rear jaw remains behind the leaf.
module lower_post(){difference(){cube([16,12,37]);
 translate([-1,-1,27])cube([18,6+leaf_t/2+1,11]);
 hole_z([8,6,-.1],12.1,2.5);hole_y([8,-1,32],14,3.2);
}}
module front_jaw(){difference(){cube([16,6,10]);hole_y([8,-1,5],8,3.2);}}
module upper_rear_jaw(){difference(){cube([16,6,18]);hole_y([8,-1,5],8,3.2);hole_z([8,3,11.9],6.2,2.5);}}
module flexures(){for(x=leaf_x)for(y=leaf_y){
 color([.35,.4,.44])translate([x-16,y-12,12])foot();
 color([.35,.4,.44])translate([x-8,y-6,18])lower_post();
 color([.7,.74,.77])translate([x-5,y-leaf_t/2,45])leaf_blank();
 color([.55,.62,.66])translate([x-8,y-leaf_t/2-6,45])front_jaw();
 color([.55,.62,.66])translate([x-8,y+leaf_t/2,95])upper_rear_jaw();
 color([.55,.62,.66])translate([x-8,y-leaf_t/2-6,95])front_jaw();
 rod_y([x,y-7,50],15,3);rod_y([x,y-7,100],15,3);
}}
module plate(contact="top"){difference(){cube(clay_plate);
 for(x=[5,43])for(y=[5,27])hole_z([x,y,-1],5,3.2);
 // shallow cross keys; geometrical contact, not guaranteed adhesion
 for(y=[8,16,24])translate([9,y-.4,contact=="top"?2.7:-.1])cube([30,.8,.4]);
}}
module pedestal(){difference(){cube([55,34,69]);for(x=[8.5,46.5])for(y=[6,28]){
 hole_z([x,y,-.1],12.1,3.3);hole_z([x,y,60.9],8.2,2.5);
}}}
module carrier(){difference(){cube(carrier_size);
 for(x=[26,106])translate([x,20,-1])cube([20,40,8]);
 for(x=[16,136])for(y=[12+leaf_t/2+3,52+leaf_t/2+3])hole_z([x,y,-1],8,3.4);
 for(x=[57,95])for(y=[21,43])hole_z([x,y,-1],8,3.4);
 for(x=[68,84])for(y=[6,70])hole_z([x,y,-1],8,3.4);
 for(y=[12,60])hole_z([76,y,-1],8,3.4);
}}
module bridge_bar(){difference(){cube([12,72,6]);
 for(y=[18,30,42,54])translate([-1,y-.3,5.7])cube([14,.6,.4]);
 for(y=[16,64])hole_z([6,y,-.1],4.1,2.5);
}}
module clevis(pin_y=8,mount_y=4){difference(){cube([26,14,26]);
 translate([8.9,-1,-1])cube([8.2,16,14]);
 // Clear the commercial cell's complete non-loading keepout by2mm;
 // the topbridge remains aboveZ100, clear of the cell'sZ96 maximum.
 if(pin_y==8)translate([-1,-1,-1])cube([28,3,14]);
 hole_x([-1,pin_y,5],28,3.1);
 for(x=[5,21])hole_z([x,mount_y,17.9],8.2,2.5);
}}
module moving_assembly(){translate([0,travel_y,0]){
 color([.64,.7,.74])translate(carrier_origin)carrier();
 color([.7,.75,.78])translate([454,36,119])bridge_bar();
 color([.7,.74,.76])translate(clay_upper)plate("bottom");
 for(x=clay_mount_x)for(y=clay_mount_y)color([.65,.7,.73])translate([x,y,95])difference(){cylinder(h=18,d=5);translate([0,0,-1])cylinder(h=20,d=3.2);}
 color([.6,.67,.72])translate([447,40,87])clevis(8,6);
 color([.6,.67,.72])translate([447,104,87])clevis(6,6);
}}
module cartridge(){
 color([.35,.4,.43])translate([432.5,55,12])pedestal();
 color([.7,.74,.76])translate(clay_lower)plate();
 box([445,57,84],[30,30,8],[.69,.32,.18]);
}
module ring(){rotate([-90,0,0])difference(){cylinder(h=6,d=60);translate([0,0,-1])cylinder(h=8,d=40);
 for(i=[0:7])translate([25*cos(45*i),25*sin(45*i),-1])cylinder(h=8,d=3.4);
}}
module gasket(th=.5){rotate([-90,0,0])difference(){cylinder(h=th,d=60);translate([0,0,-1])cylinder(h=th+2,d=40);
 for(i=[0:7])translate([25*cos(45*i),25*sin(45*i),-1])cylinder(h=th+2,d=3.4);
}}
module coupon(th=membrane_t){rotate([-90,0,0])difference(){cylinder(h=th,d=60);
 for(i=[0:7])translate([25*cos(45*i),25*sin(45*i),-1])cylinder(h=th+2,d=3.4);
}}
module tank(){
 membrane_plane=154-.5-membrane_t; // nominal free stack; actual compressed wet datum is measured
 color([.45,.74,.82,.28])difference(){
 union(){translate([374,154,29])cube([172,112,6]);translate([374,154,35])cube([172,6,100]);translate([374,260,35])cube([172,6,100]);translate([374,160,35])cube([6,100,100]);translate([540,160,35])cube([6,100,100]);}
 hole_y([460,153,92],14,40);
 for(i=[0:7])hole_y([460+25*cos(i*45),153,92+25*sin(i*45)],14,3.4);
 }
 if(show_water)box([380,160,35],[160,100,80],[.13,.57,.76,.12]);
 color([.7,.75,.78])translate([460,membrane_plane-6.5,92])ring();
 color([.15,.15,.15])translate([460,membrane_plane-.5,92])gasket();
 color([.75,.78,.82,.65])translate([460,membrane_plane,92])coupon();
 color([.15,.15,.15])translate([460,membrane_plane+membrane_t,92])gasket();
 color([.7,.75,.78])translate([460,160,92])ring();
 rod_y([460,membrane_plane-1,92],1,8);
 if(rod_connected){rod_y([460,114,92],membrane_plane-115,3);rod_x([447,110,92],26,3);}
 // Hydrophone envelope only. Cable supported from a separate splash lid.
 color([.07,.08,.09])translate([500,215,57])cylinder(h=46,d=25);
 color([.1,.1,.1])translate([500,215,103])cylinder(h=40,d=4.5);
}
module anchorfoot(){difference(){cube([60,100,8]);for(x=[10,50])for(y=[14,86])hole_z([x,y,-1],10,5.5);
 for(y=[22,78]){hole_z([30,y,-1],10,4.5);hole_z([30,y,-.1],4.6,7.5);}
}}
module anchorweb(){difference(){cube([20,80,110]);for(y=[22,34,46,58])hole_x([-1,y,104],22,4.5);
 for(y=[12,68])hole_z([10,y,-.1],16.1,3.3);
}}
module stringbanks(){
 for(x=[45,570]){
 color([.42,.48,.52])translate([x-30,22,12])anchorfoot();
 color([.46,.52,.55])translate([x-10,32,20])anchorweb();
 }
 for(y=string_y){
 // Eye/clamp bearing points are an installation datum; certify purchased
 // line retainers and measure actual positions, not this visual cylinder.
 rod_x([35,y,124],25,4);rod_x([560,y,124],25,4);
 segment([60,y,124],[460,y,125],.5);
 segment([460,y,125],[560,y,124],.5);
 }
}
module guidepost(){difference(){cube([10,12,65]);hole_y([5,-1,60],14,6);hole_z([5,6,-.1],12.1,2.5);hole_z([5,6,61.8],3.3,2.5);}}
module slider(){difference(){cube([36,20,18]);for(x=[8,28])hole_y([x,-1,6],22,6.05);}}
module writer(){
 for(x=[450,470])for(y=[-30,35])color([.5,.56,.60])translate([x-5,y-6,12])guidepost();
 for(x=[450,470])rod_y([x,-30,72],65,6);
 // Fixed nutbridge stands outside shaftposts; screw line equals load line.
 for(x=[435,477])box([x,-30,12],[8,15,72],[.55,.6,.63]);
 color([.65,.65,.62])difference(){translate([435,-30,84])cube([50,15,20]);hole_y([460,-31,92],17,5.5);}
 translate([0,writer_parked?-15:0,0]){
 color([.68,.71,.73])translate([442,-5,66])slider();
 // Thrustyoke and sensoradapter blanks require the journal/stud details
 // in ASSEMBLY.md; the commercial cell's body must remain contact-free.
 box([452,-5,84],[16,6,16],[.65,.7,.73]);
 box([452,12,84],[16,6,16],[.65,.7,.73]);
 rod_y([460,-45,92],40,6);
 rod_y([460,-53,92],8,26,[.38,.42,.45]);
 rod_y([460,18,92],2.9,3);
 rod_y([460,40,92],8,3);
 if(show_sensor_keepout)box([450.5,20.9,88],[17.5,19.1,8],[.9,.28,.22,.38]);
 if(!writer_parked)rod_x([447,48,92],26,3);
 }
}
assert(abs(travel_y)<=.6,"display travel exceeds nominal catch envelope");
if(part=="assembly"){base();flexures();cartridge();moving_assembly();tank();stringbanks();writer();}
else if(part=="base")base();
else if(part=="leaf")leaf_blank();
else if(part=="clay_plate")plate();
else if(part=="carrier")carrier();
else if(part=="diaphragm_ring")translate([30,0,30])ring();
else if(part=="writer")writer();
else assert(false,"unknown part selector");
