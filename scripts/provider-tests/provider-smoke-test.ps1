[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Provider,

    [Parameter(Mandatory = $true)]
    [ValidateSet("models", "chat", "chat-stream", "responses", "responses-stream")]
    [string]$Scenario,

    [string]$Model,

    [ValidateRange(5, 300)]
    [int]$TimeoutSeconds = 60
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($env:OS -ne "Windows_NT") {
    throw "This script requires Windows because it uses the current user's DPAPI identity."
}

if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
    throw "LOCALAPPDATA is not available."
}

$providerName = $Provider.Trim().ToLowerInvariant()
if ($providerName -notmatch '^[a-z0-9][a-z0-9_-]*$') {
    throw "Provider contains unsupported characters."
}

$storeRoot = Join-Path $env:LOCALAPPDATA "HaloWebUI\provider-tests"
$configPath = Join-Path $storeRoot "providers.json"
$secretPath = Join-Path (Join-Path $storeRoot "secrets") "$providerName.dpapi"

if (-not (Test-Path -LiteralPath $configPath)) {
    throw "Provider store is not initialized. Run provider-secret.ps1 init first."
}
if (-not (Test-Path -LiteralPath $secretPath)) {
    throw "Encrypted key is missing for provider '$providerName'."
}

$config = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
$providerProperty = $config.providers.PSObject.Properties |
    Where-Object { $_.Name -eq $providerName } |
    Select-Object -First 1
if ($null -eq $providerProperty) {
    throw "Provider '$providerName' is not configured."
}

$providerConfig = $providerProperty.Value
$baseUrl = ([string]$providerConfig.base_url).TrimEnd('/')
$configuredChatModel = [string]$providerConfig.chat_model
$chatModel = if (-not [string]::IsNullOrWhiteSpace($Model)) { $Model.Trim() } else { $configuredChatModel }

if ([string]::IsNullOrWhiteSpace($baseUrl)) {
    throw "Provider '$providerName' has no Base URL."
}
if ($Scenario -ne "models" -and [string]::IsNullOrWhiteSpace($chatModel)) {
    throw "Specify -Model for this scenario. Provider setup only discovers models and does not select one automatically."
}

$encrypted = (Get-Content -LiteralPath $secretPath -Raw -Encoding ASCII).Trim()
$secureSecret = ConvertTo-SecureString $encrypted
$credential = New-Object System.Net.NetworkCredential("", $secureSecret)
$plainSecret = $credential.Password

$uri = $null
$method = "GET"
$body = $null
$expectsStream = $false

switch ($Scenario) {
    "models" {
        $uri = "$baseUrl/models"
    }
    "chat" {
        $uri = "$baseUrl/chat/completions"
        $method = "POST"
        $body = [ordered]@{
            model = $chatModel
            messages = @(
                [ordered]@{ role = "user"; content = "Reply with exactly: OK" }
            )
            stream = $false
        }
    }
    "chat-stream" {
        $uri = "$baseUrl/chat/completions"
        $method = "POST"
        $expectsStream = $true
        $body = [ordered]@{
            model = $chatModel
            messages = @(
                [ordered]@{ role = "user"; content = "Reply with exactly: OK" }
            )
            stream = $true
        }
    }
    "responses" {
        $uri = "$baseUrl/responses"
        $method = "POST"
        $body = [ordered]@{
            model = $chatModel
            input = "Reply with exactly: OK"
            stream = $false
        }
    }
    "responses-stream" {
        $uri = "$baseUrl/responses"
        $method = "POST"
        $expectsStream = $true
        $body = [ordered]@{
            model = $chatModel
            input = "Reply with exactly: OK"
            stream = $true
        }
    }
}

$headers = @{ Authorization = "Bearer $plainSecret" }
$stopwatch = [Diagnostics.Stopwatch]::StartNew()
$result = [ordered]@{
    provider = $providerName
    scenario = $Scenario
    status = "failed"
    http_status = $null
    content_type = $null
    duration_ms = $null
}
$exitCode = 1

try {
    $requestParameters = @{
        Uri = $uri
        Method = $method
        Headers = $headers
        TimeoutSec = $TimeoutSeconds
        UseBasicParsing = $true
    }
    if ($null -ne $body) {
        $requestParameters.ContentType = "application/json"
        $requestParameters.Body = $body | ConvertTo-Json -Depth 8 -Compress
    }

    $response = Invoke-WebRequest @requestParameters
    $content = [string]$response.Content
    $contentType = [string]$response.Headers["Content-Type"]

    $result.http_status = [int]$response.StatusCode
    $result.content_type = $contentType

    if ($Scenario -eq "models") {
        $parsed = $content | ConvertFrom-Json
        $dataProperty = $parsed.PSObject.Properties | Where-Object { $_.Name -eq "data" } | Select-Object -First 1
        $models = if ($null -ne $dataProperty) { @($dataProperty.Value) } else { @() }
        $modelIds = @(
            foreach ($modelItem in $models) {
                $idProperty = $modelItem.PSObject.Properties | Where-Object { $_.Name -eq "id" } | Select-Object -First 1
                if ($null -ne $idProperty -and -not [string]::IsNullOrWhiteSpace([string]$idProperty.Value)) {
                    [string]$idProperty.Value
                }
            }
        )
        $modelCount = $models.Count
        $result.model_count = $modelCount
        $result.models = $modelIds
        if ($modelCount -lt 1) {
            throw "The models response did not contain any models."
        }
    }
    elseif ($expectsStream) {
        $completed = if ($Scenario -eq "chat-stream") {
            $content -match 'data:\s*\[DONE\]'
        }
        else {
            $content -match 'response\.completed'
        }
        $result.completed_event = $completed
        if (-not $completed) {
            throw "The stream ended without its expected completion event."
        }
    }
    else {
        $parsed = $content | ConvertFrom-Json
        $hasOutput = if ($Scenario -eq "chat") {
            $choicesProperty = $parsed.PSObject.Properties | Where-Object { $_.Name -eq "choices" } | Select-Object -First 1
            $null -ne $choicesProperty -and @($choicesProperty.Value).Count -gt 0
        }
        else {
            $outputTextProperty = $parsed.PSObject.Properties | Where-Object { $_.Name -eq "output_text" } | Select-Object -First 1
            $outputProperty = $parsed.PSObject.Properties | Where-Object { $_.Name -eq "output" } | Select-Object -First 1
            ($null -ne $outputTextProperty -and -not [string]::IsNullOrWhiteSpace([string]$outputTextProperty.Value)) -or
                ($null -ne $outputProperty -and @($outputProperty.Value).Count -gt 0)
        }
        if (-not $hasOutput) {
            throw "The response did not contain an expected output field."
        }
    }

    $result.status = "passed"
    $exitCode = 0
}
catch {
    if ($null -ne $_.Exception.Response) {
        try {
            $result.http_status = [int]$_.Exception.Response.StatusCode
            $result.content_type = [string]$_.Exception.Response.ContentType
        }
        catch {
            # Keep the result redacted when the HTTP client exposes no safe metadata.
        }
    }
    $result.error = "Provider request failed or returned an incompatible response."
}
finally {
    $stopwatch.Stop()
    $result.duration_ms = $stopwatch.ElapsedMilliseconds
    $headers.Clear()
    $plainSecret = $null
    $credential = $null
    if ($null -ne $secureSecret) {
        $secureSecret.Dispose()
    }
}

$result | ConvertTo-Json -Depth 5
exit $exitCode
