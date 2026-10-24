"""Illustrative passive clay/string model; NOT a calibrated hardware prediction.

Requires Python 3, numpy, scipy, matplotlib. Run this file from any directory.
All results and figures are written beside it. No repository code is imported.
The two coordinates are generalized mechanical displacements in metres.
The hydrophone conversion is deliberately unspecified.
"""
from pathlib import Path
import csv
import json
import numpy as np
from scipy.integrate import solve_ivp
from scipy.linalg import eigh
from scipy.optimize import least_squares
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUT = Path(__file__).resolve().parent
M = np.diag([0.012, 0.008])  # kg, illustrative modal masses
K0 = np.diag(np.diag(M) * (2*np.pi*np.array([70., 110.]))**2)
K0 += 300. * np.array([[1., -1.], [-1., 1.]])
C0 = np.diag([0.03, 0.025]) + .008*np.array([[1., -1.], [-1., 1.]])
a = np.array([1., -0.6])
B = np.array([1., 0.35])
TRUE = np.array([800., 5000., 2., 1.3, 1.])
PARAMS = ["k_infinity_N_per_m", "k_memory_N_per_m", "tau_s",
          "sensor_gain_arbitrary", "viscous_damping_scale"]


def response(freq, p):
    """Complex displacement/force at first mechanical coordinate (m/N).

    A constant, real sensor gain is an explicit fitting assumption. This is
    NOT the transfer function of any selected hydrophone or water cell.
    """
    ki, km, tau, gain, cs = p
    w = 2*np.pi*np.asarray(freq)
    kc = ki + km*(1j*w*tau)/(1+1j*w*tau)
    D = K0[None, :, :] - w[:, None, None]**2*M[None, :, :]
    D = D.astype(complex) + 1j*w[:, None, None]*cs*C0[None, :, :]
    D += kc[:, None, None]*np.outer(a, a)[None, :, :]
    q = np.linalg.solve(D, np.broadcast_to(B, (len(w), 2))[:, :, None])[:, :, 0]
    return gain*q[:, 0]


def response_separate_gain(freq, p):
    h = response(freq, p[:5])
    return h*np.where(np.asarray(freq)<3.,p[5],1.)


def log_jacobian(freq, p, eps=1e-5, response_fn=response):
    scale = np.abs(response_fn(freq, p))
    cols = []
    for j in range(len(p)):
        step = np.zeros(len(p)); step[j] = eps
        d = (response_fn(freq, p*np.exp(step)) - response_fn(freq, p*np.exp(-step))) / (2*eps*scale)
        cols.append(np.r_[d.real, d.imag])
    return np.asarray(cols).T


def analytic_log_jacobian(freq, p):
    """Exact derivatives of the specified complex transfer function."""
    ki,km,tau,gain,cs=p[:5]
    w=2*np.pi*np.asarray(freq); r=1j*w*tau
    outer=np.outer(a,a)[None,:,:]
    D=(K0[None,:,:]-w[:,None,None]**2*M[None,:,:]).astype(complex)
    D+=1j*w[:,None,None]*cs*C0[None,:,:]
    D+=(ki+km*r/(1+r))[:,None,None]*outer
    q=np.linalg.solve(D,np.broadcast_to(B,(len(w),2))[:,:,None])[:,:,0]
    slow_factor=np.where(np.asarray(freq)<3.,p[5],1.) if len(p)==6 else np.ones(len(w))
    h=gain*slow_factor*q[:,0]
    matrices=[np.broadcast_to(ki*outer,D.shape),
              km*(r/(1+r))[:,None,None]*outer,
              km*(r/(1+r)**2)[:,None,None]*outer,
              1j*w[:,None,None]*cs*C0[None,:,:]]
    derivatives=[]
    for dD in matrices:
        rhs=np.einsum('nij,nj->ni',dD,q)
        dq=-np.linalg.solve(D,rhs[:,:,None])[:,:,0]
        derivatives.append(gain*slow_factor*dq[:,0])
    derivatives.insert(3,h)
    if len(p)==6:derivatives.append(np.where(np.asarray(freq)<3.,h,0.))
    cols=[]
    for d in derivatives:
        d=d/np.abs(h)
        cols.append(np.r_[d.real,d.imag])
    return np.asarray(cols).T


