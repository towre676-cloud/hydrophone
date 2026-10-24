// RG04 completion kit,mm. M03 files remain unchanged.
// use<> this file and call rg04_retainer_assembly(),rg04_guard(),rg04_drive_mount().
// Negative spaces are real machined details; vendor exciter is a keepout only.
rg_part="assembly";
$fn=48;
module rg_hx(p,l,d){translate(p)rotate([0,90,0])cylinder(h=l,d=d);}
module rg_hy(p,l,d){translate(p)rotate([-90,0,0])cylinder(h=l,d=d);}
module rg_hz(p,l,d){translate(p)cylinder(h=l,d=d);}
module rg_box(p,s,c){color(c)translate(p)cube(s);}
module rg_bar_holder(side="left"){
 px=side=="left"?7:10;
 difference(){cube([15,16,24]);
  rg_hy([px,-1,13],18,6.05);
  translate([px-.3,-1,13])cube([.6,18,12]); // pinch slit frompin to top
  rg_hx([-1,8,4],17,4.5);
  rg_hx([-1,13,4],17,2);
  rg_hx([-1,8,19],px+1,3.2);
  rg_hx([px,8,19],16-px,2.5); // tapM3 across pinch slit
 }
}
module rg_fixed_clamp(){difference(){cube([18,11.5,12]);
 rg_hz([8,2.75,7.9],4.2,2.5); // M3capstan fromtop
 for(y=[3.75,7.75])rg_hx([-1,y,4],20,2.4);
 for(y=[2.75,8.75])rg_hz([15,y,6.9],5.2,1.25); // M1.6shoe
}}
module rg_tension_clamp(){difference(){cube([18,11.5,18]);
 rg_hz([8,2.75,13.9],4.2,2.5);
 rg_hx([-.1,5.75,6],10.1,3.3); // M4tensionstud,10deep
 rg_hx([-.1,5.75,12],8.1,3); // pressguidepin
 for(y=[2.75,8.75])rg_hz([15,y,12.9],5.2,1.25);
}}
module rg_capstan_pin(){union(){cylinder(h=4,d=3);translate([0,0,4])cylinder(h=9,d=6);translate([0,0,13])cylinder(h=1,d=8);}}
module rg_shoe(){difference(){cube([6,10,2]);for(y=[2,8])rg_hz([3,y,-1],4,1.8);}}
module rg_retainer_body(side="left",yc=54,tune=0){
 assert(tune>=0&&tune<=8,"tunertravel0..8mm");
 ox=side=="left"?17:588+tune;
 bz=side=="left"?104:98;
 color([.7,.72,.74])translate([ox,yc-5.75,bz])if(side=="left")rg_fixed_clamp();else rg_tension_clamp();
 color([.75,.78,.8])translate([ox+8,yc-3,112])rg_capstan_pin();
 // Two .35mm stopshims bound nominal shoe closure, not friction capacity.
 for(yy=[yc-5,yc+3])rg_box([ox+12,yy,116],[6,2,.35],[.65,.65,.65]);
 color([.8,.83,.85])translate([ox+12,yc-5,116.35])rg_shoe();
 if(side=="right"){
  color([.75,.78,.8])rg_hx([548+tune,yc,104],50,4);
  color([.75,.78,.8])rg_hx([548+tune,yc,110],48,3);
  for(xx=[580.8,584])color([.65,.67,.69])translate([xx,yc,104])rotate([0,90,0])cylinder(h=3.2,d=7/cos(30),$fn=6);
 }
}
module rg_web_machining(side="left"){
 // Use as subtractive tooling on the appropriate M03 anchorweb.
 for(yc=[54,66,78,90]){
  hull(){rg_hx([side=="left"?34:559,yc,120],22,4.5);rg_hx([side=="left"?34:559,yc,124],22,4.5);}
  if(side=="right"){
   rg_hx([559,yc,104],22,4.5);rg_hx([559,yc,110],22,3.1);
  }else for(yy=[yc-2,yc+2])rg_hx([34.9,yy,108],7.2,1.6); // tapM2
 }
 for(yc=[42,102]){
  if(side=="left")translate([52.9,yc-8,108])cube([2.2,16,23]);
  else translate([559.9,yc-8,108])cube([5.2,16,23]);
  rg_hx([side=="left"?42.9:564.9,yc,112],10.2,3.3); // tapM4
  rg_hx([side=="left"?46.9:564.9,yc+5,112],6.2,2); // locatingdowel
 }
}
module rg04_retainer_assembly(show_line=true){
 for(side=["left","right"]){
  for(yc=[42,102])color([.62,.67,.71])translate([side=="left"?53:550,yc-8,108])rg_bar_holder(side);
  color([.76,.79,.81])rg_hy([side=="left"?60:560,34,121],76,6);
  for(yc=[54,66,78,90])rg_retainer_body(side,yc);
 }
 if(show_line)for(yc=[54,66,78,90]){
  // Nominalstraightlegs; circularbar contact/endstretch require measurement.
  color([.94,.74,.36])rg_hx([60,yc,124],400,.5);
  color([.94,.74,.36])rg_hx([460,yc,124],100,.5);
 }
}

