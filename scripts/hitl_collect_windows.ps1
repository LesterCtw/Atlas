param(
    [string]$TgenieUrl = "",
    [switch]$SkipInstall,
    [switch]$SkipProbe
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$OutDir = Join-Path $RepoRoot "hitl-output"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$TranscriptPath = Join-Path $OutDir "hitl-$Stamp.log"

function Write-Section {
    param([string]$Name)
    Write-Host ""
    Write-Host "=== $Name ==="
}

function Invoke-HitlStep {
    param(
        [string]$Name,
        [scriptblock]$Command,
        [switch]$Required
    )

    Write-Section $Name
    $global:LASTEXITCODE = 0

    try {
        & $Command
        $exitCode = $global:LASTEXITCODE
        if ($null -eq $exitCode) {
            $exitCode = 0
        }
        Write-Host "exit_code=$exitCode"

        if ($Required -and $exitCode -ne 0) {
            throw "Step failed with exit code $exitCode"
        }
    }
    catch {
        Write-Host "ERROR: $($_.Exception.Message)"
        if ($Required) {
            throw
        }
    }
}

Start-Transcript -Path $TranscriptPath -Force | Out-Null

try {
    Set-Location $RepoRoot

    Write-Section "HITL context"
    Write-Host "date=$(Get-Date -Format o)"
    Write-Host "repo_root=$RepoRoot"
    Write-Host "powershell_version=$($PSVersionTable.PSVersion)"
    Write-Host "user=$env:USERNAME"
    Write-Host "computer=$env:COMPUTERNAME"
    Write-Host "appdata=$env:APPDATA"
    Write-Host "tgenie_url_provided=$(-not [string]::IsNullOrWhiteSpace($TgenieUrl))"

    Write-Section "Chrome candidates"
    $programFiles = [Environment]::GetEnvironmentVariable("ProgramFiles")
    $programFilesX86 = [Environment]::GetEnvironmentVariable("ProgramFiles(x86)")
    $localAppData = [Environment]::GetEnvironmentVariable("LocalAppData")
    $chromeCandidates = @(
        (Join-Path $programFiles "Google\Chrome\Application\chrome.exe"),
        (Join-Path $programFilesX86 "Google\Chrome\Application\chrome.exe"),
        (Join-Path $localAppData "Google\Chrome\Application\chrome.exe")
    )
    foreach ($candidate in $chromeCandidates) {
        Write-Host "$(Test-Path $candidate) $candidate"
    }

    $profileDir = Join-Path $env:APPDATA "Atlas\chrome-profile"
    Write-Section "Expected Atlas profile directory"
    Write-Host "profile_dir=$profileDir"
    Write-Host "profile_exists=$(Test-Path $profileDir)"

    Invoke-HitlStep "Python 3.12 version" {
        py -3.12 --version
    } -Required

    if (-not $SkipInstall) {
        Invoke-HitlStep "Create virtual environment" {
            py -3.12 -m venv .venv
        } -Required

        $venvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"

        Invoke-HitlStep "Install Atlas editable" {
            & $venvPython -m pip install -e .
        } -Required
    }
    else {
        $venvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
        Write-Section "Skip install"
        Write-Host "Using existing venv_python=$venvPython"
    }

    if (-not (Test-Path $venvPython)) {
        throw "Missing virtualenv Python at $venvPython"
    }

    $atlasExe = Join-Path $RepoRoot ".venv\Scripts\atlas.exe"

    Invoke-HitlStep "Atlas help" {
        & $atlasExe --help
    } -Required

    Invoke-HitlStep "tGenie probe help" {
        & $venvPython scripts\probe_tgenie.py --help
    } -Required

    Invoke-HitlStep "Compile Python files" {
        & $venvPython -m compileall atlas scripts
    } -Required

    if (-not $SkipProbe) {
        if ([string]::IsNullOrWhiteSpace($TgenieUrl)) {
            Write-Section "Skip interactive tGenie probe"
            Write-Host "No -TgenieUrl was provided."
            Write-Host "Manual command:"
            Write-Host ".\.venv\Scripts\python scripts\probe_tgenie.py --url `"https://your-tgenie-url`" --output-dir probe-output"
        }
        else {
            Invoke-HitlStep "Interactive tGenie probe" {
                & $venvPython scripts\probe_tgenie.py --url $TgenieUrl --output-dir probe-output
            }
        }
    }

    Write-Section "Output paths"
    Write-Host "transcript=$TranscriptPath"
    Write-Host "probe_output=$(Join-Path $RepoRoot "probe-output")"
    Write-Host "hitl_output=$OutDir"
}
finally {
    Stop-Transcript | Out-Null
    Write-Host ""
    Write-Host "HITL transcript written to: $TranscriptPath"
}
