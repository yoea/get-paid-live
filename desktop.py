# -*- coding: utf-8 -*-
"""上班鼓励器 · 桌面版

用 Windows 自带的 WebView2 内核渲染界面，双击即用，不需要装浏览器或运行库。
界面由同目录的 上班鼓励器.html 提供，打包时一并封进 exe。
所有配置只存在本机（%LOCALAPPDATA%\\ShangBanGuLiQi），不联网、不上传任何数据。
"""

import os
import sys

import webview


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

        ctypes.windll.user32.MessageBoxW(None, text, "上班鼓励器", 0x10)
    except Exception:
        pass


def main():
    # 让任务栏把窗口归到本程序名下，而不是并到 python.exe 里
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "Ewing.ShangBanGuLiQi.Desktop"
        )
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
        return

    page = resource_path("上班鼓励器.html")

    try:
        webview.create_window(
            "上班鼓励器",
            page,
            width=1180,
            height=900,
            min_size=(380, 620),
            background_color="#07090d",
            text_select=True,
        )

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


if __name__ == "__main__":
    main()
