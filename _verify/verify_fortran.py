# -*- coding: utf-8 -*-
"""Fortran 版 vs sleqn.py 的端到端一致性复核（在纯 ASCII 路径下运行）。"""
import os, shutil, subprocess, sys
import numpy as np

WS = r'D:\华为家庭存储\mywork\sealevel'
TMP = r'C:\Users\pengzhenran\AppData\Local\Temp\slverify'
FD = os.path.join(TMP, 'fdemo')
FC = (r'C:\Users\pengzhenran\AppData\Local\Microsoft\WinGet\Packages'
      r'\BrechtSanders.WinLibs.POSIX.UCRT_Microsoft.Winget.Source_8wekyb3d8bbv1'
      r'\mingw64\bin')
os.makedirs(FD, exist_ok=True)

# 准备 ASCII 工作目录
for f in ('land.fcn.1_deg', 'love_numbers', 'load_demo.txt'):
    shutil.copy(os.path.join(WS, 'demo', f), os.path.join(FD, f))
with open(os.path.join(FD, 'Filelist.txt'), 'w') as fh:
    fh.write('load_demo.txt slf_out.txt\n')


def run(cmd, cwd):
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                       errors='replace')
    return p.returncode, (p.stdout or '') + (p.stderr or '')


exes = {
    'fresh_orig (sleqn.f90)': os.path.join(TMP, 'sleqn_orig.exe'),
    'fresh_dp   (sleqn_dp.f90)': os.path.join(TMP, 'sleqn_dp.exe'),
    'shipped sleqn_static.exe': os.path.join(WS, 'sleqn_static.exe'),
    'shipped sleqn_dp_static.exe': os.path.join(WS, 'sleqn_dp_static.exe'),
}

results = {}
for name, exe in exes.items():
    out = os.path.join(FD, 'slf_out.txt')
    if os.path.exists(out):
        os.remove(out)
    rc, log = run([exe], FD)
    tag = log.strip().splitlines()
    mass = [l for l in tag if 'mass' in l.lower() or 'zmass' in l.lower()]
    if not os.path.exists(out):
        print(f'{name}: 失败 rc={rc}\n{log[-800:]}')
        continue
    a = np.loadtxt(out)
    results[name] = a
    print(f'{name}: rc={rc} 行数={len(a)}  ' +
          '  '.join(m.strip() for m in mass[:3]))

# Python 版（同样参数）
env = dict(os.environ)
py = sys.executable
rc, log = run([py, os.path.join(WS, 'sleqn.py'), '--mask', 'land.fcn.1_deg',
               '--love', 'love_numbers', '--list', 'Filelist.txt',
               '--fmt', 'e12.4', '--dlon', '0.5', '--dlat', '0.5'], FD)
py_out = os.path.join(FD, 'slf_out.txt')
apy = np.loadtxt(py_out)
print(f'python sleqn.py: rc={rc} 行数={len(apy)}')
print('   ' + '  '.join(l.strip() for l in log.splitlines()
                        if '质量' in l or 'mass' in l.lower())[:300])

print('\n================ 输出文件逐字节对比 ================')
with open(py_out, 'rb') as f:
    bpy = f.read()
for name in results:
    p = None
    # 重新生成各 exe 的输出以做字节比较
    out = os.path.join(FD, 'slf_out.txt')
    if os.path.exists(out):
        os.remove(out)
    run([exes[name]], FD)
    with open(out, 'rb') as f:
        bf = f.read()
    same = (bf == bpy)
    a = np.loadtxt(out)
    d = np.abs(a[:, 2] - apy[:, 2])
    rel = d / max(np.abs(apy[:, 2]).max(), 1e-30)
    ndiff = int((np.abs(a[:, 2] - apy[:, 2]) > 0).sum())
    print(f'{name}:')
    print(f'   逐字节相同 = {same}；不同的行数 = {ndiff}/{len(a)}')
    print(f'   max|Δ| = {d.max():.6e} cm，占场最大值 '
          f'{np.abs(apy[:,2]).max():.4f} cm 的 {rel.max():.4%}')
