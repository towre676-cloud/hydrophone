from pathlib import Path
import json, math, shutil
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor, Color, white
from reportlab.platypus import Paragraph, Table, TableStyle
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.graphics.shapes import Drawing, Rect, Line, Circle, String
from reportlab.graphics import renderPDF, renderSVG

ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'output'
OUT.mkdir(exist_ok=True)
FONT='/usr/share/fonts/truetype/dejavu'
pdfmetrics.registerFont(TTFont('D',FONT+'/DejaVuSans.ttf'))
pdfmetrics.registerFont(TTFont('DB',FONT+'/DejaVuSans-Bold.ttf'))
pdfmetrics.registerFontFamily('D',normal='D',bold='DB',italic='D',boldItalic='DB')
INK=HexColor('#173441'); TEAL=HexColor('#087e8b'); CLAY=HexColor('#b86037')
PALE=HexColor('#edf4f4'); GREY=HexColor('#51636b'); GOLD=HexColor('#a47b2c')
W,H=595.276,841.89; M=43; CW=W-2*M
BODY=ParagraphStyle('body',fontName='D',fontSize=9.2,leading=14,textColor=INK,spaceAfter=10)
SMALL=ParagraphStyle('small',parent=BODY,fontSize=7.8,leading=11.4)
CELL=ParagraphStyle('cell',parent=BODY,fontSize=8,leading=11.5,spaceAfter=0)
HEAD=ParagraphStyle('head',parent=BODY,fontName='DB',fontSize=12.2,leading=16,spaceAfter=10)
c=canvas.Canvas(str(OUT/'Fusion_Instrument_Design.pdf'),pagesize=(W,H))
c.setTitle('Fusion Instrument: clay, strings, hydrophone and Dyletsky - Engineering design 0.1')
c.setAuthor('Research design prepared for p loso')
page_no=0; y=0

def page(title,strap='ENGINEERING DESIGN 0.1 / 24 OCTOBER 2026'):
 global page_no,y
 if page_no: c.showPage()
 page_no+=1
 c.setFillColor(INK); c.rect(0,H-12,W,12,fill=1,stroke=0)
 c.setFont('DB',8); c.setFillColor(TEAL); c.drawString(M,H-40,strap)
 c.setFont('DB',22); c.setFillColor(INK); c.drawString(M,H-76,title)
 c.setStrokeColor(HexColor('#cedcde')); c.line(M,42,W-M,42)
 c.setFont('D',7); c.setFillColor(GREY)
 c.drawString(M,28,'FUSION / nominal design; no assembled hardware or measured material results')
 c.drawRightString(W-M,28,f'{page_no:02d}')
 y=H-100

def p(text,small=False):
 global y
 obj=Paragraph(text,SMALL if small else BODY)
 _,h=obj.wrap(CW,700)
 if y-h<56: raise ValueError(f'Page {page_no} overflows by {56-y+h:.1f} pt: '+text[:70])
 obj.drawOn(c,M,y-h); y-=h+(7 if small else 10)

def sub(text):
 global y
 q=Paragraph(text,HEAD); _,h=q.wrap(CW,50);q.drawOn(c,M,y-h);y-=h+10

def table(headers,rows,widths=None):
 global y
 data=[[Paragraph(str(z),CELL) for z in row] for row in [headers]+rows]
 t=Table(data,colWidths=widths or [CW/len(headers)]*len(headers),hAlign='LEFT')
 t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),PALE),('TEXTCOLOR',(0,0),(-1,0),INK),
  ('VALIGN',(0,0),(-1,-1),'TOP'),('BOTTOMPADDING',(0,0),(-1,-1),7),
  ('TOPPADDING',(0,0),(-1,-1),7),('LINEBELOW',(0,0),(-1,0),.8,TEAL),
  ('LINEBELOW',(0,1),(-1,-1),.25,HexColor('#d3dfe1'))]))
 _,h=t.wrap(CW,700)
 if y-h<56: raise ValueError(f'Page {page_no}: table overflow {h}')
 t.drawOn(c,M,y-h);y-=h+14

def fig(d,height=None):
 global y
 ht=height or d.height
 if y-ht<56: raise ValueError('figure overflow')
 renderPDF.draw(d,c,M,y-ht);y-=ht+12

def label(d,x,y,s,size=8,col=INK):
 d.add(String(x,y,s,fontName='D',fontSize=size,fillColor=col))

