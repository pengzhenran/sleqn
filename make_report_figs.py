#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_report_figs.py —— 为《海平面指纹总结报告》(HTML) 生成全部配图

流程：
  1) 用 gfortran 编译并运行三个 Fortran 版本（原文 / 仅修精度 / 修正版），
     输出高精度结果场，并与 sleqn.py 的 Python 版逐点比对；
  2) 从原文版与修正版分别 dump 全部 16381 个载荷球谐系数，量化"单精度常量"的影响；
  3) 用 sleqn.py 跑不同迭代次数，做收敛性与质量守恒验证；
  4) 用 matplotlib 出图，保存到 figs/。

依赖：gfortran（PATH 中可用）、numpy、matplotlib
运行：python make_report_figs.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile

import numpy as np

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, Rectangle, Arc

sys.path.insert(0, os.path.abspath('.'))
import sleqn
from make_demo_data import make_load, make_love, make_mask

plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei']
plt.rcParams['axes.unicode_minus'] = False
plt.rcParams['figure.dpi'] = 120
plt.rcParams['savefig.dpi'] = 120
plt.rcParams['savefig.bbox'] = 'tight'
plt.rcParams['axes.titlesize'] = 11
plt.rcParams['axes.labelsize'] = 10
plt.rcParams['xtick.labelsize'] = 9
plt.rcParams['ytick.labelsize'] = 9
plt.rcParams['legend.fontsize'] = 9

ROOT = os.path.abspath('.')
DEMO = os.path.join(ROOT, 'demo')
FIGS = os.path.join(ROOT, 'figs')
os.makedirs(FIGS, exist_ok=True)
TMP = tempfile.mkdtemp(prefix='sleqn_figs_')       # 必须 ASCII 路径（ld 打不开中文路径）

GF = shutil.which('gfortran') or (
    r"C:\Users\pengzhenran\AppData\Local\Microsoft\WinGet\Packages"
    r"\BrechtSanders.WinLibs.POSIX.UCRT_Microsoft.Winget.Source_8wekyb3d8bbwe"
    r"\mingw64\bin\gfortran.exe")
if not os.path.exists(GF):
    sys.exit('找不到 gfortran，请先安装或加入 PATH')
env = dict(os.environ)
env['PATH'] = os.path.dirname(GF) + os.pathsep + env['PATH']

FMT_OLD = ' 22   Format (F5.1, 1X, F5.1, 1X, E12.4)'
FMT_HP = ' 22   Format (F9.1, 1X, F9.1, 1X, ES24.16E3)'
DUMP_ANCHOR = """      Do l = 0, lsyn
        Do m = 0, l
          synthc(l, m) = synthc(l, m)*arad
          synths(l, m) = synths(l, m)*arad
        EndDo
      EndDo"""
DUMP_CODE = DUMP_ANCHOR + """
      Do l = 0, lsyn
        Do m = 0, l
          Write(77, '(2I5,2ES28.16E3)') l, m, synthc(l, m), synths(l, m)
        EndDo
      EndDo"""

ORIG = open('sleqn.f90', encoding='utf-8').read()
DP = open('sleqn_dp.f90', encoding='utf-8').read()
PREC_ONLY = DP.replace('float(2*2+1)', 'float(2*l+1)')     # 只修精度，pmh 仍为原文写法
assert PREC_ONLY != DP
VARIANTS = [('原文版', 'orig', ORIG), ('仅修精度', 'prec', PREC_ONLY), ('修正版', 'dp', DP)]


def make_rundir(name):
    """为每个变体建一个独立工作目录（ASCII 路径，避免同步盘锁文件）。"""
    d = os.path.join(TMP, name)
    os.makedirs(d, exist_ok=True)
    for f in ('land.fcn.1_deg', 'love_numbers', 'load_demo.txt', 'Filelist.txt'):
        shutil.copy(os.path.join(DEMO, f), os.path.join(d, f))
    return d


