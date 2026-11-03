# -*- coding: utf-8 -*-
"""上班鼓励器 · 桌面外壳

界面由同目录的 上班鼓励器.html 提供（Windows 自带的 WebView2 渲染，不打包浏览器内核）。
这一层只管系统集成：

- 开机自动启动（写 HKCU 的 Run 项，首次运行默认就注册）
- 系统托盘图标：悬停显示已上班 / 还剩 / 已赚，左键回到主界面，右键有退出
- 点窗口叉号不退出，而是隐藏到托盘
- 到午休、午休结束、下班时发一条 Windows 原生通知（可在设置里关掉）
- 每次启动查一次 GitHub Releases，有新版本就在界面上提一条

配置、桌面选项、日历备注全部存在 SQLite（store.py，落在 %LOCALAPPDATA%\\ShangBanGuLiQi\\data.db）。
所有数据都在本机，唯一的外部请求是查版本号，可在设置里关掉。
"""

import json
import os
import sys
import threading
import time
import urllib.request
import webbrowser

import webview

import store
from version import VERSION

APP_ID = "Ewing.ShangBanGuLiQi.Desktop"
TITLE = "上班鼓励器"
REPO = "yoea/get-paid-live"
RELEASES_URL = "https://github.com/%s/releases" % REPO
LATEST_API = "https://api.github.com/repos/%s/releases/latest" % REPO

# 开机启动项：每个用户各自一份，不需要管理员权限
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "ShangBanGuLiQi"


def resource_path(name):
    """onefile 打包后资源在临时解压目录，源码运行时就在脚本旁边。"""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def storage_dir():
    """设置存在用户目录：换新版 exe 覆盖安装时，之前填的工资不会丢。"""
    root = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    path = os.path.join(root, "ShangBanGuLiQi")
    try:
        os.makedirs(path, exist_ok=True)
    except OSError:
        path = os.path.expanduser("~")
    return path


# ---------------------------------------------------------------- 桌面选项
# 全部落 SQLite（见 store.py），不再有 desktop.json。

def load_options():
    return store.load_opts()


def save_options(data):
    return store.save_opts(data)


# ---------------------------------------------------------------- 开机启动

def _startup_command():
    """注册表里要写的命令行。打包后指向 exe 自己；源码运行时指向 pythonw + 本文件。"""
    if getattr(sys, "frozen", False):
        return '"%s"' % os.path.abspath(sys.executable)
    pyw = os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "pythonw.exe")
    runner = pyw if os.path.isfile(pyw) else sys.executable
    return '"%s" "%s"' % (runner, os.path.abspath(__file__))


def _autostart_value():
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, RUN_VALUE)
        return str(value or "")
    except Exception:
        return ""


def autostart_enabled():
    return bool(_autostart_value())


def system_is_light():
    """Windows 的应用主题是浅色还是深色（个性化 → 颜色 → 选择默认应用模式）。

    只用于窗口创建时垫的那层底色：界面本身在 HTML 里按用户设置上色，
    这里是让"浅色系统 + 跟随系统"的用户不会先看到一块黑底再跳白。
    """
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        ) as key:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        return bool(int(value))
    except Exception:
        return False


def autostart_set(enabled):
    """返回操作后的真实状态，调用方据此更新界面，而不是假装成功。"""
    try:
        import winreg

        if enabled:
            with winreg.CreateKeyEx(
                winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE
            ) as key:
                winreg.SetValueEx(key, RUN_VALUE, 0, winreg.REG_SZ, _startup_command())
        else:
            try:
                with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE
                ) as key:
                    winreg.DeleteValue(key, RUN_VALUE)
            except OSError:
                pass
    except Exception:
        pass
    return autostart_enabled()


