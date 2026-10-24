// Syntax and graph-contract verification without pretending to be a browser.
import vm from 'node:vm';
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync} from 'node:fs';
import {dirname,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
const ROOT=dirname(fileURLToPath(import.meta.url));
const html=readFileSync(resolve(ROOT,'output/Dyletsky_Fusion_Audition.html'),'utf8');
const script=html.match(/<script>([\s\S]*)<\/script>/)[1];
const elements=new Map(),timers=[];let oscillators=0,closed=0;
const element=id=>{if(!elements.has(id))elements.set(id,{disabled:id==='#stop',value:0,textContent:'',rows:[],append(x){this.rows.push(x)}});return elements.get(id)};
const parameter=()=>({value:0,setValueAtTime(){},linearRampToValueAtTime(){},exponentialRampToValueAtTime(){}});
const node=()=>({gain:parameter(),frequency:parameter(),Q:parameter(),pan:parameter(),threshold:parameter(),ratio:parameter(),connect(){},start(){},stop(){}});
class AudioContext{
 constructor(){this.currentTime=0;this.sampleRate=48000}
 async resume(){}
 close(){closed++}
 createGain(){return node()}
 createDynamicsCompressor(){return node()}
 createStereoPanner(){return node()}
 createBiquadFilter(){return node()}
 createOscillator(){oscillators++;return node()}
}
const context=vm.createContext({document:{querySelector:element,createElement:()=>element(Symbol())},
 window:{AudioContext},AudioContext,console,
 setTimeout:(f,ms)=>{const id=timers.length;timers.push({f,ms,active:true});return id},
 clearTimeout:id=>{if(timers[id])timers[id].active=false},
 requestAnimationFrame:()=>1,cancelAnimationFrame:()=>{}});
new vm.Script(script,{filename:'Dyletsky_Fusion_Audition.html'}).runInContext(context);
assert.equal(context.fusionAuditionCheck.eventCount,68);
assert.equal(element('#targets').rows.length,4);
await element('#play').onclick();
assert.equal(element('#play').disabled,true);
for(const t of [...timers].sort((a,b)=>a.ms-b.ms))if(t.active)t.f();
assert(oscillators>68);
element('#stop').onclick();
assert.equal(element('#play').disabled,false);assert.equal(element('#stop').disabled,true);assert.equal(closed,1);
const result={status:'PASS',method:'Node syntax plus mocked DOM/Web Audio graph-contract check',
 eventCallbacks:68,oscillatorNodesCreated:oscillators,calibrationRows:4,playStopState:'passed',
 external_dependencies:0,actual_browser_audio_tested:false,
 limitation:'A browser executable was unavailable in this runtime. This check does not establish real-time browser scheduling, audible quality or physical operation.'};
writeFileSync(resolve(ROOT,'output/audition_verification.json'),JSON.stringify(result,null,2)+'\n');
console.log(JSON.stringify(result));
