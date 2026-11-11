# Requires: gh auth login (repo admin)
# Configures labels, classic branch protection for main, and squash merge defaults.

$ErrorActionPreference = "Stop"
$Repo = "YukiMiyatake/PentaKlip"

function Ensure-Label([string]$Name, [string]$Color, [string]$Description) {
    gh label create $Name --repo $Repo --color $Color --description $Description 2>$null
    if ($LASTEXITCODE -ne 0) {
        gh label edit $Name --repo $Repo --color $Color --description $Description
    }
}

Write-Host "Creating labels..."
Ensure-Label "feature" "1D76DB" "New capability"
Ensure-Label "fix" "D73A4A" "Bug fix"
Ensure-Label "chore" "FEF2C0" "Maintenance"
Ensure-Label "docs" "0075CA" "Documentation"
Ensure-Label "ci" "BFDADC" "CI / workflow / tooling"
Ensure-Label "dependencies" "0366D6" "Dependency updates"
Ensure-Label "auto-merge" "0E8A16" "Squash auto-merge when CI is green"

Write-Host "Configuring repository merge settings..."
gh repo edit $Repo `
    --enable-squash-merge `
    --enable-auto-merge `
    --delete-branch-on-merge `
    --allow-update-branch

Write-Host "Applying branch protection on main..."
# Classic protection via API (works on private repos with admin).
$protection = @{
    required_status_checks = @{
        strict = $true
        contexts = @("CI summary")
    }
    enforce_admins = $false
    required_pull_request_reviews = @{
        required_approving_review_count = 0
        dismiss_stale_reviews = $true
    }
    restrictions = $null
    allow_force_pushes = $false
    allow_deletions = $false
    required_linear_history = $true
    required_conversation_resolution = $true
} | ConvertTo-Json -Depth 6

$protection | gh api -X PUT "repos/$Repo/branches/main/protection" --input - 

Write-Host "Done. Verify: https://github.com/$Repo/settings/branches"
