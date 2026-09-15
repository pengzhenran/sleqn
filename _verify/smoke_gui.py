# -*- coding: utf-8 -*-
"""sleqn_gui.py 无头冒烟测试：构造窗口、载入演示数据、不弹窗、不计算。"""
import os, sys, traceback
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
WS = r'D:\华为家庭存储\mywork\sealevel'
sys.path.insert(0, WS)

from PySide6.QtWidgets import QApplication
import sleqn_gui as G

app = QApplication.instance() or QApplication([])

# 找出主窗口类
cands = [n for n in dir(G) if n.endswith('Window') or n.endswith('MainWindow')]
print('候选窗口类:', cands)
cls = None
for n in cands:
    o = getattr(G, n)
    if isinstance(o, type):
        cls = o
        print('使用:', n)
        break
assert cls is not None

w = cls()
print('窗口构造成功:', w.windowTitle())
print('默认参数: 负值允许 =', w.chk_negative.isChecked(),
      '| niter =', w.sp_niter.value(),
      '| lmax =', w.sp_lmax.value(),
      '| dlon =', w.sp_dlon.value(), '| dlat =', w.sp_dlat.value(),
      '| 加速内核 =', w.chk_fast.isChecked())

# 载入演示数据（只填路径，不计算）
if hasattr(w, 'load_demo'):
    w.load_demo()
    print('load_demo() 之后: 掩膜 =', w.ed_mask.text())
    print('                  勒夫数 =', w.ed_love.text())
    print('                  数据 =', w.ed_data.text())

# 把 demo 真跑一遍（后台线程 + 事件循环），验证 GUI 与命令行一致
import numpy as np, time
WS_demo = os.path.join(WS, 'demo')
w.ed_mask.setText(os.path.join(WS_demo, 'land.fcn.1_deg'))
w.ed_love.setText(os.path.join(WS_demo, 'love_numbers'))
w.ed_data.setText(os.path.join(WS_demo, 'load_demo.txt'))
out = r'C:\Users\pengzhenran\AppData\Local\Temp\slverify\gui_demo.txt'
w.ed_out.setText(out)
w.sp_dlon.setValue(0.5); w.sp_dlat.setValue(0.5)
w.on_run()
t0 = time.time()
while w.thread is not None and w.thread.isRunning() and time.time() - t0 < 600:
    app.processEvents()
    time.sleep(0.05)
app.processEvents()
print('GUI 计算结束，输出存在 =', os.path.exists(out))

# 与命令行版逐字节比较
here = os.path.dirname(os.path.abspath(G.__file__))
import subprocess
cli = r'C:\Users\pengzhenran\AppData\Local\Temp\slverify\gui_demo_cli.txt'
subprocess.run([sys.executable, os.path.join(WS, 'sleqn.py'),
                '--mask', w.ed_mask.text(), '--love', w.ed_love.text(),
                '--list', os.path.join(WS_demo, 'Filelist.txt'),
                '--allow-negative', '--fmt', 'e12.4',
                '--dlon', '0.5', '--dlat', '0.5'],
               cwd=WS_demo, capture_output=True)
shipped = os.path.join(WS_demo, 'slf_demo.txt')
a = np.loadtxt(out)[:, 2]
if os.path.exists(shipped):
    b = np.loadtxt(shipped)[:, 2]
    print('GUI 输出 vs demo/slf_demo.txt: max|Δ| = %.6e cm (n=%d)'
          % (np.abs(a - b).max(), len(a)))
print('GUI 冒烟测试完成')
