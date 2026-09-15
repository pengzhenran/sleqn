#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
verify_polar_switch.py -- 验证极移（polar motion）反馈开关 polar=True/False
==========================================================================

``sleqn.solve_one(..., polar=False)`` 应当正好等价于"把 (l=2,m=1) 的极移系数换回
未含极移的通用系数 coefh(2)/coefp(2)，其余一切不变"。本脚本用四条互相独立的判据
来确认：

  A. 闭合解（全球皆海洋）。海平面方程在球谐域对角化：
         S_lm = coefp_lm * T_lm / (1 - coefh_lm)      (l >= 1)
     (0,0) 由质量守恒定。把带/不带极移的 (2,1) 权重分别代进去：
       A1  两种开关状态都与各自的闭合解一致（残差 = 1° 网格求积误差，与开关无关）；
       A2  差场的 (2,1) 系数 = 两个闭合解 (2,1) 系数之差（严格到迭代/求积水平）。
  B. 赤道镜像载荷。载荷关于赤道镜像后 (2,1) 系数严格为 0（P_2^1 在赤道反射下
     变号），此时开/关极移反馈必须给出**逐点完全相同**的结果 —— 证明开关只动
     (2,1) 这一条通道。
  C. 差异谱。有 (2,1) 载荷时，开/关两次结果的差场做球谐变换，功率应集中在
     (2,1)（全球海洋时应接近 100%）。
  D. （可选 --gravtk）与独立实现 ``gravity_toolkit.sea_level_equation`` 的
     POLAR=True / POLAR=False 分别对照（两套代码用**同一套**勒夫数），验证两种
     开关状态的端到端一致性。

运行：
    _verify\\venv-gravtk\\Scripts\\python.exe _verify\\verify_polar_switch.py --gravtk
    python _verify\\verify_polar_switch.py            # 只跑 A/B/C（不需要 gravtk）
    python _verify\\verify_polar_switch.py --lmax 60 --iters 2 20
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
import time

import numpy as np

WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, WS)

import sleqn  # noqa: E402

RESULTS = []


def ck(name, ok, detail=''):
    RESULTS.append(bool(ok))
    print(f"[{'PASS' if ok else 'FAIL'}] {name:50s} {detail}", flush=True)


# ---------------------------------------------------------------- 公共前处理
def build_common(mask_file, love_file, lmax):
    """复刻 sleqn.run() 的前处理（plm/ccos/ssin/coefh/coefp）。"""
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
        plm[:, :, j] = sleqn.martin(
            lmax, np.cos((90.0 - rlat[j]) * sleqn.DTR)) * fac[None, :]
    ms = np.arange(lmax + 1)[:, None]
    phase = ms * (rlon[None, :] * sleqn.DTR)
    return dict(ofcn=ofcn, rlon=rlon, rlat=rlat, h=h, rk=rk, coefh=coefh,
                coefp=coefp, plm=plm, ccos=np.cos(phase), ssin=np.sin(phase))


def weights(c, polar):
    """coefh/coefp 二维表；(2,1) 行按 polar 取极移系数或通用系数。"""
    lmax = sleqn.LMOST
    ch = np.tile(c['coefh'][:, None], (1, lmax + 1))
    cp = np.tile(c['coefp'][:, None], (1, lmax + 1))
    if polar:
        rk, h = c['rk'], c['h']
        coefpm = ((1.0 + rk[2]) * (1.0 + sleqn.RK2B - sleqn.H2B)
                  / (sleqn.RKF - sleqn.RK2B))
        pmp = (1.0 + rk[2] - h[2] + coefpm) / (1.0 + rk[2])
        pmh = (pmp * (1.0 + rk[2]) * 3.0 * sleqn.RHO0 / sleqn.RHOAVE
               / float(2 * 2 + 1))
        ch[2, 1], cp[2, 1] = pmh, pmp
    return ch, cp


def run_sleqn(c, load, out, niter, polar, dlon, dlat, clip):
    """跑 sleqn.solve_one，并捕获它内部实际使用的载荷球谐系数。"""
    cap = {}
    orig = sleqn.gdisc

    def wrapper(rlon, rlat, area, rmass, synthc, synths, lmost, rk):
        cap['c'] = synthc
        cap['s'] = synths
        return orig(rlon, rlat, area, rmass, synthc, synths, lmost, rk)

    sleqn.gdisc = wrapper
    try:
        z, tm, sm, ar = sleqn.solve_one(
            load, out, c['ofcn'], c['rlon'], c['rlat'], c['plm'], c['ccos'],
            c['ssin'], c['coefh'], c['coefp'], c['h'], c['rk'],
            niter=niter, dlon=dlon, dlat=dlat, clip_negative=clip, polar=polar)
    finally:
        sleqn.gdisc = orig
    grid = np.loadtxt(out)[:, 2].reshape(sleqn.NPHI, sleqn.NTH)
    # 捕获到的系数在 solve_one 内部已被乘上 ARAD（cm 量纲，供解析闭式解使用）；
    # gravity_toolkit 的 loadClm 约定是不乘 ARAD 的原始值，故另存一份。
    T = cap['c'].copy()
    S = cap['s'].copy()
    return dict(zmass=z, tmass=tm, T=T, S=S, T_raw=T / sleqn.ARAD,
                S_raw=S / sleqn.ARAD, grid=grid)


