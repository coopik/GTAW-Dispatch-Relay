; Inno Setup script for 911 Dispatch Relay
; Compile with the Inno Setup Compiler (ISCC.exe) or let build.bat do it.
; Works with Inno Setup 6 OR 7 (Inno 7 is fully backward compatible with 6 scripts).
; Download Inno Setup: https://jrsoftware.org/isdl.php

#define AppName "911 Dispatch Relay"
#define AppVersion "1.5.3"
#define AppPublisher "911 Dispatch Relay"
#define AppExeName "911 Dispatch Relay.exe"

[Setup]
AppId={{7B3D5A1C-9E42-4C7A-9C1E-911DISPATCH01}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
UninstallDisplayIcon={app}\{#AppExeName}
OutputDir=installer_output
OutputBaseFilename=911DispatchRelay-Setup-{#AppVersion}
SetupIconFile=assets\app.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
DisableProgramGroupPage=yes
; Let a silent in-app update replace files while the app closes.
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"

[Files]
; The entire PyInstaller output folder.
Source: "dist\911 Dispatch Relay\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent
