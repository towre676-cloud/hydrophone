import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import * as THREE from "three";

// ═══════════════════════════════════════════════════════════════════════════════
// DYLETSKY ENGINE v6
// Six advances:
//   1. Fully spelled semantics — weights, targets, forcing on spelled labels
//   2. Compositional weight algebra — primitive operators (KEY·CAD·HEX·CON·VL)
//   3. Sparse inverse recovery — minimal symmetry breaker from observed data
//   4. Spectral flow law — modal ODE: ȧₘ = −γₘaₘ + σₘ·(context forcing)
//   5. Algebraic room — Three.js acoustics driven by operator invariants
//   6. Comparative formal operators — Dyletsky vs Tonal vs Chant vs Guide-Tone
// ═══════════════════════════════════════════════════════════════════════════════

const PC=['C','C#','D','Eb','E','F','F#','G','Ab','A','Bb','B'];
const N=12;
const QCM={M3:-13.686,m3:10.265,P5:-3.422};
const HEX_NAT=new Set([0,2,4,5,7,9]);
const HEX_HARD=new Set([7,9,11,0,2,4]);
const HEX_SOFT=new Set([5,7,9,10,0,2]);
const MODE_FIN=new Set([2,4,5,7]);

// ── ADVANCE 1: FULLY SPELLED 17-NOTE SYSTEM ──────────────────────────────────
// Every note has a spelled identity; enharmonics are distinct columns
const SP17=['C','Db','C#','D','Eb','D#','E','F','Gb','F#','G','Ab','G#','A','Bb','A#','B'];
const SP17_PC={C:0,Db:1,'C#':1,D:2,Eb:3,'D#':3,E:4,F:5,Gb:6,'F#':6,G:7,Ab:8,'G#':8,A:9,Bb:10,'A#':10,B:11};
const SP17_DIA={C:0,Db:1,'C#':0,D:1,Eb:2,'D#':1,E:2,F:3,Gb:4,'F#':3,G:4,Ab:5,'G#':4,A:5,Bb:6,'A#':5,B:6};
// Spelled hexachord membership — distinguishes G# (hard) from Ab (soft)
const SP17_HARD=new Set(['G','G#','A','A#','B','C']); // hard-hex sharps
const SP17_SOFT=new Set(['F','Gb','Ab','Bb','C','Db']); // soft-hex flats
const SP17_NAT=new Set(['C','D','E','F','G','A','B']); // natural hex (pure diatonics)
const SP17_FIN=new Set(['D','E','F','G']); // mode finals (spelled)

function buildJ17(){
  // 37×17 Jacobian on spelled basis — semitone + diatonic step matching
  const IVMAP={M3:[4,2],m3:[3,1],P5:[7,4]};
  const rows=[],labels=[];
  for(const[fam,[sem,dia]]of Object.entries(IVMAP)){
    for(let si=0;si<17;si++){
      const sn=SP17[si];
      for(let ej=0;ej<17;ej++){
        const en=SP17[ej];
        if((SP17_PC[en]-SP17_PC[sn]+12)%12===sem&&(SP17_DIA[en]-SP17_DIA[sn]+7)%7===dia){
          const row=Array(17).fill(0);row[ej]=1;row[si]=-1;
          rows.push(row);
          // Spelled labels carry full enharmonic identity
          labels.push({fam,si,ej,sn,en,
            pc_s:SP17_PC[sn],pc_e:SP17_PC[en],
            sharp_s:sn.includes('#'),flat_s:sn.includes('b'),
            sharp_e:en.includes('#'),flat_e:en.includes('b'),
            nat_s:!sn.includes('#')&&!sn.includes('b'),
            nat_e:!en.includes('#')&&!en.includes('b'),
          });
        }
      }
    }
  }
  return{rows,labels};
}

// ── ADVANCE 2: COMPOSITIONAL WEIGHT ALGEBRA ───────────────────────────────────
// Style = product/blend of primitive symmetry-breaking operators
// KEY: key-field weighting | CAD: cadence-field | HEX: hexachord sector
// CON: consonance priority | VL: voice-leading privilege
const PRIM_OPS={
  KEY:  (lbl,p)=>{ // key-field: upweight intervals whose tones are in key
    const inKey=new Set(p.key||[0,2,4,5,7,9,11]);
    return(inKey.has(lbl.pc_s)&&inKey.has(lbl.pc_e))?p.w||3:1;
  },
  CAD:  (lbl,p)=>{ // cadential: upweight intervals resolving to finals
    const fins=p.finals||[7,2,4,5];
    return fins.includes(lbl.pc_e)?p.w||5:1;
  },
  HEX:  (lbl,p)=>{ // hexachord sector — fully spelled: G# ≠ Ab
    const sect=p.sector||'nat';
    if(sect==='hard') return(SP17_HARD.has(lbl.sn)&&SP17_HARD.has(lbl.en))?p.w||3:1;
    if(sect==='soft') return(SP17_SOFT.has(lbl.sn)&&SP17_SOFT.has(lbl.en))?p.w||3:1;
    return(SP17_NAT.has(lbl.sn)&&SP17_NAT.has(lbl.en))?p.w||3:1;
  },
  CON:  (lbl,p)=>{ // consonance: upweight P5 and M3 families
    return(p.fams||['P5','M3']).includes(lbl.fam)?p.w||2:1;
  },
  VL:   (lbl,p)=>{ // voice-leading: upweight short intervals (m3 privilege)
    return lbl.fam==='m3'?p.w||2.5:1;
  },
};

// Named strategies as compositions of primitive operators
// Each entry: array of {op, params} — final weight = product of all primitive weights
const STRAT_ALGEBRA={
  ET:        [],
  hex_nat:   [{op:'HEX',p:{sector:'nat',w:3}},{op:'CON',p:{w:1.5}}],
  hex_hard:  [{op:'HEX',p:{sector:'hard',w:3}},{op:'CON',p:{w:1.5}}],
  hex_soft:  [{op:'HEX',p:{sector:'soft',w:3}},{op:'VL',p:{w:2}}],
  modal:     [{op:'CAD',p:{finals:[2,4,5,7],w:5}},{op:'KEY',p:{key:[0,2,4,5,7,9],w:2}}],
  resurrect: [{op:'HEX',p:{sector:'hard',w:4}},{op:'CAD',p:{finals:[2,4,5,7],w:8}},{op:'CON',p:{w:2}}],
  passion:   [{op:'VL',p:{w:3}},{op:'HEX',p:{sector:'soft',w:2}},{op:'CON',p:{fams:['m3'],w:2}}],
  liturgy:   [{op:'CON',p:{fams:['M3','m3'],w:2.5}},{op:'HEX',p:{sector:'nat',w:1.5}},{op:'KEY',p:{w:1.5}}],
  cadence:   [{op:'CAD',p:{finals:[4,7,11],w:5}},{op:'CON',p:{w:2}}],
  // ── ADVANCE 6: Comparative operators ──
  tonal:     [{op:'KEY',p:{key:[0,2,4,5,7,9,11],w:4}},{op:'CAD',p:{finals:[0,7],w:6}},{op:'CON',p:{fams:['P5','M3'],w:3}}],
  chant:     [{op:'CAD',p:{finals:[2,5,7,9],w:7}},{op:'KEY',p:{key:[0,2,4,5,7,9],w:3}},{op:'VL',p:{w:1.5}}],
  guidetone: [{op:'CON',p:{fams:['M3','m3'],w:5}},{op:'VL',p:{w:3}},{op:'CAD',p:{finals:[4,10,7,2],w:3}}],
  triad:     [{op:'CON',p:{fams:['M3','m3','P5'],w:4}},{op:'KEY',p:{key:[0,4,7],w:5}}],
};

// Algebraic weight computation: product of all primitive operators on spelled labels
function algebraicWeight(strat,lbl){
  const ops=STRAT_ALGEBRA[strat]||[];
  if(!ops.length)return 1;
  return ops.reduce((w,{op,p})=>w*PRIM_OPS[op](lbl,p),1);
}

// Spelled target vector: can depend on spelled interval identity (not just family)
// This is the key advance — b is now spelled-label-aware
function spelledTarget(lbl){
  const base=QCM[lbl.fam];
  // Spelled correction: sharp-side M3s are slightly brighter, flat-side slightly darker
  if(lbl.fam==='M3'){
    if(lbl.sharp_s&&!lbl.sharp_e) return base-0.8; // ascending from sharp: brighter
    if(lbl.flat_e&&!lbl.flat_s)   return base+0.8; // descending to flat: darker
  }
  if(lbl.fam==='P5'){
    if(lbl.nat_s&&lbl.nat_e) return base+0.4; // natural fifths: slightly purer
  }
  return base;
}

function solve_n(A,b){
  const n=A.length,M=A.map((r,i)=>[...r,b[i]]);
  for(let c=0;c<n;c++){
    let mx=c;for(let r=c+1;r<n;r++)if(Math.abs(M[r][c])>Math.abs(M[mx][c]))mx=r;
    [M[c],M[mx]]=[M[mx],M[c]];
    const p=M[c][c];if(Math.abs(p)<1e-14)continue;
    for(let r=0;r<n;r++){if(r===c)continue;const f=M[r][c]/p;for(let j=c;j<=n;j++)M[r][j]-=f*M[c][j];}
  }
  return M.map((r,i)=>r[n]/r[i]);
}

// Fully spelled solve: weights AND targets are spelled-label-aware
function computeSpelled(strat,J17,lam=0.008){
  const w=J17.labels.map(lbl=>algebraicWeight(strat,lbl));
  const b=J17.labels.map(lbl=>spelledTarget(lbl));
  const Jr=J17.rows.map(r=>r.slice(1)),n=Jr[0].length; // n=16 (gauge: C fixed)
  const JtWJ=Array.from({length:n},(_,i)=>Array.from({length:n},(_,j)=>Jr.reduce((s,r,k)=>s+w[k]*r[i]*r[j],0)));
  const JtWb=Array.from({length:n},(_,j)=>Jr.reduce((s,r,k)=>s+w[k]*r[j]*b[k],0));
  const eta_sp=Math.sqrt(JtWb.reduce((s,v)=>s+v*v,0)); // spelled forcing invariant
  for(let i=0;i<n;i++)JtWJ[i][i]+=lam;
  const xr=eta_sp>1e-12?solve_n(JtWJ,JtWb):Array(n).fill(0);
  const xf17=[0,...xr]; // 17-dim spelled offset vector
  // Playback projection P: R^17 → R^12 (average enharmonic pairs)
  const pcOffs=Array(N).fill(0),pcCnt=Array(N).fill(0);
  SP17.forEach((note,i)=>{const pc=SP17_PC[note];pcOffs[pc]+=xf17[i];pcCnt[pc]++;});
  const xf12=pcOffs.map((v,i)=>pcCnt[i]?v/pcCnt[i]:0);
  // Enharmonic distinction (G#−Ab, C#−Db, etc.)
  const enhDiff={};
  [[8,'G#','Ab'],[1,'C#','Db'],[3,'D#','Eb'],[6,'F#','Gb'],[10,'A#','Bb']].forEach(([pc,sh,fl])=>{
    const si=SP17.indexOf(sh),fi=SP17.indexOf(fl);
    enhDiff[`${sh}/${fl}`]=xf17[si]-xf17[fi];
  });
  const wRMS_num=J17.rows.reduce((s,r,k)=>{const res=w[k]*(r.reduce((s2,v,i)=>s2+v*xf17[i],0)-b[k]);return s+res*res;},0);
  const wRMS=Math.sqrt(wRMS_num/w.reduce((s,v)=>s+v,0));
  return{xf17,xf12,eta_sp,xnorm:Math.sqrt(xf17.reduce((s,v)=>s+v*v,0)),wRMS,enhDiff,
         opDecomposition:STRAT_ALGEBRA[strat]||[]};
}

// ── ADVANCE 4: SPECTRAL FLOW LAW ──────────────────────────────────────────────
// Modal ODE: ȧₘ = −γₘ·aₘ + σₘ·fₘ(context)
// where fₘ = projection of context forcing onto mode m
// γₘ = decay rate (slower for soft modes, faster for stiff modes)
// This turns the Kalman snapshot into a dynamical system in R^11 (or R^16 spelled)
const EIGENMODES=[
  {val:8.732051,sigma:2.955004,vec:[0,-0.204124,-0.353553,-0.408248,-0.353553,-0.204124,0,0.204124,0.353553,0.408248,0.353553,0.204124]},
  {val:8.486734,sigma:2.913200,vec:[0,0.333615,0.190267,0.221825,-0.166202,-0.309551,-0.599747,-0.309551,-0.166202,0.221825,0.190267,0.333615]},
  {val:8.000000,sigma:2.828427,vec:[0,0.472866,-0.162472,0,-0.472866,0.162472,0,0.472866,-0.162472,0,-0.472866,0.162472]},
  {val:8.000000,sigma:2.828427,vec:[0,-0.162472,-0.472866,0,0.162472,0.472866,0,-0.162472,-0.472866,0,0.162472,0.472866]},
  {val:6.970936,sigma:2.640253,vec:[0,-0.325990,-0.173921,0.577964,-0.026272,0.125796,-0.160779,0.125796,-0.026272,0.577964,-0.173921,-0.325990]},
  {val:6.000000,sigma:2.449490,vec:[0,-0.353553,0.353553,0,-0.353553,0.353553,0,-0.353553,0.353553,0,-0.353553,0.353553]},
  {val:5.617691,sigma:2.370167,vec:[0,-0.139492,0.210434,-0.194945,0.076654,0.426580,-0.648706,0.426580,0.076654,-0.194945,0.210434,-0.139492]},
  {val:5.267949,sigma:2.295201,vec:[0,0.204124,-0.353553,0.408248,-0.353553,0.204124,0,-0.204124,0.353553,-0.408248,0.353553,-0.204124]},
  {val:4.424066,sigma:2.103346,vec:[0,-0.186361,0.391335,0.015149,-0.519077,0.058620,0.279355,0.058620,-0.519077,0.015149,0.391335,-0.186361]},
  {val:4.000000,sigma:2.000000,vec:[0,-0.408248,0,0.408248,0,-0.408248,0,0.408248,0,-0.408248,0,0.408248]},
  {val:0.500572,sigma:0.707511,vec:[0,0.321315,0.333353,0.280211,0.267152,0.279190,0.339991,0.279190,0.267152,0.280211,0.333353,0.321315]},
];
// Decay rates: γₘ proportional to σₘ² (stiff modes decay fast, soft modes persist)
const GAMMA=EIGENMODES.map(m=>0.08*m.val/8.732051);

