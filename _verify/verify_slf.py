#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
verify_slf.py -- cross-check sleqn.py against independent implementations.

Three comparisons:
  A. Closed form.  With an all-ocean Earth the sea level equation is diagonal
     in the spherical harmonic domain:
         S_lm = coefp_lm * T_lm / (1 - coefh_lm)     (l >= 1)
     with the (0,0) coefficient fixed by mass conservation.
  B. gravity_toolkit.sea_level_equation -- an independent code (different
     authors, Clenshaw summation) using exactly the same load harmonics and
     the same land-sea mask, so any difference comes from the solver alone.
  C. sleqn convergence in the number of iterations.

The load harmonics are captured from inside sleqn (by hooking sleqn.gdisc), so
they are bit-identical to the ones sleqn itself used.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

import numpy as np

WS = r'D:\华为家庭存储\mywork\sealevel'
TMP = r'C:\Users\pengzhenran\AppData\Local\Temp\slverify'
sys.path.insert(0, WS)
os.makedirs(TMP, exist_ok=True)

import sleqn                      # noqa: E402
import gravity_toolkit as gravtk  # noqa: E402


def build_common(mask_file, love_file, lmax):
    """Replicate sleqn.run() preprocessing exactly."""
    sleqn.set_lmax(lmax)
    ofcn, rlon, rlat = sleqn.load_mask(mask_file)
    h, rk = sleqn.load_love(love_file)
    ls = np.arange(sleqn.LLOVE + 1)
    coefh = (1.0 + rk - h) * 3.0 * sleqn.RHO0 / sleqn.RHOAVE / (2.0 * ls + 1.0)
    coefp = (1.0 + rk - h) / (rk + 1.0)
    plm = np.zeros((lmax + 1, lmax + 1, sleqn.NTH))
    fac = np.full(lmax + 1, 2.0)
    fac[0] = np.sqrt(2.0)
    for j in range(sleqn.NTH):
        plm[:, :, j] = sleqn.martin(lmax, np.cos((90.0 - rlat[j]) * sleqn.DTR)) * fac[None, :]
    m_sin = np.arange(lmax + 1)[:, None]
    phase = m_sin * (rlon[None, :] * sleqn.DTR)
    return dict(ofcn=ofcn, rlon=rlon, rlat=rlat, h=h, rk=rk, coefh=coefh,
                coefp=coefp, plm=plm, ccos=np.cos(phase), ssin=np.sin(phase))


def make_love_file_from_gravtk(path, lmax, love_opt, ref):
    """Write gravity_toolkit's PREM load Love numbers in sleqn's file format."""
    L = gravtk.load_love_numbers(lmax, LOVE_NUMBERS=love_opt,
                                 REFERENCE=ref, FORMAT='class')
    with open(path, 'w') as f:
        f.write('# generated from gravity_toolkit load_love_numbers\n')
        f.write('#        l        h_load        k_load      (reserved)\n')
        for l in range(lmax + 1):
            f.write(f'{l:9d} {L.hl[l]: .8e} {L.kl[l]: .8e} {L.ll[l]: .8e}\n')
    return L


def run_sleqn(c, inpath, outpath, niter):
    """Run sleqn.solve_one and capture the load harmonics it used internally."""
    cap = {}
    orig = sleqn.gdisc

    def wrapper(rlon, rlat, area, rmass, synthc, synths, lmost, rk):
        cap['c'] = synthc
        cap['s'] = synths
        return orig(rlon, rlat, area, rmass, synthc, synths, lmost, rk)

    sleqn.gdisc = wrapper
    try:
        z, tm, sm, ar = sleqn.solve_one(
            inpath, outpath, c['ofcn'], c['rlon'], c['rlat'], c['plm'],
            c['ccos'], c['ssin'], c['coefh'], c['coefp'], c['h'], c['rk'],
            niter=niter, dlon=c['dlon'], dlat=c['dlat'], clip_negative=c['clip'])
    finally:
        sleqn.gdisc = orig
    # the captured arrays were multiplied by ARAD inside solve_one
    raw = cap['c'] / sleqn.ARAD
    sraw = cap['s'] / sleqn.ARAD
    grid = np.loadtxt(outpath)[:, 2].reshape(sleqn.NPHI, sleqn.NTH)
    return dict(zmass=z, tmass=tm, T=raw, S=sraw,
                T_after=cap['c'].copy(), S_after=cap['s'].copy(), grid=grid)


