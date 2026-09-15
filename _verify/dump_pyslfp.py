# -*- coding: utf-8 -*-
"""Dump the pyslfp vs sleqn all-ocean fields for plotting (run in the pyslfp venv)."""
import os, sys
import numpy as np
from pyshtools import SHGrid

WS = r'D:\华为家庭存储\mywork\sealevel'
TMP = r'C:\Users\pengzhenran\AppData\Local\Temp\slverify'
sys.path.insert(0, WS)
sys.path.insert(0, os.path.join(WS, '_verify'))

import sleqn                                   # noqa: E402
import pyslfp as sl                            # noqa: E402
from pyslfp.core import EarthModel             # noqa: E402
from pyslfp.state import EarthState            # noqa: E402

LMAX = 180
AMP_M, R_CAP, LAT0, LON0 = 1.0, 8.0, 45.0, 0.0


def gauss_cap(lat, lon):
    def one(la, lo):
        d2 = ((la - LAT0) ** 2 + (((lo - LON0 + 180) % 360) - 180) ** 2
              * np.cos(np.deg2rad(la)) ** 2)
        return AMP_M * np.exp(-0.5 * (d2 / R_CAP ** 2))
    return one(lat, lon) + one(-lat, lon)


model = EarthModel.from_defaults(lmax=LMAX)
p = model.parameters
lats_p, lons_p = model.lats(), model.lons()
sig_p = gauss_cap(lats_p[:, None], lons_p[None, :])
ice = SHGrid.from_array(np.zeros_like(sig_p), grid=model.grid)
sea = SHGrid.from_array(np.ones_like(sig_p), grid=model.grid)
state = EarthState(ice, sea, model, exclude_caspian=False)
load_nd = SHGrid.from_array(p.raw_water_density * sig_p / p.load_scale, grid=model.grid)

sle = sl.LinearSeaLevelEquation(state)
slc_nd, _, _, _ = sle.solve_sea_level_equation(load_nd, rotational_feedbacks=True,
                                               rtol=1e-10, max_iterations=2000)
S_pyslfp_cm = slc_nd.data * p.length_scale * 100.0
co = model.expand_field(slc_nd)
print('pyslfp done', flush=True)

# sleqn side (1 deg all-ocean grid)
_ce = np.loadtxt(os.path.join(WS, 'grace_example', 'love_numbers'), skiprows=2)
H, K = _ce[:181, 1], _ce[:181, 2]
love_f = os.path.join(TMP, 'love_dump_pys.txt')
with open(love_f, 'w') as f:
    f.write('# Wang et al. (2012) PREM CE\n#  l  h  k\n')
    for l in range(LMAX + 1):
        f.write(f'{l:9d} {H[l]: .8e} {K[l]: .8e} {0.0: .8e}\n')

mask_f = os.path.join(TMP, 'mask_allocean.txt')
lat_c = 90.0 - (np.arange(sleqn.NTH) + 0.5) * 180.0 / sleqn.NTH
lon_c = (np.arange(sleqn.NPHI) + 0.5) * 360.0 / sleqn.NPHI
with open(mask_f, 'w') as f:
    for la in lat_c:
        for lo in lon_c:
            f.write(f'{lo:7.1f} {la:7.1f}    0\n')
load_f = os.path.join(TMP, 'load_gauss_1deg.txt')
sig_1 = gauss_cap(lat_c[:, None], lon_c[None, :])
with open(load_f, 'w') as f:
    for j in range(sleqn.NTH):
        for i in range(sleqn.NPHI):
            f.write(f'{lon_c[i]:8.2f} {lat_c[j]:8.2f} {sig_1[j, i]:12.6f}\n')

sleqn.set_lmax(LMAX)
ofcn, rlon, rlat = sleqn.load_mask(mask_f)
h, rk = sleqn.load_love(love_f)
ls = np.arange(sleqn.LLOVE + 1)
coefh = (1.0 + rk - h) * 3.0 * sleqn.RHO0 / sleqn.RHOAVE / (2.0 * ls + 1.0)
coefp = (1.0 + rk - h) / (rk + 1.0)
plm = np.zeros((LMAX + 1, LMAX + 1, sleqn.NTH))
fac = np.full(LMAX + 1, 2.0); fac[0] = np.sqrt(2.0)
for j in range(sleqn.NTH):
    plm[:, :, j] = sleqn.martin(LMAX, np.cos((90.0 - rlat[j]) * sleqn.DTR)) * fac[None, :]
ms = np.arange(LMAX + 1)[:, None]
ph = ms * (rlon[None, :] * sleqn.DTR)
z, tm, sm, ar = sleqn.solve_one(load_f, os.path.join(TMP, 'dump_pys_sleqn.txt'),
                                ofcn, rlon, rlat, plm, np.cos(ph), np.sin(ph),
                                coefh, coefp, h, rk, niter=50, dlon=1.0, dlat=1.0,
                                clip_negative=False)
S_sleqn = np.loadtxt(os.path.join(TMP, 'dump_pys_sleqn.txt'))[:, 2]
S_sleqn = S_sleqn.reshape(sleqn.NPHI, sleqn.NTH)
c_s, _ = sleqn.geoid(S_sleqn, rlon, rlat, plm, np.cos(ph), np.sin(ph),
                     sleqn.NTH, sleqn.NPHI, LMAX, LMAX)
print('sleqn done', flush=True)

S_p_on = np.asarray(co.expand(lat=lat_c[:, None] * np.ones((1, sleqn.NPHI)),
                              lon=np.ones((sleqn.NTH, 1)) * lon_c[None, :])
                    ).reshape(sleqn.NTH, sleqn.NPHI).T * p.length_scale * 100.0
c_p = co.coeffs / np.sqrt(4 * np.pi) * p.length_scale * 100.0

ln = model.love_numbers
F = -(ln.h + ln.k / p.gravitational_acceleration)
np.savez(os.path.join(TMP, 'fields_pyslfp.npz'),
         lon_p=lons_p, lat_p=lats_p, S_pyslfp=S_pyslfp_cm,
         lon_s=rlon, lat_s=rlat, S_sleqn=S_sleqn, S_p_on_sleqn=S_p_on,
         C_p=c_p[0, :, 0].real, C_s=c_s[:, 0], F=F,
         H=H, K=K, density_scale=p.density_scale)
print('saved')
