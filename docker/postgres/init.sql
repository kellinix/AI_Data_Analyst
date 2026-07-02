-- ============================================================
-- AI Dashboard Generator — PostgreSQL Initialisation
-- ============================================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
CREATE EXTENSION IF NOT EXISTS "btree_gin";

-- Create application database (if not exists via env)
-- The database itself is created by the POSTGRES_DB env var

-- Set timezone
SET timezone = 'UTC';

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE ai_dashboard TO ai_dashboard_user;
