#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_guide_figs.py —— 生成《使用说明》的两张科学配图
============================================================================

    python tools/make_guide_figs.py            # 只写 docs/使用说明_img/
    python tools/make_guide_figs.py --figs     # 同时刷新 figs/（总结报告用）

两张图：

* **图 2　原理示意**：海平面方程各物理量。要点
    - 方程文字放在**左上角**（旧版压在曲线的下坡段上，被挡住）；
    - 远场"海面低于参考面"的量极小（近场 1 cm 量级、远场 0.01 cm 量级），
      主图上根本看不出来，所以右上角加一个**放大窗**把远场单独画清楚。

* **图 3　载荷与指纹**：合成算例。要点
    - **经度以 0° 为中心**（旧版 0~360°，异常被挤在左上角）；做法是把
      0…360 的场滚半圈并改用 −180…180 的坐标，物理位置不变；
    - 载荷总质量按 Σ(水高 × 格点面积 × ρ) 正确计算并标在标题里
      （旧版用了 6.556 Gt/(m·格点) 的系数，比真值大 10 倍）。

海平面场的数值由 ``sleqn`` 直接算出（不需要 Fortran），与编译版逐字节一致。
正负载 → 近场抬升、远场下降，质量守恒的核查见 ``tools/verify_load_sign.py``。
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import matplotlib                                              # noqa: E402
matplotlib.use('Agg')
import matplotlib.pyplot as plt                                # noqa: E402
from matplotlib.patches import Rectangle                       # noqa: E402

import sleqn                                                   # noqa: E402

plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei']
plt.rcParams['axes.unicode_minus'] = False
plt.rcParams['savefig.dpi'] = 120
plt.rcParams['savefig.bbox'] = 'tight'

DEMO = os.path.join(ROOT, 'demo')


# ============================================================ 图 2：原理示意
def _curves(x):
    """原理示意图用的三条曲线（纯示意，纵向已大幅放大）。"""
    y_ref = -0.03 * x ** 2                                    # 原始固体表面
    y_def = y_ref + 0.14 * np.exp(-(x / 0.35) ** 2)           # 变形后 R^L
    y_sea = y_ref + 0.24 * np.exp(-(x / 0.50) ** 2) - 0.018   # 海面 S
    return y_ref, y_def, y_sea


def _at(x, xs, ys):
    """在曲线上取 x 处的值（线性插值）。"""
    return float(np.interp(x, xs, ys))


