#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_icon.py —— 生成程序图标（.ico 多尺寸 + .png 预览）
============================================================================

设计
----
一个圆形"地球"，里面就是本程序算出来的**海平面指纹场**：暖色斑块（近场抬升）
与冷色背景（远场下降）的偶极图案；再叠加该场的**等值线** —— 偶极场的等值线
天然是同心的回旋曲线，正好读出"指纹"的意思。

小尺寸（16/24 px）下细节会糊掉，所以刻意做得简单：一个圆 + 冷暖对比 + 白色轮廓，
缩到 16 px 仍然能认出来。

输出
----
    assets/sleqn.ico          多尺寸图标（16/24/32/48/64/128/256），给窗口与安装包用
    assets/sleqn_256.png      256×256 预览（给关于对话框/文档用）
    assets/sleqn_icon_sheet.png  各尺寸对照表（自检用）

    python tools/make_icon.py
"""

from __future__ import annotations

import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import matplotlib                                              # noqa: E402
matplotlib.use('Agg')
import matplotlib.pyplot as plt                                # noqa: E402
from matplotlib.colors import Normalize                        # noqa: E402
from matplotlib.patches import Circle, FancyBboxPatch          # noqa: E402

ASSETS = os.path.join(ROOT, 'assets')
MASTER = 1024                     # 先画大图再缩，边缘更干净
SIZES = [16, 24, 32, 48, 64, 128, 256]

BG_TOP = '#0f3f63'                # 背景渐变（深海蓝）
BG_BOT = '#061726'
RIM = '#f4f8fc'


def fingerprint_field(n=700):
    """造一个"海平面指纹"偶极场：冷色铺满全球（远场下降）+ 紧凑暖斑（近场抬升）。

    纯为图标造型，不追求物理量级；形态与本程序算出来的指纹场一致。
    要点是**冷背景铺满整个圆球**，否则边缘会退化成白色、小尺寸下糊成一团。
    """
    x = np.linspace(-1.0, 1.0, n)
    y = np.linspace(-1.0, 1.0, n)
    X, Y = np.meshgrid(x, y)

    def blob(cx, cy, sx, sy, rot=0.0):
        c, s = np.cos(rot), np.sin(rot)
        U = (X - cx) * c + (Y - cy) * s
        V = -(X - cx) * s + (Y - cy) * c
        return np.exp(-((U / sx) ** 2 + (V / sy) ** 2))

    near = blob(-0.30, 0.32, 0.27, 0.21, rot=-0.5)             # 近场抬升（暖斑）
    far = blob(0.14, -0.22, 1.30, 1.10, rot=0.20)              # 远场下降（冷背景）
    f = 1.50 * near - 0.60 * far
    # 大尺度起伏：等值线才不会是一圈圈同心圆，而像指纹的回旋
    f += 0.13 * np.sin(2.5 * X + 0.9) * np.cos(2.1 * Y - 0.5)
    return X, Y, f


def draw_master(path, size=MASTER, detail=True):
    X, Y, F = fingerprint_field()
    fig = plt.figure(figsize=(size / 100, size / 100), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis('off')

    # ---------- 圆角方形底：深海蓝渐变 ----------
    r = 0.22
    box = FancyBboxPatch((0.006, 0.006), 0.988, 0.988,
                         boxstyle=f'round,pad=0,rounding_size={r}',
                         linewidth=0, facecolor='none', zorder=1)
    ax.add_patch(box)
    grad = np.linspace(0, 1, 256).reshape(-1, 1)
    im_bg = ax.imshow(grad, extent=[0, 1, 0, 1], origin='lower', aspect='auto',
                      cmap=matplotlib.colors.LinearSegmentedColormap.from_list(
                          'bg', [BG_BOT, BG_TOP]), zorder=1)
    im_bg.set_clip_path(box)

    # ---------- 圆球：占满画布（小尺寸下才看得出颜色）----------
    cx, cy, R = 0.50, 0.50, 0.415
    ax.add_patch(Circle((cx, cy + 0.010), R * 1.03, facecolor='#03101c',
                        alpha=0.8, zorder=2, edgecolor='none'))   # 外圈阴影
    globe = Circle((cx, cy), R, transform=ax.transData, zorder=3)
    im = ax.imshow(F, extent=[cx - R, cx + R, cy - R, cy + R], origin='lower',
                   cmap='RdBu_r', norm=Normalize(-0.72, 1.0), aspect='auto',
                   zorder=3)
    im.set_clip_path(globe)

    # ---------- 等值线：读作"指纹"（小尺寸下会糊成一团，故只在 detail 时画）----------
    if detail:
        lon = np.linspace(cx - R, cx + R, F.shape[1])
        lat = np.linspace(cy - R, cy + R, F.shape[0])
        cs = ax.contour(lon, lat, F, levels=np.linspace(-0.62, 0.95, 13),
                        colors=RIM, linewidths=size * 0.0026, alpha=0.55, zorder=4)
        # 必须裁到圆球里，否则等值线会画到球外面去（像划痕）
        try:
            cs.set_clip_path(globe)                # matplotlib >= 3.8
        except Exception:                          # noqa: BLE001
            for coll in getattr(cs, 'collections', []):
                coll.set_clip_path(globe)

    # ---------- 球面高光 + 描边 ----------
    ax.add_patch(Circle((cx - 0.11, cy + 0.12), R * 0.72, facecolor='white',
                        alpha=0.10 if detail else 0.14, zorder=4.5,
                        edgecolor='none'))
    ax.add_patch(Circle((cx, cy), R, facecolor='none', edgecolor=RIM,
                        linewidth=size * (0.010 if detail else 0.026), zorder=5))

    fig.savefig(path, transparent=True)
    plt.close(fig)
    return path


def build_ico(frames, out):
    """自己拼 ICO：Pillow 只会拿一张底图去缩放，做不到"小尺寸换一张简版"。

    frames: [(边长, PIL.Image), ...]
    """
    import io
    import struct
    frames = sorted(frames, key=lambda t: t[0])
    head = struct.pack('<HHH', 0, 1, len(frames))
    entries, blobs = b'', b''
    offset = 6 + 16 * len(frames)
    for s, img in frames:
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        blob = buf.getvalue()
        w = 0 if s >= 256 else s          # ICO 里 256 记作 0
        entries += struct.pack('<BBBBHHII', w, w, 0, 0, 1, 32, len(blob), offset)
        offset += len(blob)
        blobs += blob
    with open(out, 'wb') as f:
        f.write(head + entries + blobs)
    return out


def main():
    from PIL import Image
    os.makedirs(ASSETS, exist_ok=True)

    # 大尺寸带"指纹"等值线；小尺寸换成简版（去掉发丝线、加粗描边），
    # 否则 16/24 px 下等值线会糊成一团脏点。
    big_sizes = [48, 64, 128, 256]
    small_sizes = [16, 24, 32]

    m_big = os.path.join(ASSETS, '_icon_big.png')
    m_small = os.path.join(ASSETS, '_icon_small.png')
    draw_master(m_big, MASTER, detail=True)
    draw_master(m_small, 256, detail=False)

    img_big = Image.open(m_big).convert('RGBA')
    img_small = Image.open(m_small).convert('RGBA')

    frames = [(s, img_big.resize((s, s), Image.LANCZOS)) for s in big_sizes]
    frames += [(s, img_small.resize((s, s), Image.LANCZOS)) for s in small_sizes]

    ico = os.path.join(ASSETS, 'sleqn.ico')
    build_ico(frames, ico)

    # 256 预览（给"关于"对话框/文档用）
    png256 = os.path.join(ASSETS, 'sleqn_256.png')
    img_big.resize((256, 256), Image.LANCZOS).save(png256)

    # 各尺寸对照表（自检用）
    order = sorted(frames, key=lambda t: t[0])
    sheet = Image.new('RGBA', (sum(s for s, _ in order) + 12 * (len(order) + 1), 300),
                      (250, 250, 252, 255))
    x = 12
    for s, t in order:
        sheet.alpha_composite(t, (x, 250 - s))
        x += s + 12
    sheet_path = os.path.join(ASSETS, 'sleqn_icon_sheet.png')
    sheet.save(sheet_path)

    os.remove(m_big)
    os.remove(m_small)

    with Image.open(ico) as chk:
        got = sorted(s[0] for s in chk.info.get('sizes', []))
    print(f'  图标: {os.path.relpath(ico, ROOT)}  '
          f'({os.path.getsize(ico) / 1024:.1f} kB, 尺寸 {got})')
    print(f'  预览: {os.path.relpath(png256, ROOT)}')
    print(f'  对照: {os.path.relpath(sheet_path, ROOT)}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