def build_run(src_text, tag, dump_coefs=False):
    """编译并运行一个变体，返回 (场网格 (nphi,nth), 系数 或 None)。"""
    src = src_text.replace(FMT_OLD, FMT_HP)
    if dump_coefs:
        assert src.count(DUMP_ANCHOR) == 1
        src = src.replace(DUMP_ANCHOR, DUMP_CODE)
    f90 = os.path.join(TMP, f'{tag}.f90')
    open(f90, 'w', encoding='utf-8').write(src)
    exe = os.path.join(TMP, f'{tag}.exe')
    r = subprocess.run([GF, '-O2', '-o', exe, f90], capture_output=True, text=True,
                       encoding='utf-8', errors='replace')
    assert r.returncode == 0, r.stderr[:500]
    rundir = make_rundir(tag)
    r = subprocess.run([exe], cwd=rundir, capture_output=True, text=True,
                       encoding='utf-8', errors='replace', env=env)
    assert r.returncode == 0, r.stderr[:500]
    d = np.loadtxt(os.path.join(rundir, 'slf_demo.txt'))
    field = d[:, 2].reshape(sleqn.NPHI, sleqn.NTH)
    coef = None
    if dump_coefs:
        c = np.zeros((181, 181))
        s = np.zeros((181, 181))
        for line in open(os.path.join(rundir, 'fort.77'), encoding='utf-8'):
            t = line.split()
            if len(t) == 4:
                c[int(t[0]), int(t[1])] = float(t[2])
                s[int(t[0]), int(t[1])] = float(t[3])
        coef = (c, s)
    print(f'  [{tag}] 编译+运行完成, max|S| = {np.abs(field).max():.6f} cm')
    return field, coef


print('=== 1) 三个 Fortran 变体 ===')
fields = {}
coefs = {}
for tag, ascii_tag, src in VARIANTS:
    f, c = build_run(src, ascii_tag, dump_coefs=tag in ('原文版', '修正版'))
    fields[tag] = f
    if c is not None:
        coefs[tag] = c

print('=== 2) Python 版参考 ===')
pydir = make_rundir('pyref')
subprocess.run([sys.executable, os.path.join(ROOT, 'sleqn.py'), '--mask',
                'land.fcn.1_deg', '--love', 'love_numbers', '--list', 'Filelist.txt',
                '--niter', '2', '--fmt', 'e24.16'],
               cwd=pydir, check=True, capture_output=True)
py_field = np.loadtxt(os.path.join(pydir, 'slf_demo.txt'))[:, 2].reshape(
    sleqn.NPHI, sleqn.NTH)
print(f'  [Python] max|S| = {np.abs(py_field).max():.6f} cm')

# 经纬度、载荷
ofcn, rlon, rlat = sleqn.load_mask(os.path.join(DEMO, 'land.fcn.1_deg'))
load = np.loadtxt(os.path.join(DEMO, 'load_demo.txt'))

# ============================================================ 图 1：原理示意
print('=== 图 1：原理示意 ===')


def fig_principle():
    """原理示意：改用 tools/make_guide_figs.py 的共享实现。

    共享版修了两处：方程文字移到左上角（旧版压在下坡曲线上被挡住），
    右上角加了远场放大窗（近场 1 cm 量级、远场 0.01 cm 量级，主图看不出来）。
    """
    sys.path.insert(0, os.path.join(ROOT, 'tools'))
    import make_guide_figs as mgf
    mgf.draw_principle(os.path.join(FIGS, 'fig1_principle.png'))


fig_principle()

# ============================================================ 图 2：载荷与指纹
print('=== 图 2：载荷与指纹场 ===')


# 经纬网格边界：数据为 1° 网格的中心点（经度 0.5…359.5，纬度 89.5…-89.5）
LON_E = np.arange(0, 361)              # 经度边界（升序）
LAT_E = np.arange(90, -91, -1)         # 纬度边界（必须降序！数据第 0 行 = 89.5°N）


