#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""画「掩膜修复前 / 修复后」的海平面指纹对比图。

用法:
    python plot_slf_compare.py [修复前文件] [修复后文件] [输出png]

默认:
    grace_example/slf_gui.txt                （修复前，西半球被判为海）
    grace_example/slf_grace_t0001_1deg.txt   （修复后）
    slf_图_掩膜修复对比.png
"""

from __future__ import annotations

import os
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

matplotlib.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']
matplotlib.rcParams['axes.unicode_minus'] = False

HERE = os.path.dirname(os.path.abspath(__file__))


def read_result(path):
    """读三列结果文件（经度外层、纬度内层），返回 (S[nphi,nth], rlon, rlat)。"""
    d = np.loadtxt(path)
    lat0 = d[0, 1]
    same = np.where(np.abs(d[:, 1] - lat0) < 1e-9)[0]
    nth = int(same[1]) if len(same) > 1 else len(d)
    nphi = len(d) // nth
    return d[:, 2].reshape(nphi, nth), d[::nth, 0].copy(), d[:nth, 1].copy()


def edges(c):
    c = np.asarray(c, dtype=float)
    d = c[1] - c[0] if len(c) > 1 else 1.0
    return np.concatenate([[c[0] - d / 2.0], c + d / 2.0])


def main():
    before = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, 'grace_example', 'slf_gui.txt')
    after = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, 'grace_example', 'slf_grace_t0001_1deg.txt')
    out = sys.argv[3] if len(sys.argv) > 3 else os.path.join(HERE, 'slf_图_掩膜修复对比.png')

    S1, rlon, rlat = read_result(before)
    S2, _, _ = read_result(after)
    vabs = float(max(np.abs(S1).max(), np.abs(S2).max()))

    try:
        import cartopy.crs as ccrs
        proj = ccrs.Robinson(central_longitude=0)
        tr = ccrs.PlateCarree()
        use_cc = True
    except Exception:
        proj, tr, use_cc = None, None, False

    fig = plt.figure(figsize=(15, 4.6))
    for k, (S, tag) in enumerate([
            (S1, f'(a) 修复前  峰值 {np.abs(S1).max():.2f} cm  ← 西半球被误判为海'),
            (S2, f'(b) 修复后  峰值 {np.abs(S2).max():.2f} cm  ← 陆地严格为 0')]):
        ax = fig.add_subplot(1, 2, k + 1, projection=proj) if use_cc else fig.add_subplot(1, 2, k + 1)
        kw = dict(transform=tr) if use_cc else {}
        m = ax.pcolormesh(edges(rlon), edges(rlat), S.T, vmin=-vabs, vmax=vabs,
                          shading='auto', cmap='RdBu_r', **kw)
        if use_cc:
            ax.coastlines(resolution='110m', linewidth=0.6, color='0.25')
        ax.set_title(tag, fontsize=12, pad=10)

    cb = fig.colorbar(m, ax=fig.axes, shrink=0.8, pad=0.015)
    cb.set_label('海平面变化 (cm)')
    fig.savefig(out, dpi=200, bbox_inches='tight')
    print(f'已写出 {out}')
    print(f'  共享色标 ±{vabs:.3f} cm')


if __name__ == '__main__':
    main()
