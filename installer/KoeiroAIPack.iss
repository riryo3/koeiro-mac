; Koeiro AI voice pack (Inno Setup 6) — the frozen worker, the MeanVC2 checkpoints this
; route loads, the LavaSR tree and the shipped standard voice. It installs *into the
; folder Koeiro.exe already lives in*, so the app finds the worker beside itself
; (src/runtime_paths.py: worker_executable / KOEIRO_ASSETS).
;
; Built by tools/build_ai_pack.py:
;   ISCC /DMyAppVersion=... /DMyTag=... /DStageDir=... /DOutDir=... installer\KoeiroAIPack.iss
;
; Disk spanning is on because BOOTH caps one file at 1.2 GB: the buyer downloads every
; part into the same folder and runs part 1.

#define MyAppName "Koeiro AI Voice Pack"
#define KoeiroAppId "{{B6EC4706-BBD0-4A17-9056-58892A44AFD1}"
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
  #define OutDir "dist\ai-pack"
#endif
#ifndef RepoRoot
  #define RepoRoot "."
#endif

[Setup]
AppId={{61C3CD1E-6682-403F-BD87-4BB79E92D864}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=heynegix
AppPublisherURL=https://github.com/heynegix/koeiro
AppSupportURL=https://github.com/heynegix/koeiro/issues
DefaultDirName={code:KoeiroDir}
DisableProgramGroupPage=yes
DisableWelcomePage=no
LicenseFile={#StageDir}\LICENSE.txt
OutputDir={#OutDir}
OutputBaseFilename=koeiro-{#MyTag}-ai-pack
SetupIconFile={#RepoRoot}\assets\icon.ico
UninstallDisplayIcon={app}\Koeiro.exe
UninstallDisplayName={#MyAppName}
Compression=lzma2/fast
SolidCompression=no
DiskSpanning=yes
; Bytes, not MB. BOOTH caps one file at 1.2 GB, and part 1 also carries the setup stub,
; so the slices stay under 1.05 GB.
DiskSliceSize=1050000000
WizardStyle=modern
ArchitecturesAllowed=x64compatible
PrivilegesRequired=lowest
CloseApplications=yes
RestartApplications=no
SetupLogging=yes
VersionInfoVersion={#MyAppVersion}
VersionInfoProductName={#MyAppName}

[Languages]
Name: "ja"; MessagesFile: "compiler:Languages\Japanese.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "{#StageDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Code]
// The pack has no business inventing an install folder: it belongs next to Koeiro.exe.
// Read where the app was installed from its own uninstall key, and fall back to the
// app's default per-user location when the key is missing.
function KoeiroDir(Param: String): String;
var
  Location: String;
  Key: String;
begin
  Key := 'Software\Microsoft\Windows\CurrentVersion\Uninstall\' + '{#KoeiroAppId}_is1';
  Result := ExpandConstant('{localappdata}\Programs\Koeiro');
  Location := '';
  if RegQueryStringValue(HKCU, Key, 'InstallLocation', Location) and (Location <> '') then
    Result := Location
  else if RegQueryStringValue(HKCU64, Key, 'InstallLocation', Location) and (Location <> '') then
    Result := Location;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    // Loud, but not fatal: without Koeiro.exe this pack is a folder of files nothing runs.
    if not FileExists(ExpandConstant('{app}\Koeiro.exe')) then
      Log('WARNING: no Koeiro.exe in ' + ExpandConstant('{app}') + ' - install Koeiro first');
  end;
end;
