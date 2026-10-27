import json
import math
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import uuid


DEFAULT_PARAMETERS = {"mesh_size_m": 0.004, "cad_scale": 1.0, "young_Pa": 210e9,
                      "poisson": 0.3, "load_N": 1000.0, "element_order": 1,
                      "load_axis": "x", "load_kind": "face", "density_kg_m3": 7850.0, "mode_count": 6}
CAPABILITIES = [
    {"name": "CAD import", "enabled": True, "detail": "Single-solid STEP, IGES, BREP"},
    {"name": "Tetrahedral meshing", "enabled": True, "detail": "Gmsh C3D4 or quadratic C3D10"},
    {"name": "Static structural", "enabled": True, "detail": "X-min clamp; X/Y/Z force at tip center or end face"},
    {"name": "Displacement results", "enabled": True, "detail": "Rotatable displacement contour"},
    {"name": "MCP automation", "enabled": True, "detail": "Local stdio tools and shared workspace"},
    {"name": "Modal analysis", "enabled": True, "detail": "Undamped unprestressed modes; X-min face fixed; positive density"},
    *[{"name": name, "enabled": False, "detail": "Planned — not implemented"} for name in
      ("Thermal analysis", "Transient dynamics", "Fluid dynamics",
       "Electromagnetics", "Contact", "Nonlinear materials", "Optimization", "GPU solve")],
]


def default_workspace() -> Path:
    return Path(__file__).resolve().parents[2] / "workspace"


