<#
================================================================================
 create_env.ps1 —— 重建打包用的精简 conda 环境
================================================================================

    powershell -ExecutionPolicy Bypass -File packaging\create_env.ps1
    powershell -ExecutionPolicy Bypass -File packaging\create_env.ps1 -Force   # 先删旧的

环境建在 anaconda3\envs\ 下（默认名字 sleqn），这样 PyCharm / VS Code / Trae
等 IDE 能自动识别，不用手工指解释器路径。

**只用 conda 装 python + pip，其余全部 pip 装**：conda 版的 numpy/matplotlib
会拉进 MKL 等一大堆东西，体积翻倍，也偏离我们要锁定的那套版本。
#>
param(
    [string]$Name = 'sleqn',
    [string]$Python = '3.12',
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path

$conda = "$env:USERPROFILE\anaconda3\Scripts\conda.exe"
if (-not (Test-Path $conda)) {
    $c = Get-Command conda -ErrorAction SilentlyContinue
    if (-not $c) { throw "找不到 conda。请确认已安装 Anaconda/Miniconda。" }
    $conda = $c.Source
}
Write-Host "conda: $conda"

$envDir = "$env:USERPROFILE\anaconda3\envs\$Name"
if (Test-Path $envDir) {
    if (-not $Force) { throw "环境 $Name 已存在。要重建请加 -Force（会先删掉它）。" }
    Write-Host "删除旧环境 $Name ..."
    & $conda env remove -n $Name -y
}

Write-Host "创建环境 $Name (python $Python) ..."
& $conda create -n $Name "python=$Python" -y
if ($LASTEXITCODE -ne 0) { throw "conda create 失败" }

$py = Join-Path $envDir 'python.exe'
if (-not (Test-Path $py)) { throw "创建后找不到解释器：$py" }
& $py -c "import sys; print('  ->', sys.version.split()[0], sys.executable)"

Write-Host "安装依赖（只用 pip，见 requirements.txt 的说明）..."
& $py -m pip install --no-input --upgrade pip
& $py -m pip install --no-input -r (Join-Path $here 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw "pip install 失败" }

Write-Host ""
Write-Host "环境就绪：$py"
Write-Host "自检请运行："
Write-Host "  & `"$py`" packaging\verify_env.py"
