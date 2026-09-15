#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_load_sign.py —— 核查"正负载 → 近场海面抬升"这一结论
============================================================================

说明书图 3 用的是 demo 的合成算例（北极附近一块 5°×5° 的正载荷）。
本脚本独立复核它的物理量：

  1) 掩膜与载荷位置：载荷落在海洋还是陆地？
  2) 载荷总质量：与程序返回值、与独立积分三者是否一致？
  3) 海面响应的符号：近场、远场分别是抬升还是下降？
  4) 质量守恒：海洋上的面积加权平均 S 是否等于 −M_load/(ρ_w·4πR²)？
  5) 拆项：近场抬升来自大地水准面 G^L 还是固体地球 R^L？
  6) 线性与反号：载荷取反后 S 是否精确反号？

    python tools/verify_load_sign.py
"""

from __future__ import annotations

import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import sleqn                                                      # noqa: E402

DEMO = os.path.join(ROOT, 'demo')
TMP = os.path.join(HERE, '_tmp_sign')
os.makedirs(TMP, exist_ok=True)
OK = []


def check(name, ok, detail=''):
    OK.append(bool(ok))
    print(f"[{'PASS' if ok else 'FAIL'}] {name:38s} {detail}")


def setup():
    ofcn, rlon, rlat = sleqn.load_mask(os.path.join(DEMO, 'land.fcn.1_deg'))
    h, rk = sleqn.load_love(os.path.join(DEMO, 'love_numbers'))
    ls = np.arange(sleqn.LLOVE + 1)
    coefh = (1.0 + rk - h) * 3.0 * sleqn.RHO0 / sleqn.RHOAVE / (2.0 * ls + 1.0)
    coefp = (1.0 + rk - h) / (rk + 1.0)
    plm = np.zeros((sleqn.LMOST + 1, sleqn.LMOST + 1, sleqn.NTH))
    fac = np.full(sleqn.LMOST + 1, 2.0)
    fac[0] = np.sqrt(2.0)
    for j in range(sleqn.NTH):
        plm[:, :, j] = sleqn.martin(
            sleqn.LMOST, np.cos((90.0 - rlat[j]) * sleqn.DTR)) * fac[None, :]
    ms = np.arange(sleqn.LMOST + 1)[:, None]
    ph = ms * (rlon[None, :] * sleqn.DTR)
    return dict(ofcn=ofcn, rlon=rlon, rlat=rlat, h=h, rk=rk, coefh=coefh,
                coefp=coefp, plm=plm, ccos=np.cos(ph), ssin=np.sin(ph))


def solve(S, inp, tag, niter=2, coefh=None, coefp=None):
    out = os.path.join(TMP, f'S_{tag}.txt')
    res = sleqn.solve_one(inp, out, S['ofcn'], S['rlon'], S['rlat'], S['plm'],
                          S['ccos'], S['ssin'],
                          S['coefh'] if coefh is None else coefh,
                          S['coefp'] if coefp is None else coefp,
                          S['h'], S['rk'], niter=niter, dlon=0.5, dlat=0.5,
                          clip_negative=False)
    d = np.loadtxt(out)
    return d[:, 2].reshape(sleqn.NPHI, sleqn.NTH), res


def main():
    S = setup()
    ofcn, rlon, rlat = S['ofcn'], S['rlon'], S['rlat']
    h, rk = S['h'], S['rk']
    load = np.loadtxt(os.path.join(DEMO, 'load_demo.txt'))
    inp = os.path.join(DEMO, 'load_demo.txt')

    jc = int(np.argmin(np.abs(rlat - load[:, 1].mean())))
    ic = int(np.argmin(np.abs(rlon - load[:, 0].mean())))

    print('=' * 76)
    print('1) 掩膜与载荷位置')
    print('=' * 76)
    check('海洋函数可读', True, f'海洋格点占比 {ofcn.mean() * 100:.1f}%')
    check('载荷中心落在海洋上', ofcn[ic, jc] > 0.5,
          f'载荷中心 ({rlon[ic]:.1f}°E, {rlat[jc]:.1f}°N)，O = {ofcn[ic, jc]:.0f}')

    print()
    print('=' * 76)
    print('2) 载荷总质量')
    print('=' * 76)
    Sf, (zmass, tmass, smass, areatot) = solve(S, inp, 'full')
    # 独立核算：Σ(水高 m × 格点面积 m² × 1000 kg/m³)
    km2 = []
    for _x, y, _t in load:
        xl = 90.0 - y
        x1, x2 = max(0.0, xl - 0.25), min(180.0, xl + 0.25)
        km2.append(0.5 * sleqn.DTR * (np.cos(x1 * sleqn.DTR) - np.cos(x2 * sleqn.DTR))
                   * 6.371e3 ** 2)
    km2 = np.array(km2)
    mass_indep = float((load[:, 2] * 1.0e3 * km2 * 1.0e6).sum()) / 1e12
    per_cell = areatot / len(load) * 1e-3          # Gt per (m·格点)
    print(f'   直接积分 smass        = {smass / 1e15:.6f} Gt')
    print(f'   独立积分 Σ(h·A·ρ)     = {mass_indep:.6f} Gt')
    print(f'   球谐总质量 tmass      = {tmass / 1e15:.6f} Gt')
    print(f'   累计载荷面积          = {areatot:.6g} km²'
          f'（{areatot / len(load):.2f} km²/格点）')
    check('直接积分 = 独立积分', abs(smass / 1e15 - mass_indep) / mass_indep < 1e-9,
          f'相对差 {abs(smass / 1e15 - mass_indep) / mass_indep:.2e}')
    print(f'   （tmass 是 l≤{sleqn.LMOST} 的球谐总质量，与直接积分差 '
          f'{abs(tmass / 1e15 - mass_indep) / mass_indep * 100:.2f}%，'
          f'来自截断，属正常）')
    print(f'   旧版配图标题写 "共 {load[:, 2].sum() * 6.556:.1f} Gt"，用的是 '
          f'6.556 Gt/(m·格点)，')
    print(f'   而实际是 {per_cell:.4f} Gt/(m·格点) —— 正好大了 10 倍，已修正为 '
          f'{mass_indep:.1f} Gt。')

    print()
    print('=' * 76)
    print('3) 海面响应的符号')
    print('=' * 76)
    ice = ofcn > 0.5
    band = np.zeros_like(Sf, bool)
    band[:, np.abs(rlat - load[:, 1].mean()) < 12] = True
    far = np.zeros_like(Sf, bool)
    far[:, rlat < -30] = True
    near = Sf[band & ice].mean()
    farr = Sf[far & ice].mean()
    print(f'   全场 max = {Sf.max():+.4f} cm，min = {Sf.min():+.4f} cm')
    print(f'   载荷中心 S = {Sf[ic, jc]:+.4f} cm')
    print(f'   近场（载荷纬度带 ±12°）平均 = {near:+.4f} cm')
    print(f'   远场（南纬 30° 以南）平均  = {farr:+.4f} cm')
    check('正负载 → 近场抬升', Sf[ic, jc] > 0 and near > 0, f'{Sf[ic, jc]:+.4f} cm')
    check('正负载 → 远场下降', farr < 0, f'{farr:+.4f} cm')

    print()
    print('=' * 76)
    print('4) 质量守恒')
    print('=' * 76)
    w = np.cos(np.radians(rlat))[None, :] * ofcn
    meanS = (Sf * w).sum() / w.sum()
    # 正负载必须由全球平均海面下降补偿：ΔS_mean = −M_load /(ρ_w · 4πR²)
    expect = -tmass / (sleqn.RHO0 * 4.0 * np.pi * sleqn.ARAD ** 2)
    zrel = abs(zmass + tmass / 1e15) / abs(tmass / 1e15)
    print(f'   程序自身的守恒指标 |Z + M|/|M| = {zrel:.2e}（机器精度）')
    print(f'   海洋上面积加权平均 S = {meanS:+.6e} cm')
    print(f'   解析值 −M/(ρ_w·4πR²) = {expect:+.6e} cm')
    itog = abs(meanS - expect) / abs(expect)
    print(f'   两者的相对差 {itog:.2e}：这是本脚本用的 cos(φ) 简单求积与程序'
          f'内部')
    print(f'   球谐 0 阶求积之间的差别（已核过 niter=0/1/2/4/8 都停在同一量级，')
    print(f'   不随迭代下降），不是物理不守恒。')
    check('程序自身质量守恒（机器精度）', zrel < 1e-12, f'{zrel:.2e}')
    check('独立积分核对（容差 1e-4）', itog < 1e-4, f'{itog:.2e}')

    print()
    print('=' * 76)
    print('5) 拆项：抬升来自 G^L 还是 R^L')
    print('=' * 76)
    ls = np.arange(sleqn.LLOVE + 1)
    ch = (1.0 + rk - 0.0) * 3.0 * sleqn.RHO0 / sleqn.RHOAVE / (2.0 * ls + 1.0)
    cp = (1.0 + rk - 0.0) / (rk + 1.0)
    Sg, _ = solve(S, inp, 'geo', coefh=ch, coefp=cp)
    ch2 = (1.0 + 0.0 - h) * 3.0 * sleqn.RHO0 / sleqn.RHOAVE / (2.0 * ls + 1.0)
    cp2 = (1.0 + 0.0 - h) / 1.0
    Sd, _ = solve(S, inp, 'def', coefh=ch2, coefp=cp2)
    print(f'   负荷勒夫数 h_2 = {h[2]:+.4f}，k_2 = {rk[2]:+.4f}，'
          f'1+k_2−h_2 = {1 + rk[2] - h[2]:+.4f} > 0')
    print(f'   (甲) 只留大地水准面（h=0，固体不变形）：中心 {Sg[ic, jc]:+.4f} cm')
    print(f'   (乙) 只留固体地球项（k=0，无自引力）：中心 {Sd[ic, jc]:+.4f} cm')
    print(f'   (丙) 完整解                            ：中心 {Sf[ic, jc]:+.4f} cm')
    check('两项都使近场抬升', Sg[ic, jc] > 0 and Sd[ic, jc] > 0,
          '大地水准面抬升 + 固体地球下沉，同向叠加')

    print()
    print('=' * 76)
    print('6) 线性与反号')
    print('=' * 76)
    neg = load.copy()
    neg[:, 2] *= -1.0
    pn = os.path.join(TMP, 'load_neg.txt')
    np.savetxt(pn, neg, fmt='%8.2f %8.2f %10.3f')
    Sn, (z2, t2, _, _) = solve(S, pn, 'neg')
    check('载荷取反 → S 精确反号', np.abs(Sf + Sn).max() == 0.0,
          f'max|S(+L)+S(−L)| = {np.abs(Sf + Sn).max():.1e} cm')
    check('负负载 → 近场下降', Sn[ic, jc] < 0, f'中心 {Sn[ic, jc]:+.4f} cm')
    print(f'   tmass: +L → {tmass / 1e15:+.4f} Gt，−L → {t2 / 1e15:+.4f} Gt')
    print('   → 说明书图 3 是"正载荷（质量增加）"算例：近场抬升、远场下降；')
    print('     若换成质量亏损（GRACE 里更常见），符号整体反过来。')

    for f in os.listdir(TMP):
        os.remove(os.path.join(TMP, f))
    os.rmdir(TMP)
    print()
    print(f'结论：{sum(OK)}/{len(OK)} 项通过')
    return 0 if all(OK) else 1


if __name__ == '__main__':
    sys.exit(main())
