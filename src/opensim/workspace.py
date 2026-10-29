from opensim.application.parameters import DEFAULT_PARAMETERS, TEXT_PARAMETERS, prepare_parameters
from opensim.storage.schema import initialize, connect_database
import json
from pathlib import Path
import shutil
import sqlite3
import time
import uuid


from opensim.storage.status import ACTIVE_STATUSES,TERMINAL_STATUSES,CANCEL_MESSAGE
from opensim.application.studies import STUDY_TYPES, STUDIES, VIEW_STUDIES, job_is_current
from opensim.storage.jobs import JobsMixin
from opensim.storage.results import ResultsMixin
CAPABILITIES = [
    {"name": "CAD import", "enabled": True, "detail": "Single-solid STEP, IGES, BREP; closed STL, OBJ or 3MF surface meshes"},
    {"name": "Tetrahedral meshing", "enabled": True, "detail": "Gmsh C3D4 or quadratic C3D10"},
    {"name": "Static structural", "enabled": True, "detail": "X-min clamp; point, legacy equal-node end load, or uniform vector traction on a bounding-plane patch"},
    {"name": "Displacement results", "enabled": True, "detail": "Rotatable displacement contour"},
    {"name": "Stress results", "enabled": True, "detail": "Recovered nodal von Mises, MPa display; support-edge peaks may be singular"},
    {"name": "Surface regions", "enabled": True, "detail": "CAD face IDs and optional centroid-box filtering; fully fixed support or global vector traction"},
    {"name": "MCP automation", "enabled": True, "detail": "Local stdio tools and shared workspace"},
    {"name": "Convergence study", "enabled": True, "detail": "Static solve on 3–6 successively finer meshes; change, verdict, Richardson extrapolation and GCI per quantity"},
    {"name": "Modal analysis", "enabled": True, "detail": "Undamped unprestressed modes; X-min face fixed; positive density"},
    {"name": "Thermal analysis", "enabled": True, "detail": "Steady isotropic conduction; fixed temperature plus second temperature or total surface heat input; other surfaces insulated"},
    {"name": "Fluid dynamics", "enabled": True, "detail": "Main-window CFD on user CAD: automatic external fluid enclosures or existing fluid volumes. Native SU2 incompressible Navier-Stokes, laminar or Spalart-Allmaras RANS; velocity slices, pressure, residual/flux checks. Legacy pressure-driven Stokes and analytical benchmarks remain available. No thermal coupling or time-accurate CFD."},
    {"name":"Elastic drop test","enabled":True,"detail":"Low-height blunt drop weight on a parametric simply supported elastic plate; modal bending, contact spring, playback and energy checks. No CAD contact, plasticity, fracture or penetration."},
    *[{"name": name, "enabled": False, "detail": "Planned — not implemented"} for name in
      ("Transient dynamics",
       "Electromagnetics", "Contact", "Nonlinear materials", "Optimization", "GPU solve")],
]


def default_workspace() -> Path:
    return Path(__file__).resolve().parents[2] / "workspace"


