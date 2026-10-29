"""Idempotent SQLite setup; preserves existing projects and job snapshots."""
import time
import sqlite3


class WorkspaceConnection(sqlite3.Connection):
    """Keep sqlite's transaction API, and release file handles on context exit."""
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()


def connect_database(path):
    connection=sqlite3.connect(path,timeout=10,factory=WorkspaceConnection)
    connection.row_factory=sqlite3.Row
    return connection


def initialize(connection):
    had_open_projects = connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='open_projects'").fetchone()
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS open_projects (project_id TEXT PRIMARY KEY, opened REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS project_studies (project_id TEXT PRIMARY KEY, study TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS project_sources (
            project_id TEXT PRIMARY KEY, cad_path TEXT NOT NULL, source_path TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, cad TEXT,
            parameters TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 0,
            created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY, project_id TEXT NOT NULL, kind TEXT NOT NULL,
            status TEXT NOT NULL, revision INTEGER NOT NULL, payload TEXT NOT NULL,
            result TEXT, error TEXT, created REAL NOT NULL, updated REAL NOT NULL);
        CREATE UNIQUE INDEX IF NOT EXISTS one_active_job ON jobs(project_id)
            WHERE status IN ('queued', 'running');
        CREATE TABLE IF NOT EXISTS job_progress (
            job_id TEXT PRIMARY KEY, stage TEXT NOT NULL, updated REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS ui (id INTEGER PRIMARY KEY CHECK(id=1),
            project_id TEXT, view TEXT NOT NULL DEFAULT 'geometry', heartbeat REAL NOT NULL DEFAULT 0);
        INSERT OR IGNORE INTO ui(id) VALUES(1);
    """)
    if "theme" not in {row["name"] for row in connection.execute("PRAGMA table_info(ui)")}:
        connection.execute("ALTER TABLE ui ADD COLUMN theme TEXT NOT NULL DEFAULT 'dark'")
    if "modal_mode" not in {row["name"] for row in connection.execute("PRAGMA table_info(ui)")}:
        connection.execute("ALTER TABLE ui ADD COLUMN modal_mode INTEGER NOT NULL DEFAULT 1")
    if "language" not in {row["name"] for row in connection.execute("PRAGMA table_info(ui)")}:
        connection.execute("ALTER TABLE ui ADD COLUMN language TEXT NOT NULL DEFAULT 'en'")
    if not had_open_projects:
        connection.execute("INSERT OR IGNORE INTO open_projects SELECT project_id,? FROM ui WHERE project_id IN (SELECT id FROM projects)", (time.time(),))
    connection.execute("INSERT OR IGNORE INTO project_studies SELECT project_id,CASE WHEN view='modal' THEN 'modal' ELSE 'static' END FROM ui WHERE project_id IN (SELECT id FROM projects)")
    connection.execute("CREATE INDEX IF NOT EXISTS jobs_by_project_created ON jobs(project_id,created DESC)")