def autostart_sync():
    """首次运行默认就注册开机启动；之后只在"用户还开着但路径变了"时修一下。"""
    opts = load_options()
    if not opts.get("autostart_initialized"):
        opts["autostart_initialized"] = True
        opts.setdefault("check_update", True)
        # 到点提醒默认开着：这是这个程序最主要的"被需要"时刻
        opts.setdefault("notify_schedule", True)
        save_options(opts)
        autostart_set(True)
        return
    current = _autostart_value()
    if current and os.path.normcase(current) != os.path.normcase(_startup_command()):
        # 换了目录或者换了新版本 exe：把注册表里的路径改成现在这个，否则开机启动会指向不存在的文件
        autostart_set(True)


# ---------------------------------------------------------------- 运行状态

class _State(object):
    def __init__(self):
        self.window = None
        self.tray = None
        self.tray_ready = False
        self.quitting = False
        self.status = {}          # 界面每隔几秒推来的快照
        self.status_at = 0.0
        self.update = None        # 查到的版本信息，供界面轮询取走
        self.first_hide = True
        self.notices = {}         # 到点提醒的去重表：{(kind, 日期): True}


state = _State()


def notify(title, message):
    """走系统托盘的气泡（Windows 会把它归到通知中心）。系统关了通知就静默失败。"""
    tray = state.tray
    if tray is None:
        return False
    try:
        tray.notify(message, title)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------- 到点提醒

def notify_enabled():
    return bool(load_options().get("notify_schedule", True))


def _money(value, masked):
    if masked:
        return "****"
    try:
        return "￥{:,.2f}".format(float(value or 0))
    except (TypeError, ValueError):
        return "￥0.00"


def schedule_message(kind, data):
    """把界面推来的数值翻成一句人话。返回 (标题, 正文)，认不出来的类型返回 None。"""
    d = data if isinstance(data, dict) else {}
    masked = bool(d.get("masked"))
    earned = _money(d.get("earned"), masked)
    remain = _money(d.get("remain"), masked)

    if kind == "lunch":
        return "午休时间到了", "先去吃饭 · 上午已经赚了 %s，下午还有 %s" % (earned, remain)
    if kind == "lunch_end":
        return "午休结束", "回来啦 · 今天还差 %s 就收工" % remain
    if kind == "off":
        return "下班了", "今天一共 %s · 收工，别再惦记工作" % earned
    return None


# ---------------------------------------------------------------- 托盘文案

def _dur(sec):
    total = int(max(0, sec))
    if total < 60:
        # 比"不到 1 分钟"更清楚：这里拿到的就是秒数，别含糊
        return "%d 秒" % total
    hours, rest = divmod(total, 3600)
    minutes = rest // 60
    if hours:
        return "%d 小时 %d 分" % (hours, minutes) if minutes else "%d 小时" % hours
    return "%d 分" % minutes


def tray_tooltip():
    """把最后一次快照按当前时刻外推。窗口藏到托盘后界面计时会被系统节流，
    这里自己把「已赚」和「还剩」往前推，悬停看到的就不是几分钟前的旧数。"""
    snap = state.status
    if not snap:
        return "%s v%s" % (TITLE, VERSION)

    # status_at 没设过就别外推，否则会拿 1970 年算出一个荒谬的数
    elapsed = 0.0
    if state.status_at:
        elapsed = max(0.0, min(time.time() - state.status_at, 4 * 3600))
    working = bool(snap.get("working"))
    earned = float(snap.get("earned") or 0)
    worked = float(snap.get("worked") or 0)
    remain = float(snap.get("remain") or 0)

    if working:
        earned += float(snap.get("rate") or 0) * elapsed
        worked += elapsed
        remain = max(0.0, remain - elapsed)

    money = "****" if snap.get("masked") else "￥{:,.2f}".format(earned)
    status = str(snap.get("status") or "")

    if working or status in ("上班中", "小憩"):
        if remain <= 0:
            # 界面可能已被节流到一分钟才推一次，跨过下班点时自己把话说清楚
            return "已经到点了 · 今日 %s" % money
        return "已上班 %s · 还有 %s · %s" % (_dur(worked), _dur(remain), money)
    if status == "已下班":
        return "今天下班了 · 今日 %s" % money
    if status == "未开工":
        return "还没开工 · 今日 %s" % money
    if status == "休息":
        return "今天休息 · 今日 %s" % money
    return "%s · %s" % (status or TITLE, money)


