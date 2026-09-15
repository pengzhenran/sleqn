# -*- coding: utf-8 -*-
"""Build the comparison figures for the sleqn verification report.

Run with the pzr conda env (matplotlib + cartopy available).
"""
import os
import sys

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import TwoSlopeNorm, LogNorm
from matplotlib.gridspec import GridSpec

try:
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature
    HAVE_CARTOPY = True
except Exception:
    HAVE_CARTOPY = False

WS = r'D:\华为家庭存储\mywork\sealevel'
TMP = r'C:\Users\pengzhenran\AppData\Local\Temp\slverify'
OUT = os.path.join(WS, '_verify', 'figs')
os.makedirs(OUT, exist_ok=True)
plt.rcParams.update({'font.size': 9, 'axes.titlesize': 10,
                     'figure.dpi': 130, 'savefig.dpi': 130,
                     'axes.unicode_minus': False})
try:
    plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']
except Exception:
    pass


def mesh(lon, lat):
    return np.meshgrid(lon, lat, indexing='ij')


def gmap(ax, lon, lat, data, title, cmap='RdBu_r', vmin=None, vmax=None,
         norm=None, cbar_label='cm', levels=None):
    if HAVE_CARTOPY:
        ax.set_global()
        try:
            ax.coastlines(resolution='110m', linewidth=0.4, color='0.35')
        except Exception:
            pass
        try:
            ax.add_feature(cfeature.LAND, facecolor='0.92', zorder=0)
        except Exception:
            pass
        tr = ccrs.PlateCarree()
    else:
        tr = None
    LON, LAT = mesh(lon, lat)
    if norm is not None:
        im = ax.pcolormesh(LON, LAT, data, transform=tr, cmap=cmap, norm=norm,
                           shading='auto', rasterized=True)
    else:
        im = ax.pcolormesh(LON, LAT, data, transform=tr, cmap=cmap,
                           vmin=vmin, vmax=vmax, shading='auto', rasterized=True)
    ax.set_title(title)
    return im


def add_cbar(fig, im, ax, label):
    cb = fig.colorbar(im, ax=ax, orientation='horizontal', pad=0.06,
                      fraction=0.05, shrink=0.92)
    cb.set_label(label, fontsize=8)
    cb.ax.tick_params(labelsize=7)


def stats(a, b, mask=None):
    if mask is None:
        mask = np.ones(a.shape, bool)
    d = (a - b)[mask]
    ra, rb = a[mask], b[mask]
    return (np.abs(d).max(), np.abs(d).mean(),
            np.corrcoef(ra, rb)[0, 1], np.abs(rb).max())


# ======================================================================
# Fig 1 -- demo: sleqn vs gravity-toolkit vs closed form
# ======================================================================
d = np.load(os.path.join(TMP, 'fields_demo.npz'))
lon, lat = d['lon'], d['lat']
s50, s2, gt, ana = d['sleqn_n50'], d['sleqn_n2'], d['gravtk'], d['analytic']

fig = plt.figure(figsize=(15, 8.4))
gs = GridSpec(2, 3, figure=fig, hspace=0.32, wspace=0.18)
proj = ccrs.Robinson() if HAVE_CARTOPY else None

ax = fig.add_subplot(gs[0, 0], projection=proj)
v = np.abs(s50).max()
im = gmap(ax, lon, lat, s50, '(a) sleqn  niter=50', vmin=-v, vmax=v)
add_cbar(fig, im, ax, 'cm')

ax = fig.add_subplot(gs[0, 1], projection=proj)
im = gmap(ax, lon, lat, gt, '(b) gravity-toolkit（独立实现，收敛）',
          vmin=-v, vmax=v)
add_cbar(fig, im, ax, 'cm')

mxa, mna, cor, ref = stats(gt, s50)
ax = fig.add_subplot(gs[0, 2], projection=proj)
lim = np.abs(gt - s50).max()
im = gmap(ax, lon, lat, gt - s50,
          f'(c) 差值 (b)-(a)\nmax|Δ|={mxa:.2e} cm = {mxa/ref:.3%}×峰值, r={cor:.8f}',
          cmap='RdBu_r', vmin=-lim, vmax=lim)