def identifiability(freq, p=TRUE, response_fn=response, names=PARAMS):
    J = analytic_log_jacobian(freq, p)
    _, sv, vt = np.linalg.svd(J, full_matrices=False)
    # Declared 1% Gaussian noise in EACH real and imaginary part relative to
    # the noiseless complex magnitude. A local model-conditional diagnostic.
    variance = np.sum(vt.T**2*(.01/sv)[None, :]**2, axis=1)
    stability = {}
    for eps in [1e-4,1e-5,1e-6]:
        scheck=np.linalg.svd(log_jacobian(freq,p,eps=eps,response_fn=response_fn),compute_uv=False)
        stability[str(eps)]={"smallest_singular_value":float(scheck[-1]),"condition_number":float(scheck[0]/scheck[-1])}
    return {"frequencies_Hz": freq.tolist(), "sensitivity_singular_values": sv.tolist(),
            "main_sensitivity_method":"analytic transfer derivatives; SVD covariance",
            "condition_number": float(sv[0]/sv[-1]),
            "finite_difference_step_stability":stability,
            "local_one_sigma_log_parameter_errors": dict(zip(names, np.sqrt(variance).tolist()))}


def state_rhs(t, s, p, forcing):
    ki, km, tau, _, cs = p
    q, v, z = s[:2], s[2:4], s[4]
    y = a@q
    acc = np.linalg.solve(M, B*forcing(t) - cs*C0@v - K0@q - a*(ki*y+km*(y-z)))
    zdot = (y-z)/tau
    power_in = forcing(t)*(B@v)
    diss = cs*(v@C0@v) + km/tau*(y-z)**2
    return np.r_[v, acc, zdot, power_in, diss]


def energy(s, p):
    ki, km = p[:2]
    q, v, z = s[:2], s[2:4], s[4]
    y = a@q
    return .5*(q@K0@q + v@M@v + ki*y*y + km*(y-z)**2)


def integrate(forcing, initial, duration=0.5):
    times=np.linspace(0.,duration,5001)
    sol=solve_ivp(lambda t,s: state_rhs(t,s,TRUE,forcing), [0.,duration],
                  np.r_[initial,0.,0.], t_eval=times, rtol=2e-10, atol=1e-12,
                  max_step=1e-4, method="DOP853")
    if not sol.success:
        raise RuntimeError(sol.message)
    e=np.array([energy(s,TRUE) for s in sol.y.T])
    balance=e-e[0]-sol.y[5]+sol.y[6]
    return times, sol.y, e, balance


