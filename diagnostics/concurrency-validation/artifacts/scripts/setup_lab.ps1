param(
    [string]$Repo = "D:\working\ascend-sleuth",
    [string]$LabRoot = $(if ($env:ASV_ROOT) { $env:ASV_ROOT } else { "D:\working\asv" })
)
$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $LabRoot | Out-Null
$origin = Join-Path $LabRoot "origin.git"
if (-not (Test-Path $origin)) {
    git clone -q --bare --branch main --single-branch $Repo $origin
    Write-Host "created $origin"
} else {
    Write-Host "reusing $origin"
}
# The harnesses reset the lab main to this baseline; make sure the object exists.
$base = "28adab0d1db1f00989b5416dfeaf8206df71ca4a"
git -C $origin cat-file -e "$base^{commit}" 2>$null
if ($LASTEXITCODE -ne 0) {
    Push-Location $Repo
    try { git push $origin "${base}:refs/heads/main" } finally { Pop-Location }
}
New-Item -ItemType Directory -Force -Path (Join-Path $LabRoot "logs") | Out-Null
Write-Host "lab root: $LabRoot"
Write-Host "baseline: $base"
