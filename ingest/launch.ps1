param(
    [ValidateRange(1, 400)][int]$Limit = 350,
    [ValidateSet('auto', 'freesound', 'jamendo')][string]$Source = 'auto',
    [switch]$Foreground
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$uvPath = Join-Path $env:USERPROFILE '.local/bin/uv.exe'
$ffmpegBin = Join-Path $repo 'common/data/tools/ffmpeg/ffmpeg-9.0.2-essentials_build/bin'
$env:PATH = $ffmpegBin + ';' + $env:PATH
$env:UV_CACHE_DIR = Join-Path $repo 'ingest/data/uv-cache'
$env:HF_HUB_CACHE = Join-Path $repo 'common/data/huggingface'
$env:HF_HUB_OFFLINE = '1'
$env:OMP_NUM_THREADS = '4'
$env:MKL_NUM_THREADS = '4'
# Approved session-2 per-process override. API deployment must use the same revision.
$env:CLAP_MODEL = 'laion/larger_clap_general'
$env:CLAP_REVISION = 'ada0c23a36c4e8582805bb38fec3905903f18b41'
if ($Foreground) {
    Push-Location $repo
    try {
        & $uvPath run --project ingest --env-file .env python -m ingest.run --source $Source --limit $Limit
    } finally {
        Pop-Location
    }
    return
}
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$stdout = Join-Path $repo "ingest/data/launch-$stamp.stdout.log"
$stderr = Join-Path $repo "ingest/data/launch-$stamp.stderr.log"
$process = Start-Process -FilePath $uvPath -ArgumentList @(
    'run', '--project', 'ingest', '--env-file', '.env', 'python', '-m', 'ingest.run',
    '--source', $Source, '--limit', $Limit
) -WorkingDirectory $repo -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
[pscustomobject]@{ LauncherPID = $process.Id; Source = $Source; Limit = $Limit; Stdout = $stdout; Stderr = $stderr }
