# Reel Studio (Digitalni Mama Marcela): launcher for Windows 10 and 11.
#
# Usage:  powershell -NoProfile -ExecutionPolicy Bypass -File spust.ps1 <step> [options]   (the same steps as start.py)
#
# The computer needs nothing but what Windows ships (PowerShell 5.1, .NET). No Python, no winget, no admin rights,
# nothing installed system-wide. Everything lands in the studio data folder:
#   %USERPROFILE%\.claude-reel-studio               (REEL_STUDIO_DATA overrides it, for tests)
#   Not in AppData: the Claude app on Windows is a packaged (MSIX) app and Windows silently redirects
#   its writes to AppData into AppData\Local\Packages\Claude_...\LocalCache. Links uv makes there point to
#   the place that does not exist (found on a real Windows laptop, 12 Nov 2026). The home folder is not
#   redirected; Claude Code keeps its own .claude folder there too.
# What it does:
#   1. gets the studio its own copy of uv (pinned version, checked against its SHA-256) into <data>\uv
#   2. uv gets the studio its own Python 3.12 into <data>\python. Always the x64 build: the speech engine has no
#      Windows ARM build, and Windows 11 on ARM runs x64 programs. Only uv-managed Pythons are used, so the
#      Microsoft Store "python3" placeholder is never touched.
#   3. runs start.py with that Python
# Output: STATUS lines in English for Claude; start.py then prints its own Czech lines for the customer.
#
# Keep this file ASCII only: Windows PowerShell 5.1 reads a file without a byte order mark as ANSI, not UTF-8.

$ErrorActionPreference = 'Continue'
$ProgressPreference = 'SilentlyContinue'      # downloads are many times slower with the progress bar on

$UvVersion = '0.12.24'
$UvSha256  = '7c38608c8a18ee137d748a1773053b07ec8f3a30fab49aebaa6f4e4efeceb019'
$UvUrl     = "https://github.com/astral-sh/uv/releases/download/$UvVersion/uv-x86_64-pc-windows-msvc.zip"
$PyRequest = 'cpython-3.12-windows-x86_64-none'

$Here = Split-Path -Parent $MyInvocation.MyCommand.Path

$Data = $env:REEL_STUDIO_DATA
if (-not $Data) {
    $Home0 = $env:USERPROFILE
    if (-not $Home0) { $Home0 = $HOME }
    $Data = Join-Path $Home0 '.claude-reel-studio'
}
$UvDir = Join-Path $Data 'uv'
$Uv = Join-Path $UvDir 'uv.exe'

function Stop-Missing([string]$What, [string]$Why) {
    Write-Output "STATUS $What MISSING ($Why)"
    Write-Output 'NOT READY'
    exit 1
}

function Test-Uv {
    if (-not (Test-Path -LiteralPath $Uv -PathType Leaf)) { return $false }
    try {
        & $Uv --version *> $null
        return ($LASTEXITCODE -eq 0)
    } catch { return $false }
}

function Get-Sha256([string]$Path) {
    # .NET, not Get-FileHash: started from PowerShell 7, Windows PowerShell 5.1 can fail to load the module
    # Get-FileHash lives in. .NET is always there.
    try {
        $stream = [IO.File]::OpenRead($Path)
        try {
            $sha = [Security.Cryptography.SHA256]::Create()
            return ([BitConverter]::ToString($sha.ComputeHash($stream))).Replace('-', '').ToLower()
        } finally { $stream.Dispose() }
    } catch { return '' }
}