class Workspace:
    def __init__(self, root: Path | None = None):
        self.root = (root or default_workspace()).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.database = self.root / "workspace.sqlite3"
        with self.connect() as connection:
            connection.executescript("""
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

    def connect(self):
        connection = sqlite3.connect(self.database, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def create_project(self, name: str) -> dict:
        name = name.strip()
        if not name or len(name) > 120:
            raise ValueError("Project name must contain 1–120 characters")
        project_id = uuid.uuid4().hex
        (self.root / project_id).mkdir()
        with self.connect() as connection:
            connection.execute("INSERT INTO projects VALUES(?,?,?,?,?,?)",
                               (project_id, name, None, json.dumps(DEFAULT_PARAMETERS), 0, time.time()))
        return self.get_project(project_id)

    def list_projects(self) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute("SELECT id FROM projects ORDER BY created DESC").fetchall()
        return [self.get_project(row["id"]) for row in rows]

    def get_project(self, project_id: str) -> dict:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        if row is None:
            raise ValueError("Unknown project")
        project = dict(row)
        project["parameters"] = DEFAULT_PARAMETERS | json.loads(project["parameters"])
        return project

    def _assert_idle(self, connection, project_id):
        if connection.execute("SELECT id FROM jobs WHERE project_id=? AND status IN ('queued','running')",
                              (project_id,)).fetchone():
            raise ValueError("This project has an active job; wait before changing its inputs")

    def import_cad(self, project_id: str, source: str) -> dict:
        self.get_project(project_id)
        path = Path(source).expanduser().resolve()
        if path.suffix.lower() not in {".step", ".stp", ".iges", ".igs", ".brep"}:
            raise ValueError("Choose STEP, IGES or BREP CAD")
        if not path.is_file():
            raise FileNotFoundError(path)
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._assert_idle(connection, project_id)
            target = self.root / project_id / ("input-" + uuid.uuid4().hex + path.suffix.lower())
            shutil.copyfile(path, target)
            connection.execute("UPDATE projects SET cad=?, revision=revision+1 WHERE id=?",
                               (str(target), project_id))
        return self.get_project(project_id)

    def set_parameters(self, project_id: str, parameters: dict) -> dict:
        project = self.get_project(project_id)
        if set(parameters) - set(DEFAULT_PARAMETERS):
            raise ValueError("Unsupported analysis parameter")
        merged = project["parameters"] | parameters
        numeric = [value for key, value in merged.items() if key not in {"load_axis", "load_kind"}]
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
               for value in numeric):
            raise ValueError("All parameters must be finite numbers")
        if merged["element_order"] not in {1, 2} or merged["load_axis"] not in {"x", "y", "z"} or merged["load_kind"] not in {"face", "point"}:
            raise ValueError("Choose element order 1/2, direction X/Y/Z and face/point application")
        if any(merged[key] <= 0 for key in ("mesh_size_m", "cad_scale", "young_Pa")):
            raise ValueError("Mesh size, CAD scale and Young's modulus must be positive")
        from opensim.modal_parameters import validate_modal_parameters
        validate_modal_parameters(merged["density_kg_m3"], merged["mode_count"])
        if not -1 < merged["poisson"] < 0.5 or merged["load_N"] == 0:
            raise ValueError("Use -1 < Poisson ratio < 0.5 and a nonzero axial load")
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._assert_idle(connection, project_id)
            current = connection.execute("SELECT parameters FROM projects WHERE id=?", (project_id,)).fetchone()
            current_parameters = DEFAULT_PARAMETERS | json.loads(current["parameters"])
            if any(current_parameters[key] != merged[key] for key in parameters):
                current_parameters.update(parameters)
                connection.execute("UPDATE projects SET parameters=?,revision=revision+1 WHERE id=?",
                                   (json.dumps(current_parameters), project_id))
        return self.get_project(project_id)

    def start_job(self, project_id: str, kind: str, example="perforated_plate") -> dict:
        if kind not in {"example", "mesh", "solve", "modal"}:
            raise ValueError("Unsupported job kind")
        if example not in {"perforated_plate", "axial_bar", "cantilever_beam"}:
            raise ValueError("Unsupported test object")
        job_id = uuid.uuid4().hex
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._assert_idle(connection, project_id)
            row = connection.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
            if row is None:
                raise ValueError("Unknown project")
            project = dict(row)
            if kind != "example" and not project["cad"]:
                raise ValueError("Import CAD or create a test object first")
            if kind == "example":
                project["revision"] += 1
                connection.execute("UPDATE projects SET revision=? WHERE id=?", (project["revision"], project_id))
            payload = {"cad": project["cad"], "parameters": DEFAULT_PARAMETERS | json.loads(project["parameters"]), "example": example}
            now = time.time()
            connection.execute("INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?)",
                               (job_id, project_id, kind, "queued", project["revision"],
                                json.dumps(payload), None, None, now, now))
        directory = self.job_directory(job_id)
        directory.mkdir(parents=True)
        try:
            with (directory / "worker.log").open("w", encoding="utf-8") as log:
                process = subprocess.Popen(
                    [sys.executable, "-m", "opensim.worker", "--workspace", str(self.root), "--job", job_id],
                    stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        except OSError as error:
            self.finish_job(job_id, error=str(error))
            raise
        threading.Thread(target=self._watch, args=(process, job_id), daemon=True).start()
        return self.get_job(job_id)

    def _watch(self, process, job_id):
        process.wait()
        if self.get_job(job_id)["status"] in {"queued", "running"}:
            self.finish_job(job_id, error=f"Worker exited unexpectedly ({process.returncode}); inspect worker.log")

    def get_job(self, job_id: str) -> dict:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise ValueError("Unknown job")
        job = dict(row)
        job["payload"] = json.loads(job["payload"])
        job["result"] = json.loads(job["result"]) if job["result"] else None
        return job

    def list_jobs(self, project_id: str) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute("SELECT id FROM jobs WHERE project_id=? ORDER BY created DESC", (project_id,)).fetchall()
        return [self.get_job(row["id"]) for row in rows]

    def job_directory(self, job_id: str) -> Path:
        job = self.get_job(job_id)
        return self.root / job["project_id"] / "jobs" / job_id

    def finish_job(self, job_id: str, result: dict | None = None, error: str | None = None):
        with self.connect() as connection:
            connection.execute("UPDATE jobs SET status=?,result=?,error=?,updated=? WHERE id=?",
                               ("failed" if error else "completed", json.dumps(result) if result else None,
                                error, time.time(), job_id))

    def current_artifact(self, project_id: str, view="results", mode=1) -> Path | None:
        project = self.get_project(project_id)
        for job in self.list_jobs(project_id):
            if job["revision"] != project["revision"] or job["status"] != "completed":
                continue
            directory = self.job_directory(job["id"])
            if view == "modal" and job["kind"] == "modal":
                if isinstance(mode, bool) or not isinstance(mode, int) or not 1 <= mode <= job["result"]["mode_count"]:
                    raise ValueError("Selected mode is outside the completed result range")
                return directory / "modal" / f"mode-{mode}.html"
            if view == "results" and job["kind"] == "solve":
                return directory / "solve" / "results.html"
            if view in {"geometry", "mesh"}:
                relative = "modal/mode-1.html" if job["kind"] == "modal" else "solve/results.html" if job["kind"] == "solve" else "preview.html"
                candidate = directory / relative
                if candidate.is_file():
                    return candidate
        return None

    def get_results(self, project_id: str) -> dict:
        project = self.get_project(project_id)
        for job in self.list_jobs(project_id):
            if job["revision"] == project["revision"] and job["kind"] == "solve" and job["status"] == "completed":
                return {"job_id": job["id"], "summary": job["result"],
                        "artifacts": {name: str(self.job_directory(job["id"]) / "solve" / name)
                                      for name in ("results.html", "results.vtk", "model.frd", "manifest.json")}}
        raise ValueError("No completed solve for the current project inputs")

    def get_modal_results(self, project_id: str) -> dict:
        project = self.get_project(project_id)
        for job in self.list_jobs(project_id):
            if job["revision"] == project["revision"] and job["kind"] == "modal" and job["status"] == "completed":
                directory = self.job_directory(job["id"]) / "modal"
                return {"job_id": job["id"], "summary": job["result"],
                        "artifacts": {name: str(directory / name) for name in ("modes.npz", "model.frd", "manifest.json")},
                        "modes": [{"mode": index, "frequency_Hz": frequency, "viewer": str(directory / f"mode-{index}.html"),
                                   "vtk": str(directory / f"mode-{index}.vtk")}
                                  for index, frequency in enumerate(job["result"]["frequencies_Hz"], start=1)]}
        raise ValueError("No completed modal solve for the current project inputs")

    def show_project(self, project_id: str, view="geometry", mode=1) -> dict:
        self.get_project(project_id)
        if view not in {"geometry", "mesh", "results", "modal"}:
            raise ValueError("View must be geometry, mesh, results or modal")
        if isinstance(mode, bool) or not isinstance(mode, int) or not 1 <= mode <= 30:
            raise ValueError("Mode must be an integer from 1 to 30")
        if view == "modal":
            self.current_artifact(project_id, view, mode)
        with self.connect() as connection:
            connection.execute("UPDATE ui SET project_id=?,view=?,modal_mode=? WHERE id=1", (project_id, view, mode))
        return self.ui_state()

    def ui_state(self) -> dict:
        with self.connect() as connection:
            state = dict(connection.execute("SELECT * FROM ui WHERE id=1").fetchone())
        state["desktop_connected"] = time.time() - state["heartbeat"] < 5
        return state

    def heartbeat(self):
        with self.connect() as connection:
            connection.execute("UPDATE ui SET heartbeat=? WHERE id=1", (time.time(),))

    def set_theme(self, theme: str):
        if theme not in {"dark", "light"}:
            raise ValueError("Theme must be dark or light")
        with self.connect() as connection:
            connection.execute("UPDATE ui SET theme=? WHERE id=1", (theme,))

    def set_language(self, language: str):
        if language not in {"en", "cat"}:
            raise ValueError("Language must be en or cat")
        with self.connect() as connection:
            connection.execute("UPDATE ui SET language=? WHERE id=1", (language,))
