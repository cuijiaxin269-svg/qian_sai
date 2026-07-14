param(
    [string]$OutputDir = "D:\ji_chuang\control_app_portable",
    [switch]$Zip
)

$ErrorActionPreference = "Stop"

$AppDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonRoot = "C:\Users\lenovo\AppData\Local\Programs\Python\Python314"
$UserSite = "C:\Users\lenovo\AppData\Roaming\Python\Python314\site-packages"

if (-not (Test-Path -LiteralPath (Join-Path $AppDir "control.py"))) {
    throw "control.py was not found in $AppDir"
}

if (-not (Test-Path -LiteralPath (Join-Path $PythonRoot "python.exe"))) {
    throw "Python was not found at $PythonRoot"
}

if (Test-Path -LiteralPath $OutputDir) {
    Remove-Item -LiteralPath $OutputDir -Recurse -Force
}

$PythonOut = Join-Path $OutputDir "python"
$AppOut = Join-Path $OutputDir "app"

New-Item -ItemType Directory -Force -Path $PythonOut, $AppOut | Out-Null

Write-Host "Copying Python runtime..."
robocopy $PythonRoot $PythonOut /MIR /XD "__pycache__" /XF "*.pyc" | Out-Null
if ($LASTEXITCODE -ge 8) {
    throw "robocopy failed while copying Python runtime. Exit code: $LASTEXITCODE"
}

$PortableSite = Join-Path $PythonOut "Lib\site-packages"
New-Item -ItemType Directory -Force -Path $PortableSite | Out-Null

if (Test-Path -LiteralPath $UserSite) {
    Write-Host "Copying user site-packages..."
    robocopy $UserSite $PortableSite /E /XD "__pycache__" /XF "*.pyc" | Out-Null
    if ($LASTEXITCODE -ge 8) {
        throw "robocopy failed while copying user site-packages. Exit code: $LASTEXITCODE"
    }
}

Write-Host "Copying app files..."
Copy-Item -LiteralPath (Join-Path $AppDir "control.py") -Destination (Join-Path $AppOut "control.py") -Force

@'
@echo off
setlocal

cd /d "%~dp0"

set "PYTHONHOME=%~dp0python"
set "PYTHONPATH=%~dp0python\Lib;%~dp0python\Lib\site-packages"
set "PATH=%~dp0python;%~dp0python\Scripts;%PATH%"

"%~dp0python\python.exe" -m streamlit run "%~dp0app\control.py"

echo.
echo The app has stopped.
pause
'@ | Set-Content -LiteralPath (Join-Path $OutputDir "start_control_app.cmd") -Encoding ASCII

@'
This is a portable Streamlit control app package.

How to use:
1. Copy this whole folder to another Windows computer.
2. Double-click "start_control_app.cmd".
3. The browser page will open automatically.

Notes:
- The target computer does not need Python installed.
- Keep the "python" and "app" folders next to "start_control_app.cmd".
- For serial devices, install the USB-to-serial driver on the target computer if Windows does not recognize the COM port.
'@ | Set-Content -LiteralPath (Join-Path $OutputDir "README.txt") -Encoding ASCII

if ($Zip) {
    $ZipPath = "$OutputDir.zip"
    if (Test-Path -LiteralPath $ZipPath) {
        Remove-Item -LiteralPath $ZipPath -Force
    }
    Compress-Archive -LiteralPath $OutputDir -DestinationPath $ZipPath -Force
    Write-Host "ZIP created: $ZipPath"
}

Write-Host "Portable package created: $OutputDir"
