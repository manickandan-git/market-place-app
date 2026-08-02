$ErrorActionPreference = "Stop"

if (-not (Test-Path ".env.integration")) {
    Write-Error "Missing .env.integration. Copy .env.integration.example first."
}

Write-Host "Checking and installing test dependencies..."
uv sync

Write-Host "Running Marketplace integration tests..."
uv run pytest -m integration -v

