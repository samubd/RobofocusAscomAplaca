; Inno Setup Script for Robofocus ASCOM Alpaca Driver
;
; To build the installer:
; 1. First run: python build.py
; 2. Then compile this script with Inno Setup Compiler
;
; To sign the installer (optional):
; - Set SignTool in Inno Setup: Tools -> Configure Sign Tools
; - Add: signtool=$qC:\Program Files (x86)\Windows Kits\10\bin\x64\signtool.exe$q sign /f $qYOUR_CERT.pfx$q /t http://timestamp.digicert.com /fd SHA256 $f
; - Uncomment SignTool line below
;
; Download Inno Setup from: https://jrsoftware.org/isinfo.php

#define MyAppName "Robofocus ASCOM Alpaca Driver"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Samuele Vecchi"
#define MyAppURL "https://github.com/samubd/RobofocusAscomAplaca"
#define MyAppExeName "RobofocusAlpaca.exe"

[Setup]
; NOTE: The value of AppId uniquely identifies this application.
AppId={{B8F3E2A1-5C4D-4E6F-8A9B-1C2D3E4F5A6B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\RobofocusAlpaca
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
LicenseFile=LICENSE
OutputDir=installer_output
OutputBaseFilename=RobofocusAlpaca_Setup_{#MyAppVersion}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
; Uncomment to sign the installer (requires SignTool configuration)
; SignTool=signtool

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "italian"; MessagesFile: "compiler:Languages\Italian.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "startupicon"; Description: "Start automatically with Windows"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Main application files from PyInstaller output
Source: "dist\RobofocusAlpaca\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; License file
Source: "LICENSE"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{commonstartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: startupicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Code]
// Add firewall rule for Alpaca discovery during installation
procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
begin
  if CurStep = ssPostInstall then
  begin
    // Add firewall rule for UDP discovery (port 32227)
    Exec('netsh', 'advfirewall firewall add rule name="Robofocus Alpaca Discovery" dir=in action=allow protocol=udp localport=32227', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    // Add firewall rule for HTTP server (port 5000)
    Exec('netsh', 'advfirewall firewall add rule name="Robofocus Alpaca Server" dir=in action=allow protocol=tcp localport=5000', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  end;
end;

// Remove firewall rules during uninstallation
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ResultCode: Integer;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    Exec('netsh', 'advfirewall firewall delete rule name="Robofocus Alpaca Discovery"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    Exec('netsh', 'advfirewall firewall delete rule name="Robofocus Alpaca Server"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  end;
end;
