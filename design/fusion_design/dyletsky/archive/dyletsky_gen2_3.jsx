import { useState, useEffect, useRef, useCallback } from "react";

// ════════════════════════════════════════════════════════════════════
//  I. SPELLED CHROMATIC MANIFOLD — J_spelled ∈ ℝ^{43×16}
//  Pythagorean 17-note chain: Gb Db Ab Eb Bb F C G D A E B F# C# G# D# A#
//  Gauge: x_C = 0 → 16 free dimensions.  G# ≠ Ab by construction.
// ════════════════════════════════════════════════════════════════════

const CHAIN=[
  {sp:'Gb',midi:6},{sp:'Db',midi:1},{sp:'Ab',midi:8},
  {sp:'Eb',midi:3},{sp:'Bb',midi:10},{sp:'F',midi:5},
  {sp:'C',midi:0},{sp:'G',midi:7},{sp:'D',midi:2},
  {sp:'A',midi:9},{sp:'E',midi:4},{sp:'B',midi:11},
  {sp:'F#',midi:6},{sp:'C#',midi:1},{sp:'G#',midi:8},
  {sp:'D#',midi:3},{sp:'A#',midi:10},
];
const CG=6;                         // C at chain index 6 (gauge)
const ci2fi=si=>si<CG?si:si-1;     // chain index → free variable index (0..15)

function buildSpelledSys(){
  const J=[],b=[];
  // P5: chain[k] → chain[k+1]  (16 rows)
  for(let k=0;k<16;k++){
    const row=new Array(16).fill(0);
    if(k+1!==CG)row[ci2fi(k+1)]+=1; if(k!==CG)row[ci2fi(k)]-=1;
    J.push(row);b.push(1.955);
  }
  // M3: chain[k] → chain[k+4]  (13 rows, k=0..12)
  for(let k=0;k<=12;k++){
    const e=k+4,row=new Array(16).fill(0);
    if(e!==CG)row[ci2fi(e)]+=1; if(k!==CG)row[ci2fi(k)]-=1;
    J.push(row);b.push(-13.686);
  }
  // m3: chain[k] → chain[k-3]  ascending m3 (14 rows, k=3..16)
  for(let k=3;k<17;k++){
    const e=k-3,row=new Array(16).fill(0);
    if(e!==CG)row[ci2fi(e)]+=1; if(k!==CG)row[ci2fi(k)]-=1;
    J.push(row);b.push(15.641);
  }
  return{J,b};
}

// ── Linear algebra (16×16) ───────────────────────────────────────────
function chol(A){
  const n=A.length,L=A.map(r=>r.slice());
  for(let i=0;i<n;i++){
    for(let j=0;j<i;j++){let s=L[i][j];for(let k=0;k<j;k++)s-=L[i][k]*L[j][k];L[i][j]=s/L[j][j];}
    let s=L[i][i];for(let k=0;k<i;k++)s-=L[i][k]*L[i][k];L[i][i]=Math.sqrt(Math.max(s,1e-14));
  }
  return L;
}
function fwdBack(L,rhs){
  const n=rhs.length,y=new Array(n).fill(0),x=new Array(n).fill(0);
  for(let i=0;i<n;i++){let s=rhs[i];for(let j=0;j<i;j++)s-=L[i][j]*y[j];y[i]=s/L[i][i];}
  for(let i=n-1;i>=0;i--){let s=y[i];for(let j=i+1;j<n;j++)s-=L[j][i]*x[j];x[i]=s/L[i][i];}
  return x;
}
function cholInv(A){
  const n=A.length,L=chol(A),M=Array.from({length:n},()=>new Array(n).fill(0)),e=new Array(n).fill(0);
  for(let c=0;c<n;c++){e.fill(0);e[c]=1;const v=fwdBack(L,e);for(let r=0;r<n;r++)M[r][c]=v[r];}
  return M;
}

function powerIter(H,it=12){
  const n=H.length;let v=new Array(n).fill(0);v[0]=1;
  for(let t=0;t<it;t++){const w=H.map(row=>row.reduce((s,h,j)=>s+h*v[j],0)),nm=Math.sqrt(w.reduce((s,x)=>s+x*x,0));if(nm<1e-12)break;v=w.map(x=>x/nm);}
  return{lmax:H.reduce((s,row,i)=>s+row.reduce((s2,h,j)=>s2+h*v[i]*v[j],0),0),q:v};
}
function invPowerIter(Hi,it=10){
  const n=Hi.length;let v=new Array(n).fill(1/Math.sqrt(n));
  for(let t=0;t<it;t++){const w=Hi.map(row=>row.reduce((s,h,j)=>s+h*v[j],0)),nm=Math.sqrt(w.reduce((s,x)=>s+x*x,0));if(nm<1e-12)break;v=w.map(x=>x/nm);}
  return v;
}
const cl=(v,a,b)=>Math.min(b,Math.max(a,v));
const kProj=(H,lmax)=>Math.max(0,1-lmax/H.reduce((s,_,i)=>s+H[i][i],0));

// ── Style operator weights (36-dim for Z₁₂ voicing coupling) ────────
const HN=new Set([0,2,4,5,7,9]),HH=new Set([0,2,4,7,9,11]),HS=new Set([0,2,5,7,9,10]);
const FN=new Set([2,4,5,7]),CS=new Set([4,7,11]);
const SK=['resurrect','hex_nat','modal','cadence','liturgy','lent','passion','hex_hard'];

function pureW36(s){
  const IVLS_Z12=[{st:7},{st:4},{st:3}];
  const w=new Array(36).fill(1);let r=0;
  for(const{st}of IVLS_Z12)for(let p=0;p<12;p++){
    const e=(p+st)%12,iN=HN.has(p)&&HN.has(e),iH=HH.has(p)&&HH.has(e),iS=HS.has(p)&&HS.has(e);
    if(s==='hex_nat'){if(iN)w[r]=3;}else if(s==='hex_hard'){if(iH)w[r]=5;}
    else if(s==='modal'){if(FN.has(e))w[r]=5;}else if(s==='resurrect'){w[r]=(iH&&FN.has(e))?8:iH?4:1;}
    else if(s==='cadence'){if(CS.has(e))w[r]=5;}
    else if(s==='liturgy'){w[r]=iN?(st===4?3.75:st===3?3:1.5):(st===4?2.5:st===3?2:1);}
    else if(s==='lent'){w[r]=iS?(st===3?6:st===7?3:.7):(st===3?2.5:st===4?.7:1.5);}
    else if(s==='passion'){w[r]=iS?(st===3?7:st===7?2.5:.5):(st===3?3:st===4?.5:1.2);}
    r++;
  }
  return w;
}

// Map 36-dim Z₁₂ weight to 43-dim spelled weight (by interval family)
function w36toSpelled(w36){
  // First 16 rows = P5, next 13 = M3, last 14 = m3
  const w=new Array(43).fill(1);
  // P5 rows 0..15: average over the 12 P5 rows in w36 (rows 0..11)
  const avgP5=w36.slice(0,12).reduce((s,v)=>s+v,0)/12;
  for(let r=0;r<16;r++)w[r]=avgP5;
  // M3 rows 16..28: average over w36 rows 12..23
  const avgM3=w36.slice(12,24).reduce((s,v)=>s+v,0)/12;
  for(let r=16;r<29;r++)w[r]=avgM3;
  // m3 rows 29..42: average over w36 rows 24..35
  const avgm3=w36.slice(24,36).reduce((s,v)=>s+v,0)/12;
  for(let r=29;r<43;r++)w[r]=avgm3;
  return w.map(v=>Math.max(.5,v));
}