def plan():
 d=Drawing(CW,345);s=.78;ox=15;oy=57
 def pt(x,y):return ox+x*s,oy+y*s
 def rect(x,y,w,h,fc,sc=INK):
  a,b=pt(x,y);d.add(Rect(a,b,w*s,h*s,fillColor=fc,strokeColor=sc,strokeWidth=.6))
 rect(0,0,600,320,HexColor('#f2f5f6'))
 rect(374,154,172,112,HexColor('#cdeaf0'),TEAL)
 rect(380,160,160,100,HexColor('#d8f0f5'),TEAL)
 for x in [50,500]:rect(x,35,20,80,HexColor('#a5b2b8'))
 for yy in [54,66,78,90]:
  a,b=pt(60,yy);e,f=pt(510,yy);d.add(Line(a,b,e,f,strokeColor=GOLD,strokeWidth=1.15))
 rect(454,36,12,72,HexColor('#778d98'))
 rect(440,52,40,40,CLAY)
 
 for xx in [419,481]:
  for yy in [48,88]:rect(xx,yy,10,8,HexColor('#b9c6ce'))
 a,b=pt(460,102);e,f=pt(460,154);d.add(Line(a,b,e,f,strokeColor=INK,strokeWidth=2.2))
 a,b=pt(430,154);e,f=pt(490,154);d.add(Line(a,b,e,f,strokeColor=TEAL,strokeWidth=3))
 a,b=pt(500,215);d.add(Circle(a,b,12.5*s,fillColor=INK,strokeColor=INK))
 rect(440,5,40,23,HexColor('#d6ab55'))
 # Leaders sit in open areas; they do not imply a second load path.
 label(d,*pt(25,280),'DRY STRINGS + CLAY',11)
 label(d,*pt(25,261),'One intended shared bridge translation',8)
 label(d,*pt(384,286),'VENTED WATER CELL',9,TEAL)
 label(d,*pt(389,242),'1.28 L fill',8,TEAL)
 label(d,*pt(397,187),'hydrophone',8,TEAL)
 label(d,*pt(233,132),'400 mm speaking length',8,GOLD)
 a,b=pt(60,123);e,f=pt(460,123);d.add(Line(a,b,e,f,strokeColor=GOLD,strokeWidth=.7))
 for xx in [60,460]:
  a,b=pt(xx,118);e,f=pt(xx,128);d.add(Line(a,b,e,f,strokeColor=GOLD))
 label(d,*pt(23,193),'Bridge moves across strings (+Y)',8)
 a,b=pt(325,183);e,f=pt(456,96);d.add(Line(a,b,e,f,strokeColor=GREY,strokeWidth=.5))
 label(d,*pt(25,216),'Clay shear pad sits below the bridge',8,CLAY)
 a,b=pt(330,207);e,f=pt(445,80);d.add(Line(a,b,e,f,strokeColor=CLAY,strokeWidth=.5))
 label(d,*pt(26,21),'Nut / tuning anchors carry the string tension',8)
 # Envelope dimensions.
 a,b=pt(0,-21);e,f=pt(600,-21);d.add(Line(a,b,e,f,strokeColor=GREY))
 label(d,*pt(265,-35),'600 mm',8)
 for xx in [0,600]:
  a,b=pt(xx,-27);e,f=pt(xx,-15);d.add(Line(a,b,e,f,strokeColor=GREY))
 label(d,17,329,'TOP VIEW / millimetres / nominal positions',8,TEAL)
 label(d,17,10,'Rod detaches for clay writing; water never contacts clay or strings.',8,GREY)
 return d

