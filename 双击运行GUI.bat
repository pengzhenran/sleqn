@echo off
chcp 936 >nul
cd /d "%~dp0"
set "PY=C:\Users\pengzhenran\anaconda3\envs\pzr\python.exe"
if not exist "%PY%" set "PY=python"
echo ================================================================
echo   海平面指纹（SLF）计算程序 —— 图形界面
echo   使用解释器: %PY%
echo   工作目录  : %CD%
echo ================================================================
echo.
"%PY%" sleqn_gui.py
if errorlevel 1 (
  echo.
  echo ----------------------------------------------------------------
  echo 程序异常退出，请把上面的错误信息截图反馈。
  echo 若提示缺少 PySide6，请在该环境中执行:
  echo     %PY% -m pip install PySide6 matplotlib numpy
  echo ----------------------------------------------------------------
  pause
)
