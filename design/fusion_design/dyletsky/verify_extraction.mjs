import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync,writeFileSync} from 'node:fs';
import {dirname,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import * as V6 from './v6_core.mjs';
import * as G from './gen2_core.mjs';
import {strictV6,gen2Calibration,generateScore,compileInstrumentPlan} from './dyletsky_runner.mjs';
const ROOT=dirname(fileURLToPath(import.meta.url));
const plain=x=>JSON.parse(JSON.stringify(x));
function sourceReference(file,start,end,expose,seed=711){
 const text=readFileSync(resolve(ROOT,'archive',file),'utf8');
 let state=seed>>>0;const math=Object.create(Math);
 math.random=()=>{let t=state+=0x6D2B79F5;t=Math.imul(t^(t>>>15),t|1);t^=t+Math.imul(t^(t>>>7),t|61);return((t^(t>>>14))>>>0)/4294967296;};
 const ctx=vm.createContext({Math:math});
 vm.runInContext(text.slice(text.indexOf(start),text.indexOf(end))+`\nglobalThis.api={${expose.join(',')}};`,ctx);
 return ctx.api;
}
const vref=sourceReference('dyletsky_v6_fixed.jsx','const PC=','function setupChurch(',['buildJ17','computeSpelled','toHz']);
assert.deepEqual(plain(vref.buildJ17()),V6.buildJ17());
let maxV6=0;
for(const strategy of Object.keys(V6.STRAT_ALGEBRA)){
 const a=plain(vref.computeSpelled(strategy,vref.buildJ17())),b=V6.computeSpelled(strategy,V6.buildJ17());
 assert.deepEqual(a,b);maxV6=Math.max(maxV6,strictV6(strategy).normal_equation_residual);
 for(const [pair,d]of Object.entries(b.enhDiff)){const [s,f]=pair.split('/');assert.equal(d,b.xf17[V6.SP17.indexOf(s)]-b.xf17[V6.SP17.indexOf(f)]);}
}
assert(V6.computeSpelled('ET',V6.buildJ17()).xnorm>1);
assert.throws(()=>strictV6('invented-style'),/Unknown/);
assert.equal(V6.toHz(9,0,4),440);
assert(Math.abs(V6.toHz(0,0,4)-261.6255653005986)<1e-12);
assert(Math.abs(V6.toHz(0,1200,4)/V6.toHz(0,0,4)-2)<1e-14);
const gref=sourceReference('dyletsky_gen2_3.jsx','const CHAIN=','export default function DyletskyGen2',
 ['buildSpelledSys','pureW36','w36toSpelled','solve','normE_sp','mhStep','eDur','nxtPh','pcHz']);
assert.deepEqual(plain(gref.buildSpelledSys()),G.buildSpelledSys());
let maxGen2=0;
for(const strategy of G.SK){
 const sys=G.buildSpelledSys(),rSys=gref.buildSpelledSys();
 assert.deepEqual(plain(gref.pureW36(strategy)),G.pureW36(strategy));
 const a=plain(gref.solve(rSys.J,rSys.b,gref.w36toSpelled(gref.pureW36(strategy)))),b=G.solve(sys.J,sys.b,G.w36toSpelled(G.pureW36(strategy)));
 assert.deepEqual(a,b);maxGen2=Math.max(maxGen2,gen2Calibration(strategy).normal_equation_residual);
}
// Same source proposal/duration/phrase functions under one injected random stream.
G.setSeed(711);
const sys=G.buildSpelledSys(),sol=G.solve(sys.J,sys.b,G.w36toSpelled(G.pureW36('hex_nat'))),field=G.normE_sp(sol.xs,sol.H);
const voices=[{si:7,pc:7,sp:'G',oct:4,octRange:[3,5],vtype:'discant',cents:0},{si:6,pc:0,sp:'C',oct:4,octRange:[3,4],vtype:'cantus',cents:0}];
const args=[0,voices,sol.xs,sol.xs,sol.H,sol.Hi,field.norm,field.raw,[-1,-1],[7],G.MODES['G Mixolydian'],'jubilate'];
assert.deepEqual(plain(gref.mhStep(...plain(args))),G.mhStep(...plain(args)));
assert.equal(gref.eDur(7,field.norm,'discant','jubilate'),G.eDur(7,field.norm,'discant','jubilate'));
assert.equal(gref.nxtPh('jubilate'),G.nxtPh('jubilate'));
assert.equal(gref.pcHz(9,4,0),G.pcHz(9,4,0));
const s1=generateScore(),s2=generateScore();assert.deepEqual(s1,s2);
assert.notDeepEqual(s1.events,generateScore({seed:20261025}).events);
const plan=compileInstrumentPlan(s1);assert.equal(plan.hardware_execution_enabled,false);
assert.equal(plan.common_input_channels,1);assert.equal(plan.events.length,s1.events.length);
const corrupt=plain(s1);corrupt.events[0].pitch_class=(corrupt.events[0].pitch_class+1)%12;
assert.throws(()=>compileInstrumentPlan(corrupt),/Spelling/);
const bad=plain(s1);bad.events[0].target_Hz=NaN;assert.throws(()=>compileInstrumentPlan(bad),/Invalid/);
const result={status:'PASS',v6_strategies:13,gen2_strategies:8,
 source_parity:'Exact JS-number equality for full static outputs and selected seeded stochastic function calls',
 normal_equation_max_residual:{v6:maxV6,gen2:maxGen2},
 generated_events:s1.events.length,phrases:[...new Set(s1.events.map(e=>e.phrase))],
 seed_replay:'identical; changing seed changes score',
 physical_execution:'disabled; common-input plan does not retune or independently drive strings',
 invalid_inputs:'unknown strategy, spelling mismatch and nonfinite frequency rejected',
 scope:'Does not certify original GUI scheduling/audio timing, a sampler stationary law, physical dynamics or novelty'};
writeFileSync(resolve(ROOT,'output/extraction_verification.json'),JSON.stringify(result,null,2)+'\n');
console.log(JSON.stringify(result));
