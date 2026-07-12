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

function Invoke-GitHubApi(
    [string]$Method,
    [string]$Uri,
    [object]$Body = $null,
    [string]$InFile = "",
    [string]$ContentType = "application/json"
) {
    $headers = @{
        Authorization = "Bearer $env:GITHUB_TOKEN"
        Accept = "application/vnd.github+json"
        "X-GitHub-Api-Version" = "2022-11-28"
        "User-Agent" = "NetflixManager-release-script"
    }
    $parameters = @{ Method = $Method; Uri = $Uri; Headers = $headers }
    if ($InFile) {
        $parameters.InFile = $InFile
        $parameters.ContentType = $ContentType
    } elseif ($null -ne $Body) {
        $parameters.Body = ($Body | ConvertTo-Json -Depth 10)
        $parameters.ContentType = "application/json; charset=utf-8"
    }
    return Invoke-RestMethod @parameters
}

try {
    if (-not (Test-Path -LiteralPath $Git)) { Fail "Khong tim thay Git tai $Git" }
    if (-not $NoPush -and [string]::IsNullOrWhiteSpace($env:GITHUB_TOKEN)) {
        Fail "Chua co GITHUB_TOKEN. Hay tao token co quyen Contents: Read and write, roi dat bien moi truong GITHUB_TOKEN."
    }

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
    $branch = (& $Git branch --show-current).Trim()
    if (-not $branch) { Fail "Khong xac dinh duoc nhanh Git hien tai." }
    Invoke-Git @("push", "origin", $branch)
    $targetCommit = (& $Git rev-parse HEAD).Trim()

    Write-Step "Tao GitHub Release dang draft"
    $api = "https://api.github.com/repos/$Repository"
    try {
        $release = Invoke-GitHubApi "GET" "$api/releases/tags/v$Version"
        $release = Invoke-GitHubApi "PATCH" "$api/releases/$($release.id)" @{
            name = "Netflix Manager v$Version"; body = $Notes; draft = $true; prerelease = $false
        }
    } catch {
        if ($_.Exception.Response -and [int]$_.Exception.Response.StatusCode -eq 404) {
            $release = Invoke-GitHubApi "POST" "$api/releases" @{
                tag_name = "v$Version"; target_commitish = $targetCommit
                name = "Netflix Manager v$Version"; body = $Notes; draft = $true; prerelease = $false
            }
        } else { throw }
    }

    Write-Step "Upload $assetName va update.json"
    $packageAssetId = $null
    foreach ($upload in @($assetPath, $ManifestFile)) {
        $name = Split-Path -Leaf $upload
        foreach ($oldAsset in @($release.assets | Where-Object { $_.name -eq $name })) {
            Invoke-GitHubApi "DELETE" "$api/releases/assets/$($oldAsset.id)" | Out-Null
        }
        $encodedName = [Uri]::EscapeDataString($name)
        $uploadedAsset = Invoke-GitHubApi "POST" "https://uploads.github.com/repos/$Repository/releases/$($release.id)/assets?name=$encodedName" $null $upload "application/octet-stream"
        if ($name -eq $assetName) { $packageAssetId = $uploadedAsset.id }
    }

    Write-Step "Tai lai asset va xac minh SHA-256"
    if (-not $packageAssetId) { Fail "GitHub khong tra ve ID cua package da upload." }
    $verifyPath = Join-Path ([IO.Path]::GetTempPath()) "NetflixManager-release-$Version-$assetName"
    try {
        $downloadHeaders = @{
            Authorization = "Bearer $env:GITHUB_TOKEN"
            Accept = "application/octet-stream"
            "X-GitHub-Api-Version" = "2022-11-28"
            "User-Agent" = "NetflixManager-release-script"
        }
        Invoke-WebRequest -Uri "$api/releases/assets/$packageAssetId" -Headers $downloadHeaders -OutFile $verifyPath -UseBasicParsing
        $uploadedHash = (Get-FileHash -LiteralPath $verifyPath -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($uploadedHash -ne $hash) { Fail "Asset tren GitHub khong khop SHA-256 cua ban build." }
    } finally {
        Remove-Item -LiteralPath $verifyPath -Force -ErrorAction SilentlyContinue
    }

    Write-Step "Cong bo Release"
    $published = Invoke-GitHubApi "PATCH" "$api/releases/$($release.id)" @{ draft = $false }
    Write-Host "`nPHAT HANH THANH CONG v$Version" -ForegroundColor Green
    Write-Host $published.html_url
    Write-Host "SHA-256: $hash"
} catch {
    Write-Host "`n$($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Da dung quy trinh; GitHub Release draft (neu da tao) khong duoc cong bo." -ForegroundColor Yellow
    exit 1
}
