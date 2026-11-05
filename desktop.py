# -*- coding: utf-8 -*-
"""上班鼓励器 · 桌面外壳

界面由同目录的 上班鼓励器.html 提供（Windows 自带的 WebView2 渲染，不打包浏览器内核）。
那份 html 是 merge.py 从 src/ 合出来的生成物；界面源码在 src/（index.html / app.css /
engine.js / ui.js），改界面去改 src/。
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
    """开机启动默认关闭（要不要随系统启动由用户自己在设置里勾）。

    已经用过老版本的用户不受影响：库里记着 autostart_initialized，这里只在
    "用户开着自启但 exe 路径变了" 时把注册表里的路径修一下，其余一律不动
    ——开没开、什么时候开的，都以注册表里的现状为准。"""
    opts = load_options()
    if not opts.get("autostart_initialized"):
        opts["autostart_initialized"] = True
        opts.setdefault("check_update", True)
        # 到点提醒默认开着：这是这个程序最主要的"被需要"时刻
        opts.setdefault("notify_schedule", True)
        save_options(opts)
        autostart_set(False)    # 保险起见清一下，正常情况下本来就没有
        return
    current = _autostart_value()
    if current and os.path.normcase(current) != os.path.normcase(_startup_command()):
        # 换了目录或者换了新版本 exe：把注册表里的路径改成现在这个，否则开机启动会指向不存在的文件
        autostart_set(True)


# ---------------------------------------------------------------- 单实例
# 同一时刻只允许一份在跑。再双击时按版本号决定谁留下：
#   跑着的那份 >= 自己（同版本或更新）→ 把它的窗口叫到前面，自己立刻退出
#   跑着的那份 <  自己（自己更新）    → 请它退出，自己接手
#
# 全靠命名的内核对象，不落文件、不占端口，进程一死内核自动回收：
#   Local\ShangBanGuLiQi.single   互斥量：名字在就说明有一份活着
#   Local\ShangBanGuLiQi.info     共享内存：对方把版本 / pid / 窗口句柄写在里面
#   Local\ShangBanGuLiQi.quit     事件：上面的新版用它请下面对旧版体面退出
#
# 1.4.3 及更早的版本不认这套协议（既不建互斥量，也没有 info），对它们只能靠
# 窗口标题认人，等一小会儿之后直接结束进程。配置写 SQLite 是单条语句立刻落盘，
# 强杀不会丢已经保存的东西。

MUTEX_NAME = "Local\\ShangBanGuLiQi.single"
INFO_NAME = "Local\\ShangBanGuLiQi.info"
QUIT_NAME = "Local\\ShangBanGuLiQi.quit"

_ERR_ALREADY_EXISTS = 183
_SW_SHOW = 5
_SW_RESTORE = 9
_PROCESS_TERMINATE = 0x0001
_SYNCHRONIZE = 0x00100000
_EVENT_MODIFY_STATE = 0x0002
_FILE_MAP_WRITE = 0x0002
_FILE_MAP_READ = 0x0004
_PAGE_READWRITE = 0x04
_INFINITE = 0xFFFFFFFF

_state_inst = {}      # 本进程持有的内核对象；进程退出时全部自动释放
_win32 = None


def _win():
    """把用到的 Win32 调用声明一遍（只做一次）。

    必须显式写 restype/argtypes：ctypes 默认把返回值当 C int，64 位下句柄的
    高位会被截掉，后面每个调用都会拿着一个残缺的句柄失败。
    """
    global _win32
    if _win32 is not None:
        return _win32

    import ctypes
    from ctypes import wintypes as w

    k = ctypes.WinDLL("kernel32", use_last_error=True)
    u = ctypes.WinDLL("user32", use_last_error=True)

    k.CreateMutexW.argtypes = (w.LPVOID, w.BOOL, w.LPCWSTR)
    k.CreateMutexW.restype = w.HANDLE
    k.CreateFileMappingW.argtypes = (w.HANDLE, w.LPVOID, w.DWORD, w.DWORD, w.DWORD, w.LPCWSTR)
    k.CreateFileMappingW.restype = w.HANDLE
    k.OpenFileMappingW.argtypes = (w.DWORD, w.BOOL, w.LPCWSTR)
    k.OpenFileMappingW.restype = w.HANDLE
    k.MapViewOfFile.argtypes = (w.HANDLE, w.DWORD, w.DWORD, w.DWORD, ctypes.c_size_t)
    k.MapViewOfFile.restype = w.LPVOID
    k.UnmapViewOfFile.argtypes = (w.LPVOID,)
    k.CreateEventW.argtypes = (w.LPVOID, w.BOOL, w.BOOL, w.LPCWSTR)
    k.CreateEventW.restype = w.HANDLE
    k.OpenEventW.argtypes = (w.DWORD, w.BOOL, w.LPCWSTR)
    k.OpenEventW.restype = w.HANDLE
    k.SetEvent.argtypes = (w.HANDLE,)
    k.SetEvent.restype = w.BOOL
    k.CloseHandle.argtypes = (w.HANDLE,)
    k.OpenProcess.argtypes = (w.DWORD, w.BOOL, w.DWORD)
    k.OpenProcess.restype = w.HANDLE
    k.WaitForSingleObject.argtypes = (w.HANDLE, w.DWORD)
    k.WaitForSingleObject.restype = w.DWORD
    k.TerminateProcess.argtypes = (w.HANDLE, w.UINT)
    k.TerminateProcess.restype = w.BOOL
    u.FindWindowW.argtypes = (w.LPCWSTR, w.LPCWSTR)
    u.FindWindowW.restype = w.HWND
    u.FindWindowExW.argtypes = (w.HWND, w.HWND, w.LPCWSTR, w.LPCWSTR)
    u.FindWindowExW.restype = w.HWND
    u.GetWindowThreadProcessId.argtypes = (w.HWND, ctypes.POINTER(w.DWORD))
    u.GetWindowThreadProcessId.restype = w.DWORD
    u.ShowWindow.argtypes = (w.HWND, ctypes.c_int)
    u.IsIconic.argtypes = (w.HWND,)
    u.IsIconic.restype = w.BOOL
    u.BringWindowToTop.argtypes = (w.HWND,)
    u.SetForegroundWindow.argtypes = (w.HWND,)

    _win32 = {"ct": ctypes, "w": w, "k": k, "u": u}
    return _win32


def _window_pids(exclude_self=True):
    """标题是「上班鼓励器」的顶层窗口 [(hwnd, pid), ...]。

    FindWindowExW 带上前一个句柄就是「接着往后找同标题的」，比 EnumWindows
    加回调省事，也不用担心回调被 GC 掉。隐藏到托盘的窗口也能找到。
    """
    A = _win()
    u, k = A["u"], A["k"]
    ct, w = A["ct"], A["w"]
    me = os.getpid()
    out = []
    hwnd = u.FindWindowW(None, TITLE)
    while hwnd:
        pid = w.DWORD(0)
        u.GetWindowThreadProcessId(hwnd, ct.byref(pid))
        if pid.value and (not exclude_self or pid.value != me):
            out.append((hwnd, pid.value))
        hwnd = u.FindWindowExW(None, hwnd, None, TITLE)
    return out


def _own_hwnd():
    A = _win()
    u, k = A["u"], A["k"]
    ct, w = A["ct"], A["w"]
    me = os.getpid()
    hwnd = u.FindWindowW(None, TITLE)
    while hwnd:
        pid = w.DWORD(0)
        u.GetWindowThreadProcessId(hwnd, ct.byref(pid))
        if pid.value == me:
            return hwnd
        hwnd = u.FindWindowExW(None, hwnd, None, TITLE)
    return 0


def _read_info():
    """读对方写在共享内存里的 {ver, pid, hwnd}；没有或者读不出来返回 None。"""
    try:
        A = _win()
        k, ct = A["k"], A["ct"]
        h = k.OpenFileMappingW(_FILE_MAP_READ, False, INFO_NAME)
        if not h:
            return None
        try:
            addr = k.MapViewOfFile(h, _FILE_MAP_READ, 0, 0, 0)
            if not addr:
                return None
            try:
                raw = ct.string_at(addr, 512).split(b"\x00")[0]
                if not raw:
                    return None
                data = json.loads(raw.decode("utf-8", "replace"))
            finally:
                k.UnmapViewOfFile(addr)
        finally:
            k.CloseHandle(h)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _publish(version, hwnd=0):
    """把自己的版本 / pid / 窗口句柄写进共享内存。

    窗口还没建出来时先写 hwnd=0 —— 版本号才是判断谁该留下的依据，
    窗口句柄只是用来"叫到前面"，晚一点补上不影响仲裁。
    """
    try:
        A = _win()
        k, ct = A["k"], A["ct"]
        addr = _state_inst.get("addr")
        if not addr:
            h = k.CreateFileMappingW(None, None, _PAGE_READWRITE, 0, 4096, INFO_NAME)
            if not h:
                return
            addr = k.MapViewOfFile(h, _FILE_MAP_WRITE | _FILE_MAP_READ, 0, 0, 4096)
            if not addr:
                k.CloseHandle(h)
                return
            _state_inst["map"] = h
            _state_inst["addr"] = addr
        raw = json.dumps(
            {"ver": version, "pid": os.getpid(), "hwnd": int(hwnd or 0)}
        ).encode("utf-8")
        ct.memset(addr, 0, 256)
        ct.memmove(addr, raw, len(raw))
    except Exception:
        pass


def _publish_when_ready():
    """窗口是 pywebview 异步建出来的，建好之后把句柄补进共享内存。"""

    def run():
        for _ in range(150):
            hwnd = _own_hwnd()
            if hwnd:
                _publish(VERSION, hwnd)
                return
            time.sleep(0.1)

    threading.Thread(target=run, daemon=True).start()


def _activate(hwnd):
    """把跑着的那一份叫到前面：它可能藏在托盘里、也可能最小化了。"""
    if not hwnd:
        return
    try:
        A = _win()
        u = A["u"]
        if u.IsIconic(hwnd):
            u.ShowWindow(hwnd, _SW_RESTORE)
        else:
            u.ShowWindow(hwnd, _SW_SHOW)
        u.BringWindowToTop(hwnd)
        if not u.SetForegroundWindow(hwnd):
            # 后台进程抢前台会被系统拦下，换未文档化的老接口再试一次
            try:
                u.SwitchToThisWindow(hwnd, True)
            except Exception:
                pass
    except Exception:
        pass


def _evict(peers, graceful):
    """请对方退出。

    graceful=True（对方是认协议的新版本）：先发退出信号，让它走正常退出流程，
    托盘图标也收得干净。
    graceful=False（对方是 1.4.3 及更早）：它不会响应，等一小会儿直接结束进程。
    """
    A = _win()
    k = A["k"]
    if graceful:
        ev = k.OpenEventW(_EVENT_MODIFY_STATE, False, QUIT_NAME)
        if ev:
            k.SetEvent(ev)
            k.CloseHandle(ev)

    procs = []
    for _hwnd, pid in peers:
        h = k.OpenProcess(_SYNCHRONIZE | _PROCESS_TERMINATE, False, pid)
        if h:
            procs.append(h)
    deadline = time.time() + (2.5 if graceful else 0.35)
    while procs and time.time() < deadline:
        if all(k.WaitForSingleObject(h, 0) == 0 for h in procs):
            break
        time.sleep(0.08)
    for h in procs:
        if k.WaitForSingleObject(h, 0) != 0:
            k.TerminateProcess(h, 0)
            k.WaitForSingleObject(h, 1200)
        k.CloseHandle(h)


def single_instance_gate(version=VERSION):
    """启动前的仲裁。True = 继续启动；False = 已经交给别的那份，本进程该退出。

    任何一步出错都放行：宁可多开一个，也不能让人双击了打不开。
    """
    try:
        A = _win()
        k, ct = A["k"], A["ct"]
        mutex = k.CreateMutexW(None, True, MUTEX_NAME)
        exists = ct.get_last_error() == _ERR_ALREADY_EXISTS
        _state_inst["mutex"] = mutex

        peers = _window_pids()
        if mutex and not exists and not peers:
            _publish(version)          # 抢到位置：先登记版本，窗口建好再补句柄
            return True

        info = _read_info()
        if info is None and exists and not peers:
            # 另一份刚抢到互斥量、窗口还没出来：等它把版本写进共享内存
            for _ in range(25):
                time.sleep(0.08)
                info = _read_info()
                if info:
                    break
                peers = _window_pids()
                if peers:
                    break

        peer_ver = str((info or {}).get("ver") or "")
        if peer_ver:
            mine, theirs = _ver_tuple(version), _ver_tuple(peer_ver)
            replace = mine > theirs
        else:
            # 读不到版本 = 1.4.3 及更早，一定比现在这份旧
            replace = True

        if replace:
            _evict(peers, graceful=bool(peer_ver))
            _publish(version)
            return True

        # 同版本或对方更新：把它的窗口叫出来，自己安静退场
        hwnd = int((info or {}).get("hwnd") or 0)
        if not hwnd and peers:
            hwnd = peers[0][0]
        _activate(hwnd)
        return False
    except Exception:
        return True


def _start_quit_watcher():
    """等新版发来「让位」信号，收到就走正常退出（托盘、通知都收干净）。"""
    try:
        A = _win()
        k = A["k"]
        ev = k.CreateEventW(None, False, False, QUIT_NAME)
        if not ev:
            return
    except Exception:
        return
    _state_inst["quit"] = ev

    def run():
        # 窗口还没建好就收到信号也不能立刻销毁，等它建好再说
        for _ in range(400):
            if state.window is not None:
                break
            time.sleep(0.05)
        try:
            k.WaitForSingleObject(ev, _INFINITE)
        except Exception:
            return
        quit_app()

    threading.Thread(target=run, daemon=True).start()


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
        self.notices = {}         # 到点提醒的去重表：{(kind, 日期): True}
        self.win_saved = False    # 本次启动用的是上次记住的尺寸（是就不再自动收窗口）
        self.fit_size = None      # 程序自己 fit 出来的尺寸，用来区分"用户拖的"
        self.fit_until = 0.0      # 程序调 resize 后的忽略期，期间的 resized 事件不算数
        self.size_timer = None    # 尺寸落盘的 debounce 定时器


state = _State()


# ---------------------------------------------------------------- 窗口尺寸的记忆

def _screen_size():
    """主屏分辨率（物理像素）。pywebview.screens 要等 start() 之后才有，这里不能等。"""
    try:
        import ctypes

        u = ctypes.windll.user32
        return int(u.GetSystemMetrics(0)), int(u.GetSystemMetrics(1))
    except Exception:
        return (0, 0)


def _remember_size():
    """把当前窗口大小写进库。

    只有当尺寸不是"程序自己 fit 出来的那个"才记——否则用户从来没拖过窗口，
    每次启动都会被记成一次"用户尺寸"，之后就永远不再自动适配内容高度了。
    """
    win = state.window
    if win is None:
        return False
    try:
        w, h = int(win.width), int(win.height)
    except Exception:
        return False
    if state.fit_size and (w, h) == state.fit_size:
        return False
    return store.save_window(w, h)


def _remember_size_soon():
    old = state.size_timer
    if old is not None:
        try:
            old.cancel()
        except Exception:
            pass
    t = threading.Timer(0.8, _remember_size)   # 拖边框时每像素一个事件，等停手再写
    t.daemon = True
    state.size_timer = t
    t.start()


def on_resized(*_args):
    # 程序自己 resize（fit_window）引起的 WM_SIZE 不算用户行为
    if time.time() < state.fit_until:
        return
    _remember_size_soon()


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


def register_aumid_display():
    """把 AUMID 的显示名写进注册表（HKCU，只动本用户）。

    通知中心左上角的"发件人"名字解析自 AUMID 的 DisplayString；从没注册过
    的话，Windows 就把 AUMID 原串亮出来——看着就是一串 ewing.xxx。
    写上 TITLE 之后通知一律显示成「上班鼓励器」。写一次长期有效，失败
    静默：顶多名字难看，不影响任何功能。
    """
    try:
        import winreg

        key_path = r"Software\Classes\AppUserModelId" + "\\" + APP_ID
        with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.SetValueEx(key, "DisplayString", 0, winreg.REG_SZ, TITLE)
    except Exception:
        pass


# ---------------------------------------------------------------- 到点提醒

def notify_enabled():
    return bool(load_options().get("notify_schedule", True))


def close_exit_enabled():
    """点叉号是直接退出（True）还是缩进托盘继续跑（False，默认）。"""
    return bool(load_options().get("close_exit", False))


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
    _remember_size()
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

    收进托盘时静默处理，不弹"还在后台跑"之类的通知——关窗口是用户的主动
    操作，行为在设置里写得明明白白，再弹一条反而是骚扰。
    """
    if state.quitting:
        return True  # 走的是托盘里的「退出」，真关
    if not state.tray_ready:
        # 托盘没起来就别拦人，否则窗口关不掉也没地方点退出
        return True
    if close_exit_enabled():
        # 设置里选了「点叉号直接退出」：收好尺寸、托盘一起收干净，放行关窗
        state.quitting = True
        _remember_size()
        stop_tray()
        return True
    win = state.window
    try:
        if win is not None:
            _remember_size()      # 收进托盘前把尺寸记下，下次打开还是这么大
            win.hide()
    except Exception:
        return True
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


