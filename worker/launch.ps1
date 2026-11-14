param(
    [ValidateSet('serve', 'once', 'acceptance')][string]$Mode = 'serve',
    [switch]$Foreground
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$uvPath = Join-Path $env:USERPROFILE '.local/bin/uv.exe'
$env:PATH = (Join-Path $repo 'common/data/tools/ffmpeg/ffmpeg-9.0.2-essentials_build/bin') + ';' + $env:PATH
$env:UV_CACHE_DIR = Join-Path $repo 'ingest/data/uv-cache'
$env:HF_HUB_CACHE = Join-Path $repo 'common/data/huggingface'
$env:TORCH_HOME = Join-Path $repo 'common/data/torch'
$env:HF_HUB_OFFLINE = '1'
$env:OMP_NUM_THREADS = '2'
$env:MKL_NUM_THREADS = '2'
$env:CLAP_MODEL = 'laion/larger_clap_general'
$env:CLAP_REVISION = 'ada0c23a36c4e8582805bb38fec3905903f18b41'
$env:WORKER_DATA_DIR = Join-Path $repo 'worker/data'
$env:WORKER_ONCE = if ($Mode -eq 'once') { '1' } else { '0' }
$module = if ($Mode -eq 'acceptance') { 'worker.acceptance' } else { 'worker.main' }
$arguments = @('run', '--no-sync', '--project', 'worker', '--env-file', '.env', 'python', '-m', $module)
if ($Foreground) {
    Push-Location $repo
    try { & $uvPath @arguments; $workerExitCode = $LASTEXITCODE } finally { Pop-Location }
    exit $workerExitCode
}
$directory = Join-Path $repo 'worker/data'
New-Item -ItemType Directory -Path $directory -Force | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$stdout = Join-Path $directory "$Mode-$stamp.stdout.log"
$stderr = Join-Path $directory "$Mode-$stamp.stderr.log"
$process = Start-Process -FilePath $uvPath -ArgumentList $arguments -WorkingDirectory $repo -WindowStyle Hidden `
    -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
[pscustomobject]@{ LauncherPID = $process.Id; Mode = $Mode; Stdout = $stdout; Stderr = $stderr }