add_cbar(fig, im, ax, 'cm')

ax = fig.add_subplot(gs[1, 0], projection=proj)
lim = np.abs(ana - s50).max()
im = gmap(ax, lon, lat, ana - s50, '(d) 解析闭式解 - sleqn(niter=50)',
          cmap='RdBu_r', vmin=-lim, vmax=lim)
add_cbar(fig, im, ax, 'cm')

# profile
ax = fig.add_subplot(gs[1, 1])
i = np.argmin(np.abs(lon - 2.5))
ax.plot(lat, s50[i], 'k-', lw=2.2, label='sleqn niter=50')
ax.plot(lat, gt[i], 'r--', lw=1.4, label='gravity-toolkit')
ax.plot(lat, ana[i], 'c:', lw=1.4, label='解析闭式解')
ax.plot(lat, s2[i], 'g-.', lw=1.2, label='sleqn niter=2（默认）')
ax.axhline(0, color='0.7', lw=0.6)
ax.set_xlabel('纬度 (°N)')
ax.set_ylabel('海平面变化 (cm)')
ax.set_title('(e) 沿 2.5°E 的经向剖面')
ax.legend(fontsize=7.5, loc='lower left')
ax.grid(alpha=0.3)

ax = fig.add_subplot(gs[1, 2])
ax.plot(gt.ravel(), s50.ravel(), '.', ms=0.6, alpha=0.35, color='C0')
lim2 = np.abs(s50).max() * 1.05
ax.plot([-lim2, lim2], [-lim2, lim2], 'k-', lw=0.8)
ax.set_xlim(-lim2, lim2); ax.set_ylim(-lim2, lim2)
ax.set_xlabel('gravity-toolkit (cm)')
ax.set_ylabel('sleqn niter=50 (cm)')
ax.set_title(f'(f) 逐点散点  r={cor:.8f}')
ax.grid(alpha=0.3)

fig.suptitle('图 1　demo 算例（全球皆海洋）三路对照：sleqn / gravity-toolkit / 解析闭式解',
             fontsize=12, y=0.985)
fig.savefig(os.path.join(OUT, 'fig1_demo_三路对照.png'), bbox_inches='tight')
plt.close(fig)
print('fig1 done')

# ======================================================================
# Fig 2 -- grace: realistic mask + real GRACE load
# ======================================================================
d = np.load(os.path.join(TMP, 'fields_grace.npz'))
lon, lat = d['lon'], d['lat']
s50, s2, gt = d['sleqn_n50'], d['sleqn_n2'], d['gravtk']
oc = d['ofcn'] > 0.5
m = np.isfinite(gt)
oc = oc & m
v = np.abs(s50[oc]).max()

fig = plt.figure(figsize=(15, 8.0))
gs = GridSpec(2, 3, figure=fig, hspace=0.30, wspace=0.16)
proj = ccrs.Robinson() if HAVE_CARTOPY else None

ax = fig.add_subplot(gs[0, 0], projection=proj)
im = gmap(ax, lon, lat, s50, '(a) sleqn  niter=50', vmin=-v, vmax=v)
add_cbar(fig, im, ax, 'cm')

ax = fig.add_subplot(gs[0, 1], projection=proj)
im = gmap(ax, lon, lat, gt, '(b) gravity-toolkit（收敛）', vmin=-v, vmax=v)
add_cbar(fig, im, ax, 'cm')

mxa, mna, cor, ref = stats(gt, s50, oc)
ax = fig.add_subplot(gs[0, 2], projection=proj)
lim = np.abs((gt - s50)[oc]).max()
im = gmap(ax, lon, lat, np.where(m, gt - s50, np.nan),
          f'(c) 差值 (b)-(a)\nmax|Δ|={mxa:.2e} cm = {mxa/ref:.3%}×峰值, r={cor:.8f}',
          cmap='RdBu_r', vmin=-lim, vmax=lim)
add_cbar(fig, im, ax, 'cm')

