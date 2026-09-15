# -*- coding: utf-8 -*-
"""sleqn 功能面检查：负值裁剪、迭代收敛、勒夫数表比对、GUI 可用性。"""
import os, sys, subprocess, time
import numpy as np

WS = r'D:\华为家庭存储\mywork\sealevel'
TMP = r'C:\Users\pengzhenran\AppData\Local\Temp\slverify'
sys.path.insert(0, WS)

# ---------- 1. GRACE 载荷的符号统计 ----------
print('=' * 70)
print('1. GRACE 算例载荷的符号')
for f in ('load_grace_t0001_1deg.txt', 'load_grace_trend_1deg.txt'):
    d = np.loadtxt(os.path.join(WS, 'grace_example', f))
    neg = (d[:, 2] < 0)
    print(f'  {f}: n={len(d)}  负值 {neg.sum()} ({neg.mean():.1%})  '
          f'min={d[:,2].min():.3e}  max={d[:,2].max():.3e}  '
          f'mean={d[:,2].mean():.3e}')

# ---------- 2. 负值裁剪对结果的影响 ----------
print('=' * 70)
print('2. sleqn 默认清零负值 vs --allow-negative（GRACE 趋势文件）')
from gravity_toolkit.units import units as U
import sleqn
uu = U(lmax=180)
sleqn.RHOAVE = float(uu.rho_e)
sleqn.ARAD = float(uu.rad_e)

mask = os.path.join(WS, 'grace_example', 'land.fcn.1_deg')
love = os.path.join(TMP, 'love_gravtk2.txt')
load = os.path.join(WS, 'grace_example', 'load_grace_trend_1deg.txt')

ofcn, rlon, rlat = sleqn.load_mask(mask)
h, rk = sleqn.load_love(love)
ls = np.arange(sleqn.LLOVE + 1)
coefh = (1.0 + rk - h) * 3.0 * sleqn.RHO0 / sleqn.RHOAVE / (2.0 * ls + 1.0)
coefp = (1.0 + rk - h) / (rk + 1.0)
plm = np.zeros((180 + 1, 180 + 1, sleqn.NTH))
fac = np.full(181, 2.0); fac[0] = np.sqrt(2.0)
for j in range(sleqn.NTH):
    plm[:, :, j] = sleqn.martin(180, np.cos((90.0 - rlat[j]) * sleqn.DTR)) * fac[None, :]
ms = np.arange(181)[:, None]
ph = ms * (rlon[None, :] * sleqn.DTR)
ccos, ssin = np.cos(ph), np.sin(ph)

res = {}
for tag, clip in (('clip=True (默认)', True), ('clip=False (--allow-negative)', False)):
    out = os.path.join(TMP, f'grace_clip_{int(clip)}.txt')
    t = time.time()
    z, tm, sm, ar = sleqn.solve_one(load, out, ofcn, rlon, rlat, plm, ccos, ssin,
                                    coefh, coefp, h, rk, niter=2, dlon=1.0,
                                    dlat=1.0, clip_negative=clip)
    g = np.loadtxt(out)[:, 2]
    res[tag] = g
    print(f'  {tag:34s} 载荷总质量={tm/1e15:12.6f} Gt  '
          f'min={g.min():+.4f} max={g.max():+.4f} cm  ({time.time()-t:.0f}s)')
a, b = list(res.values())
print(f'  两者最大差异 = {np.abs(a-b).max():.6f} cm  '
      f'（占 max|场| {np.abs(b).max():.4f} 的 {np.abs(a-b).max()/np.abs(b).max():.1%}）')

# ---------- 3. 迭代收敛性（demo 算例，快） ----------
print('=' * 70)
print('3. 迭代次数收敛性（demo 全海洋算例，对照收敛解）')
sys.path.insert(0, os.path.join(WS, '_verify'))
import verify_slf as V
c = V.build_common(os.path.join(WS, 'demo', 'land.fcn.1_deg'), love, 180)
c['dlon'] = c['dlat'] = 0.5
c['clip'] = True
load_d = os.path.join(WS, 'demo', 'load_demo.txt')
r = V.run_sleqn(c, load_d, os.path.join(TMP, 'conv200.txt'), 200)
ref = r['grid']
Ta, Tsa, tmass = r['T_after'], r['S_after'], r['tmass']
ana = V.analytic_field(c, Ta, Tsa, tmass)
print(f'  收敛参照：niter=200 与解析闭式解 max|Δ| = {np.abs(ref-ana).max():.3e} cm')
print(f'  {"niter":>6} {"max|Δ| vs 收敛解":>20} {"相对峰值":>10} {"平均偏差":>12} {"耗时(s)":>8}')
for n in (0, 1, 2, 3, 5, 10, 20, 50):
    t = time.time()
    rr = V.run_sleqn(c, load_d, os.path.join(TMP, f'conv{n}.txt'), n)
    dt = time.time() - t
    d = np.abs(rr['grid'] - ref).max()
    print(f'  {n:>6} {d:>20.3e} {d/np.abs(ref).max():>10.3%} '
          f'{np.abs(rr["grid"]-ref).mean():>12.3e} {dt:>8.1f}')

# ---------- 4. 勒夫数表比对 ----------
print('=' * 70)
print('4. gravity_toolkit 的 PREM 勒夫数 vs grace_example/love_numbers')
import gravity_toolkit as g
for opt, nm in ((0, 'Han & Wahr 1995'), (1, 'Gegout 2005'),
                (2, 'Wang et al. 2012')):
    L = g.load_love_numbers(180, LOVE_NUMBERS=opt, REFERENCE='CF', FORMAT='class')
    print(f'  gravity_toolkit LOVE_NUMBERS={opt} ({nm}): '
          f'h1={L.hl[1]:.6f} k2={L.kl[2]:.6f} k10={L.kl[10]:.6f}')
ge = np.loadtxt(os.path.join(WS, 'grace_example', 'love_numbers'), skiprows=2)
print(f'  grace_example/love_numbers      : '
      f'h1={ge[1,1]:.6f} k2={ge[2,2]:.6f} k10={ge[10,2]:.6f}  (n={len(ge)})')
L2 = g.load_love_numbers(180, LOVE_NUMBERS=2, REFERENCE='CF', FORMAT='class')
for opt, nm in ((0, 'HW95'), (1, 'Gegout05'), (2, 'Wang12')):
    L = g.load_love_numbers(180, LOVE_NUMBERS=opt, REFERENCE='CF', FORMAT='class')
    dh = np.abs(np.asarray(L.hl) - ge[:181, 1]).max()
    dk = np.abs(np.asarray(L.kl) - ge[:181, 2]).max()
    print(f'  与 {nm:9s} 的 max|Δh|={dh:.3e}  max|Δk|={dk:.3e}')
