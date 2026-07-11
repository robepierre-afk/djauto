/*
    Per-machine configuration. Run this once on EACH machine after copying
    powershell/Send-TelegramMessage.ps1 to a local path, filling in:
      - Your bot token (create a bot via @BotFather, e.g. "123456789:AAExampleTokenAAAA")
      - Your target chat id (message @userinfobot, or your group/channel's numeric id)
      - The local path to Send-TelegramMessage.ps1 on THIS machine

    You can add more rows with different ConfigName values if a single machine needs to
    notify multiple bots/chats (e.g. 'default' for a personal chat, 'ops-channel' for a
    shared team channel) and pass @ConfigName to telegram.usp_SendMessage accordingly.
*/

MERGE telegram.Config AS target
USING (SELECT N'default' AS ConfigName) AS src
    ON target.ConfigName = src.ConfigName
WHEN MATCHED THEN
    UPDATE SET
        BotToken      = N'REPLACE_WITH_YOUR_BOT_TOKEN',
        DefaultChatId = N'REPLACE_WITH_YOUR_CHAT_ID',
        ScriptPath    = N'C:\Ops\TelegramConnector\Send-TelegramMessage.ps1',
        LogPath       = N'C:\Ops\TelegramConnector\telegram-connector.log',
        IsEnabled     = 1,
        UpdatedAt     = SYSUTCDATETIME()
WHEN NOT MATCHED THEN
    INSERT (ConfigName, BotToken, DefaultChatId, ScriptPath, LogPath, IsEnabled)
    VALUES (N'default', N'REPLACE_WITH_YOUR_BOT_TOKEN', N'REPLACE_WITH_YOUR_CHAT_ID',
            N'C:\Ops\TelegramConnector\Send-TelegramMessage.ps1',
            N'C:\Ops\TelegramConnector\telegram-connector.log', 1);