mxa2, mna2, cor2, _ = stats(gt, s2, oc)
ax = fig.add_subplot(gs[1, 0], projection=proj)
lim2 = np.abs((gt - s2)[oc]).max()
im = gmap(ax, lon, lat, np.where(m, gt - s2, np.nan),
          f'(d) 差值 改用 sleqn 默认 niter=2\nmax|Δ|={mxa2:.2e} cm = {mxa2/ref:.2%}×峰值',
          cmap='RdBu_r', vmin=-lim2, vmax=lim2)
add_cbar(fig, im, ax, 'cm')

ax = fig.add_subplot(gs[1, 1])
dd = (gt - s50)[oc]
ax.hist(dd, bins=120, color='C0', alpha=0.85)
ax.set_xlabel('Δ = gravity-toolkit − sleqn(50)  (cm)')
ax.set_ylabel('格点数')
ax.set_title(f'(e) 差值分布：mean={dd.mean():.2e}, std={dd.std():.2e} cm')
ax.grid(alpha=0.3)

ax = fig.add_subplot(gs[1, 2])
i = np.argmin(np.abs(lon - 300.5))
sel = np.isfinite(gt[i])
ax.plot(lat[sel], s50[i][sel], 'k-', lw=1.8, label='sleqn niter=50')
ax.plot(lat[sel], gt[i][sel], 'r--', lw=1.2, label='gravity-toolkit')
ax.plot(lat[sel], s2[i][sel], 'g-.', lw=1.0, label='sleqn niter=2（默认）')
ax.axhline(0, color='0.7', lw=0.6)
ax.set_xlabel('纬度 (°N)')
ax.set_ylabel('海平面变化 (cm)')
ax.set_title('(f) 沿 300.5°E 的经向剖面')
ax.legend(fontsize=7.5)
ax.grid(alpha=0.3)

fig.suptitle('图 2　grace_example 真实算例（Natural Earth 掩膜 + CSR GRACE 趋势载荷）',
             fontsize=12, y=0.985)
fig.savefig(os.path.join(OUT, 'fig2_grace_真实算例.png'), bbox_inches='tight')
plt.close(fig)
print('fig2 done')

# ======================================================================
# Fig 3 -- pyslfp
# ======================================================================
d = np.load(os.path.join(TMP, 'fields_pyslfp.npz'))
lon_s, lat_s = d['lon_s'], d['lat_s']
lats_p = d['lat_p']
Sp, Ss, Sp_on = d['S_pyslfp'], d['S_sleqn'], d['S_p_on_sleqn']
v = max(abs(Ss).max(), abs(Sp_on).max())

fig = plt.figure(figsize=(15, 8.0))
gs = GridSpec(2, 3, figure=fig, hspace=0.30, wspace=0.16)
proj = ccrs.Robinson() if HAVE_CARTOPY else None

ax = fig.add_subplot(gs[0, 0], projection=proj)
im = gmap(ax, lon_s, lat_s, Sp_on, '(a) pyslfp 2.0.6（自带 PREM_4096）',
          vmin=-v, vmax=v)
add_cbar(fig, im, ax, 'cm')

ax = fig.add_subplot(gs[0, 1], projection=proj)
im = gmap(ax, lon_s, lat_s, Ss, '(b) sleqn（Wang et al. 2012 PREM）',
          vmin=-v, vmax=v)
add_cbar(fig, im, ax, 'cm')

mxa, mna, cor, ref = stats(Sp_on, Ss)
ax = fig.add_subplot(gs[0, 2], projection=proj)
lim = np.abs(Sp_on - Ss).max()
im = gmap(ax, lon_s, lat_s, Sp_on - Ss,
          f'(c) 差值 (a)-(b)\nmax|Δ|={mxa:.3e} cm = {mxa/ref:.3%}×峰值, r={cor:.8f}',
          cmap='RdBu_r', vmin=-lim, vmax=lim)
add_cbar(fig, im, ax, 'cm')