function solve(J,b,w){
  const n=J[0].length,lam=.008,G=Array.from({length:n},()=>new Array(n).fill(0)),f=new Array(n).fill(0);
  for(let r=0;r<J.length;r++){const wr=w[r];for(let i=0;i<n;i++){f[i]+=wr*J[r][i]*b[r];for(let j=0;j<n;j++)G[i][j]+=wr*J[r][i]*J[r][j];}}
  for(let i=0;i<n;i++)G[i][i]+=lam;
  const L=chol(G),xs=fwdBack(L,f),Hi=cholInv(G);
  const eta=f.reduce((s,v)=>s+v*v,0),norm=Math.sqrt(xs.reduce((s,v)=>s+v*v,0));
  let wN=0,wD=0;
  for(let r=0;r<J.length;r++){const res=b[r]-J[r].reduce((s,v,i)=>s+v*xs[i],0);wN+=w[r]*res*res;wD+=w[r];}
  return{xs,H:G,Hi,eta,norm,wRMS:Math.sqrt(wN/wD),trHi:Hi.reduce((s,_,i)=>s+Hi[i][i],0)};
}

function mixW(g){
  const w=new Array(36).fill(0);
  SK.forEach((s,k)=>{const pw=pureW36(s),gk=g[k]||0;for(let r=0;r<36;r++)w[r]+=gk*pw[r];});
  return w.map(v=>Math.max(.5,v));
}

// ── Spelled energy field (16-dim) ────────────────────────────────────
// e_{si} ∈ ℝ^16: unit vector at free variable ci2fi(si), zero at gauge
function eVec(si){const v=new Array(16).fill(0);if(si!==CG)v[ci2fi(si)]=1;return v;}

function pcE_sp(si,xs,H){
  const n=16,d=xs.map((v,i)=>eVec(si)[i]-v);
  let e=0;for(let i=0;i<n;i++)for(let j=0;j<n;j++)e+=d[i]*H[i][j]*d[j];return Math.max(0,e);
}
function normE_sp(xs,H){
  const raw=Array.from({length:17},(_,si)=>pcE_sp(si,xs,H));
  const mu=raw.reduce((s,v)=>s+v,0)/17,sigma=Math.sqrt(raw.reduce((s,v)=>s+(v-mu)**2,0)/17);
  return{raw,norm:raw.map(e=>(e-mu)/(sigma+1e-6)),sigma};
}
function hinvW_sp(si,xs,Hi){
  const n=16,ev=eVec(si),d=xs.map((v,i)=>ev[i]-v);
  let q=0;for(let i=0;i<n;i++)for(let j=0;j<n;j++)q+=d[i]*Hi[i][j]*d[j];return Math.exp(-.5*q);
}
function geomCost_sp(fSi,tSi,H){
  const n=16,fv=eVec(fSi),tv=eVec(tSi),d=Array.from({length:n},(_,i)=>tv[i]-fv[i]);
  let q=0;for(let i=0;i<n;i++)for(let j=0;j<n;j++)q+=d[i]*H[i][j]*d[j];return Math.max(0,q);
}

// Voice-block register modifiers on spelled weight vector (43-dim)
const VREG={
  discant:{P5:.85,M3:1.55,m3:.90},cantus:{P5:1.05,M3:1.20,m3:1.05},
  bass:{P5:1.80,M3:.50,m3:1.20},pedal:{P5:2.20,M3:.30,m3:.80},
};
function applyVreg43(w43,vtype){
  const m=VREG[vtype]||VREG.cantus;
  return w43.map((v,r)=>v*(r<16?m.P5:r<29?m.M3:m.m3));
}
function blockSolve(J,b,baseW43){
  return Object.fromEntries(['discant','cantus','bass','pedal'].map(vc=>[vc,solve(J,b,applyVreg43(baseW43,vc)).xs]));
}

// Geodesic: precompute d²_rs from pure spelled x* vectors
function buildGeoMat(J,b,sys){
  const pxs=SK.map(s=>solve(J,b,w36toSpelled(pureW36(s))).xs);
  return pxs.map(xi=>pxs.map(xj=>xj.reduce((s,v,i)=>s+(v-xi[i])**2,0)));
}

// ════════════════════════════════════════════════════════════════════
//  II. GEODESIC γ FLOW — true quadratic form G(γ) = γᵀ D² γ
// ════════════════════════════════════════════════════════════════════

// ∇G(γ) = 2 D² γ,  projected onto simplex tangent (subtract mean)
function geoGradient(g,d2){
  const raw=g.map((_,r)=>2*d2[r].reduce((s,d,c)=>s+d*g[c],0));
  const mean=raw.reduce((s,v)=>s+v,0)/g.length;
  return raw.map(v=>v-mean);
}

const PAFF={
  jubilate:{resurrect:3,hex_hard:1.5,hex_nat:.8,modal:.5,cadence:.3,liturgy:.2,lent:0,passion:.1},
  interior:{hex_nat:2.5,modal:1.2,liturgy:1,resurrect:.5,cadence:.4,hex_hard:.3,lent:.2,passion:.1},
  precad:  {cadence:2.8,modal:1.5,hex_nat:.8,resurrect:.6,hex_hard:.4,liturgy:.2,lent:.1,passion:.1},
  cadence: {modal:3,cadence:2,resurrect:.8,hex_nat:.5,liturgy:.4,hex_hard:.3,lent:.1,passion:.2},
  resolve: {liturgy:3,hex_nat:1.5,modal:1,lent:.6,cadence:.3,resurrect:.2,hex_hard:.1,passion:.1},
};
function smx(v,t){const mx=Math.max(...v),ex=v.map(x=>Math.exp((x-mx)/(t||1))),s=ex.reduce((a,b)=>a+b,0);return ex.map(x=>x/s);}

function flowG(g,ph,D,pin,d2){
  // PAFF phrase target
  const target=pin?SK.map((_,k)=>k===SK.indexOf(pin)?.93:.01):smx(SK.map(s=>(PAFF[ph]||PAFF.interior)[s]||0),.6+.8*D);
  const nu=.15,mu=.04;  // mu = geodesic repulsion on γ
  const gg=d2?geoGradient(g,d2):new Array(g.length).fill(0);
  // γ̇ = −ν(γ − γ*) − μ ∇G(γ),  then project onto simplex
  const nx=g.map((v,k)=>Math.max(.001,v+nu*(target[k]-v)-mu*gg[k]));
  const sm=nx.reduce((a,b)=>a+b,0);return nx.map(v=>v/sm);
}

// ── Memory ────────────────────────────────────────────────────────────
const ML=8,MR=.72,MLM=2.4,MLM_PH=1.6,MR_PH=.85;
const updMem=(m,pc)=>[pc,...m.slice(0,ML-1)];
const memPen=(m,si)=>m.reduce((s,x,j)=>s+(x===si?Math.pow(MR,j+1):0),0);
const phaseMemPen=(pm,si)=>(pm||[]).reduce((s,x,j)=>s+(x===si?Math.pow(MR_PH,j+1):0),0);

// ── MH sampler in spelled space (17 candidates per octave) ───────────
const PB={jubilate:new Set([7,4,11,2]),interior:new Set([0,2,9,5]),precad:new Set([9,2,11,6]),cadence:new Set([7,4,11,5]),resolve:new Set([4,9,0,5])};
const ST={discant:1.8,cantus:1.2,bass:.9,pedal:.7};

function pairV(p1,o1,p2,o2){
  const iv=Math.abs(o1*12+p1-o2*12-p2)%12;
  return[2.5,.3,.2,-.8,-1.2,.5,-.2,-.6,.1,-.7,.3,.4][iv]+(Math.abs(o1*12+p1-o2*12-p2)<3?.8:0);
}
function jointE_midi(cfg,xs,H){
  let E=0;
  for(const{si,oct}of cfg)E+=pcE_sp(si,xs,H)*.5;
  for(let i=0;i<cfg.length;i++)for(let j=i+1;j<cfg.length;j++)E+=pairV(CHAIN[cfg[i].si].midi,cfg[i].oct,CHAIN[cfg[j].si].midi,cfg[j].oct);
  return E;
}

