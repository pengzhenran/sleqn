#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_guide.py —— 校验《使用说明》是否完整可用
============================================================================

打包前后都建议跑一遍：

    python tools/check_guide.py

检查项：
  * docs/使用说明.html 存在，图片引用全部能找到对应文件；
  * 图号连续、目录锚点都有对应标题；
  * 界面代码能找到说明书与公众号二维码（打包后仍能打开「帮助 → 使用说明」）；
  * 文档里没有混入面向开发者的内容（源码文件名、编译/打包工具名等）。

退出码：0 = 全部通过，1 = 有问题。
"""

from __future__ import annotations

import os
import re
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

GUIDE = os.path.join(ROOT, 'docs', '使用说明.html')

# 说明书是给第三方使用者看的，不该出现这些词（源码文件名、打包/开发工具、内部实现话术）。
# 不列入本表的两种情况：
#   * Qt / PySide6 之类的**许可声明**，是必须提供给使用者的；
#   * Fortran —— 指本程序另一个版本的实现，属于"结果与谁一致"的来源说明，
#     与使用者判断可信度直接相关，不是内部实现细节。
DEV_WORDS = ['sleqn.py', 'sleqn_fast', 'sleqn_dp.f90', 'sleqn.f90',
             '逐字节', '向量化', 'PyInstaller', 'pyinstaller', 'NumPy', 'numpy',
             'matplotlib', 'pip install', 'JSON', 'API', 'Makefile']

OK = []


def check(name, ok, detail=''):
    OK.append(bool(ok))
    print(f"[{'PASS' if ok else 'FAIL'}] {name:42s} {detail}")


def main():
    check('说明书存在', os.path.exists(GUIDE), GUIDE)
    if not os.path.exists(GUIDE):
        return 1
    html = open(GUIDE, encoding='utf-8').read()

    # ---------------------------------------------------------- 图片引用
    srcs = re.findall(r'<img[^>]*\bsrc="([^"]+)"', html)
    missing = []
    for s in srcs:
        fp = os.path.join(ROOT, 'docs', s.replace('/', os.sep))
        if not os.path.exists(fp):
            missing.append(s)
    check(f'图片引用可解析（{len(srcs)} 处）', not missing,
          '' if not missing else f'缺失：{missing}')

    # ---------------------------------------------------------- 图号连续
    nums = sorted({int(n) for n in re.findall(r'图\s*(\d+)\s*　', html)})
    expect = list(range(1, len(nums) + 1))
    check(f'图号连续 1..{len(nums)}', nums == expect, f'实际：{nums}')

    # ---------------------------------------------------------- 锚点
    ids = set(re.findall(r'\bid="([^"]+)"', html))
    hrefs = set(re.findall(r'href="#([^"]+)"', html))
    dead = sorted(hrefs - ids)
    check(f'目录锚点有效（{len(hrefs)} 个）', not dead,
          '' if not dead else f'失效：{dead}')

    # ---------------------------------------------------------- 表格标签配平
    # 多写一个 </tr> 浏览器会忍，Qt 的富文本引擎会直接把排版搞坏甚至卡死，
    # 所以这里必须查。
    bad = []
    for tag in ('tr', 'td', 'th', 'table', 'pre', 'div'):
        o = len(re.findall(rf'<{tag}\b', html, re.I))
        c = len(re.findall(rf'</{tag}>', html, re.I))
        if o != c:
            bad.append(f'<{tag}>={o} </{tag}>={c}')
    check('表格/块级标签配平', not bad, '' if not bad else '；'.join(bad))

    # ---------------------------------------------------------- 标题结构
    h2 = re.findall(r'<h2[^>]*>(.*?)</h2>', html, re.S)
    check('章节结构完整', len(h2) >= 10, f'{len(h2)} 个 h2 小节')

    # ---------------------------------------------------------- 开发者内容
    hit = [w for w in DEV_WORDS if w in html]
    check('未混入开发向内容', not hit, '' if not hit else f'出现：{hit}')

    # ---------------------------------------------------------- 界面侧可达性
    try:
        import sleqn_gui
        gp = sleqn_gui.guide_html_path()
        qp = sleqn_gui.wechat_qr_path()
        check('GUI 能找到使用说明', bool(gp), gp or '(未找到)')
        check('GUI 能找到公众号二维码', bool(qp), qp or '(未找到)')
    except Exception as exc:                                   # noqa: BLE001
        check('界面模块可导入', False, f'{type(exc).__name__}: {exc}')

    print()
    print(f'结论：{sum(OK)}/{len(OK)} 项通过' + ('' if all(OK) else '  ← 有问题'))
    return 0 if all(OK) else 1


if __name__ == '__main__':
    sys.exit(main())
