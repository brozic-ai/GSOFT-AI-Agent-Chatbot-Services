-- =====================================================================
-- GSOFT AI Extension for Azure DevOps
-- Schema khởi tạo PostgreSQL - Phase 0 (ERD sơ khởi)
-- Chạy tự động 1 lần khi container postgres khởi tạo lần đầu
-- =====================================================================

-- Cho phép sinh UUID bằng gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ---------------------------------------------------------------------
-- PROJECTS
-- ---------------------------------------------------------------------
CREATE TABLE projects (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        VARCHAR(255) NOT NULL,
    customer    VARCHAR(255),
    scope       TEXT,
    objective   TEXT,
    timeline    VARCHAR(255),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by  VARCHAR(255)
);

-- ---------------------------------------------------------------------
-- PHASE_TEMPLATES
-- ---------------------------------------------------------------------
CREATE TABLE phase_templates (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    phase_name          VARCHAR(255) NOT NULL,
    phase_order         INT NOT NULL,
    task_template_json  JSONB,
    is_active           BOOLEAN NOT NULL DEFAULT true
);

-- ---------------------------------------------------------------------
-- DOCUMENTS
-- ---------------------------------------------------------------------
CREATE TABLE documents (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id     UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    document_type  VARCHAR(50) NOT NULL
        CHECK (document_type IN ('Contract','BRD','SRS','MeetingMinutes','UIDesign','BugReport')),
    file_name      VARCHAR(500) NOT NULL,
    blob_url       VARCHAR(1000) NOT NULL,
    uploaded_by    VARCHAR(255),
    uploaded_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    status         VARCHAR(50) NOT NULL DEFAULT 'Uploaded'
);
CREATE INDEX idx_documents_project_id ON documents(project_id);

-- ---------------------------------------------------------------------
-- SRS_JOBS
-- ---------------------------------------------------------------------
CREATE TABLE srs_jobs (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id           UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    status                VARCHAR(50) NOT NULL DEFAULT 'Checking'
        CHECK (status IN ('Checking','NeedMoreInfo','SummaryReady','Decomposing','Done')),
    completeness_report   JSONB,
    summary               TEXT,
    started_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at          TIMESTAMPTZ
);
CREATE INDEX idx_srs_jobs_document_id ON srs_jobs(document_id);

-- ---------------------------------------------------------------------
-- DECOMPOSITION_PREVIEWS
-- ---------------------------------------------------------------------
CREATE TABLE decomposition_previews (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    srs_job_id    UUID NOT NULL REFERENCES srs_jobs(id) ON DELETE CASCADE,
    tree_json     JSONB NOT NULL,
    version       INT NOT NULL DEFAULT 1,
    status        VARCHAR(50) NOT NULL DEFAULT 'Draft'
        CHECK (status IN ('Draft','Approved','Rejected','Synced')),
    approved_by   VARCHAR(255),
    approved_at   TIMESTAMPTZ
);
CREATE INDEX idx_decomp_previews_srs_job_id ON decomposition_previews(srs_job_id);

-- ---------------------------------------------------------------------
-- BUG_IMPORT_JOBS
-- ---------------------------------------------------------------------
CREATE TABLE bug_import_jobs (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id      UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    source_file      VARCHAR(500) NOT NULL,
    status           VARCHAR(50) NOT NULL DEFAULT 'Pending'
        CHECK (status IN ('Pending','Processing','Done','Failed')),
    total_items      INT NOT NULL DEFAULT 0,
    processed_items  INT NOT NULL DEFAULT 0
);
CREATE INDEX idx_bug_import_jobs_document_id ON bug_import_jobs(document_id);

-- ---------------------------------------------------------------------
-- BUG_ITEMS
-- ---------------------------------------------------------------------
CREATE TABLE bug_items (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id              UUID NOT NULL REFERENCES bug_import_jobs(id) ON DELETE CASCADE,
    row_index           INT NOT NULL,
    raw_text            TEXT NOT NULL,
    classified_type     VARCHAR(50)
        CHECK (classified_type IN ('Bug','Improvement')),
    linked_feature_id   VARCHAR(255),
    status              VARCHAR(50) NOT NULL DEFAULT 'Pending'
        CHECK (status IN ('Pending','Classified','Linked','Rejected'))
);
CREATE INDEX idx_bug_items_job_id ON bug_items(job_id);

-- ---------------------------------------------------------------------
-- ROLES
-- ---------------------------------------------------------------------
CREATE TABLE roles (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    role_name  VARCHAR(100) NOT NULL UNIQUE
);

-- ---------------------------------------------------------------------
-- PERMISSIONS
-- ---------------------------------------------------------------------
CREATE TABLE permissions (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    permission_name  VARCHAR(150) NOT NULL UNIQUE
);

-- ---------------------------------------------------------------------
-- ROLE_PERMISSIONS (bảng nối N-N giữa ROLES và PERMISSIONS)
-- ERD gốc vẽ quan hệ "ROLES ||--o{ PERMISSIONS : grants" nhưng N-N
-- cần bảng trung gian trong SQL thực tế -> bổ sung bảng này.
-- ---------------------------------------------------------------------
CREATE TABLE role_permissions (
    role_id        UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    permission_id  UUID NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
    PRIMARY KEY (role_id, permission_id)
);

-- ---------------------------------------------------------------------
-- USER_ROLE_MAP
-- ---------------------------------------------------------------------
CREATE TABLE user_role_map (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    role_id              UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    project_id           UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    azure_ad_object_id   VARCHAR(255) NOT NULL,
    UNIQUE (role_id, project_id, azure_ad_object_id)
);
CREATE INDEX idx_user_role_map_project_id ON user_role_map(project_id);
CREATE INDEX idx_user_role_map_role_id ON user_role_map(role_id);

-- ---------------------------------------------------------------------
-- AUDIT_LOG
-- ---------------------------------------------------------------------
CREATE TABLE audit_log (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id    UUID REFERENCES projects(id) ON DELETE SET NULL,
    module        VARCHAR(100) NOT NULL,
    action        VARCHAR(150) NOT NULL,
    performed_by  VARCHAR(255),
    metadata      JSONB,
    "timestamp"   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_audit_log_project_id ON audit_log(project_id);

-- ---------------------------------------------------------------------
-- Seed dữ liệu tối thiểu cho 8 vai trò (theo quy trình V1.0)
-- ---------------------------------------------------------------------
INSERT INTO roles (role_name) VALUES
    ('PM'), ('BA Lead'), ('BA'), ('Tech Lead'),
    ('DEV'), ('QC Lead'), ('QC'), ('DevOps');