#ifndef AppVersion
  #define AppVersion "0.6.0"
#endif
#ifndef PackageDir
  #error PackageDir must be set by build_windows.py
#endif
#ifndef OutputDir
  #error OutputDir must be set by build_windows.py
#endif
[Setup]
AppId={{A1AC4053-95FA-42D0-9165-9B80C19E763B}
AppName=校园乐跑助手
AppVersion={#AppVersion}
AppPublisher=Campus Route Studio
AppPublisherURL=https://github.com/Chanray-May9/campus-route-studio
DefaultDirName={localappdata}\Programs\CampusRouteStudio
DefaultGroupName=校园乐跑助手
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#OutputDir}
OutputBaseFilename=CampusRouteStudio-Windows-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayName=校园乐跑助手
UninstallDisplayIcon={app}\CampusRouteStudio.exe
CloseApplications=yes
SetupMutex=CampusRouteStudioSetup
LicenseFile=..\LICENSE
[Languages]
Name: "chinesesimp"; MessagesFile: "ChineseSimplified.isl"
[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; Flags: checkedonce
[Files]
Source: "{#PackageDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{group}\校园乐跑助手"; Filename: "{app}\CampusRouteStudio.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\校园乐跑助手"; Filename: "{app}\CampusRouteStudio.exe"; WorkingDir: "{app}"; Tasks: desktopicon
[Run]
Filename: "{app}\CampusRouteStudio.exe"; Description: "打开校园乐跑助手"; Flags: nowait postinstall skipifsilent

[Code]
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  Result := '';
  if FileExists(ExpandConstant('{app}\CampusRouteStudio.exe')) then
    Exec(ExpandConstant('{app}\CampusRouteStudio.exe'), '--quit', ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;
