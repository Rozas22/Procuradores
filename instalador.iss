; Instalador de Windows (Inno Setup 6). Se instala para el usuario actual, sin pedir permisos de administrador.
#define AppName "Escritos Procura"
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{6C1E2B0A-6E4D-4E43-9A57-5E1C3A9D2F11}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppName}
DefaultDirName={localappdata}\Programs\EscritosProcura
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename=EscritosProcura-Instalador-{#AppVersion}
SetupIconFile=recursos\icono.ico
UninstallDisplayIcon={app}\EscritosProcura.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes
CloseApplications=yes
RestartApplications=no
UsePreviousAppDir=yes
DisableDirPage=auto

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "escritorio"; Description: "Crear un acceso directo en el escritorio"; Flags: checkedonce

[Files]
Source: "dist\EscritosProcura\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{userprograms}\{#AppName}"; Filename: "{app}\EscritosProcura.exe"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\EscritosProcura.exe"; Tasks: escritorio

[Run]
Filename: "{app}\EscritosProcura.exe"; Description: "Abrir {#AppName}"; Flags: nowait postinstall