// ── VOICE PROFILES ────────────────────────────────────────────────────────────
const VOICE_PROFILES=[
  {name:'S1',hex:'hex_hard',color:'#f9a8d4',gains:[1,.72,.48,.32,.20,.13,.07,.03],subGain:0.00,detuneHz:.35,vibRate:5.40,vibMaxHz:.90,pos:[-2.8,1.85,-8.5]},
  {name:'S2',hex:'hex_hard',color:'#f472b6',gains:[1,.70,.45,.29,.17,.10,.05,.02],subGain:0.00,detuneHz:-.30,vibRate:5.20,vibMaxHz:.80,pos:[2.8,1.85,-8.5]},
  {name:'A1',hex:'hex_nat', color:'#c4b5fd',gains:[1,.62,.38,.22,.12,.06,.02,.01],subGain:0.06,detuneHz:.20,vibRate:5.00,vibMaxHz:.70,pos:[-1.8,1.65,-10.0]},
  {name:'A2',hex:'hex_nat', color:'#a78bfa',gains:[1,.60,.36,.20,.11,.05,.02,.01],subGain:0.07,detuneHz:-.16,vibRate:4.80,vibMaxHz:.65,pos:[1.8,1.65,-10.0]},
  {name:'T1',hex:'hex_nat', color:'#6ee7b7',gains:[1,.65,.42,.25,.13,.06,.02,.01],subGain:0.09,detuneHz:.12,vibRate:4.60,vibMaxHz:.55,pos:[-2.5,1.50,-12.0]},
  {name:'T2',hex:'hex_nat', color:'#34d399',gains:[1,.63,.40,.23,.12,.05,.02,.01],subGain:0.10,detuneHz:-.08,vibRate:4.40,vibMaxHz:.50,pos:[2.5,1.50,-12.0]},
  {name:'B1',hex:'hex_soft',color:'#fcd34d',gains:[1,.76,.53,.33,.19,.10,.05,.02],subGain:0.16,detuneHz:.05,vibRate:4.10,vibMaxHz:.35,pos:[-3.5,1.30,-13.5]},
  {name:'B2',hex:'hex_soft',color:'#fb923c',gains:[1,.79,.57,.37,.23,.13,.07,.03],subGain:0.22,detuneHz:-.03,vibRate:3.90,vibMaxHz:.30,pos:[3.5,1.30,-13.5]},
];

const PH_STRAT={jubilate:'resurrect',interior:'hex_nat','pre-cad':'cadence',cadence:'modal',resolve:'liturgy',rest:'ET'};
const SCORE8=[
  {b:0,v:0,pc:7,oct:5,dur:2,ph:'jubilate'},{b:0,v:1,pc:4,oct:5,dur:2,ph:'jubilate'},
  {b:0,v:2,pc:0,oct:5,dur:2,ph:'jubilate'},{b:0,v:3,pc:11,oct:4,dur:2,ph:'jubilate'},
  {b:0,v:4,pc:7,oct:4,dur:2,ph:'jubilate'},{b:0,v:5,pc:4,oct:4,dur:2,ph:'jubilate'},
  {b:0,v:6,pc:0,oct:3,dur:2,ph:'jubilate'},{b:0,v:7,pc:7,oct:2,dur:2,ph:'jubilate'},
  {b:2,v:0,pc:9,oct:5,dur:1,ph:'interior'},{b:2,v:1,pc:5,oct:5,dur:1,ph:'interior'},
  {b:2,v:2,pc:2,oct:5,dur:1,ph:'interior'},{b:2,v:3,pc:0,oct:5,dur:1,ph:'interior'},
  {b:2,v:4,pc:9,oct:4,dur:1,ph:'interior'},{b:2,v:5,pc:5,oct:4,dur:1,ph:'interior'},
  {b:2,v:6,pc:2,oct:3,dur:1,ph:'interior'},{b:2,v:7,pc:9,oct:2,dur:1,ph:'interior'},
  {b:3,v:0,pc:11,oct:5,dur:1,ph:'interior'},{b:3,v:1,pc:7,oct:5,dur:1,ph:'interior'},
  {b:3,v:2,pc:4,oct:5,dur:1,ph:'interior'},{b:3,v:3,pc:2,oct:5,dur:1,ph:'interior'},
  {b:3,v:4,pc:11,oct:3,dur:1,ph:'interior'},{b:3,v:5,pc:7,oct:3,dur:1,ph:'interior'},
  {b:3,v:6,pc:4,oct:3,dur:1,ph:'interior'},{b:3,v:7,pc:11,oct:2,dur:1,ph:'interior'},
  {b:4,v:0,pc:9,oct:5,dur:1,ph:'pre-cad'},{b:4,v:1,pc:7,oct:5,dur:1,ph:'pre-cad'},
  {b:4,v:2,pc:5,oct:5,dur:1,ph:'pre-cad'},{b:4,v:3,pc:2,oct:5,dur:1,ph:'pre-cad'},
  {b:4,v:4,pc:9,oct:3,dur:1,ph:'pre-cad'},{b:4,v:5,pc:5,oct:3,dur:1,ph:'pre-cad'},
  {b:4,v:6,pc:2,oct:3,dur:1,ph:'pre-cad'},{b:4,v:7,pc:7,oct:2,dur:1,ph:'pre-cad'},
  {b:5,v:0,pc:7,oct:5,dur:3,ph:'cadence'},{b:5,v:1,pc:4,oct:5,dur:3,ph:'cadence'},
  {b:5,v:2,pc:11,oct:4,dur:3,ph:'cadence'},{b:5,v:3,pc:7,oct:4,dur:3,ph:'cadence'},
  {b:5,v:4,pc:4,oct:4,dur:3,ph:'cadence'},{b:5,v:5,pc:11,oct:3,dur:3,ph:'cadence'},
  {b:5,v:6,pc:7,oct:3,dur:3,ph:'cadence'},{b:5,v:7,pc:7,oct:2,dur:3,ph:'cadence'},
  {b:8,v:0,pc:4,oct:5,dur:4,ph:'resolve'},{b:8,v:1,pc:7,oct:4,dur:4,ph:'resolve'},
  {b:8,v:2,pc:11,oct:4,dur:4,ph:'resolve'},{b:8,v:3,pc:4,oct:4,dur:4,ph:'resolve'},
  {b:8,v:4,pc:7,oct:3,dur:4,ph:'resolve'},{b:8,v:5,pc:11,oct:3,dur:4,ph:'resolve'},
  {b:8,v:6,pc:4,oct:3,dur:4,ph:'resolve'},{b:8,v:7,pc:7,oct:2,dur:4,ph:'resolve'},
];
const VH8=['hex_hard','hex_hard','hex_nat','hex_nat','hex_nat','hex_nat','hex_soft','hex_soft'];

function toHz(pc,off,oct=4){return 440*Math.pow(2,((pc-9+12*(oct-4))*100+off)/1200);}

// ── ADVANCE 5: ALGEBRAIC ROOM ─────────────────────────────────────────────────
// Room responds to operator invariants: η, modal energy, soft-mode energy, hex sector
function setupChurch(canvas,refs){
  const W=canvas.clientWidth||700,H=canvas.clientHeight||400;
  const renderer=new THREE.WebGLRenderer({canvas,antialias:true});
  renderer.setSize(W,H);renderer.setPixelRatio(Math.min(window.devicePixelRatio,2));
  renderer.setClearColor(0x040508);
  const scene=new THREE.Scene();
  scene.fog=new THREE.FogExp2(0x080510,0.035);
  const camera=new THREE.PerspectiveCamera(68,W/H,0.1,200);
  camera.position.set(0,1.7,12);

  // Room
  scene.add(new THREE.Mesh(new THREE.BoxGeometry(22,14,50),
    new THREE.MeshLambertMaterial({color:0x0d0505,side:THREE.BackSide})));
  // Floor
  const floor=new THREE.Mesh(new THREE.BoxGeometry(22,0.4,50),
    new THREE.MeshLambertMaterial({color:0x2a1a0a}));
  floor.position.y=-7.2;scene.add(floor);
  // Iconostasis
  const ico=new THREE.Mesh(new THREE.BoxGeometry(22,11,0.6),
    new THREE.MeshLambertMaterial({color:0x3a2008}));
  ico.position.set(0,0,-20);scene.add(ico);
  // Cross
  const cMat=new THREE.MeshLambertMaterial({color:0xFFD700,emissive:new THREE.Color(0xFFD700),emissiveIntensity:0.5});
  const cv=new THREE.Mesh(new THREE.BoxGeometry(0.25,3.5,0.25),cMat);
  const ch=new THREE.Mesh(new THREE.BoxGeometry(2.2,0.25,0.25),cMat);
  cv.position.set(0,3.5,-19.5);ch.position.set(0,4.8,-19.5);
  scene.add(cv);scene.add(ch);
  // Lights
  const altarLight=new THREE.PointLight(0xFFCC44,3,25);
  altarLight.position.set(0,4,-18);scene.add(altarLight);
  scene.add(new THREE.AmbientLight(0x221205,2));
  // Dome
  const dome=new THREE.Mesh(new THREE.SphereGeometry(11,24,12,0,Math.PI*2,0,Math.PI/2),
    new THREE.MeshLambertMaterial({color:0x06040f,side:THREE.BackSide}));
  dome.position.set(0,7,0);scene.add(dome);
  // Stars
  const starPos=new Float32Array(360);
  for(let i=0;i<120;i++){
    const th=Math.random()*2*Math.PI,ph=Math.random()*Math.PI*.45,r=10.5;
    starPos[i*3]=r*Math.sin(ph)*Math.cos(th);
    starPos[i*3+1]=r*Math.cos(ph)+7;
    starPos[i*3+2]=r*Math.sin(ph)*Math.sin(th);
  }
  const starGeo=new THREE.BufferGeometry();
  starGeo.setAttribute('position',new THREE.BufferAttribute(starPos,3));
  scene.add(new THREE.Points(starGeo,new THREE.PointsMaterial({color:0xEEEEFF,size:0.06})));
  // 12 Icon planes — colored by hex sector
  const ICON_COLS=[0x3b82f6,0xf59e0b,0x3b82f6,0x10b981,0x3b82f6,0x3b82f6,0xf59e0b,0x3b82f6,0x10b981,0x3b82f6,0x10b981,0x475569];
  const iconMeshes=[],iconLights=[];
  for(let i=0;i<N;i++){
    const side=i<6?1:-1,zi=i%6,z=(zi-2.5)*6.5;
    const col=ICON_COLS[i];
    const mat=new THREE.MeshLambertMaterial({color:new THREE.Color(col).multiplyScalar(0.25),emissive:new THREE.Color(col),emissiveIntensity:0.08});
    const mesh=new THREE.Mesh(new THREE.PlaneGeometry(2.5,3.5),mat);
    mesh.position.set(side*10.8,1,z);mesh.rotation.y=-side*Math.PI/2;
    scene.add(mesh);iconMeshes.push(mesh);
    const lt=new THREE.PointLight(new THREE.Color(col),0.3,10);
    lt.position.set(side*9.5,1.5,z);scene.add(lt);iconLights.push(lt);
  }
  // Candles
  [[2,-6.5,-12],[-2,-6.5,-12],[4,-6.5,0],[-4,-6.5,0],[2,-6.5,12],[-2,-6.5,12]].forEach(([x,y,z])=>{
    const candle=new THREE.Mesh(new THREE.CylinderGeometry(0.06,0.08,1.8),
      new THREE.MeshLambertMaterial({color:0xFFFFDD}));
    candle.position.set(x,y,z);scene.add(candle);
    const fl=new THREE.PointLight(0xFF9933,0.7,5);
    fl.position.set(x,y+1.1,z);scene.add(fl);
  });
  // Incense particles — diffusion rate driven by η (Advance 5)
  const incN=200,incPos=new Float32Array(incN*3),incVel=new Float32Array(incN*3);
  for(let i=0;i<incN;i++){
    incPos[i*3]=(Math.random()-.5)*18;incPos[i*3+1]=(Math.random()-.5)*10;
    incPos[i*3+2]=(Math.random()-.5)*40;
    incVel[i*3]=(Math.random()-.5)*.003;incVel[i*3+1]=Math.random()*.004+.001;
    incVel[i*3+2]=(Math.random()-.5)*.002;
  }
  const incGeo=new THREE.BufferGeometry();
  incGeo.setAttribute('position',new THREE.BufferAttribute(incPos,3));
  const incPts=new THREE.Points(incGeo,new THREE.PointsMaterial({color:0xCCBB99,size:0.1,transparent:true,opacity:.3}));
  scene.add(incPts);
  // Gravity spheres at mode finals
  const gravSpheres=[];
  [2,4,5,7].forEach(pc=>{
    const side=pc<6?1:-1,zi=pc%6,z=(zi-2.5)*6.5;
    const sg=new THREE.Mesh(new THREE.SphereGeometry(0.22,8,8),
      new THREE.MeshLambertMaterial({color:0x8b5cf6,emissive:new THREE.Color(0x8b5cf6),emissiveIntensity:0.4}));
    sg.position.set(side*9,2.5,z);scene.add(sg);gravSpheres.push({pc,mesh:sg});
  });
  // Soft-mode bloom sphere (Advance 5: soft-mode energy → room bloom)
  const bloomMesh=new THREE.Mesh(new THREE.SphereGeometry(3,16,8),
    new THREE.MeshLambertMaterial({color:0xc084fc,emissive:new THREE.Color(0xc084fc),emissiveIntensity:0,transparent:true,opacity:.08,side:THREE.BackSide}));
  bloomMesh.position.set(0,2,0);scene.add(bloomMesh);
  // Mouse look
  let mouseDown=false,lastX=0,lastY=0,yaw=0,pit=0;
  canvas.style.cursor='grab';
  canvas.addEventListener('mousedown',e=>{mouseDown=true;lastX=e.clientX;lastY=e.clientY;canvas.style.cursor='grabbing';});
  canvas.addEventListener('mouseup',()=>{mouseDown=false;canvas.style.cursor='grab';});
  canvas.addEventListener('mouseleave',()=>{mouseDown=false;canvas.style.cursor='grab';});
  canvas.addEventListener('mousemove',e=>{
    if(!mouseDown)return;
    yaw-=(e.clientX-lastX)*.0025;pit=Math.max(-.55,Math.min(.55,pit-(e.clientY-lastY)*.0025));
    lastX=e.clientX;lastY=e.clientY;
  });
  let lastTX=0,lastTY=0;
  canvas.addEventListener('touchstart',e=>{lastTX=e.touches[0].clientX;lastTY=e.touches[0].clientY;});
  canvas.addEventListener('touchmove',e=>{
    yaw-=(e.touches[0].clientX-lastTX)*.002;pit=Math.max(-.55,Math.min(.55,pit-(e.touches[0].clientY-lastTY)*.002));
    lastTX=e.touches[0].clientX;lastTY=e.touches[0].clientY;e.preventDefault();
  },{passive:false});
  const incPosArr=incGeo.attributes.position.array;
  let frame,t=0;
  function animate(){
    frame=requestAnimationFrame(animate);t+=0.016;
    camera.rotation.order='YXZ';camera.rotation.y=yaw;camera.rotation.x=pit;
    const xs=refs.xSmooth.current,eta_=refs.eta.current,av=refs.active.current;
    const softE=refs.softEnergy.current||0; // soft-mode energy from spectral flow
    const hexSector=refs.hexSector.current||'nat';
    // Advance 5: Icons respond to spelled hex sector
    iconMeshes.forEach((m,i)=>{
      const isAct=av.some(a=>a.pc===i),isFin=MODE_FIN.has(i);
      const off=xs[i]||0;
      m.material.emissiveIntensity=isAct?1.2:(isFin?0.4+eta_/237*.5:0.05+Math.abs(off)/20*.3);
      iconLights[i].intensity=isAct?3:(isFin?1+eta_/237*1.2:0.15+Math.abs(off)/20*.6);
      // Hex sector colors icons: hard→gold, soft→teal, nat→blue (Advance 5)
      if(isAct){iconLights[i].color.set(0xFFCC44);m.material.emissive.set(0xFFCC44);}
      else if(hexSector==='hard'&&HEX_HARD.has(i)){iconLights[i].color.set(0xf59e0b);m.material.emissive.set(0xf59e0b);}
      else if(hexSector==='soft'&&HEX_SOFT.has(i)){iconLights[i].color.set(0x10b981);m.material.emissive.set(0x10b981);}
      else{iconLights[i].color.setHex(ICON_COLS[i]);m.material.emissive.setHex(ICON_COLS[i]);}
    });
    cMat.emissiveIntensity=0.4+eta_/237*.8;
    altarLight.intensity=2+eta_/237*2;
    // Advance 5: Soft-mode energy → room bloom width and opacity
    bloomMesh.material.emissiveIntensity=softE*0.4;
    bloomMesh.scale.setScalar(1+softE*2);
    // Advance 5: η → incense diffusion rate
    const diffRate=1+eta_/237*3;
    for(let i=0;i<incN;i++){
      incPosArr[i*3]+=incVel[i*3]*diffRate;
      incPosArr[i*3+1]+=incVel[i*3+1]*diffRate;
      incPosArr[i*3+2]+=incVel[i*3+2]*diffRate;
      if(incPosArr[i*3+1]>6){incPosArr[i*3+1]=-6;incPosArr[i*3]=(Math.random()-.5)*16;}
    }
    incGeo.attributes.position.needsUpdate=true;
    gravSpheres.forEach(({pc,mesh})=>{
      const off=Math.abs(xs[pc]||0);
      mesh.material.emissiveIntensity=0.2+off/20*.8+Math.sin(t*2)*0.1;
      mesh.scale.setScalar(0.15+off/20*.3+Math.sin(t+pc)*0.05);
    });
    renderer.render(scene,camera);
  }
  animate();
  return()=>{cancelAnimationFrame(frame);renderer.dispose();};
}

