"""Independent Fraction and augmented-least-squares checks of exported engines.

This verifier imports no recovered JavaScript solver and does not call Node.
It reconstructs both interval systems from their declared note conventions,
forms exact normal equations over Fraction, and independently solves an
augmented least-squares problem with NumPy. Checks concern musical algebra,
not mechanical energy, historical authenticity, or hardware performance.
"""
from __future__ import annotations

from collections import Counter
from fractions import Fraction as Q
import hashlib
import json
import math
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
RIDGE = Q(1, 125)
SP17 = ['C','Db','C#','D','Eb','D#','E','F','Gb','F#','G','Ab','G#','A','Bb','A#','B']
CHAIN = ['Gb','Db','Ab','Eb','Bb','F','C','G','D','A','E','B','F#','C#','G#','D#','A#']
BASE_PC = dict(zip('CDEFGAB', [0, 2, 4, 5, 7, 9, 11]))
LETTER = dict(zip('CDEFGAB', range(7)))
HARD = set(['G','G#','A','A#','B','C'])
SOFT = set(['F','Gb','Ab','Bb','C','Db'])
NATURAL = set('CDEFGAB')


def pc(note):
    return (BASE_PC[note[0]] + note.count('#') - note.count('b')) % 12


def exact_rank(rows):
    a = [[Q(v) for v in row] for row in rows]
    rank = 0
    for col in range(len(a[0])):
        pivot = next((i for i in range(rank, len(a)) if a[i][col]), None)
        if pivot is None:
            continue
        a[rank], a[pivot] = a[pivot], a[rank]
        p = a[rank][col]
        a[rank] = [x / p for x in a[rank]]
        for i in range(rank + 1, len(a)):
            f = a[i][col]
            if f:
                a[i] = [x - f*y for x, y in zip(a[i], a[rank])]
        rank += 1
        if rank == len(a):
            break
    return rank


def determinant(rows):
    """Integer Bareiss determinant, separate from Fraction linear solving."""
    a = [list(map(int, r)) for r in rows]
    den, sign = 1, 1
    for k in range(len(a) - 1):
        if not a[k][k]:
            pivot = next((i for i in range(k + 1, len(a)) if a[i][k]), None)
            if pivot is None:
                return 0
            a[k], a[pivot] = a[pivot], a[k]
            sign *= -1
        p = a[k][k]
        for i in range(k + 1, len(a)):
            for j in range(k + 1, len(a)):
                num = a[i][j]*p - a[i][k]*a[k][j]
                assert num % den == 0
                a[i][j] = num // den
            a[i][k] = 0
        den = p
    return sign*a[-1][-1]


def gram(rows):
    return [[sum(r[i]*r[j] for r in rows) for j in range(len(rows[0]))]
            for i in range(len(rows[0]))]


def solve_exact(a, rhs):
    """Independent Gaussian elimination/back substitution, exact rationals."""
    a = [[Q(v) for v in row] + [Q(b)] for row, b in zip(a, rhs)]
    n = len(a)
    for k in range(n):
        p = next(i for i in range(k, n) if a[i][k])
        a[p], a[k] = a[k], a[p]
        for i in range(k + 1, n):
            factor = a[i][k]/a[k][k]
            if factor:
                for j in range(k + 1, n + 1):
                    a[i][j] -= factor*a[k][j]
                a[i][k] = Q(0)
    x = [Q(0)]*n
    for i in reversed(range(n)):
        x[i] = (a[i][-1] - sum(a[i][j]*x[j] for j in range(i + 1, n)))/a[i][i]
    return x


def rebuild_v6():
    rows, labels, target = [], [], []
    # The legacy m3 spelling rule intentionally uses one letter step.
    for family, semitone, letters in [('M3',4,2), ('m3',3,1), ('P5',7,4)]:
        for i, source in enumerate(SP17):
            for j, end in enumerate(SP17):
                if ((pc(end)-pc(source)) % 12 != semitone or
                    (LETTER[end[0]]-LETTER[source[0]]) % 7 != letters):
                    continue
                row = [0]*17
                row[i], row[j] = -1, 1
                rows.append(row)
                labels.append((family, source, end))
                b = {'M3':Q('-13.686'), 'm3':Q('10.265'), 'P5':Q('-3.422')}[family]
                if family == 'M3':
                    if '#' in source and '#' not in end:
                        b -= Q('.8')
                    elif 'b' in end and 'b' not in source:
                        b += Q('.8')
                elif family == 'P5' and len(source) == len(end) == 1:
                    b += Q('.4')
                target.append(b)
    return rows, labels, target


