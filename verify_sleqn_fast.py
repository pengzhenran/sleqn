#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_sleqn_fast.py —— 验证 sleqn_fast 的加速是**通用**的，且结果逐位不变
============================================================================

对每个算例都用「原内核 sleqn」和「加速内核 sleqn_fast」各跑一遍，比较
  (a) 输出文件是否逐字节相同
  (b) 耗时

覆盖：不同数据源、不同网格分辨率、不同经度集合、不同行序、niter=0/2、
      高精度输出格式、逐格点唯一经度（cos/sin 表退化的路径）。

    python verify_sleqn_fast.py           # 各算例核对（约 1 分钟）
    python verify_sleqn_fast.py --full    # 另把 grace_example 的整个 Filelist
                                          # 用两个内核各跑一遍（原约 190 s）

不会覆盖 grace_example/ 与 demo/ 下的任何原文件，中间结果写在 _gentest/。
"""

from __future__ import annotations

import argparse
import filecmp
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sleqn        # noqa: E402
import sleqn_fast   # noqa: E402

TMP = os.path.join(HERE, '_gentest')
GRACE = os.path.join(HERE, 'grace_example')
MASK = os.path.join(GRACE, 'land.fcn.1_deg')
LOVE = os.path.join(GRACE, 'love_numbers')
ORIG_MARTIN, ORIG_GDISC = sleqn.martin, sleqn.gdisc      # 留住原内核


# ---------------------------------------------------------------- 完整流程
def run_full(inp, outp, dlon, dlat, niter, fmt, use_fast, lmax=None):
    """复刻 run() 的前处理 + solve_one。返回 (预处理秒, 求解秒)。"""
    sleqn.OUT_FMT = fmt
    sleqn._MARTIN_CACHE.clear()
    sleqn_fast._CS_TAB.clear()
    if lmax is not None:
        sleqn.set_lmax(lmax)
    if use_fast:
        sleqn.martin, sleqn.gdisc = sleqn_fast.martin_fast, sleqn_fast.gdisc_fast
    else:
        sleqn.martin, sleqn.gdisc = ORIG_MARTIN, ORIG_GDISC

    t0 = time.perf_counter()
    ofcn, rlon, rlat = sleqn.load_mask(MASK)
    h, rk = sleqn.load_love(LOVE)
    ls = np.arange(sleqn.LLOVE + 1)
    coefh = (1.0 + rk - h) * 3.0 * sleqn.RHO0 / sleqn.RHOAVE / (2.0 * ls + 1.0)
    coefp = (1.0 + rk - h) / (rk + 1.0)
    plm = np.zeros((sleqn.LMOST + 1, sleqn.LMOST + 1, sleqn.NTH))
    fac = np.full(sleqn.LMOST + 1, 2.0)
    fac[0] = np.sqrt(2.0)
    for j in range(sleqn.NTH):                       # 180 条纬度带的 martin
        plm[:, :, j] = sleqn.martin(
            sleqn.LMOST, np.cos((90.0 - rlat[j]) * sleqn.DTR)) * fac[None, :]
    m_sin = np.arange(sleqn.LMOST + 1)[:, None]
    ccos = np.cos(m_sin * (rlon[None, :] * sleqn.DTR))
    ssin = np.sin(m_sin * (rlon[None, :] * sleqn.DTR))
    t_pre = time.perf_counter() - t0

    t1 = time.perf_counter()
    sleqn.solve_one(inp, outp, ofcn, rlon, rlat, plm, ccos, ssin,
                    coefh, coefp, h, rk, niter=niter, dlon=dlon, dlat=dlat,
                    clip_negative=False)
    return t_pre, time.perf_counter() - t1


_CNT = [0]
RESULTS = []


def case(tag, inp, dlon, dlat, niter=2, fmt=(12, 4), lmax=None):
    _CNT[0] += 1
    k = _CNT[0]
    a = os.path.join(TMP, f'a{k}.txt')
    b = os.path.join(TMP, f'b{k}.txt')
    ncell = sum(1 for _ in open(inp, encoding='utf-8'))
    pa, ta = run_full(inp, a, dlon, dlat, niter, fmt, use_fast=False, lmax=lmax)
    pb, tb = run_full(inp, b, dlon, dlat, niter, fmt, use_fast=True, lmax=lmax)
    same = filecmp.cmp(a, b, shallow=False)
    print(f'  {tag:30s} 单元{ncell:7d} niter={niter} e{fmt[0]}.{fmt[1]} '
          f'lmax={sleqn.LMOST}')
    print(f'      逐字节相同={same}   求解 {ta:7.2f}s → {tb:6.2f}s '
          f'({ta / tb:5.2f}×)   预处理 {pa:5.2f}s → {pb:.2f}s')
    RESULTS.append(same)
    return same


def make_synthetic():
    """另造一个 0.5° 网格荷载：720 经度 × 20 纬度带，高斯型异常。"""
    lon = 0.25 + 0.5 * np.arange(720)
    lat = 0.25 + 0.5 * np.arange(20)
    LON, LAT = np.meshgrid(lon, lat)
    thick = 1.0 * np.exp(-(((LON - 180.0) / 30.0) ** 2 + ((LAT - 5.0) / 4.0) ** 2))
    p = os.path.join(TMP, 'load_05deg.txt')
    with open(p, 'w', encoding='utf-8') as f:
        for i in range(LAT.size):
            f.write(f'{LON.ravel()[i]:8.2f} {LAT.ravel()[i]:8.2f} '
                    f'{thick.ravel()[i]:12.6e}\n')
    return p


def make_offgrid():
    """逐格点唯一经度（非规则），数量超过 cos/sin 表上限 → 走退化路径。"""
    rng = np.random.default_rng(7)
    n = 4200
    lon = rng.uniform(0.0, 360.0, n)
    thick = 0.5 * np.sin(np.radians(lon * 3.0))
    p = os.path.join(TMP, 'load_offgrid.txt')
    with open(p, 'w', encoding='utf-8') as f:
        for i in range(n):
            f.write(f'{lon[i]:10.4f} {30.0:7.1f} {thick[i]:12.6e}\n')
    return p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--full', action='store_true',
                    help='另外把 grace_example 的整个 Filelist 用两个内核各跑一遍')
    args = ap.parse_args()
    os.makedirs(TMP, exist_ok=True)

    print('=' * 78)
    print('0) 前提检查：martin 在 m>l（严格上三角）处恒为 +0.0')
    print('   —— 这是「m 循环可以整块向量化」的依据：多算的位置加的是 0.0')
    print('=' * 78)
    ok_zero = True
    lmax_probe = sleqn.LMOST
    for j in (0, 60, 120, 179):
        x = np.cos((90.0 - (-89.5 + j)) * sleqn.DTR)
        P = sleqn_fast.martin_fast(lmax_probe + 1, x)
        n = lmax_probe + 2
        ok_zero &= bool(np.all(P[np.triu(np.ones((n, n), bool), 1)] == 0.0))
    print(f'  4 条纬度带全部满足: {ok_zero}')

    print()
    print('=' * 78)
    print('1) 换数据 / 换网格分辨率 / 换迭代次数 / 换输出格式')
    print('=' * 78)
    case('demo 合成 10x10 @0.5°', os.path.join(HERE, 'demo', 'load_demo.txt'), 0.5, 0.5)
    case('demo 合成 niter=0', os.path.join(HERE, 'demo', 'load_demo.txt'), 0.5, 0.5, niter=0)
    case('demo 合成 e20.12', os.path.join(HERE, 'demo', 'load_demo.txt'), 0.5, 0.5, fmt=(20, 12))
    case('自造 720x20 @0.5° 高斯载荷', make_synthetic(), 0.5, 0.5)

    print()
    print('=' * 78)
    print('2) 对抗性行序 / 经度集合（专打缓存假设）')
    print('=' * 78)
    g = np.loadtxt(os.path.join(GRACE, 'load_grace_t0001_1deg.txt'))
    p = os.path.join(TMP, 'load_lonouter.txt')
    np.savetxt(p, g[np.arange(60) * 360], fmt='%7.1f %7.1f %12.6e')
    case('经度外层 60 个不同纬度', p, 1.0, 1.0)      # martin 缓存全失效
    case('非规则经度 4200 格点', make_offgrid(), 1.0, 1.0)   # cos/sin 表退化

    print()
    print('=' * 78)
    print('3) 不同截断阶数 lmax（原文 Fortran 写死 180，这里运行期可调）')
    print('=' * 78)
    sub = os.path.join(TMP, 'load_grace_20band.txt')
    np.savetxt(sub, g[:20 * 360], fmt='%7.1f %7.1f %12.6e')
    for lm in (20, 60, 120, 180):
        case(f'grace 20 条纬度带 lmax={lm}', sub, 1.0, 1.0, lmax=lm)

    print()
    print('=' * 78)
    print('4) 真正的 grace_example（64800 单元）加速版 vs 已有结果文件')
    print('=' * 78)
    ref = os.path.join(GRACE, 'slf_grace_t0001_1deg.txt')
    outp = os.path.join(TMP, 'grace_fast.txt')
    _, t = run_full(os.path.join(GRACE, 'load_grace_t0001_1deg.txt'), outp,
                    1.0, 1.0, 2, (12, 4), use_fast=True, lmax=180)
    print(f'  加速版求解 {t:.2f} s（原版实测 102.7 s）')
    same = filecmp.cmp(ref, outp, shallow=False)
    print(f'  与 grace_example/{os.path.basename(ref)} 逐字节相同 = {same}')
    RESULTS.append(same)

    if args.full:
        print()
        print('=' * 78)
        print('5) 整个 Filelist（2 个任务）用两个内核各跑一遍')
        print('=' * 78)
        sleqn.set_lmax(180)
        for mode in ('orig', 'fast'):
            if mode == 'fast':
                sleqn_fast.patch()
            else:
                sleqn.martin, sleqn.gdisc = ORIG_MARTIN, ORIG_GDISC
            pre = 'slff' if mode == 'fast' else 'slfo'
            lst = os.path.join(TMP, f'Filelist_{mode}.txt')
            outs = [os.path.join(TMP, pre + '_t0001.txt'),
                    os.path.join(TMP, pre + '_trend.txt')]
            with open(lst, 'w', encoding='utf-8') as f:
                f.write(f'{os.path.join(GRACE, "load_grace_t0001_1deg.txt")} {outs[0]}\n')
                f.write(f'{os.path.join(GRACE, "load_grace_trend_1deg.txt")} {outs[1]}\n')
            t0 = time.perf_counter()
            sleqn.run(MASK, LOVE, lst, niter=2, dlon=1.0, dlat=1.0, clip_negative=False)
            print(f'  >>> {mode} 全程 wall = {time.perf_counter() - t0:.1f} s')
            for r, o in zip(('slf_grace_t0001_1deg.txt', 'slf_grace_trend_1deg.txt'), outs):
                ok = filecmp.cmp(os.path.join(GRACE, r), o, shallow=False)
                RESULTS.append(ok)
                print(f'      {r}: 逐字节相同 = {ok}')

    print()
    print('=' * 78)
    print(f'结论：{sum(RESULTS)}/{len(RESULTS)} 项逐字节相同，'
          f'全部通过 = {all(RESULTS)}')
    print('=' * 78)
    return 0 if all(RESULTS) else 1


if __name__ == '__main__':
    sys.exit(main())