def _tooltip_loop():
    while not state.quitting:
        tray = state.tray
        if tray is not None:
            try:
                text = tray_tooltip()
                if tray.title != text:
                    tray.title = text
            except Exception:
                pass
        time.sleep(3)


def _tray_image():
    try:
        from PIL import Image

        img = Image.open(resource_path("app.ico"))
        img.load()
        return img.convert("RGBA")
    except Exception:
        # 图标读不到也要有托盘，画个纯色圆点顶上
        try:
            from PIL import Image, ImageDraw

            img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
            ImageDraw.Draw(img).ellipse((5, 5, 59, 59), fill=(255, 200, 87, 255))
            return img
        except Exception:
            return None


# ---------------------------------------------------------------- 窗口动作

def show_window():
    win = state.window
    if win is None:
        return
    try:
        win.show()
    except Exception:
        pass


def quit_app():
    """真正的退出：先立旗子，再关窗口，closing 事件才不会又把它塞回托盘。"""
    state.quitting = True
    win = state.window
    if win is None:
        return
    try:
        win.destroy()
    except Exception:
        pass


def start_tray():
    try:
        import pystray
    except Exception:
        return False

    image = _tray_image()
    if image is None:
        return False

    def on_open(icon=None, item=None):
        show_window()

    def on_toggle_autostart(icon=None, item=None):
        autostart_set(not autostart_enabled())
        try:
            icon.update_menu()
        except Exception:
            pass

    def on_check_update(icon=None, item=None):
        threading.Thread(
            target=check_update, kwargs={"manual": True}, daemon=True
        ).start()

    def on_quit(icon=None, item=None):
        quit_app()

    try:
        menu = pystray.Menu(
            pystray.MenuItem("打开主界面", on_open, default=True),
            pystray.MenuItem(
                "开机自动启动",
                on_toggle_autostart,
                checked=lambda item: autostart_enabled(),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("检查更新", on_check_update),
            pystray.MenuItem("退出", on_quit),
        )
        tray = pystray.Icon("shangban-guliqi", image, TITLE, menu)
        tray.run_detached()
    except Exception:
        return False

    state.tray = tray
    state.tray_ready = True
    threading.Thread(target=_tooltip_loop, daemon=True).start()
    return True


def stop_tray():
    tray = state.tray
    state.tray = None
    state.tray_ready = False
    if tray is None:
        return
    try:
        tray.stop()
    except Exception:
        pass


def on_closing():
    """拦截叉号。

    注意 pywebview 的约定是反的：handler 返回 False 才表示"不许关"
    （Event.set() 只有在有 handler 返回 False 时才返回 True，winforms 拿到 True 就 Cancel）。
    所以下面"放行"返回 True，"拦下"返回 False。
    """
    if state.quitting:
        return True  # 走的是托盘里的「退出」，真关
    if not state.tray_ready:
        # 托盘没起来就别拦人，否则窗口关不掉也没地方点退出
        return True
    win = state.window
    try:
        if win is not None:
            win.hide()
    except Exception:
        return True
    if state.first_hide:
        state.first_hide = False
        notify("还在后台跑", "点托盘图标回到界面，右键菜单里有「退出」。")
    return False


# ---------------------------------------------------------------- 检查更新

def _ver_tuple(text):
    parts = []
    for seg in str(text).strip().lstrip("vV").split("."):
        digits = ""
        for ch in seg:
            if ch.isdigit():
                digits += ch
            else:
                break
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts)


