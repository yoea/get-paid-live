# -*- coding: utf-8 -*-
"""SQLite 存储层。

以前设置是一坨 JSON 塞在 localStorage 里，桌面选项又是一个 desktop.json。
现在全部落在一个 data.db 里，按语义拆表，方便查询和单独改某一项：

    settings  标量配置（月薪、上下班、主题、桌面开关……）
    weekdays  哪几天上班
    holidays  法定节假日 / 调休补班日（kind 区分）
    items     鼓励语商品表
    notes     每个日期的备注（日历上点出来的）
    meta      schema 版本、是否完成过首次设置

数据库放在 %LOCALAPPDATA%\\ShangBanGuLiQi\\data.db。只在本机，不上传。
"""

import os
import re
import sqlite3
import time

DB_NAME = "data.db"
SCHEMA_VERSION = 3

_path = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS weekdays (
  dow INTEGER PRIMARY KEY
);
CREATE TABLE IF NOT EXISTS holidays (
  date TEXT PRIMARY KEY,
  kind TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS items (
  id    INTEGER PRIMARY KEY AUTOINCREMENT,
  name  TEXT NOT NULL,
  price REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS notes (
  date       TEXT PRIMARY KEY,
  body       TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
"""

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
NOTE_MAX = 100


# ---------------------------------------------------------------- 连接

def init(directory):
    """由 desktop.py 在启动时调用一次。目录不存在就建。"""
    global _path
    try:
        os.makedirs(directory, exist_ok=True)
    except OSError:
        pass
    _path = os.path.join(directory, DB_NAME)
    with _connect() as conn:
        conn.executescript(SCHEMA)
        _migrate(conn)
    _import_legacy_options(directory)
    return _path


def path():
    return _path


def _default_dir():
    root = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(root, "ShangBanGuLiQi")


def _connect():
    # 有人绕过 desktop.py 直接调 store（测试脚本）时也能用，路径按默认规则取
    if _path is None:
        init(_default_dir())
    conn = sqlite3.connect(_path, timeout=5.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
    except sqlite3.Error:
        pass
    return conn


def _migrate(conn):
    row = conn.execute("SELECT value FROM meta WHERE key='schema'").fetchone()
    cur = int(row["value"]) if row else 0
    if cur < SCHEMA_VERSION:
        # 表都是 IF NOT EXISTS 建的，这里只记版本，供以后加字段时判断
        conn.execute(
            "INSERT INTO meta(key, value) VALUES('schema', ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (str(SCHEMA_VERSION),),
        )


def _import_legacy_options(directory):
    """老版本的 desktop.json 并进 settings 表，然后把文件改成 .bak。
    不直接删：万一用户还想看，文件还在。"""
    try:
        import json

        old = os.path.join(directory, "desktop.json")
        if not os.path.isfile(old):
            return
        with open(old, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            with _connect() as conn:
                for k, v in data.items():
                    _set(conn, "desk." + str(k), "1" if v is True else "0" if v is False else str(v))
        os.replace(old, old + ".bak")
    except Exception:
        pass


# ---------------------------------------------------------------- 取值工具

def _get(conn, key, default=None):
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def _set(conn, key, value):
    conn.execute(
        "INSERT INTO settings(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, str(value)),
    )


def _num(text, default=0.0):
    try:
        return float(text)
    except (TypeError, ValueError):
        return default


def _hhmm(text, default=""):
    m = re.match(r"^(\d{1,2})[:：](\d{1,2})$", str(text or "").strip())
    if not m:
        return default
    h, mi = int(m.group(1)), int(m.group(2))
    if 0 <= h <= 23 and 0 <= mi <= 59:
        return "%02d:%02d" % (h, mi)
    return default


def _valid_date(text):
    """必须是真实存在的日期：2026-02-30 这种格式对、日子不对的要挡掉。"""
    s = str(text or "")
    if not DATE_RE.match(s):
        return False
    try:
        import datetime

        datetime.date(int(s[0:4]), int(s[5:7]), int(s[8:10]))
        return True
    except ValueError:
        return False


def _flag(text, default=False):
    if text is None:
        return default
    return str(text) in ("1", "true", "True", "yes")


# ---------------------------------------------------------------- 配置读写

def has_saved():
    try:
        with _connect() as conn:
            row = conn.execute("SELECT value FROM meta WHERE key='ready'").fetchone()
            return bool(row and row["value"] == "1")
    except sqlite3.Error:
        return False


def load_cfg():
    """返回界面能直接吃的 dict。缺的键不补，交给 JS 的 normalize 兜默认值。"""
    out = {}
    try:
        with _connect() as conn:
            keys = {
                "monthly_salary": "num",
                "work_start": "hhmm",
                "work_end": "hhmm",
                "break_start": "hhmm",
                "break_end": "hhmm",
                # 发薪日：0 / 空 = 用户留空，不显示发薪倒计时（键照存，别丢掉这个选择）
                "pay_day": "num",
                "pay_time": "hhmm",
                "theme": "text",
                "demo": "bool",
                "demo_offset": "num",
                "hide_money": "bool",
            }
            for key, kind in keys.items():
                raw = _get(conn, "cfg." + key)
                if raw is None:
                    continue
                if kind == "num":
                    out[key] = _num(raw)
                elif kind == "hhmm":
                    out[key] = _hhmm(raw)
                elif kind == "bool":
                    out[key] = _flag(raw)
                else:
                    out[key] = raw

            week = [r["dow"] for r in conn.execute("SELECT dow FROM weekdays ORDER BY dow")]
            if week:
                out["work_weekdays"] = week

            hol, mak = [], []
            for r in conn.execute("SELECT date, kind FROM holidays ORDER BY date"):
                (hol if r["kind"] == "holiday" else mak).append(r["date"])
            out["holidays"] = hol
            out["makeup_workdays"] = mak

            items = [
                {"name": r["name"], "price": r["price"]}
                for r in conn.execute("SELECT name, price FROM items ORDER BY id")
            ]
            if items:
                out["items"] = items
    except sqlite3.Error:
        return {}
    if "hide_money" in out:
        out["display"] = {"hide_money": out.pop("hide_money")}
    return out


def save_cfg(cfg):
    """整份覆盖。只动传进来的键，没传的保持原样。"""
    if not isinstance(cfg, dict):
        return False
    try:
        with _connect() as conn:
            for key in ("work_start", "work_end", "break_start", "break_end"):
                if key not in cfg:
                    continue
                raw = cfg.get(key)
                if raw is None or str(raw).strip() == "":
                    # 午休本来就允许留空；上班/下班留空交给界面校验，这里别写成脏值
                    _set(conn, "cfg." + key, "")
                    continue
                parsed = _hhmm(raw)
                # 解析不出来就当作没传：宁可保留上一次的正确值，也不要把 99:99 存进去
                if parsed:
                    _set(conn, "cfg." + key, parsed)
            if "monthly_salary" in cfg:
                _set(conn, "cfg.monthly_salary", repr(max(0.0, _num(cfg.get("monthly_salary")))))
            if "pay_day" in cfg:
                # 留空存 0：load 时原样交回界面，界面据此把发薪倒计时整行收起
                try:
                    pd = int(round(float(cfg.get("pay_day") or 0)))
                except (TypeError, ValueError):
                    pd = 0
                _set(conn, "cfg.pay_day", str(pd if 1 <= pd <= 31 else 0))
            if "pay_time" in cfg:
                raw_pt = str(cfg.get("pay_time") or "").strip()
                _set(conn, "cfg.pay_time", _hhmm(raw_pt) if raw_pt else "")
            if "theme" in cfg:
                theme = cfg.get("theme")
                _set(conn, "cfg.theme", theme if theme in ("system", "light", "dark") else "system")
            if "demo" in cfg:
                _set(conn, "cfg.demo", "1" if cfg.get("demo") else "0")
            if "demo_offset" in cfg:
                off = _num(cfg.get("demo_offset"))
                off = max(-172800000.0, min(172800000.0, off))
                _set(conn, "cfg.demo_offset", str(int(off)))
            disp = cfg.get("display")
            if isinstance(disp, dict) and "hide_money" in disp:
                _set(conn, "cfg.hide_money", "1" if disp.get("hide_money") else "0")

            week = cfg.get("work_weekdays")
            if isinstance(week, list):
                conn.execute("DELETE FROM weekdays")
                for dow in week:
                    try:
                        d = int(dow)
                    except (TypeError, ValueError):
                        continue
                    if 1 <= d <= 7:
                        conn.execute("INSERT OR IGNORE INTO weekdays(dow) VALUES(?)", (d,))

            if isinstance(cfg.get("holidays"), list) or isinstance(cfg.get("makeup_workdays"), list):
                conn.execute("DELETE FROM holidays")
                for kind, key in (("holiday", "holidays"), ("makeup", "makeup_workdays")):
                    for d in cfg.get(key) or []:
                        d = str(d)
                        if _valid_date(d):
                            conn.execute(
                                "INSERT OR REPLACE INTO holidays(date, kind) VALUES(?, ?)",
                                (d, kind),
                            )

            items = cfg.get("items")
            if isinstance(items, list):
                conn.execute("DELETE FROM items")
                for it in items:
                    try:
                        name = str(it.get("name") or "").strip()
                        price = _num(it.get("price"))
                    except AttributeError:
                        continue
                    if name and price > 0:
                        conn.execute(
                            "INSERT INTO items(name, price) VALUES(?, ?)", (name, price)
                        )

            conn.execute(
                "INSERT INTO meta(key, value) VALUES('ready', '1') "
                "ON CONFLICT(key) DO UPDATE SET value='1'"
            )
        return True
    except sqlite3.Error:
        return False


def reset():
    """重设：清掉配置和备注，schema 留着。"""
    try:
        with _connect() as conn:
            for table in ("settings", "weekdays", "holidays", "items", "notes"):
                conn.execute("DELETE FROM " + table)
            conn.execute("DELETE FROM meta WHERE key='ready'")
        return True
    except sqlite3.Error:
        return False


# ---------------------------------------------------------------- 桌面选项

def load_opts():
    out = {}
    try:
        with _connect() as conn:
            for key, kind in (
                ("autostart_initialized", "bool"),
                ("check_update", "bool"),
                ("notify_schedule", "bool"),
                ("close_exit", "bool"),
            ):
                raw = _get(conn, "desk." + key)
                if raw is None:
                    continue
                out[key] = _flag(raw)
    except sqlite3.Error:
        return {}
    return out


def save_opts(data):
    if not isinstance(data, dict):
        return False
    try:
        with _connect() as conn:
            for k, v in data.items():
                _set(conn, "desk." + str(k), "1" if v is True else "0" if v is False else str(v))
        return True
    except sqlite3.Error:
        return False


def set_opt(key, value):
    return save_opts({key: value})


# ---------------------------------------------------------------- 窗口尺寸

# 和 desktop.py 的 min_size 保持一致：小于这个值一定是脏数据
WIN_MIN_W, WIN_MIN_H = 400, 620


def load_window():
    """上次退出时的窗口大小 (w, h)。没有记录或值不合理就返回 (0, 0)。"""
    try:
        with _connect() as conn:
            w = int(_num(_get(conn, "desk.win_w"), 0))
            h = int(_num(_get(conn, "desk.win_h"), 0))
    except (sqlite3.Error, ValueError, TypeError):
        return (0, 0)
    if w < WIN_MIN_W or h < WIN_MIN_H or w > 10000 or h > 10000:
        return (0, 0)
    return (w, h)


def save_window(width, height):
    """记住窗口大小。值不合理就直接放弃，别把 0×0 写进库。"""
    try:
        w, h = int(width), int(height)
    except (TypeError, ValueError):
        return False
    if w < WIN_MIN_W or h < WIN_MIN_H or w > 10000 or h > 10000:
        return False
    try:
        with _connect() as conn:
            _set(conn, "desk.win_w", str(w))
            _set(conn, "desk.win_h", str(h))
        return True
    except sqlite3.Error:
        return False


# ---------------------------------------------------------------- 日历备注

def notes_in_month(prefix):
    """prefix 形如 2026-11。返回 {日期: 备注}。"""
    text = str(prefix or "")
    if not re.match(r"^\d{4}-\d{2}$", text):
        return {}
    try:
        with _connect() as conn:
            rows = conn.execute(
                "SELECT date, body FROM notes WHERE date LIKE ? ORDER BY date",
                (text + "-%",),
            ).fetchall()
        return {r["date"]: r["body"] for r in rows}
    except sqlite3.Error:
        return {}


def get_note(date):
    try:
        with _connect() as conn:
            row = conn.execute("SELECT body FROM notes WHERE date=?", (str(date),)).fetchone()
        return row["body"] if row else ""
    except sqlite3.Error:
        return ""


def set_note(date, body):
    """空内容 = 删掉这条备注。超过 100 字直接截断，不报错。"""
    day = str(date or "")
    if not _valid_date(day):
        return {"ok": False, "body": ""}
    text = str(body or "").strip()
    if len(text) > NOTE_MAX:
        text = text[:NOTE_MAX]
    try:
        with _connect() as conn:
            if text:
                conn.execute(
                    "INSERT INTO notes(date, body, updated_at) VALUES(?, ?, ?) "
                    "ON CONFLICT(date) DO UPDATE SET body=excluded.body, updated_at=excluded.updated_at",
                    (day, text, time.strftime("%Y-%m-%d %H:%M:%S")),
                )
            else:
                conn.execute("DELETE FROM notes WHERE date=?", (day,))
        return {"ok": True, "body": text}
    except sqlite3.Error:
        return {"ok": False, "body": ""}


def all_notes_count():
    try:
        with _connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
    except sqlite3.Error:
        return 0