def v6_weights(ops, labels):
    """Evaluate exported declarative primitive menu, independently of JS."""
    weights = []
    for family, source, end in labels:
        value = Q(1)
        for item in ops:
            op, p = item['op'], item['p']
            if op == 'KEY':
                allowed = set(p.get('key', [0,2,4,5,7,9,11]))
                yes = pc(source) in allowed and pc(end) in allowed
                factor = p.get('w', 3)
            elif op == 'CAD':
                yes = pc(end) in p.get('finals', [7,2,4,5])
                factor = p.get('w', 5)
            elif op == 'HEX':
                allowed = {'hard':HARD, 'soft':SOFT, 'nat':NATURAL}[p.get('sector', 'nat')]
                yes = source in allowed and end in allowed
                factor = p.get('w', 3)
            elif op == 'CON':
                yes = family in p.get('fams', ['P5','M3'])
                factor = p.get('w', 2)
            elif op == 'VL':
                yes = family == 'm3'
                factor = p.get('w', 2.5)
            else:
                raise AssertionError('Unexpected primitive '+op)
            if yes:
                value *= Q(str(factor))
        weights.append(value)
    return weights


def rebuild_gen2():
    full, target, labels = [], [], []
    for family, pairs, b in [
        ('P5', [(k,k+1) for k in range(16)], Q('1.955')),
        ('M3', [(k,k+4) for k in range(13)], Q('-13.686')),
        ('m3', [(k,k-3) for k in range(3,17)], Q('15.641')),
    ]:
        for i, j in pairs:
            row = [0]*17
            row[i], row[j] = -1, 1
            full.append(row)
            labels.append((family, CHAIN[i], CHAIN[j]))
            target.append(b)
    reduced = [r[:6] + r[7:] for r in full]
    return full, reduced, labels, target


def gen2_weights(strategy):
    hn, hh, hs = set([0,2,4,5,7,9]), set([0,2,4,7,9,11]), set([0,2,5,7,9,10])
    vals = []
    for step in [7,4,3]:
        family = []
        for p in range(12):
            end = (p + step) % 12
            natural, hard, soft = (p in sector and end in sector for sector in [hn,hh,hs])
            w = Q(1)
            if strategy == 'hex_nat':
                w = Q(3) if natural else Q(1)
            elif strategy == 'hex_hard':
                w = Q(5) if hard else Q(1)
            elif strategy == 'modal':
                w = Q(5) if end in [2,4,5,7] else Q(1)
            elif strategy == 'resurrect':
                w = Q(8) if hard and end in [2,4,5,7] else Q(4) if hard else Q(1)
            elif strategy == 'cadence':
                w = Q(5) if end in [4,7,11] else Q(1)
            elif strategy == 'liturgy':
                w = {4:Q('3.75'),3:Q(3),7:Q('1.5')}[step] if natural else {4:Q('2.5'),3:Q(2),7:Q(1)}[step]
            elif strategy == 'lent':
                w = {3:Q(6),7:Q(3),4:Q('.7')}[step] if soft else {3:Q('2.5'),4:Q('.7'),7:Q('1.5')}[step]
            elif strategy == 'passion':
                w = {3:Q(7),7:Q('2.5'),4:Q('.5')}[step] if soft else {3:Q(3),4:Q('.5'),7:Q('1.2')}[step]
            else:
                raise AssertionError('Unexpected Gen2 strategy '+strategy)
            family.append(w)
        vals.append(max(Q('.5'), sum(family)/12))
    return [vals[0]]*16 + [vals[1]]*13 + [vals[2]]*14


