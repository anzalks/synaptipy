#ifndef MyAppVersion
#define MyAppVersion "0.1.2b2"
#endif

[Setup]
AppName=Synaptipy
AppVersion={#MyAppVersion}
DefaultDirName={autopf}\Synaptipy
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
