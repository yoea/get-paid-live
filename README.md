# 上班鼓励器 · Get Paid Live

把月薪拆成每秒都在跳的数字。上班时瞄一眼：今天已经赚了多少，还要熬多久。

Windows 桌面小程序，单个 exe 双击即用，不装 Python、不装运行库、不联网。

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

![上班鼓励器界面](assets/screenshot.png)

## 界面上有什么

- **今日已赚**：四位小数实时累加，午休时段冻结不涨
- **当前赚钱速度**：每秒多少钱
- **工时进度**：百分比 + 进度条 + 已工作 / 总工作小时
- **本月累计、本年已赚、时薪、今日满勤**
- **当月日历点阵**：每天都画出来，上班日、休息日、节假日、今天各一色
- **鼓励语**：算出「再过多久，某件小东西就到手了」。内置 32 件商品，从 2 元的矿泉水到 1 万元的一次旅行，日薪几百和日薪上千的人都能挑到合适的目标
- **藏钱模式**（`H`）：金额全变 `****`，只留工时，工位旁边不怕被看见
- **演示模式**：可以设一个假的"当前时间"，下班后也能看效果

## 下载

到 [**Releases**](https://github.com/yoea/get-paid-live/releases) 下载 `GetPaidLive-v1.2.0.exe`，双击运行。

单文件约 13 MB，不需要安装 Python、浏览器或任何运行库。文件名和右键「属性 → 详细信息」里都带版本号，方便确认拿到的是哪一版。

exe 不是手工传上去的：每个 Release 都由 GitHub Actions 在干净的 Windows 环境里现编译，从源码到产物这条链路可查（见下面的[打包与发布](#打包与发布)）。

> 文件名是英文的：GitHub Release 的附件名只保留 ASCII 字母数字和 `._-`，中文会被静默删掉（`上班鼓励器-v1.2.0.exe` 会变成 `-v1.2.0.exe`）。窗口标题和文件属性里仍然是中文的「上班鼓励器」。

## 打包与发布

打包全部交给 GitHub Actions，本地不需要装任何东西。工作流文件是 [`.github/workflows/build.yml`](.github/workflows/build.yml)。

### 发一个正式版本

版本号只有一个来源：`build.py` 里的 `VERSION`。改它，exe 文件名、文件属性、Release 标签全都跟着走。

```bash
# 1. 改 build.py：VERSION = "1.3.0"
# 2. 顺手改 上班鼓励器.html 里的 <span id="verNum">v1.3.0</span>
# 3. 提交
git add -A && git commit -m "v1.3.0"
git push

# 4. 打同名标签推上去，剩下的交给 CI
git tag -a v1.3.0 -m "v1.3.0"
git push origin v1.3.0
```

推完标签后大概 1–2 分钟，[Releases](https://github.com/yoea/get-paid-live/releases) 上就多一个带 exe 的版本。

### CI 做了什么

| 步骤 | 说明 |
|---|---|
| 检出代码 | `windows-latest` 干净环境 |
| 安装 Python | 3.12，`cache: pip` 按 `requirements.txt` 缓存依赖 |
| 装依赖 | pywebview（框架）+ pyinstaller（打包器），只装在构建机上 |
| 校验版本号 | 标签 `v1.3.0` 必须等于 `build.py` 里的 `VERSION`，不一致直接失败 |
| 打包 | 跑 `python build.py`，产出单文件 exe |
| 校验产物 | 文件名里必须含版本号、体积必须大于 5 MB，否则判定打包缺东西 |
| 存构建产物 | 上传到 Actions 的 Artifacts，保留 7 天 |
| 发 Release | 用 `gh release` 创建版本并附上 exe，正文取自 `.github/release-notes.md` |

**版本号对不上就让 CI 失败**，是这个工作流最有用的一条：避免出现「标签写 1.3.0、exe 里却是 1.2.0」这种发出去才发现的问题。

### 只想试打包，不想发版

到 Actions 页面选 **Build exe → Run workflow**，手动触发一次。这种运行只产出 Artifacts，不会创建 Release——适合验证改动能不能打包成功。Artifacts 需要在登录状态下下载，7 天后自动清理。

### 本地打包（可选）

CI 挂了或者想离线验证，本地也能打，约 24 秒：

```bash
打包exe.bat
```

生成 `dist\GetPaidLive-v1.2.0.exe`。第一次运行会联网装 pywebview / pyinstaller，装在项目内的 `.venv-build`，不动你的全局 Python。

或者手动执行等价的三条：

```bash
python -m venv .venv-build
.venv-build\Scripts\python.exe -m pip install -r requirements.txt
.venv-build\Scripts\python.exe build.py
```

### 踩过的坑

这几个都写在代码注释里，也记一下免得重犯：

- **Release 附件名只能是 ASCII。** 平台会静默删掉文件名里的非 ASCII 字符，任何上传方式（Softprops action、`gh release upload`、网页拖拽）都一样。所以产物名固定为 `GetPaidLive-v{版本}.exe`，中文名只留在窗口标题和文件属性 `ProductName` 里。
- **Windows runner 的控制台默认是 cp1252。** `build.py` 打印中文会当场 `UnicodeEncodeError`，所以脚本开头强制 `sys.stdout.reconfigure(encoding="utf-8")`，工作流里再补 `PYTHONIOENCODING` / `PYTHONUTF8` 两个环境变量透传给 PyInstaller 子进程。
- **`setup-python` 的 `cache: pip` 找不到依赖清单会直接失败**，连 Python 都装不上。所以仓库里必须有 `requirements.txt`，并用 `cache-dependency-path` 指向它。
- **用 `gh release` 而不是 marketplace 的发布 action。** 两者剥中文名的行为一模一样，`gh` 少一层封装，日志更直接、出错时好查。
- **打包前清理 `dist` 里的旧 exe**（`build.py` 的 `clean_old_exe()`），否则本地多次打包会混进旧版本的包。

## 为什么只有 13 MB

界面交给 Windows 自带的 WebView2 渲染，不打包浏览器内核。Electron 这类方案最少 100 MB 起，这个方案只带 Python 运行时和一份 HTML。

启动前会检测 WebView2（Win11 自带，正常更新的 Win10 也有），真的缺了会弹出提示并给出官方下载地址，而不是双击没反应。

## 数据只存本地

**不联网、无账号、不上传任何东西。**

- 配置全部存在 `%LOCALAPPDATA%\ShangBanGuLiQi`
- 覆盖安装新版 exe，之前填的工资和作息不会丢
- 想彻底清除，删掉那个目录即可

技术细节：程序启动时会在 `127.0.0.1` 上起一个本地静态服务来托管界面。这不是网络服务——WebView2 在 `file://` 协议下拒绝使用 localStorage（判定为不安全），只能走本地 http。它只监听回环地址，外部访问不到，也不产生任何外部请求。

## 算法口径

| 项目 | 口径 |
|---|---|
| 日薪 | 月薪 ÷ **当月实际工作日数**（扣掉周末和节假日，加上调休补班日） |
| 时薪 | 日薪 ÷ 每日工时（午休时段不计入） |
| 今日已赚 | 已工作时长 × 时薪，午休期间冻结 |
| 本月累计 | 本月已过的工作日按满勤补算 + 今日已赚（只算已赚到的，不预支未来） |
| 本年已赚 | 1 月至上月满勤 + 本月累计 |

所以每日金额会随当月工作日数浮动：同样 8000 月薪，21 个工作日的月份日薪 380.95，23 个工作日的月份日薪 347.83。这比「月薪 ÷ 21.75」更贴近你当月的实际付出。

**鼓励语怎么挑**：从商品表里筛出「今天还没赚到、但下班前赚得到」的，选最贵的一件，算出还差多久；已经赚到的自动跳过。

## 首次使用

打开后会先让你填：月薪、上下班时间、午休时段、哪几天上班。
填完才进主界面开始计时——不会拿一份写死的默认值糊弄你。

月薪建议填**到手数**，这样算出来的钱才是你真正能花的。

## 项目结构

```
desktop.py                    启动器（pywebview + WebView2）
上班鼓励器.html                界面与全部逻辑
build.py                      打包脚本，版本号与作者信息在这里
打包exe.bat                   一键打包（本地用，CI 不用它）
requirements.txt              打包依赖（只装在构建机，不随 exe 分发）
app.ico                       应用图标
LICENSE                       MIT 许可证
.github/workflows/build.yml   CI：推 v* 标签自动构建并发 Release
.github/release-notes.md      Release 正文模板
assets/screenshot.png         README 用的界面截图
```

## 已知限制

- **内置 2026–2027 年节假日安排**（2027 年按国务院办公厅通知预置）。两年之后请自行在设置里补充，或者干脆留空——留空不会报错，只会把节假日当工作日算。调休补班日因各公司排班不同，默认留空，需要你自己填。
- 统计只覆盖**当月和当年**，没有历史账本，也不构成任何财务建议。
- 只支持 Windows 10 及以上。

## 许可

[MIT License](LICENSE) © 2026 Ethan

随便用、随便改、随便分发，包括商用，保留版权声明即可。软件按「原样」提供，不附带任何担保。

---

作者 **Ethan** · v1.2.0 · MIT
