; packaging/installer.iss
; Installs the one-folder PyInstaller output with a Start Menu shortcut and
; an optional run-at-login entry. Run-at-login matters because a tray
; watcher the user forgets to start does nothing.

#define AppName "OBS YouTube Uploader"
#define AppVersion "2.0.0"
#define AppExe "OBSYouTubeUploader.exe"

[Setup]
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=elboaf
DefaultDirName={autopf}\OBSYouTubeUploader
DefaultGroupName={#AppName}
UninstallDisplayIcon={app}\{#AppExe}
OutputDir=..\dist
OutputBaseFilename=OBS-YouTube-Uploader-Setup-{#AppVersion}
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