def section():
 d=Drawing(CW,240)
 label(d,0,223,'BRIDGE SECTION / heights shown schematically; Z in mm',9,TEAL)
 # Schematic stacked module, deliberately labelled not scale.
 x=108;z0=28;scale=1.35
 def r(z,h,w,col):d.add(Rect(x-w/2,z0+z*scale,w,h*scale,fillColor=col,strokeColor=INK,strokeWidth=.6))
 r(0,12,164,HexColor('#263f4a'));r(12,63,52,HexColor('#a6b2b8'))
 r(75,3,90,HexColor('#a6b2b8'));r(78,8,68,CLAY);r(86,3,90,HexColor('#a6b2b8'))
 r(89,6,12,HexColor('#9baab1'));r(95,24,45,HexColor('#9baab1'));r(113,12,120,HexColor('#778d98'))
 for xx in [41,175]:d.add(Rect(xx,z0+55*scale,2,40*scale,fillColor=INK,strokeColor=INK))
 for zz,yy,txt,col in [(125,202,'String saddle Z=125',GOLD),(113,184,'Bridge Z=113..125',INK),(95,166,'Flexure tops Z=95',INK),
                    (86,148,'Upper plate Z=86..89',INK),(78,130,'Clay pad Z=78..86',CLAY),(75,112,'Fixed plate Z=75..78',INK)]:
  actual=z0+zz*scale;d.add(Line(198,actual,226,yy,strokeColor=col));label(d,232,yy-2,txt,8,col)
 label(d,232,74,'Leaf free length 40; thin axis is Y',8)
 label(d,232,56,'Rod centre Z=85; offset carrier',8)
 label(d,232,38,'Stop screws limit Y travel',8)
 label(d,0,7,'Four-leaf guide: measure parasitic rotation. Anchors carry axial string load.',8,GREY)
 return d

page('A physical fusion instrument')
p('<b>A clay-controlled musical measurement instrument.</b> Four dry strings share a transverse bridge whose motion shears a replaceable clay cartridge. A removable dry rod drives a diaphragm in a vented water cell. A hydrophone records that water-coupled response while a separate vibration reference and a slow force/displacement instrument reveal what the clay actually retains.')
fig(plan())
p('Dyletsky supplies spelled pitch targets, interval priorities and musical drive phrases. DynaComp predicts selected outputs of a calibrated mechanical model. Singularity chooses distinguishing experiments, PerfectJet checks whether a requested decision is supported, PerfectPower schedules admissible finite drive programs, and nonlinearhamiltonian checks the conservative symbolic reference. Each service has a precise interface; the acquisition and hardware adapters are new work.')
p('<b>Delivered status.</b> This packet supplies nominal geometry, an assembly layout, components, calibration protocol, data contracts and reproducible synthetic calculations. It is a preliminary engineering design, with an explicit path to a first physical experiment. It does not report an assembled object, verified material law, physical computing advantage or completed repository integration.',True)

page('Geometry and construction')
fig(section())
table(['Item','Nominal geometry / location'],[
 ['Base / envelope','600 × 320 × 12 plate; reserve total height 240. X is string direction; Y is bridge motion; Z is height.'],
 ['Strings','Nut X=60; bridge X=460; afterlength anchor X=510. Y=54,66,78,90; saddle Z=125. Speaking length 400; afterlength 50.'],
 ['Clay sandwich','30 × 30 × 8 clay between 40 × 40 × 3 plates. Centre X=460,Y=72. Lower plate Z=75..78; clay 78..86; upper plate 86..89.'],
 ['Carrier / flexures','Four leaves 40 × 10 × 0.30 spring steel, free Z=55..95, thin direction Y; centres X=424/486,Y=52/92. Bridge crossbar 12 × 72 × 12 at X=454..466,Y=36..108,Z=113..125.'],
 ['Water cell','Internal X=380..540,Y=160..260,Z=35..135. Six mm walls; fill to Z=115. External extent 172 × 112 × 106. Vented removable lid.'],
 ['Wet interface','Diaphragm centre X=460,Z=85; external plane Y=154. Forty mm clear aperture. Dry rod diameter 3, centre Z=85. Hydrophone centre X=500,Y=215,Z=80.']
 ],[110,CW-110])
p('Base drilling, bracket holes and cable routes must follow purchased component drawings. The OpenSCAD assembly checks nominal fit and load-path arrangement; omitted fasteners, saddle caps, seals and electronics are not fabrication details inferred from the render. Use captive grooved saddles or light retaining caps for transverse string coupling and characterize their slip and damping.',True)

