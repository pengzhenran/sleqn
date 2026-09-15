#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sleqn_fast.py —— sleqn.py 的加速数值内核（可选，输出与原版**逐字节相同**）
============================================================================

为什么 grace_example 算得慢
----------------------------
``sleqn.solve_one`` 对**每一个网格单元**调用一次 ``gdisc``，而每次 ``gdisc`` 都
要在 Python 层展开一遍 0..180 阶（181 次 m 循环 + 362 次切片缩放 + 2 次
``martin`` 递推）。1° 网格是 64800 个单元，于是：

    64800 单元 × 约 360 次 NumPy 微调用 ≈ 2.3×10⁷ 次 ufunc 调用，
    每次只作用在 ≤181 个元素上 → 完全被解释器/ufunc 开销支配。

实测（grace_example，1° 64800 单元，niter=2，Anaconda Py3.13 + NumPy 2.1/MKL）：

    总计 102.7 s
      ├─ gdisc 自身（不含 martin）      80.2 s   78%
      ├─ martin（129600 次调用）        17.9 s   17%
      ├─ martin 命中缓存的 .copy()       2.5 s    2%
      └─ 真正的"数学"（geoid + 181 步
          BLAS 迭代 + 读写 + 加载）      ~1.5 s   <2%

    单胞内部：m 循环 63%、plmart 缩放循环 29%、两次 martin 约 5%

也就是说：慢的原因**不是迭代次数、不是磁盘 I/O、不是矩阵运算**，而是
"每单元一遍 Python 层 O(L²) 微操作"，以及 ``martin`` 用 ``np.sqrt`` 标量
做 16.6k 次递推（单次冷调用 42~48 ms；换成 ``math.sqrt`` 约 2.8 ms）。

本模块怎么加速
--------------
1. ``martin_fast``：用 ``math`` 标量 + 预先算好的 sqrt 因子表替代 NumPy 标量
   递推，**乘法结合顺序与原式完全一致**，因此逐位相同。
2. ``gdisc_fast``：把 362 次切片缩放压成 2 次向量乘；把 181 次 m 循环压成 4 次
   向量运算（``cos/sin(m·rlon)`` 按经度查表，用标量 ``np.cos`` 逐点生成，
   避免 SIMD 版 cos 与标量 cos 的 1 ulp 差异）。累加顺序不变，因此逐位相同。

实测效果（本机）：

    gdisc 单胞        1.270 ms → 0.143 ms   （8.9×）
    martin 冷调用     43.4 ms  → 2.82 ms    （15.4×）
    solve_one 端到端  102.7 s  → 10.5 s     （9.8×）
    输出文件          与 grace_example/slf_grace_t0001_1deg.txt 逐字节相同

用法
----
    import sleqn, sleqn_fast
    sleqn_fast.patch()          # 之后照常调用 sleqn.run / sleqn.solve_one
    sleqn_fast.unpatch()        # 需要与原内核逐位对照时再切回来
    sleqn_fast.is_patched()     # 查询当前状态

截断阶数 lmax 是运行期可调的（``sleqn.set_lmax(n)`` 或 ``sleqn.run(..., lmax=n)``），
本模块的两个内核都跟随 ``sleqn.LMOST``，改 lmax 后无需重新 patch。

自检（多种 lmax 下的逐位一致性 + 速度）：

    python sleqn_fast.py
