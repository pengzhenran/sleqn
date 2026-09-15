# -*- coding: utf-8 -*-
"""Run the cross-checks once more and dump the fields to .npy for plotting."""
import os, sys
import numpy as np

WS = r'D:\华为家庭存储\mywork\sealevel'
TMP = r'C:\Users\pengzhenran\AppData\Local\Temp\slverify'
sys.path.insert(0, WS)
sys.path.insert(0, os.path.join(WS, '_verify'))

import verify_slf as V                                    # noqa: E402
import sleqn                                              # noqa: E402
import gravity_toolkit as gravtk                          # noqa: E402
from gravity_toolkit.units import units as _u             # noqa: E402

LMAX = 180
_uu = _u(lmax=LMAX)
sleqn.RHOAVE = float(_uu.rho_e)
sleqn.ARAD = float(_uu.rad_e)

love_f = os.path.join(TMP, 'love_dump.txt')
L = V.make_love_file_from_gravtk(love_f, LMAX, 2, 'CF')
LOVE = (np.asarray(L.hl), np.asarray(L.kl), np.asarray(L.ll))


def dump(case):
    if case == 'demo':
        src = os.path.join(WS, 'demo')
        load = os.path.join(src, 'load_demo.txt')
        dlon = dlat = 0.5
        clip = True
    else:
        src = os.path.join(WS, 'grace_example')
        load = os.path.join(src, 'load_grace_trend_1deg.txt')
        dlon = dlat = 1.0
        clip = False
    mask = os.path.join(src, 'land.fcn.1_deg')
    c = V.build_common(mask, love_f, LMAX)
    c['dlon'], c['dlat'], c['clip'] = dlon, dlat, clip
    print(case, 'preprocessing done', flush=True)

    r50 = V.run_sleqn(c, load, os.path.join(TMP, f'dump_{case}_n50.txt'), 50)
    r2 = V.run_sleqn(c, load, os.path.join(TMP, f'dump_{case}_n2.txt'), 2)
    print(case, 'sleqn done', flush=True)
    T, Ts, Ta, Tsa, tmass = r50['T'], r50['S'], r50['T_after'], r50['S_after'], r50['tmass']

    sl = gravtk.sea_level_equation(T, Ts, c['rlon'], c['rlat'], 1.0 - c['ofcn'],
                                   LMAX=LMAX, LOVE=LOVE, POLAR=True,
                                   ITERATIONS=500, FILL_VALUE=np.nan)
    print(case, 'gravity_toolkit done', flush=True)

    d = dict(lon=c['rlon'], lat=c['rlat'], ofcn=c['ofcn'],
             sleqn_n50=r50['grid'], sleqn_n2=r2['grid'], gravtk=sl,
             tmass=tmass)
    if case == 'demo':
        d['analytic'] = V.analytic_field(c, Ta, Tsa, tmass)
    np.savez(os.path.join(TMP, f'fields_{case}.npz'), **d)
    print(case, 'saved', flush=True)


dump('demo')
dump('grace')