def check_update(manual=False):
    """查 GitHub 上最新一个 Release。失败一律静默：连不上网不该弹框骚扰人。"""
    if not manual and not load_options().get("check_update", True):
        return None

    try:
        req = urllib.request.Request(
            LATEST_API,
            headers={
                "User-Agent": "ShangBanGuLiQi/" + VERSION,
                "Accept": "application/vnd.github+json",
            },
        )
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        tag = str(data.get("tag_name") or "")
        newer = _ver_tuple(tag) > _ver_tuple(VERSION)
        info = {
            "current": VERSION,
            "tag": tag,
            "newer": newer,
            "url": (data.get("html_url") or RELEASES_URL) if newer else "",
            # 界面点版本号查更新时，靠这个时间戳判断"这次查完了"
            "at": time.time(),
        }
    except Exception:
        if manual:
            notify("检查更新失败", "网络不通，待会儿再点一次。")
        return None

    state.update = info
    if manual:
        if info["newer"]:
            notify("有新版 " + info["tag"], "打开主界面就能看到下载入口。")
        else:
            notify("已是最新版本", "v" + VERSION)
    return info


def _delayed_update_check():
    time.sleep(4)  # 等窗口先画出来，别跟启动抢带宽
    check_update()


# ---------------------------------------------------------------- 给界面的接口

class Api(object):
    """界面通过 window.pywebview.api 调这些方法。

    刻意都做成"取数据/写状态"的短操作：所有 UI 动作都发生在界面自己的线程里，
    只有 show/hide/destroy 从托盘线程发起，而 pywebview 对这三个是线程安全的。
    """

    def get_settings(self):
        opts = load_options()
        return {
            "version": VERSION,
            "autostart": autostart_enabled(),
            "check_update": bool(opts.get("check_update", True)),
            "notify_schedule": bool(opts.get("notify_schedule", True)),
            "update": state.update,
            "db": store.path() or "",
        }

    # ---- 数据存储（SQLite）。界面启动时整份拉一次，保存时整份写回。
    def get_state(self):
        return {
            "version": VERSION,
            "ready": store.has_saved(),
            "cfg": store.load_cfg(),
            "opts": self.get_settings(),
        }

    def save_cfg(self, cfg):
        return store.save_cfg(cfg)

    def reset_store(self):
        return store.reset()

    def get_notes(self, prefix):
        return store.notes_in_month(prefix)

    def set_note(self, payload):
        data = payload if isinstance(payload, dict) else {}
        return store.set_note(data.get("date"), data.get("body"))

    def set_autostart(self, enabled):
        ok = autostart_set(bool(enabled))
        tray = state.tray
        if tray is not None:
            try:
                tray.update_menu()
            except Exception:
                pass
        return ok

    def set_check_update(self, enabled):
        opts = load_options()
        opts["check_update"] = bool(enabled)
        opts["autostart_initialized"] = True
        save_options(opts)
        return bool(enabled)

    def set_notify_schedule(self, enabled):
        opts = load_options()
        opts["notify_schedule"] = bool(enabled)
        opts["autostart_initialized"] = True
        save_options(opts)
        return bool(enabled)

    def notify_event(self, payload):
        """界面在跨过午休/下班时点调这里。界面只报"发生了什么"，措辞交给这边，
        这样通知文案和托盘悬停的格式是一致的。"""
        if not notify_enabled():
            return False
        data = payload if isinstance(payload, dict) else {}
        kind = str(data.get("kind") or "")
        text = schedule_message(kind, data)
        if text is None:
            return False
        # 双保险：界面已按天去重，这里再挡一次进程内的重复调用
        key = (kind, time.strftime("%Y-%m-%d"))
        if state.notices.get(key):
            return False
        ok = notify(text[0], text[1])
        if ok:
            state.notices[key] = True
        return ok

    def push_status(self, snap):
        if isinstance(snap, dict):
            state.status = snap
            state.status_at = time.time()
            return True
        return False

    def poll_update(self):
        return state.update

    def check_update_now(self):
        threading.Thread(
            target=check_update, kwargs={"manual": True}, daemon=True
        ).start()
        return True

    def open_url(self, url):
        text = str(url or "")
        if text.startswith("https://github.com/") or text.startswith(
            "https://api.github.com/"
        ):
            try:
                webbrowser.open(text)
                return True
            except Exception:
                return False
        return False

    def hide_window(self):
        win = state.window
        if win is None:
            return False
        try:
            win.hide()
            return True
        except Exception:
            return False

    def quit(self):
        threading.Thread(target=quit_app, daemon=True).start()
        return True