def check_solution(rows, b, w, exported_x):
    n = len(rows[0])
    h = [[sum(w[k]*r[i]*r[j] for k,r in enumerate(rows)) + (RIDGE if i == j else 0)
          for j in range(n)] for i in range(n)]
    f = [sum(w[k]*r[j]*b[k] for k,r in enumerate(rows)) for j in range(n)]
    exact = solve_exact(h, f)
    assert all(sum(h[i][j]*exact[j] for j in range(n)) == f[i] for i in range(n))
    jf, bf, wf = np.array(rows, dtype=float), np.array(b, dtype=float), np.array(w, dtype=float)
    source = np.array(exported_x, dtype=float)
    aug = np.vstack([np.sqrt(wf)[:,None]*jf, math.sqrt(float(RIDGE))*np.eye(n)])
    rhs = np.concatenate([np.sqrt(wf)*bf, np.zeros(n)])
    lstsq, _, rank, _ = np.linalg.lstsq(aug, rhs, rcond=None)
    xf = np.array(exact, dtype=float)
    max_diff = float(np.max(np.abs(source-xf)))
    assert max_diff < 1e-9
    assert float(np.max(np.abs(lstsq-xf))) < 1e-9 and rank == n
    res = jf@source-bf
    normal = jf.T@(wf*res)+float(RIDGE)*source
    wrms = float(np.sqrt(np.dot(wf, res*res)/wf.sum()))
    legacy = float(np.sqrt(np.dot(wf*wf, res*res)/wf.sum()))
    # Quadratic stationarity: F(x+d)-F(x) = d^T H d at the optimum.
    delta = np.array([(-1)**i*(i+1)/17 for i in range(n)])
    energy = lambda x: float(np.dot(wf, (jf@x-bf)**2)+float(RIDGE)*np.dot(x,x))
    gap_error = abs(energy(source+delta)-energy(source)-float(delta@np.array(h,dtype=float)@delta))
    assert gap_error < 1e-7
    assert float(np.linalg.norm(normal)) < 1e-8
    return {'source_vs_exact_solution_max_abs_cents':max_diff,
            'numpy_augmented_lstsq_max_abs_cents':float(np.max(np.abs(lstsq-xf))),
            'normal_equation_residual_l2':float(np.linalg.norm(normal)),
            'conventional_weighted_RMS':wrms, 'legacy_squared_weight_RMS':legacy,
            'regularized_objective':energy(source),
            'quadratic_energy_gap_identity_error':gap_error,
            'regularized_normal_matrix_min_eigenvalue':float(np.linalg.eigvalsh(np.array(h,dtype=float))[0]),
            'arithmetic_scope':'exact rational nominal coefficients; exported JS result checked numerically',
            'energy_scope':'weighted musical objective; not joules'}