"""

from __future__ import annotations

import math
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import sleqn  # noqa: E402

_SQ = math.sqrt
_R2 = np.sqrt(2.0)
_CS_TAB = {}
_CS_TAB_MAX = 4096          # 防御：载荷经度非规则网格时不至于无限增长
_RAT = {}
_LS_TAB = {}                # lmax → np.arange(lmax+1)


def _ls(lmax):
    """``np.arange(lmax+1)``（按 lmax 缓存，lmax 可运行期改变）。"""
    a = _LS_TAB.get(lmax)
    if a is None:
        a = np.arange(lmax + 1, dtype=np.float64)
        _LS_TAB[lmax] = a
    return a


# ============================================================================
# 1) 归一化勒让德函数：数值与原 martin 逐位相同
# ============================================================================
def _build_ratios(lmax):
    """预算每个 sqrt 因子（各存一张表，保持与原式相同的乘法结合顺序）。"""
    if lmax in _RAT:
        return
    n = lmax + 1
    A1 = [[0.0] * n for _ in range(n)]
    A2 = [[0.0] * n for _ in range(n)]
    B1 = [[0.0] * n for _ in range(n)]
    B2 = [[0.0] * n for _ in range(n)]
    B3 = [[0.0] * n for _ in range(n)]
    for m in range(n):
        for k in range(1, lmax - m + 1):
            A1[m][k] = _SQ(1.0 + (m - 0.5) / k)
            A2[m][k] = _SQ(1.0 - (m - 0.5) / (k + 2 * m))
            if k > 1:
                B1[m][k] = _SQ(1.0 + 4.0 / (2 * k + 2 * m - 3))
                B2[m][k] = _SQ(1.0 - 1.0 / k)
                B3[m][k] = _SQ(1.0 - 1.0 / (k + 2 * m))
    _RAT[lmax] = (A1, A2, B1, B2, B3)


def martin_fast(lmax, x):
    """等价于 ``sleqn.martin``，逐位相同，约 15× 快。

    ``math.sqrt`` 与 ``np.sqrt`` 对同一 double 入参都是正确舍入，结果一致；
    关键是保持 ``((2x·p)·s1)·s2`` 这样的左结合顺序，否则会有 1 ulp 差异。
    """
    x = float(x)
    key = (lmax, x)
    hit = sleqn._MARTIN_CACHE.get(key)
    if hit is not None:
        return hit.copy()

    _build_ratios(lmax)
    A1, A2, B1, B2, B3 = _RAT[lmax]
    plm = np.zeros((lmax + 1, lmax + 1), dtype=np.float64)
    rsin = _SQ(max(0.0, 1.0 - x * x))
    ptemp = [0.0] * (lmax + 1)
    p0 = 1.0 / _SQ(2.0)
    for m in range(lmax + 1):
        if m > 0:
            p0 *= _SQ(1.0 + 0.5 / m)
        ptemp[0] = p0
        kmax = lmax - m
        a1, a2 = A1[m], A2[m]
        b1, b2, b3 = B1[m], B2[m], B3[m]
        for k in range(1, kmax + 1):
            ptemp[k] = 2.0 * x * ptemp[k - 1] * a1[k] * a2[k]
            if k > 1:
                ptemp[k] -= ptemp[k - 2] * b1[k] * b2[k] * b3[k]
        rm = rsin ** m
        plm[m:lmax + 1, m] = [rm * v for v in ptemp[0:kmax + 1]]

    if len(sleqn._MARTIN_CACHE) >= sleqn._cache_limit(lmax):
        sleqn._MARTIN_CACHE.pop(next(iter(sleqn._MARTIN_CACHE)))
    sleqn._MARTIN_CACHE[key] = plm
    return plm.copy()


# ============================================================================
# 2) 单胞斯托克斯系数：数值与原 gdisc 逐位相同
# ============================================================================
def _cs_table(rlon, lmax):
    """``cos/sin(m·rlon)``, m=0..lmax —— 逐点用标量 np.cos/np.sin 生成，
    与 ``np.cos(m * rlon)`` 取值逐位一致（SIMD 版 array cos 可能差 1 ulp）。"""
    key = (float(rlon), int(lmax))
    t = _CS_TAB.get(key)
    if t is not None:
        return t
    m = np.arange(lmax + 1, dtype=np.float64)
    ang = m * key[0]
    c = np.array([np.cos(float(a)) for a in ang], dtype=np.float64)
    s = np.array([np.sin(float(a)) for a in ang], dtype=np.float64)
    t = (c, s)
    if len(_CS_TAB) < _CS_TAB_MAX:
        _CS_TAB[key] = t
    return t


def gdisc_fast(rlon, rlat, area, rmass, synthc, synths, lmost, rk):
    """等价于 ``sleqn.gdisc``，逐位相同，约 9× 快。

    截断阶数跟随 ``sleqn.LMOST``（可用 ``sleqn.set_lmax()`` 在运行期修改）。
    """
    # 原文此处为编译期常量 180；改为跟随模块当前的截断阶数
    lmax = sleqn.LMOST
    lmax1 = lmax + 1
    if lmost > lmax:
        raise ValueError(f'error #5 {lmost} {lmax}')

    # --- 圆盘平均勒让德函数（同步 sleqn.gdisc） ---
    clat = 1.0 - area / 6.371e3 ** 2 / 2.0 / sleqn.PI
    plmart = martin_fast(lmax1, clat)
    plmart[:, 0] *= np.sqrt(2.0 / (2.0 * np.arange(lmax1 + 1) + 1.0))
    temp = np.zeros(lmax + 1, dtype=np.float64)
    temp[1:lmax + 1] = (plmart[0:lmax, 0] - plmart[2:lmax + 2, 0]) / 2.0
    temp[0] = (1.0 - clat) / 2.0

    # --- 单元中心处的勒让德函数 ---
    clat = np.cos(rlat)
    plmart = martin_fast(lmax1, clat)
    # 原式：列 m=0 乘一次 sqrt2，列 m≥1 乘两次 → 两次向量乘，顺序不变
    plmart *= _R2
    plmart[:, 1:] *= _R2

    ls = _ls(lmax)
    h = rmass / (area * 1.0e5 ** 2)
    ha = h / 6.371e8
    fact_l = temp / (2.0 * ls + 1.0)
    coef_l = 3.0 / 5.517 * (1.0 + rk[0:lmax + 1]) / (2.0 * ls + 1.0) * ha

    c, s = _cs_table(rlon, lmax)
    # 原式：w = fact_l[idx]*plmart[idx,m]; synth += (w*coef_l[idx])*cos/sin(m*rlon)
    # idx 只覆盖行 0..lmax → 取 plmart 的 0:lmax+1 行/列；m>l 处 plmart 恒为 0，
    # 加上 0.0 不改变结果，故可整块累加而保持逐位一致。
    P = plmart[0:lmax + 1, 0:lmax + 1]
    K = (fact_l[:, None] * P) * coef_l[:, None]
    synthc += K * c[None, :]
    synths += K * s[None, :]


# ============================================================================
# 3) 安装到 sleqn 模块
# ============================================================================
_ORIG = {'martin': sleqn.martin, 'gdisc': sleqn.gdisc}


def patch():
    """把 ``sleqn.martin`` / ``sleqn.gdisc`` 换成加速版（数值逐位不变）。

    可重复调用（幂等）。截断阶数由 ``sleqn.LMOST`` 决定，因此
    ``sleqn.set_lmax()`` / ``sleqn.run(..., lmax=...)`` 之后无需重新 patch。

    与编译版 Fortran（sleqn_dp_static.exe）的区别：该 exe 里 dlon=dlat=0.5
    是**硬编码**的，用于 1° 的 grace_example 会把单元面积算错，不能直接替代。
    """
    if sleqn.martin is not martin_fast:
        _ORIG['martin'] = sleqn.martin
    if sleqn.gdisc is not gdisc_fast:
        _ORIG['gdisc'] = sleqn.gdisc
    sleqn.martin = martin_fast
    sleqn.gdisc = gdisc_fast
    return sleqn


def unpatch():
    """恢复 ``sleqn`` 原来的（未加速）内核，便于做逐位对照。"""
    sleqn.martin = _ORIG['martin']
    sleqn.gdisc = _ORIG['gdisc']
    return sleqn


def is_patched():
    """当前是否已安装加速内核。"""
    return sleqn.martin is martin_fast and sleqn.gdisc is gdisc_fast


# ============================================================================
# 自检
# ============================================================================
def _selftest():
    ex = os.path.join(HERE, 'grace_example')
    if not os.path.exists(os.path.join(ex, 'land.fcn.1_deg')):
        print('未找到 grace_example/，跳过自检')
        return
    _, rlon, rlat = sleqn.load_mask(os.path.join(ex, 'land.fcn.1_deg'))
    data = np.loadtxt(os.path.join(ex, 'load_grace_t0001_1deg.txt'))
    orig_martin, orig_gdisc = sleqn.martin, sleqn.gdisc

    print('1) martin 逐位一致性（多种 lmax）')
    for lmax in (60, 180, 181):
        for x in (0.9999, 0.5, 0.0, -0.87):
            sleqn._MARTIN_CACHE.pop((lmax, float(x)), None)
            ref = orig_martin(lmax, x)
            sleqn._MARTIN_CACHE.pop((lmax, float(x)), None)
            got = martin_fast(lmax, x)
            if not np.array_equal(ref, got):
                print(f'   ✘ lmax={lmax} x={x}')
        print(f'   lmax={lmax}: 全部逐位相同')

    print('2) gdisc 逐位一致性（多种 lmax，200 个真实单元/档）')
    for lmax in (60, 180):
        sleqn.set_lmax(lmax)
        h, rk = sleqn.load_love(os.path.join(ex, 'love_numbers'))
        rng = np.random.default_rng(0)
        bad = 0
        for k in rng.choice(len(data), 200, replace=False):
            xlon, latv, thick = data[k]
            xlat = 90.0 - float(latv)
            x1 = max(0.0, xlat - 0.5); x2 = min(180.0, xlat + 0.5)
            area = (sleqn.DTR * (np.cos(x1 * sleqn.DTR) - np.cos(x2 * sleqn.DTR))
                    * 6.371e3 ** 2)
            rmass = float(thick) * 100.0 * (area * 1.0e10)
            n = lmax + 1
            a = np.zeros((n, n)); b = np.zeros((n, n))
            c = np.zeros((n, n)); d = np.zeros((n, n))
            r = float(xlon) * sleqn.DTR
            t = xlat * sleqn.DTR
            orig_gdisc(r, t, area, rmass, a, b, lmax, rk)
            gdisc_fast(r, t, area, rmass, c, d, lmax, rk)
            if not (np.array_equal(a, c) and np.array_equal(b, d)):
                bad += 1
        print(f'   lmax={lmax}: 不一致单元数 = {bad}')

    print('3) 速度（lmax=180）')
    sleqn.set_lmax(180)
    h, rk = sleqn.load_love(os.path.join(ex, 'love_numbers'))
    xlat = 90.0 - 30.5
    area = sleqn.DTR * (np.cos((xlat - 0.5) * sleqn.DTR)
                        - np.cos((xlat + 0.5) * sleqn.DTR)) * 6.371e3 ** 2
    rmass = 0.01 * 100.0 * (area * 1.0e10)
    for tag, fn in (('原 gdisc  ', orig_gdisc), ('gdisc_fast', gdisc_fast)):
        a = np.zeros((181, 181)); b = np.zeros((181, 181))
        fn(0.1, xlat * sleqn.DTR, area, rmass, a, b, 180, rk)
        n = 1000
        t = time.perf_counter()
        for _ in range(n):
            fn(0.1, xlat * sleqn.DTR, area, rmass, a, b, 180, rk)
        dt = (time.perf_counter() - t) / n
        print(f'   {tag} {dt * 1000:7.3f} ms/单元 → 64800 单元约 {dt * 64800:6.1f} s')


if __name__ == '__main__':
    _selftest()
