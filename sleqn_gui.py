#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sleqn_gui.py —— 海平面指纹（SLF）计算程序 · PySide6 图形界面
=============================================================

把已验证的数值核心（``sleqn.py``，与修正版 Fortran ``sleqn_dp.f90`` 逐字节一致）
包成桌面程序：选文件 → 设参数 → 后台计算（带进度、可取消）→ 出图与统计。

功能
----
* 输入：海陆掩膜 / 负荷勒夫数 / 质量变化数据（三列网格文件）
* 参数：迭代次数 niter、载荷网格间隔 dlon/dlat、截断阶数 lmax、
        极移（polar motion）反馈开关、数值内核、输出数值格式
* 计算：在后台线程调用 ``sleqn.run()``，实时进度与日志，可随时取消
* 结果：全球海平面指纹图（等经纬 / Robinson 投影，可选海岸线）、
        经向/纬向剖面、统计与质量守恒自检、前若干行数据预览
* 其它：保存图片（PNG/PDF）、另存结果文件、直接打开已有结果文件查看、
        一键载入演示数据

运行
----
    python sleqn_gui.py
（本机建议用 pzr 环境：C:\\Users\\<用户>\\anaconda3\\envs\\pzr\\python.exe sleqn_gui.py）
"""

from __future__ import annotations

import os
import re
import shutil
import sys
import time
import traceback

import numpy as np

# ---------------------------------------------------------------- Qt
from PySide6.QtCore import Qt, QThread, Signal, QUrl, QStandardPaths, QTimer
from PySide6.QtGui import (QAction, QDesktopServices, QIcon, QKeySequence,
                           QPixmap, QFont)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QSplitter, QTabWidget, QGroupBox,
    QFormLayout, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit,
    QPushButton, QToolButton, QFileDialog, QSpinBox, QDoubleSpinBox, QComboBox,
    QCheckBox, QProgressBar, QPlainTextEdit, QTableWidget, QTableWidgetItem,
    QMessageBox, QStatusBar, QHeaderView, QSizePolicy, QFrame,
    QDialog, QDialogButtonBox, QScrollArea, QTextBrowser,
    QListWidget, QListWidgetItem)

# ---------------------------------------------------------------- matplotlib
import matplotlib
matplotlib.use('QtAgg')
matplotlib.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']
matplotlib.rcParams['axes.unicode_minus'] = False
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from matplotlib.colors import SymLogNorm

# ---------------------------------------------------------------- 数值核心
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sleqn  # noqa: E402
import guide_render  # noqa: E402  （说明书转 Qt 富文本，见该模块说明）

try:                                                  # 加速内核（可选）
    import sleqn_fast  # noqa: E402
    HAVE_FAST = True
except Exception:                                     # pragma: no cover
    sleqn_fast = None
    HAVE_FAST = False

try:
    import cartopy
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature
    HAVE_CARTOPY = True
    # 离线底图：随包的 Natural Earth 110m 岸线（packaging/cartopy_data，约 0.8 MB）。
    # 找到就把 cartopy 的数据目录指过去，否则 cartopy 会去网上取底图，
    # 在不能联网的机器上会失败（GUI 里会退回等经纬矩形图）。
    for _rel in (os.path.join('packaging', 'cartopy_data'), 'cartopy_data'):
        _cd = os.path.join(os.path.dirname(os.path.abspath(__file__)), _rel)
        if os.path.isdir(os.path.join(_cd, 'shapefiles')):
            cartopy.config['data_dir'] = _cd
            break
except Exception:                                     # pragma: no cover
    ccrs = None
    cfeature = None
    HAVE_CARTOPY = False

APP_TITLE = '海平面指纹（SLF）计算程序'
APP_NAME_EN = 'Sea Level Fingerprint Toolkit'
VERSION = '1.0.1'
HERE = os.path.dirname(os.path.abspath(__file__))

# ============================================================ 作者 / 身份信息
# 「关于」对话框与 HTML 使用说明共用这一份，改这里即可全站同步。
AUTHOR_NAME_CN = '彭桢燃'
AUTHOR_NAME_EN = 'Zhenran Peng'
AUTHOR_AFFILIATION_CN = '中国地质大学（武汉）'
AUTHOR_AFFILIATION_EN = 'China University of Geosciences (Wuhan)'
AUTHOR_EMAIL = 'zhenran.peng@cug.edu.cn'
AUTHOR_PHONE = '15927402265'

WECHAT_ACCOUNT = '地球重力与人类生活'
WECHAT_ACCOUNT_EN = 'TVGG'
WECHAT_QR_FILENAME = '地球重力与人类生活TVGG.jpg'
WECHAT_QR_CAPTION = f'课题组公众号：{WECHAT_ACCOUNT}（{WECHAT_ACCOUNT_EN}）'

# 随包文档：docs/使用说明.html（截图版说明书，含高清配图）
DOCS_DIRNAME = 'docs'
GUIDE_HTML_NAME = '使用说明.html'

# 参考文献（中文在前、英文在后；使用者引用本程序时请一并引用）
CITATION_ZH_HTML = (
    '王林松, 陈超, 马险, 杜劲松. 冰盖消融的海平面指纹变化及其对 GRACE '
    '监测结果的影响[J]. <i>地球物理学报</i>, 2018, 61(7): 2679–2690. '
    '<a href="https://doi.org/10.6038/cjg2018L0335">doi:10.6038/cjg2018L0335</a>')
CITATION_EN_HTML = (
    'Sun J. W., Wang L. S., Peng Z. R., Fu Z. Y., Chen C (2022). '
    'The sea level fingerprints of global terrestrial water storage changes '
    'detected by GRACE and GRACE-FO data. <i>Pure and Applied Geophysics</i>, '
    '179(9), 3303–3317. <a href="https://doi.org/10.1007/s00024-022-03099-5">'
    'doi:10.1007/s00024-022-03099-5</a>')
PAPER_CITATION_HTML = (f'[1] {CITATION_ZH_HTML}<br>[2] {CITATION_EN_HTML}')


def _first_existing(*rel_paths):
    """返回第一个存在的文件路径（相对本文件所在目录），都没有则返回空串。"""
    for rel in rel_paths:
        p = rel if os.path.isabs(rel) else os.path.join(HERE, rel)
        if os.path.exists(p):
            return p
    return ''


def wechat_qr_path():
    """课题组公众号二维码图片路径（放在 assets/ 或 docs/使用说明_img/ 均可）。"""
    return _first_existing(os.path.join('assets', WECHAT_QR_FILENAME),
                           os.path.join(DOCS_DIRNAME, '使用说明_img',
                                        WECHAT_QR_FILENAME),
                           WECHAT_QR_FILENAME)


def guide_html_path():
    """截图版使用说明 HTML 的路径。"""
    return _first_existing(os.path.join(DOCS_DIRNAME, GUIDE_HTML_NAME),
                           GUIDE_HTML_NAME)


def _writable_dir(preferred):
    """优先用 ``preferred``；不可写（例如程序装在 Program Files 下）就退到
    「文档\\海平面指纹」。

    装到 Program Files 后普通用户对安装目录没有写权限，而界面里"载入演示数据"
    默认会把结果写到示例数据旁边；这里先探一下可写性，免得用户一点开始计算就报错。
    """
    try:
        os.makedirs(preferred, exist_ok=True)
        probe = os.path.join(preferred, '.write_test')
        with open(probe, 'w'):
            pass
        os.remove(probe)
        return preferred
    except Exception:                                          # noqa: BLE001
        doc = (QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation)
               or os.path.expanduser('~'))
        d = os.path.join(doc, '海平面指纹')
        os.makedirs(d, exist_ok=True)
        return d


def app_icon_path():
    """程序图标（.ico 优先，退回 256 px PNG）。由 tools/make_icon.py 生成。"""
    return _first_existing(os.path.join('assets', 'sleqn.ico'),
                           os.path.join('assets', 'sleqn_256.png'),
                           'sleqn.ico')


class Cancelled(Exception):
    """用户在 GUI 里点了取消。"""


# ============================================================================
# 结果文件读取 / 网格整理
# ============================================================================
def read_result(path):
    """读取三列结果文件 ``经度 纬度 值``，返回 (S, rlon, rlat)。

    行序按程序约定为「经度外层、纬度内层」，这里从数据本身推断网格尺寸，
    因此对任意 nphi×nth 的结果文件都适用。
    """
    d = np.loadtxt(path)
    if d.ndim == 1:
        d = d[None, :]
    if d.shape[0] < 2:
        raise ValueError('结果文件行数太少')
    lat0 = d[0, 1]
    same = np.where(np.abs(d[:, 1] - lat0) < 1e-9)[0]
    nth = int(same[1]) if len(same) > 1 else len(d)
    if len(d) % nth:
        raise ValueError(f'结果文件行数 {len(d)} 不是纬度格点数 {nth} 的整数倍')
    nphi = len(d) // nth
    rlon = d[::nth, 0].copy()
    rlat = d[:nth, 1].copy()
    S = d[:, 2].reshape(nphi, nth)
    return S, rlon, rlat


def edges_from_centers(c):
    """由格点中心求网格边界（首末各外推半个格距）。"""
    c = np.asarray(c, dtype=float)
    if len(c) == 1:
        return np.array([c[0] - 0.5, c[0] + 0.5])
    d = c[1] - c[0]
    return np.concatenate([[c[0] - d / 2.0], c + d / 2.0])


def prepare_grid(S, rlon, rlat):
    """统一成「纬度降序」的绘图网格：返回 (S2, lon_edges, lat_edges)。

    程序输出的数据第 0 行是最北的纬度带；若打开的结果文件纬度是升序，
    这里自动翻转，保证地图不会上下颠倒（这是本项目踩过的坑）。
    """
    lon_e = edges_from_centers(rlon)
    if rlat[0] < rlat[-1]:                       # 升序 → 翻转
        S = S[:, ::-1]
        rlat = rlat[::-1]
    lat_e = edges_from_centers(rlat)
    return S, lon_e, lat_e


# ============================================================================
# 后台计算线程
# ============================================================================
class ComputeThread(QThread):
    """在后台线程里跑 sleqn.run()，期间把进度/日志通过信号发回主线程。"""

    sig_progress = Signal(int, str)        # 百分比, 说明
    sig_log = Signal(str)
    sig_done = Signal(dict)
    sig_failed = Signal(str)

    def __init__(self, mask, love, data, out, niter, dlon, dlat, fmt,
                 allow_negative=True, lmax=None, use_fast=True, polar=True):
        super().__init__()
        self.args = (mask, love, data, out, niter, dlon, dlat, fmt,
                     allow_negative, lmax, use_fast, polar)
        self._cancel = False

    def cancel(self):
        self._cancel = True

    # -- stdout 重定向：把 sleqn 里的 print 变成日志信号
    class _Stream:
        def __init__(self, sig):
            self.sig = sig
            self.buf = ''

        def write(self, s):
            self.buf += s
            while '\n' in self.buf:
                line, self.buf = self.buf.split('\n', 1)
                if line.strip():
                    self.sig.emit(line.rstrip())
            return len(s)

        def flush(self):
            if self.buf.strip():
                self.sig.emit(self.buf.rstrip())
            self.buf = ''

    def run(self):
        (mask, love, data, out, niter, dlon, dlat, fmt, allow_neg,
         lmax, use_fast, polar) = self.args
        t0 = time.time()
        old_stdout = sys.stdout
        sys.stdout = ComputeThread._Stream(self.sig_log)

        def progress(frac, msg):
            if self._cancel:
                raise Cancelled('用户取消了计算')
            self.sig_progress.emit(int(max(0.0, min(1.0, frac)) * 100), msg)

        try:
            # 输出格式（sleqn 的模块级设置）
            w, d = fmt.lower().lstrip('e').split('.')
            sleqn.OUT_FMT = (int(w), int(d))

            # 截断阶数 + 数值内核（都在 sleqn 模块级生效，本线程独占计算）
            if lmax is not None:
                sleqn.set_lmax(lmax)
            if use_fast:
                if HAVE_FAST:
                    sleqn_fast.patch()
                    self.sig_log.emit(
                        f'[内核] 加速内核 sleqn_fast（lmax={sleqn.LMOST}，'
                        f'结果与原内核逐位相同）')
                else:
                    self.sig_log.emit('[内核] 未找到 sleqn_fast.py，改用原内核')
            else:
                if HAVE_FAST:
                    sleqn_fast.unpatch()
                self.sig_log.emit(f'[内核] 原内核（lmax={sleqn.LMOST}）')

            # 用临时 Filelist 复用 sleqn.run 的完整流程
            import tempfile
            tmpdir = tempfile.mkdtemp(prefix='sleqn_gui_')
            flist = os.path.join(tmpdir, 'Filelist.txt')
            with open(flist, 'w', encoding='utf-8') as f:
                # 路径必须加引号：程序可能装在 "C:\Program Files\..." 下，
                # 控制文件是按行读、按空白切分的，不引起来路径会被空格截断。
                f.write(f'"{os.path.abspath(data)}" "{os.path.abspath(out)}"\n')

            res = sleqn.run(mask, love, flist, niter, dlon=dlon, dlat=dlat,
                            clip_negative=not allow_neg, progress=progress,
                            lmax=sleqn.LMOST, polar=polar)
            r = res[0] if res else {}
            r['elapsed'] = time.time() - t0
            r['out'] = os.path.abspath(out)
            self.sig_done.emit(r)
        except Cancelled as e:
            self.sig_log.emit(f'已取消：{e}')
            self.sig_failed.emit('CANCELLED')
        except Exception:
            self.sig_failed.emit(traceback.format_exc())
        finally:
            sys.stdout = old_stdout


# ============================================================================
# 绘图部件
# ============================================================================
class MapCanvas(FigureCanvasQTAgg):
    """结果图 / 剖面图通用画布（含 matplotlib 导航工具栏）。"""

    def __init__(self, parent=None):
        self.fig = Figure(figsize=(7.4, 5.0), dpi=100, constrained_layout=True)
        super().__init__(self.fig)
        self.setParent(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.ax = None

    def clear_axes(self):
        self.fig.clear()
        self.ax = None

    def draw_empty(self, text='请先计算或打开结果文件'):
        self.fig.clear()
        ax = self.fig.add_subplot(111)
        ax.text(0.5, 0.5, text, ha='center', va='center', fontsize=12,
                color='#888')
        ax.axis('off')
        self.draw()


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f'{APP_TITLE}  v{VERSION}')
        self.resize(1360, 860)
        _icon = app_icon_path()
        if _icon:
            self.setWindowIcon(QIcon(_icon))     # 子对话框会自动继承
        self.S = None            # (nphi, nth) 海平面指纹
        self.rlon = None
        self.rlat = None
        self.thread = None
        self.last_stats = {}
        self._build_ui()
        self._load_demo_paths(quiet=True)

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        splitter = QSplitter(Qt.Horizontal)

        # ---------------- 左侧：参数 ----------------
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(10, 10, 10, 10)
        lv.setSpacing(10)

        g_in = QGroupBox('① 输入文件')
        f_in = QFormLayout(g_in)
        self.ed_mask = self._file_row(f_in, '海陆掩膜', 'land.fcn.1_deg',
                                      '每行「经度 纬度 value」，value=1 陆地、0 海洋')
        self.ed_love = self._file_row(f_in, '负荷勒夫数', 'love_numbers',
                                      '前 2 行表头，其后每行「l h_l k_l 保留列」，'
                                      '行数应不少于 lmax+1')
        self.ed_data = self._file_row(f_in, '质量变化数据', 'load_demo.txt',
                                      '每行「经度 纬度 水当量高度(m)」')

        g_p = QGroupBox('② 计算参数')
        f_p = QFormLayout(g_p)
        self.sp_niter = QSpinBox()
        self.sp_niter.setRange(0, 20)
        self.sp_niter.setValue(2)
        self.sp_niter.setToolTip('迭代次数；0 表示把水均匀铺在一层海面上（不做自吸引/负荷迭代）')
        f_p.addRow('迭代次数 niter', self.sp_niter)
        self.sp_dlon = QDoubleSpinBox()
        self.sp_dlon.setRange(0.01, 10.0)
        self.sp_dlon.setDecimals(3)
        self.sp_dlon.setSingleStep(0.25)
        self.sp_dlon.setValue(0.5)
        self.sp_dlon.setToolTip('载荷数据网格的经度间隔（度），必须与实际数据一致，否则单元面积算错')
        f_p.addRow('载荷网格间隔 dlon', self.sp_dlon)

        self.sp_dlat = QDoubleSpinBox()
        self.sp_dlat.setRange(0.01, 10.0)
        self.sp_dlat.setDecimals(3)
        self.sp_dlat.setSingleStep(0.25)
        self.sp_dlat.setValue(0.5)
        f_p.addRow('载荷网格间隔 dlat', self.sp_dlat)

        self.sp_lmax = QSpinBox()
        self.sp_lmax.setRange(sleqn.LMAX_MIN, 4000)
        self.sp_lmax.setValue(sleqn.DEF_LMOST)
        self.sp_lmax.setSingleStep(10)
        self.sp_lmax.setToolTip(
            f'球谐截断阶数（原文 Fortran 固定为 {sleqn.DEF_LMOST}）。\n'
            '• 需要 love_numbers 至少到该阶（不足时高阶层会按 0 处理，结果失真）；\n'
            '• 载荷/输出网格为 360×180（1°），只能分辨到约 180 阶，再大只是数学截断；\n'
            '• 调小可用于低频分析或与低阶模型对照；\n'
            '• 预计算的勒让德函数内存约 8×(lmax+1)²×180 字节。')
        f_p.addRow('截断阶数 lmax', self.sp_lmax)

        self.chk_polar = QCheckBox('含极移（Polar motion）反馈')
        self.chk_polar.setChecked(True)
        self.chk_polar.setToolTip(
            '极移（自转）反馈：质量重分布改变地球惯性张量 → 自转轴漂移 → 离心位变化，\n'
            '该扰动只含球谐 (l=2, m=1)（Kendall et al. 2005；Tamisiea et al. 2010 式 11）。\n'
            '• 勾选（默认）：与修正版 Fortran sleqn_dp.f90、gravity-toolkit（POLAR=True）一致；\n'
            '• 取消勾选：求解不含该反馈的经典海平面方程，该 (2,1) 项改用普通系数，\n'
            '  可用于敏感性分析或与不含极移反馈的模型对照。\n'
            '影响量级：本算例全场约 1e-3 cm（场峰值的千分之几），差异集中在 (2,1) 项。')
        f_p.addRow('极移反馈', self.chk_polar)

        self.chk_fast = QCheckBox('使用加速内核（结果与原内核逐位相同）')
        self.chk_fast.setChecked(HAVE_FAST)
        self.chk_fast.setEnabled(HAVE_FAST)
        self.chk_fast.setToolTip(
            'sleqn_fast 把 gdisc/martin 的 Python 逐单元循环向量化，'
            '并缓存勒让德递推因子。\n'
            '实测 grace_example（1°、64800 单元、niter=2）：约 190 s → 19 s，'
            '输出文件逐字节相同。\n'
            '取消勾选可切回原内核做对照。')
        f_p.addRow('数值内核', self.chk_fast)

        self.cb_fmt = QComboBox()
        # 默认最高精度（0.ddddddddddddddddE±ee，共 24 列）；后两项为兼容/对照用
        self.cb_fmt.addItems(['e24.16（最高精度，默认）', 'e18.10',
                              'e12.4（与 Fortran 输出格式一致）'])
        self.cb_fmt.setCurrentIndex(0)
        self.cb_fmt.setToolTip('结果文件的有效数字位数。最高精度便于后续做趋势/精度分析；'
                               'e12.4 与原文 Fortran 的输出格式完全一致')
        f_p.addRow('输出数值格式', self.cb_fmt)

        self.chk_negative = QCheckBox('允许负值载荷（GRACE 质量亏损）')
        self.chk_negative.setChecked(True)
        self.chk_negative.setToolTip('原文 Fortran 代码会把负的载荷清零（If(thick<0) thick=0）。'
                                     'GRACE 质量异常有正有负，用 GRACE 数据时必须勾选；'
                                     '若要与原文 Fortran 结果对照，请取消勾选')
        f_p.addRow('负值处理', self.chk_negative)

        g_o = QGroupBox('③ 输出')
        f_o = QFormLayout(g_o)
        self.ed_out = self._file_row(f_o, '结果文件', os.path.join('demo', 'slf_gui.txt'),
                                     '每行「经度 纬度 海平面变化(cm)」', save=True)

        self.btn_run = QPushButton('▶  开始计算')
        self.btn_run.setMinimumHeight(38)
        self.btn_run.setStyleSheet('font-weight:bold;')
        self.btn_run.clicked.connect(self.on_run)
        self.btn_cancel = QPushButton('取消')
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self.on_cancel)
        self.btn_open = QPushButton('📂  打开已有结果文件查看')
        self.btn_open.clicked.connect(self.on_open_result)
        self.btn_demo = QPushButton('载入演示数据（demo/）')
        self.btn_demo.clicked.connect(lambda: self._load_demo_paths(quiet=False))

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat('%p%')
        self.lb_stage = QLabel('就绪')
        self.lb_stage.setStyleSheet('color:#555;')

        lv.addWidget(g_in)
        lv.addWidget(g_p)
        lv.addWidget(g_o)
        lv.addWidget(self.btn_run)
        lv.addWidget(self.btn_cancel)
        lv.addWidget(self.progress)
        lv.addWidget(self.lb_stage)
        lv.addWidget(self.btn_open)
        lv.addWidget(self.btn_demo)
        lv.addStretch(1)
        left.setMinimumWidth(390)
        left.setMaximumWidth(560)

        # ---------------- 右侧：结果 ----------------
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_map_tab(), '海平面指纹图')
        self.tabs.addTab(self._build_profile_tab(), '剖面')
        self.tabs.addTab(self._build_stats_tab(), '统计与数据')
        self.tabs.addTab(self._build_log_tab(), '日志')

        splitter.addWidget(left)
        splitter.addWidget(self.tabs)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([420, 940])
        self.setCentralWidget(splitter)

        # 状态栏
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage('就绪。提示：先点「载入演示数据」再点「开始计算」即可看到效果。')

        # 菜单
        m = self.menuBar().addMenu('文件(&F)')
        a = QAction('打开结果文件…', self)
        a.setShortcut(QKeySequence.Open)
        a.triggered.connect(self.on_open_result)
        m.addAction(a)
        a = QAction('保存当前图片…', self)
        a.setShortcut(QKeySequence.Save)
        a.triggered.connect(self.on_save_fig)
        m.addAction(a)
        m.addSeparator()
        a = QAction('退出', self)
        a.triggered.connect(self.close)
        m.addAction(a)
        mh = self.menuBar().addMenu('帮助(&H)')
        a = QAction('📘  使用说明', self)
        a.setShortcut(QKeySequence('F1'))
        a.triggered.connect(self.on_guide)
        mh.addAction(a)
        a = QAction('🧭  快速上手', self)
        a.triggered.connect(self.on_quickstart)
        mh.addAction(a)
        mh.addSeparator()
        a = QAction('ℹ️  关于 / 作者信息', self)
        a.triggered.connect(self.on_about)
        mh.addAction(a)
        a = QAction('📱  课题组公众号', self)
        a.triggered.connect(self.on_wechat)
        mh.addAction(a)

    def _file_row(self, form, label, default, tip, save=False):
        """一行「标签 + 输入框 + 浏览按钮」。"""
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        ed = QLineEdit(default)
        ed.setToolTip(tip)
        ed.setMinimumWidth(210)
        btn = QToolButton()
        btn.setText('…')
        h.addWidget(ed, 1)
        h.addWidget(btn)

        def browse():
            if save:
                p, _ = QFileDialog.getSaveFileName(self, '选择输出文件',
                                                   ed.text() or HERE,
                                                   '文本文件 (*.txt);;所有文件 (*)')
            else:
                p, _ = QFileDialog.getOpenFileName(self, '选择文件',
                                                   os.path.dirname(ed.text()) or HERE,
                                                   '所有文件 (*);;文本文件 (*.txt)')
            if p:
                ed.setText(p)
        btn.clicked.connect(browse)
        form.addRow(label, w)
        return ed

    # ---------------- 地图页
    def _build_map_tab(self):
        page = QWidget()
        v = QVBoxLayout(page)
        bar = QHBoxLayout()
        bar.addWidget(QLabel('色标：'))
        self.cb_scale = QComboBox()
        self.cb_scale.addItems(['自适应（近场，对称 ±max）', '远场放大（±0.03 cm）',
                                '对称对数（symlog）'])
        self.cb_scale.currentIndexChanged.connect(self.redraw)
        bar.addWidget(self.cb_scale)
        bar.addWidget(QLabel('放大阈值：'))
        self.sp_vmax = QDoubleSpinBox()
        self.sp_vmax.setRange(0.0001, 1000.0)
        self.sp_vmax.setDecimals(4)
        self.sp_vmax.setValue(0.03)
        self.sp_vmax.setSingleStep(0.01)
        self.sp_vmax.valueChanged.connect(self.redraw)
        bar.addWidget(self.sp_vmax)
        self.cb_cmap = QComboBox()
        self.cb_cmap.addItems(['RdBu_r', 'coolwarm', 'viridis', 'jet'])
        self.cb_cmap.currentIndexChanged.connect(self.redraw)
        bar.addWidget(QLabel('色表：'))
        bar.addWidget(self.cb_cmap)
        self.chk_map = QCheckBox('地图投影 + 海岸线')
        self.chk_map.setChecked(HAVE_CARTOPY)
        self.chk_map.setEnabled(HAVE_CARTOPY)
        self.chk_map.setToolTip('使用 cartopy 的 Robinson 投影与海岸线（首次使用可能需联网下载底图）')
        self.chk_map.stateChanged.connect(self.redraw)
        bar.addWidget(self.chk_map)
        self.chk_grid = QCheckBox('经纬网')
        self.chk_grid.setChecked(True)
        self.chk_grid.stateChanged.connect(self.redraw)
        bar.addWidget(self.chk_grid)
        bar.addStretch(1)
        b = QPushButton('保存图片…')
        b.clicked.connect(self.on_save_fig)
        bar.addWidget(b)
        v.addLayout(bar)

        self.map_canvas = MapCanvas()
        self.map_canvas.draw_empty()
        v.addWidget(NavigationToolbar2QT(self.map_canvas, page))
        v.addWidget(self.map_canvas, 1)
        return page

    # ---------------- 剖面页
    def _build_profile_tab(self):
        page = QWidget()
        v = QVBoxLayout(page)
        bar = QHBoxLayout()
        bar.addWidget(QLabel('剖面方向：'))
        self.cb_pdir = QComboBox()
        self.cb_pdir.addItems(['沿经线（固定经度，横轴纬度）', '沿纬线（固定纬度，横轴经度）'])
        self.cb_pdir.currentIndexChanged.connect(self._reload_profile_axis)
        bar.addWidget(self.cb_pdir)
        bar.addWidget(QLabel('位置：'))
        self.cb_paxis = QComboBox()
        self.cb_paxis.currentIndexChanged.connect(self.redraw)
        self.cb_paxis.setMinimumWidth(130)
        bar.addWidget(self.cb_paxis)
        self.chk_eust = QCheckBox('标出均匀海面（eustatic）参考线')
        self.chk_eust.setChecked(True)
        self.chk_eust.stateChanged.connect(self.redraw)
        bar.addWidget(self.chk_eust)
        bar.addStretch(1)
        v.addLayout(bar)
        self.prof_canvas = MapCanvas()
        self.prof_canvas.draw_empty()
        v.addWidget(NavigationToolbar2QT(self.prof_canvas, page))
        v.addWidget(self.prof_canvas, 1)
        return page

    # ---------------- 统计页
    def _build_stats_tab(self):
        page = QWidget()
        v = QVBoxLayout(page)
        self.tbl = QTableWidget(0, 2)
        self.tbl.setHorizontalHeaderLabels(['项目', '数值'])
        self.tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.setMaximumHeight(330)
        v.addWidget(self.tbl)
        v.addWidget(QLabel('结果文件前 100 行预览：'))
        self.txt_preview = QPlainTextEdit()
        self.txt_preview.setReadOnly(True)
        self.txt_preview.setStyleSheet('font-family:Consolas,monospace; font-size:12px;')
        v.addWidget(self.txt_preview, 1)
        return page

    # ---------------- 日志页
    def _build_log_tab(self):
        page = QWidget()
        v = QVBoxLayout(page)
        self.txt_log = QPlainTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setStyleSheet('font-family:Consolas,monospace; font-size:12px;')
        v.addWidget(self.txt_log)
        h = QHBoxLayout()
        b = QPushButton('清空日志')
        b.clicked.connect(self.txt_log.clear)
        h.addWidget(b)
        b = QPushButton('复制到剪贴板')
        b.clicked.connect(lambda: QApplication.clipboard().setText(self.txt_log.toPlainText()))
        h.addWidget(b)
        h.addStretch(1)
        v.addLayout(h)
        return page

    # ------------------------------------------------------------------ 交互
    def log(self, msg):
        self.txt_log.appendPlainText(msg)

    def _load_demo_paths(self, quiet=False):
        """优先载入 grace_example/（真实 GRACE mascon + PREM 勒夫数），
        没有则退回 demo/（合成算例）。"""
        ge = os.path.join(HERE, 'grace_example')
        if os.path.exists(os.path.join(ge, 'land.fcn.1_deg')):
            self.ed_mask.setText(os.path.join(ge, 'land.fcn.1_deg'))
            self.ed_love.setText(os.path.join(ge, 'love_numbers'))
            cand = [f for f in sorted(os.listdir(ge))
                    if f.startswith('load_grace_') and f.endswith('.txt')]
            if cand:
                self.ed_data.setText(os.path.join(ge, cand[0]))
            self.ed_out.setText(os.path.join(_writable_dir(ge), 'slf_gui.txt'))
            self.sp_dlon.setValue(1.0)
            self.sp_dlat.setValue(1.0)
            self.sp_lmax.setValue(sleqn.DEF_LMOST)
            if not quiet:
                self.log('[数据] 已载入 grace_example/：真实 GRACE mascon + PREM 负荷勒夫数')
                self.status.showMessage('已载入 GRACE 示例数据（载荷网格 1°，dlon/dlat 已设为 1）')
            return
        d = os.path.join(HERE, 'demo')
        m = os.path.join(d, 'land.fcn.1_deg')
        if not os.path.exists(m):
            if not quiet:
                QMessageBox.information(self, '未找到演示数据',
                                        f'没有找到 {m}\n可先运行：python make_demo_data.py --out demo')
            return
        self.ed_mask.setText(m)
        self.ed_love.setText(os.path.join(d, 'love_numbers'))
        self.ed_data.setText(os.path.join(d, 'load_demo.txt'))
        self.ed_out.setText(os.path.join(_writable_dir(d), 'slf_gui.txt'))
        self.sp_dlon.setValue(0.5)
        self.sp_dlat.setValue(0.5)
        self.sp_lmax.setValue(sleqn.DEF_LMOST)
        if not quiet:
            self.log('[演示] 已载入 demo/ 下的合成算例（非真实观测数据）')
            self.status.showMessage('已载入演示数据')

    def on_run(self):
        if self.thread and self.thread.isRunning():
            return
        mask, love, data = self.ed_mask.text().strip(), self.ed_love.text().strip(), \
            self.ed_data.text().strip()
        out = self.ed_out.text().strip()
        for p, name in ((mask, '海陆掩膜'), (love, '负荷勒夫数'), (data, '质量变化数据')):
            if not os.path.exists(p):
                QMessageBox.critical(self, '文件不存在', f'{name} 文件不存在：\n{p}')
                return
        if not out:
            QMessageBox.critical(self, '缺少输出路径', '请指定结果文件路径。')
            return

        fmt = ['e24.16', 'e18.10', 'e12.4'][self.cb_fmt.currentIndex()]
        lmax = self.sp_lmax.value()
        use_fast = self.chk_fast.isChecked() and HAVE_FAST
        polar = self.chk_polar.isChecked()
        self.progress.setValue(0)
        self.btn_run.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.tabs.setCurrentIndex(3)
        self.log(f'=== 开始计算 {time.strftime("%Y-%m-%d %H:%M:%S")} ===')
        self.log(f'掩膜: {mask}')
        self.log(f'勒夫数: {love}')
        self.log(f'数据: {data}')
        self.log(f'参数: niter={self.sp_niter.value()}, '
                 f'dlon={self.sp_dlon.value()}, dlat={self.sp_dlat.value()}, fmt={fmt}, '
                 f'lmax={lmax}, 允许负值载荷={self.chk_negative.isChecked()}, '
                 f'极移反馈={"含" if polar else "不含"}')
        self.log(f'内核: {"sleqn_fast（加速）" if use_fast else "sleqn（原版）"}')

        self.thread = ComputeThread(mask, love, data, out, self.sp_niter.value(),
                                    self.sp_dlon.value(), self.sp_dlat.value(), fmt,
                                    allow_negative=self.chk_negative.isChecked(),
                                    lmax=lmax, use_fast=use_fast, polar=polar)
        self.thread.sig_progress.connect(self._on_progress)
        self.thread.sig_log.connect(self.log)
        self.thread.sig_done.connect(self._on_done)
        self.thread.sig_failed.connect(self._on_failed)
        self.thread.start()

    def on_cancel(self):
        if self.thread and self.thread.isRunning():
            self.thread.cancel()
            self.lb_stage.setText('正在取消 …')

    def _on_progress(self, pct, msg):
        self.progress.setValue(pct)
        self.lb_stage.setText(msg)
        self.status.showMessage(f'{pct}%  {msg}')

    def _on_done(self, r):
        self.btn_run.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.progress.setValue(100)
        self.lb_stage.setText('计算完成')
        self.last_stats = r
        out = r.get('out', self.ed_out.text().strip())
        self.log(f'=== 计算完成，用时 {r.get("elapsed", 0):.1f} s ===')
        try:
            self.load_result(out, stats=r)
        except Exception:
            self.log(traceback.format_exc())
        self.tabs.setCurrentIndex(0)

    def _on_failed(self, msg):
        self.btn_run.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        if msg == 'CANCELLED':
            self.lb_stage.setText('已取消')
            self.status.showMessage('计算已取消')
            self.progress.setValue(0)
            return
        self.lb_stage.setText('出错')
        self.log('!!! 计算失败 !!!')
        self.log(msg)
        # 日志里已有完整 traceback；弹窗只取异常本身那一行，比取最后一行的
        # 文件路径/引号片段更容易看懂（完整内容在「日志」页签）。
        _lines = [ln.strip() for ln in (msg or '').splitlines() if ln.strip()]
        _detail = _lines[-1] if _lines else '未知错误'
        for _ln in reversed(_lines):
            if re.match(r'^[A-Za-z_][A-Za-z0-9_.]*(Error|Exception|Warning|Interrupt)\b',
                        _ln):
                _detail = _ln
                break
        QMessageBox.critical(self, '计算失败', _detail)

    def on_open_result(self):
        p, _ = QFileDialog.getOpenFileName(self, '打开结果文件', HERE,
                                           '文本文件 (*.txt);;所有文件 (*)')
        if not p:
            return
        try:
            self.load_result(p)
            self.tabs.setCurrentIndex(0)
            self.log(f'已载入结果文件：{p}')
        except Exception as e:
            QMessageBox.critical(self, '无法读取', f'{p}\n\n{e}')

    def on_save_fig(self):
        idx = self.tabs.currentIndex()
        canvas = self.map_canvas if idx != 1 else self.prof_canvas
        p, _ = QFileDialog.getSaveFileName(self, '保存图片',
                                           os.path.join(HERE, 'slf_figure.png'),
                                           'PNG (*.png);;PDF (*.pdf);;SVG (*.svg)')
        if not p:
            return
        try:
            canvas.fig.savefig(p, dpi=200, bbox_inches='tight')
            self.status.showMessage(f'图片已保存：{p}')
        except Exception as e:
            QMessageBox.critical(self, '保存失败', str(e))

    def on_about(self):
        """帮助 → 关于 / 作者信息。"""
        AboutDialog(self).exec()

    def on_wechat(self):
        """帮助 → 课题组公众号（显示二维码，可直接扫码关注）。"""
        WeChatDialog(self).exec()

    def on_quickstart(self):
        """帮助 → 快速上手（六步走完整条流程）。"""
        QuickStartDialog(self).exec()

    def on_guide(self):
        """帮助 → 使用说明（F1）：在窗口内渲染 docs/使用说明.html。"""
        GuideDialog(self).exec()

    # ------------------------------------------------------------------ 结果
    def load_result(self, path, stats=None):
        S, rlon, rlat = read_result(path)
        self.S, self.rlon, self.rlat = S, rlon, rlat
        self.result_path = path
        self._reload_profile_axis()
        self.redraw()
        self.update_stats(path, stats)
        self.update_preview(path)

    def _reload_profile_axis(self):
        if self.S is None:
            return
        self.cb_paxis.blockSignals(True)
        self.cb_paxis.clear()
        if self.cb_pdir.currentIndex() == 0:
            self.cb_paxis.addItems([f'{v:.1f}°E' for v in self.rlon])
        else:
            self.cb_paxis.addItems([f'{v:.1f}°N' for v in self.rlat])
        self.cb_paxis.blockSignals(False)
        if self.cb_pdir.currentIndex() == 0:
            self.cb_paxis.setCurrentIndex(int(np.argmin(np.abs(self.rlon - 0))))
        else:
            self.cb_paxis.setCurrentIndex(int(np.argmin(np.abs(self.rlat - 0))))
        self.redraw()

    def redraw(self):
        if self.S is None:
            return
        try:
            self.draw_map()
            self.draw_profile()
        except Exception:
            self.log(traceback.format_exc())

    # ---------------- 地图
    def draw_map(self):
        c = self.map_canvas
        c.fig.clear()
        S, lon_e, lat_e = prepare_grid(self.S, self.rlon, self.rlat)
        mode = self.cb_scale.currentIndex()
        cmap = self.cb_cmap.currentText()
        vabs = float(np.nanmax(np.abs(S)))

        proj = None
        if self.chk_map.isChecked() and HAVE_CARTOPY:
            try:
                proj = ccrs.Robinson(central_longitude=0)
            except Exception:
                proj = None
        ax = c.fig.add_subplot(111, projection=proj) if proj else c.fig.add_subplot(111)

        kw = dict(shading='auto', cmap=cmap)
        if proj is not None:
            kw['transform'] = ccrs.PlateCarree()
        if mode == 0:
            m = ax.pcolormesh(lon_e, lat_e, S.T, vmin=-vabs, vmax=vabs, **kw)
            cb_label = '海平面变化 (cm)'
            title = (f'海平面指纹  |  对称色标 ±{vabs:.4g} cm（近场）  |  '
                     f'峰值 {np.nanmax(S):+.4g} cm')
        elif mode == 1:
            v = float(self.sp_vmax.value())
            m = ax.pcolormesh(lon_e, lat_e, S.T, vmin=-v, vmax=v, **kw)
            cb_label = '海平面变化 (cm)'
            title = (f'海平面指纹  |  色标放大 ±{v:.4g} cm（远场；载荷处已超量程）  |  '
                     f'全场最低 {np.nanmin(S):+.4g} cm')
        else:
            v = float(self.sp_vmax.value())
            norm = SymLogNorm(linthresh=v, vmin=-vabs, vmax=vabs, base=10)
            m = ax.pcolormesh(lon_e, lat_e, S.T, norm=norm, **kw)
            cb_label = f'海平面变化 (cm)（symlog，线性区 ±{v:.3g}）'
            title = f'海平面指纹  |  对称对数色标（±{vabs:.4g} cm 内）'
        cb = c.fig.colorbar(m, ax=ax, shrink=0.82, pad=0.02, label=cb_label)
        cb.ax.tick_params(labelsize=8)

        if proj is not None:
            try:
                # 只要海岸线，不要国界
                ax.coastlines(resolution='110m', linewidth=0.6, color='0.25')
            except Exception as e:                     # 底图数据缺失（离线）
                self.log(f'[提示] 海岸线不可用（{e}）；已改用纯网格显示')
                self.chk_map.blockSignals(True)
                self.chk_map.setChecked(False)
                self.chk_map.blockSignals(False)
                return self.draw_map()
            if self.chk_grid.isChecked():
                try:
                    ax.gridlines(draw_labels=False, linewidth=0.3, color='0.6',
                                 linestyle=':')
                except Exception:
                    pass
        else:
            ax.set_xlim(lon_e[0], lon_e[-1])
            ax.set_ylim(lat_e[-1], lat_e[0])
            ax.set_xlabel('经度 (°E)')
            ax.set_ylabel('纬度 (°N)')
            if self.chk_grid.isChecked():
                ax.grid(alpha=0.3, ls=':')
            ax.set_xticks(np.arange(0, 361, 60))
            ax.set_yticks(np.arange(-90, 91, 30))

        ax.set_title(title, fontsize=11, pad=14)
        c.ax = ax
        c.draw()

    # ---------------- 剖面
    def draw_profile(self):
        c = self.prof_canvas
        if not self.cb_paxis.count():
            return
        c.fig.clear()
        S, rlon, rlat = self.S, self.rlon, self.rlat
        along_lon = (self.cb_pdir.currentIndex() == 0)
        if along_lon:
            i = self.cb_paxis.currentIndex()
            y = S[i, :]
            x = rlat
            ttl = f'沿 {rlon[i]:.1f}°E 的经向剖面'
            xl = '纬度 (°N)'
        else:
            j = self.cb_paxis.currentIndex()
            y = S[:, j]
            x = rlon
            ttl = f'沿 {rlat[j]:.1f}°N 的纬向剖面'
            xl = '经度 (°E)'

        ax = c.fig.add_subplot(111)
        ax.axhline(0, color='0.7', lw=0.8)
        ax.plot(x, y, '-', color='#1565c0', lw=1.8, label='海平面指纹 $S$')
        if self.chk_eust.isChecked():
            eust = -self.last_stats.get('tmass_g', np.nan) / \
                (sleqn.RHO0 * sleqn.ARAD ** 2 * 4.0 * np.pi) if self.last_stats else np.nan
            if np.isfinite(eust):
                ax.axhline(eust, ls=':', color='#c62828', lw=1.5,
                           label=f'均匀海面 {eust:.4g} cm')
        ax.set_xlabel(xl)
        ax.set_ylabel('海平面变化 (cm)')
        ax.set_title(f'{ttl}　（max {np.nanmax(y):+.4g} cm，min {np.nanmin(y):+.4g} cm）',
                     fontsize=11)
        ax.grid(alpha=0.3, ls=':')
        ax.legend(fontsize=9)
        c.ax = ax
        c.draw()

    # ---------------- 统计
    def update_stats(self, path, stats=None):
        S = self.S
        rows = []
        if stats:
            tm = stats.get('tmass', np.nan)
            zm = stats.get('zmass', np.nan)
            rows += [
                ('输入数据文件', os.path.basename(stats.get('namein', ''))),
                ('载荷总质量', f'{tm / 1e15:.6f} Gt'),
                ('解算海水质量', f'{zm:.6f} Gt'),
                ('质量守恒相对误差', f'{abs(zm + tm / 1e15) / abs(tm / 1e15):.3e}'
                                    if tm else '—'),
                ('累计载荷面积', f'{stats.get("areatot", float("nan")):.4g} km²'),
                ('累计载荷质量', f'{stats.get("smass", float("nan")):.4g} g'),
                ('计算用时', f'{stats.get("elapsed", float("nan")):.1f} s'),
            ]
        rows += [
            ('结果文件', path),
            ('网格', f'{len(self.rlon)} × {len(self.rlat)}'
                     f'（经度 {self.rlon.min():.1f}~{self.rlon.max():.1f}°E，'
                     f'纬度 {self.rlat.min():.1f}~{self.rlat.max():.1f}°N）'),
            ('海平面指纹 最小值', f'{np.nanmin(S):+.6f} cm'),
            ('海平面指纹 最大值', f'{np.nanmax(S):+.6f} cm'),
        ]
        # 面积加权平均（中点求积，与程序内部一致）
        w = np.sin(np.radians(90.0 - self.rlat))
        mean = float((S * w[None, :]).sum() / (w.sum() * len(self.rlon)))
        j = int(np.argmax(np.abs(S).max(axis=0)))
        ipk, jpk = np.unravel_index(int(np.argmax(np.abs(S))), S.shape)
        rows += [
            ('面积加权平均', f'{mean:+.6f} cm'),
            ('峰值位置', f'{self.rlon[ipk]:.1f}°E, {self.rlat[jpk]:.1f}°N'
                         f'（峰值 {S[ipk, jpk]:+.6f} cm）'),
        ]
        self.tbl.setRowCount(len(rows))
        for r, (k, v) in enumerate(rows):
            self.tbl.setItem(r, 0, QTableWidgetItem(str(k)))
            it = QTableWidgetItem(str(v))
            it.setFlags(it.flags() ^ Qt.ItemIsEditable)
            self.tbl.setItem(r, 1, it)
        self.tbl.resizeRowsToContents()
        if stats:
            self.status.showMessage(
                f'完成：载荷 {stats.get("tmass", 0) / 1e15:.3f} Gt，'
                f'解算海水 {stats.get("zmass", 0):.3f} Gt'
                f'（守恒误差 {abs(stats.get("zmass", 0) + stats.get("tmass", 0) / 1e15) / abs(stats.get("tmass", 1) / 1e15):.2e}）')

    def update_preview(self, path):
        lines = []
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            for k, ln in enumerate(f):
                if k >= 100:
                    break
                lines.append(ln.rstrip())
        self.txt_preview.setPlainText('\n'.join(lines))

    # ------------------------------------------------------------------
    def closeEvent(self, e):
        if self.thread and self.thread.isRunning():
            self.thread.cancel()
            self.thread.wait(3000)
        e.accept()


def _qr_pixmap(size):
    """读取课题组公众号二维码并缩放到指定边长（保持比例、平滑缩放）。"""
    p = wechat_qr_path()
    if not p:
        return None, ''
    pix = QPixmap(p)
    if pix.isNull():
        return None, p
    return pix.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation), p


def _mailto_label(email):
    lab = QLabel(f'<a href="mailto:{email}">{email}</a>')
    lab.setOpenExternalLinks(True)
    lab.setTextInteractionFlags(Qt.TextBrowserInteraction)
    return lab


class WeChatDialog(QDialog):
    """课题组公众号二维码（可点击放大查看、另存图片）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('课题组公众号')
        v = QVBoxLayout(self)
        lab = QLabel(WECHAT_QR_CAPTION)
        lab.setStyleSheet('font-size:12pt; font-weight:bold; color:#1b3a5c;')
        lab.setAlignment(Qt.AlignCenter)
        v.addWidget(lab)

        pix, path = _qr_pixmap(420)
        if pix is not None:
            img = QLabel()
            img.setPixmap(pix)
            img.setAlignment(Qt.AlignCenter)
            v.addWidget(img)
            v.addWidget(QLabel('<div align="center" style="color:#556">'
                               '微信「扫一扫」，关注课题组公众号</div>'))
        else:
            msg = (f'未找到二维码图片。<br><br>请把 <code>{WECHAT_QR_FILENAME}</code> '
                   f'放到 <code>{os.path.join(DOCS_DIRNAME, "使用说明_img")}</code> 或 '
                   f'<code>assets</code> 目录下。')
            if path:
                msg += f'<br><br>（找到的路径无法读取：{path}）'
            lab2 = QLabel(msg)
            lab2.setWordWrap(True)
            v.addWidget(lab2)

        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.button(QDialogButtonBox.Close).setText('关闭')
        bb.rejected.connect(self.reject)
        v.addWidget(bb)


