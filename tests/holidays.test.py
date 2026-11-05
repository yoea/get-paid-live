# -*- coding: utf-8 -*-
"""2026 年官方放假 / 调休补班日的守卫用例。

钉住两件事：
1. store.py 的一次性迁移名单必须和 engine.js 的 DEFAULT_CFG 一致；
2. 老库升级只增不删地补齐，之后用户删掉的日期不会被重新灌回来。
"""
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import store  # noqa: E402


def check(ok, label):
    if not ok:
        raise AssertionError(label)
    print("  ok   " + label)
    return 1


def js_defaults():
    code = ("var G=require('./src/engine.js');var d=G.defaults();"
            "console.log(JSON.stringify({h:d.holidays,m:d.makeup_workdays}));")
    out = subprocess.check_output(["node", "-e", code], cwd=ROOT)
    return json.loads(out.decode("utf-8"))


def main():
    total = 0
    d = js_defaults()
    total += check(len(store.OFFICIAL_2026_MAKEUP) == 6, "2026 官方补班日 6 天")
    total += check(set(store.OFFICIAL_2026_MAKEUP) == set(d["m"]),
                   "迁移名单与引擎默认补班日一致")
    total += check(set(store.OFFICIAL_2026_HOLIDAYS).issubset(set(d["h"])),
                   "迁移名单里的放假日期都在引擎默认里")
    total += check("2026-02-15" in d["h"] and "2026-02-23" in d["h"],
                   "春节 2/15-2/23 共 9 天已校准")

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        store.init(tmp)                      # 建库（新装路径）
        with store._connect() as conn:       # 造一个「老库」：只有用户手工填的两天
            conn.execute("DELETE FROM holidays")
            conn.execute("DELETE FROM meta WHERE key='official2026'")
            conn.execute("INSERT INTO holidays(date,kind) VALUES('2026-10-10','makeup')")
            conn.execute("INSERT INTO holidays(date,kind) VALUES('2026-12-12','makeup')")
        store.init(tmp)                      # 升级：跑一次性种子
        cfg = store.load_cfg()
        mak = set(cfg["makeup_workdays"])
        total += check(set(store.OFFICIAL_2026_MAKEUP).issubset(mak),
                       "老库升级后补齐全年 6 天")
        total += check("2026-12-12" in mak, "用户自己加的补班日保留")
        total += check("2026-02-23" in cfg["holidays"], "缺失的春节假日补齐")
        with store._connect() as conn:
            conn.execute("DELETE FROM holidays WHERE date='2026-10-10'")
        store.init(tmp)                      # 再启动：标记已存在，不该回灌
        total += check("2026-10-10" not in store.load_cfg()["makeup_workdays"],
                       "用户删掉的日期不会被重新灌回来")

    print("\n全部通过：%d 项" % total)
    return 0


if __name__ == "__main__":
    sys.exit(main())
