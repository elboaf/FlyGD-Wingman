; packaging/installer.iss
; Installs the one-folder PyInstaller output with a Start Menu shortcut and
; an optional run-at-login entry. Run-at-login matters because a tray
; watcher the user forgets to start does nothing.

#define AppName "FlyGD Wingman"
#define AppVersion "2.0.2"
#define AppExe "OBSYouTubeUploader.exe"

[Setup]
; AppId is the upgrade identity. Inno Setup defaults it to AppName, so the
; installs already in the wild are registered under the pre-rename product
; name. Pinning that old string here is what makes the rename an in-place
; upgrade rather than a second, side-by-side installation. Do not "tidy" this
; to match AppName -- that would strand every existing installation.
AppId=OBS YouTube Uploader
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=FlyGD
AppPublisherURL=https://wingman.zoolanders.vip/
AppSupportURL=https://wingman.zoolanders.vip/
; Install directory and executable name are deliberately NOT renamed: the
; run-at-login shortcut and the %LOCALAPPDATA% state folder both key off
; them, and renaming would orphan an existing install's settings and token.
DefaultDirName={autopf}\OBSYouTubeUploader
DefaultGroupName={#AppName}
UninstallDisplayIcon={app}\{#AppExe}
OutputDir=..\dist
OutputBaseFilename=FlyGD-Wingman-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
; Per-user install avoids an admin prompt and keeps the app writable.
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern

[Tasks]
Name: "startup"; Description: "Start automatically when I log in"; GroupDescription: "Startup"
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts"; Flags: unchecked

[Files]
Source: "..\dist\OBSYouTubeUploader\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon
Name: "{userstartup}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: startup

[Run]
Filename: "{app}\{#AppExe}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Leave %LOCALAPPDATA% state in place so a reinstall keeps the user signed in.
Type: filesandordirs; Name: "{app}"