def mesh(ax, C, **kw):
    """把 (nphi, nth) 的场画到等经纬网格上。

    注意：程序输出的数据第 0 行对应最北的纬度带（89.5°N），因此纬度边界必须
    降序传入；早期版本误用升序边界，导致图像上下颠倒（载荷被画到南极）。
    这里统一封装并做形状断言，防止再次写错。
    """
    assert C.shape == (sleqn.NPHI, sleqn.NTH), C.shape
    return ax.pcolormesh(LON_E, LAT_E, C.T, shading='auto', **kw)


def fig_load_slf():
    """载荷与指纹场：改用 tools/make_guide_figs.py 的共享实现。

    共享版修了两处：经度改为以 **0° 为中心**（异常落在图中央，不再挤在左上角）；
    载荷总质量按 Σ(h·A·ρ) 正确计算（旧版用 Σh×6.556，比真值大 10 倍）。
    """
    sys.path.insert(0, os.path.join(ROOT, 'tools'))
    import make_guide_figs as mgf
    S = fields['修正版']
    mass = mgf.load_mass_Gt(load)
    mgf.draw_example(os.path.join(FIGS, 'fig2_load_slf.png'),
                     S, rlon, rlat, load, mass)
    # 方向自检：指纹峰值必须落在载荷所在纬度区间附近（防止图上下颠倒）
    j_peak = int(np.argmax(np.abs(S).max(axis=0)))
    lat_min = load[:, 1].min() - 0.25
    lat_max = load[:, 1].max() + 0.25
    print(f'   方向自检: 载荷 {lat_min:.1f}~{lat_max:.1f}°N, '
          f'指纹峰值 {rlat[j_peak]:.1f}°N')
    assert lat_min - 3.0 <= rlat[j_peak] <= lat_max + 3.0, '纬度方向错误（图上下颠倒）'
    assert rlat[j_peak] > 0, '指纹峰值不在北半球'


fig_load_slf()

# ============================================================ 图 3：残差场
print('=== 图 3：残差场 ===')


def fig_residual_fields():
    res = {k: fields[k] - py_field for k in fields}
    fig, axes = plt.subplots(3, 1, figsize=(9.6, 8.0), constrained_layout=True)
    for ax, (tag, r) in zip(axes, res.items()):
        v = np.abs(r).max()
        im = mesh(ax, r, cmap='RdBu_r', vmin=-v, vmax=v)
        ax.set_title(f'{tag} − Python：max|Δ| = {v:.3e} cm'
                     f'（占场最大值 {v / np.abs(py_field).max() * 100:.4g}%）')
        fig.colorbar(im, ax=ax, shrink=0.9, label='cm')
        ax.set_ylabel('纬度 (°N)')
        ax.grid(alpha=0.2, ls=':')
    axes[-1].set_xlabel('经度 (°E)')
    fig.savefig(os.path.join(FIGS, 'fig3_residual_fields.png'))
    plt.close(fig)


fig_residual_fields()

# ============================================================ 图 4：残差谱
print('=== 图 4：残差球谐谱 ===')


