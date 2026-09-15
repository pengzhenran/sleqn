# -*- coding: utf-8 -*-
"""
verify_pyslfp.py -- what pyslfp can and cannot be used for on this machine.

Records, reproducibly:
  1. the installed version and that the package imports;
  2. that its runtime datasets are fetched from Zenodo and are unreachable
     from this network, so ``EarthModel.from_defaults()`` cannot be built;
  3. what happens through the documented custom Love-number path
     (``EarthModel(lmax, love_number_file=...)``) when the file holds the
     classical PREM load Love numbers;
  4. the per-degree factor pyslfp's solver applies, next to the standard
     geoid-minus-displacement factor.
"""
import os
import sys
import traceback

import numpy as np
from pyshtools import SHGrid

TMP = r'C:\Users\pengzhenran\AppData\Local\Temp\slverify'
LMAX = 64
raw = np.loadtxt(TMP + r'\prem_love_180.txt')
h, k = raw[:LMAX + 1, 1], raw[:LMAX + 1, 2]

import pyslfp as sl                                    # noqa: E402
from pyslfp.core import EarthModel                     # noqa: E402
from pyslfp.state import EarthState                    # noqa: E402

print('1) 版本')
print('   pyslfp', sl.__version__ if hasattr(sl, '__version__') else '(no __version__)',
      '| python', sys.version.split()[0])

print('\n2) 默认地球模型（需要 Zenodo 数据）')
try:
    m = EarthModel.from_defaults(lmax=LMAX)
    print('   成功:', m)
except Exception as e:
    print('   失败:', type(e).__name__, str(e)[:200].replace('\n', ' '))

print('\n3) 自定义勒夫数文件路径')
fn = TMP + r'\prem_pyslfp_classic.dat'
with open(fn, 'w') as f:
    for l in range(LMAX + 1):
        f.write(f'{l:d} {h[l]:.12e} {k[l]:.12e} 0.0 0.0 0.0 0.0\n')
model = EarthModel(LMAX, love_number_file=fn)
p = model.parameters
print(f'   length_scale={p.length_scale:.6e}  density_scale={p.density_scale:.6e}')
print(f'   g_nd={p.gravitational_acceleration:.6f}  rho_w_nd={p.water_density:.6e}')
print(f'   非量纲 h_nd[0:4] = {model.love_numbers.h[:4]}')
print(f'   非量纲 k_nd[0:4] = {model.love_numbers.k[:4]}')

lats, lons = model.lats(), model.lons()
ice = SHGrid.from_array(np.zeros((len(lats), len(lons))), grid=model.grid)
sea = SHGrid.from_array(np.ones((len(lats), len(lons))), grid=model.grid)
state = EarthState(ice, sea, model, exclude_caspian=False)
print(f'   海洋函数 均值={state.ocean_function.data.mean():.6f} '
      f'面积={state.ocean_area:.6f} (4pi={4*np.pi:.6f})')

# 单阶载荷响应
co = model.zero_coefficients()
co.coeffs[0, 2, 0] = 1.0
load = model.expand_coefficient(co)
sle = sl.LinearSeaLevelEquation(state)
import warnings
with warnings.catch_warnings(record=True) as w:
    warnings.simplefilter('always')
    slc, _, _, _ = sle.solve_sea_level_equation(load, rotational_feedbacks=False,
                                                 rtol=1e-13, max_iterations=200)
    for x in w[:2]:
        print('   警告:', str(x.message)[:120])
sc = model.expand_field(slc)
got = sc.coeffs[0, 2, 0].real
f_pyslfp = -(model.love_numbers.h[2] + model.love_numbers.k[2] /
             p.gravitational_acceleration)
f_std = 3 * (1 + k[2] - h[2]) / (p.density_scale * 5)
print(f'   单阶(l=2,m=0)载荷 C20=1 的响应 S20 = {got:.6e}')
print(f'   收敛判据 |rho_w_nd * slc_factor| = '
      f'{abs(p.water_density * f_pyslfp):.3e}  (需 < 1 才收敛)')

print('\n4) 逐阶响应因子对照（均为非量纲量）')
print('    l    pyslfp: -(h_nd + k_nd/g)    标准: 3(1+k-h)/(rho_e*(2l+1))')
for l in (1, 2, 3, 5, 10):
    a = -(model.love_numbers.h[l] + model.love_numbers.k[l] / p.gravitational_acceleration)
    b = 3 * (1 + k[l] - h[l]) / (p.density_scale * (2 * l + 1))
    print(f'   {l:2d}   {a:+.6e}                {b:+.6e}')
