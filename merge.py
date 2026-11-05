# -*- coding: utf-8 -*-
"""把 src/ 下的四个源文件合成单文件 上班鼓励器.html。

为什么要有这一步：发布形态是一个单文件 exe，界面只有一份 html 封在里面。
开发时把 html / css / js 分开写，定位、diff、单独跑测试都干净；打包和运行时
仍然只认合成后的单个文件，所以 exe 的体积和结构与拆分前完全一样。

源文件：
    src/index.html   标记（head 里的防白闪脚本必须内联，留在里面）
    src/app.css      样式
    src/engine.js    纯计算引擎，不碰 DOM
    src/ui.js        渲染与交互

用法：
    python merge.py           生成 上班鼓励器.html
    python merge.py --check   只检查产物是否与源同步（不一致返回 1）
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "src")
OUT = os.path.join(HERE, "上班鼓励器.html")

# 产物第一行是生成提示，放在 DOCTYPE 之后（DOCTYPE 必须是文件开头）
BANNER = "<!-- 本文件由 merge.py 从 src/ 生成。要改东西请改 src/ 下的源文件，别直接编辑这里。 -->\n"

# (index.html 里的占位标签, 资源文件, 内联用的包裹标签)
PARTS = (
    ('<link rel="stylesheet" href="app.css">', "app.css", "style"),
    ('<script src="engine.js"></script>', "engine.js", "script"),
    ('<script src="lunar.js"></script>', "lunar.js", "script"),
    ('<script src="ui.js"></script>', "ui.js", "script"),
)


def _read(path):
    # newline="" 原样保留换行，避免 Windows 上写出 CRLF 导致每次 diff 全变
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


def build():
    """返回合成后的整页文本。"""
    page = _read(os.path.join(SRC, "index.html"))
    for token, name, tag in PARTS:
        if page.count(token) != 1:
            raise SystemExit(
                "src/index.html 里 %r 应该出现且只出现一次，实际 %d 次"
                % (token, page.count(token))
            )
        body = _read(os.path.join(SRC, name))
        if "</" + tag + ">" in body:
            raise SystemExit(
                "src/%s 里出现了 </%s> 字面量，内联会截断页面，先转义它"
                % (name, tag)
            )
        page = page.replace(token, "<%s>\n%s</%s>" % (tag, body, tag))

    head, sep, rest = page.partition("\n")
    return head + "\n" + BANNER + rest


def merge(quiet=False):
    """写好产物，返回路径。"""
    page = build()
    with open(OUT, "w", encoding="utf-8", newline="") as f:
        f.write(page)
    if not quiet:
        print("已生成 %s（%.1f KB）" % (os.path.basename(OUT), len(page.encode("utf-8")) / 1024.0))
    return OUT


def in_sync():
    try:
        return _read(OUT) == build()
    except OSError:
        return False


def main(argv):
    if "--check" in argv:
        if in_sync():
            print("产物与 src/ 一致")
            return 0
        print("产物与 src/ 不一致，跑一次 python merge.py 重新生成")
        return 1
    merge()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
