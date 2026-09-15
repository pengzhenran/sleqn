# -*- coding: utf-8 -*-
"""Debug the analytic all-ocean closed form against sleqn."""
import os, sys
import numpy as np
WS = r'D:\华为家庭存储\mywork\sealevel'
TMP = r'C:\Users\pengzhenran\AppData\Local\Temp\slverify'
sys.path.insert(0, WS); sys.path.insert(0, os.path.join(WS, '_verify'))
import sleqn
import verify_slf as V
from gravity_toolkit.units import units as U

lmax = 180
uu = U(lmax=lmax)
sleqn.RHOAVE = float(uu.rho_e)
sleqn.ARAD = float(uu.rad_e)

c = V.build_common(os.path.join(WS, 'demo', 'land.fcn.1_deg'),
                   os.path.join(TMP, 'love_gravtk2.txt'), lmax)
c['dlon'] = c['dlat'] = 0.5
c['clip'] = True

r2 = V.run_sleqn(c, os.path.join(WS, 'demo', 'load_demo.txt'),
                 os.path.join(TMP, 'dbg_n2.txt'), 2)
r50 = V.run_sleqn(c, os.path.join(WS, 'demo', 'load_demo.txt'),
                  os.path.join(TMP, 'dbg_n50.txt'), 50)
T, Ts, tmass = r2['T'], r2['S'], r2['tmass']

print('max|sleqn n2 | = %.6f   max|sleqn n50| = %.6f'
      % (np.abs(r2['grid']).max(), np.abs(r50['grid']).max()))
print('argmax n2  =', np.unravel_index(np.abs(r2['grid']).argmax(), r2['grid'].shape))
print('argmax n50 =', np.unravel_index(np.abs(r50['grid']).argmax(), r50['grid'].shape))
print('tmass = %.6e   S00(cons) = %.10e' %
      (tmass, -tmass / (sleqn.RHO0 * sleqn.ARAD ** 2) / (4 * np.pi)))

# ---- round trip test of synthesis / analysis pair ----
coef = np.zeros((lmax + 1, lmax + 1))
rng = np.random.default_rng(0)
for l in range(lmax + 1):
    coef[l, :l + 1] = rng.standard_normal(l + 1)
ccT, ssT, plm = c['ccos'].T, c['ssin'].T, c['plm']
field = np.zeros((sleqn.NPHI, sleqn.NTH))
for l in range(lmax + 1):
    mm = l + 1
    field += (coef[l, 0:mm][None, :] * ccT[:, 0:mm]) @ plm[l, 0:mm, :]
back, _ = sleqn.geoid(field, c['rlon'], c['rlat'], plm, c['ccos'], c['ssin'],
                      sleqn.NTH, sleqn.NPHI, lmax, lmax)
print('\n[round trip] Syn->Ana 比值（应为 1）:')
for (l, m) in [(0, 0), (1, 0), (2, 0), (2, 1), (2, 2), (5, 3), (10, 10), (60, 30)]:
    print('   (l=%3d,m=%3d)  in=%+.6e  out=%+.6e  ratio=%+.6f'
          % (l, m, coef[l, m], back[l, m], back[l, m] / coef[l, m]))

# ---- coefficient-wise check of the closed form ----
ana = V.analytic_field(c, T, Ts, tmass)
ca, _ = sleqn.geoid(ana, c['rlon'], c['rlat'], plm, c['ccos'], c['ssin'],
                    sleqn.NTH, sleqn.NPHI, lmax, lmax)
c50, _ = sleqn.geoid(r50['grid'], c['rlon'], c['rlat'], plm, c['ccos'], c['ssin'],
                     sleqn.NTH, sleqn.NPHI, lmax, lmax)
c2, _ = sleqn.geoid(r2['grid'], c['rlon'], c['rlat'], plm, c['ccos'], c['ssin'],
                    sleqn.NTH, sleqn.NPHI, lmax, lmax)
print('\n[coefficients]   ana          sleqn50       sleqn2      ana/sleqn50')
for (l, m) in [(0, 0), (1, 0), (1, 1), (2, 0), (2, 1), (2, 2), (3, 0), (5, 0),
               (10, 0), (20, 0)]:
    print('   (l=%3d,m=%3d) %+.6e %+.6e %+.6e  %+.6f'
          % (l, m, ca[l, m], c50[l, m], c2[l, m], ca[l, m] / c50[l, m]))
print('\nmax|ana| = %.6f  max|sleqn50| = %.6f' %
      (np.abs(ana).max(), np.abs(r50['grid']).max()))
print('ana vs sleqn50: max|d| = %.6e' % np.abs(ana - r50['grid']).max())
