/*
    Example usage patterns for telegram.usp_SendMessage from an SSMS script.
*/

-- 1) Simplest case: fire a message whenever a script finishes.
PRINT 'Doing the work...';
WAITFOR DELAY '00:00:02'; -- stand-in for your real query/job

EXEC telegram.usp_SendMessage
    @Message = N'Script finished on ' + @@SERVERNAME + N' at ' + CONVERT(NVARCHAR(30), SYSDATETIME(), 120);


-- 2) Success/failure notification wrapped around a real long-running query.
BEGIN TRY
    DECLARE @StartTime DATETIME2 = SYSUTCDATETIME();

    -- ... your actual query / stored procedure call goes here ...
    EXEC dbo.MyLongRunningProc;

    DECLARE @DurationSec INT = DATEDIFF(SECOND, @StartTime, SYSUTCDATETIME());

    EXEC telegram.usp_SendMessage
        @Message = CONCAT(N'✅ ', @@SERVERNAME, N'/', DB_NAME(), N': job completed in ', @DurationSec, N's');
END TRY
BEGIN CATCH
    EXEC telegram.usp_SendMessage
        @Message = CONCAT(N'❌ ', @@SERVERNAME, N'/', DB_NAME(), N': job FAILED - ', ERROR_MESSAGE());
    THROW;
END CATCH;


-- 3) Send to a specific chat/channel instead of the config's default, with Markdown formatting.
EXEC telegram.usp_SendMessage
    @Message    = N'*Nightly ETL* finished with `0` errors.',
    @ChatId     = N'-1001234567890',   -- a group/channel id (negative numbers are groups)
    @ParseMode  = N'Markdown';


-- 4) Wait for delivery instead of fire-and-forget (useful when debugging connectivity issues).
EXEC telegram.usp_SendMessage
    @Message = N'Synchronous test message',
    @Async   = 0;
