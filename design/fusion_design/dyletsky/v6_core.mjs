// Source-preserving pure core; see source_provenance.json.
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

export { PC, N, QCM, SP17, SP17_PC, SP17_DIA, PRIM_OPS, STRAT_ALGEBRA, buildJ17, algebraicWeight, spelledTarget, solve_n, computeSpelled, EIGENMODES, GAMMA, VOICE_PROFILES, PH_STRAT, SCORE8, toHz, sparseInvert };
