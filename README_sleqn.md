# sleqn —— 海平面指纹（SLF）计算程序 使用说明

由文章所附 Fortran95 代码整理而来，并提供了等价功能的 Python/NumPy 版本与 PySide6 图形界面。
两个版本已用 gfortran 16.1.0 实际编译、运行、逐点比对（见 §8）。

程序求解海平面方程 $S(\theta,\psi,t) = C(\theta,\psi,t)[G^{L}-R^{L}]$（叠加保证质量守恒的 0 阶常数项），
输入全球表面质量变化网格，输出相应的全球海平面指纹。

| 文件 | 说明 |
| --- | --- |
| `sleqn.f90` | **原文版**：与文章代码逐行一致（含原文写法与 ★ 注释），便于对照 |
| `sleqn_dp.f90` | **修正版（推荐实际使用）**：算法相同，修正了 2 处数值缺陷（见 §6） |
| `sleqn.py` | Python/NumPy 版，与 `sleqn_dp.f90` 数值一致（合成算例逐字节相同） |
| `sleqn_gui.py` + `双击运行GUI.bat` | **PySide6 图形界面**（见 §1.3） |
| `sleqn_static.exe` | 由 `sleqn.f90` 编译好的 Windows 单文件程序（原文版） |
| `sleqn_dp_static.exe` | 由 `sleqn_dp.f90` 编译好的 Windows 单文件程序（修正版） |
| `make_demo_data.py` | 生成**合成**演示数据（非真实观测），用于先跑通流程 |
| `selftest_sleqn.py` | 自检脚本（7 项数值检验，见 §9） |
| `make_report_figs.py` | 生成总结报告的全部配图 |
| `总结报告.html` | 方法/原理/公式/算法/验证的图文总结报告（单文件，图片已内嵌） |
| `demo/` | 已生成的合成演示数据 |

---

## 1. 快速开始

### 1.1 Python 版（推荐先跑这个验证环境）

```bash
# （可选）生成合成演示数据；若已有真实数据可跳过
python make_demo_data.py --out demo

# 运行
python sleqn.py --mask demo/land.fcn.1_deg --love demo/love_numbers --list demo/Filelist.txt
```

`demo/` 里的数据是**合成**的（全球海洋 + 北极附近的方形"冰盖"），
只用来验证程序能否跑通，结果不代表任何真实海平面指纹。

### 1.2 Fortran 版

```bash
gfortran -O2 -o sleqn_dp.exe sleqn_dp.f90                  # 动态链接
gfortran -O2 -static -o sleqn_dp.exe sleqn_dp.f90          # 静态链接（推荐，便于分发）
```

然后把 `land.fcn.1_deg`、`love_numbers`、`Filelist.txt` 和你的数据文件放在**同一个目录**下，
在该目录中运行 exe（Fortran 按当前工作目录找文件）：

```bash
cd demo && ../sleqn_dp.exe        # demo 目录里就是要用的那 4 个文件
```

> **找不到 DLL 时**：WinLibs / MSYS2 等发行的 gfortran 生成的 exe 默认依赖
> `libgfortran-5.dll`、`libgcc_s_seh-1.dll`、`libwinpthread-1.dll`（位于其 `mingw64\bin`）。
> 若报错或退出码为 `0xC0000135`，把该 `bin` 目录加入 `PATH`，或改用 `-static` 编译。
> 本目录已提供两个静态编译好的 exe，可直接运行。
>
> **不要用 `-std=f95`** 编译：原文中的 `Real*8`、`Character*120` 是各编译器通用的扩展写法，
> 不是 F95 标准（`-std=f95` 会报错）。用默认标准或 `-std=legacy` 即可。

### 1.3 图形界面（PySide6，推荐日常使用）

```bash
# 直接双击 双击运行GUI.bat，或：
"C:\Users\<用户>\anaconda3\envs\pzr\python.exe" sleqn_gui.py
```

界面分左右两栏：

