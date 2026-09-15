# -*- coding: utf-8 -*-
"""
verify_pyslfp_full.py -- quantitative cross-check of sleqn against pyslfp.

Design (deliberately non-circular):
  * Both codes solve the *same* problem: an all-ocean Earth under the same
    smooth, equatorially symmetric surface mass load.
  * pyslfp uses its own official PREM_4096 Love numbers and its own solver.
  * sleqn uses gravity_toolkit's PREM load Love numbers (a third, independent
    PREM tabulation) and its own solver.
  * The load is defined analytically on each grid, so no regridding is needed.
  * Equatorial symmetry kills the degree-2, order-1 term, so rotational
    feedback is inactive in both codes and does not have to be matched.

Comparison is made both in the spatial domain and degree by degree in the
spherical harmonic domain.
"""
import os
import sys
import time

import numpy as np
import pyshtools as pysh
from pyshtools import SHGrid

WS = r'D:\华为家庭存储\mywork\sealevel'
TMP = r'C:\Users\pengzhenran\AppData\Local\Temp\slverify'
sys.path.insert(0, WS)
sys.path.insert(0, os.path.join(WS, '_verify'))

import sleqn                       # noqa: E402
import pyslfp as sl                # noqa: E402
from pyslfp.core import EarthModel  # noqa: E402
from pyslfp.state import EarthState  # noqa: E402

# 独立的第三套 PREM 负荷勒夫数：gravity_toolkit 的 Wang et al. (2012) PREM 表，
# 以 CE 参考框架存成 ASCII（即 grace_example/love_numbers 的同一张表）。
_ce = np.loadtxt(os.path.join(WS, 'grace_example', 'love_numbers'), skiprows=2)
H_CE, K_CE = _ce[:181, 1].copy(), _ce[:181, 2].copy()

LMAX = 180
AMP_M = 1.0            # peak water-equivalent thickness [m]
CAP_RADIUS_DEG = 8.0   # Gaussian cap half-width
CAP_LAT, CAP_LON = 45.0, 0.0


def gauss_cap(lat, lon, lat0=CAP_LAT, lon0=CAP_LON, r=CAP_RADIUS_DEG):
    """Smooth cap, mirrored about the equator to preserve equatorial symmetry."""
    def one(la, lo):
        d2 = ((la - lat0) ** 2 + ((lo - lon0 + 180) % 360 - 180) ** 2
              * np.cos(np.deg2rad(la)) ** 2)
        return AMP_M * np.exp(-0.5 * (d2 / r ** 2))
    return one(lat, lon) + one(-lat, lon)


print('=' * 72)
print('pyslfp 官方数据与地球模型')
model = EarthModel.from_defaults(lmax=LMAX)
p = model.parameters
print(f'  网格={model.grid_name}  lmax={model.lmax}  归一化={model.normalization}')
print(f'  length_scale={p.length_scale:.6e} m  density_scale={p.density_scale:.6e} kg/m3')
print(f'  rho_w_nd={p.water_density:.6e}  g_nd={p.gravitational_acceleration:.6f}')
ln = model.love_numbers
print(f'  h_nd[1:5]={ln.h[1:5]}')
print(f'  k_nd[1:5]={ln.k[1:5]}')
# pyslfp 求解器实际使用的逐阶响应因子
F = -(ln.h + ln.k / p.gravitational_acceleration)

print('\n与独立的 Wang et al. (2012) PREM 表给出的标准因子对比')
print('   标准因子 = 3(1+k-h)/(2l+1)   （pyslfp 的非量纲化下 4*pi*G_nd = 3）')
print(f'   {"l":>4} {"pyslfp F_l":>14} {"标准(Wang12 CE)":>18} {"比值-1":>12}')
rels = []
for l in range(1, 41):
    std = 3.0 * (1 + K_CE[l] - H_CE[l]) / (2 * l + 1)
    rels.append(F[l] / std - 1.0)
    if l <= 10 or l in (20, 40):
        print(f'   {l:>4} {F[l]:>14.6f} {std:>18.6f} {F[l]/std-1:>12.4%}')
rels = np.array(rels)
print(f'  F_l / 标准因子 - 1  (l=1..40): 均值 {rels.mean():+.4%}  '
      f'标准差 {rels.std():.4%}  最大 {np.abs(rels).max():.4%}')