def fig_residual_spectrum():
    L = sleqn.LMOST + 1
    fac = np.full(L, 2.0)
    fac[0] = np.sqrt(2.0)
    plm = np.zeros((L, L, sleqn.NTH))
    for j in range(sleqn.NTH):
        plm[:, :, j] = sleqn.martin(sleqn.LMOST, np.cos((90.0 - rlat[j]) * sleqn.DTR)) * fac[None, :]
    ms = np.arange(L)[:, None]
    ccos = np.cos(ms * (rlon[None, :] * sleqn.DTR))
    ssin = np.sin(ms * (rlon[None, :] * sleqn.DTR))

    fig, ax = plt.subplots(figsize=(8.4, 4.4))
    colors = {'原文版': '#c62828', '仅修精度': '#ef6c00', '修正版': '#2e7d32'}
    for tag in fields:
        r = fields[tag] - py_field
        clm, slm = sleqn.geoid(r, rlon, rlat, plm, ccos, ssin,
                               sleqn.NTH, sleqn.NPHI, sleqn.LMOST, sleqn.LMOST)
        amp = np.zeros(L)
        for l in range(L):
            a = np.hypot(clm[l, 0:l + 1], slm[l, 0:l + 1])
            amp[l] = np.sqrt((a ** 2).sum() / (l + 1))
        ax.semilogy(np.arange(L), np.maximum(amp, 1e-20), '-', lw=1.6,
                    color=colors[tag], label=tag)
    ax.set_xlabel('球谐阶 $l$')
    ax.set_ylabel('残差各阶振幅 (cm)')
    ax.set_title('三个 Fortran 版本与 Python 版的残差球谐谱（相对"真解"的偏差分布）')
    ax.annotate('原文版残差 97.7% 集中在 (2,1)，\n即极移项 $pmh$ 分母取错所致',
                xy=(2, 4e-4), xytext=(28, 3e-3), fontsize=9, color='#c62828',
                arrowprops=dict(arrowstyle='->', color='#c62828', lw=1.2))
    ax.grid(alpha=0.3, ls=':', which='both')
    ax.legend(loc='upper right')
    fig.savefig(os.path.join(FIGS, 'fig4_residual_spectrum.png'))
    plt.close(fig)


fig_residual_spectrum()

# ============================================================ 图 5：系数相对误差
print('=== 图 5：载荷球谐系数的相对误差 ===')


def fig_coef_error():
    c_o, s_o = coefs['原文版']
    c_d, s_d = coefs['修正版']
    L = sleqn.LMOST + 1
    rel = np.full(L, np.nan)
    for l in range(L):
        num = np.hypot(c_o[l, 0:l + 1] - c_d[l, 0:l + 1],
                       s_o[l, 0:l + 1] - s_d[l, 0:l + 1])
        den = np.hypot(c_d[l, 0:l + 1], s_d[l, 0:l + 1])
        m = den > 1e-300
        if m.any():
            rel[l] = np.max(num[m] / den[m])

    fig, axes = plt.subplots(1, 2, figsize=(10.4, 4.2))
    ax = axes[0]
    ax.semilogy(np.arange(L), rel, '-', color='#c62828', lw=1.6)
    ax.axhline(1e-8, ls='--', color='#616161', lw=1.2)
    ax.text(95, 1.6e-8, '单精度常量本身带来的 ~1e-8 相对误差',
            fontsize=9, color='#616161', ha='center')
    ax.set_xlabel('阶 $l$')
    ax.set_ylabel('载荷球谐系数最大相对误差')
    ax.set_title('(a) 载荷系数相对误差（原文版 vs 修正版）')
    ax.grid(alpha=0.3, ls=':', which='both')
    ax.annotate('$temp(l)=\\frac{P_{l-1}(\\cos\\alpha)-P_{l+1}(\\cos\\alpha)}{2}$\n'
                '两个 ≈1 的数相减\n→ 误差被放大到 1e-3 量级',
                xy=(60, 3e-3), xytext=(20, 3e-2), fontsize=9, color='#c62828',
                arrowprops=dict(arrowstyle='->', color='#c62828', lw=1.2))

    # (b) 角半径越小 -> temp(l) 越"小" -> 抵消越严重
    ax = axes[1]
    area = 536.758                                  # demo 单元面积 km^2
    a_rad = np.sqrt(area / np.pi) / 6.371e3         # 角半径（弧度）
    for dgrid, col in ((0.5, '#1565c0'), (1.0, '#2e7d32'), (2.0, '#ef6c00')):
        al = np.sqrt(dgrid ** 2 / np.pi) / 6.371e3
        t = (2 * np.arange(L) + 1) * al ** 2 / 4
        ax.semilogy(np.arange(L), np.maximum(t, 1e-30), lw=1.6, color=col,
                    label=f'{dgrid}° 网格（$\\alpha$={np.degrees(al):.2f}°）')
    ax.axhline(1e-16, ls='--', color='#616161', lw=1.2)
    ax.text(50, 1.3e-16, '双精度机器精度（≈1e-16）', fontsize=9, color='#616161')
    ax.set_xlabel('阶 $l$')
    ax.set_ylabel('$temp(l)$ 的量级')
    ax.set_title('(b) 抵消程度：$temp(l)$ 随阶数变小 → 有效数字流失')
    ax.grid(alpha=0.3, ls=':', which='both')
    ax.legend()
    fig.savefig(os.path.join(FIGS, 'fig5_coef_error.png'))
    plt.close(fig)


