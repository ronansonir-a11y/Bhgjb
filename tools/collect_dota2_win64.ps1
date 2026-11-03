<#
.SYNOPSIS
  Packs ONLY the Windows x86-64 PE binaries of the CURRENT Dota 2 install into
  dota2-win64-bins.zip for the PE-analysis pipeline in this repository.

.DESCRIPTION
  Run on the Windows machine that has the up-to-date Steam installation.
  The ZIP keeps the relative paths game/bin/win64/** and
  game/dota/bin/win64/** exactly as Steam lays them out — tools/validate_archive.py
  and tools/analyze_pe.py depend on that layout.

  IMPORTANT: the ZIP contains Valve's proprietary binaries. Do NOT commit it to a
  public repository. Upload it as a PRIVATE GitHub Release asset, or keep it local
  and run the analysis locally. See docs/04-FILE-MANIFEST.md.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File tools\collect_dota2_win64.ps1 `
      -GameDir "C:\Program Files (x86)\Steam\steamapps\common\dota 2 beta" `
      -IncludeOptional
#>
[CmdletBinding()]
param(
  [string]$GameDir = "C:\Program Files (x86)\Steam\steamapps\common\dota 2 beta",
  [string]$OutZip = "dota2-win64-bins.zip",
  [switch]$IncludeOptional,
  [switch]$Force
)

$ErrorActionPreference = "Stop"
$GameDir = [System.IO.Path]::GetFullPath($GameDir).TrimEnd('\','/')

$critical = @(
  "game\bin\win64\dota2.exe",
  "game\bin\win64\engine2.dll",
  "game\bin\win64\rendersystemvulkan.dll",
  "game\bin\win64\filesystem_stdio.dll",
  "game\bin\win64\tier0.dll",
  "game\bin\win64\steam_api64.dll",
  "game\bin\win64\SDL3.dll",
  "game\dota\bin\win64\client.dll",
  "game\dota\bin\win64\server.dll",
  "game\dota\bin\win64\host.dll"
)

if (-not (Test-Path -LiteralPath $GameDir -PathType Container)) {
  throw "Game folder not found: $GameDir"
}
$binDirs = @(
  (Join-Path $GameDir "game\bin\win64"),
  (Join-Path $GameDir "game\dota\bin\win64")
)
foreach ($d in $binDirs) {
  if (-not (Test-Path -LiteralPath $d -PathType Container)) { throw "Missing folder: $d" }
}

foreach ($c in $critical) {
  $p = Join-Path $GameDir $c
  if (-not (Test-Path -LiteralPath $p -PathType Leaf)) { throw "Missing critical file: $p" }
}

$files = @()
foreach ($d in $binDirs) {
  $files += Get-ChildItem -LiteralPath $d -Recurse -File |
            Where-Object { $_.Extension -in @(".dll", ".exe") }
}
if ($IncludeOptional) {
  $optional = @(
    "game\dota\steam.inf",
    "game\dota\gameinfo.gi",
    "game\bin\win64\steam_appid.txt",
    "game\dota\pak01_dir.vpk"
  )
  foreach ($o in $optional) {
    $p = Join-Path $GameDir $o
    if (Test-Path -LiteralPath $p -PathType Leaf) { $files += Get-Item -LiteralPath $p }
  }
}

$total = ($files | Measure-Object -Property Length -Sum).Sum
Write-Host ("[collect] {0} files, {1:N1} MiB" -f $files.Count, ($total / 1MB))
Write-Host "[collect] reference depot 373303 @ 2026-11-03 = 624.73 MiB / 96 PE files"
Write-Host "[collect] if the number differs, Valve shipped a newer build - that is fine,"
Write-Host "[collect] but refresh data/depot-373303-2026-11-03.tsv from SteamDB."

$outFull = [System.IO.Path]::GetFullPath($OutZip)
if ((Test-Path -LiteralPath $outFull) -and -not $Force) {
  throw "Output already exists: $outFull (use -Force to overwrite)"
}
if (Test-Path -LiteralPath $outFull) { Remove-Item -LiteralPath $outFull -Force }

Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [System.IO.Compression.ZipFile]::Open(
    $outFull, [System.IO.Compression.ZipArchiveMode]::Create)
try {
  foreach ($f in $files) {
    $rel = $f.FullName.Substring($GameDir.Length).TrimStart('\','/').Replace('\','/')
    $entry = [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
        $zip, $f.FullName, $rel, [System.IO.Compression.CompressionLevel]::Optimal)
    Write-Host ("  + {0}" -f $rel)
  }
} finally {
  $zip.Dispose()
}

$hash = (Get-FileHash -LiteralPath $outFull -Algorithm SHA256).Hash.ToLowerInvariant()
"$hash  $([System.IO.Path]::GetFileName($outFull))" |
    Set-Content -LiteralPath "$outFull.sha256" -Encoding ascii
Write-Host ("[collect] wrote {0}" -f $outFull)
Write-Host ("[collect] sha256 = {0}" -f $hash)
Write-Host ""
Write-Host "NEXT (choose ONE, do not 'git add' the ZIP into a public repo):"
Write-Host "  A) private release: gh release create dota2-bins --private ... "
Write-Host "     then set repository variable DOTA2_BINS_URL and run the 'pe-analysis' workflow."
Write-Host "  B) local: python tools/validate_archive.py --zip '$outFull' --strict"
Write-Host "            python tools/analyze_pe.py --input '$outFull' --out report --deep"
Write-Host ""
Write-Host "REMINDER: for actually RUNNING the game on the phone you additionally need"
Write-Host "the full content (game/dota/pak01_*.vpk, game/core/...) copied to /sdcard/Dota2/."
Write-Host "That is 25-40 GB and must NOT be put in Git or in this ZIP."
