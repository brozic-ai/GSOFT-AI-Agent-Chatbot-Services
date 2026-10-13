-- Additive, repeatable migration. Existing legacy duplicates are preserved.
IF OBJECT_ID('dbo.RagDocuments', 'U') IS NOT NULL
BEGIN
    IF COL_LENGTH('dbo.RagDocuments', 'FileSha256') IS NULL
        ALTER TABLE dbo.RagDocuments ADD FileSha256 VARCHAR(64) NULL;
    IF COL_LENGTH('dbo.RagDocuments', 'CurrentIngestionAttemptId') IS NULL
        ALTER TABLE dbo.RagDocuments ADD CurrentIngestionAttemptId VARCHAR(36) NULL;
END;
GO
IF OBJECT_ID('dbo.IngestionTasks', 'U') IS NOT NULL
BEGIN
    IF COL_LENGTH('dbo.IngestionTasks', 'AttemptId') IS NULL
        ALTER TABLE dbo.IngestionTasks ADD AttemptId VARCHAR(36) NULL;
END;
GO
IF OBJECT_ID('dbo.IngestionTasks', 'U') IS NOT NULL
AND NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'UX_IngestionTasks_DocumentAttempt' AND object_id = OBJECT_ID('dbo.IngestionTasks'))
    CREATE UNIQUE INDEX UX_IngestionTasks_DocumentAttempt ON dbo.IngestionTasks(BackendDocumentId, AttemptId) WHERE AttemptId IS NOT NULL;
GO
IF OBJECT_ID('dbo.RagDocuments', 'U') IS NOT NULL AND OBJECT_ID('dbo.RagDocumentFingerprints', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.RagDocumentFingerprints (
        TenantScope VARCHAR(40) NOT NULL,
        FileSha256 VARCHAR(64) NOT NULL,
        DocumentId INT NOT NULL,
        CONSTRAINT PK_RagDocumentFingerprints PRIMARY KEY (TenantScope, FileSha256),
        CONSTRAINT FK_RagDocumentFingerprints_Document FOREIGN KEY (DocumentId) REFERENCES dbo.RagDocuments(Id)
    );
END;