| 区域 | 内容 |
| --- | --- |
| 左栏 ① | 输入文件：海陆掩膜、负荷勒夫数、质量变化数据（各带「…」浏览按钮） |
| 左栏 ② | 计算参数：迭代次数 `niter`、载荷网格间隔 `dlon/dlat`、截断阶数 `lmax`、**极移反馈开关**、数值内核、输出格式、负值处理 |
| 左栏 ③ | 结果文件路径 + **开始计算 / 取消** + 进度条 + 当前阶段说明 |
| 右栏 · 海平面指纹图 | 等经纬网格或 Robinson 投影（cartopy 海岸线），三种色标模式：<br>**自适应（近场对称 ±max）**、**远场放大（±可调阈值）**、**对称对数 symlog** |
| 右栏 · 剖面 | 沿任意经线或纬线的剖面，可叠加均匀海面（eustatic）参考线 |
| 右栏 · 统计与数据 | 载荷质量、解算海水质量、**质量守恒自检**、面积加权平均、峰值位置、结果文件前 100 行预览 |
| 右栏 · 日志 | 与命令行版完全相同的输出，可复制 |

其它操作：菜单「文件 → 打开结果文件…」可直接查看已有结果（不需要重算，且能自动识别
纬度升序/降序的文件）；「保存当前图片…」可导出 PNG/PDF/SVG；按钮「载入演示数据」一键填好
`demo/` 里的合成算例路径。

「帮助」菜单里是三份随包文档，都在窗口内打开、不需要浏览器：

| 菜单项 | 内容 |
| --- | --- |
| **使用说明（F1）** | 本说明书的窗口版：**左侧目录栏**（点章节跳转）、右上角 `A+` / `A−` / `默认字号` 调字号、正文截图**随窗口宽度自动缩放**（表格也会按新宽度重排，不会出现横向滚动条），另有「用浏览器打开」看最完整的排版 |
| 快速上手 | 六步流程图 |
| 关于 / 作者信息 | 作者、单位、联系方式、公众号二维码与**引用方式**（中文文献在前、英文在后） |

> 提示：计算在后台线程运行，界面不会卡死，日志与进度实时刷新，可随时点「取消」。
> 提示：色标模式里选「远场放大」才能看清远场的负异常——海平面指纹的动态范围很大
> （载荷处可比远场高约 50 倍），单幅线性色标图往往"只见正值"。

---

## 2. 输入文件格式

### 2.1 海陆掩膜 `land.fcn.1_deg`

每行 3 列，共 `nth*nphi` 行（默认 180×360 = 64800 行）：

```
经度(度)  纬度(度)  value
```

`value = 1` 表示陆地、`0` 表示海洋（程序内部 `ofcn = 1 - value`）。
行序为**按纬度带**排列：先第 1 个纬度带的所有经度，再第 2 个纬度带……

> ⚠️ 该文件**不能有注释行**：Fortran 用的是 `Read(80,*)` 表控读入。
>
> ⚠️ 第 3 列请写成**整数** `0` / `1`：Fortran 版中 `ivalue` 因隐式类型规则是**整型**
> （字母 `i` 不在 `Implicit Real*8(A-H, O-Z)` 的范围内），列值为 `0.0`/`1.0`
> 会导致该记录读入失败。Python 版两者都能读。

### 2.2 负荷勒夫数 `love_numbers`

前 2 行为表头（Fortran 直接跳过、不解析，内容任意），其后每行 **4 列**：

```
l   h_l   k_l   (保留列)
```

必须从 `l = 0` 起连续给到 `l = 180`（共 181 行）——Fortran 的
`Read(90,*) ldum, h(l), rk(l), rll` 每次固定读 4 个数，**列数不足会导致后续错位**。

### 2.3 控制文件 `Filelist.txt`

每行两个文件名（用空白分隔）：

```
输入数据文件1  输出结果文件1
输入数据文件2  输出结果文件2
```

