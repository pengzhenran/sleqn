#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
selftest_sleqn.py —— sleqn.py 的自检脚本
=======================================

在没有真实 GRACE 数据的情况下，用合成数据检验 sleqn.py 是否算“对”：

  1. 质量守恒：解算得到的海水质量应严格等于输入载荷质量的相反数
     （Fortran 原文注释：'the mass in gton is (should = -tmass/1E15)'）；
  2. 线性性：载荷加倍 → 海平面指纹加倍；
  3. 迭代收敛：niter=0（水均匀铺一层）与 niter≥2 的解仅差一个自吸引/负荷项，
     两者质量守恒均成立；
  4. 指纹形态：质量载荷吸引海水并向其堆积 —— 载荷处海平面抬升，
     远场（对跖点）海平面下降，这是海平面指纹的典型特征；
  5. 输出文件顺序：把结果文件按 (经度, 纬度) 重新组织后做面积加权平均，
     应精确等于全球水量守恒给出的“均匀海面”值 -tmass/(rho_w*a^2*4pi)。

运行： python selftest_sleqn.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sleqn  # noqa: E402
from make_demo_data import make_load, make_love, make_mask  # noqa: E402


def make_mask_allocean(path, nth=180, nphi=360):
    """全球都是海洋（海洋函数 = 1）的掩膜，便于做严格的质量守恒检验。"""
    make_mask(path, nth=nth, nphi=nphi, land=False)