def draw_principle(out_png):
    fig, ax = plt.subplots(figsize=(9.6, 5.8))
    xs = np.linspace(-1.05, 1.05, 800)
    y_ref, y_def, y_sea = _curves(xs)
    y_geo = y_sea + 0.006

    ax.set_xlim(-1.24, 1.30)
    ax.set_ylim(-0.62, 1.72)                 # 上方留白给标题与放大窗

    # ---- 固体地球 / 海水 / 界面 ----
    ax.fill_between(xs, y_def, -0.62, color='#efebe9', zorder=0)
    ax.plot(xs, y_def, '-', color='#8d6e63', lw=2.2, zorder=3,
            label='变形后固体表面 $R^{L}$')
    ax.fill_between(xs, y_def, y_sea, color='#90caf9', alpha=0.6, zorder=1)
    ax.plot(xs, y_geo, ':', color='#c62828', lw=2.4, zorder=4,
            label='大地水准面 $G^{L}$')
    ax.plot(xs, y_sea, '-', color='#1565c0', lw=2.0, zorder=5, label='海面 $S$')
    ax.plot(xs, y_ref, '--', color='#9e9e9e', lw=1.4, zorder=2,
            label='原始固体表面（参考面）')

    # ---- 负荷 ----
    ax.add_patch(Rectangle((-0.19, 0.235), 0.38, 0.20, color='#bbdefb',
                           ec='#0d47a1', lw=1.5, zorder=6))
    ax.text(0, 0.335, '负荷 $L$', ha='center', va='center', fontsize=11,
            color='#0d47a1', zorder=7)
    ax.annotate('冰盖 / 陆地水质量变化（正负载）', xy=(0.19, 0.33),
                xytext=(0.46, 0.42), fontsize=9, color='#0d47a1',
                arrowprops=dict(arrowstyle='->', color='#0d47a1', lw=1.1))

    # ---- 近场：S 的定义（双箭头，留在原处） ----
    xa = -0.30
    ax.annotate('', xy=(xa, _at(xa, xs, y_sea)), xytext=(xa, _at(xa, xs, y_ref)),
                arrowprops=dict(arrowstyle='<->', color='#2e7d32', lw=1.8))
    ax.text(xa - 0.05, 0.075, '$S$', fontsize=11, color='#2e7d32',
            ha='right', va='center')
    # 方程移到左上角（旧版压在下坡曲线上被挡住），用细引线连到双箭头
    ax.annotate('近场（载荷附近）：\n$S=C\\,(G^{L}-R^{L})>0$\n海面抬升',
                xy=(xa - 0.03, 0.11), xytext=(-1.22, 0.80),
                fontsize=10, color='#2e7d32', ha='left', va='center',
                bbox=dict(boxstyle='round,pad=0.4', fc='#f1f8f2',
                          ec='#a5d6a7', lw=1.0),
                arrowprops=dict(arrowstyle='->', color='#2e7d32', lw=1.0,
                                ls='--', shrinkA=2, shrinkB=2))

    # ---- 远场放大窗 ----
    axin = ax.inset_axes([0.60, 0.555, 0.375, 0.275])
    axin.plot(xs, y_ref, '--', color='#9e9e9e', lw=1.3, label='参考面')
    axin.plot(xs, y_sea, '-', color='#1565c0', lw=1.9, label='海面 $S$')
    xf = 0.98
    axin.annotate('', xy=(xf, _at(xf, xs, y_sea)), xytext=(xf, _at(xf, xs, y_ref)),
                  arrowprops=dict(arrowstyle='<->', color='#ef6c00', lw=1.7))
    axin.set_xlim(0.66, 1.16)
    axin.set_ylim(-0.062, -0.002)
    axin.set_xticks([])
    axin.set_yticks([])
    axin.set_title('远场放大：海面低于参考面（纵向约 20×）', fontsize=8.5,
                   color='#ef6c00', pad=4)
    for s in axin.spines.values():
        s.set_color('#ef6c00')
    axin.legend(loc='lower left', fontsize=7.5, framealpha=0.92)

    # 主图上的远场标记
    ax.annotate('', xy=(xf, _at(xf, xs, y_sea)), xytext=(xf, _at(xf, xs, y_ref)),
                arrowprops=dict(arrowstyle='<->', color='#ef6c00', lw=1.6))
    ax.annotate('远场（见右上放大窗）', xy=(xf, -0.045), xytext=(0.70, 0.20),
                fontsize=9, color='#ef6c00', ha='center',
                arrowprops=dict(arrowstyle='->', color='#ef6c00', lw=1.2))

    # ---- 标题 ----
    ax.text(0, 1.62, '海平面方程：$S(\\theta,\\psi,t)=C(\\theta,\\psi,t)'
            '\\,[G^{L}(\\theta,\\psi,t)-R^{L}(\\theta,\\psi,t)]$',
            ha='center', fontsize=13.5)
    ax.text(0, 1.47, '$C$：海洋函数（海洋 1，陆地 0）；'
            '$G^{L}$：负荷引起的大地水准面异常；$R^{L}$：固体地球表面径向位移',
            ha='center', fontsize=9.5, color='#424242')
    ax.text(0, -0.555, '示意图：纵向尺度已大幅放大；近场抬升与远场下降的'
            '真实量级相差约两个数量级',
            ha='center', fontsize=8.5, color='#757575', style='italic')

    ax.legend(loc='lower left', framealpha=0.9, fontsize=9)
    ax.axis('off')
    fig.savefig(out_png)
    plt.close(fig)
    print(f'  已写入 {os.path.relpath(out_png, ROOT)}')
    return out_png


# ============================================================ 图 3：载荷与指纹
def load_mass_Gt(load, dlon=0.5, dlat=0.5):
    """载荷总质量 (Gt)：Σ(水当量高度 m × 单元面积 m² × ρ_water)。

    单元面积用与 sleqn.gdisc 相同的球面公式。旧版配图误用了
    ``Σh × 6.556``，把 6.556 当成"每格点每米的 Gt 数"（实际是 0.6556），
    结果大了整整 10 倍。
    """
    tot = 0.0
    for _x, y, thick in load:
        xl = 90.0 - y
        x1 = max(0.0, xl - dlat / 2.0)
        x2 = min(180.0, xl + dlat / 2.0)
        area_km2 = dlon * sleqn.DTR * (np.cos(x1 * sleqn.DTR)
                                       - np.cos(x2 * sleqn.DTR)) * 6.371e3 ** 2
        tot += thick * area_km2 * 1.0e6 * 1.0e3        # m × m² × kg/m³ = kg
    return tot / 1e12                                   # kg → Gt