def _weights(c):
    """coefh/coefp including the degree 2 order 1 polar-motion row."""
    lmax = sleqn.LMOST
    ch = np.zeros((lmax + 1, lmax + 1))
    cp = np.zeros((lmax + 1, lmax + 1))
    for l in range(lmax + 1):
        ch[l, :] = c['coefh'][l]
        cp[l, :] = c['coefp'][l]
    rk, h = c['rk'], c['h']
    coefpm = (1.0 + rk[2]) * (1.0 + sleqn.RK2B - sleqn.H2B) / (sleqn.RKF - sleqn.RK2B)
    pmp = (1.0 + rk[2] - h[2] + coefpm) / (1.0 + rk[2])
    pmh = pmp * (1.0 + rk[2]) * 3.0 * sleqn.RHO0 / sleqn.RHOAVE / float(2 * 2 + 1)
    ch[2, 1] = pmh
    cp[2, 1] = pmp
    return ch, cp


def analytic_field(c, T, Ssin, tmass):
    """Closed-form all-ocean solution, synthesised with sleqn's own operator."""
    lmax = sleqn.LMOST
    ch, cp = _weights(c)
    hclm = np.zeros_like(T)
    hslm = np.zeros_like(T)
    for l in range(1, lmax + 1):
        d = 1.0 - ch[l, :l + 1]
        hclm[l, :l + 1] = cp[l, :l + 1] * T[l, :l + 1] / d
        hslm[l, :l + 1] = cp[l, :l + 1] * Ssin[l, :l + 1] / d
    hclm[0, 0] = -tmass / (sleqn.RHO0 * sleqn.ARAD ** 2) / (4.0 * np.pi)
    ccT, ssT, plm = c['ccos'].T, c['ssin'].T, c['plm']
    total = np.zeros((sleqn.NPHI, sleqn.NTH))
    for l in range(lmax + 1):
        mm = l + 1
        total += (hclm[l, 0:mm][None, :] * ccT[:, 0:mm]
                  + hslm[l, 0:mm][None, :] * ssT[:, 0:mm]) @ plm[l, 0:mm, :]
    return total * c['ofcn']


