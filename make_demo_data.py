#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_demo_data.py —— 生成 sleqn.py / sleqn.f90 的合成演示数据
============================================================

文章配套的测试数据需要通过“阅读原文”到网盘下载；在拿到真实数据之前，
可以用本脚本生成一组**合成演示数据**（不是真实 GRACE 观测、也不是真实海陆掩膜），
先把程序流程跑通、确认编译/运行环境无误。

生成的文件（默认写入 demo/ 目录）：
    land.fcn.1_deg  合成海陆掩膜（默认：全球皆海洋）
    love_numbers    合成弹性负荷勒夫数（PREM 量级的平滑近似）
    load_demo.txt   位于北极附近的方形“冰盖”质量载荷（水当量 1 m）
    Filelist.txt    控制文件：load_demo.txt → slf_demo.txt

用法:
    python make_demo_data.py                 # 写入 ./demo
    python make_demo_data.py --out mydemo    # 写入 ./mydemo
    python make_demo_data.py --land          # 掩膜改为“合成大陆”（矩形陆地）

随后即可运行:
    python sleqn.py --mask demo/land.fcn.1_deg --love demo/love_numbers \\
                    --list demo/Filelist.txt
"""

from __future__ import annotations

import argparse
import os

import numpy as np


def make_love(path, nl=181):
    """生成平滑、量级合理的弹性负荷勒夫数表（PREM 近似，非真实数值表）。

    前 2 行为表头（Fortran 版直接跳过、不解析），其后每行 4 列：
    ``l  h_l  k_l  (保留列)``，与 Fortran 的
    ``Read(90,*) ldum, h(l), rk(l), rll`` 严格对齐。
    """
    lines = ['# synthetic PREM-like elastic load Love numbers (DEMO ONLY)',
             '#        l        h_load        k_load      (reserved)']
    for l in range(nl):
        if l == 0:
            h, k = 0.0, 0.0
        elif l == 1:
            h, k = -0.2695, 0.0
        else:
            h = -1.0 - 0.05 * (1.0 - np.exp(-(l - 2) / 2.0))
            k = -0.303 * np.exp(-(l - 2) / 2.5)
        lines.append(f'{l:9d} {h: .8e} {k: .8e} {0.0: .8e}')
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')


def make_mask(path, nth=180, nphi=360, land=False):
    """合成海陆掩膜：value=1 为陆地、0 为海洋，每行 '经度 纬度 value'。

    注意两件事：
    1. 数据文件中**不能**写 '#' 之类的注释行，否则 Fortran 版的 ``Read(80,*)``
       会读错；
    2. 第 3 列写成**整数** 0/1：Fortran 版中 ``ivalue`` 因隐式类型规则是整型
       （字母 i 不在 A-H/O-Z 之内），写成 "0.0"/"1.0" 会导致读入失败。
    """
    with open(path, 'w', encoding='utf-8') as f:
        for j in range(nth):
            lat = 90.0 - (j + 0.5) * 180.0 / nth
            for i in range(nphi):
                lon = (i + 0.5) * 360.0 / nphi
                if land:
                    # 两个"矩形大陆"：一个跨赤道、一个在南半球中纬
                    is_land = ((0.0 <= lon <= 120.0 and -10.0 <= lat <= 60.0)
                               or (200.0 <= lon <= 300.0 and -50.0 <= lat <= 10.0))
                    val = 1
                else:
                    val = 0
                f.write(f'{lon:7.1f} {lat:7.1f} {val:4d}\n')


def make_load(path, lon0=0.25, lat0=80.0, ncell=10, thick=1.0, dgrid=0.5):
    """在北极附近生成一块方形“冰盖”载荷（每行：经度 纬度 水当量高度(m)）。"""
    with open(path, 'w', encoding='utf-8') as f:
        for k in range(ncell):
            for m in range(ncell):
                lon = lon0 + k * dgrid
                lat = lat0 - m * dgrid
                f.write(f'{lon:8.2f} {lat:8.2f} {thick:10.3f}\n')


def main():
    ap = argparse.ArgumentParser(description='生成 sleqn 的合成演示数据')
    ap.add_argument('--out', default='demo', help='输出目录（默认 demo）')
    ap.add_argument('--land', action='store_true',
                    help='掩膜生成"合成大陆"而非全球海洋')
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    mask = os.path.join(args.out, 'land.fcn.1_deg')
    love = os.path.join(args.out, 'love_numbers')
    load = os.path.join(args.out, 'load_demo.txt')
    flist = os.path.join(args.out, 'Filelist.txt')

    make_mask(mask, land=args.land)
    make_love(love)
    make_load(load)
    with open(flist, 'w', encoding='utf-8') as f:
        f.write('load_demo.txt slf_demo.txt\n')

    print(f'已生成合成演示数据于 {os.path.abspath(args.out)}:')
    for p in (mask, love, load, flist):
        print(f'  {os.path.basename(p):16s} {os.path.getsize(p):>10d} B')
    print('\n运行示例：')
    print(f'  python sleqn.py --mask {mask} --love {love} --list {flist}')
    print('（注意：这是合成数据，结果只用于验证程序流程，不代表真实海平面指纹）')


if __name__ == '__main__':
    main()