page('Mechanics that make it work')
p('<b>Separate axial load, clay writing and acoustic reading.</b> Independent nut and end blocks carry string tension into the frame. Four leaf flexures in two Y-separated pairs resist bridge pitch and guide it laterally, so the clay does not carry the full axial string load. The upper clay plate moves with the carrier; its lower plate is fixed. The dry rod connects at Z=85 through an offset bracket below the Z=125 string saddle. The intended translation changes clay shear; actual motion can include parasitic rotation because string and rod forces act at different heights. Measure both sides of the carrier, include pitch as a model coordinate when needed, and reject records with uncontrolled normal loading or saddle motion. Pure translation and constant string height are design targets, not established constraints.')
p('Use a non-drying modelling clay as one candidate specimen, weighed and batch-labelled. Compare it with a rigid spacer and a characterized elastomer. Non-drying clay is not automatically a calibrated or nonvolatile memory device: creep, oil migration, wall slip and contact evolution can dominate. A replaceable cartridge permits identical fixtures and independently prepared specimens. Add a removable side window or fiducials to observe shape and plate slip.')
table(['Operation','Initial design setting; to be validated'],[
 ['Slow writing','Manual micrometer or screw stage, inline 20 N nominal load-cell range, independent displacement readout. Begin at ±0.05 mm; extend toward ±0.5 mm only after measured checks. The latter gives nominal clay shear strain 0.0625.'],
 ['Uncoupled write','Release the indexed dry rod before large clay writing strokes. Record force/displacement/history. Reattach without detectable preload; record the new equilibrium and test reconnection repeatability.'],
 ['Acoustic read','Begin below 10 micrometres bridge dynamic amplitude about its measured equilibrium; use low-level sweeps and ringdown. Hardware travel stops at ±0.6 mm are protection, not an allowed dynamic excursion.'],
 ['Diaphragm coupons','Sixty mm disc / forty mm clear aperture; compare 0.10 and 0.25 mm spring-stainless sheet. Clamp ring OD60, ID40, thickness5; eight M3 clearance holes on 50 mm bolt circle. Gasket and wet sealing require leak and creep checks.']
 ],[100,CW-100])
p('A useful screening estimate is k = 16πD/a² with D = Et³/[12(1−ν²)]. At E=200 GPa, ν=0.3 and a=20 mm, the ideal dry central-point stiffness is about 2.30 kN/m for 0.10 mm sheet and 35.96 kN/m for 0.25 mm. These are not assured wet stiffnesses. At 30 mm centre depth, hydrostatic loading alone gives an idealized 40 micrometre central deflection for the thin coupon. Measure tangent stiffness around the actual wet equilibrium, including water, clamp and rod loading.',True)

page('Sensing and electrical interfaces')
p('Use one multichannel audio interface for all phase-sensitive acoustic channels. A Behringer UMC1820 is a candidate with eight analogue preamps, 24-bit/96 kHz conversion and phantom-power support [H2]. Begin at 48 kHz with fixed gain and disabled automatic processing. An Aquarian H2dX is an audio-band candidate; its 25 × 46 mm body fits the cell, and its XLR output needs phantom power [H1]. The manufacturer states that response depends on the preamp, power and cable. Calibrate the assembled chain; its advertised bandwidth does not calibrate this small reflective tank.')
table(['Audio input','Signal / purpose'],[
 ['1','Hydrophone in water. Phantom power only as required by the matched hardware.'],
 ['2','Optional air microphone outside the cell: audible result and airborne crosstalk.'],
 ['3','Optional second pressure point / reference microphone; mark unused if absent.'],
 ['4','Optional diagnostic; preserve full simultaneous acquisition initially.'],
 ['5','Buffered bridge vibration reference. A piezo channel gives AC strain/voltage, not calibrated DC displacement.'],
 ['6','Buffered base/reference vibration channel to expose frame transmission.'],
 ['7','Electrical command loopback through a correctly rated line-level attenuator.'],
 ['8','Measured drive proxy or synchronization marker, appropriately conditioned.']
 ],[85,CW-85])
p('Acquire slow load-cell force, independent displacement and water/room temperature on a separate DC-capable logger. Audio inputs cannot measure static clay displacement or long relaxation reliably. Record a common synchronization event in both systems and estimate offset and drift; do not infer synchronous clocks merely because both devices use USB. The minimum design-resolution target is 0.01 N force and 0.01 mm slow displacement, with uncertainty measured across the used range. These are acceptance targets, not promised sensor performance.')
p('Drive a dry-mounted exciter through a current-limited low-voltage amplifier. The Dayton DAEX25 family is a candidate; the installed panel determines its response [H3]. An audio interface line output must feed an amplifier input, never a voice coil directly. Keep amplifier outputs, sensor conditioning and phantom-powered microphone inputs distinct. Nylon strings require optical or piezo pickup methods; magnetic guitar pickups do not sense nonmagnetic nylon. Keep electrical connectors above the water tray and use the manufacturer-supplied power equipment.',True)
p('A concrete slow-logger candidate is the Phidgets DAQ1500_0 bridge interface with a compatible USB VINT hub. Its stated maximum 50 Hz rate suits slow holds, not audio. Choose and calibrate the force transducer separately: a cheap 5 kg cell with roughly 0.025 N repeatability cannot be presumed to meet the 0.01 N target. Never attach a high-force contact indicator to the bridge during free acoustic reads without measuring its added loading.',True)

