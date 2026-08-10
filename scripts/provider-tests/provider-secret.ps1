[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet("init", "set", "list", "remove")]
    [string]$Command,

    [string]$Provider,
    [string]$BaseUrl,
    [string]$Compatibility,
    [string]$ChatModel,
    [string]$ImageModel,
    [switch]$SkipProbe,
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($env:OS -ne "Windows_NT") {
    throw "This script requires Windows because it uses the current user's DPAPI identity."
}

if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
    throw "LOCALAPPDATA is not available."
}

$storeRoot = Join-Path $env:LOCALAPPDATA "HaloWebUI\provider-tests"
$secretRoot = Join-Path $storeRoot "secrets"
$configPath = Join-Path $storeRoot "providers.json"

function Write-JsonFile {
    param(
        [Parameter(Mandatory = $true)]$Value,
        [Parameter(Mandatory = $true)][string]$Path
    )

    $json = $Value | ConvertTo-Json -Depth 10
    $utf8WithoutBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $json + [Environment]::NewLine, $utf8WithoutBom)
}

function Initialize-Store {
    New-Item -ItemType Directory -Path $secretRoot -Force | Out-Null

    if (-not (Test-Path -LiteralPath $configPath)) {
        Write-JsonFile -Path $configPath -Value ([ordered]@{
            version = 1
            providers = [ordered]@{}
        })
    }
}

function Read-Config {
    Initialize-Store
    $raw = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8
    if ([string]::IsNullOrWhiteSpace($raw)) {
        throw "Provider configuration is empty: $configPath"
    }

    $config = $raw | ConvertFrom-Json
    if ($null -eq $config.providers) {
        throw "Provider configuration does not contain a providers object: $configPath"
    }
    return $config
}

function ConvertTo-ProviderMap {
    param([Parameter(Mandatory = $true)]$Config)

    $providers = [ordered]@{}
    foreach ($property in $Config.providers.PSObject.Properties) {
        $providers[$property.Name] = $property.Value
    }
    return $providers
}

function Get-NormalizedProviderName {
    param([Parameter(Mandatory = $true)][string]$Name)

    $normalized = $Name.Trim().ToLowerInvariant()
    if ($normalized -notmatch '^[a-z0-9][a-z0-9_-]*$') {
        throw "Provider must contain only lowercase letters, numbers, underscores, or hyphens."
    }
    return $normalized
}

function Read-Value {
    param(
        [Parameter(Mandatory = $true)][string]$Label,
        [string]$CurrentValue,
        [switch]$Required
    )

    $prompt = $Label
    if (-not [string]::IsNullOrWhiteSpace($CurrentValue)) {
        $prompt += " [$CurrentValue]"
    }

    $value = Read-Host $prompt
    if ([string]::IsNullOrWhiteSpace($value)) {
        $value = $CurrentValue
    }
    if ($Required -and [string]::IsNullOrWhiteSpace($value)) {
        throw "$Label is required."
    }
    return $value.Trim()
}

function Get-ExistingProvider {
    param($Config, [string]$Name)

    $property = $Config.providers.PSObject.Properties | Where-Object { $_.Name -eq $Name } | Select-Object -First 1
    if ($null -eq $property) {
        return $null
    }
    return $property.Value
}

