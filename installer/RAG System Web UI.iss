; Inno Setup script: RAG System Web UI (Flask :80, проксирует /rag/* на ядро)
; Собирает installer из dist/RAG System Web UI/ (результат PyInstaller build.spec).
; Per-user установка ({localappdata}): приложение пишет users.json/data рядом
; с exe, поэтому каталог должен быть доступен на запись без админа.
; ВАЖНО: корпус (out/) сюда не входит. При желании укажите MEMO_CORPUS_DIR.

#define MyAppName "RAG System Web UI"
#define MyAppVersion "26.06.25"
#define MyAppPublisher "RAG System"
#define MyAppExeName "RAG System Web UI.exe"

[Setup]
AppId={{77A1B2C3-D4E5-4F6A-8B9C-D0E1F2A3B4C5}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=Output
OutputBaseFilename=RAG-System-WebUI-Setup-{#MyAppVersion}
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
; users.json/data — локальные данные машины сборки, в установщик не входят.
Source: "..\RAG System Web UI\dist\RAG System Web UI\*"; DestDir: "{app}"; Excludes: "users.json,data"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Messages]
SetupWindowTitle=Установка {#MyAppName}
WelcomeLabel2=[name] установит [name/ver] на ваш компьютер.%n%nВеб-интерфейс слушает порт 80 и проксирует /rag/* на ядро (127.0.0.1:11455).%nДля порта отличного от 80 задайте переменную окружения PORT перед запуском.
FinishedLabel=Установка {#MyAppName} завершена.