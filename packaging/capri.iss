; Inno Setup script: turns dist\Capri into one Capri-Setup-<version>.exe installer.
; build.bat runs this automatically if Inno Setup 6 is installed (https://jrsoftware.org/isdl.php).
;
; * Installs for the current user only (no admin prompt) into %LOCALAPPDATA%\Programs\Capri
; * Start menu shortcut, optional desktop shortcut, optional "Start with Windows"
; * Uninstaller removes the program and the startup entry. Your settings
;   (%LOCALAPPDATA%\Capri) are kept unless you tick the box to remove them.

#define AppName "Capri"
#ifndef AppVersion
  #define AppVersion "2.3.3"
#endif

[Setup]
AppId={{6C1D7A55-3F3E-4C61-9B7B-CA9B1C0E2077}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Capri desktop companion
DefaultDirName={localappdata}\Programs\Capri
DefaultGroupName=Capri
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=Capri-Setup-{#AppVersion}
SetupIconFile=..\assets\capri\app_icon.ico
UninstallDisplayIcon={app}\Capri.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked
Name: "autostart"; Description: "Start Capri with Windows (she greets you when you sign in)"

[Files]
Source: "..\dist\Capri\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\Capri"; Filename: "{app}\Capri.exe"
Name: "{group}\Uninstall Capri"; Filename: "{uninstallexe}"
Name: "{userdesktop}\Capri"; Filename: "{app}\Capri.exe"; Tasks: desktopicon

[Registry]
; Same entry Capri's own "Start with Windows" menu item uses, so they stay in sync.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Capri"; \
    ValueData: """{app}\Capri.exe"" --startup"; Tasks: autostart; Flags: uninsdeletevalue

[Run]
Filename: "{app}\Capri.exe"; Description: "Start Capri now"; Flags: nowait postinstall skipifsilent
; Capri updating herself (/update=1, silent): start her again afterwards.
Filename: "{app}\Capri.exe"; Flags: nowait; Check: IsCapriUpdate

[UninstallRun]
Filename: "{cmd}"; Parameters: "/C taskkill /IM Capri.exe /F"; Flags: runhidden; RunOnceId: "StopCapri"

[UninstallDelete]
Type: dirifempty; Name: "{app}"

[Code]
function IsCapriUpdate: Boolean;
begin
  Result := ExpandConstant('{param:update|0}') = '1';
end;

// Capri updating herself: she quits right after starting this installer. Wait (up to 30 s) until
// she has really gone, so her files aren't in use and nothing is half-replaced.
function InitializeSetup: Boolean;
var
  Waited: Integer;
begin
  Waited := 0;
  if IsCapriUpdate then
    while CheckForMutexes('CapriCompanionRunning') and (Waited < 30000) do
    begin
      Sleep(250);
      Waited := Waited + 250;
    end;
  Result := True;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
  begin
    RegDeleteValue(HKEY_CURRENT_USER, 'Software\Microsoft\Windows\CurrentVersion\Run', 'Capri');
    if MsgBox('Also delete your Capri settings, app list and Spotify / AI keys?', mbConfirmation, MB_YESNO) = IDYES then
      DelTree(ExpandConstant('{localappdata}\Capri'), True, True, True);
  end;
end;
