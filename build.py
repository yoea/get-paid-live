# -*- coding: utf-8 -*-
"""把 上班鼓励器 打成单文件 exe。

需要先用 .venv-build 里的 Python 装好 pywebview / pyinstaller。
直接双击 打包exe.bat 即可，不必手动敲命令。
"""

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
NAME = "上班鼓励器"

# 版本号与作者信息：界面上（右下角签名）也有一处，改版本时记得两边一起改。
VERSION = "1.1.0"
AUTHOR = "Ethan"

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
        StringStruct('InternalName', 'ShangBanGuLiQi'),
        StringStruct('LegalCopyright', 'Copyright (C) 2026 %(author)s'),
        StringStruct('OriginalFilename', '%(name)s.exe'),
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
        "name": NAME,
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
        return
    if 'id="verNum">v' + VERSION + "<" not in html:
        print("提示：%s 里的签名版本号不是 v%s，记得同步。" % (NAME + ".html", VERSION))


def main():
    os.chdir(HERE)

    pyinstaller = os.path.join(HERE, ".venv-build", "Scripts", "pyinstaller.exe")
    if not os.path.isfile(pyinstaller):
        print("找不到构建环境，请先双击 打包exe.bat（它会自动准备）")
        return 1

    if not os.path.isfile(os.path.join(HERE, NAME + ".html")):
        print("缺少 " + NAME + ".html，无法打包")
        return 1

    check_html_version()
    version_file = write_version_file()

    cmd = [
        pyinstaller,
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",           # 不弹黑色控制台窗口
        "--name", NAME,
        "--icon", "app.ico",
        "--version-file", version_file,
        # 界面直接复用网页版那份 html，改完网页版重新打包即可
        "--add-data", NAME + ".html;.",
        "--collect-all", "webview",
        "desktop.py",
    ]
    print("正在打包 v%s，第一次会慢一些……" % VERSION)
    code = subprocess.call(cmd, cwd=HERE)

    exe = os.path.join(HERE, "dist", NAME + ".exe")
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
