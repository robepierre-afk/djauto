/*
    Enables xp_cmdshell so the connector's stored procedure can invoke PowerShell.

    SECURITY NOTE
    -------------
    xp_cmdshell lets any login with EXECUTE rights on it run arbitrary OS commands as the
    SQL Server service account. Do not grant EXECUTE on xp_cmdshell broadly.
    Instead:
      1. Run this script once per instance (as sysadmin) to turn the feature on.
      2. Lock it down with a proxy credential (see the commented block below) so
         xp_cmdshell runs as a low-privilege Windows account instead of the service account.
      3. Only grant EXECUTE on telegram.usp_SendMessage to the roles/logins that need it;
         never grant EXECUTE on xp_cmdshell itself to non-admin logins.
*/

EXEC sp_configure 'show advanced options', 1;
RECONFIGURE;

EXEC sp_configure 'xp_cmdshell', 1;
RECONFIGURE;

EXEC sp_configure 'show advanced options', 0;
RECONFIGURE;

/*
    OPTIONAL BUT RECOMMENDED: run xp_cmdshell as a restricted proxy account instead of the
    SQL Server service account. Replace the domain\user and password below with a low
    privilege local/service account that only needs rights to run powershell.exe and read
    the connector script.

    EXEC master..sp_xp_cmdshell_proxy_account 'DOMAIN\svc-telegram-connector', 'StrongPasswordHere';

    To remove the proxy account later:
    EXEC master..sp_xp_cmdshell_proxy_account 'DROP';
*/