class Workspace(JobsMixin,ResultsMixin):
    def __init__(self, root: Path | None = None):
        self.root = (root or default_workspace()).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.database = self.root / "workspace.sqlite3"
        with self.connect() as connection:
            initialize(connection)

    def connect(self):
        return connect_database(self.database)

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
            rows = connection.execute("SELECT * FROM projects ORDER BY created DESC").fetchall()
        return [self._decode_project(row) for row in rows]

    @staticmethod
    def _decode_project(row):
        project = dict(row)
        project["parameters"] = DEFAULT_PARAMETERS | json.loads(project["parameters"])
        return project

    def get_project(self, project_id: str) -> dict:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        if row is None:
            raise ValueError("Unknown project")
        return self._decode_project(row)

    def selected_study(self, project_id):
        with self.connect() as connection:
            row=connection.execute('SELECT study FROM project_studies WHERE project_id=?',(project_id,)).fetchone()
        return row['study'] if row else 'static'

    def job_is_current(self, job, project=None):
        return job_is_current(job,project or self.get_project(job['project_id']))

    def study_settings(self, project_id, study):
        """A named, scoped input view; legacy flat settings remain supported."""
        from opensim.application.studies import input_values,input_signature
        if study not in STUDIES:raise ValueError('Unknown study')
        project=self.get_project(project_id);definition=STUDIES[study]
        return {'study':study,'title':definition.title,'parameters':input_values(study,project['parameters']),
                'input_signature':input_signature(study,project['cad'],project['parameters']),
                'job_kind':definition.job_kind,'result_view':definition.result_view}

    def list_open_projects(self) -> list[dict]:
        with self.connect() as connection:
            rows=connection.execute("SELECT p.* FROM open_projects o JOIN projects p ON p.id=o.project_id ORDER BY o.opened DESC").fetchall()
        return [self._decode_project(row) for row in rows]

    def rename_project(self, project_id: str, name: str) -> dict:
        self.get_project(project_id)
        name = name.strip()
        if not name or len(name) > 120:
            raise ValueError("Project name must contain 1–120 characters")
        with self.connect() as connection:
            connection.execute("UPDATE projects SET name=? WHERE id=?", (name, project_id))
        return self.get_project(project_id)

    def close_project(self, project_id: str):
        """Remove a project from the outline; retain its model, jobs and settings."""
        self.get_project(project_id)
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("DELETE FROM open_projects WHERE project_id=?", (project_id,))
            selected = connection.execute("SELECT project_id FROM ui WHERE id=1").fetchone()["project_id"]
            if selected == project_id:
                replacement = connection.execute("SELECT project_id FROM open_projects ORDER BY opened DESC LIMIT 1").fetchone()
                connection.execute("UPDATE ui SET project_id=?,view='geometry',modal_mode=1 WHERE id=1",
                                   (replacement["project_id"] if replacement else None,))
        return self.ui_state()

    def project_locations(self, project_id: str) -> dict:
        project = self.get_project(project_id)
        with self.connect() as connection:
            source = connection.execute("SELECT source_path FROM project_sources WHERE project_id=? AND cad_path=?",
                                        (project_id, project["cad"])).fetchone()
            latest = connection.execute("SELECT id FROM jobs WHERE project_id=? ORDER BY created DESC LIMIT 1", (project_id,)).fetchone()
        return {"project_folder": str(self.root / project_id), "library_file": str(self.database),
                "cad_file": project["cad"], "source_file": source["source_path"] if source else None,
                "jobs_folder": str(self.root / project_id / "jobs"),
                "latest_run": str(self.root / project_id / "jobs" / latest["id"]) if latest else None}

    def _assert_idle(self, connection, project_id):
        if connection.execute("SELECT id FROM jobs WHERE project_id=? AND status IN ('queued','running')",
                              (project_id,)).fetchone():
            raise ValueError("This project has an active job; wait before changing its inputs")

    def import_cad(self, project_id: str, source: str) -> dict:
        self.get_project(project_id)
        path = Path(source).expanduser().resolve()
        from opensim.file_formats import SUPPORTED_SUFFIXES
        if path.suffix.lower() not in SUPPORTED_SUFFIXES:
            raise ValueError("Choose a STEP, IGES, BREP, STL, OBJ or 3MF file")
        if not path.is_file():
            raise FileNotFoundError(path)
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._assert_idle(connection, project_id)
            target = self.root / project_id / ("input-" + uuid.uuid4().hex + path.suffix.lower())
            shutil.copyfile(path, target)
            current = connection.execute("SELECT parameters FROM projects WHERE id=?", (project_id,)).fetchone()
            parameters = DEFAULT_PARAMETERS | json.loads(current["parameters"])
            parameters.update({"support_region": {}, "load_region": {}, "load_cases": [], "thermal_fixed_region": {}, "thermal_source_region": {}, "cfd_inlet_region":{}, "cfd_outlet_region":{}})
            connection.execute("UPDATE projects SET cad=?, parameters=?, revision=revision+1 WHERE id=?",
                               (str(target), json.dumps(parameters), project_id))
            connection.execute("INSERT INTO project_sources VALUES(?,?,?) ON CONFLICT(project_id) DO UPDATE SET cad_path=excluded.cad_path,source_path=excluded.source_path",
                               (project_id, str(target), str(path)))
        return self.get_project(project_id)

    def set_parameters(self, project_id: str, parameters: dict) -> dict:
        project = self.get_project(project_id)
        parameters, merged = prepare_parameters(project["parameters"], parameters)
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


    def show_project(self, project_id: str, view="geometry", mode=1) -> dict:
        self.get_project(project_id)
        if view not in {'geometry','mesh'} | set(VIEW_STUDIES):
            raise ValueError('Choose a view: '+', '.join(sorted({'geometry','mesh'} | set(VIEW_STUDIES))))
        if isinstance(mode, bool) or not isinstance(mode, int) or not 1 <= mode <= 30:
            raise ValueError("Mode must be an integer from 1 to 30")
        if view == "modal":
            self.current_artifact(project_id, view, mode)
        with self.connect() as connection:
            connection.execute("INSERT OR IGNORE INTO open_projects VALUES(?,?)", (project_id, time.time()))
            if view in VIEW_STUDIES:
                study = VIEW_STUDIES[view]
                connection.execute("INSERT INTO project_studies VALUES(?,?) ON CONFLICT(project_id) DO UPDATE SET study=excluded.study", (project_id, study))
            connection.execute("UPDATE ui SET project_id=?,view=?,modal_mode=? WHERE id=1", (project_id, view, mode))
        return self.ui_state()

    def select_study(self, project_id: str, study: str) -> dict:
        """Select a study's settings without solving or changing numerical inputs."""
        if study not in STUDY_TYPES:
            raise ValueError('Choose a study: '+', '.join(STUDY_TYPES))
        self.get_project(project_id)
        with self.connect() as connection:
            connection.execute("INSERT INTO project_studies VALUES(?,?) ON CONFLICT(project_id) DO UPDATE SET study=excluded.study", (project_id, study))
            connection.execute("INSERT OR IGNORE INTO open_projects VALUES(?,?)", (project_id, time.time()))
            connection.execute("UPDATE ui SET project_id=?,view='geometry',modal_mode=1 WHERE id=1", (project_id,))
        return self.ui_state()

    def ui_state(self) -> dict:
        with self.connect() as connection:
            state = dict(connection.execute("SELECT ui.*,COALESCE(s.study,'static') AS study FROM ui LEFT JOIN project_studies s ON s.project_id=ui.project_id WHERE ui.id=1").fetchone())
        state["desktop_connected"] = time.time() - state["heartbeat"] < 5
        return state

    def heartbeat(self):
        with self.connect() as connection:
            connection.execute("UPDATE ui SET heartbeat=? WHERE id=1", (time.time(),))

    def set_theme(self, theme: str):
        if theme not in {"dark", "light", "midnight"}:
            raise ValueError("Theme must be dark, light or midnight")
        with self.connect() as connection:
            connection.execute("UPDATE ui SET theme=? WHERE id=1", (theme,))

    def set_language(self, language: str):
        if language not in {"en", "cat"}:
            raise ValueError("Language must be en or cat")
        with self.connect() as connection:
            connection.execute("UPDATE ui SET language=? WHERE id=1", (language,))
