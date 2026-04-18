param(
    [string]$MainFile = "main.tex"
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

if (-not (Test-Path $MainFile)) {
    throw "Main LaTeX file not found: $MainFile"
}

$baseName = [System.IO.Path]::GetFileNameWithoutExtension($MainFile)

Write-Host "Compiling $MainFile ..."

for ($i = 1; $i -le 2; $i++) {
    Write-Host "pdflatex pass $i/2"
    & pdflatex -interaction=nonstopmode -halt-on-error $MainFile
    if ($LASTEXITCODE -ne 0) {
        throw "pdflatex failed on pass $i."
    }
}

$cleanupPatterns = @(
    "$baseName.aux",
    "$baseName.log",
    "$baseName.out",
    "$baseName.toc",
    "$baseName.fdb_latexmk",
    "$baseName.fls",
    "$baseName.synctex.gz",
    "main_check.aux",
    "main_check.log",
    "main_check.out",
    "main_check.pdf"
)

foreach ($pattern in $cleanupPatterns) {
    $target = Join-Path $scriptDir $pattern
    if (Test-Path $target) {
        try {
            Remove-Item -LiteralPath $target -Force -ErrorAction Stop
            Write-Host "Removed $pattern"
        } catch {
            Write-Warning "Could not remove ${pattern}: $($_.Exception.Message)"
        }
    }
}

Write-Host "Build complete: $(Join-Path $scriptDir "$baseName.pdf")"