// ── ADVANCE 3: SPARSE STYLE INVERSION ─────────────────────────────────────────
// Given observed offsets, find minimal operator composition (sparse weights on primitives)
// Solve: min ‖Σ wₛ·xₛ − obs‖ + λ·‖w‖₁ (LASSO-style via projected gradient)
function sparseInvert(obsArr,J17,lambda=0.05){
  const strats=Object.keys(STRAT_ALGEBRA);
  // Compute spelled x* for each strategy
  const Xs=strats.map(s=>{
    try{return computeSpelled(s,J17).xf12;}
    catch(e){return Array(N).fill(0);}
  });
  let w=Array(strats.length).fill(1/strats.length);
  // Projected subgradient descent with L1 regularization
  for(let iter=0;iter<1200;iter++){
    const pred=Array(N).fill(0);
    w.forEach((wi,si)=>Xs[si].forEach((v,i)=>{pred[i]+=wi*v;}));
    const residual=pred.map((v,i)=>v-obsArr[i]);
    const gradW=strats.map((_,si)=>2*Xs[si].reduce((s,v,i)=>s+v*residual[i],0)/N);
    const lr=0.008;
    // Subgradient: ∂‖w‖₁ = sign(w)
    w=w.map((wi,si)=>wi-lr*(gradW[si]+lambda*Math.sign(wi)));
    // Project: non-negative simplex (soft-threshold + normalize)
    w=w.map(v=>Math.max(0,v));
    const wSum=w.reduce((s,v)=>s+v,0);
    if(wSum>1e-10)w=w.map(v=>v/wSum);
  }
  const pred=Array(N).fill(0);
  w.forEach((wi,si)=>Xs[si].forEach((v,i)=>{pred[i]+=wi*v;}));
  const residual=pred.map((v,i)=>v-obsArr[i]);
  const rms=Math.sqrt(residual.reduce((s,v)=>s+v**2,0)/N);
  const sparsity=w.filter(v=>v<0.01).length/w.length;
  // Decompose recovered W into primitive operator contributions
  const domIdx=w.indexOf(Math.max(...w));
  const primContrib={KEY:0,CAD:0,HEX:0,CON:0,VL:0};
  strats.forEach((s,si)=>{
    STRAT_ALGEBRA[s].forEach(({op})=>{if(primContrib[op]!==undefined)primContrib[op]+=w[si];});
  });
  // Modal fingerprint of observed data
  const modalProj=EIGENMODES.map(m=>({sigma:m.sigma,coeff:obsArr.reduce((s,v,i)=>s+v*m.vec[i],0)}));
  return{w,strats,pred,residual,rms,sparsity,domStrat:strats[domIdx],primContrib,modalProj};
}

