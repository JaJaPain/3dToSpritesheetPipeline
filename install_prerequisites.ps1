# Automated Installer for VS Build Tools & CUDA Toolkit 12.1 for Windows
# Run this script to configure system prerequisites for TRELLIS extensions.

$workDir = "c:\CodingProjects\3D_To_Spritesheet"
$tempDir = Join-Path $workDir "temp_installers"

if (-not (Test-Path $tempDir)) {
    New-Item -ItemType Directory -Path $tempDir | Out-Null
}

# Speed up Invoke-WebRequest by disabling progress stream
$ProgressPreference = 'SilentlyContinue'

# 1. Check & Install VS Build Tools 2022
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "1. Checking for Visual Studio Build Tools..." -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan

$vsWherePath = "C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe"
$vsInstalled = $false

if (Test-Path $vsWherePath) {
    $vsInstalledOutput = & $vsWherePath -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
    if ($vsInstalledOutput) {
        $vsInstalled = $true
        Write-Host "Visual Studio C++ Build Tools are already installed at: $vsInstalledOutput" -ForegroundColor Green
    }
}

if (-not $vsInstalled) {
    Write-Host "Visual Studio Build Tools not found. Downloading installer..." -ForegroundColor Yellow
    $vsUrl = "https://aka.ms/vs/17/release/vs_buildtools.exe"
    $vsPath = Join-Path $tempDir "vs_buildtools.exe"
    
    Write-Host "Downloading vs_buildtools.exe from $vsUrl..."
    Invoke-WebRequest -Uri $vsUrl -OutFile $vsPath
    
    Write-Host "Launching Visual Studio Build Tools installer (requires Administrator approval in UAC popup)..." -ForegroundColor Yellow
    # Installs the MSVC compiler, Windows SDK, and recommended tools silently
    $process = Start-Process -FilePath $vsPath -ArgumentList "--quiet --wait --norestart --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended" -Verb RunAs -PassThru -Wait
    
    if ($process.ExitCode -eq 0) {
        Write-Host "Visual Studio Build Tools installed successfully!" -ForegroundColor Green
    } else {
        Write-Warning "Visual Studio Build Tools installation returned code: $($process.ExitCode). Please check if you accepted the UAC prompt."
    }
}

# 2. Check & Install CUDA Toolkit 12.1.1
Write-Host ""
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "2. Checking for CUDA Toolkit 12.1..." -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan

$cudaPath = $env:CUDA_PATH
if (-not $cudaPath) {
    $cudaDirs = Get-ChildItem "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA" -ErrorAction SilentlyContinue
    if ($cudaDirs) {
        $cudaPath = $cudaDirs[0].FullName
    }
}

if (-not $cudaPath) {
    Write-Host "CUDA Toolkit 12.1 not found. Downloading CUDA 12.1.1 local installer (approx. 3 GB)..." -ForegroundColor Yellow
    $cudaUrl = "https://developer.download.nvidia.com/compute/cuda/12.1.1/local_installers/cuda_12.1.1_531.14_windows.exe"
    $cudaPathExe = Join-Path $tempDir "cuda_12.1.1_531.14_windows.exe"
    
    Write-Host "Downloading CUDA installer from $cudaUrl... (this may take a few minutes depending on connection speed)"
    Invoke-WebRequest -Uri $cudaUrl -OutFile $cudaPathExe
    
    Write-Host "Launching CUDA Toolkit installer silently (requires Administrator approval in UAC popup)..." -ForegroundColor Yellow
    # -s runs installer silently with default settings (installs Toolkit and necessary runtime components)
    $process = Start-Process -FilePath $cudaPathExe -ArgumentList "-s" -Verb RunAs -PassThru -Wait
    
    if ($process.ExitCode -eq 0) {
        Write-Host "CUDA Toolkit 12.1 installed successfully!" -ForegroundColor Green
    } else {
        Write-Warning "CUDA Toolkit installer returned code: $($process.ExitCode). Please check if you accepted the UAC prompt."
    }
} else {
    Write-Host "CUDA Toolkit 12.1 is already installed at: $cudaPath" -ForegroundColor Green
}

Write-Host ""
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "Prerequisites check complete! Please restart your terminal to reload new path variables." -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
