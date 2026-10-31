import {AdaptiveSoundtrack} from './adaptive-soundtrack.js?v=5.33.0';

export const LAYERS={calm:{bed:1,theme:.65,motion:.15},alert:{bed:1,theme:.85,motion:.55},danger:{bed:1,theme:1,motion:1}};
export const nextBar=(now,start,bar=2.4)=>start+Math.ceil((now-start+.04)/bar)*bar;

/** Existing media/instrument controls plus a three-stem, sample-clock transport.
 * Every source in an arrangement has the same start, offset and finite stop.
 * Downloads are generation guarded; pause never restarts an obsolete request. */
export class OrchestralSoundtrack extends AdaptiveSoundtrack {
 constructor(options={}){super(options);this.orchestra=null;this.orchestraVoices=new Set();this.intensity='calm';}
 get playbackState(){
  const s=this.orchestra;if(!s)return super.playbackState;
  const elapsed=this.playing?Math.max(0,this.context.currentTime-s.start):0;
  const position=Math.min(s.duration,s.offset+elapsed);
  return {playing:this.playing&&this.context.state==='running',requested:this.playing,
   blocked:this.blocked,contextState:this.context.state,transport:'orchestral-stems',
   position,duration:s.duration,remaining:s.duration-position,trackId:s.track.id,
   intensity:this.intensity,stems:s.nodes.length};
 }
 retireOrchestra(seconds=0,at=this.context?.currentTime||0){
  for(const voice of this.orchestraVoices){
   voice.retired=true;
   const p=voice.gain.gain;p.cancelScheduledValues(at);p.setValueAtTime(voice.level,at);p.linearRampToValueAtTime(0,at+seconds);
   try{voice.source.stop(at+seconds);}catch{}
  }
 }
 async stemBuffers(track){return Promise.all(Object.entries(track.stems).map(async([name,file])=>({name,buffer:await this.load(file)})));}
 launch(track,buffers,offset,start,fade){
  const duration=track.duration_s,session={track,buffers,offset,start,duration,nodes:[],ended:false};
  for(const {name,buffer} of buffers){
   if(Math.abs(buffer.duration-track.cycle_s)>.02)throw Error('Decoded stem length differs from score clock');
   const source=this.context.createBufferSource(),gain=this.context.createGain();
   source.buffer=buffer;source.loop=!!track.loopScore;source.loopStart=0;source.loopEnd=track.cycle_s;
   const level=LAYERS[this.intensity][name]??1;
   gain.gain.setValueAtTime(0,start);gain.gain.linearRampToValueAtTime(level,start+fade);
   source.connect(gain);gain.connect(this.master);
   const voice={source,gain,name,level,retired:false};session.nodes.push(voice);this.orchestraVoices.add(voice);
   source.onended=()=>{
    this.orchestraVoices.delete(voice);gain.disconnect();source.disconnect();
    if(voice.retired||name!=='bed'||this.orchestra!==session||session.ended||!this.playing)return;
    session.ended=true;session.offset=duration;this.playing=false;this.endDelivered=true;
    this.options.onState?.(false);this.options.onEnd?.();
   };
   source.start(start,offset%track.cycle_s);source.stop(start+duration-offset);
  }
  return session;
 }
 async play(track){
  if(!track?.stems){this.retireOrchestra(.3);this.orchestra=null;return super.play(track);}
  this.cancelPending();const token=this.fadeToken;
  try{
   this.setup();await this.context.resume();
   const buffers=await this.stemBuffers(track);if(token!==this.fadeToken)return null;
   const now=this.context.currentTime,old=this.orchestra;
   const at=old&&this.playing?nextBar(now,old.start-old.offset):now+.05;
   const fade=old?Math.min(2.4,old.duration-old.offset):.12;
   const session=this.launch(track,buffers,0,at,fade);
   this.retireOrchestraExcept(session,fade,at);
   this.clearEndTimer();this.fadeMedia(.3);this.fadeVoices(.3);this.adaptive=null;this.activeTrack=null;
   this.orchestra=session;this.playing=true;this.endDelivered=false;this.blocked=false;this.select(track);
   this.options.onState?.(true);return true;
  }catch(error){if(token!==this.fadeToken)return null;this.reportError(error);return false;}
 }
 retireOrchestraExcept(session,seconds,at){
  const keep=new Set(session.nodes);
  for(const voice of this.orchestraVoices){
   if(keep.has(voice)||voice.retired)continue;voice.retired=true;
   const p=voice.gain.gain;p.cancelScheduledValues(at);p.setValueAtTime(voice.level,at);p.linearRampToValueAtTime(0,at+seconds);
   try{voice.source.stop(at+seconds);}catch{}
  }
 }
 setIntensity(value){
  if(!LAYERS[value]||this.intensity===value)return;this.intensity=value;
  const at=Math.max(this.context?.currentTime||0,this.orchestra?.start||0);
  for(const voice of this.orchestra?.nodes||[]){if(voice.retired)continue;
   const level=LAYERS[value][voice.name]??1,p=voice.gain.gain;
   p.cancelScheduledValues(at);p.setValueAtTime(voice.level,at);p.linearRampToValueAtTime(level,at+.8);voice.level=level;
  }
 }
 pause(){
  const s=this.orchestra;
  if(s&&this.playing)s.offset=Math.min(s.duration,s.offset+Math.max(0,this.context.currentTime-s.start));
  this.retireOrchestra(0);super.pause();
 }
 async resume(){
  const s=this.orchestra;if(!s)return super.resume();if(this.playing)return true;
  if(s.ended||s.offset>=s.duration)return false;
  this.cancelPending();const token=this.fadeToken;
  try{await this.context.resume();if(token!==this.fadeToken||this.orchestra!==s)return null;
   this.orchestra=this.launch(s.track,s.buffers,s.offset,this.context.currentTime+.03,.08);
   this.playing=true;this.blocked=false;this.options.onState?.(true);return true;
  }catch(error){this.reportError(error);return false;}
 }
 stop(options={}){this.retireOrchestra(options.fadeSeconds||0);this.orchestra=null;super.stop(options);}
 preload(track){if(!track?.stems)return super.preload(track);if(!this.context)return false;
  if(this.stemPreload?.id===track.id)return true;
  this.stemPreload={id:track.id,promise:this.stemBuffers(track).catch(()=>null)};return true;
 }
 async cue(track){
  if(!track?.stems)return super.cue(track);
  const token=this.fadeToken;this.setup();await this.context.resume();
  const buffers=await this.stemBuffers(track);if(token!==this.fadeToken)return null;
  const at=this.context.currentTime+.03;
  for(const {buffer} of buffers){const source=this.context.createBufferSource(),gain=this.context.createGain();
   source.buffer=buffer;gain.gain.value=.22;source.connect(gain);gain.connect(this.master);
   const voice={source,gain,level:.22,retired:false};this.orchestraVoices.add(voice);
   source.onended=()=>{source.disconnect();gain.disconnect();this.orchestraVoices.delete(voice);};source.start(at);
  }return true;
 }
}

