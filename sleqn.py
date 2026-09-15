#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sleqn.py —— 海平面指纹（Sea Level Fingerprints, SLF）计算
=========================================================

本程序是文章所附 Fortran95 程序 ``sleqn.f90`` 的 Python 版本（NumPy 实现），
数组约定、变量名、计算流程均与 Fortran 版一一对应，可直接对照阅读。

数值实现对应 **修正版** ``sleqn_dp.f90``（全程双精度常量；极移项分母按物理意义取
(2*2+1)），二者在合成算例上输出逐字节相同。与原文 ``sleqn.f90`` 的差异及定量核查
见 ``README_sleqn.md`` §6、§8。

极移（polar motion）反馈可以**在运行期开关**：``solve_one(..., polar=False)`` /
``run(..., polar=False)`` / 命令行 ``--no-polar`` / GUI 的「含极移反馈」复选框。
默认 ``polar=True``，即与修正版 Fortran、gravity-toolkit（POLAR=True）一致。
该反馈只在球谐 $(l,m)=(2,1)$ 处生效，关掉它相当于把该分支的系数换回未含极移的
通用系数 ``coefh(2)/coefp(2)``。

    求解海平面方程：
        S(theta, phi) = O(theta, phi) * [ N(theta, phi) - U(theta, phi) ] + c
    其中 O 为海洋函数，N 为大地水准面异常，U 为固体地球表面径向位移，
    c 为维持海水质量守恒的 0 阶常数项（迭代中逐步修正）。

输入
----
land.fcn.1_deg : 海陆掩膜，每行 "经度 纬度 value"（value=1 陆地，0 海洋）。
                 按纬度带顺序排列，共 nth*nphi 行。
love_numbers   : 负荷勒让德数，前 2 行为表头，其后每行 "l  h_l  k_l  [x]"。
Filelist.txt   : 控制文件，每行两个文件名——输入数据文件、输出结果文件。
                 含空格的路径要用双引号括起来，例如
                 "C:\\Program Files\\海平面指纹\\a.txt" "D:\\out\\b.txt"；
                 不加引号时按空白切分（与 Fortran 原文一致）。
输入数据文件   : 每行 "经度 纬度 水当量高度(m)"。

输出
----
每个输入文件对应一个输出文件，每行 "经度 纬度 海平面变化(cm)"，
经度为外层循环、纬度为内层循环，与输入网格一一对应。

依赖
----
Python >= 3.8，NumPy

用法
----
    python sleqn.py                                  # 使用默认文件名
    python sleqn.py --mask land.fcn.1_deg --love love_numbers \\
                    --list Filelist.txt --niter 2 --lmax 180
    python sleqn.py --no-polar                       # 不算极移反馈（敏感性分析）

截断阶数 lmax
-------------
原文 Fortran 把 ``lmost``/``lsyn``/``llove`` 都写成编译期常量 180。这里改成
运行期可调：默认仍是 180（因此默认行为与原文逐字节一致），可用 ``--lmax``
或 ``sleqn.set_lmax(n)`` 修改，以适配不同的勒夫数表/分辨率需求。