print('\n' + '=' * 72)
print('载荷与海洋函数')
lats_p, lons_p = model.lats(), model.lons()
sig_p = gauss_cap(lats_p[:, None], lons_p[None, :])
ice = SHGrid.from_array(np.zeros_like(sig_p), grid=model.grid)
sea = SHGrid.from_array(np.ones_like(sig_p), grid=model.grid)
state = EarthState(ice, sea, model, exclude_caspian=False)
print(f'  pyslfp 网格 {sig_p.shape}  海洋函数均值={state.ocean_function.data.mean():.6f}')
print(f'  pyslfp 海洋面积(nd)={state.ocean_area:.8f}  4pi*({p.mean_sea_floor_radius:.1f}/'
      f'{p.length_scale:.1f})^2={4*np.pi*p.mean_sea_floor_radius**2:.8f}')

# pyslfp：载荷为非量纲面密度 = rho_w * h / (rho_e * L)
rho_w_si = p.raw_water_density
sig_phys = rho_w_si * sig_p                     # kg/m^2
load_nd = SHGrid.from_array(sig_phys / p.load_scale, grid=model.grid)

print('\n求解 pyslfp ...')
t0 = time.time()
sle = sl.LinearSeaLevelEquation(state)
slc_nd, disp, pot, omega = sle.solve_sea_level_equation(
    load_nd, rotational_feedbacks=True, rtol=1e-10, max_iterations=2000)
S_pyslfp_m = slc_nd.data * p.length_scale       # metres
S_pyslfp_cm = S_pyslfp_m * 100.0
print(f'  完成 {time.time()-t0:.1f} s  min={S_pyslfp_cm.min():+.4f} '
      f'max={S_pyslfp_cm.max():+.4f} cm  极移={omega}')

# 载荷总质量（两种算法应当一致）
M_p = p.length_scale ** 2 * model.integrate(load_nd) * p.density_scale * p.length_scale
print(f'  pyslfp 侧载荷质量 = {M_p:.6e} kg')

print('\n' + '=' * 72)
print('sleqn 侧：同一载荷写到 1 度网格')
gt_love = os.path.join(TMP, 'love_gt2CE.txt')
L = None
with open(gt_love, 'w') as f:
    f.write('# from gravity_toolkit Wang et al. (2012) PREM, CE frame\n')
    f.write('#        l        h_load        k_load      (reserved)\n')
    for l in range(LMAX + 1):
        f.write(f'{l:9d} {H_CE[l]: .8e} {K_CE[l]: .8e} {0.0: .8e}\n')

# 全海洋掩膜
mask_f = os.path.join(TMP, 'mask_allocean.txt')
lat_c = 90.0 - (np.arange(sleqn.NTH) + 0.5) * 180.0 / sleqn.NTH
lon_c = (np.arange(sleqn.NPHI) + 0.5) * 360.0 / sleqn.NPHI
with open(mask_f, 'w') as f:
    for la in lat_c:
        for lo in lon_c:
            f.write(f'{lo:7.1f} {la:7.1f}    0\n')

load_f = os.path.join(TMP, 'load_gauss_1deg.txt')
sig_1deg = gauss_cap(lat_c[:, None], lon_c[None, :])
with open(load_f, 'w') as f:
    for j in range(sleqn.NTH):
        for i in range(sleqn.NPHI):
            f.write(f'{lon_c[i]:8.2f} {lat_c[j]:8.2f} {sig_1deg[j, i]:12.6f}\n')
M_s = (sleqn.ARAD ** 2 * sleqn.DTR ** 2
       * np.sum(sig_1deg * 100.0 * np.sin(np.deg2rad(90 - lat_c))[:, None]))
print(f'  1 度网格载荷质量 = {M_s:.6e} g = {M_s/1000:.6e} kg  '
      f'(与 pyslfp 之比 {M_s/1000/M_p:.6f})')

sleqn.set_lmax(LMAX)
ofcn, rlon, rlat = sleqn.load_mask(mask_f)
h, rk = sleqn.load_love(gt_love)
ls = np.arange(sleqn.LLOVE + 1)
coefh = (1.0 + rk - h) * 3.0 * sleqn.RHO0 / sleqn.RHOAVE / (2.0 * ls + 1.0)
coefp = (1.0 + rk - h) / (rk + 1.0)
plm = np.zeros((LMAX + 1, LMAX + 1, sleqn.NTH))
fac = np.full(LMAX + 1, 2.0); fac[0] = np.sqrt(2.0)
for j in range(sleqn.NTH):
    plm[:, :, j] = sleqn.martin(LMAX, np.cos((90.0 - rlat[j]) * sleqn.DTR)) * fac[None, :]