switch ($Command) {
    "init" {
        Initialize-Store
        Write-Host "Local provider store initialized: $storeRoot"
        Write-Host "Secrets are encrypted with Windows DPAPI for the current user and machine."
    }

    "set" {
        Initialize-Store
        if ([string]::IsNullOrWhiteSpace($Provider)) {
            $Provider = Read-Host "Provider name"
        }
        $providerName = Get-NormalizedProviderName -Name $Provider

        $config = Read-Config
        $existing = Get-ExistingProvider -Config $config -Name $providerName
        $existingBaseUrl = if ($null -ne $existing) { [string]$existing.base_url } else { "" }
        $existingChatModel = if ($null -ne $existing) { [string]$existing.chat_model } else { "" }

        if ([string]::IsNullOrWhiteSpace($BaseUrl)) {
            $BaseUrl = Read-Value -Label "Base URL" -CurrentValue $existingBaseUrl -Required
        }
        if ([string]::IsNullOrWhiteSpace($Compatibility)) {
            $defaultCompatibility = if ($null -ne $existing) {
                [string]$existing.compatibility
            }
            elseif ($providerName -in @("sub2api", "grok2api", "cliproxyapi")) {
                $providerName
            }
            else {
                "standard"
            }
            $Compatibility = Read-Value -Label "Compatibility mode" -CurrentValue $defaultCompatibility -Required
        }
        if ([string]::IsNullOrWhiteSpace($ChatModel)) {
            $ChatModel = $existingChatModel
        }
        if ([string]::IsNullOrWhiteSpace($ImageModel)) {
            $ImageModel = if ($null -ne $existing) { [string]$existing.image_model } else { "" }
        }

        $parsedBaseUrl = $null
        if (-not [Uri]::TryCreate($BaseUrl, [UriKind]::Absolute, [ref]$parsedBaseUrl) -or
            $parsedBaseUrl.Scheme -notin @("http", "https")) {
            throw "Base URL must be an absolute HTTP or HTTPS URL."
        }

        $secretPath = Join-Path $secretRoot "$providerName.dpapi"
        $replaceSecret = $true
        if (Test-Path -LiteralPath $secretPath) {
            $answer = Read-Host "Replace the stored API key? [y/N]"
            $replaceSecret = $answer -match '^(?i:y|yes)$'
        }

        if ($replaceSecret) {
            $secret = Read-Host "API Key" -AsSecureString
            try {
                if ($secret.Length -eq 0) {
                    throw "API Key cannot be empty."
                }
                $encrypted = ConvertFrom-SecureString -SecureString $secret
                Set-Content -LiteralPath $secretPath -Value $encrypted -Encoding ASCII
            }
            finally {
                if ($null -ne $secret) {
                    $secret.Dispose()
                }
            }
        }

        if (-not (Test-Path -LiteralPath $secretPath)) {
            throw "No API key is stored for provider '$providerName'."
        }

        $providers = ConvertTo-ProviderMap -Config $config
        $providers[$providerName] = [ordered]@{
            base_url = $parsedBaseUrl.AbsoluteUri.TrimEnd('/')
            compatibility = $Compatibility.Trim()
            chat_model = $ChatModel.Trim()
            image_model = $ImageModel.Trim()
            updated_at = [DateTimeOffset]::UtcNow.ToString("o")
        }
        Write-JsonFile -Path $configPath -Value ([ordered]@{
            version = 1
            providers = $providers
        })

        Write-Host "Provider '$providerName' saved locally."
        Write-Host "Configuration: $configPath"
        Write-Host "Encrypted secret: $secretPath"

        if (-not $SkipProbe) {
            $smokeScript = Join-Path $PSScriptRoot "provider-smoke-test.ps1"
            Write-Host "Discovering models from $($parsedBaseUrl.AbsoluteUri.TrimEnd('/'))/models ..."
            & powershell -NoProfile -File $smokeScript -Provider $providerName -Scenario models
            if ($LASTEXITCODE -ne 0) {
                Write-Warning "The provider was saved, but the /models probe did not succeed."
            }
        }
    }

    "list" {
        $config = Read-Config
        $items = foreach ($property in $config.providers.PSObject.Properties) {
            $name = $property.Name
            $value = $property.Value
            [PSCustomObject]@{
                Provider = $name
                Configured = "yes"
                Secret = if (Test-Path -LiteralPath (Join-Path $secretRoot "$name.dpapi")) { "present" } else { "missing" }
                Compatibility = $value.compatibility
                ChatModel = $value.chat_model
                BaseUrl = $value.base_url
            }
        }

        if ($null -eq $items) {
            Write-Host "No providers are configured."
        }
        else {
            $items | Format-Table -AutoSize
        }
    }

    "remove" {
        if ([string]::IsNullOrWhiteSpace($Provider)) {
            throw "-Provider is required for remove."
        }
        $providerName = Get-NormalizedProviderName -Name $Provider
        $config = Read-Config
        $providers = ConvertTo-ProviderMap -Config $config

        if (-not $providers.Contains($providerName)) {
            throw "Provider '$providerName' is not configured."
        }

        if (-not $Force) {
            $answer = Read-Host "Remove provider '$providerName' and its encrypted key? [y/N]"
            if ($answer -notmatch '^(?i:y|yes)$') {
                Write-Host "No changes made."
                exit 0
            }
        }

        $providers.Remove($providerName)
        $secretPath = Join-Path $secretRoot "$providerName.dpapi"
        if (Test-Path -LiteralPath $secretPath) {
            Remove-Item -LiteralPath $secretPath -Force
        }
        Write-JsonFile -Path $configPath -Value ([ordered]@{
            version = 1
            providers = $providers
        })
        Write-Host "Provider '$providerName' removed from the local store."
    }
}