参考
----
Sun J. W., Wang L. S., Peng Z. R., Fu Z. Y., Chen C (2022).
The sea level fingerprints of global terrestrial water storage changes
detected by GRACE and GRACE-FO data. Pure and Applied Geophysics, 179(9).
"""

from __future__ import annotations

import argparse
import os
import shlex
import sys
import time

import numpy as np

# ============================================================================
# 参数（与 sleqn.f90 中的 Parameter 语句一致）
# ============================================================================
DEF_LMOST = 180      # 默认最大阶数（= 原文 Parameter(lmost=180)）
LMOST = DEF_LMOST    # 当前截断阶数；用 set_lmax() / --lmax 修改
LSYN = LMOST         # 合成谐波系数的最大阶数（与 LMOST 同步）
LLOVE = LMOST        # 负荷勒夫数的最大阶数（与 LMOST 同步）
LMAX_MIN = 2         # 极移项用到 l=2，故 lmax 不能低于 2
NTH = 180            # 纬度格点数
NPHI = 360           # 经度格点数
NITER = 2            # 迭代次数；0 表示把水均匀铺在一层海面上

PI = 3.14159265
DTR = PI / 180.0
RHO0 = 1.0           # 水的密度 (g/cm^3)
RHOAVE = 5.517       # 地球平均密度 (g/cm^3)
ARAD = 6.371e8       # 地球半径 (cm)
RKF = 0.00328475 / 0.00348118
RK2B = 0.298
H2B = 0.604
EARTH_MASS = 5.97e27  # 地球质量 (g)

# 输出格式 (字段宽度, 小数位数)：默认 E12.4，与 Fortran 版完全一致；
# 若下游处理需要更高精度，可设为 (18, 10) 之类，见 --fmt 选项。
OUT_FMT = (12, 4)


def set_lmax(lmax: int) -> int:
    """设置截断阶数，同步更新 ``LMOST`` / ``LSYN`` / ``LLOVE``。

    原文 Fortran 中这三个量是编译期常量 180；本实现把它们变成运行期可调，
    默认仍是 180，因此不调用本函数时行为与原文逐字节一致。

    Parameters
    ----------
    lmax : int   截断阶数，至少为 2（极移项需要 l=2）

    Notes
    -----
    * ``love_numbers`` 至少要有 lmax+1 阶；不足时 ``load_love`` 会警告并把
      缺失的高阶按 0 处理（结果会失真），此时应换用更高阶的勒夫数表。
    * 输出/载荷网格为 NPHI×NTH（360×180），可分辨到约 180 阶；lmax 取更大值时
      超过的部分在网格上无法表达，仅作为数学截断（会给出一条提示）。
    * 预计算的勒让德函数占用 ``8*(lmax+1)^2*NTH`` 字节，lmax 很大时注意内存。
    """
    global LMOST, LSYN, LLOVE
    lmax = int(lmax)
    if lmax < LMAX_MIN:
        raise ValueError(f'lmax 至少为 {LMAX_MIN}（极移项需要 l=2），收到 {lmax}')
    if lmax > 180:
        print(f'[提示] lmax={lmax} > 180：载荷/输出网格 {NPHI}x{NTH} 只能分辨到'
              f'约 180 阶，更高阶在网格上无法表达（仅作数学截断）。')
    LMOST = LSYN = LLOVE = lmax
    return lmax


# ============================================================================
# 归一化勒让德函数（Martin 递推关系）
# ============================================================================
# martin(lmax, x) 是纯函数：同 (lmax, x) 必然得到同一数组。而 gdisc 对每个网格
# 单元都要调用它两次（一次取圆盘角半径、一次取单元余纬），真实 GRACE 网格动辄几万
# 个单元，重复计算代价极大。这里做**结果缓存**：只缓存计算结果，不改变任何数值，
# 因此与 Fortran 版仍逐位一致（实测 64800 行输出完全相同）。
_MARTIN_CACHE = {}
_MARTIN_CACHE_MAX = 512          # 条目数上限（lmax=180 时为 512 → 约 136 MB）


def _cache_limit(lmax: int) -> int:
    """按内存预算给出缓存条目上限（每条约 8*(lmax+2)^2 字节）。

    lmax=180 时返回 512（与原实现一致）；lmax 更大时自动收紧，
    避免 lmax=720/2000 时单是缓存就吃掉几 GB 内存。
    """
    per = 8.0 * (int(lmax) + 2) ** 2
    return max(8, min(_MARTIN_CACHE_MAX, int(256.0e6 / per)))


def martin(lmax: int, x: float) -> np.ndarray:
    """使用 Martin 的递归关系计算归一化缔合勒让德函数。

    对应 Fortran 子程序 ``martin``。返回数组 plm(l, m)，l、m 均为 0..lmax。

    Parameters
    ----------
    lmax : int  最大阶数
    x    : float  余弦纬度 cos(theta)
    """
    key = (lmax, float(x))
    hit = _MARTIN_CACHE.get(key)
    if hit is not None:
        return hit.copy()                # 返回副本：调用方会原地修改

    plm = np.zeros((lmax + 1, lmax + 1), dtype=np.float64)
    rsin = np.sqrt(max(0.0, 1.0 - x * x))
    ptemp = np.zeros(lmax + 1, dtype=np.float64)

    p0 = 1.0 / np.sqrt(2.0)          # m = 0 时的 ptemp(0)
    for m in range(lmax + 1):
        if m > 0:
            # ptemp(0) = prod_{j=1..m} sqrt(1 + 1/(2j)) / sqrt(2)
            p0 *= np.sqrt(1.0 + 0.5 / m)
        ptemp[0] = p0

        kmax = lmax - m
        for k in range(1, kmax + 1):
            ptemp[k] = (2.0 * x * ptemp[k - 1]
                        * np.sqrt(1.0 + (m - 0.5) / k)
                        * np.sqrt(1.0 - (m - 0.5) / (k + 2 * m)))
            if k > 1:
                ptemp[k] -= (ptemp[k - 2]
                             * np.sqrt(1.0 + 4.0 / (2 * k + 2 * m - 3))
                             * np.sqrt(1.0 - 1.0 / k)
                             * np.sqrt(1.0 - 1.0 / (k + 2 * m)))
        plm[m:lmax + 1, m] = rsin ** m * ptemp[0:kmax + 1]

    if len(_MARTIN_CACHE) >= _cache_limit(lmax):
        _MARTIN_CACHE.pop(next(iter(_MARTIN_CACHE)))
    _MARTIN_CACHE[key] = plm
    return plm.copy()


# ============================================================================
# 均匀圆盘（单个网格单元）的斯托克斯系数
# ============================================================================
def gdisc(rlon, rlat, area, rmass, synthc, synths, lmost, rk):
    """把单个网格单元（视为均匀圆盘）的质量载荷累加到球谐系数中。

    对应 Fortran 子程序 ``gdisc``；``synthc``/``synths`` 原地累加。

    Parameters
    ----------
    rlon, rlat : float  单元中心经、纬度，单位为弧度
    area       : float  单元面积 (km^2)
    rmass      : float  单元质量 (g)
    synthc     : ndarray (lmost+1, lmost+1) 余弦系数，原地累加
    synths     : ndarray (lmost+1, lmost+1) 正弦系数，原地累加
    lmost      : int    最大阶数
    rk         : ndarray 负荷勒夫数 k_l
    """
    # 原文此处为 lmax = 180（编译期常量）；改为跟随模块的截断阶数 LMOST，
    # 默认值不变，因此 lmax=180 时与原实现逐位一致。
    lmax = LMOST
    lmax1 = lmax + 1
    if lmost > lmax:
        raise ValueError(f'error #5 {lmost} {lmax}')

    # 角半径的余弦：clat = cos(角半径)
    clat = 1.0 - area / 6.371e3 ** 2 / 2.0 / PI
    # alpha = np.cos(clat)      # ← 原文（Fortran）中有此行，但 alpha 其后并未使用
    #                           #   （若原意为“角半径”，应写成 alpha = arccos(clat)）
    plmart = martin(lmax1, clat)

    # 圆盘的平均勒让德函数（0 阶系数）
    plmart[:, 0] *= np.sqrt(2.0 / (2.0 * np.arange(lmax1 + 1) + 1.0))
    temp = np.zeros(lmax + 1, dtype=np.float64)
    temp[1:lmax + 1] = (plmart[0:lmax, 0] - plmart[2:lmax + 2, 0]) / 2.0
    temp[0] = (1.0 - clat) / 2.0

    # 单元中心处的勒让德函数
    clat = np.cos(rlat)
    plmart = martin(lmax1, clat)
    for l in range(lmax + 1):
        plmart[l, 0:l + 1] *= np.sqrt(2.0)
        plmart[l, 1:l + 1] *= np.sqrt(2.0)

    h = rmass / (area * 1.0e5 ** 2)      # 水高 (cm)
    ha = h / 6.371e8                     # 归一化水高

    ls = np.arange(lmax + 1)
    fact_l = temp / (2.0 * ls + 1.0)
    coef_l = 3.0 / 5.517 * (1.0 + rk[0:lmax + 1]) / (2.0 * ls + 1.0) * ha

    for m in range(lmax + 1):
        idx = slice(m, lmax + 1)
        ang = m * rlon
        w = fact_l[idx] * plmart[idx, m]
        synthc[idx, m] += w * coef_l[idx] * np.cos(ang)
        synths[idx, m] += w * coef_l[idx] * np.sin(ang)


# ============================================================================
# 由网格值积分求球谐系数
# ============================================================================
def geoid(dens, rlon, rlat, plm, ccos, ssin, nth, nphi, lmost, lmax):
    """对 theta、phi 积分，求 0..lmax 阶的斯托克斯系数。

    对应 Fortran 子程序 ``geoid``。返回 (clm1, slm1)，两者均为
    (lmost+1, lmost+1) 数组（仅 0..lmax 阶有意义）。

    Parameters
    ----------
    dens : ndarray (nphi, nth)  网格上的密度（此处为海面高度，cm）
    plm  : ndarray (lmost+1, lmost+1, nth)  归一化勒让德函数
    ccos : ndarray (lmost+1, nphi)  cos(m*phi)
    ssin : ndarray (lmost+1, nphi)  sin(m*phi)
    """
    if lmax > lmost:
        raise ValueError(f'error #35: {lmax} {lmost}')

    dphi = 360.0 / float(nphi) * DTR     # theta、phi 的网格间隔（弧度）
    dth = 180.0 / float(nth) * DTR
    th = (90.0 - rlat) * DTR             # 余纬

    L = lmax + 1
    # plm1(l, m, i) = plm(l, m, i) * dth * dphi * sin(theta_i)
    plm1 = plm[0:L, 0:L, :] * (dth * dphi * np.sin(th))[None, None, :]

    # 先对经度求和：A[i, m] = sum_j dens[j, i] * cos(m*phi_j)
    A = dens.T @ ccos[0:L, :].T          # (nth, L)
    B = dens.T @ ssin[0:L, :].T          # (nth, L)

    clm1 = np.zeros((lmost + 1, lmost + 1), dtype=np.float64)
    slm1 = np.zeros((lmost + 1, lmost + 1), dtype=np.float64)
    clm1[0:L, 0:L] = np.einsum('lmi,im->lm', plm1, A) / (4.0 * PI)
    slm1[0:L, 0:L] = np.einsum('lmi,im->lm', plm1, B) / (4.0 * PI)
    return clm1, slm1


# ============================================================================
# 读取输入文件
# ============================================================================
def _open_text(path):
    """打开文本输入文件，并**容忍 UTF-8 BOM**。

    Windows 的记事本、PowerShell 的 ``Set-Content -Encoding UTF8`` 等会写出带
    BOM 的文件；用普通 ``utf-8`` 读，首行的第一个字段会带上 ``\\ufeff``，
    控制文件里的文件名就会变成"找不到"。``utf-8-sig`` 对无 BOM 的文件行为不变。
    """
    return open(path, 'r', encoding='utf-8-sig', errors='replace')


def _split_filelist_line(line):
    """把控制文件的一行切成 ``[输入文件, 输出文件]``，**支持带空格的路径**。

    Fortran 原文用列表输入读 ``Filelist``，按空白切分，因此路径里不能有空格；
    但程序一旦装到 ``C:\\Program Files\\...`` 下，这条规则就会把路径拦腰截断
    （``C:\\Program Files\\海平面指纹\\x.txt`` → ``C:\\Program``），报出
    "No such file or directory"。所以这里放宽为：

    * 路径带空格时用**双引号**括起来：``"C:\\a b\\in.txt" "D:\\out c.txt"``；
    * 不带引号仍按空白切分，与原文行为一致（老的控制文件不受影响）。
    """
    s = line.strip()
    if not s:
        return []
    try:
        parts = shlex.split(s, posix=False)
    except ValueError:                 # 引号不配平等，退回按空白切分
        parts = s.split()
    out = []
    for p in parts:
        if len(p) >= 2 and p[0] == p[-1] and p[0] in '"\'':
            p = p[1:-1]                # posix=False 会把引号留下，这里剥掉
        out.append(p)
    return out


def load_mask(path, nth=NTH, nphi=NPHI):
    """读取海陆掩膜文件，返回 (ofcn, rlon, rlat)。

    ofcn : (nphi, nth) 海洋函数（海洋 1、陆地 0）
    rlon : (nphi,) 经度 (度)
    rlat : (nth,)  纬度 (度)
    """
    with _open_text(path) as fh:
        d = np.loadtxt(fh)
    if d.ndim != 2 or d.shape[1] < 3:
        raise ValueError(f'{path}: 掩膜文件应为 3 列（经度 纬度 value）')
    if d.shape[0] != nth * nphi:
        raise ValueError(f'{path}: 期望 {nth * nphi} 行（{nth}x{nphi}），'
                         f'实际 {d.shape[0]} 行')
    d = d.reshape(nth, nphi, 3)
    # Fortran 中 rlon(i)、rlat(j) 为循环内最后一次赋值的值，此处保持一致
    rlon = d[-1, :, 0].copy()
    rlat = d[:, -1, 1].copy()
    ofcn = (1.0 - d[:, :, 2]).T.copy()      # → (nphi, nth)

    lat_bad = np.abs(d[:, :, 1] - d[:, 0:1, 1]).max()
    lon_bad = np.abs(d[:, :, 0] - d[0:1, :, 0]).max()
    if lat_bad > 1e-6 or lon_bad > 1e-6:
        print(f'[警告] {path}: 网格经纬度不完全规则 '
              f'(dlat_max={lat_bad:g}, dlon_max={lon_bad:g})，'
              f'仅使用每个纬度带的第一个经度与每个经度列的最后一个纬度')
    return ofcn, rlon, rlat


def load_love(path, llove=None):
    """读取负荷勒夫数文件（跳过 2 行表头），返回 (h, rk)。

    ``llove`` 默认取当前的 ``LLOVE``（由 :func:`set_lmax` 同步），因此改过
    lmax 之后无需显式传参。
    """
    if llove is None:
        llove = LLOVE
    with _open_text(path) as fh:
        lv = np.loadtxt(fh, skiprows=2)
    if lv.ndim == 1:
        lv = lv[None, :]
    h = np.zeros(llove + 1, dtype=np.float64)
    rk = np.zeros(llove + 1, dtype=np.float64)
    n = min(lv.shape[0], llove + 1)
    h[0:n] = lv[0:n, 1]
    rk[0:n] = lv[0:n, 2]
    if n < llove + 1:
        print(f'[警告] {path}: 只有 {n} 阶勒夫数，而当前 lmax={llove - 1} '
              f'需要 {llove} 阶；l>={n} 的阶将按 0 处理，结果会失真。'
              f'请换用更高阶的勒夫数表，或用 set_lmax()/--lmax 把 lmax '
              f'调到不超过 {n - 1}')
    return h, rk


# ============================================================================
# 单个质量变化网格 → 海平面指纹
# ============================================================================
def solve_one(namein, nameout, ofcn, rlon, rlat, plm, ccos, ssin,
              coefh, coefp, h, rk, niter=NITER, dlon=0.5, dlat=0.5,
              clip_negative=True, progress=None, polar=True):
    """对单个输入网格求解海平面方程，写出结果文件。

    返回 (zmass, tmass, smass, areatot)：分别为解算得到的海水质量、输入载荷质量
    （单位 1e15 g）以及累计载荷质量（g）与面积（km²）。

    Parameters
    ----------
    dlon, dlat : 载荷数据网格的经、纬度间隔（度），必须与实际数据一致
    clip_negative : 是否把负的载荷清零。**原文 Fortran 代码为清零（默认 True）**，
                 但 GRACE 质量异常有正有负（质量亏损就是负值），
                 用 GRACE 数据时须设为 False，否则结果会被严重扭曲。
    progress   : 可选回调 ``progress(frac, message)``，frac∈[0,1]；
                 若回调抛异常，计算会立即中止（用于 GUI 的取消操作）
    polar      : 是否包含极移（polar motion / rotational）反馈，默认 True
                 （与修正版 Fortran、gravity-toolkit 的 POLAR=True 一致）。
                 该反馈只作用于球谐 (l=2, m=1)（Kendall et al. 2005；
                 Tamisiea et al. 2010 式 11）。设为 False 即求解"不含极移反馈"
                 的经典海平面方程，可用于敏感性分析或与不含该反馈的模型对照。
                 本条只是开关，不改变任何公式。
    """
    def rep(frac, msg):
        if progress is not None:
            progress(frac, msg)

    synthc = np.zeros((LSYN + 1, LSYN + 1), dtype=np.float64)
    synths = np.zeros((LSYN + 1, LSYN + 1), dtype=np.float64)

    # ---- 极移（polar motion）反馈 ----
    # 只在 (l=2, m=1) 处生效；polar=False 时不计算这三个系数，迭代中也走通用分支。
    if polar:
        coefpm = (1.0 + rk[2]) * (1.0 + RK2B - H2B) / (RKF - RK2B)
        pmp = (1.0 + rk[2] - h[2] + coefpm) / (1.0 + rk[2])
        # ★注意：Fortran 原文此行分母中的 l 在循环结束后已无物理含义
        #   （Do l = 0, lsyn 结束后 l = lsyn+1，即分母为 2*181+1 = 363）。
        #   极移项只在 l=2, m=1 处生效，按物理意义分母应为 (2*2+1)=5。
        #   此处按物理意义取 l=2；如需与原文逐行对照，可改成
        #   pmh = pmp*(1.0+rk[2])*3.0*RHO0/RHOAVE/float(2*181+1)
        pmh = pmp * (1.0 + rk[2]) * 3.0 * RHO0 / RHOAVE / float(2 * 2 + 1)
        print(f'[极移] 含极移(polar motion)反馈：coefpm={coefpm:.12f}, '
              f'pmp={pmp:.12f}, pmh={pmh:.12f}（仅作用于 l=2, m=1）')
    else:
        print('[极移] 已关闭极移(polar motion)反馈：(l=2, m=1) 使用未含极移的'
              '通用系数 coefh(2)/coefp(2)')

    # ---- 读入网格化的水当量高度，累加成球谐系数 ----
    smass = 0.0
    areatot = 0.0
    # area1 = dlat*dlon*DTR**2*6.371e3**2   # 不含纬度因素的网格面积（原文中未使用）

    rep(0.02, '读取质量变化网格 …')
    with _open_text(namein) as fh:
        data = np.loadtxt(fh)
    if data.ndim == 1:
        data = data[None, :]
    if data.size == 0:
        data = np.zeros((0, 3))

    # ---- 先核对网格间隔：填错会让每个格点面积算错、结果整体失真 ----
    # （第三方交叉验证里实测：1° 数据按默认 0.5° 跑，全场偏差达到峰值的 65%）
    if len(data):
        ulon = np.unique(data[:, 0])
        ulat = np.unique(data[:, 1])
        for _name, _u, _d in (('经度', ulon, dlon), ('纬度', ulat, dlat)):
            if _u.size > 1:
                _dd = float(np.median(np.diff(np.sort(_u))))
                if _d > 0 and abs(_dd - _d) / _d > 0.01:
                    print(f'[警告] 载荷数据的{_name}间隔实际是 {_dd:g}°，'
                          f'而 dlon/dlat 设成了 {dlon:g}/{dlat:g} —— '
                          f'每个格点的面积会算错，结果整体失真。'
                          f'请把{_name}间隔参数改成 {_dd:g}。')

    nclip = 0
    mclip = 0.0
    ncell = len(data)
    for k, row in enumerate(data):
        xlon, xlat, thick = float(row[0]), float(row[1]), float(row[2])
        xlat = 90.0 - xlat
        x1 = xlat - dlat / 2.0
        x2 = xlat + dlat / 2.0
        if x1 < 0.0:
            x1 = 0.0
        if x2 > 180.0:
            x2 = 180.0
        xlon = xlon * DTR
        xlat = xlat * DTR
        area = dlon * DTR * (np.cos(x1 * DTR) - np.cos(x2 * DTR)) * 6.371e3 ** 2
        if thick < 0.0 and clip_negative:   # 原文 Fortran：If(thick<0) thick=0
            nclip += 1
            mclip += -thick * 100.0 * 1.00 * (area * 1.0e10)
            thick = 0.0
        rmass = thick * 100.0 * 1.00 * (area * 1.0e10)   # 水高(m)→cm，面积 km^2→cm^2
        smass += rmass
        areatot += area
        gdisc(xlon, xlat, area, rmass, synthc, synths, LSYN, rk)
        if ncell and (k % 200 == 0 or k == ncell - 1):
            rep(0.02 + 0.48 * (k + 1) / ncell, f'载荷谐波化 {k + 1}/{ncell} 个网格单元')

    if nclip:
        # 真实 GRACE 载荷有正有负（质量亏损），清零会严重扭曲结果，
        # 而原文 Fortran 的行为就是这样，所以这里必须响亮地提示。
        print(f'[警告] {nclip}/{ncell} 个格点的载荷为负，已被**清零**'
              f'（合计 {mclip / 1e15:.4g} Gt）。'
              f'GRACE 等真实数据请改用 --allow-negative（GUI 里勾选'
              f'「允许负值载荷」），否则近场与远场都会失真。')

    # ---- 归一化谐波系数 ----
    tmass = synthc[0, 0] * EARTH_MASS        # 载荷的总质量 (g)
    synthc *= ARAD                           # 乘地球半径后即大地水准面系数 (cm)
    synths *= ARAD

    # ---- 整合海平面方程 ----
    rep(0.52, '积分海洋函数（求海洋面积）…')
    clm1, slm1 = geoid(ofcn, rlon, rlat, plm, ccos, ssin, NTH, NPHI, LMOST, 0)
    ocnint = clm1[0, 0] * 4.0 * PI           # 海洋面积（立体角）

    amass = -tmass / RHO0 / ARAD ** 2 / ocnint
    total = amass * ofcn                      # 0 阶解：水在海面均匀分布

    hclm, hslm = geoid(total, rlon, rlat, plm, ccos, ssin, NTH, NPHI, LMOST, LMOST)

    # ---- 迭代 ----
    ccT = ccos.T                              # (nphi, LMOST+1)
    ssT = ssin.T
    niter = int(niter)
    for it in range(niter):
        if niter:
            rep(0.58 + 0.34 * it / niter,
                f'迭代求解海平面方程 {it + 1}/{niter}')
        total = np.zeros((NPHI, NTH), dtype=np.float64)
        for l in range(LMOST + 1):
            mm = l + 1
            # temp = coefh(l)*(海洋自身负荷的[N-U]) + coefp(l)*(外部载荷的[N-U])
            Tl = (coefh[l] * (hclm[l, 0:mm][None, :] * ccT[:, 0:mm]
                              + hslm[l, 0:mm][None, :] * ssT[:, 0:mm])
                  + coefp[l] * (synthc[l, 0:mm][None, :] * ccT[:, 0:mm]
                                + synths[l, 0:mm][None, :] * ssT[:, 0:mm]))
            if polar and l == 2:
                # //polar motion//  （polar=False 时走上面的通用系数）
                Tl[:, 1] = (pmh * (hclm[2, 1] * ccT[:, 1] + hslm[2, 1] * ssT[:, 1])
                            + pmp * (synthc[2, 1] * ccT[:, 1]
                                     + synths[2, 1] * ssT[:, 1]))
            total += Tl @ plm[l, 0:mm, :]
        total *= ofcn

        clm1, slm1 = geoid(total, rlon, rlat, plm, ccos, ssin, NTH, NPHI, LMOST, 0)
        rint = clm1[0, 0] * 4.0 * PI
        amass = (-tmass / RHO0 / ARAD ** 2 - rint) / ocnint
        total = total + amass * ofcn

        # 求海面高度的球谐系数
        hclm, hslm = geoid(total, rlon, rlat, plm, ccos, ssin, NTH, NPHI,
                           LMOST, LMOST)

    # ---- 输出 ----
    rep(0.94, '计算质量守恒并写出结果 …')
    zmass = hclm[0, 0] * ARAD ** 2 * RHO0 * 4.0 * PI / 1.0e15
    lon_col = np.repeat(rlon, NTH)
    lat_col = np.tile(rlat, NPHI)
    vals = total.reshape(-1)                  # i 外层、j 内层
    with open(nameout, 'w', encoding='utf-8') as f:
        w, d = OUT_FMT
        n = len(vals)
        for k, (lo, la, va) in enumerate(zip(lon_col, lat_col, vals)):
            f.write(f'{lo:5.1f} {la:5.1f} {_fmt_fortran_e(va, w, d)}\n')
            if k % 20000 == 0 and n:
                rep(0.94 + 0.05 * k / n, f'写出结果 {k}/{n} 行')
    rep(1.0, '完成')

    return zmass, tmass, smass, areatot


def _fmt_fortran_e(v, width=12, digits=4):
    """按 Fortran 的 E 格式（0.ddddE±ee）输出，字段总宽度为 width。

    注意：Fortran 要求尾数在 [0.1, 1) 区间；若四舍五入到 digits 位后尾数进位成
    1.0000…，必须把尾数除以 10、指数加 1（例如 0.1 必须写成 0.1000E+00 而不是
    1.0000E-01），否则下游按定点格式解析会出错。
    """
    zero = '0.' + '0' * digits + 'E+00'
    if v is None or not np.isfinite(v) or v == 0.0:
        return ' ' * max(0, width - len(zero)) + zero
    exp = int(np.floor(np.log10(abs(v)))) + 1
    mant = v / 10.0 ** exp
    while abs(mant) >= 1.0:
        mant /= 10.0
        exp += 1
    while abs(mant) < 0.1:
        mant *= 10.0
        exp -= 1
    if round(abs(mant), digits) >= 1.0:      # 进位到 1.0000 -> 重新归一
        mant /= 10.0
        exp += 1
    mw = width - 4               # 尾数域宽度（指数域 E±dd 占 4 列）
    return f'{mant:{mw}.{digits}f}E{exp:+03d}'


# ============================================================================
# 主程序
# ============================================================================
def run(mask_file, love_file, list_file, niter=NITER, dlon=0.5, dlat=0.5,
        clip_negative=True, progress=None, lmax=None, polar=True):
    """按 Filelist.txt 逐行处理。

    progress : 可选回调 ``progress(frac, message)``，frac∈[0,1]；抛异常即中止计算。
    dlon/dlat: 载荷数据网格间隔（度）。
    lmax     : 截断阶数；给定则先调用 :func:`set_lmax`（默认 None = 沿用当前值）。
    polar    : 是否包含极移（polar motion）反馈（默认 True，同修正版 Fortran）。
               只在 (l=2, m=1) 处生效，详见 :func:`solve_one`。
    """
    def rep(frac, msg):
        if progress is not None:
            progress(frac, msg)

    t0 = time.time()

    if lmax is not None:
        set_lmax(lmax)
    rep(0.00, '读取海陆掩膜 …')
    ofcn, rlon, rlat = load_mask(mask_file)
    rep(0.03, '读取负荷勒夫数 …')
    h, rk = load_love(love_file)
    ls = np.arange(LLOVE + 1)
    coefh = (1.0 + rk - h) * 3.0 * RHO0 / RHOAVE / (2.0 * ls + 1.0)
    coefp = (1.0 + rk - h) / (rk + 1.0)

    # //计算勒让德函数和 cos(m*phi)、sin(m*phi)
    plm_bytes = 8 * (LMOST + 1) ** 2 * NTH
    print(f'计算勒让德函数 ... (lmax={LMOST}, plm 约 {plm_bytes / 1e6:.0f} MB)')
    plm = np.zeros((LMOST + 1, LMOST + 1, NTH), dtype=np.float64)
    fac = np.full(LMOST + 1, 2.0)
    fac[0] = np.sqrt(2.0)
    for j in range(NTH):
        x = np.cos((90.0 - rlat[j]) * DTR)
        plm[:, :, j] = martin(LMOST, x) * fac[None, :]
        if j % 10 == 0:
            rep(0.05 + 0.20 * (j + 1) / NTH, f'计算勒让德函数 {j + 1}/{NTH} 条纬度带')

    m_sin = np.arange(LMOST + 1)[:, None]
    phase = m_sin * (rlon[None, :] * DTR)
    ccos = np.cos(phase)
    ssin = np.sin(phase)

    # //逐行读入控制文件
    base = os.path.dirname(os.path.abspath(list_file))
    with _open_text(list_file) as fl:
        lines = [ln.strip() for ln in fl if ln.strip()]

    if not lines:
        print(f'[警告] 控制文件 {list_file} 为空，没有任务需要处理')
        return

    results = []
    ntask = len(lines)
    for it, ln in enumerate(lines):
        parts = _split_filelist_line(ln)
        if len(parts) < 2:
            print(f'[跳过] 控制文件行无法解析出两个文件名: {ln!r}')
            continue
        namein, nameout = parts[0], parts[1]
        inpath = namein if os.path.exists(namein) else os.path.join(base, namein)
        outpath = nameout if os.path.isabs(nameout) else os.path.join(base, nameout)
        print(f'done reading from the input file: {namein}')
        if not os.path.exists(inpath):
            # 说清楚是哪个文件、控制文件在哪、以及最常见的原因（路径被切分），
            # 免得只甩一个 "No such file or directory" 让人无从下手。
            raise FileNotFoundError(
                f'控制文件里的输入文件不存在：{namein}\n'
                f'（控制文件：{list_file}；按相对路径解析得到：{inpath}）\n'
                f'提示：路径含空格时必须用双引号括起来写进控制文件，'
                f'否则会被按空白切分而截断。')

        lo = 0.25 + 0.75 * it / ntask
        span = 0.75 / ntask
        zmass, tmass, smass, areatot = solve_one(
            inpath, outpath, ofcn, rlon, rlat, plm, ccos, ssin,
            coefh, coefp, h, rk, niter, dlon=dlon, dlat=dlat,
            clip_negative=clip_negative, polar=polar,
            progress=(None if progress is None else
                      (lambda f, m, _lo=lo, _s=span: rep(_lo + _s * f, m))))

        print(f'  载荷总质量 = {tmass / 1.0e15:.6f} Gt, '
              f'解算海水质量 = {zmass:.6f} Gt '
              f'(应等于 {-tmass / 1.0e15:.6f})')
        print(f'  累计载荷面积 = {areatot:.4g} km^2, 累计质量 = {smass:.4g} g')
        print(f'done all from {namein} -> {nameout}')
        results.append(dict(namein=namein, nameout=outpath, zmass=zmass,
                            tmass=tmass, smass=smass, areatot=areatot))

    rep(1.0, '全部完成')
    print(f'全部完成，用时 {time.time() - t0:.1f} s')
    return results


def main(argv=None):
    ap = argparse.ArgumentParser(
        description='海平面指纹 (SLF) 计算 —— sleqn.f90 的 Python 版本')
    ap.add_argument('--mask', default='land.fcn.1_deg',
                    help='海陆掩膜文件（默认 land.fcn.1_deg）')
    ap.add_argument('--love', default='love_numbers',
                    help='负荷勒夫数文件（默认 love_numbers）')
    ap.add_argument('--list', dest='filelist', default='Filelist.txt',
                    help='控制文件（默认 Filelist.txt）')
    ap.add_argument('--niter', type=int, default=NITER,
                    help=f'迭代次数，0 表示水均匀铺在一层海面上（默认 {NITER}）')
    ap.add_argument('--fmt', default='e12.4',
                    help='结果输出格式，形如 e12.4（与 Fortran 一致，默认）'
                         '或 e18.10（更高精度）')
    ap.add_argument('--allow-negative', action='store_true',
                    help='允许负的载荷（GRACE 质量亏损）。原文 Fortran 会把负值清零，'
                         '用 GRACE 数据时必须加此选项')
    ap.add_argument('--dlon', type=float, default=0.5,
                    help='载荷数据网格经度间隔（度），必须与实际数据一致（默认 0.5）')
    ap.add_argument('--dlat', type=float, default=0.5,
                    help='载荷数据网格纬度间隔（度），必须与实际数据一致（默认 0.5）')
    ap.add_argument('--lmax', type=int, default=DEF_LMOST,
                    help=f'截断阶数（默认 {DEF_LMOST}）。原文 Fortran 固定为 180；'
                         f'改大需要 love_numbers 有相应的高阶勒夫数，'
                         f'改小可用于低频分析或与低阶模型对照')
    ap.add_argument('--no-polar', dest='polar', action='store_false',
                    help='关闭极移（polar motion / rotational）反馈。默认包含该反馈'
                         '（与修正版 Fortran、gravity-toolkit 一致）；该反馈只作用于'
                         '球谐 (l=2, m=1)，关闭后可用于敏感性分析或与不含该反馈的'
                         '模型对照')
    args = ap.parse_args(argv)

    global OUT_FMT
    try:
        w, d = args.fmt.lower().lstrip('e').split('.')
        OUT_FMT = (int(w), int(d))
        _fmt_fortran_e(1.2345e-3, *OUT_FMT)
    except Exception:
        print(f'[错误] 无法解析 --fmt {args.fmt!r}，应形如 e12.4', file=sys.stderr)
        return 2

    if args.lmax < LMAX_MIN:
        print(f'[错误] --lmax 至少为 {LMAX_MIN}（本程序固定要求，收到 {args.lmax}）；'
              f'极移反馈需要 l=2，网格分辨率也远高于此', file=sys.stderr)
        return 2

    for p in (args.mask, args.love, args.filelist):
        if not os.path.exists(p):
            print(f'[错误] 找不到文件：{p}', file=sys.stderr)
            return 2

    print(f'极移(polar motion)反馈：{"开启" if args.polar else "已关闭（--no-polar）"}')
    run(args.mask, args.love, args.filelist, args.niter,
        dlon=args.dlon, dlat=args.dlat,
        clip_negative=not args.allow_negative, lmax=args.lmax,
        polar=args.polar)
    return 0


if __name__ == '__main__':
    sys.exit(main())
