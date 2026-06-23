param(
    [int]$MaxProducts = 160,
    [switch]$SkipBehaviorTrain
)

$ErrorActionPreference = "Stop"

function Invoke-DockerCompose {
    param([string[]]$ComposeArgs)

    & docker compose @ComposeArgs
    if ($LASTEXITCODE -ne 0) {
        throw ("docker compose {0} failed with exit code {1}" -f ($ComposeArgs -join " "), $LASTEXITCODE)
    }
}

function Get-ArtifactState {
    param([string]$Path)

    if (-not (Test-Path $Path)) {
        return @{
            Exists = $false
            LastWriteTimeUtc = $null
        }
    }

    $item = Get-Item $Path
    return @{
        Exists = $true
        LastWriteTimeUtc = $item.LastWriteTimeUtc
    }
}

function Describe-ArtifactStateChange {
    param(
        [string]$Path,
        [hashtable]$BeforeState
    )

    if (-not (Test-Path $Path)) {
        throw "Expected artifact was not found on host path: $Path"
    }

    $item = Get-Item $Path
    if (-not $BeforeState.Exists) {
        return "created"
    }

    if ($item.LastWriteTimeUtc -gt $BeforeState.LastWriteTimeUtc) {
        return "updated"
    }

    return "unchanged"
}

$chatbotArtifacts = "services/chatbot_service/chatbot/artifacts"
if (-not (Test-Path $chatbotArtifacts)) {
    New-Item -Path $chatbotArtifacts -ItemType Directory -Force | Out-Null
}

$artifactTargets = @(
    "knowledge_base.json",
    "model_behavior.json",
    "training_data_behavior.json"
)
$artifactStateBefore = @{}
foreach ($artifactName in $artifactTargets) {
    $artifactStateBefore[$artifactName] = Get-ArtifactState -Path (Join-Path $chatbotArtifacts $artifactName)
}

Write-Host "[1/4] Building chatbot KB inside container..."
Invoke-DockerCompose -ComposeArgs @(
    "exec",
    "chatbot_service",
    "python",
    "manage.py",
    "build_chat_kb",
    "--max-products",
    "$MaxProducts"
)

if (-not $SkipBehaviorTrain) {
    Write-Host "[2/4] Training behavior model inside container..."
    Invoke-DockerCompose -ComposeArgs @(
        "exec",
        "chatbot_service",
        "python",
        "manage.py",
        "train_behavior_model"
    )
} else {
    Write-Host "[2/4] Skipping behavior model training (SkipBehaviorTrain=true)."
}

Write-Host "[3/4] Verifying bind-mounted artifacts on host..."
foreach ($artifactName in $artifactTargets) {
    $artifactPath = Join-Path $chatbotArtifacts $artifactName
    $status = Describe-ArtifactStateChange -Path $artifactPath -BeforeState $artifactStateBefore[$artifactName]
    $item = Get-Item $artifactPath
    Write-Host ("- {0} [{1}] last_write_utc={2}" -f $artifactPath, $status, $item.LastWriteTimeUtc.ToString("s"))
}

$runtimeConfigPath = Join-Path $chatbotArtifacts "runtime_config.json"
if (Test-Path $runtimeConfigPath) {
    $runtimeConfigItem = Get-Item $runtimeConfigPath
    Write-Host ("- {0} [present] last_write_utc={1}" -f $runtimeConfigPath, $runtimeConfigItem.LastWriteTimeUtc.ToString("s"))
} else {
    Write-Host ("- {0} [optional_missing]" -f $runtimeConfigPath)
}

Write-Host "[4/4] Artifact workflow completed on bind mount."