module rg_corner_angle(){difference(){union(){cube([15,2,65]);cube([2,15,65]);}
 for(z=[10,55]){rg_hy([7,-1,z],4,3.2);rg_hx([-1,7,z],4,3.2);}
}}
module rg_guard_post(){difference(){cube([10,10,147]);rg_hz([5,5,-.1],12.1,2.5);rg_hz([5,5,134.9],12.2,2.5);
 for(z=[99,139])rg_hy([5,-1,z],12,2.5);
}}
module rg_guard_foot(){difference(){cube([20,20,6]);rg_hz([10,10,-1],8,3.4);}}
module rg_guard_rail(){difference(){cube([605,10,5]);for(x=[10,280,560])rg_hz([x,5,-1],7,3.4);}}
module rg_side_panel(rear=false){difference(){cube([625,3,65]);
 for(x=[30,300,580])for(z=[12,52])rg_hy([x,-1,z],5,4.2);
 for(x=[10,615])for(z=[10,55])rg_hy([x,-1,z],5,3.2);
 if(!rear){for(x=[105,115,505,515])rg_hy([x,-1,50],5,3.2);
  translate([576,-1,-1])cube([14,5,6]); // offset7AFspanneraccessbelowline plane
 }
}}
module rg_end_panel(){difference(){cube([3,119,65]);for(y=[7,112])for(z=[10,55])rg_hx([-1,y,z],5,3.2);}}
module rg_lid(){difference(){cube([625,125,3]);
 for(x=[104,126,504,526])rg_hz([x,118,-1],5,3.4);
 for(x=[110,510])hull(){rg_hz([x,12,-1],5,4.5);rg_hz([x,14,-1],5,4.5);}
}}
module rg_fixed_hinge(){difference(){union(){cube([34,20,4]);translate([5,4,4])cube([5,12,14]);translate([24,4,4])cube([5,12,14]);}
 for(x=[6,28])rg_hz([x,14,-1],6,3.2);
 rg_hx([4,10,11],26,4.05);
}}
module rg_lid_hinge(){difference(){union(){cube([30,30,3]);translate([9,17,2])cube([12,10,12]);}
 for(x=[4,26])rg_hz([x,8,-1],5,3.2);
 rg_hx([8,22,8],14,4.05);
}}
module rg_latch(){difference(){union(){cube([20,4,20]);translate([0,0,16])cube([20,20,4]);}
 for(x=[5,15])rg_hy([x,-1,5],6,2.5);
 rg_hz([10,10,15.9],4.2,3.3);
}}
module rg_hinge_pin(){difference(){rg_hx([0,2,2],30,4);for(x=[1.5,28.5])rg_hz([x,2,-1],6,1.5);}}
module rg04_guard(lid_angle=0){
 assert(lid_angle>=0&&lid_angle<=95,"serviceopening0..95deg");
 for(x=[30,300,580])for(y=[8,154]){
  color([.5,.55,.59])translate([x-10,y-10,12])rg_guard_foot();
  color([.58,.63,.66])translate([x-5,y-5,18])rg_guard_post();
 }
 for(y=[3,149])color([.62,.66,.69])translate([20,y,165])rg_guard_rail();
 color([.55,.82,.9,.22])translate([0,18,105])rg_side_panel();
 color([.55,.82,.9,.22])translate([0,140,105])rg_side_panel(true);
 color([.55,.82,.9,.22])translate([0,21,105])rg_end_panel();
 color([.55,.82,.9,.22])translate([622,21,105])rg_end_panel();
 color([.6,.65,.68])translate([3,21,105])rg_corner_angle();
 color([.6,.65,.68])translate([622,21,105])scale([-1,1,1])rg_corner_angle();
 color([.6,.65,.68])translate([3,140,105])scale([1,-1,1])rg_corner_angle();
 color([.6,.65,.68])translate([622,140,105])scale([-1,-1,1])rg_corner_angle();
 for(x=[98,498])color([.65,.7,.73])translate([x,140,170])rg_fixed_hinge();
 for(x=[100,500]){
  color([.8,.82,.85])translate([x,148,179])rg_hinge_pin();
  color([.64,.68,.72])translate([x,21,150])rg_latch();
 }
 translate([0,150,181])rotate([-lid_angle,0,0])translate([0,-150,-181]){
  color([.58,.84,.92,.20])translate([0,18,170])rg_lid();
  for(x=[100,500])color([.62,.67,.70])translate([x,128,173])rg_lid_hinge();
 }
}

module rg_drive_bracket(){difference(){union(){translate([4,0,0])cube([24,10,3]);translate([4,7,0])cube([24,3,46]);
  for(x=[4,25])translate([x,0,0])rotate([0,90,0])linear_extrude(3)polygon([[0,0],[0,7],[-35,7]]);
  for(x=[0,28])translate([x,7,38])cube([4,3,8]); // cableearsoutsideentiremotorbody
 }
 for(x=[8,24])rg_hz([x,0,-1],48,6.2); // through edge reliefs for rearclevisM3heads
 for(x=[13,19])rg_hz([x,3.6,-1],5,2.4);
 for(x=[2,30])rg_hy([x,6,42],5,2);
}}
module rg04_drive_mount(show_motor=true){
 color([.65,.7,.74])translate([444,110,119])rg_drive_bracket();
 // Manufacturer drawing maximum20.2x41x9mm,not'13mm'voice-coildiameter.
 if(show_motor)rg_box([449.9,120,121.5],[20.2,9,41],[.18,.2,.22]);
}

if(rg_part=="assembly"){rg04_retainer_assembly();rg04_guard();rg04_drive_mount();}
else if(rg_part=="holder_left")rg_bar_holder("left");
else if(rg_part=="holder_right")rg_bar_holder("right");
else if(rg_part=="fixed_clamp")rg_fixed_clamp();
else if(rg_part=="tension_clamp")rg_tension_clamp();
else if(rg_part=="capstan_pin")rg_capstan_pin();
else if(rg_part=="shoe")rg_shoe();
else if(rg_part=="guard_lid")rg_lid();
else if(rg_part=="guard_post")rg_guard_post();
else if(rg_part=="fixed_hinge")rg_fixed_hinge();
else if(rg_part=="lid_hinge")rg_lid_hinge();
else if(rg_part=="hinge_pin")rg_hinge_pin();
else if(rg_part=="drive_bracket")rg_drive_bracket();
