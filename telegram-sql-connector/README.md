# Telegram SQL Connector

Lets any T-SQL script running in SSMS send a status message ("query finished",
"job failed", etc.) to a Telegram chat, bot, or channel. Install once per
machine, configure a row per machine/bot, then call one stored procedure from
any script.

## How it works

SQL Server has no built-in HTTP client, so the stored procedure shells out
(via `xp_cmdshell`) to a small PowerShell script that calls the Telegram Bot
API (`https://api.telegram.org/bot<token>/sendMessage`).

```
T-SQL script  -->  telegram.usp_SendMessage  -->  xp_cmdshell  -->  Send-TelegramMessage.ps1  -->  Telegram
```

Per-machine settings (bot token, default chat id, local script path) live in
a `telegram.Config` table, so the same procedure works unmodified on every
machine — you just seed a different config row on each one.

The message text is base64-encoded before it's ever placed on a command
line, so arbitrary text (quotes, newlines, unicode, emoji) can't break the
command or inject shell commands. `@ChatId` and `@ParseMode` are validated
against strict whitelists for the same reason.

## Prerequisites

- A Telegram bot token: message [@BotFather](https://t.me/BotFather) on
  Telegram, `/newbot`, follow the prompts.
- The chat id to send to: message [@userinfobot](https://t.me/userinfobot)
  for your personal chat id, or add the bot to a group/channel and use its
  (negative) group id.
- PowerShell 5.1+ available on the machine (present by default on Windows;
  SQL Server on Linux is not supported by this connector as written).

## Install (per machine)

1. Copy `powershell/Send-TelegramMessage.ps1` to a local path on the machine,
   e.g. `C:\Ops\TelegramConnector\Send-TelegramMessage.ps1`.
2. Run `sql/00_enable_xp_cmdshell.sql` on the instance (as sysadmin). Read
   the security notes in that file — set up a restricted proxy account
   rather than leaving `xp_cmdshell` running as the SQL Server service
   account.
3. Run `sql/01_create_schema_and_config.sql` in whichever database you want
   the connector installed in (a shared ops/utility database works well if
   you want one install reused by every script on the box).
4. Run `sql/02_create_procedure.sql` to create `telegram.usp_SendMessage`.
5. Edit and run `sql/03_seed_config_example.sql`, filling in your bot token,
   chat id, and the local script path from step 1.
6. Test it:
   ```sql
   EXEC telegram.usp_SendMessage @Message = N'Hello from ' + @@SERVERNAME;
   ```

## Usage

```sql
EXEC telegram.usp_SendMessage @Message = N'Backup job finished successfully.';
```

See `sql/04_example_usage.sql` for a TRY/CATCH pattern that sends a success
message on completion and a failure message (with the error text) on
exception — the "let me know when this script is done" use case.

### Parameters

| Parameter     | Default     | Notes                                                          |
|---------------|-------------|------------------------------------------------------------------|
| `@Message`    | required    | The text to send. Any content is safe (base64-encoded internally). |
| `@ChatId`     | NULL        | Overrides the config's `DefaultChatId`. Numeric only.           |
| `@ConfigName` | `'default'` | Which `telegram.Config` row to use — lets one machine notify multiple bots/chats. |
| `@ParseMode`  | NULL        | `Markdown`, `MarkdownV2`, or `HTML` for formatted messages.     |
| `@Silent`     | 0           | Send without a notification sound/banner.                       |
| `@Async`       | 1           | Fire-and-forget (don't block the calling script waiting on PowerShell/network). Set to 0 to wait and see errors while debugging. |

## Security notes

- `telegram.Config` stores the bot token in plain text. Restrict SELECT on
  that table to DBAs only; grant application logins EXECUTE on
  `telegram.usp_SendMessage` alone, never direct table access.
- Only grant EXECUTE on `xp_cmdshell` itself to admins. Everyone else should
  go through the stored procedure, which is the only thing that needs it.
- Use a low-privilege Windows proxy account for `xp_cmdshell`
  (`sp_xp_cmdshell_proxy_account`, see `00_enable_xp_cmdshell.sql`) instead
  of running it as the SQL Server service account.
- If your organization disallows `xp_cmdshell` entirely, the same
  `Send-TelegramMessage.ps1` script can instead be called from a SQL Server
  Agent job step of type "PowerShell" (as a step following the T-SQL step),
  or wrapped in a signed CLR stored procedure — ask if you want that variant
  instead.

## Files

```
telegram-sql-connector/
├── README.md
├── powershell/
│   └── Send-TelegramMessage.ps1     # calls the Telegram Bot API
└── sql/
    ├── 00_enable_xp_cmdshell.sql    # one-time instance setup
    ├── 01_create_schema_and_config.sql
    ├── 02_create_procedure.sql      # telegram.usp_SendMessage
    ├── 03_seed_config_example.sql   # per-machine bot token / chat id / script path
    └── 04_example_usage.sql
```
