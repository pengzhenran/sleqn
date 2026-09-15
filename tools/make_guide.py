#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_guide.py —— 生成《使用说明》里的高清界面配图
============================================================================

在**离屏**模式下真实启动图形界面、真实跑一遍 grace_example 算例，然后把各个
页签、参数面板和对话框抓成 PNG，输出到 ``docs/使用说明_img/``。

高清是怎么来的
--------------
* 离屏平台本身不带字体，中文会变成方框（tofu）。这里显式指定
  ``QT_QPA_FONTDIR=C:\\Windows\\Fonts`` 并把应用字体设为「Microsoft YaHei UI」。
* ``QT_SCALE_FACTOR`` 在 ``QApplication`` 构造**之前**设置，窗口按逻辑尺寸布局、
  按 devicePixelRatio 出图，于是 ``widget.grab()`` 得到的是 2~3 倍的像素图
  （例：窗口 1500×920 → 图片 3000×1840）。缩放因子必须在建 QApplication 前定死，
  所以「整窗图」和「面板特写（要更大的倍数）」分两次进程跑。

    python tools/make_guide.py                    # 整窗 + 面板 + 对话框，全部
    python tools/make_guide.py --only window      # 只抓整窗与各页签
    python tools/make_guide.py --only panels --scale 3
    python tools/make_guide.py --only dialogs

抓图过程不会改动任何原始文件：算例结果写进临时目录；如果目标输出文件已存在，
抓完会原样还原。
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
import time

# ---------------------------------------------------------------- 环境（必须在 Qt 之前）
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('QT_QPA_FONTDIR', r'C:\Windows\Fonts')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import numpy as np                                              # noqa: E402
from PySide6.QtGui import QFont                                 # noqa: E402
from PySide6.QtWidgets import QApplication, QGroupBox, QDialog   # noqa: E402

RESULTS = []


def check(name, ok, detail=''):
    RESULTS.append(bool(ok))
    print(f"[{'PASS' if ok else 'FAIL'}] {name:44s} {detail}", flush=True)


