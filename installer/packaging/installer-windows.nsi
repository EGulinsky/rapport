; Rapport Installer -- Windows setup wizard.
;
; Wraps the PyInstaller onedir bundle (installer-windows.spec) in a real
; graphical Setup.exe via NSIS (Nullsoft Scriptable Install System,
; https://nsis.sourceforge.io/ -- free and open source under the zlib/libpng
; license) instead of the bare .zip this installer used to ship as: welcome/
; license/directory/progress/finish wizard pages, a Start Menu shortcut, and
; a proper uninstaller registered in Windows' Add/Remove Programs.
;
; Invoked by build_windows.ps1 with /DVERSION=x.y.z /DREPO_ROOT=<path>
; /DDIST_DIR=<path> -- paths are passed in rather than computed here, since
; NSIS resolves relative paths against the compiler's working directory,
; which may differ from this script's own location depending on how
; makensis is invoked.

!ifndef VERSION
  !error "VERSION must be defined (pass /DVERSION=<version> to makensis)"
!endif
!ifndef REPO_ROOT
  !error "REPO_ROOT must be defined (pass /DREPO_ROOT=<path> to makensis)"
!endif
!ifndef DIST_DIR
  !error "DIST_DIR must be defined (pass /DDIST_DIR=<path> to makensis)"
!endif

!define APP_NAME "Rapport Installer"
!define PUBLISHER "Eugen Gulinsky"
!define UNINST_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\RapportInstaller"
!define BUNDLE_DIR "${DIST_DIR}\Rapport Installer"

Name "${APP_NAME}"
OutFile "${DIST_DIR}\Rapport-Setup-${VERSION}.exe"
InstallDir "$PROGRAMFILES64\Rapport Installer"
InstallDirRegKey HKLM "${UNINST_KEY}" "InstallLocation"
RequestExecutionLevel admin
SetCompressor /SOLID lzma

!include "MUI2.nsh"

!define MUI_ABORTWARNING
!define MUI_FINISHPAGE_RUN "$INSTDIR\Rapport Installer.exe"
!define MUI_FINISHPAGE_RUN_TEXT "Run Rapport Installer now"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "${REPO_ROOT}\LICENSE"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "English"

VIProductVersion "${VERSION}.0"
VIAddVersionKey "ProductName" "${APP_NAME}"
VIAddVersionKey "ProductVersion" "${VERSION}"
VIAddVersionKey "FileVersion" "${VERSION}"
VIAddVersionKey "CompanyName" "${PUBLISHER}"
VIAddVersionKey "FileDescription" "Rapport Installer Setup"
VIAddVersionKey "LegalCopyright" "(c) ${PUBLISHER}"

Section "Install" SEC_INSTALL
  SetOutPath "$INSTDIR"
  File /r "${BUNDLE_DIR}\*.*"

  WriteUninstaller "$INSTDIR\Uninstall.exe"

  CreateDirectory "$SMPROGRAMS\Rapport Installer"
  CreateShortcut "$SMPROGRAMS\Rapport Installer\Rapport Installer.lnk" "$INSTDIR\Rapport Installer.exe"
  CreateShortcut "$SMPROGRAMS\Rapport Installer\Uninstall.lnk" "$INSTDIR\Uninstall.exe"

  WriteRegStr HKLM "${UNINST_KEY}" "DisplayName" "${APP_NAME}"
  WriteRegStr HKLM "${UNINST_KEY}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKLM "${UNINST_KEY}" "Publisher" "${PUBLISHER}"
  WriteRegStr HKLM "${UNINST_KEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKLM "${UNINST_KEY}" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegStr HKLM "${UNINST_KEY}" "DisplayIcon" "$INSTDIR\Rapport Installer.exe"
  WriteRegDWORD HKLM "${UNINST_KEY}" "NoModify" 1
  WriteRegDWORD HKLM "${UNINST_KEY}" "NoRepair" 1
SectionEnd

Section "Uninstall"
  RMDir /r "$INSTDIR"

  Delete "$SMPROGRAMS\Rapport Installer\Rapport Installer.lnk"
  Delete "$SMPROGRAMS\Rapport Installer\Uninstall.lnk"
  RMDir "$SMPROGRAMS\Rapport Installer"

  DeleteRegKey HKLM "${UNINST_KEY}"
SectionEnd