def compare(name, a, b, mask):
    d = (a - b)[mask]
    ra, rb = a[mask], b[mask]
    corr = np.corrcoef(ra, rb)[0, 1]
    r = dict(maxabs=float(np.abs(d).max()), meanabs=float(np.abs(d).mean()),
             rms=float(np.sqrt((d ** 2).mean())), corr=float(corr),
             refmax=float(np.abs(rb).max()))
    print(f'  [{name}] n={int(mask.sum())}  max|d|={r["maxabs"]:.6e}  '
          f'mean|d|={r["meanabs"]:.6e}  rms={r["rms"]:.6e}')
    print(f'         max|ref|={r["refmax"]:.6e}  '
          f'relative max|d|/max|ref| = {r["maxabs"]/r["refmax"]:.4%}  '
          f'corr={corr:.10f}')
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--case', choices=['demo', 'grace'], required=True)
    ap.add_argument('--love', choices=['gravtk', 'file'], default='gravtk')
    ap.add_argument('--gravtk-love', type=int, default=2)
    ap.add_argument('--gravtk-ref', default='CF', choices=['CF', 'CM', 'CE'])
    ap.add_argument('--lmax', type=int, default=180)
    ap.add_argument('--iters', type=int, nargs='+', default=[2, 50])
    ap.add_argument('--tag', default='')
    ap.add_argument('--align', action='store_true')
    args = ap.parse_args()

    if args.align:
        from gravity_toolkit.units import units as _u
        _uu = _u(lmax=args.lmax)
        sleqn.RHOAVE = float(_uu.rho_e)
        sleqn.ARAD = float(_uu.rad_e)
        print(f'[align] sleqn.RHOAVE={sleqn.RHOAVE:.10f}  sleqn.ARAD={sleqn.ARAD:.4f}')

    out = {}
    if args.case == 'demo':
        src = os.path.join(WS, 'demo')
        load = os.path.join(src, 'load_demo.txt')
        dlon = dlat = 0.5
        clip = True
    else:
        src = os.path.join(WS, 'grace_example')
        load = os.path.join(src, 'load_grace_trend_1deg.txt')
        dlon = dlat = 1.0
        clip = False
    mask = os.path.join(src, 'land.fcn.1_deg')

    if args.love == 'gravtk':
        love_use = os.path.join(TMP, f'love_gt{args.gravtk_love}{args.gravtk_ref}.txt')
        L = make_love_file_from_gravtk(love_use, args.lmax, args.gravtk_love,
                                       args.gravtk_ref)
        print(f'love numbers: gravity_toolkit LOVE_NUMBERS={args.gravtk_love} '
              f'({L.model}, {L.reference})')
    else:
        love_use = os.path.join(src, 'love_numbers')
        L = gravtk.load_love_numbers(args.lmax, LOVE_NUMBERS=args.gravtk_love,
                                     REFERENCE=args.gravtk_ref, FORMAT='class')
        print(f'love numbers: case file {love_use} ; gravity_toolkit ref='
              f'{args.gravtk_ref}')
    LOVE = (np.asarray(L.hl), np.asarray(L.kl), np.asarray(L.ll))

    t0 = time.time()
    print(f'[{args.case}] preprocessing ...')
    c = build_common(mask, love_use, args.lmax)
    c['dlon'], c['dlat'], c['clip'] = dlon, dlat, clip
    print(f'  ocean cells = {int(c["ofcn"].sum())} / {c["ofcn"].size}  '
          f'({time.time()-t0:.1f} s)')

    for niter in args.iters:
        print(f'\n=== sleqn niter={niter} ===')
        r = run_sleqn(c, load, os.path.join(TMP, f'sleqn_{args.case}_{args.tag}_n{niter}.txt'),
                      niter)
        print(f'  done in {time.time()-t0:.1f} s cumulative ; '
              f'tmass={r["tmass"]/1e15:.6f} Gt  zmass={r["zmass"]:.6f} Gt')
        out[f'n{niter}'] = r
        if niter == args.iters[0]:
            T, Ts, Ta, Tsa, tmass = r['T'], r['S'], r['T_after'], r['S_after'], r['tmass']

    om = c['ofcn'] > 0.5
    if args.case == 'demo':
        print('\n=== A. closed-form solution (all ocean) ===')
        ana = analytic_field(c, Ta, Tsa, tmass)
        for niter in args.iters:
            out[f'analytic_vs_sleqn_n{niter}'] = compare(
                f'analytic(conv) vs sleqn niter={niter}', ana, out[f'n{niter}']['grid'], om)

    print('\n=== B. gravity_toolkit.sea_level_equation ===')
    t2 = time.time()
    sl = gravtk.sea_level_equation(T, Ts, c['rlon'], c['rlat'], 1.0 - c['ofcn'],
                                   LMAX=args.lmax, LOVE=LOVE, POLAR=True,
                                   ITERATIONS=500, FILL_VALUE=np.nan)
    print(f'  done in {time.time()-t2:.1f} s')
    for niter in args.iters:
        out[f'gravtk_vs_sleqn_n{niter}'] = compare(
            f'gravtk(conv) vs sleqn niter={niter}', sl, out[f'n{niter}']['grid'], om)
    if args.case == 'demo':
        out['analytic_vs_gravtk'] = compare('analytic(conv) vs gravtk(conv)',
                                            ana, sl, om)

    summ = {k: v for k, v in out.items() if isinstance(v, dict) and 'maxabs' in v}
    summ.update(case=args.case, love=args.love, gravtk_love=args.gravtk_love,
                gravtk_ref=args.gravtk_ref, lmax=args.lmax, iters=args.iters,
                aligned=bool(args.align), tmass_Gt=float(tmass / 1e15))
    with open(os.path.join(TMP, f'summary_{args.case}_{args.tag}.json'), 'w') as f:
        json.dump(summ, f, indent=2, ensure_ascii=False)
    print(f'\ntotal {time.time()-t0:.1f} s')


if __name__ == '__main__':
    main()