def main():
    audio=np.geomspace(65.,240.,52)
    slow=np.geomspace(.015,2.,24)
    combined=np.r_[slow,audio]
    ia=identifiability(audio)
    ic=identifiability(combined)
    ic_separate=identifiability(combined,np.r_[TRUE,1.],response_separate_gain,PARAMS+["relative_slow_sensor_gain"])
    # Independent state-space calculation checks the eliminated frequency law.
    ki,km,tau,gain,cs=TRUE
    A=np.zeros((5,5)); A[:2,2:4]=np.eye(2)
    A[2:4,:2]=-np.linalg.solve(M,K0+(ki+km)*np.outer(a,a))
    A[2:4,2:4]=-np.linalg.solve(M,cs*C0)
    A[2:4,4]=np.linalg.solve(M,km*a)
    A[4,:2]=a/tau;A[4,4]=-1/tau
    U=np.r_[np.zeros(2),np.linalg.solve(M,B),0.]
    check_freq=np.array([.015,.1,1.,65.,100.,240.])
    hs=np.array([gain*np.linalg.solve(2j*np.pi*f*np.eye(5)-A,U)[0] for f in check_freq])
    state_space_relative_error=float(np.max(np.abs(hs-response(check_freq,TRUE))/np.abs(hs)))
    assert state_space_relative_error<1e-12
    rng=np.random.default_rng(20261024)
    H=response(combined,TRUE); scale=np.abs(H)
    estimates=[]; rms=[]
    lo=np.log([100.,1000.,.05,.3,.2])
    hi=np.log([4000.,15000.,30.,3.,4.])
    for _ in range(30):
        measured=H+.01*scale*(rng.normal(size=len(H))+1j*rng.normal(size=len(H)))
        def residual(logp):
            r=(response(combined,np.exp(logp))-measured)/scale
            return np.r_[r.real,r.imag]
        fit=least_squares(residual,np.log(TRUE*np.exp(rng.normal(0,.1,5))),
                          bounds=(lo,hi),xtol=1e-11,ftol=1e-11,gtol=1e-11,max_nfev=500)
        if not fit.success:
            raise RuntimeError("Synthetic fit did not converge")
        estimates.append(np.exp(fit.x)); rms.append(float(np.sqrt(np.mean(fit.fun**2))))
    estimates=np.array(estimates)
    t,s,e,balance=integrate(lambda t: 0., [1e-4,-4e-5,0.,0.,0.])
    tf,sf,ef,bf=integrate(lambda t: .01*np.sin(2*np.pi*120*t)*(t<.15), np.zeros(5))
    _,s2,e2,b2=integrate(lambda t: 0., [1e-4,-4e-5,0.,0.,0.])
    repeat_max=float(np.max(np.abs(s-s2)))
    eig_inf=eigh(K0+(TRUE[0]+TRUE[1])*np.outer(a,a),M,eigvals_only=True)
    p2=TRUE.copy();p2[0]*=1.2;p2[1]*=.8
    H2=response(audio,p2);H1=response(audio,TRUE)
    # Best constant complex gain cannot explain a change in mechanics.
    gfit=np.vdot(H1,H2)/np.vdot(H1,H1)
    shape_residual=float(np.linalg.norm(H2-gfit*H1)/np.linalg.norm(H2))
    max_increase=float(np.max(np.diff(e)))
    result={
      "status":"ILLUSTRATIVE_SYNTHETIC_MODEL_NOT_HARDWARE_VALIDATION",
      "units":"SI except declared arbitrary sensor gain; modal masses and all coefficients assumed",
      "parameters":dict(zip(PARAMS,TRUE.tolist())),
      "model":{"M_kg":M.tolist(),"K0_N_per_m":K0.tolist(),"C0_N_s_per_m":C0.tolist(),"clay_coordinate_a":a.tolist(),"force_vector_B":B.tolist()},
      "frozen_clay_modal_frequencies_Hz":(np.sqrt(eig_inf)/(2*np.pi)).tolist(),
      "audio_only":ia,"slow_and_audio":ic,
      "slow_and_audio_separate_gain_nuisance":ic_separate,
      "monte_carlo":{"seed":20261024,"trials":30,"noise_std_each_complex_component_relative":.01,
                     "median_estimates":dict(zip(PARAMS,np.median(estimates,axis=0).tolist())),
                     "relative_RMSE":dict(zip(PARAMS,np.sqrt(np.mean(((estimates-TRUE)/TRUE)**2,axis=0)).tolist())),
                     "mean_normalized_residual_RMS":float(np.mean(rms))},
      "energy_checks":{"free_initial_energy_J":float(e[0]),"free_final_energy_J":float(e[-1]),
                       "free_max_energy_balance_residual_J":float(np.max(np.abs(balance))),
                       "forced_max_energy_balance_residual_J":float(np.max(np.abs(bf))),
                       "maximum_sampled_free_energy_increment_J":max_increase,
                       "repeat_run_max_state_difference":repeat_max,
                       "state_space_frequency_law_max_relative_error":state_space_relative_error},
      "configuration_change":{"k_inf_multiplier":1.2,"k_memory_multiplier":.8,
                              "residual_after_best_constant_complex_gain":shape_residual},
      "exact_limits":[
        "At fixed coefficients, the incremental linear frequency response is independent of initial z: acoustic FRF alone cannot identify history.",
        "The SLS state z relaxes; this model does not establish nonvolatile clay memory or plasticity.",
        "An arbitrary unknown frequency-dependent water/sensor transfer function can absorb every candidate mechanical FRF; hydrophone-only mechanical identification is then impossible.",
        "Synthetic parameter errors condition on correct two-mode model, known force and frequency, and a single real frequency-independent sensor gain."]}
    assert np.max(np.abs(balance))<1e-10
    assert np.max(np.abs(bf))<1e-10
    assert max_increase<1e-14
    assert repeat_max==0.
    (OUT/"model_results.json").write_text(json.dumps(result,indent=2)+"\n")
    with (OUT/"synthetic_sweep.csv").open("w",newline="") as f:
        w=csv.writer(f);w.writerow(["frequency_Hz","real_mechanical_sensor_response_per_N","imag_mechanical_sensor_response_per_N","absolute_response_per_N"])
        for fr,h in zip(combined,H):w.writerow([fr,h.real,h.imag,abs(h)])
    with (OUT/"free_ringdown.csv").open("w",newline="") as f:
        w=csv.writer(f);w.writerow(["time_s","q1_m","q2_m","v1_m_per_s","v2_m_per_s","z_m","energy_J","energy_balance_residual_J"])
        for j in range(len(t)):w.writerow([t[j],*s[:5,j],e[j],balance[j]])
    fig,ax=plt.subplots(2,2,figsize=(10.5,7.5),layout="constrained")
    ax[0,0].loglog(combined,np.abs(H),"o",ms=3,label="Assumed configuration A")
    ax[0,0].loglog(audio,np.abs(H2),"-",label="Assumed configuration B")
    ax[0,0].set(xlabel="Drive frequency (Hz)",ylabel="Sensor response per N (arbitrary gain)",title="Slow and acoustic measurements are complementary")
    ax[0,0].legend(fontsize=8)
    ax[0,1].semilogx(audio,np.unwrap(np.angle(H1))*180/np.pi,label="A")
    ax[0,1].semilogx(audio,np.unwrap(np.angle(H2))*180/np.pi,label="B")
    ax[0,1].set(xlabel="Drive frequency (Hz)",ylabel="Phase (degrees)",title="Phase and resonance shape survive constant gain")
    ax[0,1].legend()
    ax[1,0].semilogy(t,e,label="Stored energy")
    ax[1,0].set(xlabel="Time (s)",ylabel="Energy (J)",title="Free response dissipates energy")
    labels=["k_inf","k_memory","tau","gain","damping"]
    x=np.arange(5)
    ax[1,1].bar(x-.18,list(ia["local_one_sigma_log_parameter_errors"].values()),width=.36,label="Audio only")
    ax[1,1].bar(x+.18,list(ic["local_one_sigma_log_parameter_errors"].values()),width=.36,label="Slow + audio")
    ax[1,1].set(xticks=x,xticklabels=labels,yscale="log",ylabel="Local 1-sigma log-parameter uncertainty",title="1% synthetic complex noise; conditional diagnostic")
    ax[1,1].legend(fontsize=8)
    fig.suptitle("ILLUSTRATIVE MODEL - no measured hardware data",fontsize=14,fontweight="bold")
    fig.savefig(OUT/"model_diagnostics.png",dpi=180)
    plt.close(fig)
    print(json.dumps({"audio_condition":ia["condition_number"],"combined_condition":ic["condition_number"],
                      "audio_local_errors":ia["local_one_sigma_log_parameter_errors"],
                      "combined_local_errors":ic["local_one_sigma_log_parameter_errors"],
                      "separate_gain_condition":ic_separate["condition_number"],
                      "separate_gain_local_errors":ic_separate["local_one_sigma_log_parameter_errors"],
                      "energy_checks":result["energy_checks"],"monte_carlo":result["monte_carlo"],
                      "gain_residual":shape_residual},indent=2))


if __name__=="__main__":main()
