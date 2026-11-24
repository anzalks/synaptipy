#ifndef MyAppVersion
#define MyAppVersion "0.1.9"
#endif

[Setup]
AppId={{8E4C7A2D-5B91-4F3E-A6D2-9C1B8E7F4A10}
AppName=Synaptipy
AppVersion={#MyAppVersion}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
; Allow both admin and non-admin installation
; Admin: installs to 64-bit Program Files (system-wide)
; Non-admin: installs to user's AppData\Local\Programs (per-user)
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DefaultDirName={autopf}\Synaptipy
DefaultGroupName=Synaptipy
SetupIconFile=..\src\synaptipy\resources\icons\logo.ico
UninstallDisplayIcon={app}\synaptipy.exe
OutputBaseFilename=Synaptipy_Setup_{#MyAppVersion}
Compression=lzma2
CompressionThreads=auto
SolidCompression=yes
OutputDir=..

[InstallDelete]
; Purge previous PyInstaller runtime directory before upgrading so removed or
; renamed .pyd/.dll modules from older releases cannot collide at import time.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\dist\synaptipy\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\src\synaptipy\resources\icons\logo.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Synaptipy"; Filename: "{app}\synaptipy.exe"; IconFilename: "{app}\logo.ico"
Name: "{autodesktop}\Synaptipy"; Filename: "{app}\synaptipy.exe"; IconFilename: "{app}\logo.ico"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