ax = fig.add_subplot(gs[1, 0])
ll = np.arange(1, 41)
F, H, K = d['F'], d['H'], d['K']
rho = float(d['density_scale'])
std = 3.0 * (1 + K[1:41] - H[1:41]) / (2 * ll + 1)
ax.plot(ll, F[1:41], 'k-', lw=2, label='pyslfp 求解器因子 $-(\u0125+\\hat k)$')
ax.plot(ll, std, 'r--', lw=1.5, label='标准 $3(1+k-h)/(2l+1)$')
ax.set_xlabel('阶 $l$')
ax.set_ylabel('逐阶响应因子')
ax.set_title('(d) 逐阶响应因子对照')
ax.legend(fontsize=7.5)
ax.grid(alpha=0.3)

ax = fig.add_subplot(gs[1, 1])
ax.plot(ll, F[1:41] / std - 1, 'o-', ms=3, color='C3')
ax.axhline(0, color='k', lw=0.7)
ax.set_xlabel('阶 $l$')
ax.set_ylabel('相对偏差')
ax.set_title('(e) 与独立 PREM 表的偏差\n均值 %+.3f%%，最大 %.3f%%'
             % (100 * np.mean(F[1:41] / std - 1), 100 * np.max(np.abs(F[1:41] / std - 1))))
ax.grid(alpha=0.3)

ax = fig.add_subplot(gs[1, 2])
ls_show = np.array([0, 2, 4, 6, 8, 10, 12, 16, 20])
Cp, Cs = d['C_p'], d['C_s']
ax.plot(ls_show, Cp[ls_show], 'ko-', ms=4, label='pyslfp $C_{l0}$')
ax.plot(ls_show, Cs[ls_show], 'r^--', ms=4, label='sleqn $C_{l0}$')
ax.set_yscale('symlog', linthresh=1e-3)
ax.set_xlabel('阶 $l$')
ax.set_ylabel('$C_{l0}$ (cm)')
ax.set_title('(f) 球谐系数逐阶对照')
ax.legend(fontsize=7.5)
ax.grid(alpha=0.3)

fig.suptitle('图 3　与 pyslfp 2.0.6 的独立对照（全球皆海洋 + 赤道对称光滑高斯帽载荷）',
             fontsize=12, y=0.985)
fig.savefig(os.path.join(OUT, 'fig3_pyslfp_对照.png'), bbox_inches='tight')
plt.close(fig)
print('fig3 done')

# ======================================================================
# Fig 4 -- default-parameter hazard + convergence + clipping
# ======================================================================
ref_f = os.path.join(WS, 'grace_example', 'slf_grace_t0001_1deg.txt')
REF = np.loadtxt(ref_f)[:, 2].reshape(360, 180)
lon1 = (np.arange(360) + 0.5) * 1.0
lat1 = 90.0 - (np.arange(180) + 0.5) * 1.0
cases = [('out_naive.txt', '全部默认\n(dlon=0.5, 负值清零)'),
         ('out_onlyclip.txt', 'dlon=1\n但负值清零'),
         ('out_onlygrid.txt', '允许负值\n但 dlon=0.5'),
         ('out_proper.txt', 'dlon=1 + 允许负值\n（正确）')]
oc1 = (1.0 - np.loadtxt(os.path.join(WS, 'grace_example', 'land.fcn.1_deg'))[:, 2]
       ).reshape(180, 360).T > 0.5          # 真实海洋掩膜 (lon, lat)

fig = plt.figure(figsize=(19, 8.2))
gs = GridSpec(2, 4, figure=fig, hspace=0.34, wspace=0.16)
proj = ccrs.Robinson() if HAVE_CARTOPY else None
v = np.abs(REF).max()
oc1 = np.abs(REF) > 0

panels = [('参照（正确设置）', REF, None)]
for fn, lab in cases:
    panels.append((lab, np.loadtxt(os.path.join(TMP, fn))[:, 2].reshape(360, 180), fn))

for k, (lab, A, _fn) in enumerate(panels[:4]):
    ax = fig.add_subplot(gs[0, k], projection=proj)
    if k == 0:
        ttl = '(a) ' + lab
    else:
        mxa, mna, cor, _ = stats(A, REF, oc1)
        ttl = f'({"bcd"[k-1]}) {lab}\nmax|Δ|={mxa:.2f} cm ({mxa/v:.0%}×峰值), r={cor:.3f}'
    im = gmap(ax, lon1, lat1, A, ttl, vmin=-v, vmax=v)
    add_cbar(fig, im, ax, 'cm')

