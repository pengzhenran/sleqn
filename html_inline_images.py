#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
html_inline_images.py —— 把 HTML 中的 <img src="figs/xxx"> 内嵌为 base64 数据 URI，
                        生成"单文件版"报告（便于分发、打印、不丢图）。

用法：
    python html_inline_images.py 总结报告.html            # 原地内嵌
    python html_inline_images.py 总结报告.html -o out.html
"""

from __future__ import annotations

import argparse
import base64
import mimetypes
import os
import re
import sys


def inline(html_path, out_path=None):
    html = open(html_path, encoding='utf-8').read()
    base = os.path.dirname(os.path.abspath(html_path))
    n = 0
    total = 0

    def repl(m):
        nonlocal n, total
        src = m.group(1)
        if src.startswith(('data:', 'http:', 'https:')):
            return m.group(0)
        p = os.path.join(base, src)
        if not os.path.exists(p):
            print(f'  [警告] 找不到图片: {src}')
            return m.group(0)
        mime = mimetypes.guess_type(p)[0] or 'image/png'
        data = base64.b64encode(open(p, 'rb').read()).decode('ascii')
        n += 1
        total += len(data)
        print(f'  内嵌 {src}  ({os.path.getsize(p) / 1024:.0f} KB -> base64 {len(data) / 1024:.0f} KB)')
        return f'src="data:{mime};base64,{data}"'

    html = re.sub(r'src="([^"]+)"', repl, html)
    out = out_path or html_path
    open(out, 'w', encoding='utf-8').write(html)
    print(f'完成：内嵌 {n} 张图片，输出 {out}（{os.path.getsize(out) / 1024 / 1024:.2f} MB）')
    return n


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('html')
    ap.add_argument('-o', '--out')
    a = ap.parse_args()
    if inline(a.html, a.out) == 0:
        sys.exit('没有内嵌任何图片，请检查 <img src> 路径')
