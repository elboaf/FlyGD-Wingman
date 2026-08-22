; packaging/installer.iss
; Installs the one-folder PyInstaller output with a Start Menu shortcut and
; an optional run-at-login entry. Run-at-login matters because a tray
; watcher the user forgets to start does nothing.

#define AppName "FlyGD Wingman"
#define AppVersion "3.1.1"
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
; FIRST on purpose. SolidCompression=yes means the archive must be
; decompressed from the beginning to reach any given file, so a dontcopy file
; placed after the whole application tree would force a second pass over
; every byte of it when ExtractTemporaryFile is called at ssPostInstall.
; Listed first, the extraction is nearly free.
;
; dontcopy: this is never installed into {app}. It is extracted to {tmp}
; only when the runtime is actually missing, and deleted with {tmp}.
Source: "bin\MicrosoftEdgeWebview2Setup.exe"; Flags: dontcopy noencryption
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

[Code]
{ ------------------------------------------------------------------------
  WebView2 Evergreen runtime.

  The application renders its entire UI in WebView2. Without the runtime,
  pywebview logs a FileNotFoundException, webview.start() returns normally,
  and the process EXITS 0 -- no window, no error, no crash dialog, and a
  success exit code. In a windowed build the log line is not visible either.
  That is why this exists.

  This installer is only HALF the fix. The runtime can be uninstalled or
  broken after a successful install, so obs_youtube_uploader/ui/preflight.py
  runs the same check at every launch and shows a native message box before
  webview.start() is ever called.

  THE TWO CHECKS MUST BE THE SAME PREDICATE. The GUID below is duplicated in
  preflight.py's WEBVIEW2_GUID, and ci.yml's "Check the WebView2 detection
  predicate agrees" step fails the build if the two drift. If you change the
  rule here -- the keys, the pv handling, the 0.0.0.0 case -- change it there
  in the same commit.
  ------------------------------------------------------------------------ }
const
  { EdgeUpdate's client id for the Evergreen runtime. Microsoft documents
    this registry probe as the supported detection method; there is no API. }
  WEBVIEW2_GUID = '{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';
  WEBVIEW2_CLIENT_PATH = 'SOFTWARE\Microsoft\EdgeUpdate\Clients\';
  WEBVIEW2_DOWNLOAD_URL = 'https://developer.microsoft.com/microsoft-edge/webview2/';

var
  WebView2Missing: Boolean;

function ReadRuntimeVersion(RootKey: Integer): String;
var
  Value: String;
begin
  Result := '';
  if RegQueryStringValue(RootKey, WEBVIEW2_CLIENT_PATH + WEBVIEW2_GUID, 'pv', Value) then
    Result := Trim(Value);
end;

function VersionIsReal(const Version: String): Boolean;
begin
  { An empty pv, or the literal '0.0.0.0', is what a partially removed or
    never-completed install leaves behind. Treating either as "present" is
    the exact mistake that produces the silent-exit-0 launch. }
  Result := (Version <> '') and (Version <> '0.0.0.0');
end;

function WebView2RuntimePresent(): Boolean;
begin
  // Line comments, not a braced { } block: this text has to name the
  // registry paths, which end in the GUID -- and a braced comment is ended
  // by the FIRST closing brace, so the one in ...\Clients\<GUID> would
  // close it early and leave the prose to be parsed as code.
  //
  // Three locations, matching preflight.py's three:
  //
  //   HKLM32 -> HKLM\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\<GUID>
  //             on 64-bit Windows. EdgeUpdate is a 32-bit process, so this
  //             is where a per-machine install actually lands, and it is
  //             the key observed present on the dev machine
  //             (pv=151.0.4129.93). On 32-bit Windows there is no
  //             redirection and this same view IS
  //             HKLM\SOFTWARE\Microsoft\EdgeUpdate\Clients\<GUID>.
  //   HKLM64 -> the native hive on 64-bit Windows. Guarded by IsWin64
  //             because the 64-bit root constants error on 32-bit Windows.
  //   HKCU   -> a per-user runtime install, which is what an UNELEVATED
  //             bootstrapper produces -- and PrivilegesRequired=lowest
  //             means that is our normal case, not an edge case.
  //
  // Any one of them counts.
  Result := VersionIsReal(ReadRuntimeVersion(HKLM32));
  if not Result then
    Result := VersionIsReal(ReadRuntimeVersion(HKCU));
  if (not Result) and IsWin64 then
    Result := VersionIsReal(ReadRuntimeVersion(HKLM64));
