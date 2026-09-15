# 打包（安装程序）工作目录

这里放**打包成 Windows 安装程序**所需要的东西。发布给第三方使用者的说明书在
`../docs/`，本目录是构建用的，不打进安装包。

---

## 1. 打包用的 Python 环境

| 项目 | 值 |
| --- | --- |
| 环境名 | `sleqn` |
| 位置 | `C:\Users\pengzhenran\anaconda3\envs\sleqn` |
| 解释器 | `...\anaconda3\envs\sleqn\python.exe` |
| Python | 3.12.14（conda-forge） |
| 体积 | 约 509 MB / 14526 个文件 |
| 重建 | `powershell -ExecutionPolicy Bypass -File packaging\create_env.ps1 -Force` |
| 自检 | `& "$env:USERPROFILE\anaconda3\envs\sleqn\python.exe" packaging\verify_env.py` |

**为什么用 conda 而不是独立 venv**：放在 `anaconda3\envs\` 下，PyCharm / VS Code /
Trae 等 IDE 能**自动识别**，不用手工指定解释器路径（独立 venv 放项目外时 IDE 往往
扫不到）。

**只用 conda 装 `python` + `pip`，其余一律 pip 装**：conda 版的 numpy/matplotlib
会连带 MKL 等一大堆依赖，体积翻倍，而且拿不到我们要锁定的那套版本号。
conda 提供的只有 python 3.12.14 / pip / setuptools / wheel / packaging。

> 早先还建过一个独立 venv（`C:\Users\pengzhenran\sleqn-build\venv`），因为 IDE 识别
> 不到已经删掉了。`create_env.ps1` 已改为 conda 版。

**注意：本目录的 `.ps1` 必须存成「UTF-8 with BOM」。** 脚本里有中文，而
`powershell -File`（Windows PowerShell 5.1）对**没有 BOM** 的文件按 ANSI 解码，
会把中文字节解坏、顺带吃掉字符串的收尾引号，报出莫名其妙的语法错
（"意外的标记"）。用编辑器另存时记得选 UTF-8 with BOM；`create_env.ps1` 已经是。

## 2. 装了哪些包（最精简）

运行时只有 3 个顶层依赖，加 cartopy 共 4 个：

| 包 | 版本 | 作用 |
| --- | --- | --- |
| numpy | 2.1.3 | 数值核心 `sleqn.py` 唯一依赖 |
| PySide6-Essentials | 6.8.3 | 图形界面（QtCore/QtGui/QtWidgets） |
| matplotlib | 3.10.0 | 全部绘图（地图、剖面、配图） |
| cartopy | 0.25.0 | Robinson 投影 + 岸线 |

传递依赖只有 matplotlib 的绘图基础件（contourpy / cycler / fonttools /
kiwisolver / pillow / pyparsing / python-dateutil / six / packaging）和 cartopy 的
地理件（shapely / pyproj / pyshp / certifi）。精确版本见 `requirements-lock.txt`。

**刻意不用完整的 `PySide6`**：完整包会带 `PySide6-Addons`，其中 Qt Charts、
Qt Data Visualization 等模块是 **GPL-only**，会传染打包出来的程序。本程序绘图
全部用 matplotlib，只依赖 Essentials 即可，可保持 LGPL-3.0 的宽松条件
（详见 `../licenses/NOTICE.txt`，待补）。

## 3. 离线底图

`cartopy_data/` 里是 **Natural Earth 110m** 的岸线/陆地/海洋/国界 shapefile，
共 20 个文件、**0.79 MB**。程序启动时会把 `cartopy.config['data_dir']` 指到这里
（见 `sleqn_gui.py` 的 cartopy 导入段），因此**完全离线**也能画出带岸线的
Robinson 投影图 —— 否则 cartopy 会去网上取底图，在无网络的机器上会失败，
只能退回等经纬矩形图。

只要 110m 就够：GUI 用的是 `ax.coastlines(resolution='110m')`。本机
`~/.local/share/cartopy` 里那 15.6 MB 大部分是 10m/50m 的数据，用不上。

## 4. 环境自检

`verify_env.py` 会依次检查：三个必需包版本 → 跑一遍 demo 算例并核对质量守恒 →
离屏建主窗口与四个对话框 → **把 `CARTOPY_DATA_DIR` 指向空目录**（模拟本机没有
底图缓存）后渲染一张带岸线的 Robinson 图，确认走的是随包数据。

当前结果：**19/19 通过**（GUI 侧的 `--selftest` 另有 20 项，见 §6）。

```
[PASS] numpy                                  2.1.3
[PASS] matplotlib                             3.10.0
[PASS] PySide6                                6.8.3
[PASS] 质量守恒（机器精度）                          相对误差 0.00e+00
[PASS] 离线渲染 Robinson + 岸线                     114 kB
结论：19/19 项通过
```

## 5. 图标

| 文件 | 说明 |
| --- | --- |
| `../assets/sleqn.ico` | 多尺寸图标（16/24/32/48/64/128/256），约 91 kB，供窗口与安装包用 |
| `../assets/sleqn_256.png` | 256 px 预览图（给"关于"对话框或文档用） |
| `../assets/sleqn_icon_sheet.png` | 各尺寸对照表（自检用，不随包） |
| `../tools/make_icon.py` | 生成脚本 |

图形是**圆球 + 本程序算出来的海平面指纹场**：蓝色铺满全球（远场下降）、
左上紧凑红斑（近场抬升），再叠上该场的**等值线**——偶极场的等值线天然是同心的
回旋曲线，正好读出"指纹"的意思。

两个细节：等值线要 `set_clip_path` 裁到球内，否则会画到球外面像划痕；
16/24/32 px 换用**去掉发丝线的简版**（描边加粗），否则小尺寸下会糊成一团脏点。
ICO 是自己拼的（Pillow 只会拿一张底图缩放，做不到"小尺寸换一张图"）。

重生成：`& "<env>\python.exe" tools\make_icon.py`

打包时给 PyInstaller 用：`--icon assets\sleqn.ico`。

## 6. 打包（已完成）

```powershell
cd <项目根>
& "$env:USERPROFILE\anaconda3\envs\sleqn\python.exe" -m PyInstaller --noconfirm --clean `
  --distpath "D:\" `
  --workpath "$env:USERPROFILE\sleqn-build\build" `
  packaging\sleqn.spec
```

