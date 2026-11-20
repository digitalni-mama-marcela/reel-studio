# Reel Studio (Digitalni Mama Marcela): sound hook for Windows, for hooks/hooks.json. ASCII only (PowerShell 5.1).
#
# hooks.json runs one line in sh or in PowerShell (Windows without Git Bash): first cink.sh, then this file, then
# exit 0. On a Mac powershell.exe does not exist and this file is never reached. On Windows cink.sh does nothing and
# this file runs studio/cink.py with the studio's OWN Python (never a bare python). Before the studio is installed
# there is no Python yet: then it does nothing. It always ends with exit 0, so a hook never shows an error.
param([string]$Druh = '')
try {
    # cink.py writes UTF-8; without this PowerShell 5.1 would re-encode it in the console code page
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    $Here = Split-Path -Parent $MyInvocation.MyCommand.Path
    $Data = $env:REEL_STUDIO_DATA
    if (-not $Data) {
        $Home0 = $env:USERPROFILE
        if (-not $Home0) { $Home0 = $HOME }
        $Data = Join-Path $Home0 '.claude-reel-studio'    # the same folder as spust.ps1
    }
    $Py = Join-Path $Data 'venv\Scripts\python.exe'
    if (Test-Path -LiteralPath $Py) {
        $env:REEL_STUDIO_DATA = $Data
        $env:PYTHONIOENCODING = 'utf-8'
        $Skript = Join-Path $Here 'studio\cink.py'
        if ($Druh -eq 'zacatek') {
            # only "zacatek" may print: a notice about a new studio version, Claude gets it as a note
            & $Py $Skript $Druh 2>$null
        } else {
            & $Py $Skript $Druh *> $null
        }
    }
} catch { }
exit 0
