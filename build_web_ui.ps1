# Сборка Web UI RAG System в standalone EXE (PyInstaller, onedir).
# Используется собственный venv проекта.
# ВАЖНО: без $ErrorActionPreference="Stop" — PyInstaller пишет INFO в stderr,
# и в PowerShell 5.1 это превратится в завершающую ошибку (NativeCommandError).

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Project = "RAG System Web UI"
$venvPy = Join-Path $Root "$Project\.venv\Scripts\python.exe"

if (-not (Test-Path $venvPy)) {
    throw "Нет venv: $venvPy"
}

# PyInstaller ставится в venv проекта при первом использовании.
& $venvPy -m pip show pyinstaller *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "    установка PyInstaller..."
    & $venvPy -m pip install pyinstaller
    if ($LASTEXITCODE -ne 0) { throw "pip install pyinstaller ($Project)" }
}

Push-Location (Join-Path $Root $Project)
try {
    & $venvPy -m PyInstaller --noconfirm --clean --log-level=WARN build.spec
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller ($Project)" }
}
finally {
    Pop-Location
}
Write-Host "Готово: $Root\$Project\dist\RAG System Web UI\RAG System Web UI.exe"