产物 **`D:\sleqn_build\`，195.7 MB / 589 个文件**（`--distpath D:\` + spec 里
`COLLECT_NAME='sleqn_build'` 就是这个目录）：

```
sleqn_build\sleqn.exe      7.7 MB，双击即用（图标已嵌入）
sleqn_build\_internal\     运行库
    PySide6\  68.4 MB       其中 Qt 的 DLL 占 57.7 MB，是体积大头
    pyproj\   18.5 MB       含 PROJ 数据
    PIL\ 11.4 / matplotlib\ 11.4 / numpy\ 6.6 MB
    docs\          4.2 MB   使用说明 + 12 张配图（含目录栏版说明书窗口截图）
    grace_example\ 8.4 MB   真实 GRACE 示例（已剔除历史错误产物与临时输出）
    demo\          3.0 MB   合成算例（已剔除附带的 Fortran exe 与启动脚本）
    cartopy_data\  0.8 MB   离线岸线
    assets\        0.2 MB   图标 + 公众号二维码
```

打包后自检 **20/20 通过**（在 `%TEMP%` 下运行，确认不依赖开发目录）：

```
& "D:\sleqn_build\sleqn.exe" --selftest      # 退出码 0 = 全部通过
[PASS] 使用说明 / 公众号二维码 / 程序图标
[PASS] cartopy 可用 / 离线底图目录 / 示例数据
[PASS] 数值内核（demo, lmax=60） / 质量守恒（相对误差 0.00e+00） / 结果量级合理
[PASS] 极移开关：关闭后仍质量守恒 / 开、关结果不同且量级合理（max|Δ| = 2.389e-03 cm）
[PASS] 路径含空格的算例（带引号控制文件）        ← v1.0.1 新增
[PASS] 界面：极移开关默认勾选 / 经 on_run 生效（与直接调用 polar=False 一致）
[PASS] 界面与地图渲染
[PASS] 说明书改写：目录锚点保留（40 个 id） / 表格已补列宽（20 个） / 样式已内联
[PASS] 说明书窗口可渲染（9398 字）
[PASS] 关于对话框：引用文字未被裁掉（中文文献在前）
结论：20/20 项通过
```

`--selftest` 是给打包/安装后用的：装到别的机器上跑一下就知道随包文件、
离线底图、数值内核是否都还在。

### 踩过的三个坑（改 spec / 说明书时注意）

1. **`datas` 的 dest 写 `'.'` 会把目录"摊平"**：`(grace_example, '.')` 不是把
   `grace_example\` 放进去，而是把它**里面的文件**倒进 `_internal\` 根下，于是
   `demo\` 与 `grace_example\` 同名的 `land.fcn.1_deg`、`love_numbers` 互相覆盖。
   dest 要写目录名。现在用 `tree()` 逐文件列举，顺便按通配符剔文件。
2. **conda 的 DLL 在非标准位置**：`liblzma / libexpat / libssl / libcrypto /
   ffi-8 / libbz2` 放在 `envs\sleqn\Library\bin`，PyInstaller 自动分析找不到，
   `_lzma / pyexpat / _ssl / _ctypes / _bz2` 在包里会导入失败。已手工列进
   `binaries`（约 9 MB）。
3. **说明书 HTML 标签必须配平**：多写一个 `</tr>` 浏览器会忍，**Qt 的富文本引擎
   会直接把排版搞坏甚至卡死**。曾经因为 TOC 表里遗留一个多余的 `<td></td></tr>`，
   窗口渲染时整个卡住。`tools/check_guide.py` 现在会查 `tr/td/th/table/pre/div`
   的配平。
4. **控制文件里的路径不能裸写空格**（v1.0.1 修）：`Filelist.txt` 每行是"输入 输出"
   两个文件名，原实现按空白切分，于是装在默认的 `C:\Program Files\海平面指纹\` 下时
   路径被截断成 `C:\Program`，一点「开始计算」就报
   `No such file or directory: 'C:\Program'`（用户实测截图即此）。
   现在 GUI 写控制文件时给两个路径**加双引号**，`sleqn._split_filelist_line()`
   用 `shlex`（`posix=False`，兼容单双引号）解析，旧的裸路径写法行为不变；
   找不到输入文件时还会打印控制文件路径与"路径含空格要加引号"的提示。
   回归项：GUI `--selftest` 的「路径含空格的算例」（在
   `%TEMP%\…\Program Files\hai ping mian\` 下真跑一遍），以及
   `README_sleqn.md` §2.3 的写法说明。

调试用：设 `SLEQN_CONSOLE=1` 可以打一个带控制台的版本（`SLEQN_DIR` 改目录名），
启动期报错就能直接看到。

## 7. 窗口内的说明书排版

同一份 `docs/使用说明.html`，浏览器打开正常，但塞进 `QTextBrowser` 会出各种毛病
（表格第一列被压成一字宽、`<pre>` 不换行把整篇撑宽、提示框背景丢失）。
原因是 Qt 的富文本只支持 CSS 2.1 的一个子集，不认 `border-collapse`、
`max-width`、`white-space: pre-wrap`，对 `<div>` 背景也画不可靠。

解决办法是**渲染时改写**（`guide_render.py`，HTML 本体不动，浏览器里仍是原样）：

1. 丢掉 `<style>`，样式全部内联；
2. `<table>` 补 `width` / `cellpadding` / `cellspacing`，**按正文内容宽度的比例**
   给每列写死像素宽（Qt 只按首行定列宽，所以必须写死；但用比例算，视口变窄时
   表格不会撑出横向滚动条），单元格补边框与内边距；
3. `<pre>` 与 `.tip` / `.warn` 提示框改成**单格表格** —— 这样才有背景、边框，
   而且宽度受控、内容能换行；
4. `<img>` 按真实像素宽写一个不超视口的宽度，并写 `data-full="原始宽度"`；
5. **重写标题标签时保留 `id`** —— 否则目录锚点全部失效（这个坑踩过一次）。

窗口本身（`GuideDialog`）与同类工具 SHSynth 的说明书窗口一致：

| 特性 | 实现 |
| --- | --- |
| 左侧目录 | 从渲染后 HTML 的 `h2`/`h3` 自动生成（二级加粗、三级缩进、点击跳锚点） |
| 字号 | 顶部 `A+` / `A−` / `默认字号` |
| 图片自适应 | `_FittingBrowser`：只缩小不放大，靠 `data-full` 记原始宽度，120 ms 防抖，保留滚动位置与锚点 |
| 表格自适应 | 视口一变就按新宽度**整篇重排**（表格列宽是写死的像素，只缩图片不够） |
| 链接 | 内部锚点自己处理，DOI / 邮箱交给系统浏览器 |
| 完整排版 | 底部保留「用浏览器打开」按钮 |

> 说明书里的 `h2`/`h3` **必须带 `id`** 才会进目录栏；`h3` 没有 `id` 时只能靠
> `h2` 跳转（`docs/使用说明.html` 已补全，`tools/check_guide.py` 会检查锚点有效）。

## 8. 安装程序（已完成）

用 **Inno Setup 6**（装在 `E:\Inno Setup 6\`）。脚本 `sleqn.iss`：

```powershell
& "E:\Inno Setup 6\ISCC.exe" packaging\sleqn.iss
```

产物 **`D:\sleqn_installer\海平面指纹_Setup_v1.0.1.exe`，52.9 MB**
（195.7 MB 的 onedir 产物用 lzma2/max 压到 53 MB）。
（`_Setup_v1.0.exe` 是修掉"路径含空格"缺陷之前的旧包，别再分发。）

| 项目 | 值 |
| --- | --- |
| 默认安装位置 | `{autopf}\海平面指纹`（Program Files，需管理员确认） |
| 免管理员安装 | 向导里可选「仅为我安装」，或命令行 `/CURRENTUSER` |
| 快捷方式 | 开始菜单：程序 / 使用说明 / 卸载；桌面（可选，默认勾选） |
| 安装前 | 显示 `licenses\NOTICE.txt`（第三方组件与许可声明） |
| 安装后 | 显示 `安装后说明.txt`，并可勾选启动程序 / 打开使用说明 |
| 卸载 | 「设置 → 应用」或开始菜单卸载项；连同程序写下的结果文件一起清掉 |
| 语言 | 简体中文（主）/ English |

简体中文语言包是社区维护的，Inno Setup 本体不带，已随本目录放了一份
`ChineseSimplified.isl`（来自 [kira-96/Inno-Setup-Chinese-Simplified-Translation]
(https://github.com/kira-96/Inno-Setup-Chinese-Simplified-Translation)）。

### 实测验证

静默装到 `D:\sleqn_installtest`，从 `%TEMP%` 跑自检，再静默卸载：

```
安装退出码 0 → 200 MB / 591 个文件
已安装副本 --selftest → 退出码 0，19/19 项通过
开始菜单 4 个快捷方式 + 桌面图标；注册表卸载项名称/版本/发布者正确
卸载退出码 0 → 目录、快捷方式、注册表项全部清干净
```

v1.0.1 复测（刻意选了**含空格的安装目录**，即用户报错的那类路径）：

```
ISCC 编译 → D:\sleqn_installer\海平面指纹_Setup_v1.0.1.exe（52.9 MB，49.6 s）
静默装到 "D:\海平面指纹 test"（含空格）→ 安装退出码 0，sleqn.exe 就位
已安装副本 --selftest（从 %TEMP% 运行）→ 退出码 0，20/20 项通过
注册表：DisplayName=海平面指纹（SLF）计算程序，DisplayVersion=1.0.1，
        InstallLocation="D:\海平面指纹 test\"