function mhStep(vi,vs,xs_v,xs_sh,H,Hi,En_sp,Er_sp,mem,phaseMem,mode,ph){
  const vc=vs[vi],bias=PB[ph]||PB.interior,beta=1/(ST[vc.vtype]||1);
  const[lo,hi]=vc.octRange,curSi=vc.si,oth=vs.filter((_,i)=>i!==vi).map(v=>v.oct*12+CHAIN[v.si].midi);
  const cands=[];
  for(let oct=lo;oct<=hi;oct++)for(let si=0;si<17;si++){
    const{midi:pc}=CHAIN[si];
    const midiThis=oct*12+pc,midiCur=vc.oct*12+CHAIN[curSi].midi;
    const dist=Math.abs(midiThis-midiCur);if(dist>14)continue;
    const sw=dist<=2?1:dist<=4?.65:dist<=7?.32:.10;
    let sp=1;for(const om of oth){const iv=Math.abs(midiThis-om)%12;if(!iv)sp*=.08;else if(iv===7)sp*=.55;}
    const cw=(ph==='cadence'||ph==='precad')&&CS.has(pc)?1.6:1;
    const bw=bias.has(pc)?1.35:mode.includes(pc)?.85:.28;
    let aw=1;
    if(vc.vtype==='pedal'){
      const top2=new Set(Er_sp.map((e,i)=>({si:i,e})).sort((a,b)=>a.e-b.e).slice(0,3).filter(x=>mode.includes(CHAIN[x.si].midi)).slice(0,2).map(x=>x.si));
      aw=top2.has(si)?3.2:mode.includes(pc)?.5:.04;
    }
    const hw=hinvW_sp(si,xs_v,Hi);
    const stabW=Math.exp(-beta*.5*(En_sp[si]||0));
    const gtW=Math.exp(-beta*.18*geomCost_sp(curSi,si,H));
    const memE=MLM*memPen(mem,si)+MLM_PH*phaseMemPen(phaseMem,si);
    cands.push({si,oct,w:hw*stabW*gtW*Math.exp(-beta*memE)*sw*sp*cw*bw*aw});
  }
  if(!cands.length)return vs;
  const tot=cands.reduce((s,c)=>s+c.w,0);let r=Math.random()*tot,prop=cands[cands.length-1];
  for(const c of cands){r-=c.w;if(r<=0){prop=c;break;}}
  const cc=vs.map(v=>({si:v.si,oct:v.oct})),p2=cc.map((v,i)=>i===vi?{si:prop.si,oct:prop.oct}:v);
  const dE=jointE_midi(p2,xs_sh,H)-jointE_midi(cc,xs_sh,H),T=(ST[vc.vtype]||1)*2;
  if(dE<0||Math.random()<Math.exp(-dE/T)){
    const nv=vs.slice();
    const cents=prop.si===CG?0:(xs_v[ci2fi(prop.si)]||0);
    nv[vi]=Object.assign({},vs[vi],{si:prop.si,pc:CHAIN[prop.si].midi,oct:prop.oct,sp:CHAIN[prop.si].sp,cents});
    return nv;
  }
  return vs;
}

function eDur(si,En_sp,vt,ph){
  const base=Math.exp(-.35*(En_sp[si]||0));
  const SC={discant:{lo:1,hi:5},cantus:{lo:2,hi:9},bass:{lo:3,hi:11},pedal:{lo:5,hi:20}};
  const sc=SC[vt]||SC.cantus,pm=ph==='cadence'?1.5:ph==='jubilate'?.65:1;
  return Math.round(cl(-(sc.lo+base*(sc.hi-sc.lo)*pm)*Math.log(Math.max(Math.random(),.001)),sc.lo,sc.hi*1.6));
}

const gjt=d=>1+.3282804759*d+.08007661*d*d+.01088191*d*d*d+.0009844771*Math.pow(d,4);
function stepD(D,ph){const c2=ph==='cadence'||ph==='precad',a=c2?-.7133:ph==='jubilate'?.11:ph==='resolve'?-.25:-.04,g=c2?-4.277:-1.2;return cl(D+.28*(a+g*D*D),0,3);}
const sigT=(D,ph)=>.12*(1+(ph==='jubilate'?1.8:ph==='resolve'?.6:1.2)*D);

function residualNominate(xs,xs_block,g){
  const rms=vt=>xs_block[vt]?Math.sqrt(xs_block[vt].reduce((s,v,i)=>s+(v-(xs[i]||0))**2,0)):0;
  const devs=['discant','cantus','bass','pedal'].map(rms),maxDev=Math.max(...devs,.001);
  const nom={resurrect:devs[0]/maxDev,lent:devs[3]/maxDev};
  return g.map((v,k)=>Math.max(.001,v+.03*(nom[SK[k]]||0)*(1-v))).map((v,_,a)=>v/a.reduce((s,x)=>s+x,0));
}

const PHT={jubilate:[[.5,'interior'],[.2,'jubilate'],[.18,'precad'],[.12,'cadence']],interior:[[.33,'precad'],[.27,'interior'],[.22,'jubilate'],[.18,'cadence']],precad:[[.7,'cadence'],[.18,'interior'],[.12,'precad']],cadence:[[.5,'resolve'],[.28,'jubilate'],[.22,'interior']],resolve:[[.35,'jubilate'],[.3,'interior'],[.2,'resolve'],[.15,'cadence']]};
function nxtPh(ph){const t=PHT[ph]||PHT.interior;let r=Math.random(),c=0;for(const[p,n]of t){c+=p;if(r<c)return n;}return t[0][1];}

const MODES={'G Mixolydian':[7,9,11,0,2,4,5],'G Major':[7,9,11,0,2,4,6],'D Dorian':[2,4,5,7,9,11,0],'E Phrygian':[4,5,7,9,11,0,2],'A Aeolian':[9,11,0,2,4,5,7],'C Lydian':[0,2,4,6,7,9,11],'Bb Major':[10,0,2,3,5,7,9],'F Dorian':[5,7,8,10,0,2,3]};
const MK=Object.keys(MODES);

const VCFG=[
  {name:'S1',vtype:'discant',octRange:[4,5],amp:.48,color:'#f59e0b',pan:-.6},
  {name:'S2',vtype:'cantus', octRange:[4,5],amp:.41,color:'#fcd34d',pan:-.3},
  {name:'A1',vtype:'discant',octRange:[3,4],amp:.38,color:'#60a5fa',pan:.3},
  {name:'A2',vtype:'cantus', octRange:[3,4],amp:.34,color:'#818cf8',pan:.6},
  {name:'T1',vtype:'discant',octRange:[2,3],amp:.32,color:'#34d399',pan:-.5},
  {name:'T2',vtype:'cantus', octRange:[2,3],amp:.29,color:'#6ee7b7',pan:.5},
  {name:'B1',vtype:'bass',   octRange:[2,3],amp:.27,color:'#f87171',pan:-.2},
  {name:'B2',vtype:'pedal',  octRange:[1,2],amp:.24,color:'#fb923c',pan:.2},
];

// ════════════════════════════════════════════════════════════════════
//  III. DUAL Π+/Π- SYNTHESIS PATHS
//  Π+(t) = constraint tightening  →  bright, high-Q, short
//  Π-(t) = constraint release     →  dark, inharmonic, bloom
// ════════════════════════════════════════════════════════════════════

function pcHz(pc,oct,cents){return 261.626*Math.pow(2,(oct-4+pc/12)+cents/1200);}

function getFmts(vt,ph,sigE){
  const phS={jubilate:1,interior:.83,precad:.78,cadence:.72,resolve:.64};
  const vtB={discant:[900,1400,2800],cantus:[720,1160,2550],bass:[510,1010,2210],pedal:[410,820,1820]};
  return(vtB[vt]||vtB.cantus).map(f=>f*(phS[ph]||1)*(1+.28*Math.min(sigE||0,600)/600));
}

