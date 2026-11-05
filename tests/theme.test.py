# -*- coding: utf-8 -*-
"""主题白名单回归用例。

v1.4.12 的教训：新增彩色主题时，界面预览和 SQLite 落库两处各留了一份
写死的「浅/深/跟随系统」判断，结果点彩色主题没反应、保存也被改回 system。
这里以 engine.js 的 THEME_LIST 为唯一真源，把界面点击、启动防闪、
数据库、CSS 场景、粒子配方几处名单钉在一起，并真正存读一遍。
新增主题时只要改 engine.js，别处漏改这里会立刻报错。
"""
import os
import re
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import store  # noqa: E402

BASE_THEMES = ("system", "light", "dark")


def read(path):
    with open(os.path.join(ROOT, path), "r", encoding="utf-8") as f:
        return f.read()


def check(ok, label):
    if not ok:
        raise AssertionError(label)
    print("  ok   " + label)


def main():
    engine = read(os.path.join("src", "engine.js"))
    block = re.search(r"var THEME_LIST = \{(.*?)\};", engine, re.S).group(1)
    keys = tuple(re.findall(r"(\w+)\s*:\s*1", block))
    check(keys[:3] == BASE_THEMES, "engine.js 前三项是默认深浅/跟随系统")
    colors = tuple(k for k in keys if k not in BASE_THEMES)
    check(len(colors) == 8, "engine.js 含 8 套彩色主题")
    all_themes = BASE_THEMES + colors
    print("  彩色主题：" + "、".join(colors))

    # 界面点击处理走名单，不许再出现写死的浅/深二选一
    ui = read(os.path.join("src", "ui.js"))
    click = re.search(
        r"fTheme'\)\.addEventListener\('click'(.*?)\n  \}\);", ui, re.S
    ).group(1)
    check("THEME_LIST[v]" in click, "ui.js 主题点击按 THEME_LIST 判断")
    check("v === 'light'" not in click, "ui.js 没有写死的浅/深二选一")

    # 每套主题都得有：防闪底色、CSS 变量块、CSS 场景、粒子配方、设置里的按钮
    head = read(os.path.join("src", "index.html"))
    css = read(os.path.join("src", "app.css"))
    for t in colors:
        check(head.count(t + ": '") >= 1, "防闪脚本认得 " + t)
        check("[data-accent=" + t + "]" in css, "CSS 配色块有 " + t)
        check(re.search(t + r":\s*\{", ui) is not None, "粒子配方有 " + t)
        check('data-theme-opt="' + t + '"' in head, "设置按钮有 " + t)
    base = re.search(r"var THEME_BASE = \{(.*?)\};", ui, re.S).group(1)
    for t in colors:
        check(t + ":" in base, "ui.js THEME_BASE 有 " + t)

    # 落库白名单与引擎一致，并且真能原样存读
    check(tuple(store.THEME_VALUES) == all_themes, "store.THEME_VALUES 与引擎一致")
    # store 用 WAL 且连接靠 GC 回收，Windows 上临时目录可能还被占着；
    # 清理失败不影响断言结果，放它过去即可（目录留给系统临时文件清理）
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        store.init(tmp)
        for t in all_themes:
            store.save_cfg({"theme": t})
            check(store.load_cfg().get("theme") == t, "存读 " + t)
        store.save_cfg({"theme": "bogus"})
        check(store.load_cfg().get("theme") == "system", "脏值退回 system")

    print("\n全部通过：%d 项" % (4 + len(colors) * 5 + len(all_themes) + 2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