def check_update(manual=False, quiet=False, silent=False):
    """查 GitHub 上最新一个 Release。失败一律静默：连不上网不该弹框骚扰人。

    quiet=True 是"打开设置时顺手看一眼"用的：照样联网查，但不发系统通知
    （用户只是打开设置，不该每次都被弹一下）。
    silent=True 是"界面里点版本号手动查"用的：结果完全由界面自己呈现
    （有新版弹模态框、已是最新弹 toast），系统通知反而多余。
    托盘菜单里的"检查更新"仍走系统通知——那个入口没有界面可看。
    """
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
        if manual and not quiet and not silent:
            notify("检查更新失败", "网络不通，待会儿再点一次。")
        return None

    state.update = info
    if manual and not quiet and not silent:
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
        # 只把"根目录"交给界面：data.db 是里面的一个文件，用户要的是能找到它的地方
        data_dir = os.path.dirname(store.path() or "") or storage_dir()
        return {
            "version": VERSION,
            "autostart": autostart_enabled(),
            "check_update": bool(opts.get("check_update", True)),
            "notify_schedule": bool(opts.get("notify_schedule", True)),
            "close_exit": bool(opts.get("close_exit", False)),
            "update": state.update,
            "data_dir": data_dir,
        }

    # ---- 数据存储（SQLite）。界面启动时整份拉一次，保存时整份写回。
    def get_state(self):
        return {
            "version": VERSION,
            "ready": store.has_saved(),
            "cfg": store.load_cfg(),
            "opts": self.get_settings(),
            "win_saved": state.win_saved,
        }

    def save_cfg(self, cfg):
        return store.save_cfg(cfg)

    def reset_store(self):
        return store.reset()

    def get_notes(self, prefix):
        return store.notes_in_month(prefix)

    def fit_window(self, height):
        """把窗口高度收到内容实际需要的大小（页面启动后量好报上来）。

        初始 900 高是固定值，内容用不满时底部空一截。只调高度不动宽度，
        夹在 min_size 和屏幕高度之间；和当前高度差得太小就不折腾，
        避免内容一像素一像素长高时窗口跟着抖。

        用户自己拖过窗口（库里有尺寸）就完全不碰——他要多大就多大。
        """
        if state.win_saved:
            return "user size"
        try:
            h = int(round(float(height)))
        except (TypeError, ValueError):
            return "bad height"
        win = state.window
        if win is None:
            return "no window"
        max_h = 1100
        try:
            scr = webview.screens[0]
            max_h = max(620, int(scr.height) - 80)
        except Exception:
            pass
        h = max(620, min(h, max_h))
        # 目标尺寸先记下来：退出时如果窗口仍是这个尺寸，说明不是用户拖的，不落库
        state.fit_size = (int(win.width), h)
        if abs(h - win.height) < 16:
            return "close enough"
        try:
            state.fit_until = time.time() + 2.5
            win.resize(win.width, h)
        except Exception:
            return "resize failed"
        return "ok"

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

    def set_close_exit(self, enabled):
        """点叉号：True=直接退出，False=缩进托盘（默认）。随设置面板的
        「保存」一起落库。"""
        opts = load_options()
        opts["close_exit"] = bool(enabled)
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
        # silent：界面自己会弹模态框/toast 呈现结果，别再发系统通知
        threading.Thread(
            target=check_update, kwargs={"manual": True, "silent": True}, daemon=True
        ).start()
        return True

    def check_update_quiet(self):
        """设置面板打开时顺手查一次：不弹通知，两分钟内查过就直接复用结果。"""
        info = state.update
        if info and time.time() - float(info.get("at") or 0) < 120:
            fresh = dict(info)
            fresh["at"] = time.time()     # 换个时间戳，界面才知道"这次查完了"
            state.update = fresh
            return True
        threading.Thread(
            target=check_update, kwargs={"manual": True, "quiet": True}, daemon=True
        ).start()
        return True

    def open_data_dir(self):
        """在资源管理器里打开数据目录（配置、备注都在这个文件夹里）。"""
        path = os.path.dirname(store.path() or "") or storage_dir()
        try:
            os.startfile(path)          # 仅 Windows 有；其它平台直接走异常分支
            return True
        except Exception:
            try:
                webbrowser.open("file:///" + path.replace("\\", "/"))
                return True
            except Exception:
                return False

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
    # 通知中心里的"发件人"显示成「上班鼓励器」，而不是一串 AUMID 原文
    register_aumid_display()

    # 先做单实例仲裁：已经有旧的一份在跑就把它换掉，同版本/更新的就把它的窗口
    # 叫到前面。这一步放最前面，免得第二个实例白弹一堆检查框。
    if not single_instance_gate():
        return 0

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

    # 上次退出时的窗口大小；没有就用默认值。屏幕变小了就把尺寸收回屏内，
    # 免得上限改过分辨率后窗口一半在屏幕外面。
    win_w, win_h = store.load_window()
    state.win_saved = bool(win_w and win_h)
    if state.win_saved:
        sw, sh = _screen_size()
        if sw and sh:
            win_w = max(400, min(win_w, sw - 40))
            win_h = max(620, min(win_h, sh - 80))
    else:
        win_w, win_h = 1180, 900

    try:
        window = webview.create_window(
            TITLE,
            resource_path("上班鼓励器.html"),
            width=win_w,
            height=win_h,
            min_size=(380, 620),
            background_color="#f5f6f8" if system_is_light() else "#07090d",
            text_select=True,
            js_api=Api(),
        )
        state.window = window
        window.events.closing += on_closing
        try:
            window.events.resized += on_resized   # 拖一下边框就记下来（debounce 0.8s）
        except Exception:
            pass

        _start_quit_watcher()      # 认「让位」信号，新版本要接手时走正常退出
        _publish_when_ready()      # 窗口建好后把句柄补进共享内存

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
