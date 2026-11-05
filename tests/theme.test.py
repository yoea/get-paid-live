# -*- coding: utf-8 -*-
"""主题元数据回归用例。

v1.4.12 的教训：新增主题时界面预览和落库各留了一份写死的三选一判断。
v1.4.16 起以 engine.js 的 THEME_META 为唯一真源，这里把防闪脚本、CSS 场景、
粒子配方、设置面板、数据库几处名单钉在一起校验，并真正存读一遍。
新增主题只改 engine.js 的 THEME_META，别处漏改这里立刻报错。
"""
import io
import json
import math
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import store  # noqa: E402


def read(path):
    with io.open(os.path.join(ROOT, path), "r", encoding="utf-8") as f:
        return f.read()


def check(ok, label):
    if not ok:
        raise AssertionError(label)
    print("  ok   " + label)
    return 1


def theme_meta():
    code = "var G=require('./src/engine.js');console.log(JSON.stringify(G.THEME_META));"
    out = subprocess.check_output(["node", "-e", code], cwd=ROOT)
    return json.loads(out.decode("utf-8"))


def main():
    total = 0
    meta = theme_meta()
    keys = list(meta.keys())
    scenes = [k for k in keys if not meta[k].get("mode")]
    total += check(len(keys) == 13, "共 13 项：1 个模式 + 12 套场景主题")
    total += check(keys[0] == "system" and meta["system"]["mode"] is True,
                   "首项是「跟随系统」模式开关")
    total += check(len(scenes) == 12, "场景主题 12 套")

    # 命名统一「场景 2 + 意向 2 + 主色 1」，并且每套都有场景文案与预览渐变
    names = []
    for k in scenes:
        m = meta[k]
        total += check(len(m["name"]) == 5, k + " 名称为 5 字（场景+意向+色彩）")
        total += check(len(m["scene"]) >= 12, k + " 有场景意向文案")
        total += check(m["sw"].startswith("linear-gradient"), k + " 有预览渐变")
        total += check(m["base"] in ("light", "dark"), k + " 明暗基底合法")
        total += check(re.match(r"^#[0-9a-f]{6}$", m["meta"]) is not None,
                       k + " 标题栏色合法")
        names.append(m["name"])
    total += check(len(set(names)) == len(names), "12 个名字不重复")

    head = read(os.path.join("src", "index.html"))
    css = read(os.path.join("src", "app.css"))
    ui = read(os.path.join("src", "ui.js"))
    total += check('id="themeMode"' in head and 'id="themeStory"' in head,
                   "设置面板有独立模式行与场景说明区")
    total += check('<div class="seg" id="fTheme"' in head,
                   "12 张预览卡由脚本生成（HTML 只留容器）")
    total += check("TM[v]" in ui and "G.THEME_META" in ui,
                   "界面按 THEME_META 判断，没有写死名单")
    total += check("Object.keys(TM)" in ui, "预览卡由元数据生成")

    for k in scenes:
        base = meta[k]["base"]
        total += check(head.count(k + ": '" + base + "'") >= 1,
                       "防闪脚本认得 " + k + "（" + base + " 底）")
        total += check("[data-accent=" + k + "]" in css, "CSS 配色块有 " + k)
        total += check(re.search(r"\[data-accent=" + k + r"\][^{]*\.fx-", css) is not None
                       or (":root[data-accent=" + k + "] .fx-") in css,
                       "CSS 场景元素有 " + k)
        total += check(re.search(r"\b" + k + r":\s*\{", ui) is not None,
                       "粒子配方有 " + k)

    # 粒子引擎的三层深度、阵风、二次扬起这几条关键能力不能丢
    total += check("var LAYER = [" in ui and "layerOf(i)" in ui, "粒子三层深度")
    total += check("conf.gust" in ui and "conf.lift" in ui, "阵风与落瓣二次扬起")
    total += check("shape: 'petal'" in ui and "shape: 'leaf'" in ui
                   and "shape: 'flake'" in ui, "花瓣 / 枫叶 / 雪花形状")

    # 雨丝：不能用 background-position 逐帧重绘（1px 硬边斜线会亚像素闪），
    # 且循环位移在条纹法线上的投影必须是整数个周期，否则到头会瞬移一下。
    total += check("animation:fxRain var(--fx-rain-dur" in css
                   and "@keyframes fxRain{from{transform:translate3d(0,0,0)}"
                       "to{transform:translate3d(-23.34px,96.52px,0)}}" in css,
                   "雨丝走 transform 合成层")
    rad = math.radians(76)
    dot = -23.34 * math.sin(rad) + 96.52 * (-math.cos(rad))
    total += check(abs(dot + 46) < 0.05, "雨丝循环位移在法线上的投影恰为一个周期(46px)")
    total += check(re.search(r"drops:\s*\d+", ui) is not None
                   and "spawnDrop" in ui and "drawRain(t, conf)" in ui
                   and "--fx-rain-dur" in css, "雨夜小雨滴/落地涟漪与分主题雨速")
    total += check('<canvas id="rainFx"' in head and "#rainFx{" in css
                   and "rctx.clearRect" in ui, "雨滴走独立前景层，不被卡片模糊")

    # 落库白名单与引擎一致，并且真能原样存读
    total += check(tuple(store.THEME_VALUES) == tuple(keys), "store.THEME_VALUES 与引擎一致")
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        store.init(tmp)
        for k in keys:
            store.save_cfg({"theme": k})
            total += check(store.load_cfg().get("theme") == k, "存读 " + k)
        store.save_cfg({"theme": "bogus"})
        total += check(store.load_cfg().get("theme") == "system", "脏值退回 system")

    print("\n全部通过：%d 项" % total)
    return 0


if __name__ == "__main__":
    sys.exit(main())
