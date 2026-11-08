; Instalator LocalChef Studia (Inno Setup 6).
; Sestaveni:  iscc /DAppVersion=1.6 installer\localchef_studio.iss
; Predpoklad: build_exe.bat uz vytvoril dist\LocalChefStudio (PyInstaller).
;
; Instaluje se pro aktualniho uzivatele do %LOCALAPPDATA%\Programs\LocalChef Studio (bez administratora).
; Aplikace tak muze mit data (localchef_data) vedle programu. Data se pri odinstalaci NEMAZOU.

#ifndef AppVersion
  #define AppVersion "1.6"
#endif
#ifndef SourceDir
  #define SourceDir "..\dist\LocalChefStudio"
#endif
#define AppName "LocalChef Studio"
#define AppExe "LocalChefStudio.exe"

[Setup]
AppId={{1EAC7825-CD32-49AA-B622-6823010A04B3}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=John Preclik
AppPublisherURL=https://github.com/johnpreclik/localchef-studio
AppSupportURL=https://github.com/johnpreclik/localchef-studio
AppComments=Offline recipe manager, parser, and converter for smart kitchen appliances.
VersionInfoVersion={#AppVersion}
VersionInfoProductName={#AppName}
VersionInfoDescription={#AppName} Setup
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName} {#AppVersion}
LicenseFile=..\LICENSE
InfoBeforeFile=..\DISCLAIMER.txt
OutputDir=..\dist_installer
OutputBaseFilename=LocalChef_Studio_{#AppVersion}
Compression=lzma2/normal
SolidCompression=no
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
ShowLanguageDialog=auto

[Languages]
Name: "czech"; MessagesFile: "compiler:Languages\Czech.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\LICENSE"; DestDir: "{app}"; DestName: "LICENSE.txt"; Flags: ignoreversion
Source: "..\docs\*.pdf"; DestDir: "{app}\docs"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
; update from the app: a silent install with /relaunch=1 starts the app again afterwards
Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; Flags: nowait runasoriginaluser; Check: RelaunchAfterUpdate

[UninstallDelete]
; jen docasne soubory programu – recepty, nastaveni a prihlaseni (localchef_data) zustanou
Type: filesandordirs; Name: "{app}\__pycache__"

[Code]
function RelaunchAfterUpdate: Boolean;
begin
  Result := ExpandConstant('{param:relaunch|0}') = '1';
end;