// ── MAIN COMPONENT ────────────────────────────────────────────────────────────
export default function DyletskyV6(){
  const J17=useMemo(buildJ17,[]);
  const audioCtx=useRef(null),masterG=useRef(null),panners=useRef([]);
  const analyserW=useRef(null),analyserF=useRef(null);
  const animFr=useRef(null),wCvs=useRef(null),sCvs=useRef(null);
  const beatTmr=useRef(null),beatRef=useRef(0);
  const churchCvs=useRef(null);
  // Refs for Three.js algebraic room
  const xSRef=useRef(Array(N).fill(0)),etaRef=useRef(0),avRef=useRef([]);
  const softEnergyRef=useRef(0),hexSectorRef=useRef('nat');

  // Engine state
  const [xSmooth,setXSmooth]=useState(Array(N).fill(0));
  const [voiceX,setVoiceX]=useState(Array(8).fill(null).map(()=>Array(N).fill(0)));
  const [spelled17,setSpelled17]=useState(Array(17).fill(0));
  const [spelled12,setSpelled12]=useState(Array(N).fill(0));
  const [enhDiff,setEnhDiff]=useState({});
  const [opDecomp,setOpDecomp]=useState([]);
  const [strategy,setStrategy]=useState('hex_nat');
  const [eta,setEta]=useState(0);
  const [xnorm,setXnorm]=useState(0);
  const [wRMS,setWrms]=useState(0);

  // Advance 4: Spectral flow state
  const [flowCoeffs,setFlowCoeffs]=useState(Array(11).fill(0));
  const [flowX,setFlowX]=useState(Array(N).fill(0));
  const [flowOn,setFlowOn]=useState(false);
  const [flowDt,setFlowDt]=useState(0.08); // integration step
  const [softEnergy,setSoftEnergy]=useState(0);

  // Audio features
  const [spatialOn,setSpatialOn]=useState(true);
  const [vibratoOn,setVibratoOn]=useState(true);
  const [eigenmodeOn,setEigenmodeOn]=useState(true);
  const [modeAmps,setModeAmps]=useState(Array(11).fill(0));

  // UI
  const [panel,setPanel]=useState('main');
  const [perfMode,setPerfMode]=useState(false);
  const [beat,setBeat]=useState(0);
  const [bpm,setBpm]=useState(68);
  const [activeV,setActiveV]=useState([]);
  const [beatHist,setBeatHist]=useState([]);
  const [midiNotes,setMidiNotes]=useState(new Map());
  const [midiOn,setMidiOn]=useState(false);

  // Advance 2: Operator algebra display
  const [showAlgebra,setShowAlgebra]=useState(false);

  // Advance 3: Inversion
  const [invInput,setInvInput]=useState('');
  const [invResult,setInvResult]=useState(null);
  const [invLambda,setInvLambda]=useState(0.05);

  // Advance 6: Comparator
  const [compareStrats,setCompareStrats]=useState(['resurrect','tonal','chant','guidetone']);

  // Timbre editor
  const [editVoice,setEditVoice]=useState(0);
  const [voiceGains,setVoiceGains]=useState(VOICE_PROFILES.map(p=>[...p.gains]));
  const [voiceSubGain,setVoiceSubGain]=useState(VOICE_PROFILES.map(p=>p.subGain));

  const ALPHA=0.10;
  const SC={ET:'#475569',hex_nat:'#3b82f6',hex_hard:'#f59e0b',hex_soft:'#10b981',modal:'#8b5cf6',
            resurrect:'#ef4444',passion:'#6366f1',liturgy:'#059669',cadence:'#dc2626',
            tonal:'#f97316',chant:'#a78bfa',guidetone:'#06b6d4',triad:'#84cc16'};
  const cc=SC[strategy]||'#3b82f6';

  // ── AUDIO SETUP ──────────────────────────────────────────────────────────────
  function ensureAudio(){
    if(audioCtx.current?.state==='suspended')audioCtx.current.resume();
    if(audioCtx.current)return audioCtx.current;
    const ctx=new(window.AudioContext||window.webkitAudioContext)({sampleRate:44100});
    audioCtx.current=ctx;
    const mg=ctx.createGain();mg.gain.value=0.45;mg.connect(ctx.destination);masterG.current=mg;
    const aW=ctx.createAnalyser();aW.fftSize=2048;aW.smoothingTimeConstant=0.82;
    const aF=ctx.createAnalyser();aF.fftSize=4096;aF.smoothingTimeConstant=0.75;
    mg.connect(aW);mg.connect(aF);analyserW.current=aW;analyserF.current=aF;
    const L=ctx.listener;
    if(L.positionX){L.positionX.value=0;L.positionY.value=1.7;L.positionZ.value=0;L.forwardX.value=0;L.forwardY.value=0;L.forwardZ.value=-1;L.upX.value=0;L.upY.value=1;L.upZ.value=0;}
    else try{L.setPosition(0,1.7,0);L.setOrientation(0,0,-1,0,1,0);}catch(e){}
    panners.current=VOICE_PROFILES.map((prof)=>{
      const pn=ctx.createPanner();
      pn.panningModel='HRTF';pn.distanceModel='exponential';pn.rolloffFactor=0.7;pn.refDistance=4;pn.maxDistance=60;
      const[px,py,pz]=prof.pos;
      if(pn.positionX){pn.positionX.value=px;pn.positionY.value=py;pn.positionZ.value=pz;}
      else try{pn.setPosition(px,py,pz);}catch(e){}
      pn.connect(mg);return pn;
    });
    startVis();return ctx;
  }

  // ── PLAY NOTE (v5 engine preserved + spectral flow offset) ───────────────────
  function playNote(pc,oct=4,vi=0,vel=0.36,dur=1.8){
    const ctx=ensureAudio();
    const prof=VOICE_PROFILES[Math.min(vi,7)];
    const gains=voiceGains[vi]||prof.gains;
    const subG=voiceSubGain[vi]??prof.subGain;
    // Offset: spelled12 as primary + spectral flow contribution
    let off=spelled12[pc]||0;
    const flowOff=flowX[pc]||0;
    off=off*0.7+flowOff*0.3; // blend spelled solve with spectral flow
    // Eigenmode shimmer
    if(eigenmodeOn){
      const domIdx=modeAmps.reduce((b,a,i)=>Math.abs(a)>Math.abs(modeAmps[b])?i:b,0);
      const domAmp=modeAmps[domIdx]||0;
      if(Math.abs(domAmp)>0.01){
        const t=ctx.currentTime,phase=(vi/8)*2*Math.PI;
        off+=EIGENMODES[domIdx].vec[pc]*domAmp*20*0.25*Math.sin(2*Math.PI*0.18*t+phase);
      }
    }
    if(eigenmodeOn&&eta>10){
      const t=ctx.currentTime,softVec=EIGENMODES[10].vec,phase2=(vi/8)*Math.PI;
      off+=softVec[pc]*0.8*(eta/237)*Math.sin(2*Math.PI*0.07*t+phase2);
    }
    const freq=toHz(pc,off,oct);
    const phrasePos=(beatRef.current%12)/12;
    const rho=Math.sin(Math.PI*phrasePos)**2;
    const vDepth=vibratoOn?prof.vibMaxHz*rho*Math.min(1.0,eta/80):0;
    const eg=ctx.createGain();
    const attackTime=0.02+0.02*rho;
    eg.gain.setValueAtTime(0.001,ctx.currentTime);
    eg.gain.linearRampToValueAtTime(vel*0.88,ctx.currentTime+attackTime);
    eg.gain.setValueAtTime(vel*0.82,ctx.currentTime+dur*0.70);
    eg.gain.exponentialRampToValueAtTime(0.001,ctx.currentTime+dur);
    if(spatialOn&&vi<8&&panners.current[vi])eg.connect(panners.current[vi]);
    else eg.connect(masterG.current);
    let lfoGain=null;
    if(vDepth>0.04){
      const lfo=ctx.createOscillator();lfo.type='sine';lfo.frequency.value=prof.vibRate;
      lfoGain=ctx.createGain();lfoGain.gain.value=vDepth;
      lfo.connect(lfoGain);lfo.start(ctx.currentTime+0.08);lfo.stop(ctx.currentTime+dur+0.1);
    }
    gains.forEach((g,hi)=>{
      if(g<0.008)return;
      const osc=ctx.createOscillator();
      osc.type=hi===0?'sine':hi===2?'triangle':'sine';
      osc.frequency.value=freq*(hi+1);
      osc.detune.value=prof.detuneHz*(hi%3===0?1:hi%3===1?-0.6:0.3)*15;
      if(lfoGain){const lm=ctx.createGain();lm.gain.value=(hi+1);lfoGain.connect(lm);lm.connect(osc.frequency);}
      const hg=ctx.createGain();hg.gain.value=g*0.52;
      osc.connect(hg);hg.connect(eg);osc.start(ctx.currentTime);osc.stop(ctx.currentTime+dur+0.06);
    });
    if(subG>0.02){
      const sub=ctx.createOscillator();sub.type='sine';sub.frequency.value=freq*0.5;
      const sg=ctx.createGain();sg.gain.value=subG*vel*0.6;
      sub.connect(sg);sg.connect(eg);sub.start(ctx.currentTime);sub.stop(ctx.currentTime+dur+0.06);
    }
    return freq;
  }

  // ── SPELLED KALMAN STEP (Advance 1 fully integrated) ────────────────────────
  const spelledStep=useCallback((strat)=>{
    const sp=computeSpelled(strat,J17);
    setSpelled17(sp.xf17);
    setSpelled12(sp.xf12);
    setEnhDiff(sp.enhDiff);
    setOpDecomp(sp.opDecomposition);
    setXSmooth(prev=>{
      const nx=prev.map((v,i)=>(1-ALPHA)*v+ALPHA*sp.xf12[i]);
      xSRef.current=nx;etaRef.current=sp.eta_sp;
      // Hex sector for room (Advance 5)
      const hexSect=strat.includes('hard')?'hard':strat.includes('soft')?'soft':'nat';
      hexSectorRef.current=hexSect;
      setEta(sp.eta_sp);
      setXnorm(+sp.xnorm.toFixed(3));
      setWrms(+sp.wRMS.toFixed(3));
      setVoiceX(vx=>vx.map((vxi,vi)=>{
        const vr=computeSpelled(VH8[vi],J17);
        return vxi.map((v,i)=>(1-ALPHA)*v+ALPHA*vr.xf12[i]);
      }));
      setBeatHist(h=>[...h.slice(-32),{eta:sp.eta_sp,strat}]);
      return nx;
    });
    // Advance 4: update spectral flow forcing
    // Project x* onto modal basis → fₘ = ⟨x*,vₘ⟩
    const f=EIGENMODES.map(m=>sp.xf12.reduce((s,v,i)=>s+v*m.vec[i],0));
    setFlowCoeffs(prev=>prev.map((a,mi)=>{
      const gamma=GAMMA[mi],fm=f[mi],sigma=EIGENMODES[mi].sigma;
      return a+(sigma*fm-gamma*a)*flowDt;
    }));
  },[J17,flowDt]);

  useEffect(()=>{spelledStep(strategy);},[strategy]);

  // ── ADVANCE 4: SPECTRAL FLOW ODE INTEGRATION ────────────────────────────────
  useEffect(()=>{
    if(!flowOn)return;
    const id=setInterval(()=>{
      const target=computeSpelled(strategy,J17).xf12;
      const f=EIGENMODES.map(m=>target.reduce((s,v,i)=>s+v*m.vec[i],0));
      setFlowCoeffs(prev=>{
        const next=prev.map((a,mi)=>{
          const gamma=GAMMA[mi],fm=f[mi],sigma=EIGENMODES[mi].sigma;
          // ODE: ȧₘ = −γₘ·aₘ + σₘ·fₘ
          return a+(sigma*fm-gamma*a)*flowDt;
        });
        // Soft-mode energy → room bloom (Advance 5)
        const sE=Math.abs(next[10]);
        setSoftEnergy(sE);softEnergyRef.current=sE;
        // Reconstruct x from modal coefficients
        const xRec=Array(N).fill(0);
        next.forEach((a,mi)=>EIGENMODES[mi].vec.forEach((v,i)=>{xRec[i]+=v*a;}));
        setFlowX(xRec);
        return next;
      });
    },50);
    return()=>clearInterval(id);
  },[flowOn,strategy,flowDt,J17]);

  // ── PERFORMANCE ───────────────────────────────────────────────────────────────
  useEffect(()=>{
    if(!perfMode){clearInterval(beatTmr.current);avRef.current=[];setActiveV([]);return;}
    ensureAudio();const ms=60000/bpm;
    beatTmr.current=setInterval(()=>{
      const b=(beatRef.current+1)%16;beatRef.current=b;setBeat(b);
      const evs=SCORE8.filter(e=>e.b===b);
      if(evs.length){
        spelledStep(PH_STRAT[evs[0].ph]||'hex_nat');
        evs.forEach(ev=>setTimeout(()=>playNote(ev.pc,ev.oct,ev.v,0.35,ev.dur*(ms/1000)*0.9),12));
        avRef.current=evs;setActiveV(evs);
      }
    },ms);
    return()=>clearInterval(beatTmr.current);
  },[perfMode,bpm,spatialOn,vibratoOn,eigenmodeOn]);

  // ── MIDI ─────────────────────────────────────────────────────────────────────
  async function initMIDI(){
    try{
      const acc=await navigator.requestMIDIAccess({sysex:false});
      acc.inputs.forEach(inp=>{inp.onmidimessage=msg=>{
        const[st,note,vel]=msg.data,cmd=st&0xf0,pc=note%N,oct=Math.floor(note/N)-1;
        if(cmd===0x90&&vel>0){
          const pcs=new Set([...midiNotes.keys()].map(n=>n%N));pcs.add(pc);
          let strat='hex_nat';
          if([...pcs].some(p=>MODE_FIN.has(p))&&[...pcs].some(p=>p===11))strat='cadence';
          else if([...pcs].every(p=>HEX_HARD.has(p)))strat='resurrect';
          else if([...pcs].some(p=>HEX_SOFT.has(p)&&!HEX_NAT.has(p)))strat='passion';
          ensureAudio();playNote(pc,oct,0,vel/127*.45,2.2);spelledStep(strat);
          setMidiNotes(m=>new Map([...m,[note,vel]]));
        } else if(cmd===0x80||(cmd===0x90&&vel===0)){
          setMidiNotes(m=>{const n=new Map(m);n.delete(note);return n;});
        }
      };});
      setMidiOn(true);
    }catch(e){alert('Web MIDI: Chrome/Edge + USB MIDI device required.');}
  }

  // ── VISUALIZATION ─────────────────────────────────────────────────────────────
  function startVis(){
    const tick=()=>{drawW();drawF();animFr.current=requestAnimationFrame(tick);};
    animFr.current=requestAnimationFrame(tick);
  }
  function drawW(){
    const cv=wCvs.current;if(!cv||!analyserW.current)return;
    const c=cv.getContext('2d'),W=cv.width,H=cv.height;
    const buf=new Float32Array(analyserW.current.fftSize);
    analyserW.current.getFloatTimeDomainData(buf);
    c.fillStyle='#0a0f1a';c.fillRect(0,0,W,H);
    const g=c.createLinearGradient(0,0,W,0);
    g.addColorStop(0,'#3b82f6');g.addColorStop(.5,'#c084fc');g.addColorStop(1,'#ef4444');
    c.strokeStyle=g;c.lineWidth=1.8;c.beginPath();
    buf.forEach((v,i)=>{const x=i*W/buf.length,y=H/2-v*(H/2.3);i===0?c.moveTo(x,y):c.lineTo(x,y);});
    c.stroke();
  }
  function drawF(){
    const cv=sCvs.current;if(!cv||!analyserF.current)return;
    const c=cv.getContext('2d'),W=cv.width,H=cv.height;
    const buf=new Uint8Array(analyserF.current.frequencyBinCount);
    analyserF.current.getByteFrequencyData(buf);
    c.fillStyle='#0a0f1a';c.fillRect(0,0,W,H);
    const bins=Math.min(buf.length,480);
    for(let i=0;i<bins;i++){
      const v=buf[i]/255,h=v*H;
      c.fillStyle=`hsla(${220+i/bins*140},80%,60%,${.25+v*.75})`;
      c.fillRect(i*W/bins,H-h,W/bins-1,h);
    }
    spelled12.forEach((off,pc)=>{
      if(Math.abs(off)<0.3)return;
      const f=toHz(pc,off,4),sr=audioCtx.current?.sampleRate||44100;
      const bin=Math.round(f/sr*analyserF.current.fftSize);
      if(bin<bins){c.strokeStyle='#fbbf2488';c.lineWidth=1.5;c.beginPath();c.moveTo(bin*W/bins,0);c.lineTo(bin*W/bins,H);c.stroke();}
    });
  }
  useEffect(()=>()=>{cancelAnimationFrame(animFr.current);clearInterval(beatTmr.current);},[]);

  // Church init
  useEffect(()=>{
    if(panel!=='church'||!churchCvs.current)return;
    const refs={xSmooth:xSRef,eta:etaRef,active:avRef,softEnergy:softEnergyRef,hexSector:hexSectorRef};
    return setupChurch(churchCvs.current,refs);
  },[panel]);

  const maxX=Math.max(.3,...spelled12.map(Math.abs));
  const T=({id,label})=>(
    <button onClick={()=>setPanel(id)} style={{padding:'4px 9px',borderRadius:'5px',border:'none',cursor:'pointer',
      fontSize:'10px',fontWeight:'bold',background:panel===id?'#7c3aed':'#1e293b',
      color:panel===id?'#fff':'#64748b',boxShadow:panel===id?'0 0 8px #7c3aed55':'none',transition:'all .15s'}}>
      {label}
    </button>
  );

  // ── JSX ───────────────────────────────────────────────────────────────────────
  return(
    <div style={{background:'#0a0f1a',color:'#e2e8f0',fontFamily:'monospace',minHeight:'100vh',padding:'12px'}}>

      {/* HEADER */}
      <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',borderBottom:'1px solid #1e293b',paddingBottom:'8px',marginBottom:'10px'}}>
        <div>
          <span style={{fontSize:'14px',fontWeight:'bold',color:'#c084fc',letterSpacing:'.08em'}}>DYLETSKY v6</span>
          <span style={{fontSize:'9px',color:'#334155',marginLeft:'10px'}}>
            Spelled Semantics · Operator Algebra · Sparse Inversion · Spectral Flow · Algebraic Room · Comparative Operators
          </span>
        </div>
        <div style={{display:'flex',gap:'5px',alignItems:'center',flexWrap:'wrap'}}>
          {[['⊕ Spatial',spatialOn,setSpatialOn,'#3b82f6'],['〰 Vibrato',vibratoOn,setVibratoOn,'#c084fc'],['∿ Shimmer',eigenmodeOn,setEigenmodeOn,'#22c55e']].map(([label,on,setOn,c])=>(
            <button key={label} onClick={()=>{ensureAudio();setOn(p=>!p);}}
              style={{padding:'3px 9px',borderRadius:'5px',border:`1px solid ${on?c:'#334155'}`,cursor:'pointer',fontSize:'9px',fontWeight:'bold',background:on?c+'22':'#0f172a',color:on?c:'#475569'}}>
              {on?'✓':''} {label}
            </button>
          ))}
          <button onClick={initMIDI}
            style={{padding:'4px 9px',borderRadius:'5px',border:'none',cursor:'pointer',fontSize:'9px',fontWeight:'bold',background:midiOn?'#16a34a':'#1e293b',color:midiOn?'#fff':'#94a3b8',border:'1px solid '+(midiOn?'#16a34a':'#334155')}}>
            {midiOn?'🎹 MIDI ✓':'🎹 MIDI'}
          </button>
          <button onClick={()=>{ensureAudio();setPerfMode(p=>!p);}}
            style={{padding:'4px 14px',borderRadius:'5px',border:'none',cursor:'pointer',fontSize:'10px',fontWeight:'bold',background:perfMode?'#dc2626':'#7c3aed',color:'#fff'}}>
            {perfMode?'⏹ STOP':'▶ RESURRECT'}
          </button>
          {perfMode&&<><input type="range" min="40" max="108" value={bpm} onChange={e=>setBpm(+e.target.value)} style={{width:'48px'}}/><span style={{color:'#f59e0b',fontSize:'10px'}}>{bpm}♩</span></>}
        </div>
      </div>

      {/* INVARIANTS */}
      <div style={{display:'grid',gridTemplateColumns:'repeat(8,1fr)',gap:'4px',marginBottom:'10px'}}>
        {[['rank(J₁₇)','16','#22c55e'],['det','509M','#3b82f6'],['σ_min','1/√2','#f59e0b'],
          ['η_sp',eta.toFixed(1),eta<.1?'#ef4444':'#a78bfa'],['‖x*‖',xnorm+'¢','#34d399'],
          ['wRMS',wRMS+'¢','#fb923c'],
          ['flowE',(softEnergy).toFixed(2),softEnergy>.3?'#c084fc':'#334155'],
          ['ops',opDecomp.length||'—','#06b6d4'],
        ].map(([l,v,c])=>(
          <div key={l} style={{background:'#1e293b',borderRadius:'6px',padding:'5px',border:`1px solid ${c}22`}}>
            <div style={{fontSize:'7px',color:'#475569'}}>{l}</div>
            <div style={{fontSize:'12px',fontWeight:'bold',color:c,lineHeight:1.1}}>{v}</div>
          </div>))}
      </div>

      {/* TABS */}
      <div style={{display:'flex',gap:'4px',marginBottom:'10px',flexWrap:'wrap'}}>
        <T id="main"    label="🎼 Main"/>
        <T id="church"  label="⛪ Algebraic Room"/>
        <T id="spelled" label="𝄞 Spelled Semantics"/>
        <T id="algebra" label="⊗ Operator Algebra"/>
        <T id="flow"    label="∂ Spectral Flow"/>
        <T id="compare" label="⚖ Comparators"/>
        <T id="invert"  label="🔬 Sparse Inversion"/>
        <T id="timbre"  label="🎵 Timbre"/>
        <T id="waves"   label="〰 Waves"/>
        <T id="perf"    label="🕍 Performance"/>
      </div>

      {/* ══ MAIN ══ */}
      {panel==='main'&&(
        <div style={{display:'grid',gridTemplateColumns:'3fr 2fr',gap:'10px'}}>
          <div style={{background:'#1e293b',borderRadius:'8px',padding:'10px'}}>
            <div style={{fontSize:'9px',color:'#64748b',marginBottom:'6px',fontWeight:'bold'}}>GRAMMATIKA STRATEGY</div>
            <div style={{display:'flex',flexWrap:'wrap',gap:'3px',marginBottom:'10px'}}>
              {Object.keys(STRAT_ALGEBRA).map(s=>(
                <button key={s} onClick={()=>setStrategy(s)}
                  style={{padding:'2px 7px',borderRadius:'3px',border:'none',cursor:'pointer',fontSize:'9px',background:strategy===s?(SC[s]||cc):'#334155',color:strategy===s?'#000':'#94a3b8',fontWeight:strategy===s?'bold':'normal'}}>
                  {s}
                </button>
              ))}
            </div>
            {/* Operator decomposition display */}
            {opDecomp.length>0&&(
              <div style={{background:'#0f172a',borderRadius:'5px',padding:'6px',marginBottom:'8px',fontSize:'8px'}}>
                <span style={{color:'#475569'}}>Operator algebra: </span>
                {opDecomp.map(({op,p},i)=>(
                  <span key={i} style={{color:['#3b82f6','#f59e0b','#10b981','#c084fc','#ef4444'][['KEY','CAD','HEX','CON','VL'].indexOf(op)],fontWeight:'bold',marginRight:'4px'}}>
                    {op}(w={p.w||p.finals||p.sector||p.fams||'?'})
                    {i<opDecomp.length-1?' × ':''}
                  </span>
                ))}
              </div>
            )}
            {/* Offset bars — spelled 12-class projection */}
            <div style={{display:'grid',gridTemplateColumns:'repeat(12,1fr)',gap:'2px',height:'90px',alignItems:'flex-end',marginBottom:'8px'}}>
              {spelled12.map((v,i)=>{
                const isAct=activeV.some(a=>a.pc===i);
                const h=Math.max(2,Math.abs(v)/maxX*80);
                const c=HEX_HARD.has(i)&&!HEX_NAT.has(i)?'#f59e0b':HEX_SOFT.has(i)&&!HEX_NAT.has(i)?'#10b981':HEX_NAT.has(i)?'#3b82f6':'#475569';
                return(
                  <div key={i} style={{display:'flex',flexDirection:'column',alignItems:'center'}}>
                    <div style={{fontSize:'6px',color:'#475569'}}>{v>=0?'+':''}{v.toFixed(1)}</div>
                    <div style={{width:'100%',height:`${h}px`,borderRadius:'2px 2px 0 0',background:isAct?'#fbbf24':c,transition:'height .12s',boxShadow:isAct?'0 0 6px #fbbf24':'none'}}/>
                    <div style={{fontSize:'6px',color:isAct?'#fbbf24':'#475569',marginTop:'2px'}}>{PC[i]}</div>
                  </div>
                );
              })}
            </div>
            {/* Flow overlay */}
            {flowOn&&(
              <div style={{display:'grid',gridTemplateColumns:'repeat(12,1fr)',gap:'2px',height:'30px',alignItems:'flex-end',marginBottom:'6px'}}>
                {flowX.map((v,i)=>{
                  const h=Math.max(1,Math.abs(v)/Math.max(.1,...flowX.map(Math.abs))*26);
                  return(<div key={i} style={{width:'100%',height:`${h}px`,borderRadius:'1px 1px 0 0',background:'#c084fc',opacity:.6}}/>);
                })}
              </div>
            )}
            {flowOn&&<div style={{fontSize:'7px',color:'#c084fc',marginBottom:'8px'}}>↑ Spectral flow x* (purple overlay)</div>}
            {/* Chords */}
            <div style={{display:'flex',gap:'5px',flexWrap:'wrap'}}>
              {[['G maj',[7,11,2],4,'#ef4444'],['E min',[4,7,11],4,'#8b5cf6'],['D maj',[2,6,9],4,'#3b82f6'],
                ['C maj',[0,4,7],4,'#22c55e'],['A min',[9,0,4],4,'#f59e0b'],['F maj',[5,9,0],4,'#6366f1']].map(([l,pcs,oct,c])=>(
                <button key={l} onClick={()=>{ensureAudio();pcs.forEach((pc,i)=>setTimeout(()=>playNote(pc,oct,i%8,.4,2.5),i*20));}}
                  style={{padding:'3px 8px',borderRadius:'4px',border:`1px solid ${c}55`,cursor:'pointer',background:'#0f172a',color:c,fontSize:'9px',fontWeight:'bold'}}>
                  ▶ {l}
                </button>
              ))}
            </div>
          </div>
          <div style={{display:'flex',flexDirection:'column',gap:'8px'}}>
            <div style={{background:'#1e293b',borderRadius:'8px',padding:'10px'}}>
              <div style={{fontSize:'9px',color:'#64748b',fontWeight:'bold',marginBottom:'4px'}}>KALMAN · ETA HISTORY</div>
              <div style={{height:'36px',display:'flex',gap:'1px',alignItems:'flex-end'}}>
                {beatHist.slice(-32).map((h,i)=><div key={i} style={{flex:1,height:`${Math.min(34,h.eta/237*34)}px`,minHeight:'2px',borderRadius:'1px 1px 0 0',background:SC[h.strat]||cc,opacity:.7}}/>)}
              </div>
            </div>
            <div style={{background:'#1e293b',borderRadius:'8px',padding:'10px',flex:1}}>
              <div style={{fontSize:'9px',color:'#64748b',fontWeight:'bold',marginBottom:'6px'}}>VOICES (click to solo)</div>
              <div style={{display:'grid',gridTemplateColumns:'repeat(4,1fr)',gap:'4px'}}>
                {VOICE_PROFILES.map((prof,vi)=>{
                  const isAct=activeV.some(a=>a.v===vi);
                  const vx=voiceX[vi]||Array(N).fill(0);
                  return(
                    <div key={prof.name} onClick={()=>{ensureAudio();[0,4,7].forEach((pc,j)=>setTimeout(()=>playNote(pc,3+vi%2,vi,.4,2),j*30));}}
                      style={{background:'#0f172a',borderRadius:'5px',padding:'5px',cursor:'pointer',border:`1px solid ${isAct?prof.color:'#1e293b'}`,boxShadow:isAct?`0 0 8px ${prof.color}55`:'none',transition:'all .15s'}}>
                      <div style={{color:prof.color,fontWeight:'bold',fontSize:'9px'}}>{prof.name}</div>
                      <div style={{fontSize:'7px',color:'#475569'}}>{prof.hex.replace('hex_','')}</div>
                      <div style={{display:'flex',gap:'1px',height:'18px',alignItems:'flex-end',marginTop:'3px'}}>
                        {vx.map((v,i)=>{const hex={hex_hard:HEX_HARD,hex_nat:HEX_NAT,hex_soft:HEX_SOFT}[prof.hex]||HEX_NAT;return(
                          <div key={i} style={{flex:1,height:`${Math.max(1,Math.abs(v)/Math.max(.1,...vx.map(Math.abs))*16)}px`,background:hex.has(i)?prof.color:'#334155',opacity:hex.has(i)?.8:.25,borderRadius:'1px'}}/>);})}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ══ ALGEBRAIC ROOM ══ */}
      {panel==='church'&&(
        <div>
          <div style={{background:'#1e293b',borderRadius:'8px',padding:'10px',marginBottom:'8px'}}>
            <div style={{display:'flex',justifyContent:'space-between',marginBottom:'6px'}}>
              <div>
                <div style={{fontSize:'11px',color:'#f59e0b',fontWeight:'bold'}}>⛪ ALGEBRAIC ROOM — operator invariants drive acoustics</div>
                <div style={{fontSize:'8px',color:'#475569',marginTop:'2px'}}>η → incense diffusion · soft-mode energy → bloom radius · hex sector → icon color · modal finals → gravity</div>
              </div>
              <div style={{display:'flex',gap:'4px',flexWrap:'wrap'}}>
                {Object.keys(STRAT_ALGEBRA).slice(0,9).map(s=>(
                  <button key={s} onClick={()=>setStrategy(s)}
                    style={{padding:'2px 5px',borderRadius:'3px',border:'none',cursor:'pointer',fontSize:'8px',fontWeight:strategy===s?'bold':'normal',background:strategy===s?(SC[s]||cc):'#334155',color:strategy===s?'#000':'#94a3b8'}}>
                    {s.slice(0,7)}
                  </button>
                ))}
              </div>
            </div>
            <canvas ref={churchCvs} width={700} height={400}
              style={{width:'100%',height:'400px',borderRadius:'8px',display:'block',background:'#040508',cursor:'grab'}}/>
            <div style={{display:'flex',gap:'8px',marginTop:'6px',fontSize:'8px',flexWrap:'wrap'}}>
              <span style={{color:'#f59e0b'}}>η={eta.toFixed(1)} → diffusion×{(1+eta/237*3).toFixed(2)}</span>
              <span style={{color:'#c084fc'}}>soft-mode E={softEnergy.toFixed(3)} → bloom×{(1+softEnergy*2).toFixed(2)}</span>
              <span style={{color:SC[strategy]||cc}}>hex sector: {strategy.includes('hard')?'hard':strategy.includes('soft')?'soft':'natural'}</span>
            </div>
          </div>
        </div>
      )}

      {/* ══ SPELLED SEMANTICS ══ */}
      {panel==='spelled'&&(
        <div style={{background:'#1e293b',borderRadius:'8px',padding:'14px'}}>
          <div style={{fontSize:'11px',color:'#f59e0b',fontWeight:'bold',marginBottom:'4px'}}>𝄞 ADVANCE 1: FULLY SPELLED SEMANTICS</div>
          <div style={{fontSize:'8px',color:'#475569',marginBottom:'10px'}}>
            Weights, targets, and forcing invariant all computed on spelled labels. The target b is spelled-label-aware (sharp-side M3 ≠ flat-side M3). Enharmonics are genuinely distinct — G# and Ab receive different offsets. The 12-class playback projection P:ℝ¹⁷→ℝ¹² is used only for audio, not for the solve.
          </div>
          {/* 17-note lattice */}
          <svg width="100%" viewBox="0 0 570 115" style={{display:'block',marginBottom:'10px'}}>
            {SP17.slice(0,-1).map((_,i)=>{
              const a=SP17[i],b2=SP17[i+1];
              const pca=SP17_PC[a],pcb=SP17_PC[b2];
              const ya=SP17_HARD.has(a)?22:SP17_SOFT.has(a)&&!SP17_NAT.has(a)?65:43;
              const yb=SP17_HARD.has(b2)?22:SP17_SOFT.has(b2)&&!SP17_NAT.has(b2)?65:43;
              return<line key={i} x1={14+i*33+13} y1={ya} x2={14+(i+1)*33+13} y2={yb} stroke="#1e293b" strokeWidth="1"/>;
            })}
            {SP17.map((note,i)=>{
              const pc=SP17_PC[note];
              const off17=spelled17[i]||0;
              const off12=spelled12[pc];
              const cx=14+i*33+13;
              const isHard=SP17_HARD.has(note)&&!SP17_NAT.has(note);
              const isSoft=SP17_SOFT.has(note)&&!SP17_NAT.has(note);
              const cy=isHard?22:isSoft?65:43;
              const c=isHard?'#f59e0b':isSoft?'#10b981':'#3b82f6';
              const isFin=SP17_FIN.has(note);
              return(
                <g key={note} style={{cursor:'pointer'}} onClick={()=>{ensureAudio();playNote(pc,4,0,.5,1.8);}}>
                  <circle cx={cx} cy={cy} r={13} fill={c} opacity={.15}/>
                  <circle cx={cx} cy={cy} r={13} fill="none" stroke={c} strokeWidth={isFin?2.5:1}/>
                  {Math.abs(off17)>.2&&(
                    <rect x={cx-4} y={off17>=0?cy-Math.abs(off17)/15*10:cy} width={8}
                      height={Math.max(1,Math.abs(off17)/15*10)} rx={2} fill={off17>=0?c:'#ef4444'} opacity={.65}/>
                  )}
                  <text x={cx} y={cy+4} textAnchor="middle" fontSize={note.length>2?7:8} fill="#e2e8f0" fontWeight={isFin?'bold':'normal'}>{note}</text>
                  <text x={cx} y={cy+23} textAnchor="middle" fontSize={6.5} fill={c}>{(off17>=0?'+':'')+off17.toFixed(1)}</text>
                </g>
              );
            })}
            <text x={1} y={26} fontSize={7.5} fill="#f59e0b">Hard</text>
            <text x={1} y={47} fontSize={7.5} fill="#3b82f6">Nat</text>
            <text x={1} y={69} fontSize={7.5} fill="#10b981">Soft</text>
          </svg>
          {/* Enharmonic distinctions */}
          <div style={{marginBottom:'10px'}}>
            <div style={{fontSize:'9px',color:'#94a3b8',fontWeight:'bold',marginBottom:'6px'}}>Enharmonic distinctions (G# ≠ Ab, etc.) — spelled forcing invariant η_sp={eta.toFixed(2)}</div>
            <div style={{display:'grid',gridTemplateColumns:'repeat(5,1fr)',gap:'6px'}}>
              {Object.entries(enhDiff).map(([pair,diff])=>(
                <div key={pair} style={{background:'#0f172a',borderRadius:'6px',padding:'7px',textAlign:'center',border:`1px solid ${Math.abs(diff)>.05?'#f59e0b':'#1e293b'}`}}>
                  <div style={{fontSize:'10px',color:'#c084fc',fontWeight:'bold'}}>{pair}</div>
                  <div style={{fontSize:'11px',color:diff>0?'#f59e0b':diff<0?'#10b981':'#475569',fontWeight:'bold',marginTop:'3px'}}>
                    {diff>=0?'+':''}{diff.toFixed(3)}¢
                  </div>
                  <div style={{fontSize:'7px',color:'#334155',marginTop:'2px'}}>
                    {Math.abs(diff)>.05?'distinct':'≈ equal'}
                  </div>
                </div>
              ))}
            </div>
          </div>
          <div style={{background:'#0f172a',borderRadius:'6px',padding:'8px',fontSize:'8px',color:'#475569'}}>
            <span style={{color:'#f59e0b',fontWeight:'bold'}}>Spelled theorem: </span>
            The 17-note Jacobian J_sp∈ℝ^(37×17) has rank=16. Because G# and Ab are distinct columns, a family-constant b gives ‖J_sp&#x1D40;Wb‖≠0 automatically — the spelling itself partially lifts the isotropy obstruction. The spelled target b_sp (sharp-side M3 adjusted −0.8¢, flat-side +0.8¢) makes the forcing genuinely enharmonic: G# arrives sharper than Ab for the same interval family.
          </div>
        </div>
      )}

      {/* ══ OPERATOR ALGEBRA ══ */}
      {panel==='algebra'&&(()=>{
        const PRIM_COLORS={KEY:'#3b82f6',CAD:'#ef4444',HEX:'#f59e0b',CON:'#22c55e',VL:'#c084fc'};
        const PRIM_DESC={
          KEY:'Key-field: upweights intervals whose tones are both inside the active key collection',
          CAD:'Cadential: upweights intervals resolving to modal finals (strong directional pull)',
          HEX:'Hexachord sector: distinguishes hard-hex sharps from soft-hex flats — spelled-label-aware',
          CON:'Consonance priority: upweights intervals by family (P5, M3, m3 selectable)',
          VL:'Voice-leading: privileges short intervals (m3 motion) as structural connectors',
        };
        // Compute W matrix decomposition for current strategy
        const allStrats=Object.keys(STRAT_ALGEBRA);
        const etaByStrat=allStrats.map(s=>{try{return{s,eta:computeSpelled(s,J17).eta_sp};}catch(e){return{s,eta:0};}});
        return(
          <div style={{background:'#1e293b',borderRadius:'8px',padding:'14px'}}>
            <div style={{fontSize:'11px',color:'#06b6d4',fontWeight:'bold',marginBottom:'8px'}}>⊗ ADVANCE 2: COMPOSITIONAL WEIGHT ALGEBRA</div>
            <div style={{fontSize:'9px',color:'#64748b',marginBottom:'10px'}}>
              Every strategy is a product of primitive symmetry-breaking operators. Style = KEY × CAD × HEX × CON × VL with independent parameters. This separates operator semantics from style semantics — allows asking which primitive is doing the algebraic work.
            </div>
            {/* Primitive operators */}
            <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:'10px',marginBottom:'12px'}}>
              <div>
                <div style={{fontSize:'9px',color:'#94a3b8',fontWeight:'bold',marginBottom:'6px'}}>Primitive operators</div>
                {Object.entries(PRIM_DESC).map(([op,desc])=>(
                  <div key={op} style={{background:'#0f172a',borderRadius:'5px',padding:'7px',marginBottom:'4px',borderLeft:`3px solid ${PRIM_COLORS[op]}`}}>
                    <div style={{fontSize:'9px',color:PRIM_COLORS[op],fontWeight:'bold',marginBottom:'2px'}}>{op}</div>
                    <div style={{fontSize:'8px',color:'#475569'}}>{desc}</div>
                  </div>
                ))}
              </div>
              <div>
                <div style={{fontSize:'9px',color:'#94a3b8',fontWeight:'bold',marginBottom:'6px'}}>Strategy decompositions</div>
                {Object.entries(STRAT_ALGEBRA).map(([s,ops])=>(
                  <div key={s} style={{background:'#0f172a',borderRadius:'5px',padding:'6px',marginBottom:'4px',border:`1px solid ${strategy===s?(SC[s]||'#475569'):'#1e293b'}`}}>
                    <div style={{display:'flex',justifyContent:'space-between',marginBottom:'3px'}}>
                      <button onClick={()=>setStrategy(s)} style={{background:'none',border:'none',cursor:'pointer',color:SC[s]||'#64748b',fontWeight:'bold',fontSize:'9px',padding:0}}>{s}</button>
                      <span style={{fontSize:'8px',color:'#475569'}}>η={etaByStrat.find(e=>e.s===s)?.eta.toFixed(1)||'—'}</span>
                    </div>
                    {ops.length===0
                      ?<span style={{fontSize:'8px',color:'#334155'}}>∅ (identity — ET)</span>
                      :<div style={{display:'flex',gap:'3px',flexWrap:'wrap'}}>
                        {ops.map(({op,p},i)=>(
                          <span key={i} style={{fontSize:'7px',background:PRIM_COLORS[op]+'22',color:PRIM_COLORS[op],padding:'1px 4px',borderRadius:'3px',fontWeight:'bold'}}>
                            {op}
                          </span>))}
                      </div>}
                  </div>
                ))}
              </div>
            </div>
            {/* η comparison bar */}
            <div style={{background:'#0f172a',borderRadius:'6px',padding:'10px'}}>
              <div style={{fontSize:'9px',color:'#94a3b8',fontWeight:'bold',marginBottom:'6px'}}>Forcing invariant η_sp by strategy — operator strength comparison</div>
              {etaByStrat.sort((a,b)=>b.eta-a.eta).map(({s,eta:e})=>(
                <div key={s} style={{display:'flex',gap:'6px',alignItems:'center',marginBottom:'3px'}}>
                  <div style={{minWidth:'76px',fontSize:'8px',color:SC[s]||'#475569',fontWeight:s===strategy?'bold':'normal'}}>{s}</div>
                  <div style={{flex:1,height:'10px',background:'#1e293b',borderRadius:'5px',overflow:'hidden'}}>
                    <div style={{height:'100%',width:`${e/250*100}%`,background:SC[s]||'#475569',borderRadius:'5px',transition:'width .3s'}}/>
                  </div>
                  <div style={{minWidth:'36px',fontSize:'8px',color:SC[s]||'#475569',textAlign:'right',fontWeight:'bold'}}>{e.toFixed(1)}</div>
                  {/* Operator badge count */}
                  <div style={{fontSize:'7px',color:'#334155',minWidth:'20px'}}>{STRAT_ALGEBRA[s].length}op</div>
                </div>
              ))}
              <div style={{marginTop:'8px',fontSize:'8px',color:'#475569'}}>
                ET=0 confirms isotropy obstruction (η_sp=0 for identity operator). Each added primitive operator increases η. The resurrect strategy (HEX×CAD×CON) achieves the highest η by combining three independent symmetry-breaking dimensions.
              </div>
            </div>
          </div>
        );
      })()}

      {/* ══ SPECTRAL FLOW ══ */}
      {panel==='flow'&&(()=>{
        const modeColors=['#ef4444','#f59e0b','#fbbf24','#84cc16','#22c55e','#06b6d4','#3b82f6','#6366f1','#8b5cf6','#a855f7','#22c55e'];
        const maxCoeff=Math.max(0.01,...flowCoeffs.map(Math.abs));
        const flowNorm=Math.sqrt(flowX.reduce((s,v)=>s+v**2,0));
        return(
          <div style={{background:'#1e293b',borderRadius:'8px',padding:'14px'}}>
            <div style={{fontSize:'11px',color:'#c084fc',fontWeight:'bold',marginBottom:'6px'}}>∂ ADVANCE 4: SPECTRAL FLOW LAW — Modal ODE in ℝ¹¹</div>
            <div style={{fontSize:'9px',color:'#64748b',marginBottom:'10px'}}>
              ȧₘ = −γₘ·aₘ + σₘ·fₘ(context) where fₘ=⟨x*,vₘ⟩ is the modal forcing and γₘ∝σₘ² is the decay rate. Stiff modes (σ≈2.955) decay and respond fast. The soft mode near σ=1/√2 is a dynamical carrier of stylistic drift — it persists longer and responds slowly. x*(t) = Σ aₘ(t)·vₘ.
            </div>
            <div style={{display:'flex',justifyContent:'space-between',marginBottom:'10px',alignItems:'center',flexWrap:'wrap',gap:'6px'}}>
              <div style={{display:'flex',gap:'8px',alignItems:'center'}}>
                <button onClick={()=>setFlowOn(p=>!p)}
                  style={{padding:'5px 16px',borderRadius:'6px',border:'none',cursor:'pointer',fontSize:'10px',fontWeight:'bold',background:flowOn?'#dc2626':'#c084fc',color:flowOn?'#fff':'#000'}}>
                  {flowOn?'⏹ STOP FLOW':'▶ START FLOW'}
                </button>
                <button onClick={()=>{ensureAudio();[7,11,2,5].forEach((pc,i)=>setTimeout(()=>{
                  const ctx=audioCtx.current;if(!ctx)return;
                  const off=flowX[pc]||0;const freq=toHz(pc,off,4);
                  const eg=ctx.createGain();eg.gain.setValueAtTime(.35,ctx.currentTime);eg.gain.exponentialRampToValueAtTime(.001,ctx.currentTime+2.5);eg.connect(masterG.current);
                  [1,2,3].forEach(h=>{const o=ctx.createOscillator();o.frequency.value=freq*h;const hg=ctx.createGain();hg.gain.value=[1,.5,.25][h-1]*.45;o.connect(hg);hg.connect(eg);o.start();o.stop(ctx.currentTime+2.6);});
                },i*40));}} style={{padding:'4px 10px',borderRadius:'5px',border:'none',cursor:'pointer',fontSize:'9px',background:'#334155',color:'#94a3b8'}}>▶ Hear flow x*</button>
                <button onClick={()=>setFlowCoeffs(Array(11).fill(0))}
                  style={{padding:'4px 10px',borderRadius:'5px',border:'none',cursor:'pointer',fontSize:'9px',background:'#334155',color:'#94a3b8'}}>↺ Reset</button>
              </div>
              <div style={{display:'flex',gap:'6px',alignItems:'center'}}>
                <span style={{fontSize:'8px',color:'#64748b'}}>dt =</span>
                <input type="range" min="1" max="30" value={Math.round(flowDt*100)} onChange={e=>setFlowDt(+e.target.value/100)} style={{width:'70px'}}/>
                <span style={{fontSize:'9px',color:'#c084fc',fontWeight:'bold'}}>{flowDt.toFixed(2)}</span>
              </div>
            </div>
            {/* Modal coefficient bars with decay rates */}
            <div style={{display:'grid',gap:'4px',marginBottom:'10px'}}>
              {EIGENMODES.map((m,mi)=>{
                const a=flowCoeffs[mi],gamma=GAMMA[mi],fm=spelled12.reduce((s,v,i)=>s+v*m.vec[i],0);
                const barW=Math.abs(a)/maxCoeff*100;
                const isSoft=mi===10;
                return(
                  <div key={mi} style={{background:'#0f172a',borderRadius:'4px',padding:'5px 8px',border:isSoft?'1px solid #c084fc33':'1px solid #1e293b'}}>
                    <div style={{display:'flex',gap:'8px',alignItems:'center'}}>
                      <div style={{minWidth:'80px'}}>
                        <div style={{fontSize:'8px',color:modeColors[mi],fontWeight:'bold'}}>m{mi+1} σ={m.sigma.toFixed(3)}{isSoft?' ★':''}</div>
                        <div style={{fontSize:'7px',color:'#334155'}}>γ={gamma.toFixed(3)} · f={fm.toFixed(2)}</div>
                      </div>
                      <div style={{flex:1,height:'12px',background:'#1e293b',borderRadius:'6px',overflow:'hidden',position:'relative'}}>
                        <div style={{position:'absolute',left:a>=0?'50%':'auto',right:a<0?'50%':'auto',width:`${barW/2}%`,height:'100%',background:modeColors[mi],opacity:.85}}/>
                        <div style={{position:'absolute',left:'50%',top:0,bottom:0,width:'1px',background:'#334155'}}/>
                      </div>
                      <div style={{minWidth:'48px',fontSize:'9px',color:modeColors[mi],textAlign:'right',fontWeight:'bold'}}>{a>=0?'+':''}{a.toFixed(2)}¢</div>
                      <div style={{minWidth:'48px',fontSize:'8px',color:'#475569',textAlign:'right'}}>τ={isSoft?'long':'short'}</div>
                    </div>
                  </div>
                );
              })}
            </div>
            <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:'10px'}}>
              <div>
                <div style={{fontSize:'9px',color:'#64748b',fontWeight:'bold',marginBottom:'4px'}}>Flow x*(t) vs Spelled x* (¢)</div>
                <div style={{display:'grid',gridTemplateColumns:'repeat(12,1fr)',gap:'2px',height:'60px',alignItems:'flex-end'}}>
                  {flowX.map((v,i)=>{
                    const sp=spelled12[i];const mp=Math.max(.1,flowNorm,Math.sqrt(spelled12.reduce((s,v)=>s+v**2,0)));
                    return(<div key={i} style={{display:'flex',flexDirection:'column',alignItems:'center',gap:'1px'}}>
                      <div style={{width:'45%',height:`${Math.max(1,Math.abs(v)/mp*26)}px`,background:'#c084fc',borderRadius:'1px'}}/>
                      <div style={{width:'45%',height:`${Math.max(1,Math.abs(sp)/mp*26)}px`,background:'#f59e0b',borderRadius:'1px'}}/>
                      <div style={{fontSize:'6px',color:'#475569'}}>{PC[i]}</div>
                    </div>);
                  })}
                </div>
                <div style={{display:'flex',gap:'8px',fontSize:'7px',marginTop:'3px'}}>
                  <span><span style={{color:'#c084fc'}}>■</span> Flow x*(t)</span>
                  <span><span style={{color:'#f59e0b'}}>■</span> Spelled x*</span>
                </div>
              </div>
              <div style={{background:'#0f172a',borderRadius:'6px',padding:'8px',fontSize:'8px',color:'#475569'}}>
                <div style={{color:'#c084fc',fontWeight:'bold',marginBottom:'4px'}}>Soft mode as stylistic drift carrier</div>
                <div style={{lineHeight:1.65}}>
                  Mode 11 (σ=0.707≈1/√2) has the smallest decay rate γ=0.08·σ²/σ_max²≈0.003. It therefore persists longest between context changes — acting as a memory of prior stylistic state. When context switches (e.g., jubilate→cadence), stiff modes snap to the new x* in ~6 steps; the soft mode drifts gradually, creating audible stylistic inertia. This is the 1/√2 geometry made dynamically perceptible.
                </div>
                <div style={{marginTop:'6px',display:'flex',justifyContent:'space-between'}}>
                  <span>Soft-mode E:</span>
                  <span style={{color:'#c084fc',fontWeight:'bold'}}>{softEnergy.toFixed(4)}</span>
                </div>
                <div style={{display:'flex',justifyContent:'space-between'}}>
                  <span>‖flow x*‖:</span>
                  <span style={{color:'#f59e0b',fontWeight:'bold'}}>{flowNorm.toFixed(3)}¢</span>
                </div>
              </div>
            </div>
          </div>
        );
      })()}

      {/* ══ COMPARATIVE OPERATORS ══ */}
      {panel==='compare'&&(()=>{
        const ALL_COMP=['resurrect','tonal','chant','guidetone','triad','modal','liturgy','passion'];
        const results=ALL_COMP.map(s=>{
          try{const r=computeSpelled(s,J17);return{s,eta:r.eta_sp,xnorm:r.xnorm,wRMS:r.wRMS,xf12:r.xf12,ops:STRAT_ALGEBRA[s].length};}
          catch(e){return{s,eta:0,xnorm:0,wRMS:0,xf12:Array(N).fill(0),ops:0};}
        });
        // Template distances
        const dists=[];
        for(let i=0;i<results.length;i++)for(let j=i+1;j<results.length;j++){
          const d=Math.sqrt(results[i].xf12.reduce((s,v,k)=>(s+(v-results[j].xf12[k])**2),0));
          dists.push({a:results[i].s,b:results[j].s,d});
        }
        dists.sort((a,b)=>b.d-a.d);
        return(
          <div style={{background:'#1e293b',borderRadius:'8px',padding:'14px'}}>
            <div style={{fontSize:'11px',color:'#fb923c',fontWeight:'bold',marginBottom:'8px'}}>⚖ ADVANCE 6: COMPARATIVE FORMAL OPERATORS</div>
            <div style={{fontSize:'9px',color:'#64748b',marginBottom:'10px'}}>
              Each operator receives the same invariant dashboard — η, ‖x*‖, wRMS, operator count. Is Dyletsky special because of history, sonic effect, or algebraic near-optimality? The comparison tells.
            </div>
            <div style={{display:'grid',gridTemplateColumns:'repeat(4,1fr)',gap:'6px',marginBottom:'12px'}}>
              {results.map(({s,eta:e,xnorm:xn,wRMS:w,xf12,ops})=>{
                const c=SC[s]||'#475569';const mx=Math.max(.1,...xf12.map(Math.abs));
                const isActive=strategy===s;
                return(
                  <div key={s} onClick={()=>{setStrategy(s);spelledStep(s);}}
                    style={{background:'#0f172a',borderRadius:'8px',padding:'9px',cursor:'pointer',border:`2px solid ${isActive?c:c+'44'}`,boxShadow:isActive?`0 0 12px ${c}55`:'none'}}>
                    <div style={{color:c,fontWeight:'bold',fontSize:'10px',marginBottom:'5px'}}>{s}</div>
                    {[['η_sp',e.toFixed(1),c],['‖x*‖',xn.toFixed(2)+'¢','#34d399'],['wRMS',w.toFixed(2)+'¢','#fb923c'],['ops',ops,'#06b6d4']].map(([l,v,vc])=>(
                      <div key={l} style={{display:'flex',justifyContent:'space-between',fontSize:'8px',marginBottom:'2px'}}>
                        <span style={{color:'#475569'}}>{l}</span>
                        <span style={{color:vc,fontWeight:'bold'}}>{v}</span>
                      </div>))}
                    {/* Mini sparkline */}
                    <div style={{display:'flex',gap:'1px',height:'20px',alignItems:'flex-end',marginTop:'5px'}}>
                      {xf12.map((v,i)=><div key={i} style={{flex:1,height:`${Math.max(1,Math.abs(v)/mx*18)}px`,borderRadius:'1px 1px 0 0',background:v>=0?c:'#ef4444',opacity:.8}}/>)}
                    </div>
                    <button onClick={e2=>{e2.stopPropagation();ensureAudio();[7,11,2].forEach((pc,i)=>setTimeout(()=>playNote(pc,4,i%3,0.4,2.5),i*35));}}
                      style={{marginTop:'5px',width:'100%',padding:'2px',borderRadius:'3px',border:'none',cursor:'pointer',background:c,color:'#000',fontSize:'8px',fontWeight:'bold'}}>▶ Hear</button>
                  </div>
                );
              })}
            </div>
            {/* Template distances */}
            <div style={{background:'#0f172a',borderRadius:'6px',padding:'10px'}}>
              <div style={{fontSize:'9px',color:'#94a3b8',fontWeight:'bold',marginBottom:'6px'}}>Template distances ‖x*_A − x*_B‖₂ (¢) — top 8 most separated pairs</div>
              {dists.slice(0,8).map(({a,b,d},i)=>(
                <div key={i} style={{display:'flex',gap:'6px',alignItems:'center',marginBottom:'3px'}}>
                  <div style={{minWidth:'180px',fontSize:'8px'}}>
                    <span style={{color:SC[a]||'#475569'}}>{a}</span>
                    <span style={{color:'#334155'}}> ↔ </span>
                    <span style={{color:SC[b]||'#475569'}}>{b}</span>
                  </div>
                  <div style={{flex:1,height:'8px',background:'#1e293b',borderRadius:'4px',overflow:'hidden'}}>
                    <div style={{width:`${d/30*100}%`,height:'100%',background:'linear-gradient(90deg,'+SC[a]+','+SC[b]+')',borderRadius:'4px'}}/>
                  </div>
                  <div style={{minWidth:'40px',fontSize:'8px',color:'#94a3b8',fontWeight:'bold',textAlign:'right'}}>{d.toFixed(2)}¢</div>
                </div>
              ))}
              <div style={{marginTop:'8px',fontSize:'8px',color:'#475569',lineHeight:1.6}}>
                The maximum separation confirms which operators are algebraically most distinct — not merely historically different. A large resurrect↔chant distance means the hard-hex+cadential and chant-final operators live in genuinely different subspaces of ℝ¹²; they cannot be interpolated through ET without passing through the isotropic zero.
              </div>
            </div>
          </div>
        );
      })()}

      {/* ══ SPARSE INVERSION ══ */}
      {panel==='invert'&&(()=>{
        const eg='2.1,-3.4,0.8,-6.2,4.1,-1.2,3.8,-2.7,1.5,-4.8,2.2,-1.1';
        const modeColors=['#ef4444','#f59e0b','#fbbf24','#84cc16','#22c55e','#06b6d4','#3b82f6','#6366f1','#8b5cf6','#a855f7','#22c55e'];
        const PRIM_COLORS={KEY:'#3b82f6',CAD:'#ef4444',HEX:'#f59e0b',CON:'#22c55e',VL:'#c084fc'};
        return(
          <div style={{background:'#1e293b',borderRadius:'8px',padding:'14px'}}>
            <div style={{fontSize:'11px',color:'#06b6d4',fontWeight:'bold',marginBottom:'6px'}}>🔬 ADVANCE 3: SPARSE STYLE INVERSION</div>
            <div style={{fontSize:'9px',color:'#64748b',marginBottom:'10px'}}>
              Given observed cent deviations, solve: min ‖Σ wₛ·x*ₛ − obs‖² + λ·‖w‖₁ (L1-regularized). The sparsity penalty discovers the minimal operator composition — not the richest fit, but the most parsimonious symmetry breaker consistent with the data. λ controls sparsity pressure.
            </div>
            <div style={{background:'#0f172a',borderRadius:'6px',padding:'10px',marginBottom:'10px'}}>
              <div style={{fontSize:'9px',color:'#64748b',marginBottom:'6px',fontWeight:'bold'}}>Observed deviations (¢) — 12 values C,C#,D,Eb,E,F,F#,G,Ab,A,Bb,B</div>
              <div style={{display:'flex',gap:'6px',alignItems:'flex-start',flexWrap:'wrap'}}>
                <textarea value={invInput} onChange={e=>setInvInput(e.target.value)} placeholder={eg}
                  style={{flex:1,minWidth:'200px',background:'#0a0f1a',color:'#e2e8f0',border:'1px solid #334155',borderRadius:'4px',padding:'6px',fontSize:'9px',fontFamily:'monospace',height:'36px',resize:'none'}}/>
                <div style={{display:'flex',flexDirection:'column',gap:'4px'}}>
                  <button onClick={()=>{
                    const src=invInput||eg;
                    const obs=src.split(',').map(Number);
                    if(obs.length===12&&!obs.some(isNaN))setInvResult(sparseInvert(obs,J17,invLambda));
                    else setInvResult({error:'Need exactly 12 comma-separated cent values'});
                  }} style={{padding:'5px 14px',borderRadius:'5px',border:'none',cursor:'pointer',fontSize:'10px',fontWeight:'bold',background:'#06b6d4',color:'#000'}}>▶ INVERT</button>
                  <button onClick={()=>setInvInput(spelled12.map(v=>+v.toFixed(2)).join(','))}
                    style={{padding:'3px 10px',borderRadius:'4px',border:'none',cursor:'pointer',fontSize:'8px',background:'#334155',color:'#94a3b8'}}>Use live spelled x*</button>
                  <button onClick={()=>setInvInput(eg)}
                    style={{padding:'3px 10px',borderRadius:'4px',border:'none',cursor:'pointer',fontSize:'8px',background:'#334155',color:'#94a3b8'}}>Load example</button>
                </div>
              </div>
              <div style={{display:'flex',alignItems:'center',gap:'8px',marginTop:'8px'}}>
                <span style={{fontSize:'8px',color:'#64748b'}}>λ (sparsity)</span>
                <input type="range" min="0" max="30" value={Math.round(invLambda*100)} onChange={e=>setInvLambda(+e.target.value/100)} style={{flex:1}}/>
                <span style={{fontSize:'9px',color:'#06b6d4',fontWeight:'bold',minWidth:'36px'}}>{invLambda.toFixed(2)}</span>
                <span style={{fontSize:'7px',color:'#334155'}}>λ=0: dense fit · λ=0.3: sparse (minimal)</span>
              </div>
            </div>
            {invResult&&!invResult.error&&(()=>{
              const maxW=Math.max(...invResult.w);
              const maxMod=Math.max(...invResult.modalProj.map(m=>Math.abs(m.coeff)));
              return(
                <div style={{display:'grid',gridTemplateColumns:'1fr 1fr 1fr',gap:'10px'}}>
                  <div>
                    <div style={{fontSize:'9px',color:'#64748b',fontWeight:'bold',marginBottom:'6px'}}>Recovered strategy weights</div>
                    {invResult.strats.map((s,si)=>{const w=invResult.w[si],c=SC[s]||'#475569';return(
                      <div key={s} style={{marginBottom:'3px',background:'#0f172a',borderRadius:'3px',padding:'4px 6px',opacity:w<0.005?0.3:1}}>
                        <div style={{display:'flex',justifyContent:'space-between',marginBottom:'1px'}}>
                          <span style={{fontSize:'8px',color:c,fontWeight:s===invResult.domStrat?'bold':'normal'}}>{s}{s===invResult.domStrat?' ★':''}</span>
                          <span style={{fontSize:'8px',color:w<0.01?'#334155':c}}>{(w*100).toFixed(1)}%</span>
                        </div>
                        <div style={{height:'5px',background:'#1e293b',borderRadius:'2px',overflow:'hidden'}}>
                          <div style={{width:`${w/maxW*100}%`,height:'100%',background:c}}/>
                        </div>
                      </div>);})}
                    <div style={{marginTop:'6px',background:'#0f172a',borderRadius:'4px',padding:'5px',fontSize:'8px'}}>
                      <div style={{display:'flex',justifyContent:'space-between',marginBottom:'2px'}}><span style={{color:'#475569'}}>Fit RMS</span><span style={{color:invResult.rms<2?'#22c55e':invResult.rms<5?'#f59e0b':'#ef4444',fontWeight:'bold'}}>{invResult.rms.toFixed(3)}¢</span></div>
                      <div style={{display:'flex',justifyContent:'space-between',marginBottom:'2px'}}><span style={{color:'#475569'}}>Sparsity</span><span style={{color:'#06b6d4',fontWeight:'bold'}}>{(invResult.sparsity*100).toFixed(0)}% zero</span></div>
                      <div style={{display:'flex',justifyContent:'space-between'}}><span style={{color:'#475569'}}>Dom. strategy</span><span style={{color:SC[invResult.domStrat]||'#94a3b8',fontWeight:'bold'}}>{invResult.domStrat}</span></div>
                    </div>
                  </div>
                  <div>
                    <div style={{fontSize:'9px',color:'#64748b',fontWeight:'bold',marginBottom:'6px'}}>Primitive operator decomposition</div>
                    {Object.entries(invResult.primContrib).map(([op,v])=>(
                      <div key={op} style={{marginBottom:'4px',background:'#0f172a',borderRadius:'3px',padding:'5px 7px'}}>
                        <div style={{display:'flex',justifyContent:'space-between',marginBottom:'2px'}}>
                          <span style={{fontSize:'9px',color:PRIM_COLORS[op],fontWeight:'bold'}}>{op}</span>
                          <span style={{fontSize:'8px',color:PRIM_COLORS[op]}}>{(v*100).toFixed(1)}%</span>
                        </div>
                        <div style={{height:'7px',background:'#1e293b',borderRadius:'3px',overflow:'hidden'}}>
                          <div style={{width:`${v*100}%`,height:'100%',background:PRIM_COLORS[op]}}/>
                        </div>
                      </div>))}
                    <div style={{marginTop:'6px',fontSize:'8px',color:'#475569',background:'#0f172a',borderRadius:'4px',padding:'6px'}}>
                      The primitive decomposition answers "which symmetry-breaking component is doing the real work" — independent of which named strategy dominated. A high HEX contribution means the data's structure is enharmonic-sectoral; high CAD means it's cadentially directed.
                    </div>
                  </div>
                  <div>
                    <div style={{fontSize:'9px',color:'#64748b',fontWeight:'bold',marginBottom:'6px'}}>Modal fingerprint of observed data</div>
                    {invResult.modalProj.map((m,mi)=>{
                      const barW=Math.abs(m.coeff)/maxMod*100;
                      return(<div key={mi} style={{marginBottom:'2px',display:'flex',gap:'5px',alignItems:'center'}}>
                        <div style={{fontSize:'7px',color:modeColors[mi],minWidth:'50px'}}>m{mi+1} {m.sigma.toFixed(3)}</div>
                        <div style={{flex:1,height:'8px',background:'#0f172a',borderRadius:'3px',overflow:'hidden',position:'relative'}}>
                          <div style={{position:'absolute',left:m.coeff>=0?'50%':'auto',right:m.coeff<0?'50%':'auto',width:`${barW/2}%`,height:'100%',background:modeColors[mi],opacity:.85}}/>
                          <div style={{position:'absolute',left:'50%',top:0,bottom:0,width:'1px',background:'#1e293b'}}/>
                        </div>
                        <div style={{fontSize:'7px',color:modeColors[mi],minWidth:'36px',textAlign:'right'}}>{m.coeff>=0?'+':''}{m.coeff.toFixed(2)}</div>
                      </div>);
                    })}
                    <div style={{marginTop:'6px',display:'grid',gridTemplateColumns:'1fr 1fr',gap:'3px',fontSize:'8px'}}>
                      <div style={{background:'#0f172a',borderRadius:'3px',padding:'4px',textAlign:'center'}}>
                        <div style={{color:'#475569'}}>Obs vs Predicted</div>
                        <div style={{height:'30px',display:'flex',gap:'1px',alignItems:'flex-end',marginTop:'3px'}}>
                          {invResult.pred.map((p,i)=>{const obs2=parseFloat((invInput||eg).split(',')[i])||0;const mp=Math.max(.1,...invResult.pred.map(Math.abs),...[...new Array(12)].map((_,k)=>Math.abs(parseFloat((invInput||eg).split(',')[k])||0)));return(
                            <div key={i} style={{flex:1,display:'flex',flexDirection:'column',alignItems:'center',gap:'1px'}}>
                              <div style={{width:'45%',height:`${Math.max(1,Math.abs(obs2)/mp*13)}px`,background:'#06b6d4',borderRadius:'1px'}}/>
                              <div style={{width:'45%',height:`${Math.max(1,Math.abs(p)/mp*13)}px`,background:'#f59e0b',borderRadius:'1px'}}/>
                            </div>);})}
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              );
            })()}
            {invResult?.error&&<div style={{color:'#ef4444',fontSize:'9px',padding:'8px'}}>{invResult.error}</div>}
            {!invResult&&<div style={{color:'#334155',fontSize:'9px',textAlign:'center',padding:'20px'}}>Enter 12 cent deviations and press INVERT. λ controls sparsity — higher λ → fewer non-zero strategies.</div>}
          </div>
        );
      })()}

      {/* ══ TIMBRE ══ */}
      {panel==='timbre'&&(
        <div style={{display:'grid',gridTemplateColumns:'1fr 2fr',gap:'10px'}}>
          <div style={{background:'#1e293b',borderRadius:'8px',padding:'10px'}}>
            <div style={{fontSize:'11px',color:'#c084fc',fontWeight:'bold',marginBottom:'8px'}}>🎵 VOICE ENVELOPES</div>
            <div style={{display:'flex',flexDirection:'column',gap:'4px'}}>
              {VOICE_PROFILES.map((prof,vi)=>(
                <button key={vi} onClick={()=>setEditVoice(vi)} style={{padding:'6px 8px',borderRadius:'5px',border:`1px solid ${editVoice===vi?prof.color:'#1e293b'}`,cursor:'pointer',background:editVoice===vi?prof.color+'22':'#0f172a',textAlign:'left'}}>
                  <div style={{color:prof.color,fontWeight:'bold',fontSize:'9px'}}>{prof.name} — {prof.hex.replace('hex_','')}</div>
                  <div style={{fontSize:'8px',color:'#475569'}}>vib {prof.vibRate}Hz · sub {(voiceSubGain[vi]*100|0)}%</div>
                  <div style={{display:'flex',gap:'1px',height:'12px',alignItems:'flex-end',marginTop:'2px'}}>
                    {voiceGains[vi].map((g,hi)=><div key={hi} style={{flex:1,height:`${g*10}px`,background:prof.color,opacity:.7,borderRadius:'1px'}}/>)}
                  </div>
                </button>
              ))}
            </div>
          </div>
          <div style={{background:'#1e293b',borderRadius:'8px',padding:'12px'}}>
            {(()=>{
              const prof=VOICE_PROFILES[editVoice];
              const gains=voiceGains[editVoice];
              const subG=voiceSubGain[editVoice];
              return(
                <div>
                  <div style={{display:'flex',justifyContent:'space-between',marginBottom:'10px'}}>
                    <div><div style={{fontSize:'12px',color:prof.color,fontWeight:'bold'}}>{prof.name}</div>
                    <div style={{fontSize:'8px',color:'#475569'}}>{prof.hex} · vib {prof.vibRate}Hz · pos {prof.pos.join(',')}m</div></div>
                    <button onClick={()=>{ensureAudio();[0,4,7].forEach((pc,j)=>setTimeout(()=>playNote(pc,3+editVoice%2,editVoice,.5,2.5),j*30));}}
                      style={{padding:'5px 14px',borderRadius:'5px',border:'none',cursor:'pointer',background:prof.color,color:'#000',fontSize:'10px',fontWeight:'bold'}}>▶ Play</button>
                  </div>
                  <div style={{fontSize:'9px',color:'#64748b',fontWeight:'bold',marginBottom:'8px'}}>Harmonic Gains H1–H8</div>
                  <div style={{display:'grid',gap:'6px',marginBottom:'12px'}}>
                    {gains.map((g,hi)=>(
                      <div key={hi} style={{display:'flex',gap:'8px',alignItems:'center'}}>
                        <div style={{minWidth:'30px',fontSize:'9px',color:prof.color,fontWeight:'bold'}}>H{hi+1}</div>
                        <input type="range" min="0" max="100" value={Math.round(g*100)}
                          onChange={e=>{const nv=+e.target.value/100;setVoiceGains(vg=>{const n=vg.map(v=>[...v]);n[editVoice][hi]=nv;return n;});}}
                          style={{flex:1,accentColor:prof.color}}/>
                        <div style={{width:'36px',height:`${Math.max(4,g*40)}px`,background:prof.color,borderRadius:'2px',opacity:.8,transition:'height .1s'}}/>
                        <div style={{minWidth:'32px',fontSize:'9px',color:'#64748b',textAlign:'right'}}>{(g*100|0)}%</div>
                      </div>
                    ))}
                  </div>
                  <div style={{display:'flex',gap:'8px',alignItems:'center'}}>
                    <div style={{fontSize:'9px',color:'#64748b',minWidth:'90px'}}>Subharmonic (½f)</div>
                    <input type="range" min="0" max="40" value={Math.round(subG*100)}
                      onChange={e=>setVoiceSubGain(sg=>{const n=[...sg];n[editVoice]=+e.target.value/100;return n;})}
                      style={{flex:1,accentColor:'#ef4444'}}/>
                    <div style={{fontSize:'9px',color:'#ef4444',fontWeight:'bold',minWidth:'32px'}}>{(subG*100|0)}%</div>
                  </div>
                </div>
              );
            })()}
          </div>
        </div>
      )}

      {/* ══ WAVES ══ */}
      {panel==='waves'&&(
        <div style={{background:'#1e293b',borderRadius:'8px',padding:'12px'}}>
          <div style={{display:'flex',justifyContent:'space-between',marginBottom:'8px'}}>
            <div style={{fontSize:'11px',color:'#94a3b8',fontWeight:'bold'}}>〰 WAVEFORM + SPECTRUM — spelled frequencies marked</div>
            <div style={{display:'flex',gap:'5px'}}>
              {[['G maj',[7,11,2]],['E min',[4,7,11]],['D maj',[2,6,9]],['Bb maj',[10,2,5]]].map(([l,pcs])=>(
                <button key={l} onClick={()=>{ensureAudio();pcs.forEach((pc,i)=>setTimeout(()=>playNote(pc,4,i%8,.5,3),i*25));}} style={{padding:'3px 8px',borderRadius:'4px',border:'none',cursor:'pointer',background:'#7c3aed',color:'#fff',fontSize:'9px',fontWeight:'bold'}}>▶ {l}</button>
              ))}
            </div>
          </div>
          <canvas ref={wCvs} width={700} height={120} style={{width:'100%',height:'120px',borderRadius:'6px',display:'block',background:'#0a0f1a'}}/>
          <canvas ref={sCvs} width={700} height={130} style={{width:'100%',height:'130px',borderRadius:'6px',display:'block',marginTop:'8px',background:'#0a0f1a'}}/>
        </div>
      )}

      {/* ══ PERFORMANCE ══ */}
      {panel==='perf'&&(
        <div style={{display:'grid',gridTemplateColumns:'3fr 2fr',gap:'10px'}}>
          <div style={{background:'#1e293b',borderRadius:'8px',padding:'12px'}}>
            <div style={{fontSize:'11px',color:'#ef4444',fontWeight:'bold',marginBottom:'8px'}}>🕍 RESURRECTION CANON — 8-voice SSAATTBB · Spelled tuning · Spectral flow active</div>
            <svg width="100%" viewBox="0 0 440 185" style={{display:'block',marginBottom:'8px'}}>
              {Array(8).fill(0).map((_,vi)=><line key={vi} x1={40} y1={12+vi*20} x2={430} y2={12+vi*20} stroke="#1e293b" strokeWidth="1"/>)}
              {Array.from({length:16},(_,i)=><line key={i} x1={40+i*24} y1={6} x2={40+i*24} y2={178} stroke="#1e293b" strokeWidth=".4"/>)}
              {perfMode&&<rect x={40+beat*24} y={6} width={23} height={172} fill="#7c3aed11" rx={2}/>}
              {SCORE8.map((ev,i)=>{
                const isNow=ev.b===beat&&perfMode;const prof=VOICE_PROFILES[ev.v];
                const nw=Math.max(18,ev.dur*24-2);
                return(<g key={i}>
                  <rect x={40+ev.b*24} y={12+ev.v*20-7} width={nw} height={13} rx={2}
                    fill={isNow?'#fbbf24':prof.color} opacity={isNow?1:.4}
                    style={{filter:isNow?'drop-shadow(0 0 5px #fbbf24)':'none'}}/>
                  <text x={40+ev.b*24+3} y={12+ev.v*20+3} fontSize={7} fill={isNow?'#000':'#0f172a'} fontWeight="bold">{PC[ev.pc]}</text>
                </g>);
              })}
              {VOICE_PROFILES.map((p,i)=><text key={p.name} x={2} y={16+i*20} fontSize={7} fill={p.color}>{p.name}</text>)}
            </svg>
            <div style={{display:'flex',gap:'4px',flexWrap:'wrap'}}>
              {activeV.map((ev,i)=>{
                const prof=VOICE_PROFILES[ev.v];
                const off=(voiceX[ev.v]||spelled12)[ev.pc]||0;
                return(
                  <div key={i} style={{padding:'3px 8px',borderRadius:'4px',background:'#0f172a',border:`1px solid ${prof.color}`,fontSize:'9px',color:prof.color,fontWeight:'bold'}}>
                    {prof.name}: {PC[ev.pc]} <span style={{fontSize:'8px',color:'#64748b'}}>{off>=0?'+':''}{off.toFixed(2)}¢</span>
                  </div>
                );
              })}
            </div>
          </div>
          <div style={{display:'flex',flexDirection:'column',gap:'8px'}}>
            <div style={{background:'#1e293b',borderRadius:'8px',padding:'10px'}}>
              <div style={{fontSize:'9px',color:'#64748b',fontWeight:'bold',marginBottom:'6px'}}>Live spelled offsets</div>
              <div style={{display:'grid',gridTemplateColumns:'repeat(12,1fr)',gap:'2px',height:'65px',alignItems:'flex-end'}}>
                {spelled12.map((v,i)=>{const isAct=activeV.some(a=>a.pc===i);const h=Math.max(2,Math.abs(v)/maxX*60);const c=HEX_HARD.has(i)&&!HEX_NAT.has(i)?'#f59e0b':HEX_SOFT.has(i)&&!HEX_NAT.has(i)?'#10b981':HEX_NAT.has(i)?'#3b82f6':'#475569';return(
                  <div key={i} style={{display:'flex',flexDirection:'column',alignItems:'center'}}>
                    <div style={{width:'100%',height:`${h}px`,borderRadius:'2px 2px 0 0',background:isAct?'#fbbf24':c,transition:'height .12s'}}/>
                    <div style={{fontSize:'6px',color:isAct?'#fbbf24':'#475569',marginTop:'1px'}}>{PC[i]}</div>
                  </div>);})}
              </div>
            </div>
            <div style={{background:'#1e293b',borderRadius:'8px',padding:'8px'}}>
              <div style={{fontSize:'9px',color:'#64748b',fontWeight:'bold',marginBottom:'4px'}}>Kalman · eta history</div>
              <div style={{height:'30px',display:'flex',gap:'1px',alignItems:'flex-end'}}>
                {beatHist.slice(-32).map((h,i)=><div key={i} style={{flex:1,height:`${Math.min(28,h.eta/237*28)}px`,minHeight:'2px',borderRadius:'1px 1px 0 0',background:SC[h.strat]||cc,opacity:.7}}/>)}
              </div>
            </div>
            <div style={{background:'#1e293b',borderRadius:'8px',padding:'8px',fontSize:'9px',color:'#475569'}}>
              <div style={{color:'#94a3b8',fontWeight:'bold',marginBottom:'3px'}}>Active features</div>
              {[['𝄞 Spelled semantics','ON'],['⊕ Spatial HRTF',spatialOn?'ON':'OFF'],['〰 Phrase vibrato',vibratoOn?'ON':'OFF'],['∿ Eigenmode shimmer',eigenmodeOn?'ON':'OFF'],['∂ Spectral flow',flowOn?'ON':'OFF']].map(([l,on])=>(
                <div key={l} style={{display:'flex',justifyContent:'space-between',marginBottom:'2px'}}>
                  <span>{l}</span><span style={{color:on==='ON'?'#22c55e':'#ef4444',fontWeight:'bold'}}>{on}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      <div style={{marginTop:'10px',display:'flex',justifyContent:'space-between',fontSize:'8px',color:'#1e293b'}}>
        <span>Dyletsky v6 · Spelled Semantics · Operator Algebra · Sparse Inversion · Spectral Flow Law · Algebraic Room · Comparative Operators · Grammatika 1675</span>
        <span>σ_min=1/√2 · det=509M (17-note) · Христос Воскресе</span>
      </div>
    </div>
  );
}