class QuickStartDialog(QDialog):
    """快速上手：六步走完整条流程。"""

    STEPS = [
        ('准备数据',
         '三份文件：海陆掩膜 <code>land.fcn.1_deg</code>、负荷勒夫数 '
         '<code>love_numbers</code>、质量变化数据（每行「经度 纬度 水当量高度(m)」）。'
         '没有数据就先点主界面的「载入演示数据（grace_example）」。'),
        ('选择文件',
         '在左侧「① 输入文件」里分别指定上面三份文件；「③ 输出」里填写结果文件路径。'),
        ('设置参数',
         '迭代次数 <code>niter</code> 一般用 2；<code>dlon/dlat</code> 必须与载荷数据的'
         '网格间隔一致（1° 数据就填 1）；截断阶数 <code>lmax</code> 默认 180，'
         '调大需要勒夫数表支持。'),
        ('开始计算',
         '点「▶ 开始计算」。右侧「日志」页签会实时显示进度，随时可以点「取消」。'),
        ('查看结果',
         '算完自动切到「海平面指纹图」页签；「剖面」看经/纬向剖面，'
         '「统计与数据」有质量守恒自检和结果预览。'),
        ('导出',
         '结果文件本身就是三列文本，可直接用；'
         '图片用「保存图片…」导出 PNG/PDF。'),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('快速上手')
        self.setMinimumSize(700, 640)
        outer = QVBoxLayout(self)

        head = QLabel(f'<b style="font-size:12pt;color:#1b3a5c">{APP_TITLE}</b>'
                      f'<span style="color:#556">　六步走完整条流程</span>')
        outer.addWidget(head)

        area = QScrollArea()
        area.setWidgetResizable(True)
        inner = QWidget()
        g = QGridLayout(inner)
        g.setColumnStretch(1, 1)
        for i, (title, body) in enumerate(self.STEPS, 1):
            num = QLabel(f'<b style="color:#2f6fa8;font-size:11pt">{i}</b>')
            num.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
            num.setFixedWidth(22)
            lab = QLabel(f'<b>{title}</b><br><span style="color:#334">{body}</span>')
            lab.setWordWrap(True)
            lab.setTextFormat(Qt.RichText)
            g.addWidget(num, i - 1, 0)
            g.addWidget(lab, i - 1, 1)
        area.setWidget(inner)
        outer.addWidget(area, 1)

        bb = QDialogButtonBox(QDialogButtonBox.Close)
        b_guide = bb.addButton('📘  打开完整使用说明', QDialogButtonBox.ActionRole)
        b_guide.clicked.connect(self._open_guide)
        bb.button(QDialogButtonBox.Close).setText('关闭')
        bb.rejected.connect(self.reject)
        outer.addWidget(bb)

    def _open_guide(self):
        GuideDialog(self).exec()


class _FittingBrowser(QTextBrowser):
    """会**按窗口宽度自适应图片**的说明书正文区。

    QTextBrowser 不会自己缩放图片：说明书里的界面截图有 2000+ 像素宽，
    直接塞进去就得左右拖着看。这里在窗口尺寸变化时把每张图的 ``width``
    重算成"视口宽度减一点边距"，只重排一次（带 120 ms 防抖），并保持原来的
    滚动位置与左侧目录当前项，所以拖窗口时阅读位置不会跳。

    规则（与 SHSynth 的说明书窗口一致）：
    * 不放大：图比窗口窄就按原始宽度显示（``data-full`` 记录了原始宽度）；
    * 不设 ``height``：让 Qt 按比例算高度，图下面不会留一大片空白；
    * 宽度只在小幅变化（> 24 px）时才重排，避免拖动时反复刷新。
    """

    _IMG_W = re.compile(r'(<img\b[^>]*?)\bwidth="(\d+)"', re.I)
    _IMG_FULL = re.compile(r'data-full="(\d+)"', re.I)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._raw_html = ''
        self._render_fn = None
        self._applied_width = 0
        self._search_paths = []
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(120)
        self._timer.timeout.connect(self._reflow)

    # ------------------------------------------------------------ 对外接口
    def set_render_fn(self, fn):
        """给定 ``fn(内容宽度) -> HTML``：视口变化时整篇重排。

        Qt 的表格列宽必须是写死的像素（见 :mod:`guide_render`），所以窗口一
        变窄，光缩放图片还不够——整篇按新宽度重排一次，表格才不会撑出横向
        滚动条。
        """
        self._render_fn = fn

    def set_source_html(self, html: str):
        """设置原始 HTML（宽度尚未按视口缩放），立即渲染一次。"""
        self._raw_html = html
        self._applied_width = 0
        self._reflow(force=True)

    def set_search_paths(self, paths):
        """记住图片搜索路径：``setHtml`` 会把它们清掉，重排后要补回来。"""
        self._search_paths = list(paths)
        super().setSearchPaths(self._search_paths)

    def resizeEvent(self, event):                        # noqa: N802
        super().resizeEvent(event)
        if self._raw_html:
            self._timer.start()

    # ---------------------------------------------------------------- 内部
    def _viewport_width(self) -> int:
        return max(self.viewport().width() - 26, 320)

    def _fit_images(self, html: str, avail: int) -> str:
        """把每张图的宽度重算成 ``min(原始宽度, 可用宽度)``。"""
        def repl(m):
            head, cur = m.group(1), int(m.group(2))
            full_m = self._IMG_FULL.search(head)
            full = int(full_m.group(1)) if full_m else cur
            return f'{head}width="{max(80, min(full, avail))}"'

        fitted = self._IMG_W.sub(repl, html)

        def repl2(m):
            tag = m.group(0)
            return tag if 'width=' in tag else tag[:-1] + f' width="{avail}">'

        return re.sub(r'<img\b[^>]*>', repl2, fitted)

    def _reflow(self, force: bool = False):
        avail = self._viewport_width()
        if not force and abs(avail - self._applied_width) < 24:
            return
        bar = self.verticalScrollBar()
        frac = (bar.value() / bar.maximum()) if bar.maximum() else 0.0
        anchor = self.anchorAt(self.viewport().rect().topLeft())
        self._applied_width = avail
        base = self.document().baseUrl()
        if self._render_fn is not None:
            # 视口宽度 → 正文内容宽度（两侧各留 7 px 由 _viewport_width 扣掉）
            html = self._render_fn(max(420, avail - 14))
        else:
            html = self._fit_images(self._raw_html, avail)
        self.setHtml(html)
        if self._search_paths:
            super().setSearchPaths(self._search_paths)
        self.document().setBaseUrl(base)
        if bar.maximum():
            bar.setValue(int(frac * bar.maximum()))
        if anchor:
            self.scrollToAnchor(anchor)


class GuideDialog(QDialog):
    """使用说明窗口：**左侧目录 + 右侧正文**，可缩放、可自适应图片。

    做法与同类工具（SHSynth）的说明书窗口一致：

    * 目录从 HTML 的 ``h2``/``h3`` 自动生成（二级加粗、三级缩进），点一下跳转；
    * 顶部 ``A+`` / ``A−`` / ``默认字号`` 调节正文字号；
    * 正文里的截图随窗口宽度自动缩放，不需要左右拖动；
    * 内部锚点自己处理，外部链接（DOI、邮箱）交给系统浏览器；
    * 需要最完整排版时用「用浏览器打开」看同一份 ``docs/使用说明.html``。

    渲染前仍要经 :func:`guide_render.to_qt_html` 改写成 Qt 富文本友好版：
    Qt 只支持 CSS 2.1 的一个子集（表格不给列宽会被压扁、``<pre>`` 不换行会把
    整篇文档撑宽、提示框背景丢失）。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f'使用说明 — {APP_TITLE}')
        self.resize(1080, 800)
        self.setMinimumSize(700, 460)

        self.guide_path = guide_html_path()
        self._zoom = 0

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        # ------------------------------------------------------ 顶部工具条
        bar = QHBoxLayout()
        title = QLabel(f'<b style="font-size:14pt;">使用说明</b>'
                       f'<span style="color:#666;">　{APP_TITLE}</span>')
        bar.addWidget(title)
        bar.addStretch(1)
        self.btn_smaller = QPushButton('A−')
        self.btn_smaller.setFixedWidth(44)
        self.btn_smaller.setToolTip('缩小正文字号')
        self.btn_smaller.clicked.connect(lambda: self._zoom_by(-1))
        self.btn_bigger = QPushButton('A+')
        self.btn_bigger.setFixedWidth(44)
        self.btn_bigger.setToolTip('放大正文字号')
        self.btn_bigger.clicked.connect(lambda: self._zoom_by(1))
        self.btn_reset = QPushButton('默认字号')
        self.btn_reset.setToolTip('恢复默认正文字号')
        self.btn_reset.clicked.connect(self._zoom_reset)
        self.btn_browser = QPushButton('用浏览器打开')
        self.btn_browser.setToolTip('在系统默认浏览器里打开同一份说明书（排版最完整）')
        self.btn_browser.clicked.connect(self._open_browser)
        self.btn_browser.setEnabled(bool(self.guide_path))
        for b in (self.btn_smaller, self.btn_bigger, self.btn_reset,
                  self.btn_browser):
            b.setMinimumHeight(28)
            bar.addWidget(b)
        root.addLayout(bar)

        # ------------------------------------------------------ 目录 + 正文
        split = QSplitter(Qt.Horizontal)
        self.toc = QListWidget()
        self.toc.setMaximumWidth(300)
        self.toc.setMinimumWidth(150)
        self.toc.setToolTip('点章节名跳到对应小节')
        self.toc.itemClicked.connect(self._goto_item)
        split.addWidget(self.toc)

        self.view = _FittingBrowser()
        self.view.setOpenExternalLinks(False)   # 内外部链接都自己分发
        self.view.setOpenLinks(False)
        self.view.setFrameShape(QFrame.NoFrame)
        self.view.setLineWrapMode(QTextBrowser.WidgetWidth)
        self.view.anchorClicked.connect(self._on_anchor)
        split.addWidget(self.view)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([240, 820])
        split.splitterMoved.connect(lambda *_: self.view._reflow())
        root.addWidget(split, 1)

        box = QDialogButtonBox(QDialogButtonBox.Close)
        b_top = box.addButton('↑  回到顶部', QDialogButtonBox.ActionRole)
        b_top.clicked.connect(lambda: self.view.scrollToAnchor('toc'))
        box.button(QDialogButtonBox.Close).setText('关闭')
        box.rejected.connect(self.reject)
        root.addWidget(box)

        # 等第一次布局完成、视口宽度确定后再排版（表格列宽是按内容宽度写死的）
        QTimer.singleShot(0, self._load)

    # ------------------------------------------------------------------ 加载
    def _load(self):
        guide = self.guide_path
        if not guide or not os.path.exists(guide):
            self.view.setHtml(
                f'<h3>未找到说明书文件</h3>'
                f'<p>预期位置：<code>'
                f'{os.path.join(HERE, DOCS_DIRNAME, GUIDE_HTML_NAME)}</code></p>'
                f'<p>若这是打包后的发行版，说明发行包缺少 docs/ 目录。</p>')
            return
        base = os.path.dirname(os.path.abspath(guide))
        self.view.set_search_paths([base])
        with open(guide, encoding='utf-8') as fh:
            raw = fh.read()

        def render(px):
            px = int(px)
            return guide_render.to_qt_html(raw, base, content_px=px,
                                           max_img_width=px)

        # 视口一变就按新宽度整篇重排：表格列宽是写死的像素，只缩图片不够
        self.view.set_render_fn(render)
        qt_html = render(max(560, self.view.viewport().width() - 40))
        self.view.set_source_html(qt_html)
        self._build_toc(qt_html)

    def _build_toc(self, html: str):
        """从 HTML 的 h2/h3 生成目录（二级加粗、三级缩进，过长标题截断）。"""
        self.toc.clear()
        for m in re.finditer(r'<h([23])\s+id="([^"]+)"[^>]*>(.*?)</h\1>',
                             html, re.S | re.I):
            lvl, sid, raw = m.group(1), m.group(2), m.group(3)
            if sid == 'toc':                 # 「目录」本身不进目录
                continue
            text = re.sub(r'<[^>]+>', '', raw).replace('↑', '').strip()
            label = text if len(text) <= 26 else text[:25] + '…'
            item = QListWidgetItem(('　' if lvl == '3' else '') + label)
            item.setData(Qt.UserRole, sid)
            item.setToolTip(text)
            if lvl == '2':
                f = item.font()
                f.setBold(True)
                item.setFont(f)
            self.toc.addItem(item)
        if self.toc.count():
            self.toc.setCurrentRow(0)

    # ------------------------------------------------------------------ 动作
    def _goto_item(self, item: QListWidgetItem):
        sid = item.data(Qt.UserRole)
        if sid:
            self.view.scrollToAnchor(str(sid))

    def _on_anchor(self, url: QUrl):
        if url.scheme() in ('http', 'https', 'mailto'):
            QDesktopServices.openUrl(url)
        elif url.hasFragment() or (url.toString() or '').startswith('#'):
            self.view.scrollToAnchor(url.fragment())
        else:
            QDesktopServices.openUrl(url)

    def _zoom_by(self, step: int):
        self._zoom = max(-4, min(8, self._zoom + step))
        self.view.zoomIn(1 if step > 0 else -1)

    def _zoom_reset(self):
        while self._zoom > 0:
            self.view.zoomOut(1)
            self._zoom -= 1
        while self._zoom < 0:
            self.view.zoomIn(1)
            self._zoom += 1

    def _open_browser(self):
        if self.guide_path and os.path.exists(self.guide_path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.guide_path))


class AboutDialog(QDialog):
    """关于 / 作者信息：作者、单位、联系方式、公众号二维码与引用方式。

    一屏之内看全，不需要再点二级对话框；点二维码可放大。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('关于 / 作者信息')
        self.setMinimumWidth(780)
        root = QVBoxLayout(self)

        title = QLabel(
            f'<div style="font-size:16pt;font-weight:bold;color:#1b3a5c">'
            f'{APP_TITLE}</div>'
            f'<div style="color:#556">版本 v{VERSION}　·　{APP_NAME_EN}</div>')
        title.setTextFormat(Qt.RichText)
        root.addWidget(title)

        body = QHBoxLayout()

        # ---------------- 左：作者信息 + 引用 ----------------
        left = QVBoxLayout()

        g_author = QGroupBox('作者信息  /  Author')
        f_author = QFormLayout(g_author)
        f_author.addRow('作者', QLabel(f'<b>{AUTHOR_NAME_CN}</b>'
                                       f'（{AUTHOR_NAME_EN}）'))
        f_author.addRow('单位', QLabel(f'{AUTHOR_AFFILIATION_CN}<br>'
                                       f'<span style="color:#667">'
                                       f'{AUTHOR_AFFILIATION_EN}</span>'))
        f_author.addRow('邮箱', _mailto_label(AUTHOR_EMAIL))
        f_author.addRow('电话', QLabel(AUTHOR_PHONE))
        f_author.addRow('公众号', QLabel(f'{WECHAT_ACCOUNT}（{WECHAT_ACCOUNT_EN}）'))
        left.addWidget(g_author)

        g_cite = QGroupBox('引用方式  /  How to cite')
        v_cite = QVBoxLayout(g_cite)
        self.lab_cite = QLabel(
            '本程序实现并求解海平面方程，方法出自：<br>'
            f'<span style="color:#234">{PAPER_CITATION_HTML}</span><br>'
            '<span style="color:#667">在论文或报告中使用了本程序的计算结果，'
            '请引用上述文献。</span>')
        self.lab_cite.setWordWrap(True)
        self.lab_cite.setTextFormat(Qt.RichText)
        self.lab_cite.setOpenExternalLinks(True)
        v_cite.addWidget(self.lab_cite)
        left.addWidget(g_cite)
        left.addStretch(1)

        body.addLayout(left, 1)

        # ---------------- 右：公众号二维码 ----------------
        g_qr = QGroupBox('课题组公众号')
        v_qr = QVBoxLayout(g_qr)
        pix, _path = _qr_pixmap(230)
        if pix is not None:
            btn = QPushButton()
            btn.setIcon(pix)
            btn.setIconSize(pix.size())
            btn.setFlat(True)
            btn.setFixedSize(pix.width() + 8, pix.height() + 8)
            btn.setToolTip('点击放大二维码')
            btn.clicked.connect(lambda: WeChatDialog(self).exec())
            v_qr.addWidget(btn, 0, Qt.AlignHCenter)
            cap = QLabel(f'<div align="center" style="color:#556">'
                         f'{WECHAT_ACCOUNT}（{WECHAT_ACCOUNT_EN}）<br>'
                         f'<span style="font-size:9pt">微信扫一扫 · 点击图片放大</span>'
                         f'</div>')
            cap.setTextFormat(Qt.RichText)
            v_qr.addWidget(cap)
        else:
            v_qr.addWidget(QLabel('未找到二维码图片。'))
        v_qr.addStretch(1)
        body.addWidget(g_qr)

        root.addLayout(body)

        note = QLabel(
            '<div style="color:#667;font-size:9pt">'
            '本程序在本地离线运行，不会联网、不上传任何数据。<br>'
            '界面基于 Qt for Python (PySide6)，依据 GNU LGPL v3 以未修改的动态库方式使用。'
            '</div>')
        note.setTextFormat(Qt.RichText)
        note.setWordWrap(True)
        root.addWidget(note)

        bb = QDialogButtonBox(QDialogButtonBox.Close)
        b_guide = bb.addButton('📘  使用说明', QDialogButtonBox.ActionRole)
        b_guide.clicked.connect(self._open_guide)
        b_quick = bb.addButton('🧭  快速上手', QDialogButtonBox.ActionRole)
        b_quick.clicked.connect(lambda: QuickStartDialog(self).exec())
        bb.button(QDialogButtonBox.Close).setText('关闭')
        bb.rejected.connect(self.reject)
        root.addWidget(bb)

    def _open_guide(self):
        GuideDialog(self).exec()

    def _fit_citation(self):
        lab = getattr(self, 'lab_cite', None)
        if lab is None or lab.width() <= 0:
            return
        need = lab.heightForWidth(lab.width())
        if abs(need - lab.minimumHeight()) > 2:
            lab.setMinimumHeight(need)

    def showEvent(self, event):                              # noqa: N802
        super().showEvent(event)
        QTimer.singleShot(0, self._fit_citation)

    def resizeEvent(self, event):                            # noqa: N802
        super().resizeEvent(event)
        self._fit_citation()


def _selftest():
    """打包/安装后的自检：不弹窗口，检查随包资源、跑一个小算例、渲染一张地图。

    用法：``sleqn.exe --selftest``（控制台版会打印结果，退出码 0 = 全部通过）。
    装到别的机器上之后跑一下，就能确认随包文件、离线底图、数值内核都还在。
    """
    import tempfile
    print('=' * 64)
    print(f'{APP_TITLE}  v{VERSION}  —— 安装自检')
    print('=' * 64)

    ok = []

    def ck(name, cond, detail=''):
        ok.append(bool(cond))
        print(f"[{'PASS' if cond else 'FAIL'}] {name:34s} {detail}", flush=True)

    print(f'  程序目录 : {HERE}')
    g = guide_html_path()
    ck('使用说明', bool(g), os.path.basename(g) if g else '缺失')
    q = wechat_qr_path()
    ck('公众号二维码', bool(q), os.path.basename(q) if q else '缺失')
    ic = app_icon_path()
    ck('程序图标', bool(ic), os.path.basename(ic) if ic else '缺失')
    ck('cartopy 可用', HAVE_CARTOPY, '')
    if HAVE_CARTOPY:
        import cartopy
        dd = cartopy.config['data_dir']
        ck('离线底图目录', os.path.isdir(os.path.join(dd, 'shapefiles')),
           os.path.basename(os.path.normpath(dd)))

    demo = os.path.join(HERE, 'demo')
    ck('示例数据', os.path.exists(os.path.join(demo, 'load_demo.txt')), demo)

    # ---- 数值内核：跑一个小算例 ----
    try:
        app = QApplication.instance() or QApplication([])
        tmp = tempfile.mkdtemp(prefix='sleqn_selftest_')
        out = os.path.join(tmp, 'S.txt')
        lst = os.path.join(tmp, 'Filelist.txt')
        with open(lst, 'w', encoding='utf-8') as f:
            f.write(f'"{os.path.join(demo, "load_demo.txt")}" "{out}"\n')
        _fmt = sleqn.OUT_FMT
        sleqn.OUT_FMT = (18, 10)
        res = sleqn.run(os.path.join(demo, 'land.fcn.1_deg'),
                        os.path.join(demo, 'love_numbers'), lst,
                        niter=2, dlon=0.5, dlat=0.5, clip_negative=False,
                        lmax=60)
        sleqn.OUT_FMT = _fmt
        r = res[0]
        rel = abs(r['zmass'] + r['tmass'] / 1e15) / abs(r['tmass'] / 1e15)
        S = np.loadtxt(out)[:, 2]
        ck('数值内核（demo, lmax=60）', len(S) == sleqn.NPHI * sleqn.NTH,
           f'{len(S)} 格点')
        ck('质量守恒', rel < 1e-12, f'相对误差 {rel:.2e}')
        ck('结果量级合理', 0.5 < S.max() < 2.0, f'max {S.max():+.4f} cm')

        # ---- 极移（polar motion）反馈开关：关掉后结果应略有不同（差在 (2,1)）----
        out_np = os.path.join(tmp, 'S_nopolar.txt')
        lst_np = os.path.join(tmp, 'Filelist_nopolar.txt')
        with open(lst_np, 'w', encoding='utf-8') as f:
            f.write(f'"{os.path.join(demo, "load_demo.txt")}" "{out_np}"\n')
        sleqn.OUT_FMT = (18, 10)
        res_np = sleqn.run(os.path.join(demo, 'land.fcn.1_deg'),
                           os.path.join(demo, 'love_numbers'), lst_np,
                           niter=2, dlon=0.5, dlat=0.5, clip_negative=False,
                           lmax=60, polar=False)
        sleqn.OUT_FMT = _fmt
        r_np = res_np[0]
        rel_np = abs(r_np['zmass'] + r_np['tmass'] / 1e15) / abs(r_np['tmass'] / 1e15)
        S_np = np.loadtxt(out_np)[:, 2]
        d_np = float(np.abs(S_np - S).max())
        ck('极移开关：关闭后仍质量守恒', rel_np < 1e-12, f'相对误差 {rel_np:.2e}')
        ck('极移开关：开/关结果不同且量级合理', 1e-6 < d_np < 0.05,
           f'max|Δ| = {d_np:.3e} cm（场峰值 {abs(S).max():.4f} cm）')

        # ---- 路径含空格（C:\Program Files\海平面指纹\…）回归 ----
        # 控制文件按行、按空白切分，路径不引号就会被空格截断成 "C:\Program"。
        # 装到 Program Files 的用户会 100% 撞上，所以这里必须回归。
        sdir = os.path.join(tmp, 'Program Files', 'hai ping mian')
        os.makedirs(sdir, exist_ok=True)
        s_data = os.path.join(sdir, 'load demo.txt')
        s_out = os.path.join(sdir, 'slf out.txt')
        shutil.copy(os.path.join(demo, 'load_demo.txt'), s_data)
        s_lst = os.path.join(sdir, 'Filelist.txt')
        with open(s_lst, 'w', encoding='utf-8') as f:
            f.write(f'"{s_data}" "{s_out}"\n')
        sleqn.OUT_FMT = (18, 10)
        try:
            sleqn.run(os.path.join(demo, 'land.fcn.1_deg'),
                      os.path.join(demo, 'love_numbers'), s_lst,
                      niter=2, dlon=0.5, dlat=0.5, clip_negative=False, lmax=60)
            s_ok = os.path.exists(s_out)
            s_same = (s_ok and os.path.getsize(s_out) == os.path.getsize(out))
        except Exception as exc:                               # noqa: BLE001
            s_ok = s_same = False
            print(f'  （含空格路径算例报错：{type(exc).__name__}: {exc}）')
        sleqn.OUT_FMT = _fmt
        ck('路径含空格的算例（带引号控制文件）', s_ok and s_same,
           '目录 "Program Files\\hai ping mian"' if s_ok else '未能算出结果')

        # ---- 界面与出图 ----
        win = MainWindow()
        win.resize(1000, 700)
        win.show()
        app.processEvents()
        ck('界面：极移开关默认勾选', win.chk_polar.isChecked(), '')
        # 端到端接线检查：取消勾选 → 经 on_run/ComputeThread 跑一遍 → 结果应与
        # 直接调用 sleqn.run(polar=False) 完全一致（证明复选框真的接到了数值内核）。
        # 这里显式指向 demo/（不用 _load_demo_paths，它在本仓库会优先选 grace_example）。
        _demo = os.path.join(HERE, 'demo')
        win.ed_mask.setText(os.path.join(_demo, 'land.fcn.1_deg'))
        win.ed_love.setText(os.path.join(_demo, 'love_numbers'))
        win.ed_data.setText(os.path.join(_demo, 'load_demo.txt'))
        win.sp_dlon.setValue(0.5)
        win.sp_dlat.setValue(0.5)
        win.sp_lmax.setValue(60)
        out_gui = os.path.join(tmp, 'S_gui_nopolar.txt')
        win.ed_out.setText(out_gui)
        win.chk_polar.setChecked(False)
        win.on_run()
        _t0 = time.time()
        while (win.thread is not None and win.thread.isRunning()
               and time.time() - _t0 < 300):
            app.processEvents()
            time.sleep(0.01)
        app.processEvents()
        gui_ok = os.path.exists(out_gui)
        d_gui = (float(np.abs(np.loadtxt(out_gui)[:, 2] - S_np).max())
                 if gui_ok else float('nan'))
        ck('界面：极移开关经 on_run 生效', gui_ok and d_gui < 1e-9,
           f'GUI(关极移) 与直接调用 polar=False 的 max|Δ| = {d_gui:.3e} cm')
        win.chk_polar.setChecked(True)
        win.load_result(out)
        win.chk_map.setChecked(True)
        win.redraw()
        app.processEvents()
        png = os.path.join(tmp, 'map.png')
        win.map_canvas.fig.savefig(png, dpi=110, bbox_inches='tight')
        ck('界面与地图渲染', os.path.getsize(png) > 20000,
           f'{os.path.getsize(png) // 1024} kB')
        win.close()

        # ---- 说明书的 Qt 改写（窗口里排版对不对，关键看这一步）----
        raw = open(g, encoding='utf-8').read()
        qt = guide_render.to_qt_html(raw, os.path.dirname(g), 980, 980)
        ck('说明书改写：目录锚点保留', qt.count('id="s') >= 12,
           f'{qt.count("id=")} 个 id')
        ck('说明书改写：表格已补列宽', qt.count('<table') >= 7,
           f'{qt.count("<table")} 个表格')
        ck('说明书改写：样式已内联', '<style' not in qt and 'style="' in qt, '')
        dlg = GuideDialog()
        app.processEvents()
        nt = len(dlg.view.toPlainText())
        ck('说明书窗口可渲染', nt > 5000, f'{nt} 字')
        dlg.close()

        # ---- 「关于」对话框：引用文字不能被裁掉（QLabel 自动换行的高度不向上传播，
        #      内容一多就会被裁，这里做回归检查）----
        about = AboutDialog()
        about.show()
        for _ in range(6):
            app.processEvents()
        lbl = [x for x in about.findChildren(QLabel) if '方法出自' in x.text()]
        if not lbl:
            ck('关于对话框：找得到引用文字', False, '未找到')
        else:
            lb = lbl[0]
            need = lb.heightForWidth(lb.width())
            txt = lb.text()
            zh, en = txt.find('王林松'), txt.find('Sun J. W.')
            ck('关于对话框：引用文字未被裁掉', lb.height() >= need,
               f'{lb.height()} px / 需要 {need} px；'
               f'中文文献在前={0 <= zh < en}')
        about.close()
    except Exception as exc:                                   # noqa: BLE001
        ck('数值内核 / 界面', False, f'{type(exc).__name__}: {exc}')
        traceback.print_exc()

    print()
    print(f'结论：{sum(ok)}/{len(ok)} 项通过')
    return 0 if all(ok) else 1


def main():
    # 自检模式：必须在建 QApplication 之前把平台设成离屏，别弹窗
    if '--selftest' in sys.argv:
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        os.environ.setdefault('QT_QPA_FONTDIR', r'C:\Windows\Fonts')
        app = QApplication([])
        app.setApplicationName(APP_TITLE)
        return _selftest()

    app = QApplication(sys.argv)
    app.setApplicationName(APP_TITLE)
    _icon = app_icon_path()
    if _icon:
        # 应用程序级图标：任务栏、Alt+Tab、以及没有父窗口的对话框都靠它
        app.setWindowIcon(QIcon(_icon))
    w = MainWindow()
    w.show()
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
