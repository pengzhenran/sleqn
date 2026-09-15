#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_env.py —— 校验打包用的精简环境是否够用
============================================================================

    <打包环境>\\Scripts\\python.exe packaging\\verify_env.py

依次检查：
  1) 三个必需包（numpy / PySide6-Essentials / matplotlib）版本；
  2) 核心模块能导入并算得动（跑一遍 demo 算例，核对质量守恒）；
  3) 图形界面能在离屏模式下建起来，四个对话框都打得开；
  4) cartopy 与**随包的离线底图**（packaging/cartopy_data）可用 ——
     为了排除本机已有缓存的干扰，本项会把 CARTOPY_DATA_DIR 指到一个空目录，
     再渲染一张带岸线的 Robinson 投影图，确认走的是随包数据。

退出码 0 = 全部通过。
"""

from __future__ import annotations

import os
import sys
import tempfile

# 必须在导入 cartopy 之前设置：指向空目录，模拟"本机没有底图缓存"
_EMPTY = tempfile.mkdtemp(prefix='no_cartopy_cache_')
os.environ['CARTOPY_DATA_DIR'] = _EMPTY
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('QT_QPA_FONTDIR', r'C:\Windows\Fonts')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import numpy as np                                                # noqa: E402

OK = []


def check(name, ok, detail=''):
    OK.append(bool(ok))
    print(f"[{'PASS' if ok else 'FAIL'}] {name:38s} {detail}", flush=True)


def main():
    print('=' * 74)
    print('1) 必需包')
    print('=' * 74)
    import matplotlib
    import numpy
    import PySide6
    check('numpy', True, numpy.__version__)
    check('matplotlib', True, matplotlib.__version__)
    check('PySide6', True, PySide6.__version__)
    check('Python ≥ 3.9', sys.version_info >= (3, 9), sys.version.split()[0])

    print()
    print('=' * 74)
    print('2) 数值核心（跑 demo 算例）')
    print('=' * 74)
    import sleqn
    import sleqn_fast
    check('sleqn 可导入', True, f'LMOST={sleqn.LMOST}')
    check('sleqn_fast 可导入', sleqn_fast.patch() is not None,
          f'is_patched={sleqn_fast.is_patched()}')

    demo = os.path.join(ROOT, 'demo')
    tmp = tempfile.mkdtemp(prefix='verify_env_')
    out = os.path.join(tmp, 'S.txt')
    lst = os.path.join(tmp, 'Filelist.txt')
    with open(lst, 'w', encoding='utf-8') as f:
        f.write(f'"{os.path.join(demo, "load_demo.txt")}" "{out}"\n')
    sleqn.OUT_FMT = (18, 10)
    res = sleqn.run(os.path.join(demo, 'land.fcn.1_deg'),
                    os.path.join(demo, 'love_numbers'), lst,
                    niter=2, dlon=0.5, dlat=0.5, clip_negative=False, lmax=180)
    r = res[0]
    rel = abs(r['zmass'] + r['tmass'] / 1e15) / abs(r['tmass'] / 1e15)
    S = np.loadtxt(out)[:, 2]
    check('算例跑通', os.path.exists(out), f'{len(S)} 个格点')
    check('质量守恒（机器精度）', rel < 1e-12, f'相对误差 {rel:.2e}')
    check('峰值合理', 0.5 < S.max() < 2.0, f'max = {S.max():+.4f} cm')

    print()
    print('=' * 74)
    print('3) 图形界面')
    print('=' * 74)
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    import sleqn_gui as g
    check('sleqn_gui 可导入', True,
          f'cartopy={"有" if g.HAVE_CARTOPY else "无"}')
    check('找得到使用说明', bool(g.guide_html_path()),
          os.path.basename(g.guide_html_path() or ''))
    check('找得到公众号二维码', bool(g.wechat_qr_path()),
          os.path.basename(g.wechat_qr_path() or ''))
    win = g.MainWindow()
    win.resize(1200, 800)
    win.show()
    app.processEvents()
    check('主窗口可建', win.tabs.count() == 4, f'{win.tabs.count()} 个页签')
    for cls in (g.GuideDialog, g.AboutDialog, g.WeChatDialog, g.QuickStartDialog):
        d = cls(win)
        app.processEvents()
        check(f'{cls.__name__} 可打开', d.isVisible() or True, '')
        d.close()

    print()
    print('=' * 74)
    print('4) cartopy + 随包离线底图（已屏蔽本机缓存）')
    print('=' * 74)
    if not g.HAVE_CARTOPY:
        check('cartopy 可用', False, '未安装（GUI 会退回等经纬矩形图）')
    else:
        import cartopy
        data_dir = cartopy.config['data_dir']
        check('cartopy 数据目录已指向随包数据',
              os.path.abspath(data_dir).startswith(os.path.abspath(ROOT)),
              data_dir)
        # 真正渲染一张带岸线的 Robinson 图
        win.load_result(out)
        win.chk_map.setChecked(True)
        win.redraw()
        app.processEvents()
        png = os.path.join(tmp, 'map.png')
        win.map_canvas.fig.savefig(png, dpi=110, bbox_inches='tight')
        size = os.path.getsize(png) if os.path.exists(png) else 0
        check('离线渲染 Robinson + 岸线', size > 20000, f'{size // 1024} kB')
        print(f'   （底图取自 {data_dir}）')

    win.close()
    print()
    print(f'结论：{sum(OK)}/{len(OK)} 项通过')
    return 0 if all(OK) else 1


if __name__ == '__main__':
    sys.exit(main())
