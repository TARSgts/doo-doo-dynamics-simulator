"""Jobs repository operations behind the Workspace API."""
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import uuid
from opensim.application.parameters import DEFAULT_PARAMETERS
from opensim.application.studies import STUDIES, study_for_job, input_signature
from opensim.job_progress import STAGE_LABELS
from opensim.storage.status import TERMINAL_STATUSES, CANCEL_MESSAGE


class JobsMixin:
    def start_job(self, project_id: str, kind: str, example="perforated_plate") -> dict:
        if kind not in {definition.job_kind for definition in STUDIES.values()} | {'example','mesh','cfd_validation','cfd_mesh'}:
            raise ValueError("Unsupported job kind")
        if example not in {"perforated_plate", "axial_bar", "cantilever_beam", "heat_sink"}:
            raise ValueError("Unsupported test object")
        job_id = uuid.uuid4().hex
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._assert_idle(connection, project_id)
            row = connection.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
            if row is None:
                raise ValueError("Unknown project")
            project = dict(row)
            if kind not in {"example", "cfd", "cfd_validation"} and not project["cad"]:
                raise ValueError("Import CAD or create a test object first")
            if kind == "example":
                project["revision"] += 1
                parameters = DEFAULT_PARAMETERS | json.loads(project["parameters"])
                parameters.update({"support_region": {}, "load_region": {}, "load_cases": [], "thermal_fixed_region": {}, "thermal_source_region": {}, "cfd_inlet_region":{}, "cfd_outlet_region":{}})
                if example == 'heat_sink':
                    from opensim.heat_sink import HEAT_SINK_PARAMETERS
                    parameters.update(HEAT_SINK_PARAMETERS)
                project["parameters"] = json.dumps(parameters)
                connection.execute("UPDATE projects SET revision=?,parameters=? WHERE id=?", (project["revision"], project["parameters"], project_id))
            payload = {"cad": project["cad"], "parameters": DEFAULT_PARAMETERS | json.loads(project["parameters"]), "example": example}
            selected_study = connection.execute("SELECT study FROM project_studies WHERE project_id=?", (project_id,)).fetchone()
            payload['study'] = study_for_job(kind, selected_study['study'] if selected_study else 'static', example)
            payload['input_signature'] = input_signature(payload['study'],payload['cad'],payload['parameters'],kind=kind)
            now = time.time()
            connection.execute("INSERT INTO jobs(id,project_id,kind,status,revision,payload,result,error,created,updated) VALUES(?,?,?,?,?,?,?,?,?,?)",
                               (job_id, project_id, kind, "queued", project["revision"],
                                json.dumps(payload), None, None, now, now))
            connection.execute("INSERT INTO job_progress VALUES(?,?,?)", (job_id, "queued", now))
            study = payload['study'] if kind != 'mesh' else None
            if kind == 'example' and example == 'heat_sink':
                study = 'thermal'
                payload['study'] = 'thermal'
                connection.execute('UPDATE jobs SET payload=? WHERE id=?', (json.dumps(payload), job_id))
            if study:
                connection.execute("INSERT INTO project_studies VALUES(?,?) ON CONFLICT(project_id) DO UPDATE SET study=excluded.study", (project_id, study))
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

    @staticmethod
    def _decode_job(row):
        job = dict(row)
        if job["status"] in TERMINAL_STATUSES:
            job["progress_stage"] = job["status"]
        elif not job.get("progress_stage"):
            job["progress_stage"] = "queued" if job["status"] == "queued" else "starting"
        job["payload"] = json.loads(job["payload"])
        job["result"] = json.loads(job["result"]) if job["result"] else None
        return job

    def get_job(self, job_id: str) -> dict:
        with self.connect() as connection:
            row = connection.execute("SELECT jobs.*,job_progress.stage AS progress_stage FROM jobs LEFT JOIN job_progress ON jobs.id=job_progress.job_id WHERE jobs.id=?", (job_id,)).fetchone()
        if row is None:
            raise ValueError("Unknown job")
        return self._decode_job(row)

    def list_jobs(self, project_id: str, *, limit=None, offset=0, kinds=None, status=None) -> list[dict]:
        """Read history in one query; optional pagination keeps large libraries cheap."""
        if isinstance(offset,bool) or not isinstance(offset,int) or offset<0:
            raise ValueError('Job offset must be a nonnegative integer')
        if limit is not None and (isinstance(limit,bool) or not isinstance(limit,int) or limit<1):
            raise ValueError('Job limit must be a positive integer')
        sql='SELECT jobs.*,job_progress.stage AS progress_stage FROM jobs LEFT JOIN job_progress ON jobs.id=job_progress.job_id WHERE project_id=?'
        values=[project_id]
        if kinds:
            sql+=' AND kind IN ('+','.join('?' for _ in kinds)+')';values.extend(kinds)
        if status:
            sql+=' AND status=?';values.append(status)
        sql+=' ORDER BY created DESC,id DESC LIMIT ? OFFSET ?';values.extend([limit if limit is not None else -1,offset])
        with self.connect() as connection:
            rows=connection.execute(sql,values).fetchall()
        return [self._decode_job(row) for row in rows]

    def job_directory(self, job_id: str) -> Path:
        job = self.get_job(job_id)
        return self.root / job["project_id"] / "jobs" / job_id

    def finish_job(self, job_id: str, result: dict | None = None, error: str | None = None):
        with self.connect() as connection:
            # A stopped job stays stopped even if its worker reports late.
            updated = connection.execute("UPDATE jobs SET status=?,result=?,error=?,updated=? WHERE id=? AND status IN ('queued','running')",
                                         ("failed" if error else "completed", json.dumps(result) if result else None,
                                          error, time.time(), job_id)).rowcount
            if not updated:
                return
            connection.execute("INSERT INTO job_progress VALUES(?,?,?) ON CONFLICT(job_id) DO UPDATE SET stage=excluded.stage,updated=excluded.updated",
                               (job_id, "failed" if error else "completed", time.time()))

    def cancel_job(self, job_id: str) -> dict:
        """Stop a queued or running job. Its worker notices within a second and ends any solver process."""
        self.get_job(job_id)
        with self.connect() as connection:
            now = time.time()
            updated = connection.execute("UPDATE jobs SET status='cancelled',error=?,updated=? WHERE id=? AND status IN ('queued','running')",
                                         (CANCEL_MESSAGE, now, job_id)).rowcount
            if not updated:
                raise ValueError("This job has already finished; only queued or running jobs can be stopped")
            connection.execute("INSERT INTO job_progress VALUES(?,?,?) ON CONFLICT(job_id) DO UPDATE SET stage=excluded.stage,updated=excluded.updated",
                               (job_id, "cancelled", now))
        return self.get_job(job_id)

    def active_job(self, project_id: str) -> dict | None:
        with self.connect() as connection:
            row=connection.execute("SELECT jobs.*,job_progress.stage AS progress_stage FROM jobs LEFT JOIN job_progress ON jobs.id=job_progress.job_id WHERE project_id=? AND status IN ('queued','running') LIMIT 1",(project_id,)).fetchone()
        return self._decode_job(row) if row else None

    def set_job_progress(self, job_id: str, stage: str):
        if stage not in STAGE_LABELS or stage in TERMINAL_STATUSES:
            raise ValueError("Choose a running job stage; completion is recorded by finish_job or cancel_job")
        self.get_job(job_id)
        with self.connect() as connection:
            now = time.time()
            connection.execute("INSERT INTO job_progress(job_id,stage,updated) SELECT id,?,? FROM jobs WHERE id=? AND status IN ('queued','running') ON CONFLICT(job_id) DO UPDATE SET stage=excluded.stage,updated=excluded.updated",
                               (stage, now, job_id))
            connection.execute("UPDATE jobs SET updated=? WHERE id=? AND status IN ('queued','running')", (now, job_id))
