import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
class Param{value=1;events=[];setValueAtTime(v,t){this.value=v;this.events.push(['set',v,t]);}linearRampToValueAtTime(v,t){this.value=v;this.events.push(['ramp',v,t]);}cancelScheduledValues(){}}
class Node{gain=new Param();connect(){}disconnect(){}}
class Source extends Node{constructor(ctx){super();this.ctx=ctx;ctx.sources.push(this);}start(at,offset){this.at=at;this.offset=offset;}stop(at){this.stopAt=at;}end(){if(!this.ended){this.ended=true;this.onended?.();}}}
class Context{currentTime=0;state='running';sources=[];createGain(){return new Node();}createBufferSource(){return new Source(this);}async resume(){}advance(dt){this.currentTime+=dt;for(const s of this.sources)if(s.stopAt<=this.currentTime)s.end();}}
class Base{constructor(options){this.options=options;this.fadeToken=0;this.playing=false;}setup(){this.context??=new Context();this.master??=new Node();}cancelPending(){this.fadeToken++;}async load(){return {duration:38.4};}clearEndTimer(){}fadeMedia(){}fadeVoices(){}select(t){this.track=t;}reportError(e){throw e;}pause(){this.cancelPending();this.playing=false;}stop(){this.cancelPending();this.playing=false;}async cue(){return 'legacy';}async play(){return 'legacy';}}
globalThis.__OrchestraTestBase=Base;
const source=readFileSync(new URL('./orchestral-soundtrack.js',import.meta.url),'utf8').replace(/^import .*;\n/,'const AdaptiveSoundtrack=globalThis.__OrchestraTestBase;\n');
const {OrchestralSoundtrack:Player,nextBar,orchestralCategory,orchestratedProgram,gameplayIntensity}=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
const track=id=>({id,stems:{bed:'b',theme:'t',motion:'m'},cycle_s:38.4,duration_s:76.8,loopScore:true});
test('three stems start and stop on one sample clock; end callback fires once',async()=>{
 const ends=[];const p=new Player({onEnd:()=>ends.push(1)});assert.equal(await p.play(track('field')),true);
 const nodes=p.context.sources;assert.equal(nodes.length,3);assert.equal(new Set(nodes.map(n=>n.at)).size,1);assert.equal(new Set(nodes.map(n=>n.stopAt)).size,1);
 p.context.advance(77);assert.deepEqual(ends,[1]);assert.equal(p.playbackState.remaining,0);
});
test('combat handoff uses next bar; pause stops retiring and incoming sources; resume keeps phase',async()=>{
 const p=new Player({});await p.play(track('field'));p.context.advance(5);
 const expected=nextBar(p.context.currentTime,p.orchestra.start);
 await p.play(track('combat'));assert.equal(p.orchestra.start,expected);
 p.context.advance(.2);p.pause();assert.ok(p.context.sources.every(n=>n.stopAt<=p.context.currentTime));
 const offset=p.orchestra.offset;assert.equal(await p.resume(),true);assert.ok(p.orchestra.nodes.every(n=>n.source.offset===offset%38.4));
});
test('stale download cannot start after pause',async()=>{
 const p=new Player({});let release;p.stemBuffers=()=>new Promise(r=>release=r);
 const pending=p.play(track('slow'));await Promise.resolve();p.pause();release([]);assert.equal(await pending,null);assert.equal(p.context.sources.length,0);
});
test('intensity changes gains without restarting sources or changing offsets',async()=>{
 const p=new Player({});await p.play(track('field'));const nodes=[...p.context.sources];p.setIntensity('danger');
 assert.deepEqual(p.context.sources,nodes);assert.ok(p.orchestra.nodes.every(n=>n.level===1));
 assert.equal(gameplayIntensity({battle:{heroes:[{hp:20,maxHp:100}]}}),'danger');
 assert.equal(gameplayIntensity({battle:{heroes:[{hp:80,maxHp:100}]}}),'alert');
});
test('explicit silence and performances remain intact; context chooses coherent three-variation pools',()=>{
 assert.equal(orchestralCategory({}, {kind:'performance',ids:['long']}),null);
 assert.equal(orchestralCategory({}, {kind:'field',ids:[]}),null);
 assert.equal(orchestralCategory({scene:{interior:'inn'}},{kind:'field',key:'home',ids:['a']}),'interior');
 const m={cues:[1,2,3].map(n=>({id:'combat_'+n,loop:true,category:'combat'}))};
 const select=orchestratedProgram(()=>({kind:'battle',key:'battle',ids:['old']}),m);
 const p=select({state:{chapter:1}});assert.equal(p.ids.length,3);assert.ok(p.ids.every(id=>id.startsWith('orchestra:combat_')));
});
