# Start FX Trading Lab locally on Windows without Docker.
#
# Assumes the one-time setup is already done (see README "Local development
# on Windows (no Docker)"): the fxlab role + database exist in the local
# PostgreSQL service, backend/.venv is populated, frontend/node_modules is
# installed, and backend/.env + frontend/.env.local exist.
#
# Opens four windows: Redis, the API, the market-data worker, and Next.js.

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$redisDir = Join-Path (Split-Path $root -Parent) 'tools\redis\Redis-8.8.0-Windows-x64-msys2'

function Start-Piece($title, $workDir, $exe, $argList) {
    Start-Process -FilePath 'powershell.exe' -WorkingDirectory $workDir -ArgumentList @(
        '-NoExit', '-Command', "`$host.UI.RawUI.WindowTitle='$title'; & '$exe' $argList"
    )
}

# 1. Redis — skip if something already answers on 6379.
$redisUp = try { (New-Object Net.Sockets.TcpClient).Connect('127.0.0.1', 6379); $true } catch { $false }
if ($redisUp) {
    Write-Host 'Redis already listening on 6379 — leaving it alone.'
} else {
    Start-Piece 'redis' $redisDir (Join-Path $redisDir 'redis-server.exe') '--port 6379 --save "" --appendonly no'
    Start-Sleep -Seconds 2
}

$backend = Join-Path $root 'backend'
$py = Join-Path $backend '.venv\Scripts\python.exe'

# 2. API on :8000
Start-Piece 'api' $backend $py '-m uvicorn app.main:app --reload --port 8000'

# 3. Market-data worker (price polling, candle building, retention)
Start-Piece 'worker' $backend $py '-m app.worker.main'

# 4. Frontend on :3001 (3000 is reserved for another app on this machine)
Start-Piece 'frontend' (Join-Path $root 'frontend') 'npm.cmd' 'run dev -- -p 3001'

Write-Host ''
Write-Host 'Frontend : http://localhost:3001'
Write-Host 'API docs : http://localhost:8000/docs'
