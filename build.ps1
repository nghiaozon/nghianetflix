$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Host "Tao moi truong ao .venv..."
    py -3 -m venv .venv
}

& $python -m pip install --upgrade pip
& $python -m pip install -r requirements.txt
& $python -m PyInstaller --noconfirm --clean NetflixManager.spec

$dataDir = Join-Path $PSScriptRoot "dist\data"
$configDir = Join-Path $PSScriptRoot "dist\config"
New-Item -ItemType Directory -Force -Path $dataDir | Out-Null
New-Item -ItemType Directory -Force -Path $configDir | Out-Null

# Chỉ tạo dữ liệu ban đầu khi chưa có; tuyệt đối không ghi đè dữ liệu người dùng.
if ((Test-Path "netflix_manager.db") -and -not (Test-Path "$dataDir\netflix_manager.db")) {
    Copy-Item "netflix_manager.db" "$dataDir\netflix_manager.db"
}
if ((Test-Path ".env") -and -not (Test-Path "$configDir\.env")) {
    Copy-Item ".env" "$configDir\.env"
}
if ((Test-Path "credentials.json") -and -not (Test-Path "$configDir\credentials.json")) {
    Copy-Item "credentials.json" "$configDir\credentials.json"
}

Write-Host "Build xong: $PSScriptRoot\dist\NetflixManager.exe"
