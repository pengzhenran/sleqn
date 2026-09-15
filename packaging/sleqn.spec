# -*- mode: python ; coding: utf-8 -*-
"""
sleqn.spec —— PyInstaller 打包配置（onedir）
============================================================================

    <打包环境>\\Scripts\\pyinstaller.exe --noconfirm ^
        --distpath C:\\Users\\pengzhenran\\sleqn-build\\dist ^
        --workpath C:\\Users\\pengzhenran\\sleqn-build\\build ^
        packaging\\sleqn.spec

（dist/work 刻意放到项目外：项目在同步盘上，产物几百 MB，不该往同步盘里塞。）

产物结构（onedir）：

    sleqn\\sleqn.exe                 双击即用
    sleqn\\_internal\\                运行库（PySide6 / matplotlib / numpy …）
        docs\\                        使用说明与全部配图
        assets\\                      图标与公众号二维码
        cartopy_data\\                离线岸线（Natural Earth 110m）
        grace_example\\  demo\\        示例数据

程序中用 ``os.path.dirname(__file__)`` 找这些随包资源；冻结后 ``__file__`` 落在
``_internal`` 下，所以 datas 的 dest 都写 ``.``（cartopy_data 单独放根下，
代码里两个候选路径都能命中）。
"""

import fnmatch
import os
import sys

ROOT = os.path.abspath(os.path.join(SPECPATH, '..'))


def tree(src, dest, skip=()):
    """把目录逐文件列成 datas（可以按通配符剔除不需要随包的文件）。

    直接用 (目录, dest) 会把整个目录塞进去；这里要能挑，所以自己走一遍。
    ★ dest 是"目标目录名"，不是"."。写 "." 会把源目录的**内容**摊平到 _internal
      根下，于是 demo/ 与 grace_example/ 里同名的 land.fcn.1_deg 会互相覆盖。
    """
    out = []
    for root, _dirs, files in os.walk(src):
        for f in files:
            if any(fnmatch.fnmatch(f, p) for p in skip):
                continue
            rel = os.path.relpath(root, src)
            sub = dest if rel == '.' else os.path.join(dest, rel)
            out.append((os.path.join(root, f), sub))
    return out


# 随包资源。剔除的东西：
#   *.BAD_*      —— 明确标为错误的历史产物
#   slf_gui.txt  —— 界面的临时输出，用户自己会生成
#   *.exe        —— demo 里附带的 Fortran 编译版，本程序用不到
#   运行_*.bat   —— 是给上面那两个 exe 用的启动脚本
#   *_icon_sheet —— 图标尺寸对照表，只用于开发期自检
DATAS = []
DATAS += tree(os.path.join(ROOT, 'docs'), 'docs')
DATAS += tree(os.path.join(ROOT, 'assets'), 'assets',
              skip=['sleqn_icon_sheet.png'])
DATAS += tree(os.path.join(ROOT, 'grace_example'), 'grace_example',
              skip=['*.BAD_*', 'slf_gui.txt'])
DATAS += tree(os.path.join(ROOT, 'demo'), 'demo',
              skip=['*.exe', '运行_*.bat', 'slf_gui.txt'])
DATAS += tree(os.path.join(ROOT, 'licenses'), 'licenses')
# 离线底图：代码先找 packaging/cartopy_data，再找 cartopy_data，放根下即可
DATAS += tree(os.path.join(ROOT, 'packaging', 'cartopy_data'), 'cartopy_data')

# conda 把 liblzma / libexpat / libssl / libcrypto / libffi / libbz2 放在
# Library\bin（非标准位置），PyInstaller 自动分析找不到，_lzma / pyexpat / _ssl /
# _ctypes / _bz2 在包里就会导入失败。这些是 Python 标准库的依赖，手工补进去。
CONDA_LIB = os.path.join(sys.prefix, 'Library', 'bin')
BINARIES = [
    (os.path.join(CONDA_LIB, d), '.')
    for d in ('liblzma.dll', 'libexpat.dll',
              'libssl-3-x64.dll', 'libcrypto-3-x64.dll',
              'ffi-8.dll', 'libbz2.dll')
    if os.path.exists(os.path.join(CONDA_LIB, d))
]

# 调试用：设 SLEQN_CONSOLE=1 可以打一个带控制台的版本，方便看导入/启动期报错
CONSOLE = os.environ.get('SLEQN_CONSOLE') == '1'
EXE_NAME = os.environ.get('SLEQN_NAME', 'sleqn')        # 可执行文件名
COLLECT_NAME = os.environ.get('SLEQN_DIR', 'sleqn_build')   # 产物目录名

# 明确不要的东西：换过界面的 Qt 绑定、开发期工具、打包器自己
EXCLUDES = [
    'tkinter', 'PyQt5', 'PyQt6', 'PySide2',
    'IPython', 'jupyter', 'notebook', 'pytest', 'setuptools', 'pip',
    'PyInstaller',
]

a = Analysis(
    [os.path.join(ROOT, 'sleqn_gui.py')],
    pathex=[ROOT],
    binaries=BINARIES,
    datas=DATAS,
    hiddenimports=[
        'sleqn', 'sleqn_fast', 'guide_render',   # 同目录模块，显式列出更保险
        'cartopy.crs', 'cartopy.feature',
        'shapely', 'pyproj',
        'shapefile',                    # pyshp 装出来的模块名是 shapefile
        'lzma', 'ssl', 'bz2', 'ctypes', 'xml.parsers.expat',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=EXE_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                      # UPX 常被杀软误报，且对 Qt 收益有限
    console=CONSOLE,                # 默认图形界面程序，不弹黑框
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(ROOT, 'assets', 'sleqn.ico'),
    version=os.path.join(ROOT, 'packaging', 'version_info.txt'),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=COLLECT_NAME,
)
