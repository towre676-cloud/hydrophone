// Nominal fit-check assembly, dimensions mm. NOT a stress-verified shop release.
// Strings X, bridge motion Y, Z up. Critical clamps/seals need coupon validation.
$fn=64;
base_x=600; base_y=320; base_t=12;
module box_at(p,s,c){color(c) translate(p) cube(s);}
module rod_y(p,l,d,c){color(c) translate(p) rotate([-90,0,0]) cylinder(h=l,d=d);}
module rod_x(p,l,d,c){color(c) translate(p) rotate([0,90,0]) cylinder(h=l,d=d);}
module ring_y(p,th,od,id){translate(p) rotate([-90,0,0]) difference(){
 cylinder(h=th,d=od); translate([0,0,-1]) cylinder(h=th+2,d=id);
 for(a=[0:45:315]) translate([25*cos(a),25*sin(a),-1]) cylinder(h=th+2,d=3.4);
}}
box_at([0,0,0],[600,320,12],[.12,.18,.22]);
// Nut and end supports; independent load path for string tension.
for(x=[50,500]) box_at([x,35,12],[20,80,108],[.45,.5,.53]);
box_at([55,40,120],[10,70,5],[.82,.65,.32]);
box_at([505,40,120],[10,70,5],[.82,.65,.32]);
for(y=[54,66,78,90]) {
 rod_x([60,y,125],400,.5,[.95,.8,.4]);
 rod_x([460,y,125],50,.5,[.95,.8,.4]);
}
// Shared bridge and carrier. Rod attachment is 40 mm below string saddle.
box_at([454,36,113],[12,72,12],[.65,.72,.75]);
box_at([447,53,95],[26,38,24],[.55,.62,.66]);
box_at([447,96,82],[26,6,40],[.55,.62,.66]);
// Clay sandwich centered 460,72,85, lower plate at75, top plate86.
box_at([440,52,75],[40,40,3],[.68,.72,.74]);
box_at([445,57,78],[30,30,8],[.72,.32,.17]);
box_at([440,52,86],[40,40,3],[.68,.72,.74]);
// Lower fixed pedestal. Top plate carrier connects through short standoffs.
box_at([440,52,12],[40,40,63],[.3,.36,.4]);
for(x=[448,469]) box_at([x,54,89],[3,36,6],[.5,.56,.6]);
// Four leaves in two Y-separated pairs resist pitch; verify parasitic motion.
for(x=[424,486]) for(yy=[52,92]) {
 box_at([x-6,yy-6,12],[12,12,43],[.35,.4,.43]);
 box_at([x-5,yy-.15,55],[10,.3,40],[.8,.82,.85]);
 box_at([x-6,yy-6,95],[12,12,6],[.6,.65,.68]);
}
box_at([418,46,95],[74,52,4],[.6,.65,.68]);
// Vented tank, internal 160x100x100, 80 mm nominal fill. Open top shown.
color([.4,.75,.85,.20]) difference(){
 translate([374,154,29]) cube([172,112,106]);
 translate([380,160,35]) cube([160,100,110]);
 translate([460,150,85]) rotate([-90,0,0]) cylinder(h=16,d=40);
}
box_at([380,160,35],[160,100,80],[.15,.6,.8,.15]);
color([.72,.76,.8]) ring_y([460,148.9,85],5,60,40);
rod_y([460,153.9,85],.10,60,[.8,.82,.84,.65]);
rod_y([460,102,85],51.9,3,[.78,.8,.82]);
// One suspended hydrophone; no wall/diaphragm contact.
color([.05,.07,.08]) translate([500,215,57]) cylinder(h=46,d=25);
color([.1,.1,.1]) translate([500,215,103]) cylinder(h=45,d=4.5);
// Slow writer shown parked: removable micrometer and load-cell module.
box_at([440,5,69],[40,23,32],[.85,.6,.2]);
rod_y([460,28,85],20,6,[.7,.72,.75]);
// Flexure overtravel stops are adjustable M4 screws, nominal +/-0.6 mm.
// Lid, drive puck, guards, cables, screw details and external DAQ not rendered.