def main():
    ap = argparse.ArgumentParser(description='生成使用说明的高清界面配图')
    ap.add_argument('--only', default='all',
                    choices=['all', 'window', 'panels', 'dialogs'])
    ap.add_argument('--scale', type=float, default=2.0,
                    help='QT_SCALE_FACTOR，整窗用 2，面板特写建议 3')
    ap.add_argument('--out', default=os.path.join(ROOT, 'docs', '使用说明_img'))
    ap.add_argument('--width', type=int, default=1500)
    ap.add_argument('--height', type=int, default=920)
    args = ap.parse_args()

    os.environ['QT_SCALE_FACTOR'] = str(args.scale)
    os.makedirs(args.out, exist_ok=True)

    app = QApplication.instance() or QApplication([])
    app.setFont(QFont('Microsoft YaHei UI', 10))

    import sleqn_gui                                            # noqa: E402
    from sleqn_gui import (MainWindow, AboutDialog, WeChatDialog,
                           QuickStartDialog, GuideDialog)

    def shot(widget, name):
        app.processEvents()
        p = os.path.join(args.out, name)
        pix = widget.grab()
        pix.save(p, 'PNG')
        check(f'抓图 {name}', os.path.exists(p) and os.path.getsize(p) > 5000,
              f'{pix.width()}x{pix.height()} px, dpr={pix.devicePixelRatio()}, '
              f'{os.path.getsize(p) / 1024:.0f} kB')
        return p

    def wait(worker, timeout=900.0):
        t0 = time.time()
        while worker is not None and worker.isRunning() and time.time() - t0 < timeout:
            app.processEvents()
            time.sleep(0.01)
        app.processEvents()

    # ---------------------------------------------------------------- 准备窗口
    win = MainWindow()
    win.resize(args.width, args.height)
    win.show()
    app.processEvents()

    # 载入真实 GRACE 示例；输出文件先备份，抓完（无论成败）一律还原。
    # 注意：这个同步盘上 shutil.move 不保留时间戳，所以另外 utime 还原 mtime。
    out_default = os.path.join(ROOT, 'grace_example', 'slf_gui.txt')
    backup = ''
    st = None
    if os.path.exists(out_default):
        backup = out_default + '.guidebak'
        st = os.stat(out_default)
        shutil.copy2(out_default, backup)

    win._load_demo_paths(quiet=False)
    win.sp_niter.setValue(2)
    win.sp_dlon.setValue(1.0)
    win.sp_dlat.setValue(1.0)
    win.sp_lmax.setValue(180)
    win.chk_negative.setChecked(True)
    win.chk_fast.setChecked(True)
    win.cb_fmt.setCurrentIndex(0)                # e24.16：界面默认格式
    app.processEvents()

    do_window = args.only in ('all', 'window')
    do_panels = args.only in ('all', 'panels')
    do_dialogs = args.only in ('all', 'dialogs')

    try:
        if do_window:
            print('-- 运行 grace_example 算例（lmax=180, niter=2, 1° 网格）…',
                  flush=True)
            t0 = time.time()
            win.on_run()
            wait(win.thread)
            check('GUI 计算完成', win.S is not None, f'{time.time() - t0:.1f} s')
            win.log('说明：本图为程序真实运行结果。')
            app.processEvents()

            print('-- 整窗与各页签 --', flush=True)
            for idx, name in ((0, 'gui_01_overview.png'),
                              (1, 'gui_02_profile.png'),
                              (2, 'gui_03_stats.png'),
                              (3, 'gui_04_log.png')):
                win.tabs.setCurrentIndex(idx)
                app.processEvents()
                time.sleep(0.4)
                shot(win, name)
            win.tabs.setCurrentIndex(0)

        if do_panels:
            print('-- 左侧面板特写 --', flush=True)
            groups = {g.title(): g for g in win.findChildren(QGroupBox)}
            for title, name in (('① 输入文件', 'panel_input.png'),
                                ('② 计算参数', 'panel_params.png'),
                                ('③ 输出', 'panel_output.png')):
                g = groups.get(title)
                if g is None:
                    check(f'面板 {title}', False, '未找到该分组框')
                    continue
                shot(g, name)

        if do_dialogs:
            print('-- 对话框 --', flush=True)
            for cls, name in ((AboutDialog, 'dlg_about.png'),
                              (WeChatDialog, 'dlg_wechat.png'),
                              (QuickStartDialog, 'dlg_quickstart.png'),
                              (GuideDialog, 'dlg_guide.png')):
                d = cls(win)
                d.show()
                app.processEvents()
                time.sleep(0.3)
                shot(d, name)
                d.close()
    finally:
        try:
            win.close()
        except Exception:                                       # noqa: BLE001
            pass
        if backup and os.path.exists(backup):
            # 用 copy2 + 删除，而不是 shutil.move：在本仓库所在的同步盘上，
            # move 会先尝试 rename（目标已存在 → WinError 183），再退回
            # copy2 + 删源；若此刻有进程（网盘/杀毒）正占着目标文件，就会抛
            # PermissionError 而把备份留在原地。copy2 覆盖目标更稳。
            try:
                shutil.copy2(backup, out_default)
                os.remove(backup)
                if st is not None:
                    os.utime(out_default, (st.st_atime, st.st_mtime))
                print(f'-- 已还原 {os.path.relpath(out_default, ROOT)}', flush=True)
            except OSError as exc:                              # noqa: PERF203
                print(f'!! 还原 {os.path.relpath(out_default, ROOT)} 失败：{exc}\n'
                      f'   备份仍在 {os.path.relpath(backup, ROOT)}，'
                      f'请手动改回后再删除该备份。', flush=True)
                RESULTS.append(False)

    npass = sum(RESULTS)
    print(f'\n{npass}/{len(RESULTS)} 张图抓取成功 → {args.out}', flush=True)
    # 离屏 Qt 在解释器退出阶段偶发崩溃（会跳过 finally），所以这里主动收尾：
    # 备份已在上面的 finally 里还原，直接用 os._exit 结束进程最稳。
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0 if npass == len(RESULTS) else 1)


if __name__ == '__main__':
    sys.exit(main())
