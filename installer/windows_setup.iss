#ifndef MyAppVersion
#define MyAppVersion "0.1.5b2"
#endif

[Setup]
AppName=Synaptipy
AppVersion={#MyAppVersion}
; Allow both admin and non-admin installation
; Admin: installs to Program Files (system-wide)
; Non-admin: installs to user's AppData\Local (per-user)
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DefaultDirName={autopf}\Synaptipy
; When running without admin, {autopf} becomes {localappdata}\Programs automatically
DefaultGroupName=Synaptipy
OutputBaseFilename=Synaptipy_Setup_{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
OutputDir=..

[Files]
Source: "..\dist\Synaptipy\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\src\Synaptipy\resources\icons\logo.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Synaptipy"; Filename: "{app}\Synaptipy.exe"; IconFilename: "{app}\logo.ico"
Name: "{autodesktop}\Synaptipy"; Filename: "{app}\Synaptipy.exe"; IconFilename: "{app}\logo.ico"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