function playNote(ctx,mast,freq,pHz,vt,amp,dur,ph,pan,Et,sigE,trHi){
  if(!ctx||freq<28||freq>9800)return null;
  const now=ctx.currentTime,spread=cl((trHi||0)*.035,0,.65);
  const adjPan=pan*(1-spread)+(Math.random()*.5-.25)*spread;
  const pnr=ctx.createStereoPanner?ctx.createStereoPanner():null;
  if(pnr){pnr.pan.value=adjPan;pnr.connect(mast);}
  const gN=ctx.createGain();gN.connect(pnr||mast);
  const atk=vt==='pedal'?.26:vt==='bass'?.13:.07;
  gN.gain.setValueAtTime(0,now);gN.gain.linearRampToValueAtTime(amp,now+atk);
  gN.gain.setValueAtTime(amp*.88,now+Math.max(dur*.65,atk+.05));gN.gain.linearRampToValueAtTime(0,now+dur);
  const fmts=getFmts(vt,ph,sigE),et=cl(Et||0,-2,2),pEnd=now+cl(atk*1.8,.04,.18);
  const mults={discant:[1,2,3,4],cantus:[1,2,3,4],bass:[1,2,3,4],pedal:[.5,1,2,3]}[vt]||[1,2,3,4];
  const pAmps=[1,.38+et*.08,.18+et*.05,.07+et*.03];
  const oscs=mults.map((m,h)=>{
    const o=ctx.createOscillator(),sg=ctx.createGain();
    o.type=(vt==='pedal'||vt==='bass')?'sawtooth':vt==='cantus'?'triangle':'sine';
    o.frequency.setValueAtTime((pHz>0?pHz:freq)*m,now);
    o.frequency.exponentialRampToValueAtTime(freq*m,pEnd);
    sg.gain.value=pAmps[h]||.01;o.connect(sg);
    fmts.forEach((fHz,fi)=>{const ff=ctx.createBiquadFilter();ff.type='bandpass';ff.frequency.value=fHz;ff.Q.value=8+fi;const fg=ctx.createGain();fg.gain.value=fi===0?.65:fi===1?.45:.22;sg.connect(ff);ff.connect(fg);fg.connect(gN);});
    const pg=ctx.createGain();pg.gain.value=.20;sg.connect(pg);pg.connect(gN);
    o.start(now);o.stop(now+dur+.1);return o;
  });
  if(freq>180&&(vt==='discant'||vt==='cantus')){const lfo=ctx.createOscillator(),lg=ctx.createGain();lfo.frequency.value=5.1;lg.gain.value=freq*cl(.0014+et*.0007,.001,.004);lfo.connect(lg);oscs.forEach(o=>lg.connect(o.frequency));lfo.start(now+.3);lfo.stop(now+dur);}
  return{oscs,gN,pnr,stopAt:now+dur+.1};
}

// Π+ path: constraint tightening — high-Q bandpass array, sharp pink noise, short decay
function triggerPercPlus(ctx,mast,xs,Er_sp,trH,piVal){
  if(!ctx||piVal<.1)return null;
  const now=ctx.currentTime,Fs=ctx.sampleRate,dur=cl(trH*.0025,.015,.09);
  const buf=ctx.createBuffer(1,Math.floor(Fs*dur),Fs),data=buf.getChannelData(0);
  let b0=0,b1=0,b2=0;
  for(let i=0;i<data.length;i++){const wn=Math.random()*2-1;b0=.99886*b0+wn*.0555179;b1=.99332*b1+wn*.0750759;b2=.969*b2+wn*.153852;data[i]=(b0+b1+b2+wn*.5362)*.11;}
  const src=ctx.createBufferSource();src.buffer=buf;
  const env=ctx.createGain(),outG=ctx.createGain();
  env.gain.setValueAtTime(cl(piVal*.00016,.003,.40),now);
  env.gain.exponentialRampToValueAtTime(.0001,now+dur);
  outG.gain.value=.40;outG.connect(mast);
  const Q=cl(55/(1+trH*.8),6,55);
  const Em=Math.min(...Er_sp.slice(0,12));
  Er_sp.slice(0,17).forEach((e,si)=>{
    const g=Math.exp(-(e-Em)/600);if(g<.03)return;
    const f=pcHz(CHAIN[si].midi,3,si===CG?0:(xs[ci2fi(si)]||0));
    if(f<80||f>8000)return;
    const ff=ctx.createBiquadFilter();ff.type='bandpass';ff.frequency.value=f;ff.Q.value=Q;
    const wg=ctx.createGain();wg.gain.value=g*1.8;src.connect(ff);ff.connect(wg);wg.connect(env);
  });
  env.connect(outG);src.start(now);src.stop(now+dur+.02);
  return{src,env,outG,stopAt:now+dur+.05};
}

// Π- path: constraint release — inharmonic FM bloom, dark noise, slow swell, κ_proj spatial spread
function triggerPercMinus(ctx,mast,xs,Er_sp,trH,piVal,kap,qsoft){
  if(!ctx||piVal<.1)return null;
  const now=ctx.currentTime,dur=cl(trH*.01,.06,.40);
  // Inharmonic FM: carrier = soft mode pitch, modulator = slightly detuned
  const softSi=qsoft?qsoft.reduce((best,v,i)=>Math.abs(v)>Math.abs(qsoft[best])?i:best,0):CG;
  const fCarr=pcHz(CHAIN[softSi].midi,2,softSi===CG?0:(xs[ci2fi(softSi)]||0));
  if(fCarr<20||fCarr>600)return null;
  const osc=ctx.createOscillator(),mod=ctx.createOscillator(),modG=ctx.createGain();
  osc.type='sine';mod.type='sine';
  osc.frequency.value=fCarr;mod.frequency.value=fCarr*1.414;  // √2 ratio → inharmonic
  modG.gain.value=fCarr*.7;mod.connect(modG);modG.connect(osc.frequency);
  const env=ctx.createGain();
  env.gain.setValueAtTime(0,now);
  env.gain.linearRampToValueAtTime(cl(piVal*.0004,.003,.25),now+dur*.3);  // slow bloom
  env.gain.linearRampToValueAtTime(0,now+dur);
  // κ_proj controls stereo width of release
  const pnr=ctx.createStereoPanner?ctx.createStereoPanner():null;
  if(pnr){pnr.pan.value=(Math.random()-.5)*cl(kap||0,0,.9)*1.4;pnr.connect(mast);}
  const outG=ctx.createGain();outG.gain.value=.32;outG.connect(pnr||mast);
  const flt=ctx.createBiquadFilter();flt.type='lowpass';flt.frequency.value=fCarr*3;flt.Q.value=1.5;
  osc.connect(flt);flt.connect(env);env.connect(outG);
  osc.start(now);mod.start(now);osc.stop(now+dur+.05);mod.stop(now+dur+.05);
  return{oscs:[osc,mod],gN:env,pnr,stopAt:now+dur+.05};
}

function playDroneMode(ctx,mast,qsoft,xs,kap){
  if(!ctx||!mast||!qsoft)return null;
  const now=ctx.currentTime;
  const idx=qsoft.reduce((best,v,i)=>Math.abs(v)>Math.abs(qsoft[best])?i:best,0);
  const si=idx<CG?idx:idx+1;
  const freq=pcHz(CHAIN[si].midi,1,si===CG?0:(xs[idx]||0));
  if(freq<18||freq>200)return null;
  const o=ctx.createOscillator(),g=ctx.createGain(),flt=ctx.createBiquadFilter();
  o.type='sine';o.frequency.value=freq;flt.type='lowpass';flt.frequency.value=freq*2.2;flt.Q.value=1.5;
  g.gain.setValueAtTime(0,now);g.gain.linearRampToValueAtTime(cl(.06*kap,.004,.16),now+2.5);
  o.connect(flt);flt.connect(g);g.connect(mast);o.start(now);
  return{osc:o,gain:g,flt,stopAt:null,isDrone:true};
}

const SC={resurrect:'#f59e0b',hex_nat:'#3b82f6',modal:'#a78bfa',cadence:'#ef4444',liturgy:'#34d399',lent:'#64748b',passion:'#ec4899',hex_hard:'#fb923c'};
const SL={resurrect:'Resurrect',hex_nat:'Hex Nat',modal:'Modal',cadence:'Cadence',liturgy:'Liturgy',lent:'Lenten',passion:'Passion',hex_hard:'Hex Hard'};
const PHC={jubilate:'#f59e0b',interior:'#60a5fa',precad:'#a78bfa',cadence:'#ef4444',resolve:'#34d399'};
const PHL={jubilate:'Jubilate',interior:'Interior',precad:'Pre-Cad',cadence:'Cadence',resolve:'Resolve'};