ms = np.arange(LMAX + 1)[:, None]
ph = ms * (rlon[None, :] * sleqn.DTR)
ccos, ssin = np.cos(ph), np.sin(ph)

print('  求解 sleqn (niter=50) ...')
t0 = time.time()
z, tm, sm, ar = sleqn.solve_one(load_f, os.path.join(TMP, 'slf_pyslfp_cmp.txt'),
                                ofcn, rlon, rlat, plm, ccos, ssin, coefh, coefp,
                                h, rk, niter=50, dlon=1.0, dlat=1.0,
                                clip_negative=False)
S_sleqn = np.loadtxt(os.path.join(TMP, 'slf_pyslfp_cmp.txt'))[:, 2]
S_sleqn = S_sleqn.reshape(sleqn.NPHI, sleqn.NTH)
print(f'  完成 {time.time()-t0:.1f} s  min={S_sleqn.min():+.4f} '
      f'max={S_sleqn.max():+.4f} cm')

# 把 pyslfp 的场插值到 sleqn 的 1 度网格（sleqn 的场是 [经度, 纬度]）
co = model.expand_field(slc_nd)
S_p_on_sleqn = co.expand(lat=lat_c[:, None] * np.ones((1, sleqn.NPHI)),
                         lon=np.ones((sleqn.NTH, 1)) * lon_c[None, :])
S_p_on_sleqn = np.asarray(S_p_on_sleqn).reshape(sleqn.NTH, sleqn.NPHI).T \
    * p.length_scale * 100.0

print('\n' + '=' * 72)
print('空间场对比（sleqn 的 1 度网格，全海洋）')
d = S_p_on_sleqn - S_sleqn
print(f'  max|d| = {np.abs(d).max():.6e} cm    mean|d| = {np.abs(d).mean():.6e} cm')
print(f'  max|sleqn| = {np.abs(S_sleqn).max():.6f} cm   '
      f'相对 max|d| = {np.abs(d).max()/np.abs(S_sleqn).max():.3%}')
print(f'  相关系数 = {np.corrcoef(S_p_on_sleqn.ravel(), S_sleqn.ravel())[0,1]:.8f}')
print(f'  近场(载荷中心) pyslfp={S_p_on_sleqn[np.argmin(abs(lat_c-44.5)), np.argmin(abs(lon_c-0.5))]:+.6f}'
      f'  sleqn={S_sleqn[np.argmin(abs(lat_c-44.5)), np.argmin(abs(lon_c-0.5))]:+.6f} cm')
print(f'  远场(对跖点) pyslfp={S_p_on_sleqn[np.argmin(abs(lat_c+44.5)), np.argmin(abs(lon_c-179.5))]:+.6f}'
      f'  sleqn={S_sleqn[np.argmin(abs(lat_c+44.5)), np.argmin(abs(lon_c-179.5))]:+.6f} cm')

print('\n球谐系数逐阶对比（4pi 归一化，单位 cm）')
# sleqn 的系数
c_s, _ = sleqn.geoid(S_sleqn, rlon, rlat, plm, ccos, ssin,
                     sleqn.NTH, sleqn.NPHI, LMAX, LMAX)
# pyslfp 的系数：ortho -> 4pi
c_p = co.coeffs / np.sqrt(4 * np.pi) * p.length_scale * 100.0
print(f'   {"l":>4} {"pyslfp Re C_l0":>16} {"sleqn C_l0":>16} {"比值":>10}')
for l in (0, 1, 2, 3, 4, 5, 8, 10, 15, 20, 30, 50):
    a = c_p[0, l, 0].real
    b = c_s[l, 0]
    print(f'   {l:>4} {a:>16.6e} {b:>16.6e} {a/b if b else float("nan"):>10.6f}')

# 总质量守恒核对
print('\n质量守恒')
print(f'  sleqn  zmass = {z:.6f} Gt   载荷 tmass = {tm/1e15:.6f} Gt')
m_pys = p.length_scale ** 2 * p.density_scale * p.length_scale * \
    model.integrate(SHGrid.from_array(slc_nd.data, grid=model.grid))
print(f'  pyslfp 侧全球 ∫S dΩ * rho_w * a^2 = {m_pys:.6e}  (kg, 应为载荷质量的相反数)')
