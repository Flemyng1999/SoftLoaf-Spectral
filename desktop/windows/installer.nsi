Unicode true
RequestExecutionLevel user
!include "MUI2.nsh"
!include "x64.nsh"
!ifndef APP_VERSION
!error "APP_VERSION is required"
!endif
!ifndef PAYLOAD
!error "PAYLOAD is required"
!endif
!ifndef OUTPUT
!error "OUTPUT is required"
!endif
Name "SoftLoaf Spectral ${APP_VERSION}"
OutFile "${OUTPUT}"
InstallDir "$LOCALAPPDATA\Programs\SoftLoafSpectral"
InstallDirRegKey HKCU "Software\SoftLoafSpectral" "InstallDirectory"
SetCompressor /SOLID lzma
!define MUI_ABORTWARNING
!define MUI_ICON "${PAYLOAD}\App.ico"
!define MUI_UNICON "${PAYLOAD}\App.ico"
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"
!insertmacro MUI_LANGUAGE "SimpChinese"

Function .onInit
  FindWindow $0 "SoftLoafSpectral"
  ${If} $0 != 0
    MessageBox MB_ICONSTOP "Close SoftLoaf Spectral normally before installing an update."
    Abort
  ${EndIf}
  ${IfNot} ${RunningX64}
    MessageBox MB_ICONSTOP "This package requires 64-bit Windows."
    Abort
  ${EndIf}
FunctionEnd

Section "Application" SEC_APP
  SetShellVarContext current
  SetOutPath "$INSTDIR"
  File /r "${PAYLOAD}\*"
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  CreateDirectory "$SMPROGRAMS\SoftLoaf Spectral"
  CreateShortcut "$SMPROGRAMS\SoftLoaf Spectral\SoftLoaf Spectral.lnk" "$INSTDIR\SoftLoaf Spectral.exe" "" "$INSTDIR\SoftLoaf Spectral.exe" 0
  CreateShortcut "$SMPROGRAMS\SoftLoaf Spectral\Uninstall.lnk" "$INSTDIR\Uninstall.exe"
  WriteRegStr HKCU "Software\SoftLoafSpectral" "InstallDirectory" "$INSTDIR"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SoftLoafSpectral" "DisplayName" "SoftLoaf Spectral"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SoftLoafSpectral" "DisplayVersion" "${APP_VERSION}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SoftLoafSpectral" "Publisher" "Yangming Feng and contributors"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SoftLoafSpectral" "UninstallString" '$"$INSTDIR\Uninstall.exe$"'
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SoftLoafSpectral" "URLInfoAbout" "https://github.com/Flemyng1999/SoftLoaf-Spectral"
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SoftLoafSpectral" "NoModify" 1
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SoftLoafSpectral" "NoRepair" 1
SectionEnd

Section "Uninstall"
  SetShellVarContext current
  RMDir /r "$INSTDIR\Service"
  RMDir /r "$INSTDIR\Notices"
  Delete "$INSTDIR\MSVCP140.dll"
  Delete "$INSTDIR\VCRUNTIME140.dll"
  Delete "$INSTDIR\VCRUNTIME140_1.dll"
  Delete "$INSTDIR\SoftLoaf Spectral.exe"
  Delete "$INSTDIR\App.ico"
  Delete "$INSTDIR\LICENSE"
  Delete "$INSTDIR\NOTICE"
  Delete "$INSTDIR\README.txt"
  Delete "$INSTDIR\payload-inventory.json"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"
  Delete "$SMPROGRAMS\SoftLoaf Spectral\SoftLoaf Spectral.lnk"
  Delete "$SMPROGRAMS\SoftLoaf Spectral\Uninstall.lnk"
  RMDir "$SMPROGRAMS\SoftLoaf Spectral"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SoftLoafSpectral"
  DeleteRegKey HKCU "Software\SoftLoafSpectral"
  ; Per-user settings, retained RAW stages and all external data are preserved.
SectionEnd
