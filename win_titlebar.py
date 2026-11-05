# -*- coding: utf-8 -*-
"""把 Windows 原生标题栏染成主题色（DWM）。

pywebview 默认建的是带系统标题栏的窗口，那条黑顶条由 Windows 绘制，网页 CSS 碰不到。
DWMWA_CAPTION_COLOR(35) 改它的背景色，DWMWA_USE_IMMERSIVE_DARK_MODE(20)
决定标题文字与最小/最大/关闭按钮翻黑还是翻白。两者都是 Win11 起才生效，
旧系统或任何失败都静默退回系统默认，不影响窗口本身。

刻意不依赖 pywebview：颜色转换可以单独跑回归用例。
"""
import ctypes
import sys

DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_CAPTION_COLOR = 35


def colorref(color):
    """#RRGGBB -> COLORREF 0x00BBGGRR。DWM 要 BGR 顺序，直接塞 RGB 会变错色。"""
    s = str(color or "").strip().lstrip("#")
    if len(s) != 6:
        return None
    try:
        r, g, b = (int(s[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return None
    return (b << 16) | (g << 8) | r


def apply(hwnd, color, dark=False):
    """给指定顶层窗口染色。成功返回 True，任何失败返回 False。"""
    ref = colorref(color)
    if not hwnd or ref is None or sys.platform != "win32":
        return False
    try:
        from ctypes import wintypes as w
        fn = ctypes.WinDLL("dwmapi").DwmSetWindowAttribute
        fn.argtypes = (w.HWND, w.DWORD, ctypes.c_void_p, w.DWORD)
        fn.restype = ctypes.c_long
        # 浅色主题要黑色文字/按钮，深色主题要白色，先设这个再设背景色
        mode = w.INT(1 if dark else 0)
        fn(w.HWND(hwnd), w.DWORD(DWMWA_USE_IMMERSIVE_DARK_MODE),
           ctypes.cast(ctypes.byref(mode), ctypes.c_void_p), ctypes.sizeof(mode))
        cap = w.DWORD(ref)
        hr = fn(w.HWND(hwnd), w.DWORD(DWMWA_CAPTION_COLOR),
                ctypes.cast(ctypes.byref(cap), ctypes.c_void_p), ctypes.sizeof(cap))
        return hr == 0
    except Exception:
        return False