page('The shared physical model')
p('Let q contain measured generalized displacements, v their velocities, y=aᵀq the clay deformation coordinate and z a relaxing internal coordinate. A deliberately modest reference law is <b>Mq̈ + Cv + K₀q + a[k∞y + kₘ(y−z)] = Bu</b>, with ż=(y−z)/τ. Positive mass and stiffness and positive-semidefinite damping make this standard-linear-solid model a useful passive baseline. Plastic shape retention requires an additional measured law; it is not supplied by renaming z as memory.')
p('For fixed coefficients, <b>E = ½vᵀMv + ½qᵀK₀q + ½k∞y² + ½kₘ(y−z)²</b> obeys <b>Ė = uBᵀv − vᵀCv − (kₘ/τ)(y−z)²</b>. This identity supplies a sign and energy-accounting check. If the write process changes stiffness, add P<sub>write</sub> = ½k̇∞y² + ½k̇ₘ(y−z)², with corresponding terms for every other changed coefficient. Writing and retuning do work. A decreasing-energy proof for frozen coefficients cannot certify a live adaptive controller.')
sub('Two failures that the hardware must expose')
p('<b>Acoustic blindness to a memory state.</b> The incremental clay stiffness is k*(ω)=k∞+kₘ iωτ/(1+iωτ). It contains τ and the stiffnesses but not the initial z. Two preparation histories with the same coefficients can have different slow relaxation offsets and the same small-signal frequency response. An acoustic sweep alone cannot identify those histories. A successful persistent acoustic memory write must instead change geometry, contact, stiffness, damping or coupling in a repeatable way.')
p('<b>Pressure-only ambiguity.</b> If H<sub>obs</sub>(ω)=G<sub>water</sub>(ω)H<sub>mech</sub>(ω) and G<sub>water</sub> is unrestricted and unknown, any nonzero candidate H̃<sub>mech</sub> can be explained by G̃<sub>water</sub>=H<sub>obs</sub>/H̃<sub>mech</sub>. Unique material inference fails. An independent vibration reference, a fixed hydrophone mount and disconnected/empty/filled baselines are part of the instrument, not optional statistical refinements.')
p('The Hamiltonian repository can check a chosen scalar modal submodel H(q,p)=p²/(2m)+kq²/2+αq⁴/4 in its supported single canonical pair q,p. Clay dissipation, creep and fluid losses remain explicit added terms. No classical-to-quantum identity implies quantum behaviour, an arbitrary finite observable closure, or a hardware speedup for this object.',True)

page('Dyletsky becomes a physical score')
p('The recovered dyle2/dyle3 material identifies a weighted pitch-constraint system and a 17-spelling extension [L3,L4]. Its useful engineering role is to request labelled tuning targets and controlled phrases. In a fixed gauge, solve <b>x* = argmin [(Jx−b)ᵀW(Jx−b)+λxᵀx]</b>. With positive-semidefinite W and suitable gauge or λ&gt;0, the normal equation is (JᵀWJ+λI)x*=JᵀWb. Convert a cent offset to frequency by <b>f=f<sub>ET</sub>2<sup>x*/1200</sup></b>. Preserve spelling labels; a sound frequency alone does not distinguish G-sharp from A-flat.')
p('The first physical version has four simultaneous string voices and manual tuning pegs. It does not independently realize all seventeen software pitches. Full rapid musical retuning would need a later measured motorized mechanism. Electronic oscillator changes do not by themselves retune the physical strings. The four-note example below is a new simple-ratio design fixture, not a replay of an original Dyletsky composition.')
ar=json.loads((OUT/'design_arithmetic.json').read_text())
table(['String','Target Hz','Offset cents','Ideal tension N'],[
 [r['spelling'],f"{r['ratio_fixture_Hz']:.3f}",f"{r['offset_cents']:+.3f}",f"{r['ideal_nylon_tension_N']:.3f}"] for r in ar['notes']], [100,140,135,CW-375])