if (-not (Test-Uv)) {
    Write-Output 'STATUS uv: getting the studio its own copy of uv (about 16 MB, one time)'
    try { New-Item -ItemType Directory -Force -Path $Data | Out-Null } catch { Stop-Missing 'uv' "could not create $Data" }
    $zip = Join-Path $Data 'uv-download.zip'
    $unpack = Join-Path $Data 'uv.unpack'
    foreach ($left in @($zip, $unpack)) {       # leftovers of a run that was cut off
        if (Test-Path -LiteralPath $left) { Remove-Item -LiteralPath $left -Recurse -Force -ErrorAction SilentlyContinue }
    }
    try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch { }
    $ok = $false
    for ($try = 1; $try -le 3 -and -not $ok; $try++) {
        if ($try -gt 1) {
            Write-Output "STATUS uv: the download did not finish, trying again (attempt $try of 3)"
            Start-Sleep -Seconds 3
        }
        try {
            try { (New-Object Net.WebClient).DownloadFile($UvUrl, $zip) }
            catch { Invoke-WebRequest -Uri $UvUrl -OutFile $zip -UseBasicParsing }
            $ok = (Test-Path -LiteralPath $zip -PathType Leaf)
        } catch {
            if (Test-Path -LiteralPath $zip) { Remove-Item -LiteralPath $zip -Force -ErrorAction SilentlyContinue }
        }
    }
    if (-not $ok) { Stop-Missing 'uv' 'no internet, or GitHub could not be reached' }
    if ((Get-Sha256 $zip) -ne $UvSha256) {
        Remove-Item -LiteralPath $zip -Force -ErrorAction SilentlyContinue
        Stop-Missing 'uv' 'the download did not pass its checksum, so it was not used'
    }
    New-Item -ItemType Directory -Force -Path $unpack | Out-Null
    $tar = Get-Command tar -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($tar) { & $tar.Source -xf $zip -C $unpack 2> $null }
    $exe = Get-ChildItem -LiteralPath $unpack -Recurse -Filter 'uv.exe' -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $exe) {
        try { Expand-Archive -LiteralPath $zip -DestinationPath $unpack -Force } catch { }
        $exe = Get-ChildItem -LiteralPath $unpack -Recurse -Filter 'uv.exe' -ErrorAction SilentlyContinue | Select-Object -First 1
    }
    Remove-Item -LiteralPath $zip -Force -ErrorAction SilentlyContinue
    if (-not $exe) {
        Remove-Item -LiteralPath $unpack -Recurse -Force -ErrorAction SilentlyContinue
        Stop-Missing 'uv' 'the download could not be unpacked'
    }
    New-Item -ItemType Directory -Force -Path $UvDir | Out-Null
    Move-Item -LiteralPath $exe.FullName -Destination $Uv -Force
    Remove-Item -LiteralPath $unpack -Recurse -Force -ErrorAction SilentlyContinue
    if (-not (Test-Uv)) { Stop-Missing 'uv' 'the downloaded uv does not run: antivirus or Smart App Control may have blocked it' }
    Write-Output "STATUS uv OK ($UvVersion, the studio's own copy)"
}

# Everything uv downloads or caches stays in the studio data folder
$env:UV_PYTHON_INSTALL_DIR = Join-Path $Data 'python'
$env:UV_CACHE_DIR = Join-Path $Data 'uv-cache'
$env:UV_PYTHON_PREFERENCE = 'only-managed'
$env:UV_NO_CONFIG = '1'
$env:REEL_STUDIO_UV = $Uv
$env:REEL_STUDIO_DATA = $Data
$env:REEL_STUDIO_PYTHON = $PyRequest
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'

& $Uv python find $PyRequest *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Output 'STATUS python: getting the studio its own Python 3.12 (about 30 MB, one time)'
    # --no-bin: no python.exe in %USERPROFILE%\.local\bin; --no-registry: nothing in the Windows registry
    & $Uv python install --no-bin --no-registry $PyRequest *> $null
    if ($LASTEXITCODE -ne 0) {
        & $Uv python install --no-bin --no-registry $PyRequest
        if ($LASTEXITCODE -ne 0) { Stop-Missing 'python' 'uv could not download Python 3.12: check the internet connection and run it again' }
    }
    & $Uv python find $PyRequest *> $null
    if ($LASTEXITCODE -ne 0) { Stop-Missing 'python' "Python 3.12 was downloaded but cannot be started from $Data. Send this output to Marcela" }
    Write-Output "STATUS python OK (3.12, the studio's own copy)"
}

& $Uv run --quiet --no-project --python $PyRequest (Join-Path $Here 'start.py') @args
exit $LASTEXITCODE