fig_coef_error()

# ============================================================ 图 6：指纹剖面
print('=== 图 6：经向剖面 ===')


def fig_profile():
    i0 = int(np.argmin(np.abs(rlon - 2.5)))
    S = fields['修正版'][i0, :]                       # 沿 2.5°E 的剖面
    S_o = fields['原文版'][i0, :]
    tm = np.loadtxt(os.path.join(DEMO, 'load_demo.txt'))[:, 2].sum()
    # 均匀海面（eustatic）参考：-tmass/(rho*a^2*4pi)
    m = 6.549855839263e16
    eust = -m / (1.0 * (6.371e8) ** 2 * 4 * np.pi)

    fig, axes = plt.subplots(1, 2, figsize=(10.6, 4.2))
    ax = axes[0]
    ax.plot(rlat, S, '-', color='#2e7d32', lw=2.0, label='修正版（=Python 版）')
    ax.plot(rlat, S_o, '--', color='#c62828', lw=1.6, label='原文版')
    ax.axhline(eust, ls=':', color='#1565c0', lw=1.6,
               label=f'均匀海面（eustatic）={eust:.4f} cm')
    ax.axhline(0, color='#9e9e9e', lw=0.8)
    ax.axvspan(75.5, 80.0, color='#bbdefb', alpha=0.5)
    ax.text(77.7, ax.get_ylim()[1] * 0.75, '载荷位置', ha='center', fontsize=9,
            color='#0d47a1')
    ax.set_xlabel('纬度 (°N)')
    ax.set_ylabel('海平面变化 $S$ (cm)')
    ax.set_title('(a) 沿 2.5°E 的经向剖面')
    ax.grid(alpha=0.3, ls=':')
    ax.legend(loc='lower right')

    ax = axes[1]
    ax.hist(S, bins=80, color='#90caf9', edgecolor='#1565c0', lw=0.6)
    ax.axvline(eust, color='#1565c0', ls=':', lw=1.8, label='均匀海面')
    ax.axvline(0, color='#9e9e9e', lw=0.8)
    ax.set_yscale('log')
    ax.set_xlabel('海平面变化 $S$ (cm)')
    ax.set_ylabel('网格点数')
    ax.set_title('(b) $S$ 的分布：绝大多数点接近 0，载荷处出现正异常')
    ax.grid(alpha=0.3, ls=':', which='both')
    ax.legend()
    fig.savefig(os.path.join(FIGS, 'fig6_profile.png'))
    plt.close(fig)


fig_profile()

# ============================================================ 图 7：收敛性
print('=== 图 7：迭代收敛性 ===')