**路径含空格时必须用双引号括起来**（例如程序装在 `C:\Program Files\` 下）：

```
"C:\Program Files\海平面指纹\_internal\grace_example\load_grace_t0001_1deg.txt" "D:\out\slf.txt"
```

不加引号时按空白切分（与 Fortran 原文的列表输入一致）——路径里的空格会把文件名
拦腰截断，报 `No such file or directory`。引号写法只在 Python 版里有效；Fortran 版
请把工作目录/路径安排成不含空格。

程序逐行处理直到文件结束。相对路径：Fortran 版按**当前工作目录**解析；
Python 版先按当前工作目录找，找不到再按 `Filelist.txt` 所在目录找，输出写到 `Filelist.txt` 所在目录。

### 2.4 质量变化数据文件（`Filelist.txt` 中的输入文件）

每行 3 列：

```
经度(度)  纬度(度)  水当量高度(m)
```

负值会被置 0。单元面积由主程序中的 `dlon = dlat = 0.5`（度）反算，
**必须与实际数据网格间距一致**（若数据是 1° 网格，请改成 `dlon = dlat = 1.0`）。

---

## 3. 输出文件格式

每行 3 列，共 `nphi*nth` 行，**经度为外层循环、纬度为内层循环**：

```
经度(F5.1)  纬度(F5.1)  海平面变化 cm (E12.4)
```

例如 `  0.5  89.5   0.3908E-01` 表示 (0.5°E, 89.5°N) 处海面上升 0.03908 cm。

> ⚠️ `E12.4` 只保留 **4 位有效数字**：数值 ~1 cm 时输出分辨率为 1e-3 cm，
> 因此用这个格式做对比时，**小于约 1e-3 cm 的差异根本看不出来**（本说明中的精确比对
> 都改用 `ES24.16E3` / `--fmt e24.16` 高精度输出）。若后续要做精度较高的分析，
> Fortran 请把 `22 Format` 中的 `E12.4` 改成 `E16.6` 以上，Python 用 `--fmt e18.10`。

---

## 4. 可调参数

| 位置（Fortran） | 变量 | 默认 | 说明 |
| --- | --- | --- | --- |
| `Parameter (niter=2)` | 迭代次数 | 2 | `0` 表示水均匀铺在一层海面上（不做自吸引/负荷迭代） |
| `Parameter (lmost=180)` | 最大阶数 | 180 | **Python 版改为运行期可调**（`--lmax` / `set_lmax()`），需与勒夫数表的最高阶一致 |
| `Parameter (nth/nphi)` | 格点数 | 180 / 360 | 需与掩膜、载荷网格一致 |
| `dlon/dlat` | 载荷网格间隔 | 0.5° | 必须与实际数据一致 |
| 极移 3 行 | `coefpm/pmp/pmh` | 打开 | **Python 版/GUI 改为运行期可关**（`--no-polar` / `polar=False` / GUI 复选框）；Fortran 版仍需注释掉这 3 行及迭代中的极移分支 |

Python 版对应命令行参数：

```bash
python sleqn.py \
    --mask land.fcn.1_deg \
    --love love_numbers \
    --list Filelist.txt \
    --niter 2 \
    --lmax 180 \       # 截断阶数；原文写死 180，这里可调
    --no-polar \       # 可选：不算极移（polar motion）反馈
    --fmt e12.4        # 或 e18.10 / e24.16
