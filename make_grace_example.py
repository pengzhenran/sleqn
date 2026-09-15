#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_grace_example.py —— 用真实 GRACE mascon 数据生成海平面指纹计算示例数据
============================================================================

生成 ``grace_example/`` 目录，可直接被 ``sleqn.py`` / ``sleqn_gui.py`` 使用：

    land.fcn.1_deg        1° 海陆掩膜（value=1 陆地 / 0 海洋）
    love_numbers          负荷勒夫数 l=0..180 的 (l, h_l, k_l, 保留列)
    load_grace_*.txt      质量变化网格（经度 纬度 水当量高度 m）
    Filelist.txt          控制文件
    README.txt            数据来源与单位说明

数据来源
--------
* GRACE：CSR GRACE/GRACE-FO RL06.3 mascon（all-corrections），
  ``lwe_thickness``（cm 当量水高），0.25° 全球网格，行序自南向北。
* 负荷勒夫数：Wang et al. (2012) PREM-LLNs-complete.dat 的 h、k 列（PREM 弹性地球）。

用法
----
    python make_grace_example.py --grace-dir "<mascon .grd 所在目录>" \
                                 --prem "<PREM-LLNs-complete.dat>" \
                                 --out grace_example [--grid 1.0]
"""

from __future__ import annotations

import argparse
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sleqn  # noqa: E402

DEF_GRACE = (r'D:\华为家庭存储\mywork\1_GlobalSpatiotemporal\codes\m2py\data')
DEF_PREM = (r'D:\华为家庭存储\3_research\10_GNSS_3d\code for GNSS inversion test'
            r'\PREM-LLNs-complete.dat')
EPOCHS = ['CSR_GRACE_GRACE-FO_RL0603_Mascons_all-corrections_t0001.grd',
          'CSR_GRACE_GRACE-FO_RL0603_Mascons_all-corrections_t0002.grd',
          'CSR_GRACE_GRACE-FO_RL0603_Mascons_all-corrections_t0003.grd',
          'CSR_GRACE_GRACE-FO_RL0603_Mascons_all-corrections_t0004.grd',
          'CSR_GRACE_GRACE-FO_RL0603_Mascons_all-corrections_t0005.grd']


# ---------------------------------------------------------------- 读 Surfer ASCII 网格
def read_dsaa(path):
    """读 Golden Software ASCII 网格（DSAA）。

    CSR mascon 网格：nx=1440（经度 0.125~359.875，0.25°）、
    ny=720（纬度 -89.875~89.875，0.25°），**第 0 行是最南端**。
    数值单位：cm 当量水高（lwe_thickness）。
    """
    with open(path, 'r', encoding='ascii', errors='replace') as f:
        if f.readline().strip() != 'DSAA':
            raise ValueError(f'{path}: 不是 DSAA 格式')
        nx, ny = (int(v) for v in f.readline().split())
        xlo, xhi = (float(v) for v in f.readline().split())
        ylo, yhi = (float(v) for v in f.readline().split())
        _zlo, _zhi = (float(v) for v in f.readline().split())
        vals = np.fromstring(f.read(), sep=' ')
    if vals.size != nx * ny:
        raise ValueError(f'{path}: 期望 {nx * ny} 个值，实际 {vals.size}')
    lon = np.linspace(xlo, xhi, nx)
    lat = np.linspace(ylo, yhi, ny)          # 自南向北
    return lon, lat, vals.reshape(ny, nx)


def block_mean(Z, f, lat_asc=True):
    """把 (ny, nx) 的网格按 f×f 块平均到 1/f 分辨率（要求能整除）。

    返回 (lat_c, lon_c, Zb)，lat_c 自北向南（与程序输出/掩膜的纬度方向一致）。
    """
    ny, nx = Z.shape
    assert ny % f == 0 and nx % f == 0, f'网格 {ny}x{nx} 不能被 {f} 整除'
    Zb = Z.reshape(ny // f, f, nx // f, f).mean(axis=(1, 3))
    return Zb


# ---------------------------------------------------------------- 海陆掩膜
def make_land_mask(lon_c, lat_c, out_path, nth=180, nphi=360):
    """用 Natural Earth 110m 陆地多边形栅格化 1° 海陆掩膜（1 陆地 / 0 海洋）。"""
    try:
        import cartopy.io.shapereader as shpreader
        import shapely.geometry as sgeom
        from shapely.ops import unary_union
        try:                       # shapely >= 2.0
            from shapely import contains_xy
        except ImportError:        # 旧版 shapely
            from shapely.vectorized import contains as contains_xy
    except Exception as e:                                  # pragma: no cover
        print(f'[警告] 无法使用 shapely/cartopy 生成掩膜（{e}），改用全海洋掩膜')
        return None
    try:
        shp = shpreader.natural_earth(resolution='110m', category='physical',
                                      name='land')
        polys = [r.geometry for r in shpreader.Reader(shp).records()]
        land = unary_union(polys)
        lon2, lat2 = np.meshgrid(lon_c, lat_c)
        # ★ 多边形是 -180~180 约定，而 lon_c 是 0~360：必须先绕回，
        #   否则 x>180 的点全落在多边形包围盒之外，会被误判成海洋。
        #   2026-09-12 修：此前整个西半球（含美洲、格陵兰）被判成海，
        #   导致海平面指纹在陆地上出现信号、且海洋面积虚增 12%。
        lon_w = (lon2 - 180.0) % 360.0 - 180.0
        inside = contains_xy(land, lon_w.ravel(), lat2.ravel()).reshape(lon2.shape)
        print(f'    陆地格点占比 {inside.mean() * 100:.1f}%')
        with open(out_path, 'w', encoding='utf-8') as f:
            for j in range(len(lat_c)):
                for i in range(len(lon_c)):
                    f.write(f'{lon_c[i]:7.1f} {lat_c[j]:7.1f} {1 if inside[j, i] else 0:4d}\n')
        return inside
    except Exception as e:                                  # pragma: no cover
        print(f'[警告] 生成掩膜失败（{e}）')
        return None


# ---------------------------------------------------------------- 主流程
def main():
    ap = argparse.ArgumentParser(description='用 GRACE mascon 生成 SLF 示例数据')
    ap.add_argument('--grace-dir', default=DEF_GRACE, help='mascon .grd 所在目录')
    ap.add_argument('--prem', default=DEF_PREM, help='PREM-LLNs-complete.dat 路径')
    ap.add_argument('--out', default=os.path.join(HERE, 'grace_example'))
    ap.add_argument('--grid', type=float, default=1.0, help='载荷网格分辨率（度，默认 1）')
    ap.add_argument('--no-demean', action='store_true',
                    help='不去全球面积加权均值（默认会去掉，避免均匀分量盖过指纹信号）')
    ap.add_argument('--block', type=int, default=0,
                    help='块平均因子（0=按 --grid 自动推算，1° 时 = 4）')
    a = ap.parse_args()

    os.makedirs(a.out, exist_ok=True)
    t0 = time.time()
    land_mask, lon_c, lat_c = None, None, None

    # ---------------- 1) 负荷勒夫数 ----------------
    print('=== 1) 负荷勒夫数（PREM-LLNs-complete.dat）===')
    h = np.zeros(181)
    k = np.zeros(181)
    n_read = 0
    with open(a.prem, 'r', encoding='utf-8', errors='ignore') as f:
        f.readline()                                     # 表头
        for line in f:
            tok = line.split()
            if len(tok) < 4:
                continue
            try:
                nf = float(tok[0].replace('D', 'E').replace('d', 'e'))
                if not np.isfinite(nf):        # 文件末行是 inf，跳过
                    continue
                n = int(nf)
                hh = float(tok[1].replace('D', 'E').replace('d', 'e'))
                kk = float(tok[3].replace('D', 'E').replace('d', 'e'))
            except ValueError:
                continue
            if 0 <= n <= 180:
                h[n], k[n] = hh, kk
                n_read += 1
    print(f'  读入 {n_read} 阶（文件从 l=1 起，l=0 按惯例取 0）；'
          f'h_2={h[2]:.5f}, k_2={k[2]:.5f}, h_180={h[180]:.4f}, k_180={k[180]:.5f}')
    assert n_read >= 180, f'只读到 {n_read} 阶'
    # 交叉核对：与项目里 love_numbers.npy 的 k 表比较（l≥2；l=1 两者坐标系不同）
    try:
        npy = (r'D:\华为家庭存储\mywork\1_GlobalSpatiotemporal\codes\m2py'
               r'\data\love_numbers.npy')
        k_ref = np.load(npy)
        dd = np.abs(k_ref[2:181] - k[2:181])
        print(f'  与项目 love_numbers.npy 的 k 表核对（l=2..180）：max|Δ| = {dd.max():.3e}')
    except Exception as e:
        print(f'  （跳过 k 表核对：{e}）')
    lv = os.path.join(a.out, 'love_numbers')
    with open(lv, 'w', encoding='utf-8') as f:
        f.write('# 负荷勒夫数：Wang et al. (2012) PREM-LLNs-complete.dat 的 h、k 列\n')
        f.write('# 列：l  h_l  k_l  (保留列)\n')
        for l in range(181):
            f.write(f'{l:5d} {h[l]: .8e} {k[l]: .8e} {0.0: .8e}\n')
    print(f'  已写入 {lv}')

    # ---------------- 2) GRACE 历元 ----------------
    print('=== 2) GRACE mascon ===')
    Zs, tagnames = [], []
    for name in EPOCHS:
        p = os.path.join(a.grace_dir, name)
        if os.path.exists(p):
            lon, lat, Z = read_dsaa(p)
            Zs.append(Z)
            tagnames.append(name.split('_')[-1].replace('.grd', ''))
            print(f'  {name}: {Z.shape}, {Z.min():.1f}~{Z.max():.1f} cm, 均值 {Z.mean():+.3f}')
    if not Zs:
        sys.exit(f'在 {a.grace_dir} 里找不到 mascon .grd 文件')

    f = a.block or int(round(1.0 / a.grid / 0.25))
    print(f'  块平均因子 f={f}（0.25° → {0.25 * f:g}°）')
    Zb = [block_mean(Z, f) for Z in Zs]                  # (nlat, nlon)，纬度仍自南向北
    nlat, nlon = Zb[0].shape
    # 块中心：取块内首末格点中心的平均（0.25° 的 4 格块中心正好落在 X.5，
    # 与 1° 掩膜网格一致），并改为自北向南，与掩膜/输出一致
    step = 0.25 * f
    lon_c = (lon[0] + lon[f - 1]) / 2.0 + np.arange(nlon) * step
    lat_s2n = (lat[0] + lat[f - 1]) / 2.0 + np.arange(nlat) * step   # 自南向北
    lat_n2s = lat_s2n[::-1]
    w_area = np.cos(np.radians(lat_s2n))
    w_area = w_area / w_area.sum()
    for idx, B in enumerate(Zb):
        # 面积加权均值 = Σ(B·w) / (格点数)，其中 Σw = 1
        m0 = float((B * w_area[:, None]).sum()) / nlon
        print(f'  {tagnames[idx]}: 全球面积加权均值 {m0:+.4f} cm'
              + ('（已扣除）' if not a.no_demean else '（保留）'))
        if not a.no_demean:
            Zb[idx] = B - m0
    print(f'  目标网格 {nlon}×{nlat}，经度 {lon_c[0]:.3f}~{lon_c[-1]:.3f}，'
          f'纬度 {lat_n2s[0]:.3f}~{lat_n2s[-1]:.3f}')

    def write_load(path, B_cm, label, unit):
        """B_cm: (nlat, nlon) 自南向北；写出的 (经度, 纬度, m) 顺序不限。"""
        n = 0
        with open(path, 'w', encoding='utf-8') as fh:
            for j in range(nlat):
                latv = lat_n2s[j]
                row = B_cm[nlat - 1 - j]                 # 换成同一纬度
                for i in range(nlon):
                    fh.write(f'{lon_c[i]:7.1f} {latv:7.1f} {row[i] / 100.0:12.6e}\n')
                    n += 1
        print(f'  写入 {path}：{n} 个单元，{label}（{unit}），'
              f'值域 {np.nanmin(B_cm) / 100:.4g} ~ {np.nanmax(B_cm) / 100:.4g} {unit}')
        return n

    load_files = []
    # (a) 单历元异常
    p1 = os.path.join(a.out, f'load_grace_{tagnames[0]}_{0.25 * f:g}deg.txt')
    write_load(p1, Zb[0], f'GRACE {tagnames[0]} 单历元当量水高异常', 'm')
    load_files.append((p1, f'GRACE {tagnames[0]} 单历元'))

    # (b) 线性趋势（≥2 个历元）
    if len(Zb) >= 2:
        t = np.arange(len(Zb), dtype=float)
        stack = np.stack(Zb)                             # (nt, nlat, nlon)
        tt = t - t.mean()
        slope = (stack * tt[:, None, None]).sum(axis=0) / (tt ** 2).sum()   # cm/epoch
        p2 = os.path.join(a.out, f'load_grace_trend_{0.25 * f:g}deg.txt')
        write_load(p2, slope, f'GRACE {tagnames[0]}~{tagnames[-1]} 线性趋势', 'm/历元')
        load_files.append((p2, f'趋势 {tagnames[0]}~{tagnames[-1]}'))
        d = np.abs(stack[1:] - stack[:-1])
        print(f'  相邻历元差异: 均值 {d.mean():.4f} cm，说明各历元确实不同')

    # ---------------- 3) 海陆掩膜 ----------------
    print('=== 3) 海陆掩膜 ===')
    mk = os.path.join(a.out, 'land.fcn.1_deg')
    if nlat == 180 and nlon == 360:
        land_mask = make_land_mask(lon_c, lat_n2s, mk)
    if land_mask is None:
        with open(mk, 'w', encoding='utf-8') as fh:
            for j in range(nlat):
                for i in range(nlon):
                    fh.write(f'{lon_c[i]:7.1f} {lat_n2s[j]:7.1f} {0:4d}\n')
        print('  已写入全海洋掩膜')
    print(f'  掩膜: {mk}')

    # ---------------- 4) Filelist 与说明 ----------------
    with open(os.path.join(a.out, 'Filelist.txt'), 'w', encoding='utf-8') as fh:
        for p, _ in load_files:
            fh.write(f'{os.path.basename(p)} slf_{os.path.basename(p)[5:]}\n')
    with open(os.path.join(a.out, 'README.txt'), 'w', encoding='utf-8') as fh:
        fh.write('GRACE mascon 海平面指纹示例数据\n')
        fh.write('=' * 60 + '\n\n')
        fh.write(f'网格分辨率: {0.25 * f:g}°（经度 {nlon} × 纬度 {nlat}）\n')
        fh.write('质量变化单位: **米**当量水高（原 mascon 为 cm，已除以 100）\n')
        fh.write('run 时载荷网格间隔参数 dlon/dlat 应填 ' f'{0.25 * f:g}\n\n')
        fh.write('载荷文件（每行：经度 纬度 水当量高度(m)）:\n')
        for p, tag in load_files:
            fh.write(f'  {os.path.basename(p):40s} {tag}\n')
        fh.write('\nlove_numbers: Wang et al. (2012) PREM-LLNs-complete.dat 的 h、k 列\n')
        fh.write('land.fcn.1_deg: Natural Earth 110m 陆地多边形栅格化（1=陆地，0=海洋）\n')
        fh.write('\nGRACE 来源: CSR GRACE/GRACE-FO RL06.3 mascon (all-corrections),\n')
        fh.write('           lwe_thickness, 0.25°, 行序自南向北\n')

    # ---------------- 5) 单胞耗时探针 ----------------
    print('=== 5) 单胞耗时探针 ===')
    ofcn, rlon, rlat = sleqn.load_mask(mk)
    hh, rk = sleqn.load_love(lv)
    syn_c = np.zeros((181, 181))
    syn_s = np.zeros((181, 181))
    n_probe = 200
    t1 = time.time()
    for _ in range(n_probe):
        sleqn.gdisc(0.1, 1.0, 536.0, 5.0e14, syn_c, syn_s, 180, rk)
    dt = (time.time() - t1) / n_probe
    ncell = nlon * nlat
    print(f'  gdisc 单胞 {dt * 1000:.3f} ms → {ncell} 个单元约需 '
          f'{dt * ncell:.1f} s（不含迭代与出图）')

    print(f'\n全部完成，用时 {time.time() - t0:.1f} s，输出目录：{a.out}')


if __name__ == '__main__':
    main()
