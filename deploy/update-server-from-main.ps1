param(
    [string]$Server = "acom@5.78.110.7",

    [string]$AppDir = "~/recipe-vault",
    [string]$Remote = "origin",
    [string]$Branch = "main"
)

$ErrorActionPreference = "Stop"

$remoteCommand = @"
set -e
cd $AppDir
git fetch $Remote $Branch
GIT_REMOTE=$Remote GIT_REF=$Remote/$Branch bash deploy/start_recipe_vault.sh
"@

Write-Host "Updating Recipe Vault on $Server from GitHub $Branch..."
ssh $Server $remoteCommand
Write-Host "Server update complete."
