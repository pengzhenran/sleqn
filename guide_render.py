#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
guide_render.py —— 把 HTML 说明书改写成 Qt 富文本能正常排版的样子
============================================================================

同一份 ``docs/使用说明.html`` 用浏览器打开没问题，塞进 ``QTextBrowser`` 却会出各种
布局毛病，原因是 Qt 的富文本只支持 CSS 2.1 的一个小子集：

* **不认** ``border-collapse`` / ``max-width`` / ``white-space: pre-wrap``，
  对 ``<div>`` 的背景色也画不可靠；
* **表格不给列宽就把第一列压扁** —— 参数名会变成一个字一行的竖排；
* **``<pre>`` 不换行** —— 一行长内容就把整个文档撑宽，于是全篇横向滚动、右侧被切掉。

所以这里做一次**面向 Qt 的改写**（只在渲染时做，HTML 本体不动，浏览器里仍是原样）：

1. 丢掉 ``<style>``，样式全部内联到标签上；
2. ``<table>`` 补 ``width`` / ``cellpadding`` / ``cellspacing``，按首行的格子数
   给每列写死像素宽，单元格补边框与内边距；
3. ``<pre>`` 与 ``.tip`` / ``.warn`` 提示框改成**单格表格** —— 这样才能有背景和边框，
   而且宽度受控、内容能换行；
4. ``<img>`` 按真实像素宽写死宽度（超宽的先缩到上限），另写
   ``data-full="原始宽度"`` 供窗口内的自适应显示使用。

