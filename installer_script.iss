[Setup]
AppName=BPSR Module Optimizer
AppVersion=1.0
AppPublisher=MrSnake
DefaultDirName={autopf}\BPSR Module Optimizer
DefaultGroupName=BPSR Module Optimizer
AllowNoIcons=yes
LicenseFile=LICENSE
OutputDir=Output
OutputBaseFilename=BPSR Module Optimizer Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\BPSR-Module-Optimizer.exe
PrivilegesRequired=admin
DisableProgramGroupPage=yes

[Files]
Source: "dist\BPSR-Module-Optimizer\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "npcap-1.86.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall

[Icons]
Name: "{autoprograms}\BPSR Module Optimizer"; Filename: "{app}\BPSR-Module-Optimizer.exe"; IconFilename: "{app}\icon.ico"
Name: "{autodesktop}\BPSR Module Optimizer"; Filename: "{app}\BPSR-Module-Optimizer.exe"; IconFilename: "{app}\icon.ico"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "npcap"; Description: "Install Npcap (required for packet capture)"; GroupDescription: "Optional components"

[Run]
Filename: "{tmp}\npcap-1.86.exe"; StatusMsg: "Installing Npcap (required for packet capture)..."; Flags: waituntilterminated; Tasks: npcap
Filename: "{app}\BPSR-Module-Optimizer.exe"; Description: "Launch BPSR Module Optimizer"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{pf}\Npcap\uninstall.exe"; Flags: runhidden