卸载退出码 0 → 目录、快捷方式、注册表项清干净
```

### 装到 Program Files 的两个坑（都已处理）

1. `Program Files` 下普通用户没有写权限，而界面的「载入演示数据」原本会把结果写到
   示例数据旁边，一点开始计算就会失败。现在 `_writable_dir()` 会先探可写性，
   不可写就自动落到「文档\海平面指纹\」。
2. **路径里的空格会把文件名截断**（v1.0.1 修）：默认装到
   `C:\Program Files\海平面指纹\`，而控制文件 `Filelist.txt` 是"空格分隔两个文件名"，
   按空白切分就把 `C:\Program Files\…` 截成 `C:\Program`，用户看到的是
   `No such file or directory: 'C:\Program'`。修法与回归见 §6「踩过的坑」第 4 条。
   这条同时也说明：**装到 Program Files 本身没问题**，"换成不含空格的目录"只是
   v1.0.0 的绕行办法。

## 9. 会被 Windows 拦：智能应用控制（SAC）

`sleqn.exe` 与安装包**都没有代码签名**，这是目前唯一"用户装完打不开"的现实原因。
两种提示要分清（2026-07，实测机型 Windows 11 25H2）：

| 提示 | 机制 | 用户怎么办 |
| --- | --- | --- |
| 「Windows 已保护你的电脑 / 未知发布者」 | SmartScreen 信誉提示 | 点「更多信息 → 仍要运行」即可 |
| 「智能应用控制已阻止可能不安全的应用……因为无法验证其发布者」 | Smart App Control（SAC） | **没有单应用白名单**：只能关掉 SAC，或程序有可信签名 |

SAC 的判定顺序（[微软官方 FAQ](https://support.microsoft.com/en-us/windows/security/threat-malware-protection/smart-app-control-frequently-asked-questions)）：
先问云端信誉 → 云端给不出结论就看有没有**有效签名** → 没有有效签名就按"不受信任"拦掉。
因此下面三件事**都没用**，不必再往这些方向试：

* **换安装位置**（D 盘、用户目录、改目录名）—— SAC 不看路径，只看签名；
* **「仍要运行」** —— SAC 的对话框只有「正常」和「从 Microsoft Store 获得应用」；
* **卸载重装** —— 被拦的就是 `sleqn.exe` 本身。

**用户侧处置**：设置 → 隐私和安全性 → Windows 安全中心 → 应用和浏览器控制 →
智能应用控制 → 关闭 → UAC 确认，然后重新双击程序（**不必重装**）。关掉 SAC 不影响
Defender 的病毒防护；较新的 Windows 11（含 25H2）可以在同一页面**重新打开、不必重装
系统**（早期"关了就只能重装"的说法已被微软 FAQ 更新）。受 IT 统一管理的机器开关可能
被策略置灰，那种情况只能找管理员或换机器。

| 用户能看到的位置 | 加了什么 |
| --- | --- |
| `packaging\安装后说明.txt` | 「如果程序双击打不开（被 Windows 拦住）」小节（安装完成后弹出的那页） |
| `docs\使用说明.html` §1.5 | 两种提示的对照表 + 关闭 SAC 的三步 + 三个常见误解 |
| `docs\使用说明.html` §9 | 常见问题索引条目（指向 1.5 节） |

**发布者侧（尚未做**，即下一节第 1 条）：

* SAC 只认 **RSA** 签名、**不支持 ECC**，证书必须由受信任根 CA 签发
  （[微软签名指引](https://learn.microsoft.com/en-us/windows/apps/develop/smart-app-control/code-signing-for-smart-app-control)）；
* 要签的不止主程序：安装包、`sleqn.exe`、以及 `_internal` 下会被加载的 DLL 一起签更稳；
* 签了**不等于立刻放行**：SAC 还会看云端信誉，新签名、下载量小的程序仍可能被拦，
  要靠分发量累积（[开发者的同类反馈](https://learn.microsoft.com/en-au/answers/questions/5791210/application-signed-and-blocked-by-smart-app-contro)）；
* 可把 exe 提交到 <https://www.microsoft.com/en-us/wdsi/filesubmission> 帮助建立信誉；
  彻底绕开 SAC 只有走 Microsoft Store 分发（对离线科研工具不现实）。

> 结论：签名是"更规范"，但短期内救不了全部用户；**把"关了 SAC 再运行"写清楚，
> 才是现在最可靠的做法**（已完成）。

## 10. 版本

| 版本 | 内容 |
| --- | --- |
| **v1.0.1** | **修 v1.0.0 的"路径含空格"缺陷**（默认装到 `C:\Program Files\海平面指纹\` 下必然报 `No such file or directory: 'C:\Program'`，无法计算）。控制文件里的两个路径改为加双引号，解析用 `shlex`（`posix=False`）；找不到输入文件时报错会给出控制文件路径与"路径含空格要加引号"的提示；GUI 弹窗改为显示异常正文而不是 traceback 末行；自检新增「路径含空格的算例」（19 → 20 项）；说明书 §9、`安装后说明.txt` 补了对应说明。已重新打包并复测（见 §8）。 |
| v1.0.0 | 首个发布版：GUI + 数值内核 + 离线底图 + 安装程序。 |

> 分发时只发 `_Setup_v1.0.1.exe`。v1.0.0 的包对"装在 Program Files / 用户名带空格 /
> 路径含中文以外的空格"的机器一律算不了，只有装在无空格路径下才碰巧能用。

---

## 11. 下一步（尚未做）

1. **代码签名证书**（详见第 9 节）：现在 exe 未签名，用户首次运行会依次遇到
   SmartScreen「未知发布者」提示与（部分机器）SAC 硬拦截。有证书后可以签
   `sleqn.exe`、安装包与关键 DLL，证书要求（RSA、受信任根）见第 9 节。
2. 发布说明 / 更新日志（CHANGELOG）。
3. 可选：把示例数据做成"首次运行时按需解压"，进一步压小安装包。