def analytic_field(c, T, Ssin, tmass, polar):
    """全球皆海洋时的闭合解（用 sleqn 自己的综合算子合成）。"""
    lmax = sleqn.LMOST
    ch, cp = weights(c, polar)
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


def mirror_load(src, dst):
    """把载荷关于赤道镜像（(2,1) 系数严格为 0）。"""
    d = np.loadtxt(src)
    m = d.copy()
    m[:, 1] = -d[:, 1]
    with open(dst, 'w', encoding='utf-8') as f:
        for lo, la, th in np.vstack([d, m]):
            f.write(f'{lo:8.2f} {la:8.2f} {th:10.3f}\n')
    return dst


def sht(c, field):
    return sleqn.geoid(field, c['rlon'], c['rlat'], c['plm'], c['ccos'],
                       c['ssin'], sleqn.NTH, sleqn.NPHI, sleqn.LMOST, sleqn.LMOST)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--lmax', type=int, default=60)
    ap.add_argument('--iters', type=int, nargs='+', default=[2, 20],
                    help='迭代次数列表；末项用于"收敛后"的对照（默认 2 20）')
    ap.add_argument('--gravtk', action='store_true',
                    help='额外与 gravity_toolkit 的 POLAR=True/False 对照')
    ap.add_argument('--gravtk-love', type=int, default=2)
    ap.add_argument('--gravtk-ref', default='CF', choices=['CF', 'CM', 'CE'])
    args = ap.parse_args()

    t0 = time.time()
    tmp = tempfile.mkdtemp(prefix='sleqn_polar_')
    src = os.path.join(WS, 'demo')
    mask = os.path.join(src, 'land.fcn.1_deg')
    love = os.path.join(src, 'love_numbers')
    load = os.path.join(src, 'load_demo.txt')
    dlon = dlat = 0.5
    clip = True
    nc = args.iters[-1]

    print(f'临时目录 {tmp}')
    print(f'lmax={args.lmax}  niter={args.iters}  载荷=demo/load_demo.txt  '
          f'掩膜=demo/land.fcn.1_deg')
    c = build_common(mask, love, args.lmax)
    om = c['ofcn'] > 0.5
    print(f'海洋格点 {int(om.sum())}/{om.size}\n')

    # ============================================================ 两种开关状态
    res = {}
    for polar in (True, False):
        for niter in args.iters:
            tag = f'{"on" if polar else "off"}_n{niter}'
            print(f'--- sleqn polar={polar} niter={niter} ---')
            res[tag] = run_sleqn(c, load, os.path.join(tmp, f'slf_{tag}.txt'),
                                 niter, polar, dlon, dlat, clip)
            r = res[tag]
            rel = abs(r['zmass'] + r['tmass'] / 1e15) / abs(r['tmass'] / 1e15)
            ck(f'质量守恒 polar={polar} niter={niter}', rel < 1e-12,
               f'相对误差 {rel:.2e}，zmass={r["zmass"]:.6f} Gt')

    on, off = res[f'on_n{nc}'], res[f'off_n{nc}']
    peak = max(np.abs(on['grid']).max(), np.abs(off['grid']).max())

    # ------------------------------------------------------------ A1 闭合解
    print('\n=== A1. 与闭合解对照（全球皆海洋；残差 = 1° 网格求积误差）===')
    ana = {}
    for polar, r in ((True, on), (False, off)):
        ana[polar] = analytic_field(c, r['T'], r['S'], r['tmass'], polar)
        d = np.abs(ana[polar] - r['grid'])[om].max()
        ck(f'闭合解 vs sleqn (polar={polar}, niter={nc})', d / peak < 1e-3,
           f'max|Δ| = {d:.3e} cm（占峰值 {peak:.4f} cm 的 {d / peak:.2e}）')
    d_ana = np.abs(ana[True] - ana[False])[om].max()
    d_num = np.abs(on['grid'] - off['grid'])[om].max()
    print(f'  闭合解差 max|Δ| = {d_ana:.6e} cm；sleqn 差 max|Δ| = {d_num:.6e} cm')

    # ------------------------------------------------------------ A2 (2,1) 系数
    print('\n=== A2. 差场的 (2,1) 系数 vs 闭合解系数之差 ===')
    T21, S21 = on['T'][2, 1], on['S'][2, 1]
    c21 = {}
    for polar in (True, False):
        ch, cp = weights(c, polar)
        c21[polar] = cp[2, 1] / (1.0 - ch[2, 1]) * np.array([T21, S21])
    clm, slm = sht(c, on['grid'] - off['grid'])
    for i, nm in ((0, 'C21'), (1, 'S21')):
        exp = c21[True][i] - c21[False][i]
        got = (clm[2, 1], slm[2, 1])[i]
        ck(f'差场 {nm} = 闭合解系数之差', abs(got - exp) / abs(exp) < 1e-3,
           f'{got:.10e} vs {exp:.10e}（相对偏差 {abs(got - exp) / abs(exp):.2e}）')

    # ------------------------------------------------------------ B 镜像载荷
    print('\n=== B. 赤道镜像载荷（(2,1) 系数严格为 0）===')
    load_m = mirror_load(load, os.path.join(tmp, 'load_mirror.txt'))
    r_on = run_sleqn(c, load_m, os.path.join(tmp, 'slf_mir_on.txt'), nc, True,
                     dlon, dlat, clip)
    r_off = run_sleqn(c, load_m, os.path.join(tmp, 'slf_mir_off.txt'), nc, False,
                      dlon, dlat, clip)
    d = np.abs(r_on['grid'] - r_off['grid']).max()
    ck('镜像载荷下 开/关 结果逐点相同', d < 1e-12,
       f'max|Δ| = {d:.3e} cm（场峰值 {np.abs(r_on["grid"]).max():.4f} cm，'
       f'载荷 |T21| = {abs(r_on["T"][2, 1]):.2e}）')

    # ------------------------------------------------------------ C 差异谱
    print('\n=== C. 开/关差异的球谐谱 ===')
    diff = on['grid'] - off['grid']
    clm, slm = sht(c, diff)
    tot = float((clm ** 2 + slm ** 2).sum())
    p21 = float(clm[2, 1] ** 2 + slm[2, 1] ** 2)
    frac = p21 / tot if tot > 0 else float('nan')
    others = np.hypot(clm, slm).ravel()
    others[np.ravel_multi_index((2, 1), clm.shape)] = 0.0
    print(f'  max|Δ| = {np.abs(diff).max():.4e} cm'
          f'（占峰值 {peak:.4f} cm 的 {np.abs(diff).max() / peak:.3%}）')
    print(f'  (2,1) 振幅 {np.hypot(clm[2, 1], slm[2, 1]):.6e}，'
          f'次强项 {others.max():.3e}')
    ck('差异功率集中在 (2,1)', frac > 0.95, f'占比 {frac:.6%}')

    # ------------------------------------------------------------ D gravtk
    if args.gravtk:
        print('\n=== D. 与 gravity_toolkit 的 POLAR 开关对照（同一套勒夫数）===')
        try:
            import gravity_toolkit as gravtk
        except Exception as exc:                                   # noqa: BLE001
            ck('import gravity_toolkit', False, f'{type(exc).__name__}: {exc}')
        else:
            L = gravtk.load_love_numbers(args.lmax, LOVE_NUMBERS=args.gravtk_love,
                                         REFERENCE=args.gravtk_ref, FORMAT='class')
            love_gt = os.path.join(tmp, 'love_from_gravtk.txt')
            with open(love_gt, 'w', encoding='utf-8') as f:
                f.write('# generated from gravity_toolkit.load_love_numbers\n')
                f.write('#        l        h_load        k_load      (reserved)\n')
                for l in range(args.lmax + 1):
                    f.write(f'{l:9d} {L.hl[l]: .8e} {L.kl[l]: .8e} '
                            f'{L.ll[l]: .8e}\n')
            LOVE = (np.asarray(L.hl), np.asarray(L.kl), np.asarray(L.ll))
            c2 = build_common(mask, love_gt, args.lmax)
            for polar in (True, False):
                r = run_sleqn(c2, load, os.path.join(tmp, f'gt_{polar}.txt'), nc,
                              polar, dlon, dlat, clip)
                sl = gravtk.sea_level_equation(
                    r['T_raw'], r['S_raw'], c2['rlon'], c2['rlat'],
                    1.0 - c2['ofcn'],
                    LMAX=args.lmax, LOVE=LOVE, POLAR=polar, ITERATIONS=500,
                    FILL_VALUE=np.nan)
                dd = np.abs(sl - r['grid'])[c2['ofcn'] > 0.5]
                ck(f'gravtk POLAR={polar} vs sleqn polar={polar}',
                   dd.max() / np.abs(r['grid']).max() < 5e-3,
                   f'max|Δ|={dd.max():.3e} cm'
                   f'（占峰值 {dd.max() / np.abs(r["grid"]).max():.3%}）')

    print('\n' + '=' * 64)
    print(f'结论：{sum(RESULTS)}/{len(RESULTS)} 项通过    '
          f'总耗时 {time.time() - t0:.1f} s')
    print('=' * 64)
    return 0 if all(RESULTS) else 1


if __name__ == '__main__':
    sys.exit(main())
