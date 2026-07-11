<#
Sends a message to a Telegram chat via the Bot API.
Invoked by telegram.usp_SendMessage (see ../sql/02_create_procedure.sql) through xp_cmdshell.
The message is passed base64-encoded so arbitrary text (quotes, newlines, etc.) can never
break out of the command line that invokes this script.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$EncodedMessage,
    [Parameter(Mandatory)][string]$BotToken,
    [Parameter(Mandatory)][string]$ChatId,
    [ValidateSet('Markdown', 'MarkdownV2', 'HTML', '')][string]$ParseMode = '',
    [switch]$Silent,
    [string]$LogPath
)

$ErrorActionPreference = 'Stop'

function Write-Log {
    param([string]$Text)
    if ($LogPath) {
        $line = "[{0:yyyy-MM-dd HH:mm:ss}] {1}" -f (Get-Date), $Text
        Add-Content -Path $LogPath -Value $line -Encoding UTF8
    }
}

try {
    $bytes = [Convert]::FromBase64String($EncodedMessage)
    $text = [System.Text.Encoding]::UTF8.GetString($bytes)

    $uri = "https://api.telegram.org/bot$BotToken/sendMessage"
    $body = @{
        chat_id                  = $ChatId
        text                     = $text
        disable_notification     = [bool]$Silent
        disable_web_page_preview = $true
    }
    if ($ParseMode) { $body.parse_mode = $ParseMode }

    $response = Invoke-RestMethod -Uri $uri -Method Post -Body $body -TimeoutSec 15
    if (-not $response.ok) {
        Write-Log "Telegram API returned ok=false: $($response | ConvertTo-Json -Compress)"
        Write-Error "Telegram API returned failure: $($response | ConvertTo-Json -Compress)"
        exit 1
    }

    Write-Log "Message sent to chat $ChatId (message_id=$($response.result.message_id))"
    exit 0
}
catch {
    Write-Log "ERROR: $_"
    Write-Error "Failed to send Telegram message: $_"
    exit 1
}