p('This fixture anchors C4 to 261.6256 Hz and uses ratios 9/8, 5/4 and 3/2 for D4, E4 and G4. The ideal rigid-end string relation is f=(1/2L)√(T/μ), or T=μ(2Lf)². The table assumes L=0.400 m, diameter 0.50 mm and nylon density 1150 kg/m³. Measure linear density from a long sample and use observed pitch to tune; compliant supports, stretch and endpoint effects make the calculated tensions estimates.')
p('For a controlled experiment, freeze a tuning and phrase, prepare a clay history, then record the same input and all outputs. Compare identical phrases under distinct clay preparations, and identical preparations under distinct phrases. This crossed design separates what the score does from what the material remembers. Record every manual retuning event as a state-changing action. A loss-sensitive response can be heard, but a musical impression is not a calibrated material measurement.')
p('The software score should carry pitch spelling, octave, requested hertz/cents, duration, channel, drive amplitude, target tolerance, reset requirements and a recorded input waveform. Musical fields become operator inputs only through a measured mapping. A Hessian of musical preference is not automatically a mechanical stiffness matrix.',True)

page('How the repositories coordinate')
table(['Service','Existing machinery and proposed instrument job'],[
 ['DynaComp','Compile a calibrated model for a chosen output; replay EA=GE, EB=H, DE=C or a stated residual bound. Account separately for omitted physical modes and model discrepancy.'],
 ['Singularity','Choose finite distinguishing sensor/probe panels. For declared box errors, require candidate separation greater than twice the error. Report ambiguous histories.'],
 ['PerfectJet','Check target recoverability and bounded decisions in its supported finite linear chart; keep uncertain choices unresolved. Track the declared history/protocol state.'],
 ['PerfectPower','Count, rank and optimize chronological drive words under one exact integer cost budget: 0-256, at most 16 actions, costs 1-16. Additional limits need an explicit guard-state adapter.'],
 ['nonlinearhamiltonian','Verify supported conservative symbolic identities and observable derivatives. Keep dissipation and history outside that symbolic claim.'],
 ['Dyletsky','Provide labelled pitch targets, interval priorities and reproducible excitation phrases. Four physical voices first; seventeen labels retained in the data model.']
 ],[115,CW-115])
p('<b>The common contract is a measured run.</b> Store raw multichannel WAV plus slow CSV, sensor positions, units, calibration factors and uncertainty, specimen/history ID, gain settings, measured drive, clock alignment, temperature, clay mass, missing-sample/clipping flags and exact source references. Features retain the raw run IDs. A proposed model contract then carries A/B/C, sample timing, validity domain, state/input boxes and separate calibration, discretization, reduction and physical-discrepancy budgets.')
p('Current source code supports the mathematical services above, but no inspected repo supplies this completed acquisition or actuator adapter. The packet includes explicit interface definitions and an offline evidence gate, not claimed live integrations. The gate rejects synthetic data as physical evidence. A field-complete record still needs scientific validation; metadata presence alone cannot certify accuracy.')
p('Version details matter. The audit read explicit main branches on 24 October 2026 and retained Git blob hashes; these identify file contents, not repository commit snapshots. PerfectPower has a different default branch. Integration should record a full tested commit for every dependency and use its documented argument types and size limits. An exact rational fit is exact arithmetic on a nominal model, not an exact law of clay. PerfectPower words consume the specified budget exactly; an upper-budget menu needs a sum over exact budgets or a validated padding encoding.',True)