对外只有 :func:`to_qt_html`。
"""

from __future__ import annotations

import os
import re

# 各类元素的内联样式（Qt 认这些属性）
S_TABLE = 'border-collapse:collapse; margin:8px 0;'
S_TH = ('background-color:#eaf1f8; color:#1b3a5c; border:1px solid #b9cde0;'
        ' padding:5px 8px;')
S_TD = 'border:1px solid #b9cde0; padding:5px 8px; vertical-align:top;'
S_TD_PLAIN = 'border:none; padding:2px 10px 2px 0;'

BOX_STYLE = {
    'tip': ('background-color:#f0f7f2; border:1px solid #cfe6d8;'
            ' padding:8px 11px;'),
    'warn': ('background-color:#fdf3f3; border:1px solid #eccfcf;'
             ' padding:8px 11px; color:#8a2b2b;'),
    'pre': ('background-color:#f7f8fa; border:1px solid #dde3ea;'
            ' padding:8px 10px; color:#234;'
            ' font-family:Consolas,monospace; font-size:9.5pt;'),
}

CODE_STYLE = ('font-family:Consolas,monospace; background-color:#f2f4f7;'
              ' color:#a33;')

# 各列宽度**按内容宽度的比例**给（Qt 只按首行定列宽，所以必须换算成写死的像素）。
# 用比例而不是固定像素，视口变窄（例如窗口内说明书左侧多了目录栏）时表格也不会
# 撑出横向滚动条。
COL_RATIO = {
    2: [0.19, 0.81],
    3: [0.15, 0.09, 0.76],
    4: [0.15, 0.25, 0.25, 0.35],
}


def _col_widths(ncol, content_px, plain):
    """按比例算出每列的像素宽度；列数未知的表格均分。"""
    ncol = max(ncol, 1)
    ratio = None if plain else COL_RATIO.get(ncol)
    if not ratio:
        return [max(60, content_px // ncol)] * ncol
    return [max(50, int(round(r * content_px))) for r in ratio[:ncol]]


def _clean(text):
    """把一段 HTML 压成单行，避免拼接时混入换行。"""
    return re.sub(r'\s+', ' ', text).strip()


def _pre_repl(m, content_px):
    """``<pre>`` → 单格表格：有背景、有边框、能换行。

    Qt 里 ``<pre>`` 既不换行也不认 ``white-space``，直接把整篇文档撑宽。
    换行符转 ``<br>``，行首缩进的空格转 ``&nbsp;``（否则会被合并掉），
    行内空格保留，这样长行还能自动折行。
    """
    body = m.group(1)
    lines = []
    for ln in body.split('\n'):
        stripped = ln.lstrip(' ')
        indent = len(ln) - len(stripped)
        lines.append('&nbsp;' * indent + stripped)
    inner = '<br>'.join(lines)
    return (f'<table width="{content_px}" cellpadding="0" cellspacing="0"'
            f' style="{S_TABLE}"><tr>'
            f'<td style="{BOX_STYLE["pre"]}">{inner}</td></tr></table>')


def _box_repl(m, content_px):
    """``<div class="tip|warn">`` → 单格表格（Qt 画 div 背景不可靠）。"""
    kind, body = m.group(1).lower(), m.group(2)
    return (f'<table width="{content_px}" cellpadding="0" cellspacing="0"'
            f' style="{S_TABLE}"><tr>'
            f'<td style="{BOX_STYLE.get(kind, BOX_STYLE["tip"])}">{body}'
            f'</td></tr></table>')


def _cell_repl(m, widths, idx, plain):
    """给单元格补样式和列宽。"""
    tag = m.group(1).lower()
    attrs = m.group(2) or ''
    body = m.group(3)
    keep = attrs
    # 去掉原有的 style，避免与内联样式打架
    keep = re.sub(r'\s*style="[^"]*"', '', keep)
    w = widths[idx] if idx < len(widths) else ''
    warr = f' width="{w}"' if w else ''
    style = S_TD_PLAIN if plain else (S_TH if tag == 'th' else S_TD)
    return f'<{tag}{keep}{warr} style="{style}">{body}</{tag}>'


def _table_repl(m, content_px):
    """给表格补宽度、列宽与单元格样式。"""
    attrs, body = m.group(1) or '', m.group(2)
    plain = 'toc' in attrs.lower()

    # 首行决定列数
    first = re.search(r'<tr[^>]*>(.*?)</tr>', body, re.S | re.I)
    ncol = len(re.findall(r'<t[dh]\b', first.group(1), re.I)) if first else 0
    widths = _col_widths(ncol, content_px, plain)

    # 逐行逐格补样式
    def do_row(rm):
        row = rm.group(0)
        i = [0]

        def do_cell(cm):
            out = _cell_repl(cm, widths, i[0], plain)
            i[0] += 1
            return out

        return re.sub(r'<(t[dh])\b([^>]*)>(.*?)</\1>', do_cell, row,
                      flags=re.S | re.I)

    body = re.sub(r'<tr\b[^>]*>.*?</tr>', do_row, body, flags=re.S | re.I)
    border = '0' if plain else '1'
    return (f'<table width="{content_px}" border="{border}" cellpadding="0"'
            f' cellspacing="0" style="{S_TABLE}">{body}</table>')


_IMG_RE = re.compile(r'<img\b[^>]*>', re.I)
_IMG_W_CACHE = {}          # {(绝对路径, mtime): 像素宽度}，窗口缩放时反复改写 HTML 用


def _img_px(path):
    """读图片像素宽度（带缓存，避免每次重排都重新解码十几张截图）。"""
    try:
        key = (path, os.path.getmtime(path))
    except OSError:
        return 0
    if key in _IMG_W_CACHE:
        return _IMG_W_CACHE[key]
    w = 0
    try:
        from PySide6.QtGui import QPixmap
        pm = QPixmap(path)
        if not pm.isNull():
            w = pm.width()
    except Exception:                                          # noqa: BLE001
        w = 0
    _IMG_W_CACHE[key] = w
    return w


def _fit_img(m, base_dir, max_w):
    """给 ``<img>`` 写死宽度，并记下原始宽度。

    Qt 不认 CSS ``max-width``，3000 px 的截图会撑破窗口，所以这里先给一个
    不超上限的宽度；同时写 ``data-full="原始宽度"``，供
    :class:`sleqn_gui._FittingBrowser` 在窗口变化时按视口宽度重算
    （它只缩小、不放大，靠的就是这个属性）。
    """
    tag = m.group(0)
    src = re.search(r'\bsrc="([^"]+)"', tag)
    w_attr = re.search(r'\bwidth="(\d+)"', tag)
    full_attr = re.search(r'\bdata-full="(\d+)"', tag)
    w = int(w_attr.group(1)) if w_attr else 0
    if w and full_attr:
        return tag                                   # 已带 data-full，原样保留
    if src and not w:
        p = os.path.join(base_dir, src.group(1).replace('/', os.sep))
        w = _img_px(p)
    if not w:
        return tag
    tag = re.sub(r'\s*\bwidth="\d+"', '', tag)
    tag = re.sub(r'\s*\bdata-full="\d+"', '', tag)
    shown = min(w, max_w) if max_w else w
    return re.sub(r'\s*/?>$', f' width="{shown}" data-full="{w}">', tag)


def _tag_repl(tag, style, attrs='', align=None):
    """重写一个开标签：补内联样式，但**保住 id**（目录跳转全靠它）。"""
    keep = ''
    m = re.search(r'\bid="[^"]*"', attrs or '')
    if m:
        keep = ' ' + m.group(0)
    al = f' align="{align}"' if align else ''
    return f'<{tag}{keep}{al} style="{style}">'


def to_qt_html(html, base_dir, content_px=980, max_img_width=980):
    """把浏览器版说明书改写成 Qt 富文本版。

    Parameters
    ----------
    html          : 原始 HTML 文本
    base_dir      : 说明书所在目录（用来解析图片真实尺寸）
    content_px    : 正文内容宽度（用于表格与图片）
    max_img_width : 图片最大宽度
    """
    s = html
    s = re.sub(r'<style\b.*?</style>', '', s, flags=re.S | re.I)

    # 顺序有讲究：先处理 pre（里面可能有 < > 实体，不受后续表格规则影响），
    # 再处理提示框，最后处理表格本身。
    s = re.sub(r'<pre\b[^>]*>(.*?)</pre>', lambda m: _pre_repl(m, content_px),
               s, flags=re.S | re.I)
    s = re.sub(r'<div\s+class="(tip|warn)"\s*>(.*?)</div>',
               lambda m: _box_repl(m, content_px), s, flags=re.S | re.I)
    s = re.sub(r'<table\b([^>]*)>(.*?)</table>',
               lambda m: _table_repl(m, content_px), s, flags=re.S | re.I)
    s = _IMG_RE.sub(lambda m: _fit_img(m, base_dir, max_img_width), s)

    # 零散的行内元素与标题补样式（★ 必须保留 id，否则目录锚点全失效）
    s = re.sub(r'<code\b[^>]*>', '<span style="%s">' % CODE_STYLE, s, flags=re.I)
    s = s.replace('</code>', '</span>')
    for tag, style in (('h1', 'font-size:17pt; color:#1b3a5c;'),
                       ('h2', 'font-size:13.5pt; color:#1b3a5c;'),
                       ('h3', 'font-size:11.5pt; color:#2f6fa8;')):
        s = re.sub(rf'<{tag}\b([^>]*)>',
                   lambda m, _t=tag, _s=style: _tag_repl(_t, _s, m.group(1)),
                   s, flags=re.I)
    s = re.sub(r'<p\s+class="cap"[^>]*>',
               lambda m: _tag_repl('p', 'color:#556; font-size:9pt;',
                                   m.group(0), align='center'), s, flags=re.I)
    s = re.sub(r'<p\s+class="meta"[^>]*>',
               lambda m: _tag_repl('p', 'color:#667; font-size:9.5pt;',
                                   m.group(0)), s, flags=re.I)
    s = re.sub(r'<p\s+class="center"[^>]*>',
               lambda m: _tag_repl('p', '', m.group(0), align='center'), s,
               flags=re.I)
    return s
