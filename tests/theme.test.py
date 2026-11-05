# -*- coding: utf-8 -*-
"""主题白名单回归用例。

v1.4.12 的教训：新增彩色主题时，界面预览和 SQLite 落库两处各留了一份
写死的「浅/深/跟随系统」判断，结果点彩色主题没反应、保存也被改回 system。
这里把四处名单（引擎、界面点击、head 防闪、落库）钉在一起，并真正存读一遍。
"""
import os
import re
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import store  # noqa: E402

COLOR_THEMES = ("aurora", "sakura", "sunset", "mint", "galaxy")
ALL_THEMES = ("system", "light", "dark") + COLOR_THEMES


def read(path):
    with open(os.path.join(ROOT, path), "r", encoding="utf-8") as f:
        return f.read()


def check(ok, label):
    if not ok:
        raise AssertionError(label)
    print("  ok   " + label)


def main():
    # 1) 引擎导出的名单必须正好是这 8 个
    engine = read(os.path.join("src", "engine.js"))
    block = re.search(r"var THEME_LIST = \{(.*?)\};", engine, re.S).group(1)
    keys = tuple(re.findall(r"(\w+)\s*:\s*1", block))
    check(keys == ALL_THEMES, "engine.js THEME_LIST 含全部 8 个主题")

    # 2) 界面点击处理走名单，不许再出现写死的浅/深二选一
    ui = read(os.path.join("src", "ui.js"))
    click = re.search(
        r"fTheme'\)\.addEventListener\('click'(.*?)\n  \}\);", ui, re.S
    ).group(1)
    check("THEME_LIST[v]" in click, "ui.js 主题点击按 THEME_LIST 判断")
    check("v === 'light'" not in click, "ui.js 没有写死的浅/深二选一")

    # 3) head 防闪脚本能认出每个彩色主题，否则启动时先闪一下默认色
    head = read(os.path.join("src", "index.html"))
    for t in COLOR_THEMES:
        check(head.count(t + ": '") >= 1, "防闪脚本认得 " + t)

    # 4) 落库白名单与引擎一致，并且真能原样存读
    check(tuple(store.THEME_VALUES) == ALL_THEMES, "store.THEME_VALUES 与引擎一致")
    # store 用 WAL 且连接靠 GC 回收，Windows 上临时目录可能还被占着；
    # 清理失败不影响断言结果，放它过去即可（目录留给系统临时文件清理）
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        store.init(tmp)
        for t in ALL_THEMES:
            store.save_cfg({"theme": t})
            check(store.load_cfg().get("theme") == t, "存读 " + t)
        store.save_cfg({"theme": "bogus"})
        check(store.load_cfg().get("theme") == "system", "脏值退回 system")

    print("\n全部通过：%d 项" % (3 + len(COLOR_THEMES) + len(ALL_THEMES) + 2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
