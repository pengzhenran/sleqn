@echo off
chcp 936 >nul
cd /d "%~dp0"
echo ================================================================
echo   海平面指纹（SLF）计算程序 —— 原文版
echo   程序目录（= 当前工作目录）: %CD%
echo ================================================================
echo.
rem 原文版未写 Open 的 Status，输出文件已存在时会报 "Cannot write to
rem file opened for READ"；这里先删掉旧结果，保证可以反复运行。
if exist slf_demo.txt del /q slf_demo.txt
echo 正在运行，请稍候（约 10 秒）...
echo.
sleqn_static.exe
echo.
echo ----------------------------------------------------------------
echo 运行结束，退出码 %ERRORLEVEL%
if "%ERRORLEVEL%"=="0" (
  echo 结果已写入本目录下的 slf_demo.txt（由 Filelist.txt 指定）
) else (
  echo 运行失败，请把上面的错误信息截图反馈
)
echo ----------------------------------------------------------------
echo.
pause
