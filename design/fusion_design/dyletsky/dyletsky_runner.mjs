import * as V6 from './v6_core.mjs';
import * as G from './gen2_core.mjs';
import {mkdirSync,writeFileSync} from 'node:fs';
import {dirname,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';

const ROOT=dirname(fileURLToPath(import.meta.url));
const norm=x=>Math.hypot(...x);
function conventionalRMS(J,b,w,x){return Math.sqrt(J.reduce((s,r,k)=>s+w[k]*(r.reduce((a,v,i)=>a+v*x[i],0)-b[k])**2,0)/w.reduce((a,b)=>a+b,0));}
function residual(J,b,w,x,lambda=.008){
 const n=x.length;return norm(Array.from({length:n},(_,i)=>J.reduce((s,r,k)=>s+w[k]*r[i]*(r.reduce((a,v,j)=>a+v*x[j],0)-b[k]),0)+lambda*x[i]));
}
export function strictV6(strategy){
 if(!Object.hasOwn(V6.STRAT_ALGEBRA,strategy))throw Error('Unknown v6 strategy: '+strategy);
 const J=V6.buildJ17(),s=V6.computeSpelled(strategy,J),w=J.labels.map(l=>V6.algebraicWeight(strategy,l)),b=J.labels.map(V6.spelledTarget);
 return {...s,legacy_wRMS:s.wRMS,conventional_weighted_RMS:conventionalRMS(J.rows,b,w,s.xf17),
  normal_equation_residual:residual(J.rows.map(r=>r.slice(1)),b,w,s.xf17.slice(1)),
  engine_id:'dyletsky-v6-37',basis:V6.SP17,projection:'xf17 by spelling; xf12 is legacy enharmonic average',
  ET_label_meaning:'uniform source weights, not zero-offset equal temperament'};
}
export function gen2Calibration(strategy='hex_nat'){
 if(!G.SK.includes(strategy))throw Error('Unknown Gen2 strategy');
 const sys=G.buildSpelledSys(),w=G.w36toSpelled(G.pureW36(strategy)),s=G.solve(sys.J,sys.b,w);
 const bySpelling=Object.fromEntries(G.CHAIN.map((n,i)=>[n.sp,i===G.CG?0:s.xs[G.ci2fi(i)]]));
 return {engine_id:'dyletsky-gen2-43',strategy,basis:G.CHAIN.map(n=>n.sp),offsets_by_spelling:bySpelling,
  offsets_free:s.xs,weights:w,normal_equation_residual:residual(sys.J,sys.b,w,s.xs),weighted_RMS:s.wRMS};
}

export function generateScore({seed=20261024,ticks=64,tempo=52,mode='G Mixolydian'}={}){
 if(!Number.isInteger(ticks)||ticks<1||ticks>4096)throw Error('ticks must be 1..4096');
 if(!Number.isFinite(tempo)||tempo<36||tempo>88)throw Error('tempo must be 36..88');
 if(!Object.hasOwn(G.MODES,mode))throw Error('Unknown mode');
 G.setSeed(seed);
 const sys=G.buildSpelledSys(),d2=G.buildGeoMat(sys.J,sys.b,sys),halfBeat=60/(tempo*2),md=G.MODES[mode];
 let phase='jubilate',defect=.35,gamma=G.SK.map((_,i)=>i===0?.79:.03);
 let voices=G.VCFG.map((v,i)=>{
  const pc=md[i%md.length],found=G.CHAIN.findIndex(n=>n.midi===pc&&n.sp.length===1),si=found>=0?found:G.CG;
  return {...v,si,pc:G.CHAIN[si].midi,sp:G.CHAIN[si].sp,oct:Math.round((v.octRange[0]+v.octRange[1])/2),cents:0,dur:4,rem:4};
 });
 let memory=voices.map(()=>Array(G.ML).fill(-1)),phaseMemory=voices.map(()=>[]),previousHz=voices.map(()=>0),previousE=0;
 const events=[],trace=[];
 for(let tick=0;tick<ticks;tick++){
  gamma=G.flowG(gamma,phase,defect,null,d2);
  const w=G.w36toSpelled(G.mixW(gamma)),sol=G.solve(sys.J,sys.b,w),blocks=G.blockSolve(sys.J,sys.b,w);
  const field=G.normE_sp(sol.xs,sol.H);defect=G.stepD(defect,phase);
  gamma=G.residualNominate(sol.xs,blocks,gamma);
  for(let vi=0;vi<voices.length;vi++){
   voices[vi]={...voices[vi],rem:voices[vi].rem-1};if(voices[vi].rem>0)continue;
   const local=blocks[voices[vi].vtype]||sol.xs;
   voices=G.mhStep(vi,voices,local,sol.xs,sol.H,sol.Hi,field.norm,field.raw,memory[vi],phaseMemory[vi],md,phase);
   const v=voices[vi],dur=G.eDur(v.si,field.norm,v.vtype,phase),hz=G.pcHz(v.pc,v.oct,v.cents);
   memory[vi]=G.updMem(memory[vi],v.si);phaseMemory[vi]=[v.si,...phaseMemory[vi].slice(0,23)];
   voices[vi]={...v,dur,rem:dur};
   events.push({event_id:`g2-${events.length}`,start_s:tick*halfBeat,duration_s:halfBeat*dur*.91,
    voice:vi,voice_name:v.name,voice_type:v.vtype,spelling:G.CHAIN[v.si].sp,octave:v.oct,pitch_class:v.pc,
    offset_cents:v.cents,target_Hz:hz,previous_Hz:previousHz[vi]||hz,phrase:phase,
    engine_id:'dyletsky-gen2-43',source_amplitude:v.amp,source_pan:v.pan,
    normalized_energy:field.norm[v.si],energy_sigma:field.sigma,inverse_trace:sol.trHi,
    local_memory:memory[vi].slice(),phrase_memory_length:phaseMemory[vi].length});
   previousHz[vi]=hz;
  }
  const energy=G.jointE_midi?G.jointE_midi(voices,sol.xs,sol.H):null;
  trace.push({tick,time_s:tick*halfBeat,phrase:phase,defect,style_weights:gamma.slice(),weighted_RMS:sol.wRMS,
    normal_equation_residual:residual(sys.J,sys.b,w,sol.xs),normalized_pitch_energy:field.norm,
    source_energy:energy,source_energy_units:'musical heuristic; not joules'});
  if((tick+1)%8===0){phase=G.nxtPh(phase);phaseMemory=phaseMemory.map(m=>m.slice(0,12));}
 }
 const calibration=gen2Calibration();
 return {schema:'fusion.score/1',data_origin:'software_generated_score',engine_id:'dyletsky-gen2-43',seed,ticks,tempo,
  mode,basis:G.CHAIN.map(n=>n.sp),reference_C4_Hz:261.626,
  scheduler_scope:'New deterministic headless adaptation of recovered Gen2 rules. Fixed mode; source phrase transitions, style flow, register solves, note selection, local and phase memory retained. No audio-side random draws, room, drone or percussion generated.',
  musical_energy_is_physical_energy:false,
  calibration_targets:['C','D','E','G'].map(sp=>({spelling:sp,octave:4,pitch_class:G.CHAIN.find(n=>n.sp===sp).midi,
    offset_cents:calibration.offsets_by_spelling[sp],target_Hz:G.pcHz(G.CHAIN.find(n=>n.sp===sp).midi,4,calibration.offsets_by_spelling[sp]),
    engine_id:calibration.engine_id,strategy:calibration.strategy,manual_tuning_required:true})),events,trace};
}
export function compileInstrumentPlan(score){
 if(score.schema!=='fusion.score/1'||!Array.isArray(score.events))throw Error('fusion.score/1 events required');
 for(const e of score.events){
  if(!G.CHAIN.some(n=>n.sp===e.spelling&&n.midi===e.pitch_class))throw Error('Spelling/pitch class mismatch');
  if(!Number.isFinite(e.target_Hz)||e.target_Hz<=0||!Number.isFinite(e.duration_s)||e.duration_s<=0)throw Error('Invalid tone');
 }
 return {schema:'fusion.instrument-plan/1',data_origin:'software_command_plan',hardware_execution_enabled:false,
   mode:'common_exciter_input',reason:'Physical gain/force/travel calibration and hardware driver are absent.',
   physical_string_voices:4,common_input_channels:1,software_score_voices:8,
   command_units:'normalized digital amplitude; not newtons or pressure',
   calibration_targets:score.calibration_targets,
   events:score.events.map(e=>({...e,output_channel:0,mixing:'polyphonic sum into common exciter; does not independently actuate strings',requires_calibrated_amplitude:true})),
   source_spelling_preserved:true,
   discarded_hardware_assumptions:['No automatic string retuning','No seventeen independently tuned resonators','No assumed force from DAC level']};
}
export function writeDemo(output=resolve(ROOT,'output')){
 mkdirSync(output,{recursive:true});const score=generateScore();
 const audit={v6:Object.fromEntries(Object.keys(V6.STRAT_ALGEBRA).map(s=>[s,strictV6(s)])),
  gen2:Object.fromEntries(G.SK.map(s=>[s,gen2Calibration(s)])),
  matrices:{v6:V6.buildJ17(),gen2:G.buildSpelledSys()},
  warnings:['Two different interval systems; not interchangeable versions of one matrix.',
   'v6 ET label is uniform weights, not zero-cent tuning.',
   'v6 legacy wRMS squares weights; conventional weighted RMS also exported.',
   'Gen2 note proposal is a source heuristic; no stationary-distribution or sampling-optimality theorem asserted.',
   'Gen2 musical energy and style flow do not specify mechanical energy or material evolution.',
   'Legacy v6 inverse mixture/rounded 12PC spectral flow retained in archive, not used for measurement control.']};
 writeFileSync(resolve(output,'engine_audit.json'),JSON.stringify(audit,null,2)+'\n');
 writeFileSync(resolve(output,'instrument_score.json'),JSON.stringify(score,null,2)+'\n');
 writeFileSync(resolve(output,'instrument_plan.json'),JSON.stringify(compileInstrumentPlan(score),null,2)+'\n');
 console.log(JSON.stringify({events:score.events.length,phrases:[...new Set(score.events.map(e=>e.phrase))],
  max_normal_residual:Math.max(...score.trace.map(t=>t.normal_equation_residual)),calibration_targets:score.calibration_targets,output}));
}
if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url))writeDemo();
