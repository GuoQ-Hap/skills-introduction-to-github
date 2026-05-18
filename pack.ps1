$projectName = 'ric-train-master'
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$parentDir = Split-Path -Parent $scriptDir
$outputFile = Join-Path $parentDir 'ric-train.tar.gz'

Remove-Item $outputFile -Force -ErrorAction SilentlyContinue

$excludes = @(
    '--exclude=venv',
    '--exclude=node_modules',
    '--exclude=dist',
    '--exclude=__pycache__',
    '--exclude=logs',
    '--exclude=.git',
    '--exclude=.cursor',
    '--exclude=*.pyc',
    '--exclude=*.pyo',
    '--exclude=*.tar.gz',
    '--exclude=*copy*',
    "--exclude=$projectName/.env",
    "--exclude=$projectName/auth/tokens.json",
    "--exclude=$projectName/auth/users.json"
)

tar -czf $outputFile @excludes -C $parentDir $projectName

$size = (Get-Item $outputFile).Length
$sizeMB = [math]::Round($size / 1MB, 2)

Write-Host ''
Write-Host ('Done! File: ' + $outputFile) -ForegroundColor Green
Write-Host ('Size: ' + $sizeMB + ' MB') -ForegroundColor Green
