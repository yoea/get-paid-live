# -*- coding: utf-8 -*-
"""把 上班鼓励器 打成单文件 exe，产物文件名带版本号。

本地用：双击 打包exe.bat（会自动准备 .venv-build 环境）
CI 用：装好 pywebview / pyinstaller 后直接 python build.py
"""

import os
import subprocess
import sys

from version import VERSION

# Windows 的 CI 上 stdout 默认是 cp1252，print 中文会直接抛 UnicodeEncodeError。
# 这里强制 UTF-8，并透传给 PyInstaller 子进程（它也要打印中文文件名）。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
NAME = "上班鼓励器"

# exe 文件名必须是 ASCII：GitHub Release 的附件名只保留 [A-Za-z0-9._-]，
# 中文字符会被静默删掉（"上班鼓励器-v1.1.0.exe" 会变成 "-v1.1.0.exe"）。
# 中文名保留在窗口标题和 exe 的文件属性里，不影响用户看到的名字。
EXE_BASE = "GetPaidLive"

# 版本号来自 version.py（唯一来源）：exe 文件名、文件属性、Release 标签都跟着它走。
# 界面右下角的签名是 HTML 里的静态文字，打包时会核对（见 check_html_version）。
AUTHOR = "Ethan"

EXE_NAME = "%s-v%s" % (EXE_BASE, VERSION)
INTERNAL_NAME = "ShangBanGuLiQi"

VERSION_TEMPLATE = """VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=%(ver)s,
    prodvers=%(ver)s,
    mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0,0)
  ),
  kids=[
    StringFileInfo([
      StringTable('080404B0', [
        StringStruct('CompanyName', '%(author)s'),
        StringStruct('FileDescription', '上班鼓励器 - 实时显示上班赚了多少钱'),
        StringStruct('FileVersion', '%(vs)s'),
        StringStruct('InternalName', '%(internal)s'),
        StringStruct('LegalCopyright', 'Copyright (C) 2026 %(author)s'),
        StringStruct('OriginalFilename', '%(exe)s.exe'),
        StringStruct('ProductName', '上班鼓励器'),
        StringStruct('ProductVersion', '%(vs)s')
      ])
    ]),
    VarFileInfo([VarStruct('Translation', [2052, 1200])])
  ]
)
"""


def write_version_file():
    """生成 exe 的文件属性：右键「属性 - 详细信息」里能看到作者和版本。"""
    parts = [int(x) for x in VERSION.split(".")] + [0, 0, 0, 0]
    text = VERSION_TEMPLATE % {
        "ver": tuple(parts[:4]),
        "vs": VERSION,
        "author": AUTHOR,
        "internal": INTERNAL_NAME,
        "exe": EXE_NAME,
    }
    path = os.path.join(HERE, ".version_info.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def check_html_version():
    """界面里的版本号是硬编码的，这里核对一下有没有忘了同步。"""
    page = os.path.join(HERE, NAME + ".html")
    try:
        with open(page, encoding="utf-8") as f:
            html = f.read()
    except OSError:
        return True
    if 'id="verNum">v' + VERSION + "<" in html:
        return True
    print("提示：%s 里的签名版本号不是 v%s，记得同步。" % (NAME + ".html", VERSION))
    return False


def pyinstaller_command():
    """优先用项目内的构建环境；没有就用当前解释器里的（CI 场景）。"""
    local = os.path.join(HERE, ".venv-build", "Scripts", "pyinstaller.exe")
    if os.path.isfile(local):
        return [local]
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        return None
    return [sys.executable, "-m", "PyInstaller"]


def clean_old_exe():
    """dist 是构建输出目录，打包前清掉旧 exe，免得版本混淆。"""
    dist = os.path.join(HERE, "dist")
    if not os.path.isdir(dist):
        return 0
    removed = 0
    for name in os.listdir(dist):
        if name.lower().endswith(".exe"):
            try:
                os.remove(os.path.join(dist, name))
                removed += 1
            except OSError:
                pass
    return removed


def main():
    os.chdir(HERE)

    pyinstaller = pyinstaller_command()
    if pyinstaller is None:
        print("找不到 PyInstaller。本地请双击 打包exe.bat，CI 请先 pip install pyinstaller。")
        return 1

    if not os.path.isfile(os.path.join(HERE, NAME + ".html")):
        print("缺少 " + NAME + ".html，无法打包")
        return 1

    check_html_version()
    version_file = write_version_file()

    old = clean_old_exe()
    if old:
        print("已清理 dist 里 %d 个旧 exe" % old)

    cmd = pyinstaller + [
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",           # 不弹黑色控制台窗口
        "--name", EXE_NAME,     # exe 文件名带版本号
        "--icon", "app.ico",
        "--version-file", version_file,
        # 界面资源随 exe 一起封进去
        "--add-data", NAME + ".html;.",
        # 托盘图标要在运行时用 pillow 读，所以图标也得进包
        "--add-data", "app.ico;.",
        "--collect-all", "webview",
        # pystray 的后端是按平台动态挑的，显式点名免得被静态分析漏掉
        "--hidden-import", "pystray._win32",
        "--hidden-import", "PIL.Image",
        "desktop.py",
    ]
    print("正在打包 %s（v%s）……" % (EXE_NAME, VERSION))
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    code = subprocess.call(cmd, cwd=HERE, env=env)

    exe = os.path.join(HERE, "dist", EXE_NAME + ".exe")
    if code == 0 and os.path.isfile(exe):
        size = os.path.getsize(exe) / 1048576.0
        print("")
        print("打包完成：%s" % exe)
        print("版本 v%s · 作者 %s" % (VERSION, AUTHOR))
        print("体积 %.1f MB，双击即可运行，不需要另装 Python 或运行库。" % size)
        return 0

    print("打包失败，请把上面的报错发我")
    return 1


if __name__ == "__main__":
    sys.exit(main())
