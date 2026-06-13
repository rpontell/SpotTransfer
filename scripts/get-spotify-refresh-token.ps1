param(
    [Parameter(Mandatory = $true)]
    [string]$ClientId,

    [Parameter(Mandatory = $true)]
    [string]$ClientSecret,

    [string]$RedirectUri = "http://127.0.0.1:8888/callback",
    [string]$Scope = "playlist-read-private"
)

$ErrorActionPreference = "Stop"

$state = [Guid]::NewGuid().ToString("N")
$listener = [System.Net.HttpListener]::new()
$listener.Prefixes.Add("http://127.0.0.1:8888/")

$authorizeUrl = "https://accounts.spotify.com/authorize" +
    "?response_type=code" +
    "&client_id=$([Uri]::EscapeDataString($ClientId))" +
    "&scope=$([Uri]::EscapeDataString($Scope))" +
    "&redirect_uri=$([Uri]::EscapeDataString($RedirectUri))" +
    "&state=$([Uri]::EscapeDataString($state))"

Write-Host ""
Write-Host "1. In Spotify Developer Dashboard, add this Redirect URI exactly:"
Write-Host "   $RedirectUri"
Write-Host ""
Write-Host "2. Open this URL, approve access, then come back here:"
Write-Host $authorizeUrl
Write-Host ""
Write-Host "Waiting for Spotify callback on http://127.0.0.1:8888 ..."

$listener.Start()
try {
    $context = $listener.GetContext()
    $query = $context.Request.Url.Query.TrimStart("?")
    $params = @{}

    foreach ($part in $query -split "&") {
        if (-not $part) {
            continue
        }
        $keyValue = $part -split "=", 2
        $key = [Uri]::UnescapeDataString($keyValue[0])
        $value = ""
        if ($keyValue.Count -gt 1) {
            $value = [Uri]::UnescapeDataString($keyValue[1])
        }
        $params[$key] = $value
    }

    $responseText = "Spotify authorization received. You can close this tab."
    $responseBytes = [Text.Encoding]::UTF8.GetBytes($responseText)
    $context.Response.ContentType = "text/plain; charset=utf-8"
    $context.Response.OutputStream.Write($responseBytes, 0, $responseBytes.Length)
    $context.Response.Close()

    if ($params["error"]) {
        throw "Spotify authorization failed: $($params["error"])"
    }
    if ($params["state"] -ne $state) {
        throw "Spotify authorization failed: state mismatch."
    }
    if (-not $params["code"]) {
        throw "Spotify authorization failed: no authorization code returned."
    }

    $basicValue = [Convert]::ToBase64String(
        [Text.Encoding]::UTF8.GetBytes("${ClientId}:${ClientSecret}")
    )
    $tokenResponse = Invoke-RestMethod `
        -Method Post `
        -Uri "https://accounts.spotify.com/api/token" `
        -Headers @{
            Authorization = "Basic $basicValue"
        } `
        -ContentType "application/x-www-form-urlencoded" `
        -Body @{
            grant_type = "authorization_code"
            code = $params["code"]
            redirect_uri = $RedirectUri
        }

    if (-not $tokenResponse.refresh_token) {
        throw "Spotify did not return a refresh_token. Revoke app access in your Spotify account and run this script again."
    }

    Write-Host ""
    Write-Host "Refresh token:"
    Write-Host $tokenResponse.refresh_token
    Write-Host ""
    Write-Host "Set it on Fly with:"
    Write-Host "fly secrets set -a spottransfer SPOTIFY_REFRESH_TOKEN=""$($tokenResponse.refresh_token)"""
}
finally {
    if ($listener.IsListening) {
        $listener.Stop()
    }
    $listener.Close()
}