def main():
    audit_path = ROOT/'output/engine_audit.json'
    audit = json.loads(audit_path.read_text())
    vfull, vlabels, vb = rebuild_v6()
    assert vfull == audit['matrices']['v6']['rows']
    for rebuilt, exported in zip(vlabels, audit['matrices']['v6']['labels']):
        assert rebuilt == (exported['fam'],exported['sn'],exported['en'])
    vj = [r[1:] for r in vfull]
    gfull, gj, glabels, gb = rebuild_gen2()
    assert gj == audit['matrices']['gen2']['J']
    assert np.max(np.abs(np.array(gb,dtype=float)-audit['matrices']['gen2']['b'])) < 1e-14
    report = {'schema':'fusion.dyletsky-algebra-verification/1', 'passed':True,
              'input_sha256':hashlib.sha256(audit_path.read_bytes()).hexdigest(),
              'method':'Independent note-rule reconstruction, Fraction Gaussian solve, integer Bareiss determinant, NumPy augmented least squares. No JS solver imported.',
              'ridge_exact':'1/125', 'matrices':{}, 'v6':{}, 'gen2':{}}
    for name, full, reduced, labels in [('v6',vfull,vj,vlabels),('gen2',gfull,gj,glabels)]:
        det = determinant(gram(reduced))
        assert all(sum(r)==0 and sorted(x for x in r if x)==[-1,1] for r in full)
        assert exact_rank(full)==exact_rank(reduced)==16
        report['matrices'][name] = {'full_shape':[len(full),17], 'gauge_fixed_shape':[len(reduced),16],
            'gauge_note':'C', 'basis':SP17 if name=='v6' else CHAIN,
            'rank_exact':16, 'nullity_before_gauge_exact':1,
            'unweighted_reduced_gram_determinant_exact':str(det),
            'family_counts':dict(Counter(t[0] for t in labels))}
    assert report['matrices']['v6']['unweighted_reduced_gram_determinant_exact']=='508958496'
    assert report['matrices']['gen2']['unweighted_reduced_gram_determinant_exact']=='3564531008'
    for strategy, source in audit['v6'].items():
        assert source['basis']==SP17 and source['xf17'][0]==0
        x=source['xf17']
        w=v6_weights(source['opDecomposition'],vlabels)
        result=check_solution(vj,vb,w,x[1:])
        assert abs(result['conventional_weighted_RMS']-source['conventional_weighted_RMS'])<1e-10
        assert abs(result['legacy_squared_weight_RMS']-source['legacy_wRMS'])<1e-10
        projected=[sum(x[i] for i,s in enumerate(SP17) if pc(s)==p)/sum(pc(s)==p for s in SP17) for p in range(12)]
        assert np.max(np.abs(np.array(projected)-source['xf12']))<1e-12
        for key,value in source['enhDiff'].items():
            sharp,flat=key.split('/')
            assert abs(x[SP17.index(sharp)]-x[SP17.index(flat)]-value)<1e-12
        result['gauge_projection_and_enharmonic_checks']=True
        report['v6'][strategy]=result
    for strategy, source in audit['gen2'].items():
        assert source['basis']==CHAIN and source['offsets_by_spelling']['C']==0
        w=gen2_weights(strategy)
        assert np.max(np.abs(np.array(w,dtype=float)-source['weights']))<1e-12
        free=source['offsets_free']
        assert all(free[i if i<6 else i-1]==source['offsets_by_spelling'][s] for i,s in enumerate(CHAIN) if i!=6)
        result=check_solution(gj,gb,w,free)
        assert abs(result['conventional_weighted_RMS']-source['weighted_RMS'])<1e-10
        result['exact_family_weights']=[str(w[i]) for i in [0,16,29]]
        result['gauge_spelling_and_exported_weight_checks']=True
        report['gen2'][strategy]=result
    assert len(report['v6'])==13 and len(report['gen2'])==8
    report['semantics']={
        'v6_m3':'Legacy label uses 3 semitones and 1 letter step: C to D# is an augmented second by standard spelling, not a minor third. Preserved as source convention.',
        'gen2_m3':'Fifths-chain displacement -3 gives 3 semitones and 2 letter steps: C to Eb, a standard spelled minor third.',
        'row_count_difference':'Gen2 has16 P5+13 M3+14 true spelled m3; v6 has16 P5+13 M3+8 legacy m3-labelled augmented-second rows. Not the same graph plus6 added rows.',
        'targets_differ':{'v6_family_bases':{'P5':'-3.422','M3':'-13.686','m3':'10.265'},'v6_additions':'Spelled M3 +/-0.8; natural P5 +0.4','gen2':{'P5':'1.955','M3':'-13.686','m3':'15.641'}},
        'gen2_weight_transport':'Each12-pitch-class family is averaged and broadcast to every spelled row in that family, with lower floor1/2. Pitch-location-specific weights are discarded by this transport.',
        'gen2_modal_vs_cadence':'Both transported weights are uniform across all43rows (7/3 versus2); their relative interval priorities agree. With ridge0 their exact solutions coincide; at ridge1/125 only overall regularization scale distinguishes them.',
        'v6_ET':'Uniform source weights; computed offsets are nonzero. Not an equal-temperament bypass.',
        'energy':'Normal-equation and quadratic objective identities are musical nominal algebra, not physical passivity or material calibration.'}
    out=ROOT/'output/algebra_verification.json'
    out.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'passed':True,'strategies':len(report['v6'])+len(report['gen2']),
        'matrices':report['matrices'],'max_source_solution_error_cents':max(v['source_vs_exact_solution_max_abs_cents'] for k in ['v6','gen2'] for v in report[k].values()),'output':str(out)}))


if __name__=='__main__':
    main()