```

### 截断阶数 lmax

原文把 `lmost`/`lsyn`/`llove` 都写成编译期常量 180。Python 版把它们改成运行期可调：

* 命令行：`--lmax 120`；库调用：`sleqn.set_lmax(120)` 或 `sleqn.run(..., lmax=120)`；GUI：左侧「截断阶数 lmax」。
* 默认仍是 180，因此不指定时与原 Fortran 逐字节一致。
* 约束：
  * `lmax ≥ 2`（极移项用到 l=2）；
  * `love_numbers` 至少要有 `lmax+1` 阶，不足时 `load_love` 会警告并把缺失的高阶按 0 处理（结果失真）；
  * 载荷/输出网格固定为 360×180（1°），只能分辨到约 180 阶，更大的 lmax 只是数学截断；
  * 预计算的勒让德函数占用 `8×(lmax+1)²×180` 字节（lmax=180 → 47 MB；lmax=720 → 748 MB），大 lmax 需注意内存。

### 极移（polar motion）反馈开关

原 Fortran 里极移反馈是"写死在源文件里"的（不需要就把 `coefpm/pmp/pmh` 三行与迭代中的
极移分支一起注释掉）。Python 版/GUI 把它做成**运行期开关**：

| 入口 | 写法 | 默认 |
| --- | --- | --- |
| 命令行 | `python sleqn.py ... --no-polar` | 不写 = 含极移反馈 |
| 库调用 | `sleqn.run(..., polar=False)` / `sleqn.solve_one(..., polar=False)` | `polar=True` |
| GUI | 左侧「② 计算参数」→ **「含极移（Polar motion）反馈」** 复选框 | 勾选 |

物理含义：地表质量重分布改变地球惯性张量 → 自转轴（极）漂移 → 离心位变化，
该扰动在球谐展开里**只含 $(l,m)=(2,1)$**（Kendall et al., 2005；Tamisiea et al., 2010 式 11）。
因此关掉它 = 把 $(2,1)$ 的系数换回未含极移的通用系数 `coefh(2)/coefp(2)`，
其余阶次一字不动。用真实 GRACE 载荷时该反馈的影响约在场峰值的 **0.4 %** 量级。

`sleqn.py` 中 `coefpm/pmp/pmh` 三个系数在关掉时不参与计算，迭代里的分支也一并跳过
（不是"算了不用"）——可在日志里看到 `[极移] 已关闭极移(polar motion)反馈` 的提示。

验证见 `_verify/verify_polar_switch.py`（4 组判据、12 项检查全部通过）：

| 判据 | 结果 |
| --- | --- |
| 全球海洋闭合解 $S_{lm}=\mathrm{coefp}_{lm}T_{lm}/(1-\mathrm{coefh}_{lm})$（带/不带极移权重） | 两种状态都与 sleqn 一致到 1° 网格求积误差（$7\times10^{-5}$ 峰值） |
| 差场的 $(2,1)$ 系数 vs 两个闭合解系数之差 | 相对偏差 $1.7\times10^{-5}$ / $2.3\times10^{-5}$ |
| 赤道镜像载荷（$(2,1)$ 严格为 0） | 开/关结果**逐点完全相同**（`max|Δ| = 0`） |
| 开/关差场的球谐谱 | $(2,1)$ 占总功率 **99.9999 %** |
| gravity-toolkit（`POLAR=True` / `POLAR=False`，同一套勒夫数） | 分别相差峰值的 0.026 % / 0.038 % |

### 加速内核（可选）

`sleqn_fast.py` 提供与 `sleqn.py` **逐字节相同**的加速内核（实测 grace_example
两个任务 190 s → 19 s）：

```python
import sleqn, sleqn_fast
sleqn_fast.patch()      # 启用；unpatch() 可切回原内核
```

GUI 左侧「数值内核」勾选框即对应此开关；`python verify_sleqn_fast.py`
会在多种数据/网格/行序/lmax 下核对两个内核输出逐字节相同。

---

## 5. 程序结构与变量对照

| Fortran | Python | 说明 |
| --- | --- | --- |
| `Program sleqn` | `run()` / `solve_one()` | 主流程：读文件、逐文件求解、写结果 |
| `Subroutine martin` | `martin()` | Martin 递推关系求归一化勒让德函数 |
| `Subroutine geoid` | `geoid()` | 对 θ、φ 积分求斯托克斯系数 |
| `Subroutine gdisc` | `gdisc()` | 均匀圆盘的斯托克斯系数（单个网格单元） |

| 变量 | 含义 |
| --- | --- |
| `ofcn(i,j)` | 海洋函数（海洋 1、陆地 0） |
| `synthc/synths` | 载荷 + 其引起的固体地球变形所致重力势的球谐系数 |
| `hclm/hslm` | 海面高度（海平面指纹）的球谐系数 |
| `total(i,j)` | 海面高度网格（cm），最终输出量 |
| `coefh(l)` | `(1+k-h)*3*rho0/rhoave/(2l+1)`，海水负荷的 $G-U$ 系数 |
| `coefp(l)` | `(1+k-h)/(1+k)`，外部载荷的 $G-U$ 系数 |
| `ocnint` | 海洋面积（立体角 $\int O\,d\Omega$） |
| `amass` | 保持水量守恒的 0 阶常数项 |
| `tmass` / `zmass` | 载荷总质量 / 解算得到的海水质量（程序会打印二者，应互为相反数） |

---

## 6. 与原文代码的差异（`sleqn.f90` → `sleqn_dp.f90`）

`sleqn.f90` **保持与文章代码逐行一致**，只把原文所有单词粘连处按 Fortran 语法还原
（`Programsleqn`→`Program sleqn`、`Doj = 1, nth`→`Do j = 1, nth`、`Callgeoid`→`Call geoid`、
`EndSubroutine`→`End Subroutine` 等），原文注释全部保留，另加了 ★ 提示注释与
输出单元的 `Close`。

`sleqn_dp.f90` 在此基础上修正了 2 处数值缺陷（**算法与公式完全未动**）：

### 修正 1：字面常量被截断为单精度

原文中 `1./sqrt(2.)`、`sqrt(1.+1./2./float(j))`、`sqrt(2.)`、`sqrt(2.0)`、`3./5.517`、
`6.371E3**2`、`6.371E8`、`pi = 3.14159265`、`rhoave = 5.517`、`0.298`、`0.604`、`5.97E27` 等
常量，因为字面量没有 `D0` 后缀，会**先按 REAL(4) 截断**再参与运算，带入约 $10^{-8}$ 的相对误差。

危害被 `gdisc` 里的一处相减放大：单元角半径 $\alpha$ 很小（0.1° 量级）时

```
temp(l) = ( P_{l-1}(cos α) - P_{l+1}(cos α) ) / 2
```

是两个 $\approx 1$ 的数相减，差值只有 $10^{-6}\sim10^{-5}$ 量级，有效数字大量抵消，
于是 $10^{-8}$ 的输入误差被放大到 $10^{-3}$ —— 单个网格单元的球谐系数出现千分之几误差
（实测 l=1 时约 0.6%、l=6 时约 0.3%）。

修正办法：给这些常量加 `D0`、把 `sqrt`/`float` 换成 `dsqrt`/`dfloat`。

### 修正 2：`pmh` 一行的分母用到了失效的循环变量

原文

```fortran
pmh = pmp*(1.+rk(2))*3.*rho0/rhoave/float(2*l+1)
```

位于 `Do l = 0, lsyn` **循环之后**，此时 `l` 已等于 `lsyn+1 = 181`，分母变成 363；
而极移项只在 $l=2,\,m=1$ 处生效，按物理意义分母应为 $2\times2+1=5$。
原写法把极移反馈削弱了约 72 倍（`pmh` 由 0.2667 变成 0.00367，而同一分支的
`pmp` 仍是放大后的 3.50），使该项实际上处于"被关掉一半"的不一致状态。

修正办法：分母写死为 `float(2*2+1)`。若本来就不需要极移反馈，
也可以把 `coefpm/pmp/pmh` 三行与迭代中的极移分支一起注释掉，此时修正 2 不再有影响。

### 其他（原样保留，仅注释说明）

- `gdisc` 中 `alpha = dcos(clat)` 是死代码：`clat` 已经是角半径的余弦，
  这一行既不是角半径、其后也未被使用（按原意应为 `acos(clat)`）。
- `pi`、`area1`、`phi`、`smass`、`areatot`、`rll` 等变量在原文中计算但未被使用。
- `-Wdo-subscript` 会报告 `martin` 中 `ptemp(k-2)` 越界，但该语句在 `If(k>1)` 保护之下，
  属于 gfortran 静态分析的误报（实测结果与解析式一致）。

---

## 7. 数值一致性

`sleqn.py` 与修正版 `sleqn_dp.f90` 在合成算例上给出**完全相同**的结果
（`--fmt e12.4` 的输出与 `sleqn_dp_static.exe` 逐字节一致）。
`sleqn.py` 输出的 `E12.4` 字段严格遵守 Fortran 的 `0.ddddE±ee` 规则
（例如 0.1 写成 `0.1000E+00` 而不是 `1.0000E-01`）。

---

## 8. 编译与验证（gfortran 16.1.0，MinGW-w64 UCRT）

### 8.1 编译

两个源文件均编译通过（`gfortran -O2`，退出码 0、无告警）；
`-Wall -Wextra` 只报出 §6 中那条 `martin` 误报和一条"大数组从栈改静态存储"的提示。

### 8.2 一致性验证

合成算例（`demo/`，100 个网格单元，`niter=2`），把三组 Fortran 输出的**高精度版本**
与 `sleqn.py` 逐点比较：

| Fortran 版本 | `max|Δ|` vs `sleqn.py` | 占场最大值(1.035 cm)比例 |
| --- | --- | --- |
| 原文 `sleqn.f90` | 3.427e-03 cm | 0.33 % |
| `sleqn_dp.f90` 仅修精度（pmh 仍为 363） | 1.411e-03 cm | 0.14 % |
| **`sleqn_dp.f90` 精度 + pmh** | **9.99e-15 cm** | ≈ 0 |

逐项隔离（两组 Fortran 输出直接相减）：

| 单独影响 | `max|Δ|` | 占比 |
| --- | --- | --- |
| 修正 1（单精度常量）对最终海平面场 | 3.978e-03 cm | 0.38 % |
| 修正 2（pmh 分母）对最终海平面场 | 1.411e-03 cm | 0.14 % |

用**同一 `E12.4` 文本格式**做端到端比对：

| 对比 | 结果 |
| --- | --- |
| `sleqn_dp_static.exe` vs `python sleqn.py --fmt e12.4` | **64800 / 64800 行逐字节完全相同** |
| `sleqn_static.exe`（原文版）vs 同上 | 99.23 % 的行不同，`max|Δ| = 3.40e-03 cm`，`mean|Δ| = 5.81e-04 cm` |

> 结论：`sleqn.py` 与修正版 Fortran 是同一算法的两种实现（差异为机器精度）；
> 原文版与它们相差 0.3 % 量级，其原因是 §6 的两处数值缺陷，而不是算法差异。

### 8.3 运行提示

运行时 stderr 会出现

```
Note: The following floating-point exceptions are signalling:
      IEEE_UNDERFLOW_FLAG IEEE_DENORMAL
