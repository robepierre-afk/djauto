/*
    Creates the telegram schema and its per-machine configuration table.
    Run this in whichever database you want the connector installed in (a shared
    "Ops"/"DBAUtils" database is a good choice if you want one install shared by
    every script on the box, rather than duplicating it per user database).
*/

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'telegram')
    EXEC('CREATE SCHEMA telegram');
GO

IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE object_id = OBJECT_ID('telegram.Config'))
BEGIN
    CREATE TABLE telegram.Config
    (
        ConfigId      INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        ConfigName    NVARCHAR(100)     NOT NULL,
        BotToken      NVARCHAR(200)     NOT NULL,
        DefaultChatId NVARCHAR(100)     NOT NULL,
        ScriptPath    NVARCHAR(400)     NOT NULL,   -- local path to Send-TelegramMessage.ps1 on THIS machine
        LogPath       NVARCHAR(400)     NULL,       -- optional local log file for troubleshooting
        IsEnabled     BIT               NOT NULL CONSTRAINT DF_telegram_Config_IsEnabled DEFAULT (1),
        UpdatedAt     DATETIME2         NOT NULL CONSTRAINT DF_telegram_Config_UpdatedAt DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT UQ_telegram_Config_ConfigName UNIQUE (ConfigName),
        CONSTRAINT CK_telegram_Config_DefaultChatId CHECK (DefaultChatId NOT LIKE '%[^0-9-]%')
    );
END
GO

/*
    Lock this table down: it holds the bot token in plain text. Only DBAs / the account
    that manages the connector should have SELECT/INSERT/UPDATE on telegram.Config.
    Application logins should only ever be granted EXECUTE on telegram.usp_SendMessage,
    never direct access to this table.
*/