# ---------------------------------------------------------------- 入口

# WebView2 运行库的固定产品 ID（微软公开，Edge 更新程序用它登记版本）
_WEBVIEW2_GUID = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
_WEBVIEW2_KEYS = (
    r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients" + "\\" + _WEBVIEW2_GUID,
    r"SOFTWARE\Microsoft\EdgeUpdate\Clients" + "\\" + _WEBVIEW2_GUID,
)


def webview2_ready():
    """Win11 和大部分 Win10 自带 WebView2；极老的 Win10 可能没有，得先告诉人。

    检测放宽松：注册表任一处有版本号，或磁盘上有 msedgewebview2.exe 都算有。
    """
    try:
        import winreg

        for path in _WEBVIEW2_KEYS:
            for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                try:
                    with winreg.OpenKey(root, path) as k:
                        ver, _ = winreg.QueryValueEx(k, "pv")
                        if ver and ver != "0.0.0.0":
                            return True
                except OSError:
                    continue
    except Exception:
        pass

    for base in (
        os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                     "Microsoft", "EdgeWebView", "Application"),
        os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"),
                     "Microsoft", "EdgeWebView", "Application"),
    ):
        try:
            for name in os.listdir(base):
                if os.path.isfile(os.path.join(base, name, "msedgewebview2.exe")):
                    return True
        except OSError:
            continue
    return False


def alert(text):
    """程序是 --windowed 打包的，没有控制台，只能用原生弹窗把话说清楚。"""
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, text, TITLE, 0x10)
    except Exception:
        pass


def main():
    # 让任务栏把窗口归到本程序名下，而不是并到 python.exe 里
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except Exception:
        pass

    if not webview2_ready():
        alert(
            "启动失败：这台电脑缺少 Microsoft Edge WebView2 运行库。\n\n"
            "界面是用系统自带的这个组件渲染的，缺了就打不开。\n"
            "Windows 11 一般自带；旧版 Windows 10 需要装一次（免费，约 2MB）：\n\n"
            "https://go.microsoft.com/fwlink/p/?LinkId=2124703\n\n"
            "装完再双击本程序即可。"
        )
        return 1

    store.init(storage_dir())   # 先有库，后面的读取才有着落
    autostart_sync()

    try:
        window = webview.create_window(
            TITLE,
            resource_path("上班鼓励器.html"),
            width=1180,
            height=900,
            min_size=(380, 620),
            background_color="#f5f6f8" if system_is_light() else "#07090d",
            text_select=True,
            js_api=Api(),
        )
        state.window = window
        window.events.closing += on_closing

        start_tray()
        threading.Thread(target=_delayed_update_check, daemon=True).start()

        webview.start(
            # 用本地 http 提供页面：file:// 下 localStorage 会被内核判为不安全而不给用
            http_server=True,
            # 必须关掉隐私模式，否则每次启动都当作全新用户，设置留不住
            private_mode=False,
            storage_path=storage_dir(),
            debug=False,
        )
    except Exception as exc:  # 兜底，别让窗口一闪就没了
        alert("启动时出错：\n\n" + repr(exc))
        return 1
    finally:
        state.quitting = True
        stop_tray()
    return 0


if __name__ == "__main__":
    sys.exit(main())