def compute_field():
    """用 sleqn.py 算 demo 算例，返回 (S, load, 载荷质量 Gt)。"""
    mask = os.path.join(DEMO, 'land.fcn.1_deg')
    love = os.path.join(DEMO, 'love_numbers')
    inp = os.path.join(DEMO, 'load_demo.txt')
    ofcn, rlon, rlat = sleqn.load_mask(mask)
    h, rk = sleqn.load_love(love)
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
    tmp = tempfile.mkdtemp(prefix='guide_figs_')
    out = os.path.join(tmp, 'S.txt')
    _zm, _tm, smass, _ar = sleqn.solve_one(
        inp, out, ofcn, rlon, rlat, plm, np.cos(ph), np.sin(ph),
        coefh, coefp, h, rk, niter=2, dlon=0.5, dlat=0.5, clip_negative=False)
    S = np.loadtxt(out)[:, 2].reshape(sleqn.NPHI, sleqn.NTH)
    os.remove(out)
    os.rmdir(tmp)
    ld = np.loadtxt(inp)
    return S, rlon, rlat, ld, load_mass_Gt(ld)


def _roll_center(C):
    """把 0…360°E 的场滚成以 0° 为中心、坐标为 −180…180 的排布。"""
    return np.roll(C, -C.shape[0] // 2, axis=0)


def draw_example(out_png, S, rlon, rlat, load, mass_Gt):
    fig, axes = plt.subplots(3, 1, figsize=(9.6, 9.6), constrained_layout=True)
    nphi = S.shape[0]
    lon_e = np.arange(-180, 181)                     # 以 0° 为中心的边界
    lat_e = np.arange(90, -91, -1)                   # 必须降序（第 0 行 = 89.5°N）

    def mesh(ax, C, **kw):
        assert C.shape == (nphi, sleqn.NTH), C.shape
        return ax.pcolormesh(lon_e, lat_e, _roll_center(C).T, shading='auto', **kw)

    # (a) 载荷
    lon_c = np.unique(load[:, 0])
    lat_c = np.unique(load[:, 1])
    lat_c = lat_c[np.argsort(-lat_c)]
    L = np.zeros((len(lon_c), len(lat_c)))
    for x, y, t in load:
        L[int(np.argmin(np.abs(lon_c - x))),
          int(np.argmin(np.abs(lat_c - y)))] = t
    lon_ce = np.concatenate([[lon_c[0] - 0.25], lon_c + 0.25])
    lat_ce = np.concatenate([[lat_c[0] + 0.25], lat_c - 0.25])
    im = axes[0].pcolormesh(lon_ce, lat_ce, (L * 100).T, cmap='Blues',
                            vmin=0, vmax=100, shading='flat')
    axes[0].set_title(f'(a) 输入：合成质量载荷（水当量高度，cm）——北极附近 '
                      f'{lon_c[0] - 0.25:.1f}~{lon_c[-1] + 0.25:.1f}°E、'
                      f'{lat_c[-1] - 0.25:.1f}~{lat_c[0] + 0.25:.1f}°N 的方形正载荷，'
                      f'共 {mass_Gt:.1f} Gt')
    axes[0].annotate('载荷位置\n(5°×5°，100 cm)', xy=(lon_c.mean(), lat_c.mean()),
                     xytext=(30, 52), fontsize=9, color='#0d47a1',
                     ha='left',
                     bbox=dict(boxstyle='round,pad=0.3', fc='white',
                               ec='#90a4ae', alpha=0.9),
                     arrowprops=dict(arrowstyle='->', color='#0d47a1', lw=1.2))
    fig.colorbar(im, ax=axes[0], shrink=0.9, label='cm')

    # 载荷覆盖范围（虚线框），便于对比异常位置
    box = Rectangle((lon_c[0] - 0.25, lat_c[-1] - 0.25),
                    lon_c[-1] - lon_c[0] + 0.5, lat_c[0] - lat_c[-1] + 0.5,
                    fill=False, ec='k', lw=0.9, ls='--', alpha=0.65, zorder=5)

    # (b)(c) 指纹
    vmax = np.abs(S).max()
    j_peak = int(np.argmax(np.abs(S).max(axis=0)))
    lat_min, lat_max = lat_c.min() - 0.25, lat_c.max() + 0.25
    im2 = mesh(axes[1], S, cmap='RdBu_r', vmin=-vmax, vmax=vmax)
    axes[1].set_title(f'(b) 海平面指纹 $S$（cm，对称色标 ±{vmax:.3f}）：'
                      f'峰值 {S.max():+.3f} cm 出现在 {rlat[j_peak]:.1f}°N '
                      f'（载荷 {lat_min:.1f}~{lat_max:.1f}°N）——近场抬升')
    axes[1].add_patch(Rectangle((box.get_x(), box.get_y()), box.get_width(),
                                box.get_height(), fill=False, ec='k', lw=0.9,
                                ls='--', alpha=0.65, zorder=5))
    fig.colorbar(im2, ax=axes[1], shrink=0.9, label='cm')

    v2 = 0.03
    im3 = mesh(axes[2], S, cmap='RdBu_r', vmin=-v2, vmax=v2)
    axes[2].set_title(f'(c) 同一场、色标放大到 ±{v2:.2f} cm：远场海面普遍下降'
                      f'（全场最低 {S.min():.4f} cm），载荷处已超出量程')
    axes[2].annotate(f'载荷处 {S.max():+.3f} cm\n（超出 ±{v2} 量程）',
                     xy=(lon_c.mean(), lat_c.mean()), xytext=(-95, -45),
                     fontsize=9, color='#7f0000', ha='left',
                     bbox=dict(boxstyle='round,pad=0.3', fc='white',
                               ec='#e0a0a0', alpha=0.92),
                     arrowprops=dict(arrowstyle='->', color='#7f0000', lw=1.2,
                                     connectionstyle='arc3,rad=-0.2'))
    axes[2].add_patch(Rectangle((box.get_x(), box.get_y()), box.get_width(),
                                box.get_height(), fill=False, ec='k', lw=0.9,
                                ls='--', alpha=0.65, zorder=5))
    fig.colorbar(im3, ax=axes[2], shrink=0.9, label='cm')

    for ax in axes:
        ax.set_xlabel('经度 (°E)')
        ax.set_ylabel('纬度 (°N)')
        ax.set_xlim(-180, 180)
        ax.set_xticks(np.arange(-180, 181, 60))
        ax.set_ylim(-90, 90)
        ax.grid(alpha=0.25, ls=':')
    fig.savefig(out_png)
    plt.close(fig)

    assert lat_min - 3.0 <= rlat[j_peak] <= lat_max + 3.0, '纬度方向错误（图上下颠倒）'
    assert rlat[j_peak] > 0, '指纹峰值不在北半球'
    print(f'  已写入 {os.path.relpath(out_png, ROOT)}'
          f'（载荷 {mass_Gt:.2f} Gt，峰值 {S.max():+.3f} cm @ {rlat[j_peak]:.1f}°N，'
          f'最低 {S.min():+.4f} cm）')
    return out_png


def main():
    ap = argparse.ArgumentParser(description='生成使用说明的科学配图')
    ap.add_argument('--figs', action='store_true',
                    help='同时刷新 figs/（总结报告用的同名图）')
    args = ap.parse_args()

    img = os.path.join(ROOT, 'docs', '使用说明_img')
    os.makedirs(img, exist_ok=True)
    print('=== 图 2：原理示意 ===')
    draw_principle(os.path.join(img, 'fig_principle.png'))

    print('=== 图 3：载荷与指纹 ===')
    S, rlon, rlat, load, mass = compute_field()
    draw_example(os.path.join(img, 'fig_example.png'), S, rlon, rlat, load, mass)

    if args.figs:
        figs = os.path.join(ROOT, 'figs')
        os.makedirs(figs, exist_ok=True)
        print('=== 同时刷新 figs/ ===')
        draw_principle(os.path.join(figs, 'fig1_principle.png'))
        draw_example(os.path.join(figs, 'fig2_load_slf.png'),
                     S, rlon, rlat, load, mass)

    print('\n完成。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
