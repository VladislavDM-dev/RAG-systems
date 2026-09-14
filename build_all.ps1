# Сборка обоих серверов в standalone EXE (PyInstaller, onedir).
# Используется собственный .venv каждого проекта (как и для запуска).
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path

& (Join-Path $Root "build_rag_system.ps1")
if ($LASTEXITCODE -ne 0) { throw "Сборка RAG System завершилась с ошибкой" }

& (Join-Path $Root "build_web_ui.ps1")
if ($LASTEXITCODE -ne 0) { throw "Сборка RAG System Web UI завершилась с ошибкой" }

Write-Host ""
Write-Host "Готово:"
Write-Host "  $Root\RAG System\dist\RAG System\RAG System.exe"
Write-Host "  $Root\RAG System Web UI\dist\RAG System Web UI\RAG System Web UI.exe"