page('The first physical experiment')
p('<b>Establish a repeatable instrument before claiming memory.</b> With the clay removed or replaced by a rigid reference, record electronics loopback, bridge/base vibration and hydrophone noise. Characterize the dry bridge with the rod disconnected, then with the diaphragm connected and the cell empty, then at fixed water depth. Measure dry and wet static tangent stiffness, settling and rod reconnection variability. If diaphragm or frame loading masks cartridge differences, change the membrane or coupling before adding software complexity.')
p('<b>Test clay histories under controlled present conditions.</b> Prepare independent cartridges with a repeatable low-amplitude conditioning cycle. Compare a specified hold, a loading/unloading loop and an untouched reference, each recorded with measured force, displacement, duration and relaxation time. Begin at 0.05 mm write travel with the rod released. Increase only within the measured elastic/controlled operating region of the fixture. Reconnect the indexed rod and record equilibrium before a low-level sweep. Use slow steps and holds to fit relaxation time; the hydrophone does not supply the DC record.')
p('<b>Separate signature, retention and useful computation.</b> First ask whether preparation changes the response beyond remounting, temperature and measurement uncertainty. Then ask whether that difference survives predefined waits, for example 1, 10 and 60 minutes, without continued writing power. Compare different histories at matched present geometry and include repeated detach/reattach controls. Only after reliable physical discrimination should the device attempt a task such as classifying an incoming vibration pattern or filtering a known waveform.')
table(['Gate','Predeclared result needed'],[
 ['Read does not rewrite','Repeat at least ten low-level reads. Feature drift from reading must remain inside its independently estimated repeatability interval.'],
 ['History is observable','Use full sensors initially. A finite candidate pair is accepted as separated only when declared uncertainty intervals do not overlap; otherwise retain ambiguity.'],
 ['Transfer is stable','Log water depth/temperature and bridge motion. Reject clipped, loose, slipping, leaking or unsynchronized records.'],
 ['Generalization','Freeze preparation, features and thresholds on development cartridges; evaluate at least six additional cartridges on a later day with the declared controls. This is a pilot, not a universal reliability estimate.'],
 ['Computational value','Compare with direct low-order rheology and ordinary digital filters on the same task, error, latency and setup-inclusive energy/cost. A four-string prototype may need no model reduction.']
 ],[110,CW-110])
p('No guarantee of a tenfold gain, uniqueness, nonvolatile retention or novelty is implied. The immediate scientific payoff is a well-instrumented test of whether the proposed physical memory is visible, persistent and usable. A negative result still tells us which coupling or measurement needs redesign.',True)

page('Parts and spending envelope')
table(['Part / quantity','Specification and cost status'],[
 ['Hydrophone / 1','Aquarian H2dX with appropriate cable and phantom-powered preamp [H1]. Manufacturer page displayed US $229 on 24 October 2026; verify selected connector/cable total.'],
 ['Audio interface / 1','Eight analogue input candidate: Behringer UMC1820 [H2]. Planning allowance $200-350; not a vendor quote. Existing suitable equipment can be reused.'],
 ['Exciter / amplifier','Dry audio exciter, matched current-limited amplifier and proper input/feedback conditioning [H3]. Allow $80-200, subject to parts selection.'],
 ['Mechanical assembly','600×320 base, anchor blocks and pegs, carrier/flexure clamps, cartridge, cell, gaskets, rod disconnect, coupon sheets and spill tray. Allow $450-1,200; custom machining/lab labour may exceed this.'],
 ['Slow sensing / stage','20 N nominal force range, bridge conditioning, DC logger, independent displacement instrument, manual micrometer and temperature sensors. Allow $350-900; accuracy/clock requirements drive selection.'],
 ['AC sensing / consumables','Buffered piezo/reference pickups or optical vibration reference, cables, clay, elastomer/rigid controls, nylon strings and spare seals. Allow $150-400.']
 ],[115,CW-115])
p('<b>Planning total: approximately $1,460-3,280</b> before tax, shipping, labour, computer and specialist calibration. Only the displayed $229 hydrophone price is source-verified here; the remaining bands are engineering allowances, not shopping claims. Laboratory force/vibration metrology can raise the total substantially. No order has been placed. Buy or fabricate the single cartridge/flexure/diaphragm coupon fixture first; verify stiffness and readout before committing to the full enclosure.')
p('Cut-list starting point: one 600×320×12 base, two 40×40×3 cartridge plates, four 40×10×0.30 leaf coupons with additional clamp engagement outside the free length, one 12×72×12 bridge and a stiff offset carrier. The cell has a 172×112×6 bottom; two 172×100×6 long walls and two 100×100×6 inset end walls give the declared 160×100 interior. Include solvent-bond/fastener design consistent with the chosen plastic; no unverified pressure rating is asserted.')
p('Place a vent and hydrophone cable support in a splash lid above the 80 mm water depth; do not seal the cell into a pressure vessel. Inspect membrane-edge sealing and hydrophone clearance. The acoustic wavelength in water is several metres around these notes, larger than the cell: it is a coupled reflective near-field experiment. It is not an anechoic or far-field acoustic calibration system.',True)