# (e) correct settings minus reference -> should be exactly zero
A = panels[4][1]
mxa, mna, cor, _ = stats(A, REF, oc1)
ax = fig.add_subplot(gs[1, 0], projection=proj)
im = gmap(ax, lon1, lat1, np.where(oc1, A - REF, np.nan),
          f'(e) 正确设置 vs 参照的差值\nmax|Δ|={mxa:.1e} cm（逐字节一致）',
          cmap='RdBu_r', vmin=-1e-3, vmax=1e-3)
add_cbar(fig, im, ax, 'cm')

# (f) convergence
ax = fig.add_subplot(gs[1, 1])
ns = [0, 1, 2, 3, 5, 10, 20, 50]
refc = np.loadtxt(os.path.join(TMP, 'conv200.txt'))[:, 2]
mx = np.array([np.abs(np.loadtxt(os.path.join(TMP, f'conv{n}.txt'))[:, 2] - refc).max()
               for n in ns])
pk = np.abs(refc).max()
ax.semilogy(ns, mx / pk, 'o-', color='C0')
for n, y in zip(ns, mx / pk):
    ax.annotate(f'{y:.1e}', (n, y), textcoords='offset points', xytext=(2, 5),
                fontsize=6.5)
ax.axvline(2, color='r', ls='--', lw=1)
ax.annotate('默认 niter=2', (2.2, 0.2), color='r', fontsize=8)
ax.set_xlabel('迭代次数 niter')
ax.set_ylabel('max|Δ| / 峰值')
ax.set_title('(f) 迭代收敛性（demo 算例）')
ax.grid(alpha=0.3, which='both')

# (g) clipping
ax = fig.add_subplot(gs[1, 2])
c1 = np.loadtxt(os.path.join(TMP, 'grace_clip_1.txt'))[:, 2]
c0 = np.loadtxt(os.path.join(TMP, 'grace_clip_0.txt'))[:, 2]
ax.plot(c0, c1, '.', ms=0.5, alpha=0.25, color='C3')
ax.plot([c0.min(), c0.max()], [c0.min(), c0.max()], 'k-', lw=0.8)
ax.set_xlabel('允许负值（正确）  cm')
ax.set_ylabel('默认清零负值  cm')
ax.set_title('(g) 负值清零对 GRACE 趋势载荷的影响\n'
             '（载荷 29.8%% 格点为负；峰值差 %.2f cm）' % np.abs(c0 - c1).max())
ax.grid(alpha=0.3)

# (h) text summary
ax = fig.add_subplot(gs[1, 3])
ax.axis('off')
oc1n = oc1.sum()
rows = [('设置', 'max|Δ| (cm)', '占峰值', 'r')]
for fn, lab in cases:
    A = np.loadtxt(os.path.join(TMP, fn))[:, 2].reshape(360, 180)
    mxa, mna, cor, _ = stats(A, REF, oc1)
    rows.append((lab.replace('\n', ' '), f'{mxa:.2f}', f'{mxa/v:.0%}', f'{cor:.3f}'))
tbl = ax.table(cellText=rows[1:], colLabels=rows[0], loc='center', cellLoc='left')
tbl.auto_set_font_size(False)
tbl.set_fontsize(8)
tbl.scale(1.0, 1.7)
ax.set_title('(h) grace_example t0001：与仓库自带参照的偏差\n'
             f'（海洋格点 {oc1n}；峰值 {v:.3f} cm）', fontsize=10)

fig.suptitle('图 4　命令行默认参数的风险 + 迭代收敛性 + 负值裁剪',
             fontsize=12, y=0.985)
fig.savefig(os.path.join(OUT, 'fig4_默认参数与收敛性.png'), bbox_inches='tight')
plt.close(fig)
print('fig4 done')
print('输出目录:', OUT)
