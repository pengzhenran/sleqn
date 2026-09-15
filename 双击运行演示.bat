@echo off
chcp 936 >nul
cd /d "%~dp0demo"
if exist slf_demo.txt del /q slf_demo.txt
echo ================================================================
echo   海平面指纹（SLF）演示 —— 修正版
echo   当前工作目录: %CD%
echo ================================================================
echo.
echo 程序按“当前工作目录”读取 land.fcn.1_deg / love_numbers / Filelist.txt
echo 及数据文件，所以必须在本目录中运行（本脚本已自动 cd 过来）。
echo.
sleqn_dp_static.exe
echo.
echo ----------------------------------------------------------------
echo 运行结束，退出码 %ERRORLEVEL%
echo 结果: %CD%\slf_demo.txt
echo ----------------------------------------------------------------
echo.
pause
