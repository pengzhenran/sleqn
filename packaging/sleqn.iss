; ==============================================================================
; 海平面指纹（SLF）计算程序 —— Inno Setup 安装脚本
; ==============================================================================
;
; 编译：
;   "E:\Inno Setup 6\ISCC.exe" packaging\sleqn.iss
;
; 前置：先用 PyInstaller 打出 onedir 产物到 D:\sleqn_build
;   （见 packaging\README.md §6）
;
; 产物：D:\sleqn_installer\海平面指纹_Setup_v1.0.exe
;
; 说明：
;   * 默认装到 Program Files，需要管理员确认；用户也可以在向导里改成当前用户安装
;     （PrivilegesRequiredOverridesAllowed=dialog）。
;   * 安装前会显示 licenses\NOTICE.txt（第三方组件与许可声明），这也是 LGPL-3.0
;     对 Qt 的合规要求之一；许可全文随包安装到 {app}\_internal\licenses。
;   * 桌面快捷方式可选（默认创建），开始菜单固定创建。

#define AppName        "海平面指纹"
#define AppNameFull    "海平面指纹（SLF）计算程序"
#define AppVersion     "1.0.1"
#define AppPublisher   "彭桢燃 · 中国地质大学（武汉）"
#define AppURL         "https://doi.org/10.1007/s00024-022-03099-5"
#define ExeName        "sleqn.exe"

; PyInstaller 产物目录
#define SrcDir         "D:\sleqn_build"
; 安装包输出目录
#define OutDir         "D:\sleqn_installer"

[Setup]
AppId={{8F2C4A16-7B3E-4D51-9C88-0A5E6D3F1B72}
AppName={#AppNameFull}
AppVersion={#AppVersion}
AppVerName={#AppNameFull} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppCopyright=Copyright (C) 2026 彭桢燃 (Zhenran Peng)

; 默认装到 Program Files\海平面指纹；允许用户改成"仅为我安装"
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
AllowNoIcons=yes

; 安装前展示第三方许可声明
LicenseFile=D:\华为家庭存储\mywork\sealevel\licenses\NOTICE.txt
InfoAfterFile=D:\华为家庭存储\mywork\sealevel\packaging\安装后说明.txt

OutputDir={#OutDir}
OutputBaseFilename={#AppName}_Setup_v{#AppVersion}
SetupIconFile=D:\华为家庭存储\mywork\sealevel\assets\sleqn.ico
UninstallDisplayIcon={app}\{#ExeName}
UninstallDisplayName={#AppNameFull}

; 体积不小，压到最小
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes
ShowLanguageDialog=auto

; 只接受 64 位 Windows 10 及以上
MinVersion=10.0.17763

[Languages]
; 简体中文语言包是社区维护的，Inno Setup 本体不带，已随本目录放了一份
; （ChineseSimplified.isl，来自 kira-96/Inno-Setup-Chinese-Simplified-Translation）
Name: "chinese"; MessagesFile: "ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; \
    GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce

[Files]
; 整个 onedir 产物
Source: "{#SrcDir}\*"; DestDir: "{app}"; \
    Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppNameFull}"; Filename: "{app}\{#ExeName}"
Name: "{group}\使用说明"; Filename: "{app}\_internal\docs\使用说明.html"
Name: "{group}\{cm:UninstallProgram,{#AppNameFull}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#ExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#ExeName}"; Description: "{cm:LaunchProgram,{#AppNameFull}}"; \
    Flags: nowait postinstall skipifsilent
Filename: "{app}\_internal\docs\使用说明.html"; \
    Description: "打开使用说明（浏览器）"; \
    Flags: postinstall shellexec skipifsilent unchecked

[UninstallDelete]
; 用户可能在安装目录里留下结果文件；卸载时只删程序自己的东西，
; 这里显式列出会被写到的示例输出，避免卸载残留
Type: files; Name: "{app}\_internal\grace_example\slf_gui.txt"
Type: files; Name: "{app}\_internal\demo\slf_gui.txt"

[Code]
{ 安装前提示：程序完全离线运行 }
function InitializeSetup(): Boolean;
begin
  Result := True;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    { 无额外动作：许可全文已随 _internal\licenses 安装 }
  end;
end;
