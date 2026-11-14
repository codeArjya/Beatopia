param(
    [ValidateSet('report', 'calibrate')][string]$Mode = 'report',
    [string]$Output,
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
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
if (-not $Output) { $Output = "ingest/data/session5/$Mode-$stamp.json" }
$arguments = @('run', '--no-sync', '--project', 'ingest', '--env-file', '.env',
    'python', "ingest/$Mode.py", '--output', $Output)
if ($Foreground) {
    Push-Location $repo
    try {
        # PowerShell 5 turns redirected native stderr/progress into ErrorRecords.
        # Preserve the program's exit code instead of treating a uv warning as failure.
        $ErrorActionPreference = 'Continue'
        & $uvPath @arguments
        $auditExitCode = $LASTEXITCODE
    } finally { Pop-Location }
    exit $auditExitCode
}
$stdout = Join-Path $repo "ingest/data/$Mode-$stamp.stdout.log"
$stderr = Join-Path $repo "ingest/data/$Mode-$stamp.stderr.log"
$process = Start-Process -FilePath $uvPath -ArgumentList $arguments -WorkingDirectory $repo -WindowStyle Hidden `
    -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
[pscustomobject]@{ LauncherPID = $process.Id; Mode = $Mode; Output = $Output; Stdout = $stdout; Stderr = $stderr }
