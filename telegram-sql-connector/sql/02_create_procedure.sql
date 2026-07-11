/*
    telegram.usp_SendMessage
    ------------------------
    Sends @Message to Telegram using the config row named @ConfigName from telegram.Config.
    Called from any T-SQL script (SSMS, Agent job, etc.) on this machine.

    Example:
        EXEC telegram.usp_SendMessage @Message = N'Backup job finished on ' + @@SERVERNAME;

    The message text is base64-encoded before being placed on the command line, so it is
    safe regardless of quotes, newlines, or other special characters it contains. @ChatId
    and @ParseMode are validated against strict whitelists for the same reason -- neither
    is ever concatenated into the shell command unchecked.
*/

CREATE OR ALTER PROCEDURE telegram.usp_SendMessage
    @Message    NVARCHAR(MAX),
    @ChatId     NVARCHAR(100) = NULL,      -- override the config's DefaultChatId
    @ConfigName NVARCHAR(100) = N'default',
    @ParseMode  NVARCHAR(20)  = NULL,      -- 'Markdown', 'MarkdownV2', or 'HTML'
    @Silent     BIT = 0,                   -- suppress the notification sound/banner
    @Async      BIT = 1                    -- fire-and-forget (don't block the calling script)
AS
BEGIN
    SET NOCOUNT ON;

    IF @ParseMode IS NOT NULL AND @ParseMode NOT IN (N'Markdown', N'MarkdownV2', N'HTML')
    BEGIN
        RAISERROR('Invalid @ParseMode. Must be Markdown, MarkdownV2, HTML, or NULL.', 16, 1);
        RETURN;
    END

    IF @ChatId IS NOT NULL AND (@ChatId LIKE '%[^0-9-]%' OR @ChatId = '')
    BEGIN
        RAISERROR('Invalid @ChatId. Telegram chat ids are numeric (optionally negative for groups/channels).', 16, 1);
        RETURN;
    END

    IF NOT EXISTS (
        SELECT 1 FROM sys.configurations
        WHERE name = 'xp_cmdshell' AND value_in_use = 1
    )
    BEGIN
        RAISERROR('xp_cmdshell is not enabled on this instance. Run 00_enable_xp_cmdshell.sql first.', 16, 1);
        RETURN;
    END

    DECLARE @BotToken NVARCHAR(200), @DefaultChatId NVARCHAR(100), @ScriptPath NVARCHAR(400),
            @LogPath NVARCHAR(400), @IsEnabled BIT;

    SELECT
        @BotToken      = BotToken,
        @DefaultChatId = DefaultChatId,
        @ScriptPath    = ScriptPath,
        @LogPath       = LogPath,
        @IsEnabled     = IsEnabled
    FROM telegram.Config
    WHERE ConfigName = @ConfigName;

    IF @BotToken IS NULL
    BEGIN
        RAISERROR('No telegram.Config row found for ConfigName = %s. Seed one first (see 03_seed_config_example.sql).', 16, 1, @ConfigName);
        RETURN;
    END

    IF @IsEnabled = 0
    BEGIN
        PRINT 'telegram.usp_SendMessage: config "' + @ConfigName + '" is disabled; message not sent.';
        RETURN;
    END

    SET @ChatId = COALESCE(@ChatId, @DefaultChatId);

    -- Base64-encode the message so it can't break out of the command line regardless of content.
    DECLARE @bin VARBINARY(MAX) = CAST(@Message AS VARBINARY(MAX));
    DECLARE @EncodedMessage VARCHAR(MAX) =
        CAST(N'' AS XML).value('xs:base64Binary(sql:variable("@bin"))', 'VARCHAR(MAX)');

    DECLARE @psCommand NVARCHAR(MAX) =
        N'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "' + @ScriptPath + N'"'
        + N' -EncodedMessage "' + @EncodedMessage + N'"'
        + N' -BotToken "' + @BotToken + N'"'
        + N' -ChatId "' + @ChatId + N'"'
        + CASE WHEN @ParseMode IS NOT NULL THEN N' -ParseMode "' + @ParseMode + N'"' ELSE N'' END
        + CASE WHEN @Silent = 1 THEN N' -Silent' ELSE N'' END
        + CASE WHEN @LogPath IS NOT NULL THEN N' -LogPath "' + @LogPath + N'"' ELSE N'' END;

    DECLARE @shellCommand NVARCHAR(MAX) =
        CASE WHEN @Async = 1
             THEN N'cmd /c start "" /B ' + @psCommand
             ELSE @psCommand
        END;

    EXEC master..xp_cmdshell @shellCommand;
END
GO
