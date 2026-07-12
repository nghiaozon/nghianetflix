[CmdletBinding()]
param(
    [ValidateSet("major", "minor", "patch")]
    [string]$Bump = "patch",
    [string]$Version,
    [ValidateSet("exe", "zip")]
    [string]$Package = "exe",
    [string]$Notes = "Cập nhật và cải thiện ứng dụng.",
    [switch]$SkipBuild,
    [switch]$NoPush
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
Set-Location $PSScriptRoot

$Repository = "nghiaozon/nghianetflix"
$ExecutableName = "NetflixManager.exe"
$VersionFile = Join-Path $PSScriptRoot "app_version.py"
$ManifestFile = Join-Path $PSScriptRoot "update.json"
$Git = "C:\Program Files\Git\cmd\git.exe"

function Write-Step([string]$Message) {
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Fail([string]$Message) {
    throw "PHAT HANH THAT BAI: $Message"
}

function Get-CurrentVersion {
    $content = Get-Content -LiteralPath $VersionFile -Raw -Encoding UTF8
    if ($content -notmatch 'APP_VERSION\s*=\s*"(?<version>\d+\.\d+\.\d+)"') {
        Fail "Khong doc duoc APP_VERSION trong app_version.py."
    }
    return $Matches.version
}

function Get-NextVersion([string]$Current, [string]$Part) {
    $numbers = @($Current.Split('.') | ForEach-Object { [int]$_ })
    switch ($Part) {
        "major" { return "{0}.0.0" -f ($numbers[0] + 1) }
        "minor" { return "{0}.{1}.0" -f $numbers[0], ($numbers[1] + 1) }
        default { return "{0}.{1}.{2}" -f $numbers[0], $numbers[1], ($numbers[2] + 1) }
    }
}

function Invoke-Git([string[]]$Arguments) {
    & $Git @Arguments
    if ($LASTEXITCODE -ne 0) { Fail "Git loi khi chay: git $($Arguments -join ' ')" }
}

$originalVersionContent = Get-Content -LiteralPath $VersionFile -Raw -Encoding UTF8
$originalManifestContent = Get-Content -LiteralPath $ManifestFile -Raw -Encoding UTF8
$sourceCommitted = $false

try {
    if (-not (Test-Path -LiteralPath $Git)) { Fail "Khong tim thay Git tai $Git" }

    $currentVersion = Get-CurrentVersion
    if ([string]::IsNullOrWhiteSpace($Version)) {
        $Version = Get-NextVersion $currentVersion $Bump
    }
    if ($Version -notmatch '^\d+\.\d+\.\d+$') { Fail "Version phai co dang X.Y.Z (vi du 1.2.0)." }
    if ([version]$Version -le [version]$currentVersion) { Fail "Version moi ($Version) phai lon hon $currentVersion." }

    Write-Step "Cap nhat version $currentVersion -> $Version"
    $versionContent = Get-Content -LiteralPath $VersionFile -Raw -Encoding UTF8
    $versionContent = $versionContent -replace 'APP_VERSION\s*=\s*"\d+\.\d+\.\d+"', "APP_VERSION = `"$Version`""
    [IO.File]::WriteAllText($VersionFile, $versionContent, [Text.UTF8Encoding]::new($false))

    if (-not $SkipBuild) {
        Write-Step "Build va smoke-test file EXE"
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "build.ps1")
        if ($LASTEXITCODE -ne 0) { Fail "build.ps1 tra ve exit code $LASTEXITCODE." }
    }

    $exePath = Join-Path $PSScriptRoot "dist\$ExecutableName"
    if (-not (Test-Path -LiteralPath $exePath)) { Fail "Khong tim thay $exePath" }

    $assetPath = $exePath
    if ($Package -eq "zip") {
        Write-Step "Nen goi phat hanh ZIP"
        $assetPath = Join-Path $PSScriptRoot "dist\NetflixManager-$Version.zip"
        if (Test-Path -LiteralPath $assetPath) { Remove-Item -LiteralPath $assetPath -Force }
        Compress-Archive -LiteralPath $exePath -DestinationPath $assetPath -CompressionLevel Optimal
    }
    $assetName = Split-Path -Leaf $assetPath
    $hash = (Get-FileHash -LiteralPath $assetPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $downloadUrl = "https://github.com/$Repository/releases/download/v$Version/$assetName"
    $manifest = [ordered]@{
        version = $Version
        download_url = $downloadUrl
        changelog = $Notes
        package_type = $Package
        package_name = $assetName
        file_name = $assetName
        executable_name = $ExecutableName
        sha256 = $hash
        require_authenticode = $false
        publisher = ""
    }
    [IO.File]::WriteAllText(
        $ManifestFile,
        (($manifest | ConvertTo-Json -Depth 5) + "`n"),
        [Text.UTF8Encoding]::new($false)
    )

    Write-Step "Kiem tra manifest va chay unit test"
    $python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $python)) { Fail "Khong tim thay Python trong .venv sau khi build." }
    & $python -c "import json, updater; updater.validate_manifest(json.load(open('update.json', encoding='utf-8')), require_hash=True)"
    if ($LASTEXITCODE -ne 0) { Fail "update.json khong hop le." }
    & $python -m unittest discover -s tests -v
    if ($LASTEXITCODE -ne 0) { Fail "Unit test that bai." }

    if ($NoPush) {
        Write-Host "`nDa tao ban phat hanh cuc bo v$Version (khong upload do dung -NoPush)." -ForegroundColor Yellow
        exit 0
    }

    Write-Step "Commit va push ma nguon/manifest"
    Invoke-Git @("add", "-A")
    & $Git diff --cached --quiet
    if ($LASTEXITCODE -ne 0) { Invoke-Git @("commit", "-m", "Release v$Version") }
    $sourceCommitted = $true
    $branch = (& $Git branch --show-current).Trim()
    if (-not $branch) { Fail "Khong xac dinh duoc nhanh Git hien tai." }
    Invoke-Git @("push", "origin", $branch)

    Write-Step "Tao va push tag v$Version"
    & $Git rev-parse --verify --quiet "refs/tags/v$Version" | Out-Null
    if ($LASTEXITCODE -eq 0) { Fail "Tag v$Version da ton tai." }
    Invoke-Git @("tag", "-a", "v$Version", "-m", "Netflix Manager v$Version")
    Invoke-Git @("push", "origin", "v$Version")

    Write-Host "`nDA GUI YEU CAU PHAT HANH v$Version LEN GITHUB" -ForegroundColor Green
    Write-Host "GitHub Actions se build, xac minh va tao Release tu dong."
    Write-Host "Theo doi: https://github.com/$Repository/actions"
} catch {
    if (-not $sourceCommitted) {
        [IO.File]::WriteAllText($VersionFile, $originalVersionContent, [Text.UTF8Encoding]::new($false))
        [IO.File]::WriteAllText($ManifestFile, $originalManifestContent, [Text.UTF8Encoding]::new($false))
        Write-Host "Da khoi phuc version va manifest ban dau." -ForegroundColor Yellow
    }
    Write-Host "`n$($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Da dung quy trinh. Xem loi o tren va chay lai sau khi sua." -ForegroundColor Yellow
    exit 1
}