```

这是极点附近 `rsin**m`（$m$ 达 180）下溢到非规格化数导致的，属正常现象，可忽略。

---

## 9. 自检

```bash
python selftest_sleqn.py
```

用合成数据做 8 项检验，当前全部通过：

| 编号 | 检验 | 结果 |
| --- | --- | --- |
| 1 | 质量守恒：解算海水质量 = −载荷质量 | 相对误差 0 ~ 2e-15 |
| 2 | 线性性：载荷加倍 → 指纹加倍 | 偏差 0 |
| 3 | 迭代生效：niter=0 与 niter=2 的差异 | 约 1.05 cm |
| 4 | 指纹形态：载荷处抬升、远场下降 | 载荷处 +0.94 cm、对跖点 −0.018 cm；与圆盘解析粗估之比 0.75 |
| 5 | 输出网格顺序：$\int S\,d\Omega$ = −tmass/(ρa²) | 相对误差 7e-15 |
| 6 | 输出格式与 Fortran `F5.1,1X,F5.1,1X,E12.4` 一致 | 通过 |
| 7 | `E` 格式边界值（0.1 等）符合 `0.ddddE±ee` 规则 | 通过 |
| 8 | 极移开关：关掉后仍质量守恒、结果不同、差异全在 $(2,1)$ | 差场 $(2,1)$ 功率占比 100 % |

第 4 项体现了海平面指纹的物理特征：**正质量载荷（如冰盖增长）会吸引海水向其堆积，载荷处海平面相对抬升、远场相对下降**；
反之，冰盖消融时冰盖附近海平面下降——这正是"指纹"区别于均匀（eustatic）海平面变化的根本所在。

---

## 10. 引用

Sun J. W., Wang L. S., Peng Z. R., Fu Z. Y., Chen C (2022).
The sea level fingerprints of global terrestrial water storage changes detected by
GRACE and GRACE-FO data. *Pure and Applied Geophysics*, 179(9).
