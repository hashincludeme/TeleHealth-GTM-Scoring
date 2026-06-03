# Telehealth GTM Conversion Scorer — Windows Pipeline Runner
# Run from project root: .\run_pipeline.ps1

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Host "`n=== Step 1: Generate synthetic data ===" -ForegroundColor Cyan
python generate_data.py

Write-Host "`n=== Step 2: Load seeds into DuckDB ===" -ForegroundColor Cyan
dbt seed --profiles-dir .

Write-Host "`n=== Step 3: Run dbt models ===" -ForegroundColor Cyan
dbt run --profiles-dir .

Write-Host "`n=== Step 4: Run dbt tests ===" -ForegroundColor Cyan
dbt test --profiles-dir .

Write-Host "`n=== Step 5: Train ML model ===" -ForegroundColor Cyan
python train_model.py

Write-Host "`n=== Step 6: Score and produce call list ===" -ForegroundColor Cyan
python score_and_rank.py

Write-Host "`n=== Pipeline complete ===" -ForegroundColor Green
Write-Host "Call list saved in outputs/"
