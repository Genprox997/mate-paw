; mate_paw 桌面宠物 - NSIS 安装器模板
; 用法：
;   1) 先运行 `python build.py` 生成 dist/mate_paw.exe
;   2) 用 NSIS 打开本文件编译，得到 mate_paw_setup.exe
; 说明：安装目录默认 %LOCALAPPDATA%\mate-paw，免管理员权限；
;       开始菜单创建快捷方式；含卸载程序。

!include "MUI2.nsh"

Name "mate-paw 桌面宠物"
OutFile "mate_paw_setup.exe"
InstallDir "$LOCALAPPDATA\mate-paw"
RequestExecutionLevel user

!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_LANGUAGE "SimpChinese"

Section "安装"
    SetOutPath "$INSTDIR"
    File "dist\mate_paw.exe"
    CreateShortcut "$SMPROGRAMS\mate-paw.lnk" "$INSTDIR\mate_paw.exe"
    CreateShortcut "$DESKTOP\mate-paw.lnk" "$INSTDIR\mate_paw.exe"
    WriteUninstaller "$INSTDIR\uninstall.exe"
SectionEnd

Section "Uninstall"
    Delete "$INSTDIR\mate_paw.exe"
    Delete "$INSTDIR\uninstall.exe"
    Delete "$SMPROGRAMS\mate-paw.lnk"
    Delete "$DESKTOP\mate-paw.lnk"
    RMDir "$INSTDIR"
SectionEnd