page('A testable numerical example')
model=json.loads((ROOT/'model/model_results.json').read_text())
p('A reproducible two-mode standard-linear-solid example was run to test the measurement design. Its masses, stiffnesses, damping, forcing and gains are illustrative assumptions. The synthetic acoustic sweep is 65-240 Hz, and the slow experiment is 0.015-2 Hz; these are not predicted resonances or operating performance of the four-string geometry. All model files, raw synthetic outputs and assumptions are included.')
c.drawImage(str(ROOT/'model/model_diagnostics.png'),M,y-350,width=CW,height=350,mask='auto');y-=365
table(['Diagnostic','Illustrative result'],[
 ['Sensitivity condition','Audio only: 1.46×10⁸; slow plus audio: 207.9. Separate unknown constant slow gain: 208.7. Analytic derivatives and SVD used.'],
 ['Parameter fitting','Thirty trials, declared 1% complex noise: relaxation-time relative RMSE 1.47%, conditional on the correct model and shared constant gain.'],
 ['Energy replay','Free energy-balance residual below 2×10⁻¹⁸ J; separate state-space/transfer calculations agree within 5.84×10⁻¹⁶ relative error at six frequencies.']
 ],[125,CW-125])
p('These calculations support adding the slow channel; they do not establish a real sensor sensitivity, clay retention time or physical speedup. Arbitrary frequency-dependent water or sensor error would defeat the assumed identification problem. The delivered model notes state that limitation explicitly.',True)

page('Source record and handoff')
p('<b>Recovered sources.</b> [L1] Claycompute.txt, current Library read, especially lines 409-508: deformable material as a slow control layer for an acoustic/electromechanical substrate. [L2] claycompute_exposition.md.pdf, current extracted-text read: later cavity/piezo architecture. Its high-frequency and economic claims were treated as proposals, not established specifications for this design. [L3] dyle2.txt, lines 1-230 and 490-679: weighted constraint tuning and seventeen spelled pitch classes. [L4] dyle3.txt, lines 1-170: the pitch-field framework; this read does not validate every historical or empirical claim in that long draft.')
p('The exact original hydrophone-and-string apparatus was not recovered in the selected source material. The mechanical combination in this packet is therefore a new design, not a purported restoration of its historical dimensions. Earlier conversation fragments contain incompatible scales and unsupported sensing assertions; those numbers were not used as engineering specifications.')
for title,url in [
 ('L1 / clay source','https://chatgpt.com/library?file_id=libfile_313310e9f8508191841b84e39fe135fa&amp;account_id=personal'),
 ('L2 / clay exposition','https://chatgpt.com/library?file_id=libfile_04d86703cf5c819182cea2a372a0f9ae&amp;account_id=personal'),
 ('L3 / Dyletsky source','https://chatgpt.com/library?file_id=libfile_2f22625157bc819192ee648aac5dc0fb&amp;account_id=personal'),
 ('L4 / Dyletsky continuation','https://chatgpt.com/library?file_id=libfile_5d6733f555908191a81bd8de72503bf1&amp;account_id=personal'),
 ('H1 / Aquarian manual and product','https://www.aquarianaudio.com/AqAudDocs/H2dX_manual.pdf'),
 ('H2 / Behringer interface','https://www.behringer.com/en/products/0805-AAN'),
 ('H3 / Dayton exciter family','https://www.daytonaudio.com/product/1087/daex25-sound-exciter-pair'),
 ('H4 / Phidgets slow bridge logger','https://www.phidgets.com/?prodid=957')]:
 p(f'<link href="{url}" color="#087e8b">{title}</link>',True)
p('Current repository main sources were inspected for DynaComp, singularity, PerfectJet, perfectpower and nonlinearhamiltonian. Full paths, content hashes, current API limits and caveats are in evidence/repository_audit.txt. These source inspections were read-only; no repository tests, commits or physical adapters were falsely reported as completed.')
p('<b>Handoff boundary.</b> Begin with the coupon assembly and full simultaneous sensing. The electronics/acquisition owner builds synchronized raw logging and calibrated drive/reference channels. The mechanical owner measures dry/wet stiffness and cartridge repeatability. The repository owners consume the same measured run contract and publish independent replay outputs. The existing Fusion theorems, adversary and literature work can evaluate this concrete object without needing to invent its coupling path.')
c.save()
renderSVG.drawToFile(plan(),str(OUT/'Fusion_Instrument_Top_View.svg'))
print(json.dumps({'pdf':str(OUT/'Fusion_Instrument_Design.pdf'),'pages':page_no,'svg':str(OUT/'Fusion_Instrument_Top_View.svg')}))