def fig_convergence():
    ofcn2, rlon2, rlat2 = sleqn.load_mask(os.path.join(DEMO, 'land.fcn.1_deg'))
    h, rk = sleqn.load_love(os.path.join(DEMO, 'love_numbers'))
    ls = np.arange(sleqn.LLOVE + 1)
    coefh = (1.0 + rk - h) * 3.0 * sleqn.RHO0 / sleqn.RHOAVE / (2.0 * ls + 1.0)
    coefp = (1.0 + rk - h) / (rk + 1.0)
    plm = np.zeros((sleqn.LMOST + 1, sleqn.LMOST + 1, sleqn.NTH))
    fac = np.full(sleqn.LMOST + 1, 2.0)
    fac[0] = np.sqrt(2.0)
    for j in range(sleqn.NTH):
        plm[:, :, j] = sleqn.martin(sleqn.LMOST, np.cos((90.0 - rlat2[j]) * sleqn.DTR)) * fac[None, :]
    ms = np.arange(sleqn.LMOST + 1)[:, None]
    ccos = np.cos(ms * (rlon2[None, :] * sleqn.DTR))
    ssin = np.sin(ms * (rlon2[None, :] * sleqn.DTR))

    iters = [0, 1, 2, 3, 4]
    diff = []
    cons = []
    base = None
    sleqn.OUT_FMT = (20, 12)          # 高精度输出，避免 E12.4 的 1e-3 量化掩盖收敛过程
    for n in iters:
        out = os.path.join(TMP, f'conv{n}.txt')
        z, tm, _, _ = sleqn.solve_one(os.path.join(DEMO, 'load_demo.txt'), out,
                                      ofcn2, rlon2, rlat2, plm, ccos, ssin,
                                      coefh, coefp, h, rk, n)
        f = np.loadtxt(out)[:, 2].reshape(sleqn.NPHI, sleqn.NTH)
        if base is None:
            base = f
        diff.append(f - base)
        cons.append(abs(z + tm / 1.0e15) / abs(tm / 1.0e15))
    # 以 niter=4 为参考
    ref = diff[-1]
    dev = [np.abs(d - ref).max() for d in diff]

    fig, axes = plt.subplots(1, 2, figsize=(10.4, 4.0))
    ax = axes[0]
    ax.semilogy(iters, np.maximum(dev, 1e-18), 'o-', color='#1565c0', lw=1.8)
    ax.set_xlabel('迭代次数 niter')
    ax.set_ylabel('与 niter=4 的最大差异 (cm)')
    ax.set_title('(a) 自吸引/负荷迭代的收敛性')
    ax.grid(alpha=0.3, ls=':', which='both')
    for n, v in zip(iters, dev):
        ax.annotate(f'{v:.2e}', (n, max(v, 1e-18)), textcoords='offset points',
                    xytext=(4, 6), fontsize=8)
    ax = axes[1]
    ax.semilogy(iters, np.maximum(cons, 1e-18), 's-', color='#2e7d32', lw=1.8,
                label='|zmass + tmass| / |tmass|')
    ax.set_xlabel('迭代次数 niter')
    ax.set_ylabel('质量守恒相对误差')
    ax.set_title('(b) 质量守恒（解算海水质量 = −载荷质量）')
    ax.grid(alpha=0.3, ls=':', which='both')
    ax.legend()
    fig.savefig(os.path.join(FIGS, 'fig7_convergence.png'))
    plt.close(fig)
    print('   收敛/守恒数据:', [f'{v:.2e}' for v in dev], [f'{v:.2e}' for v in cons])


fig_convergence()

# ============================================================ 图 8：原文结果图
print('=== 图 8：原文结果图（压缩）===')
from PIL import Image
src_img = None
for f in os.listdir(ROOT):
    if f.endswith('.png') and '190430' in f:
        src_img = os.path.join(ROOT, f)
if src_img:
    im = Image.open(src_img).convert('RGB')
    im.thumbnail((950, 1700), Image.LANCZOS)
    im.save(os.path.join(FIGS, 'fig8_paper.jpg'), quality=92, optimize=True,
            progressive=True)
    print('   已压缩:', im.size)

print('\n全部配图已保存到', FIGS)
for f in sorted(os.listdir(FIGS)):
    print('  ', f, os.path.getsize(os.path.join(FIGS, f)), 'B')