# ---------------------------------------------------------------- 主流程
def main():
    t0 = time.time()
    tmp = tempfile.mkdtemp(prefix='sleqn_selftest_')
    print(f'临时目录: {tmp}')

    mask = os.path.join(tmp, 'land.fcn.1_deg')
    love = os.path.join(tmp, 'love_numbers')
    in1 = os.path.join(tmp, 'load_x1.txt')
    in2 = os.path.join(tmp, 'load_x2.txt')
    out1 = os.path.join(tmp, 'slf_x1.txt')
    out2 = os.path.join(tmp, 'slf_x2.txt')
    out3 = os.path.join(tmp, 'slf_x1_niter0.txt')
    out4 = os.path.join(tmp, 'slf_x1_hp.txt')

    make_mask_allocean(mask)
    make_love(love)
    make_load(in1, thick=1.0)
    make_load(in2, thick=2.0)

    # ---- 与 run() 相同的前处理 ----
    ofcn, rlon, rlat = sleqn.load_mask(mask)
    h, rk = sleqn.load_love(love)
    ls = np.arange(sleqn.LLOVE + 1)
    coefh = (1.0 + rk - h) * 3.0 * sleqn.RHO0 / sleqn.RHOAVE / (2.0 * ls + 1.0)
    coefp = (1.0 + rk - h) / (rk + 1.0)

    print('计算勒让德函数 ...')
    plm = np.zeros((sleqn.LMOST + 1, sleqn.LMOST + 1, sleqn.NTH))
    fac = np.full(sleqn.LMOST + 1, 2.0)
    fac[0] = np.sqrt(2.0)
    for j in range(sleqn.NTH):
        x = np.cos((90.0 - rlat[j]) * sleqn.DTR)
        plm[:, :, j] = sleqn.martin(sleqn.LMOST, x) * fac[None, :]
    m_sin = np.arange(sleqn.LMOST + 1)[:, None]
    ccos = np.cos(m_sin * (rlon[None, :] * sleqn.DTR))
    ssin = np.sin(m_sin * (rlon[None, :] * sleqn.DTR))
    print(f'  检查 plm(0,0)=1: {plm[0, 0, 0]:.15f}')
    assert abs(plm[0, 0, 0] - 1.0) < 1e-12

    def solve(inp, outp, niter, polar=True):
        return sleqn.solve_one(inp, outp, ofcn, rlon, rlat, plm, ccos, ssin,
                               coefh, coefp, h, rk, niter, polar=polar)

    print('\n[1] niter=2 求解 ...')
    z1, tm1, sm1, ar1 = solve(in1, out1, 2)
    print('\n[2] niter=0 求解 ...')
    z0, tm0, sm0, ar0 = solve(in1, out3, 0)
    print('\n[3] 载荷加倍 (thick x2), niter=2 求解 ...')
    z2, tm2, sm2, ar2 = solve(in2, out2, 2)
    print('\n[4] 高精度输出求解（检验结果文件顺序）...')
    sleqn.OUT_FMT = (20, 12)
    z3, tm3, sm3, ar3 = solve(in1, out4, 2)
    sleqn.OUT_FMT = (12, 4)

    ok = True

    # ---- 检验 1：质量守恒 ----
    for tag, z, tm in (('niter=2', z1, tm1), ('niter=0', z0, tm0),
                       ('thick x2', z2, tm2)):
        target = -tm / 1.0e15
        err = abs(z - target) / abs(target)
        print(f'\n[检验1] 质量守恒 ({tag}): 解算 {z:.10f} Gt, '
              f'期望 {target:.10f} Gt, 相对误差 {err:.3e}')
        ok &= err < 1e-8

    # ---- 检验 2：线性性 ----
    rel = abs(z2 - 2.0 * z1) / abs(2.0 * z1)
    print(f'\n[检验2] 线性性: 2*z(x1)={2.0 * z1:.10f}, z(x2)={z2:.10f}, '
          f'相对偏差 {rel:.3e}')
    ok &= rel < 1e-8

    # ---- 检验 3：迭代确实改变了场，且都满足质量守恒 ----
    a1 = np.loadtxt(out1)
    a0 = np.loadtxt(out3)
    diff = np.abs(a1[:, 2] - a0[:, 2]).max()
    print(f'\n[检验3] niter=0 与 niter=2 的最大差异 = {diff:.4f} cm '
          f'(迭代/自吸引项量级)')
    ok &= diff > 0.0

    # ---- 检验 4：指纹形态（正质量载荷吸引海水向其堆积） ----
    lon, lat, sl = a1[:, 0], a1[:, 1], a1[:, 2]
    near = sl[(np.abs(lon - 2.5) < 2.0) & (np.abs(lat - 78.0) < 2.0)].mean()
    far = sl[(np.abs(lon - 2.5) < 2.0) & (np.abs(lat + 80.0) < 2.0)].mean()
    print(f'\n[检验4] 海平面指纹：载荷处 {near:+.4f} cm，对跖点 {far:+.4f} cm，'
          f'最小值 {sl.min():+.4f} cm，最大值 {sl.max():+.4f} cm')
    print(f'        极值位于 ({lon[sl.argmin()]:.1f}E, {lat[sl.argmin()]:.1f}N) 与 '
          f'({lon[sl.argmax()]:.1f}E, {lat[sl.argmax()]:.1f}N)')
    # 量级粗估：把载荷视作半径为 R 的均匀圆盘，盘心处
    #   S ~ (1 + k' - h') * 2*pi*G*sigma*R / g
    sigma = tm1 / (ar1 * 1.0e10)            # g/cm^2
    R = np.sqrt(ar1 * 1.0e10 / np.pi)       # cm
    G = 6.674e-8
    est = 2.03 * 2.0 * np.pi * G * sigma * R / 980.0
    print(f'        解析粗估（圆盘近似）峰值 ≈ {est:.3f} cm，实算 {near:.3f} cm，'
          f'比值 {near / est:.2f}')
    ok &= (near > 0.0) and (far < 0.0) and (near > far)
    ok &= (0.3 < near / est < 3.0)

    # ---- 检验 5：输出文件顺序 + 全球水量积分 ----
    # 输出文件按 i（经度）外层、j（纬度）内层写出；若顺序错位，
    # 下面按 (经度, 纬度) 还原网格后做的面积积分会明显偏离理论值。
    # 注意：程序内部用的是中点求积，∫S dΩ 的离散权重和为 Στ sinτ·dθ·dφ，
    # 与 4π 相差 ~1e-5，故这里用同一套离散权重做严格比较。
    a_hp = np.loadtxt(out4)
    grid = a_hp[:, 2].reshape(sleqn.NPHI, sleqn.NTH)
    dth = 180.0 / sleqn.NTH * sleqn.DTR
    dphi = 360.0 / sleqn.NPHI * sleqn.DTR
    wlat = np.sin((90.0 - rlat) * sleqn.DTR) * dth * dphi
    integral = (grid * wlat[None, :]).sum()
    expect = -tm1 / (sleqn.RHO0 * sleqn.ARAD ** 2)
    err5 = abs(integral - expect) / abs(expect)
    print(f'\n[检验5] 输出网格的 ∫S dΩ = {integral:+.10e} cm·sr，'
          f'理论值 -tmass/(rho*a^2) = {expect:+.10e}，相对误差 {err5:.3e}')
    print(f'        等效均匀海面高度 = {integral / (4.0 * np.pi):+.10f} cm')
    ok &= err5 < 1e-8

    # 若把输出顺序当成 j 外层、i 内层，结果应当明显不同（反证顺序检验有效）
    wrong = (a_hp[:, 2].reshape(sleqn.NTH, sleqn.NPHI)
             * wlat[:, None]).sum()
    print(f'        （若误按纬度外层解读则得 {wrong:+.6e}，'
          f'与理论值相差 {abs(wrong - expect) / abs(expect):.1e}，'
          f'说明本检验有效）')
    ok &= abs(wrong - expect) > 1e-4

    # ---- 检验 6：默认输出格式与 Fortran 的 E12.4 一致 ----
    import re
    with open(out1, 'r', encoding='utf-8') as f:
        head = [next(f).rstrip('\n') for _ in range(5)]
    ok6 = True
    for hh in head:
        ok6 &= (len(hh) == 24)
        ok6 &= (hh[5] == ' ' and hh[11] == ' ')
        ok6 &= bool(re.fullmatch(r'[ ]{1,3}[ -]?0\.[0-9]{4}E[+-][0-9]{2}', hh[12:]))
        try:
            float(hh[12:])
        except ValueError:
            ok6 = False
    print(f'\n[检验6] 默认输出格式 (F5.1,1X,F5.1,1X,E12.4) 前 5 行:')
    for hh in head:
        print(f'        |{hh}|')
    print(f'        行长 24、字段位置与 E12.4 尾数格式均符合: {ok6}')
    ok &= ok6

    # ---- 检验 7：E 格式边界值（尾数必须落在 [0.1,1) 且四舍五入正确） ----
    # 0.1 这类值若处理不当会写成 1.0000E-01，不符合 Fortran 的 0.ddddE±ee 规则
    tricky = [0.1, -0.1, 0.9999999999999, 9.99999e-3, 1.0, -1.0, 0.09999999999999999,
              1234.5, 1e-3, 9.9999e2, 0.0, 1.0351, -0.0196, 0.99999]
    ok7 = True
    print('\n[检验7] E12.4 边界值与 Fortran 0.ddddE±ee 规则:')
    for v in tricky:
        s = sleqn._fmt_fortran_e(v, 12, 4)
        m = re.fullmatch(r'[ ]*([ -]?)0\.([0-9]{4})E([+-][0-9]{2})', s)
        good = (m is not None) and (len(s) == 12)
        if good and v != 0.0:
            parsed = float(s)
            expo = int(s[-3:])
            tol = 0.5 * 10.0 ** (expo - 4) * 1.0001     # 尾数 4 位小数 -> 半个末位
            good &= abs(parsed - v) <= tol
        ok7 &= good
        print(f'        v={v!r:22s} -> |{s}|  {"OK" if good else "!! 不合规"}')
    print(f'        全部符合: {ok7}')
    ok &= ok7

    # ---- 检验 8：极移（polar motion）反馈开关 ----
    # 关掉极移反馈应当：(a) 仍然严格质量守恒；(b) 结果略有不同；
    # (c) 差异几乎全部落在球谐 (2,1)（该反馈只作用在这一项上）。
    print('\n[检验8] 极移（polar motion）反馈开关 polar=True/False:')
    out5 = os.path.join(tmp, 'slf_x1_nopolar.txt')
    sleqn.OUT_FMT = (20, 12)
    z4, tm4, sm4, ar4 = solve(in1, out5, 2, polar=False)
    sleqn.OUT_FMT = (12, 4)
    rel8 = abs(z4 + tm4 / 1.0e15) / abs(tm4 / 1.0e15)
    a_np = np.loadtxt(out5)
    diff8 = a_hp[:, 2] - a_np[:, 2]
    g_on = a_hp[:, 2].reshape(sleqn.NPHI, sleqn.NTH)
    g_off = a_np[:, 2].reshape(sleqn.NPHI, sleqn.NTH)
    clm, slm = sleqn.geoid(g_on - g_off, rlon, rlat, plm, ccos, ssin,
                           sleqn.NTH, sleqn.NPHI, sleqn.LMOST, sleqn.LMOST)
    tot = float((clm ** 2 + slm ** 2).sum())
    frac21 = float(clm[2, 1] ** 2 + slm[2, 1] ** 2) / tot if tot > 0 else 0.0
    print(f'        关极移后质量守恒相对误差 {rel8:.3e}；'
          f'开/关 max|Δ| = {np.abs(diff8).max():.4e} cm'
          f'（占场峰值 {np.abs(a_hp[:, 2]).max():.4f} cm）')
    print(f'        差场 (2,1) 功率占比 {frac21:.4%}')
    ok &= rel8 < 1e-8
    ok &= np.abs(diff8).max() > 0.0
    ok &= frac21 > 0.95

    print('\n' + ('=' * 60))
    print('自检结果：' + ('全部通过 ✔' if ok else '存在失败项 ✘'))
    print(f'耗时 {time.time() - t0:.1f} s')
    print('=' * 60)
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
