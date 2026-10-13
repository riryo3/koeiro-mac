; Koeiro Windows installer (Inno Setup 6).
;
; Built by tools/build_windows_setup.py, which stages the PyInstaller bundle and
; passes the paths in as defines. Do not run ISCC by hand with guessed defines: the
; stage has to be checked for a development build root first.
;
;   ISCC /DMyAppVersion=0.13.2 /DMyTag=v0.13.2 /DStageDir=... /DOutDir=... installer\Koeiro.iss
;
; The install folder is per-user on purpose. Program Files would make every automatic
; update ask for UAC, and the in-app updater runs this setup silently.

#define MyAppName "Koeiro"
#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif
#ifndef MyTag
  #define MyTag "v" + MyAppVersion
#endif
#ifndef StageDir
  #error StageDir must be passed with /DStageDir=
#endif
#ifndef OutDir
  #define OutDir "dist\setup"
#endif
#ifndef AppPublisher
  #define AppPublisher "heynegix"
#endif

[Setup]
AppId={{B6EC4706-BBD0-4A17-9056-58892A44AFD1}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL=https://github.com/heynegix/koeiro
AppSupportURL=https://github.com/heynegix/koeiro/issues
AppUpdatesURL=https://github.com/heynegix/koeiro/releases/latest
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
AllowNoIcons=yes
LicenseFile={#StageDir}\LICENSE.txt
OutputDir={#OutDir}
OutputBaseFilename=koeiro-{#MyTag}-windows-setup
SetupIconFile={#StageDir}\_internal\assets\icon.ico
UninstallDisplayIcon={app}\Koeiro.exe
UninstallDisplayName={#MyAppName}
Compression=lzma2/max
SolidCompression=yes
LZMAUseSeparateProcess=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
PrivilegesRequired=lowest
CloseApplications=yes
; Not RestartApplications: verified against a running install, Inno's RestartManager
; closes the app but does not always bring it back. Launching {app}\Koeiro.exe below,
; including in a silent run, is what makes an automatic update end with the app open.
RestartApplications=no
SetupLogging=yes
VersionInfoVersion={#MyAppVersion}
VersionInfoProductName={#MyAppName}

[Languages]
Name: "ja"; MessagesFile: "compiler:Languages\Japanese.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[Tasks]
; Unchecked: a silent update re-applies the default task set, so a desktop icon the
; user deleted would keep coming back. The wizard still offers it.
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#StageDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\Koeiro.exe"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\Koeiro.exe"; Tasks: desktopicon

[Run]
; No skipifsilent: an automatic update runs this setup with /VERYSILENT, and the app
; is expected to come back on its own. The app's single-instance guard makes a second
; launch just reveal the running window instead of opening another process.
Filename: "{app}\Koeiro.exe"; Description: "{cm:LaunchProgram,{#MyAppName}}"; \
  Flags: postinstall nowait

[Code]
// The AI voice models are not part of this setup (see PUBLISHING.md), and user data
// lives outside {app}. Say so once, at uninstall, instead of letting the user assume
// the uninstaller deleted a multi-GB AI pack they extracted beside the app.
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: string;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{localappdata}\Koeiro');
    if DirExists(DataDir) then
      Log('Uninstall kept settings, recordings and logs in ' + DataDir);
  end;
end;