end;

procedure ReportWebView2Failure();
var
  Message: String;
begin
  Message :=
    'The Microsoft Edge WebView2 runtime could not be installed.' + #13#10#13#10 +
    'FlyGD Wingman has been installed, but it will not open a window until' + #13#10 +
    'the runtime is present. This usually means the machine was offline: the' + #13#10 +
    'installer bundles a small downloader, not the runtime itself.' + #13#10#13#10 +
    'Connect to the internet and install it from:' + #13#10 +
    WEBVIEW2_DOWNLOAD_URL + #13#10#13#10 +
    'FlyGD Wingman will show this same message if you launch it before then.';
  Log('WebView2: ' + Message);
  { Never block an unattended install on a message box nobody can dismiss.
    /VERYSILENT is how the CI smoke install runs. }
  if WizardSilent() then
    Log('WebView2: setup is silent; suppressing the message box.')
  else
    MsgBox(Message, mbError, MB_OK);
end;

procedure InstallWebView2Runtime();
var
  SetupPath: String;
  ResultCode: Integer;
begin
  if WebView2RuntimePresent() then
  begin
    Log('WebView2: runtime already present, skipping the bootstrapper.');
    Exit;
  end;

  Log('WebView2: runtime absent, running the bundled Evergreen bootstrapper.');
  ExtractTemporaryFile('MicrosoftEdgeWebview2Setup.exe');
  SetupPath := ExpandConstant('{tmp}\MicrosoftEdgeWebview2Setup.exe');

  { '/silent /install' is the documented pair. Without /install the
    bootstrapper shows its own UI; without /silent it puts a progress window
    on top of the wizard. ewWaitUntilTerminated because the check below is
    only meaningful once it has finished. }
  if not Exec(SetupPath, '/silent /install', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
  begin
    Log('WebView2: the bootstrapper could not be started at all.');
    WebView2Missing := True;
    ReportWebView2Failure();
    Exit;
  end;
  Log(Format('WebView2: bootstrapper exited with %d', [ResultCode]));

  { Re-run the SAME predicate rather than trusting the exit code. The whole
    reason this feature exists is that a success code from something that did
    nothing is exactly the failure mode this app is vulnerable to. If the
    registry says the runtime is there, it is there, whatever the stub
    returned; if it does not, the install did not work, whatever it returned. }
  if not WebView2RuntimePresent() then
  begin
    WebView2Missing := True;
    ReportWebView2Failure();
  end
  else
    Log('WebView2: runtime installed successfully.');
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  { ssPostInstall runs after the application tree is in place and BEFORE
    the post-install "Launch FlyGD Wingman" checkbox in the Run section can
    fire, so a user who ticks it gets a working runtime.

    Do not rewrap this comment so that a line BEGINS with a bracket. Inno's
    parser looks for section tags at the start of a line and does not except
    braced comments, so a wrapped "[Run]" landing in column 1 is read as a
    section header and fails the compile with "Invalid section tag". }
  if CurStep = ssPostInstall then
    InstallWebView2Runtime();
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  { Deliberately does NOT abort the installation on failure. Aborting would
    strand a user whose only problem is a dropped connection, leaving them
    with nothing installed and no app to retry from; and the runtime install
    frequently succeeds on a later attempt. Instead the app is installed, the
    failure is reported once here, and preflight.py repeats the message with
    the same URL on every launch until it is fixed. }
  if (CurPageID = wpFinished) and WebView2Missing then
    WizardForm.FinishedLabel.Caption :=
      WizardForm.FinishedLabel.Caption + #13#10#13#10 +
      'WARNING: the Microsoft Edge WebView2 runtime is still missing, so ' +
      'FlyGD Wingman will not open a window. Install it from ' +
      WEBVIEW2_DOWNLOAD_URL;
end;