export function attachOrchestralLibrary(library,manifest,base){
 for(const cue of manifest.cues){
  const id='orchestra:'+cue.id,stems=Object.fromEntries(Object.entries(cue.stems).map(([k,v])=>[k,new URL(v.file,base).href]));
  library.set(id,{...cue,id,stems,audio:stems.bed,cycle_s:cue.duration_s,
   duration_s:cue.duration_s*(cue.loop?2:1),loopScore:cue.loop,
   family:'orchestra:'+cue.category,recordingKey:id,gain:1,orchestral:true});
 }return library;
}
export function orchestralCategory(context,legacy){
 if(legacy.kind==='performance'||!legacy.ids?.length)return null;
 if(legacy.kind==='boss')return 'boss';if(legacy.kind==='battle')return 'combat';
 const text=String(legacy.key).toLowerCase();
 if(/cavern|ruins/.test(text))return 'dungeon';
 if(context.scene?.interior||context.scene?.household)return 'interior';
 if(/night|frost|highland|chapel/.test(text))return 'atmospheric';
 if(/home|town|workshop|archive|rail/.test(text))return 'settlement';
 return 'exploration';
}
export function orchestratedProgram(legacyProgram,manifest){
 return context=>{const legacy=legacyProgram(context),category=orchestralCategory(context,legacy);
  if(!category)return legacy;
  const variants=manifest.cues.filter(c=>c.loop&&c.category===category);
  const offset=(context.state?.chapter||0)%3;
  const ids=variants.map((_,i)=>'orchestra:'+variants[(i+offset)%variants.length].id);
  return {...legacy,key:legacy.key+':orchestra:'+category,ids:ids.length?ids:legacy.ids};
 };
}
export function gameplayIntensity({battle,scene,state}={}){
 if(battle){const heroes=battle.heroes||[],danger=heroes.some(h=>Number(h.hp)/Math.max(1,Number(h.maxHp??h.max_hp??h.stats?.hp))<.35);
  return danger||battle.boss||battle.enemies?.some(e=>e.boss)?'danger':'alert';}
 return /night|storm|ruin|cavern|cistern/.test([scene?.key,scene?.biome?.style].join(' '))?'alert':'calm';
}
