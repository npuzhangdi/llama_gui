# ASCII only. Called by first_run.bat to enumerate usable Python interpreters.
# Writes one "path|version" line per interpreter to -Out (ASCII, CRLF).
param(
    [string]$Out = "",
    [string]$Root = ""
)

$ErrorActionPreference = "SilentlyContinue"
$candidates = New-Object System.Collections.Generic.List[string]

function Add-Candidate {
    param([string]$CandidatePath)
    if ([string]::IsNullOrWhiteSpace($CandidatePath)) { return }
    $CandidatePath = ([string]$CandidatePath).Trim() -replace '^"+|"+$', ''
    # Store alias and POSIX-layer builds cannot reliably load PySide6 wheels.
    if ($CandidatePath -match '(?i)WindowsApps|\\(msys2|msys64|mingw|cygwin|git\\usr)\\' ) { return }
    if (-not (Test-Path -LiteralPath $CandidatePath -PathType Leaf)) { return }
    $full = (Resolve-Path -LiteralPath $CandidatePath).Path
    if ($Root -and $full.StartsWith($Root, [StringComparison]::OrdinalIgnoreCase)) { return }
    $parent = [System.IO.Path]::GetDirectoryName($full)
    foreach ($known in $candidates) {
        if ([string]::Equals($known, $full, [StringComparison]::OrdinalIgnoreCase)) { return }
        $knownParent = [System.IO.Path]::GetDirectoryName($known)
        if ([string]::Equals($knownParent, $parent, [StringComparison]::OrdinalIgnoreCase)) { return }
    }
    $candidates.Add($full)
}

# 1) Official Windows Python launcher: "py -0p"
$launcher = Get-Command py.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
if ($launcher) {
    $lines = & $launcher.Source -0p 2>&1
    foreach ($line in $lines) {
        $text = [string]$line
        $match = [regex]::Match($text, '([A-Za-z]:\\[^\r\n]*?python\.exe)\s*$', 'IgnoreCase')
        if ($match.Success) { Add-Candidate $match.Groups[1].Value }
    }
}

# 2) Everything reachable through PATH
foreach ($name in @("python.exe", "python3.exe")) {
    $lines = & where.exe $name 2>$null
    foreach ($line in $lines) { Add-Candidate ([string]$line) }
}

# 3) Registry entries written by the official python.org installer
$hives = @(
    "HKLM:\SOFTWARE\Python\PythonCore",
    "HKCU:\SOFTWARE\Python\PythonCore",
    "HKLM:\SOFTWARE\WOW6432Node\Python\PythonCore"
)
foreach ($hive in $hives) {
    foreach ($versionKey in (Get-ChildItem -LiteralPath $hive -ErrorAction SilentlyContinue)) {
        $installKey = Get-Item -LiteralPath (Join-Path $versionKey.PSPath "InstallPath") -ErrorAction SilentlyContinue
        if ($installKey) {
            $dir = $installKey.GetValue("")
            if ($dir) { Add-Candidate (Join-Path $dir "python.exe") }
        }
    }
}

# 4) Common manual install locations
$searchRoots = @(
    (Join-Path $env:LOCALAPPDATA "Programs\Python"),
    (Join-Path $env:USERPROFILE ".pyenv\pyenv-win\versions"),
    "C:\Python3*",
    (Join-Path $env:ProgramFiles "Python3*")
)
foreach ($searchRoot in $searchRoots) {
    Get-ChildItem -Path $searchRoot -Filter "python.exe" -File -Recurse -Depth 3 -ErrorAction SilentlyContinue |
        ForEach-Object { Add-Candidate $_.FullName }
}

# 5) Keep only real 64-bit CPython >= 3.9 with venv support
$entries = @()
foreach ($exe in $candidates) {
    $output = & $exe -c "import sys,venv;print('%d.%d %d'%(sys.version_info[0],sys.version_info[1],1 if sys.maxsize>2**32 else 0))" 2>$null
    if ($LASTEXITCODE -ne 0) { continue }
    $line = [string]($output | Select-Object -First 1)
    if ($line -notmatch '^(\d+)\.(\d+)\s+(\d+)') { continue }
    $major = [int]$Matches[1]
    $minor = [int]$Matches[2]
    $is64 = [int]$Matches[3]
    if ($is64 -ne 1) { continue }
    if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 9)) { continue }
    # PySide6 wheels target CPython 3.9-3.13 on Windows; keep newer builds last.
    $stable = if ($major -eq 3 -and $minor -le 13) { 0 } else { 1 }
    $entries += [pscustomobject]@{
        Path    = $exe
        Version = ("{0}.{1}" -f $major, $minor)
        Stable  = $stable
        Key     = $major * 100 + $minor
    }
}

$rows = @($entries |
    Sort-Object -Property @{Expression = "Stable"; Ascending = $true},
                          @{Expression = "Key"; Descending = $true} |
    ForEach-Object { "{0}|{1}" -f $_.Path, $_.Version })

if ($Out) {
    if (Test-Path -LiteralPath $Out) { Remove-Item -LiteralPath $Out -Force }
    Set-Content -LiteralPath $Out -Value $rows -Encoding ASCII
} else {
    foreach ($row in $rows) { Write-Output $row }
}
