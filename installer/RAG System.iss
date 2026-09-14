; Inno Setup script: RAG System (ядро, Flask API :11455)
; Собирает installer из dist/RAG System/ (результат PyInstaller build.spec).
; Per-user установка ({localappdata}): сервер пишет settings.json/.cache рядом
; с exe, поэтому каталог должен быть доступен на запись без админа.

#define MyAppName "RAG System"
#define MyAppVersion "26.06.25"
#define MyAppPublisher "RAG System"
#define MyAppExeName "RAG System.exe"

[Setup]
AppId={{55F3C9D1-4A2B-4C3D-8E4F-1A2B3C4D5E6F}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=Output
OutputBaseFilename=RAG-System-Setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
DisableWelcomePage=no

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; settings.json и .cache — локальные данные машины сборки, в установщик не входят.
Source: "..\RAG System\dist\RAG System\*"; DestDir: "{app}"; Excludes: "settings.json,.cache"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Messages]
SetupWindowTitle=Установка {#MyAppName}
WelcomeLabel2=[name] установит [name/ver] на ваш компьютер.%n%nСервер предоставляет HTTP API на порту 11455 (префикс /rag).
FinishedLabel=Установка {#MyAppName} завершена.