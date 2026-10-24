"""Rebuild headless modules from byte-preserved user source archives.
No third-party Python packages. Node modules have no React/Three dependency.
"""
from pathlib import Path
import hashlib, json
ROOT=Path(__file__).resolve().parent

def main():
    v6=(ROOT/'archive/dyletsky_v6_fixed.jsx').read_text()
    gen=(ROOT/'archive/dyletsky_gen2_3.jsx').read_text()
    v6core=v6[v6.index("const PC="):v6.index('function setupChurch(')]
    inverse=v6[v6.index('function sparseInvert('):v6.index('export default function DyletskyV6')]
    v6exports=['PC','N','QCM','SP17','SP17_PC','SP17_DIA','PRIM_OPS','STRAT_ALGEBRA',
               'buildJ17','algebraicWeight','spelledTarget','solve_n','computeSpelled',
               'EIGENMODES','GAMMA','VOICE_PROFILES','PH_STRAT','SCORE8','toHz','sparseInvert']
    (ROOT/'v6_core.mjs').write_text('// Source-preserving pure core; see source_provenance.json.\n'+v6core+'\n'+inverse+'\nexport { '+', '.join(v6exports)+' };\n')
    gencore=gen[gen.index('const CHAIN='):gen.index('export default function DyletskyGen2')]
    n_random=gencore.count('Math.random()')
    gencore=gencore.replace('Math.random()', 'nextRandom()')
    rng='''// Only numerical change to source extraction: injected seedable PRNG.
let rngState=20261024;
function setSeed(seed){if(!Number.isInteger(seed))throw Error('Integer seed required');rngState=seed>>>0;}
function nextRandom(){let t=rngState+=0x6D2B79F5;t=Math.imul(t^(t>>>15),t|1);t^=t+Math.imul(t^(t>>>7),t|61);return((t^(t>>>14))>>>0)/4294967296;}
'''
    genexports=['CHAIN','CG','ci2fi','buildSpelledSys','chol','fwdBack','cholInv','powerIter','invPowerIter',
                'SK','pureW36','w36toSpelled','solve','mixW','eVec','pcE_sp','normE_sp','hinvW_sp',
                'geomCost_sp','jointE_midi','VREG','applyVreg43','blockSolve','buildGeoMat','geoGradient','flowG',
                'ML','MR','MLM','MLM_PH','MR_PH','updMem','memPen','phaseMemPen','mhStep','eDur',
                'stepD','sigT','residualNominate','nxtPh','MODES','MK','VCFG','pcHz',
                'playNote','triggerPercPlus','triggerPercMinus','playDroneMode','setSeed','nextRandom']
    (ROOT/'gen2_core.mjs').write_text(rng+gencore+'\nexport { '+', '.join(genexports)+' };\n')
    provenance={
      'v6':{'library_file_id':'libfile_10e997b6fa4481918adc5c45ef5e6a88',
            'original_name':'dyletsky_v6_fixed.jsx','sha256':hashlib.sha256((ROOT/'archive/dyletsky_v6_fixed.jsx').read_bytes()).hexdigest(),
            'extraction':'Pure declarations before setupChurch plus sparseInvert; numerical expressions unchanged.'},
      'gen2':{'library_file_id':'libfile_e044b8c722d081918e116b5db6abab9c',
              'original_name':'dyletsky_gen2 (3).jsx','sha256':hashlib.sha256((ROOT/'archive/dyletsky_gen2_3.jsx').read_bytes()).hexdigest(),
              'extraction':'Pure declarations before React component; Math.random() replaced with nextRandom() for replay.',
              'random_call_sites_replaced':n_random},
      'scope':'Static pure-function parity tested. New headless scheduler is an adaptation, not a bit-for-bit replay of browser/audio timing or all audio-side random draws.'}
    (ROOT/'source_provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
    print(json.dumps({'extracted':['v6_core.mjs','gen2_core.mjs'],'random_sites':n_random}))

if __name__=='__main__':main()