// ════════════════════════════════════════════════════════════════════
//  IV. COMPONENT
// ════════════════════════════════════════════════════════════════════

export default function DyletskyGen2(){
  const[ph,   setPh]   =useState('jubilate');
  const[modeN,setModeN]=useState('G Mixolydian');
  const[play, setPlay] =useState(false);
  const[tempo,setTempo]=useState(52);
  const[sol,  setSol]  =useState(null);
  const[def,  setDef]  =useState(.35);
  const[gvec, setGvec] =useState(()=>{const g=new Array(8).fill(.03);g[0]=.79;return g;});
  const[beat, setBeat] =useState(0);
  const[vsnap,setVsnap]=useState([]);
  const[rollD,setRollD]=useState([]);
  const[En17, setEn17] =useState(new Array(17).fill(0));
  const[piPos,setPiPos]=useState(0);
  const[piNeg,setPiNeg]=useState(0);
  const[hits, setHits] =useState(0);
  const[pin,  setPin]  =useState(null);
  const[sig,  setSig]  =useState(.12);
  const[trH,  setTrH]  =useState(4);
  const[kap,  setKap]  =useState(.15);
  const[softSp,setSoftSp]=useState('G');
  const[bxs,  setBxs]  =useState({});
  const[geoVal,setGeoVal]=useState(0);  // G(γ) current value

  const sysR =useRef(null),phR=useRef('jubilate'),modeR=useRef('G Mixolydian');
  const beatR=useRef(0),tpoR=useRef(52),defR=useRef(.35);
  const gR   =useRef(new Array(8).fill(.125));
  const voiR =useRef([]),memR=useRef([]),phMemR=useRef([]);
  const pFzR =useRef(new Array(8).fill(0));
  const ctxR =useRef(null),mastR=useRef(null),actR=useRef([]);
  const seqR =useRef(null),fnR=useRef(null);
  const rcnt =useRef(0),pinR=useRef(null);
  const pJeR =useRef(0),pEmaR=useRef(0),hitsR=useRef(0);
  const d2R  =useRef(null);
  const droneR=useRef(null);
  const qsoftR=useRef(null);

  useEffect(()=>{phR.current=ph;},[ph]);
  useEffect(()=>{modeR.current=modeN;},[modeN]);
  useEffect(()=>{tpoR.current=tempo;},[tempo]);
  useEffect(()=>{pinR.current=pin;},[pin]);

  useEffect(()=>{
    const sys=buildSpelledSys();sysR.current=sys;
    d2R.current=buildGeoMat(sys.J,sys.b,sys);
    const md=MODES['G Mixolydian'];
    // Init voices in spelled space: find chain index for each midi note
    voiR.current=VCFG.map((c,i)=>{
      const targetMidi=md[i%md.length]||0;
      const si=CHAIN.findIndex(ch=>ch.midi===targetMidi&&ch.sp.length===1)||CG; // prefer natural
      return{...c,si:si>=0?si:CG,pc:targetMidi,sp:CHAIN[si>=0?si:CG].sp,oct:Math.round((c.octRange[0]+c.octRange[1])/2),cents:0,dur:4,rem:4};
    });
    memR.current=VCFG.map(()=>new Array(ML).fill(-1));
    phMemR.current=VCFG.map(()=>[]);
    const g0=new Array(8).fill(.03);g0[0]=.79;gR.current=g0;setGvec(g0);
    setSol(solve(sys.J,sys.b,w36toSpelled(mixW(g0).slice(0,36))));
  },[]);

  function ensureAudio(){
    if(!ctxR.current)ctxR.current=new(window.AudioContext||window.webkitAudioContext)();
    if(ctxR.current.state==='suspended')ctxR.current.resume();
    if(!mastR.current){
      const ctx=ctxR.current,m=ctx.createGain();m.gain.value=.44;
      const comp=ctx.createDynamicsCompressor();comp.threshold.value=-18;comp.knee.value=8;comp.ratio.value=4;comp.release.value=.4;
      const d1=ctx.createDelay(.5),d2_=ctx.createDelay(.5),fb1=ctx.createGain(),fb2=ctx.createGain(),rmx=ctx.createGain();
      d1.delayTime.value=.21;d2_.delayTime.value=.33;fb1.gain.value=.18;fb2.gain.value=.15;rmx.gain.value=.11;
      m.connect(rmx);rmx.connect(d1);d1.connect(fb1);fb1.connect(d1);d1.connect(comp);
      rmx.connect(d2_);d2_.connect(fb2);fb2.connect(d2_);d2_.connect(comp);
      m.connect(comp);comp.connect(ctx.destination);mastR.current=m;
    }
  }

  const doTick=useCallback(()=>{
    if(!sysR.current||!voiR.current.length)return;
    const{J,b}=sysR.current,p=phR.current,mn=modeR.current,md=MODES[mn]||MODES['G Mixolydian'];
    const D=defR.current,bSec=60/(tpoR.current*2);
    // Gamma flow with TRUE quadratic geodesic
    let g=flowG(gR.current,p,D,pinR.current,d2R.current);gR.current=g;setGvec(g);
    // Compute G(γ) = γᵀ D² γ for display
    const gv=d2R.current?d2R.current.reduce((s,row,r)=>s+row.reduce((s2,d,c)=>s2+d*g[r]*g[c],0),0):0;
    setGeoVal(gv);

    // Main solved solve (spelled, 16-dim)
    const w43=w36toSpelled(mixW(g));
    const res=solve(J,b,w43);setSol(res);setTrH(res.trHi);
    // Voice-block (register-specific x*)
    const xs_block=blockSolve(J,b,w43);setBxs(xs_block);

    // κ_proj + eigenmode
    const{lmax,q:qmax}=powerIter(res.H);
    const kp=kProj(res.H,lmax);setKap(kp);
    const qsoft=invPowerIter(res.Hi);qsoftR.current=qsoft;
    const softIdx=qsoft.reduce((best,v,i)=>Math.abs(v)>Math.abs(qsoft[best])?i:best,0);
    const softSi=softIdx<CG?softIdx:softIdx+1;
    setSoftSp(CHAIN[softSi]?.sp||'C');

    // Defect + temperature
    const nd=stepD(D,p);defR.current=nd;setDef(nd);setSig(sigT(nd,p));

    // Spelled energy field
    const{raw:er_sp,norm:en_sp,sigma:sigE}=normE_sp(res.xs,res.H);setEn17(en_sp);

    // Residual nomination
    gR.current=residualNominate(res.xs,xs_block,gR.current);

    ensureAudio();
    const ctx=ctxR.current,mast=mastR.current;if(!ctx||!mast)return;
    const now=ctx.currentTime;actR.current=actR.current.filter(n=>n.stopAt==null||n.stopAt>now);
    const newAct=[],rollNew=[];
    let vs=voiR.current.map(v=>Object.assign({},v));

    vs.forEach((_,vi)=>{
      const upd=Object.assign({},vs[vi]);upd.rem=vs[vi].rem-1;
      if(upd.rem>0){vs[vi]=upd;return;}
      const xs_v=xs_block[vs[vi].vtype]||res.xs;
      vs=mhStep(vi,vs,xs_v,res.xs,res.H,res.Hi,en_sp,er_sp,memR.current[vi]||[],phMemR.current[vi]||[],md,p);
      const nxt=vs[vi];
      memR.current[vi]=updMem(memR.current[vi]||[],nxt.si);
      phMemR.current[vi]=[nxt.si,...(phMemR.current[vi]||[]).slice(0,23)];
      const dur=eDur(nxt.si,en_sp,nxt.vtype,p);vs[vi]=Object.assign({},nxt,{dur,rem:dur});
      const hz=pcHz(nxt.pc,nxt.oct,nxt.cents),phz=pFzR.current[vi]||hz;pFzR.current[vi]=hz;
      const nd2=playNote(ctx,mast,hz,phz,nxt.vtype,nxt.amp,bSec*dur*.91,p,nxt.pan,en_sp[nxt.si],sigE,res.trHi);
      if(nd2)newAct.push(nd2);
      rcnt.current++;rollNew.push({t:rcnt.current,midi:nxt.oct*12+nxt.pc,dur,color:nxt.color,sp:nxt.sp||'?'});
    });

    voiR.current=vs;actR.current=actR.current.concat(newAct);
    setVsnap(vs.map((v,vi)=>({name:VCFG[vi].name,color:VCFG[vi].color,pc:v.pc,si:v.si,sp:v.sp||'?',oct:v.oct,cents:v.cents,rem:v.rem,dur:v.dur})));
    if(rollNew.length)setRollD(prev=>prev.slice(-240).concat(rollNew));

    // Π+/Π- signed energy derivative
    const Ec=jointE_midi(vs.map(v=>({si:v.si,oct:v.oct})),res.xs,res.H);
    const dE=(Ec-pJeR.current)/Math.max(bSec,.001);pJeR.current=Ec;
    const piP=Math.max(0,dE),piN=Math.max(0,-dE);
    setPiPos(piP);setPiNeg(piN);
    pEmaR.current=.08*Math.abs(dE)+.92*pEmaR.current;
    const sigma=sigT(nd,p),thr=pEmaR.current+2.5*sigma*Math.max(pEmaR.current,1);
    const pp=Math.max(0,piP-thr),pn=Math.max(0,piN-thr);
    if(pp>.1){const pnc=triggerPercPlus(ctx,mast,res.xs,er_sp,res.trHi,pp);if(pnc){newAct.push(pnc);hitsR.current++;setHits(hitsR.current);}}
    if(pn>.1){const pnc=triggerPercMinus(ctx,mast,res.xs,er_sp,res.trHi,pn,kp,qsoft);if(pnc)newAct.push(pnc);}

    const nb=(beatR.current+1)%8;beatR.current=nb;setBeat(nb);
    if(nb===0){
      if(droneR.current?.osc){try{const dn=ctx.currentTime;droneR.current.gain.gain.setTargetAtTime(0,dn,.8);droneR.current.osc.stop(dn+2);}catch(_){}}
      droneR.current=playDroneMode(ctx,mast,qsoft,res.xs,kp);
      const np=nxtPh(p);phR.current=np;setPh(np);
      phMemR.current=phMemR.current.map(pm=>pm.slice(0,12));
      if(Math.random()<.12){
        const nm=MK[Math.floor(Math.random()*MK.length)];modeR.current=nm;setModeN(nm);
        const arr=MODES[nm];
        voiR.current=voiR.current.map((v,vi)=>{
          const tgtMidi=arr[vi%arr.length]||0;
          const si=CHAIN.findIndex(ch=>ch.midi===tgtMidi&&ch.sp.length===1);
          return Object.assign({},v,{si:si>=0?si:CG,pc:tgtMidi,sp:CHAIN[si>=0?si:CG].sp,rem:1});
        });
        memR.current=VCFG.map(()=>new Array(ML).fill(-1));
        phMemR.current=VCFG.map(()=>[]);pFzR.current=new Array(8).fill(0);
      }
    }
  },[]);

  useEffect(()=>{fnR.current=doTick;},[doTick]);
  const startEng=useCallback(()=>{ensureAudio();setPlay(true);fnR.current();seqR.current=setInterval(()=>fnR.current(),60000/(tpoR.current*2));},[]);
  const stopEng=useCallback(()=>{
    setPlay(false);if(seqR.current){clearInterval(seqR.current);seqR.current=null;}
    if(droneR.current?.osc){try{droneR.current.gain.gain.setTargetAtTime(0,ctxR.current?.currentTime||0,.3);droneR.current.osc.stop((ctxR.current?.currentTime||0)+1);}catch(_){}}
    if(ctxR.current){const t=ctxR.current.currentTime;actR.current.forEach(({gN,oscs})=>{try{gN.gain.setTargetAtTime(0,t,.05);if(oscs)oscs.forEach(o=>o.stop(t+.25));}catch(_){}});actR.current=[];}
  },[]);
  useEffect(()=>{if(!play)return;if(seqR.current)clearInterval(seqR.current);seqR.current=setInterval(()=>fnR.current(),60000/(tempo*2));},[tempo,play]);
  useEffect(()=>()=>{if(seqR.current)clearInterval(seqR.current);if(ctxR.current)ctxR.current.close();},[]);

  // ── RENDER ────────────────────────────────────────────────────────

  const xs=sol?sol.xs:new Array(16).fill(0);
  const eta=sol?sol.eta:0,norm=sol?sol.norm:0,wRMS=sol?sol.wRMS:0;
  const di=gvec.indexOf(Math.max(...gvec)),domSt=SK[di]||'resurrect',scol=SC[domSt]||'#f59e0b';

  // Enharmonic asymmetry display: x*_G# - x*_Ab, x*_F# - x*_Gb, x*_C# - x*_Db etc.
  const ENHARM=[
    {sharp:'G#',flat:'Ab', si_s:14,si_f:2},
    {sharp:'F#',flat:'Gb', si_s:12,si_f:0},
    {sharp:'C#',flat:'Db', si_s:13,si_f:1},
    {sharp:'D#',flat:'Eb', si_s:15,si_f:3},
    {sharp:'A#',flat:'Bb', si_s:16,si_f:4},
  ];
  const enhArr=ENHARM.map(({sharp,flat,si_s,si_f})=>{
    const cs=si_s===CG?0:(xs[ci2fi(si_s)]||0),cf=si_f===CG?0:(xs[ci2fi(si_f)]||0);
    return{sharp,flat,cs,cf,div:cs-cf};
  });

  // Ring (12 collapsed pcs, averaged over enharmonics)
  const CX=108,CY=108,RI=50,RO=86;
  const pAng=pc=>(pc/12)*2*Math.PI-Math.PI/2;
  function arcD(pc,e){
    const a0=pAng(pc)-Math.PI/12+.06,a1=pAng(pc)+Math.PI/12-.06,r=cl(RI+(RO-RI)*cl(.5-e*.25,.05,.95),RI+3,RO);
    const x0=CX+RI*Math.cos(a0),y0=CY+RI*Math.sin(a0),x1=CX+r*Math.cos(a0),y1=CY+r*Math.sin(a0);
    const x2=CX+r*Math.cos(a1),y2=CY+r*Math.sin(a1),x3=CX+RI*Math.cos(a1),y3=CY+RI*Math.sin(a1);
    return`M${x0},${y0}L${x1},${y1}A${r},${r}0,0,1,${x2},${y2}L${x3},${y3}A${RI},${RI}0,0,0,${x0},${y0}Z`;
  }
  const PCN=['C','C#','D','Eb','E','F','F#','G','Ab','A','Bb','B'];
  // Collapse 17-note energy to 12-pc for ring display
  const en12=Array.from({length:12},(_,midi)=>{
    const matching=CHAIN.map((ch,si)=>({si,e:En17[si]||0})).filter(x=>CHAIN[x.si].midi===midi);
    return matching.length?matching.reduce((s,x)=>s+x.e,0)/matching.length:0;
  });

  const arcArr=Array.from({length:12},(_,pc)=>{
    const c=pc===0?0:(xs[ci2fi(CHAIN.findIndex(ch=>ch.midi===pc&&ch.sp.length===1)||CG)]||0);
    const e=en12[pc]||0,here=vsnap.some(v=>v.pc===pc);
    return{pc,c,e,here,d:arcD(pc,e)};
  });
  const dotArr=vsnap.map((v,vi)=>{const a=pAng(v.pc),r3=cl(RI+4+vi*3.5,RI+3,RO-4);return{vi,cx:CX+r3*Math.cos(a),cy:CY+r3*Math.sin(a),color:v.color,fresh:v.rem===v.dur};});
  const lblArr=Array.from({length:12},(_,pc)=>{const a=pAng(pc),lr=RO+12,act=vsnap.some(v=>v.pc===pc);return{pc,x:CX+lr*Math.cos(a),y:CY+lr*Math.sin(a),act};});
  const rCol=(e,c)=>`hsl(${c>0?38:218},80%,${cl(54-cl(e/2,-1,1)*16,22,70)}%)`;

  const RW=385,RH=170,MLO=24,MHI=84;
  const rs=rollD.slice(-100),maxT=rs.length?rs[rs.length-1].t:1;
  const rollY=m=>RH-((m-MLO)/(MHI-MLO))*RH,rollX=t=>((t-(maxT-100))/100)*RW;
  const gridArr=Array.from({length:11},(_,i)=>{const m=MLO+Math.round(i*(MHI-MLO)/10);return{m,y:rollY(m),isC:m%12===0};});
  const rollArr=rs.map((ev,i)=>({i,y:rollY(ev.midi)-3,x:rollX(ev.t),bw:cl((ev.dur/100)*RW*.86,2,70),op:cl(.08+(100-(maxT-ev.t))/100*.92,.06,1),color:ev.color}));
  const memArr=Array.from({length:12},(_,pc)=>{const tm=memR.current.reduce((s,m)=>s+(m||[]).reduce((a,x,j)=>a+(CHAIN[x]?.midi===pc?Math.pow(MR,j+1):0),0),0);return{pc,heat:cl(tm/3,0,1),tm};});

  const card={background:'#0d1117',borderRadius:6,padding:9,border:'1px solid #21262d'};
  const mono='JetBrains Mono,Fira Code,monospace';

  return (
    <div style={{background:'#080a0d',minHeight:'100vh',color:'#c9d1d9',fontFamily:mono,padding:'12px'}}>

      <div style={{display:'flex',alignItems:'center',gap:10,marginBottom:9,flexWrap:'wrap'}}>
        <div>
          <div style={{fontSize:7,letterSpacing:3,color:'#3d4451'}}>DYLETSKY PSG — J_spelled 43x16 | GEODESIC G(y)=y^T D2 y | DUAL Pi+/Pi-</div>
          <div style={{fontSize:14,fontWeight:700,color:'#e6edf3'}}>
            <span style={{color:scol}}>dS</span>
            <span style={{fontSize:8,color:'#484f58',marginLeft:8}}>G# ≠ Ab by construction · ∇G projected onto simplex tangent · two synthesis paths</span>
          </div>
        </div>
        <div style={{marginLeft:'auto',display:'flex',alignItems:'center',gap:9}}>
          <span style={{fontSize:8,color:'#484f58'}}>{tempo}bpm</span>
          <input type="range" min={36} max={88} value={tempo} onChange={e=>setTempo(+e.target.value)} style={{width:64,accentColor:scol}}/>
          <button onClick={play?stopEng:startEng} style={{background:play?'#161b22':scol,color:play?'#8b949e':'#0d1117',border:'none',borderRadius:4,padding:'5px 16px',fontSize:12,fontWeight:700,cursor:'pointer'}}>
            {play?'STOP':'GENERATE'}
          </button>
        </div>
      </div>

      <div style={{display:'grid',gridTemplateColumns:'212px 150px 1fr 178px',gap:8,marginBottom:8}}>

        {/* Ring — shows collapsed 12-PC energies */}
        <div style={card}>
          <div style={{fontSize:7,color:'#3d4451',letterSpacing:2,marginBottom:2}}>SPELLED FIELD (12-PC collapsed)</div>
          <svg width={208} height={212} viewBox="0 0 208 212">
            <circle cx={CX} cy={CY} r={RI-3} fill="none" stroke="#12161d" strokeWidth={28}/>
            {arcArr.map(({pc,c,e,here,d})=>(
              <path key={pc} d={d} fill={rCol(e,c)} opacity={here?1:.45}/>
            ))}
            {dotArr.map(({vi,cx,cy,color,fresh})=>(
              <circle key={vi} cx={cx} cy={cy} r={fresh?3.2:2} fill={color} opacity={.92}/>
            ))}
            {lblArr.map(({pc,x,y,act})=>(
              <text key={pc} x={x} y={y} textAnchor="middle" dominantBaseline="middle" fontSize={act?9.5:7.5} fill={act?scol:'#484f58'} fontWeight={act?700:400}>{PCN[pc]}</text>
            ))}
            <text x={CX} y={CY-14} textAnchor="middle" fontSize={9} fill={scol} fontWeight={700}>{SL[domSt]}</text>
            <text x={CX} y={CY} textAnchor="middle" fontSize={7} fill="#484f58">{`eta=${eta.toFixed(0)} ||x*||=${norm.toFixed(1)}`}</text>
            <text x={CX} y={CY+12} textAnchor="middle" fontSize={7} fill={PHC[ph]||'#6b7280'}>{PHL[ph]}</text>
            <text x={CX} y={CY+24} textAnchor="middle" fontSize={6.5} fill={`hsl(${cl(kap*600,0,300)},80%,60%)`}>{`k=${kap.toFixed(3)} q->${softSp}`}</text>
          </svg>
          <div style={{display:'flex',gap:2,marginTop:2}}>
            {Array.from({length:8},(_,i)=>(
              <div key={i} style={{height:3,flex:1,borderRadius:1,background:i<beat?scol:i===beat?'#e6edf3':'#21262d',transition:'background .06s'}}/>
            ))}
          </div>
        </div>

        {/* Gamma + geodesic + percussion */}
        <div style={card}>
          <div style={{fontSize:7,color:'#3d4451',letterSpacing:2,marginBottom:5}}>GAMMA FLOW + G(y)</div>
          {SK.map((s,k)=>{
            const gk=gvec[k]||0,act=pin===s;
            return (
              <div key={s} onClick={()=>setPin(pin===s?null:s)} style={{display:'flex',alignItems:'center',gap:3,marginBottom:2.5,cursor:'pointer'}}>
                <span style={{fontSize:6.5,color:act?SC[s]:'#484f58',width:50,flexShrink:0,textDecoration:act?'underline':'none'}}>{SL[s]}</span>
                <div style={{flex:1,height:6,background:'#21262d',borderRadius:2,overflow:'hidden'}}>
                  <div style={{height:'100%',background:SC[s],width:`${cl(gk*100,0,100)}%`,transition:'width .3s'}}/>
                </div>
                <span style={{fontSize:6,color:SC[s],width:20,textAlign:'right'}}>{(gk*100).toFixed(0)}%</span>
              </div>
            );
          })}
          <div style={{fontSize:6,color:'#3d4451',marginBottom:5}}>click=pin · mu=0.04 geodesic repulsion</div>
          <div style={{display:'flex',justifyContent:'space-between',fontSize:6.5,marginBottom:5}}>
            <span style={{color:'#484f58'}}>G(y)=</span>
            <span style={{color:`hsl(${cl(geoVal*20,0,120)},80%,55%)`}}>{geoVal.toFixed(1)}</span>
          </div>
          <div style={{borderTop:'1px solid #21262d',paddingTop:6}}>
            <div style={{fontSize:7,color:'#3d4451',letterSpacing:2,marginBottom:3}}>Pi+ tighten</div>
            <div style={{height:5,background:'#21262d',borderRadius:2,marginBottom:2,overflow:'hidden'}}>
              <div style={{height:'100%',background:'#f87171',width:`${cl(Math.log10(Math.max(piPos,1))/6*100,0,100)}%`,transition:'width .12s'}}/>
            </div>
            <div style={{fontSize:7,color:'#3d4451',letterSpacing:2,marginBottom:2}}>Pi- release (FM)</div>
            <div style={{height:5,background:'#21262d',borderRadius:2,marginBottom:4,overflow:'hidden'}}>
              <div style={{height:'100%',background:'#818cf8',width:`${cl(Math.log10(Math.max(piNeg,1))/6*100,0,100)}%`,transition:'width .12s'}}/>
            </div>
            <div style={{fontSize:6,color:'#3d4451'}}>{`hits=${hits} trH=${trH.toFixed(1)} k=${kap.toFixed(3)}`}</div>
          </div>
        </div>

        {/* Roll + voice strip */}
        <div style={card}>
          <div style={{fontSize:7,color:'#3d4451',letterSpacing:2,marginBottom:4}}>PIANO ROLL — SPELLED (G# ≠ Ab in x*)</div>
          <svg width="100%" height={RH} viewBox={`0 0 ${RW} ${RH}`} style={{background:'#080a0d',borderRadius:4,display:'block'}}>
            {gridArr.map(({m,y,isC})=>(
              <g key={m}>
                <line x1={0} y1={y} x2={RW} y2={y} stroke={isC?'#21262d':'#0e1015'} strokeWidth={isC?.8:.35}/>
                {isC&&<text x={2} y={y-2} fontSize={6} fill="#3d4451">{PCN[m%12]}{Math.floor(m/12)-1}</text>}
              </g>
            ))}
            {rollArr.map(({i,y,x,bw,op,color})=>(
              <rect key={i} x={x} y={y} width={bw} height={6} rx={1.5} fill={color} opacity={op}/>
            ))}
            {piPos>.1&&<rect x={rollX(maxT)-2} y={RH-7} width={4} height={7} fill="#f87171" opacity={.85} rx={1}/>}
            {piNeg>.1&&<rect x={rollX(maxT)+2} y={RH-7} width={4} height={7} fill="#818cf8" opacity={.85} rx={1}/>}
            <line x1={rollX(maxT)} y1={0} x2={rollX(maxT)} y2={RH} stroke="#ffffff18" strokeWidth={1}/>
          </svg>
          <div style={{display:'grid',gridTemplateColumns:'repeat(8,1fr)',gap:2,marginTop:4}}>
            {VCFG.map((cfg,vi)=>{
              const v=vsnap[vi],pct=v?cl(((v.dur-v.rem+1)/Math.max(v.dur,1))*100,0,100):0;
              const e=v?(En17[v.si]||0):0;
              return (
                <div key={vi} style={{background:'#0d1117',borderRadius:3,padding:'2px',border:`1px solid ${cfg.color}36`,textAlign:'center'}}>
                  <div style={{fontSize:6.5,color:cfg.color,fontWeight:700}}>{cfg.name}</div>
                  <div style={{fontSize:7,color:'#8b949e'}}>{v?v.sp||'?':'?'}{v?v.oct:4}</div>
                  <div style={{fontSize:6,color:`hsl(${e<0?140:e>1?0:60},70%,55%)`}}>{e>=0?'+':''}{e.toFixed(1)}</div>
                  <div style={{fontSize:5.5,color:'#818cf8'}}>{v?v.cents.toFixed(0):'0'}c</div>
                  <div style={{height:2,background:'#21262d',borderRadius:1,marginTop:1}}>
                    <div style={{height:'100%',background:cfg.color,width:`${pct}%`,transition:'width .12s'}}/>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Invariants */}
        <div style={{display:'flex',flexDirection:'column',gap:7}}>
          <div style={card}>
            <div style={{fontSize:7,color:'#3d4451',letterSpacing:2,marginBottom:5}}>INVARIANTS (16-dim)</div>
            {[
              {l:'eta',      v:eta,                c:'#f59e0b',max:280,f:v=>v.toFixed(0)},
              {l:'||x*||16', v:norm,               c:'#60a5fa',max:30, f:v=>v.toFixed(2)},
              {l:'wRMS',     v:wRMS,               c:'#a78bfa',max:18, f:v=>v.toFixed(3)},
              {l:'D_mus',    v:def,                c:'#34d399',max:3,  f:v=>v.toFixed(4)},
              {l:'sigma(D)', v:sol?sigT(def,ph):0, c:'#ec4899',max:.5, f:v=>v.toFixed(4)},
              {l:'tr(H-1)',  v:trH,                c:'#6ee7b7',max:24, f:v=>v.toFixed(2)},
              {l:'k_proj',   v:kap,                c:'#818cf8',max:1,  f:v=>v.toFixed(4)},
              {l:'G(y)',     v:geoVal,             c:'#fb923c',max:200,f:v=>v.toFixed(1)},
              {l:'Gamma(d)', v:gjt(cl((norm-8)/14,-.85,.85)),c:'#3b82f6',max:1.6,f:v=>v.toFixed(4)},
            ].map(({l,v,c,max,f})=>(
              <div key={l} style={{marginBottom:3.5}}>
                <div style={{display:'flex',justifyContent:'space-between',alignItems:'baseline'}}>
                  <span style={{fontSize:7,color:'#484f58'}}>{l}</span>
                  <span style={{fontSize:9.5,color:c,fontWeight:700}}>{f(v)}</span>
                </div>
                <div style={{height:2,background:'#21262d',borderRadius:1,marginTop:1}}>
                  <div style={{height:'100%',background:c,width:`${cl(Math.abs(v)/max*100,0,100)}%`,transition:'width .4s'}}/>
                </div>
              </div>
            ))}
          </div>
          <div style={card}>
            <div style={{fontSize:7,color:'#3d4451',letterSpacing:2,marginBottom:5}}>ENHARMONIC ASYMMETRY x*_sharp - x*_flat</div>
            {enhArr.map(({sharp,flat,cs,cf,div})=>(
              <div key={sharp} style={{display:'flex',alignItems:'center',gap:4,marginBottom:3}}>
                <span style={{fontSize:6.5,color:'#60a5fa',width:16}}>{sharp}</span>
                <span style={{fontSize:6,color:'#3d4451'}}>vs</span>
                <span style={{fontSize:6.5,color:'#818cf8',width:16}}>{flat}</span>
                <div style={{flex:1,height:5,background:'#21262d',borderRadius:2,overflow:'hidden',position:'relative'}}>
                  <div style={{position:'absolute',left:'50%',top:0,height:'100%',width:`${cl(Math.abs(div)/20*50,0,50)}%`,background:div>0?'#60a5fa':'#818cf8',transform:div>0?'none':'translateX(-100%)'}}/>
                </div>
                <span style={{fontSize:6,color:div>0?'#60a5fa':'#818cf8',width:28,textAlign:'right'}}>{div>=0?'+':''}{div.toFixed(1)}c</span>
              </div>
            ))}
            <div style={{fontSize:6,color:'#3d4451',marginTop:3}}>blue=sharp↑ · purple=flat↓</div>
          </div>
          <div style={card}>
            <div style={{fontSize:7,color:'#3d4451',letterSpacing:2,marginBottom:4}}>PHRASE + MODAL</div>
            {Object.keys(PHL).map(p=>(
              <div key={p} style={{display:'flex',alignItems:'center',gap:4,padding:'2px 4px',borderRadius:3,marginBottom:2,background:ph===p?PHC[p]+'14':'transparent',border:`1px solid ${ph===p?PHC[p]:'transparent'}`}}>
                <div style={{width:5,height:5,borderRadius:'50%',background:ph===p?PHC[p]:'#21262d'}}/>
                <span style={{fontSize:7.5,color:ph===p?PHC[p]:'#484f58'}}>{PHL[p]}</span>
              </div>
            ))}
            <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:2,marginTop:5}}>
              {MK.map(m=>(
                <div key={m} onClick={()=>{setModeN(m);modeR.current=m;}} style={{fontSize:6.5,padding:'2px 3px',borderRadius:3,cursor:'pointer',background:modeN===m?'#21262d':'transparent',color:modeN===m?'#e6edf3':'#484f58'}}>{m}</div>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div style={Object.assign({},card,{marginBottom:5})}>
        <div style={{fontSize:7,color:'#3d4451',letterSpacing:2,marginBottom:4}}>MEMORY Mv(si) in spelled space — rho=0.72 L=8 + phase L=24</div>
        <div style={{display:'grid',gridTemplateColumns:'repeat(12,1fr)',gap:3}}>
          {memArr.map(({pc,heat,tm})=>(
            <div key={pc} style={{textAlign:'center'}}>
              <div style={{fontSize:6,color:'#484f58'}}>{PCN[pc]}</div>
              <div style={{height:10,background:'#21262d',borderRadius:2,margin:'2px 0',overflow:'hidden',display:'flex',alignItems:'flex-end'}}>
                <div style={{width:'100%',height:`${heat*100}%`,background:`hsl(0,${cl(heat*85,0,90)}%,55%)`}}/>
              </div>
              <div style={{fontSize:5.5,color:`hsl(0,${cl(heat*85,0,90)}%,60%)`}}>{tm.toFixed(1)}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
