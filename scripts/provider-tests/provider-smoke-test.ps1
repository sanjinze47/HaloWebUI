[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Provider,

    [Parameter(Mandatory = $true)]
    [ValidateSet("models", "chat", "chat-stream", "responses", "responses-stream", "image-edit", "image-edit-stream")]
    [string]$Scenario,

    [string]$Model,

    [string]$ReferenceImageUrl,

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
$configuredImageModel = [string]$providerConfig.image_model
$selectedModel = if (-not [string]::IsNullOrWhiteSpace($Model)) {
    $Model.Trim()
}
elseif ($Scenario -in @("image-edit", "image-edit-stream")) {
    $configuredImageModel
}
else {
    $configuredChatModel
}

if ([string]::IsNullOrWhiteSpace($baseUrl)) {
    throw "Provider '$providerName' has no Base URL."
}
if ($Scenario -ne "models" -and [string]::IsNullOrWhiteSpace($selectedModel)) {
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
$imageDataUrl = $null

if ($Scenario -in @("image-edit", "image-edit-stream")) {
    if (-not [string]::IsNullOrWhiteSpace($ReferenceImageUrl)) {
        $referenceUri = $null
        if (-not [Uri]::TryCreate($ReferenceImageUrl.Trim(), [UriKind]::Absolute, [ref]$referenceUri) -or $referenceUri.Scheme -ne "https") {
            throw "ReferenceImageUrl must be an absolute HTTPS URL to a non-sensitive test image."
        }
        $imageDataUrl = $referenceUri.AbsoluteUri
    }
    else {
        Add-Type -AssemblyName System.Drawing
        $bitmap = New-Object System.Drawing.Bitmap 256, 256
        $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
        $stream = New-Object System.IO.MemoryStream
        try {
            $graphics.Clear([System.Drawing.Color]::White)
            $graphics.FillEllipse([System.Drawing.Brushes]::Blue, 48, 48, 160, 160)
            $bitmap.Save($stream, [System.Drawing.Imaging.ImageFormat]::Png)
            $imageDataUrl = "data:image/png;base64,$([Convert]::ToBase64String($stream.ToArray()))"
        }
        finally {
            $graphics.Dispose()
            $bitmap.Dispose()
            $stream.Dispose()
        }
    }
}

switch ($Scenario) {
    "models" {
        $uri = "$baseUrl/models"
    }
    "chat" {
        $uri = "$baseUrl/chat/completions"
        $method = "POST"
        $body = [ordered]@{
            model = $selectedModel
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
            model = $selectedModel
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
            model = $selectedModel
            input = "Reply with exactly: OK"
            stream = $false
        }
    }
    "responses-stream" {
        $uri = "$baseUrl/responses"
        $method = "POST"
        $expectsStream = $true
        $body = [ordered]@{
            model = $selectedModel
            input = "Reply with exactly: OK"
            stream = $true
        }
    }
    "image-edit" {
        $uri = "$baseUrl/images/edits"
        $method = "POST"
        $body = [ordered]@{
            model = $selectedModel
            prompt = "Keep the subject and use a blue background."
            image = [ordered]@{
                url = $imageDataUrl
            }
            n = 1
            response_format = "url"
        }
    }
    "image-edit-stream" {
        $uri = "$baseUrl/images/edits"
        $method = "POST"
        $expectsStream = $true
        $body = [ordered]@{
            model = $selectedModel
            prompt = "Keep the subject and use a blue background."
            image = [ordered]@{
                url = $imageDataUrl
            }
            n = 1
            response_format = "b64_json"
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
        elseif ($Scenario -eq "image-edit-stream") {
            $content -match 'image_edit\.completed'
        }
        else {
            $content -match 'response\.completed'
        }
        $result.completed_event = $completed
        if (-not $completed) {
            throw "The stream ended without its expected completion event."
        }
    }
    elseif ($Scenario -eq "image-edit") {
        $parsed = $content | ConvertFrom-Json
        $result.response_fields = @($parsed.PSObject.Properties.Name)
        $dataProperty = $parsed.PSObject.Properties | Where-Object { $_.Name -eq "data" } | Select-Object -First 1
        $images = if ($null -ne $dataProperty) { @($dataProperty.Value) } else { @() }
        $result.image_count = $images.Count
        $result.image_fields = @(
            foreach ($imageItem in $images) {
                @($imageItem.PSObject.Properties.Name)
            }
        )
        $hasImage = $images | Where-Object {
            $urlProperty = $_.PSObject.Properties | Where-Object { $_.Name -eq "url" } | Select-Object -First 1
            $base64Property = $_.PSObject.Properties | Where-Object { $_.Name -eq "b64_json" } | Select-Object -First 1
            ($null -ne $urlProperty -and -not [string]::IsNullOrWhiteSpace([string]$urlProperty.Value)) -or
                ($null -ne $base64Property -and -not [string]::IsNullOrWhiteSpace([string]$base64Property.Value))
        }
        if (@($hasImage).Count -lt 1) {
            throw "The image edit response did not contain an image."
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
    $responseProperty = $_.Exception.PSObject.Properties["Response"]
    if ($null -ne $responseProperty -and $null -ne $responseProperty.Value) {
        try {
            $result.http_status = [int]$responseProperty.Value.StatusCode
            $result.content_type = [string]$responseProperty.Value.ContentType
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
