"""Results repository operations behind the Workspace API."""
from pathlib import Path
from opensim.application.studies import study_for_job, job_is_current


class ResultsMixin:
    def latest_result_job(self, project_id, kinds):
        project=self.get_project(project_id)
        return next((job for job in self.list_jobs(project_id,kinds=kinds,status='completed') if job_is_current(job,project)),None)

    def current_artifact(self, project_id: str, view="results", mode=1) -> Path | None:
        project = self.get_project(project_id)
        study=self.selected_study(project_id)
        for job in self.list_jobs(project_id,status='completed'):
            if not job_is_current(job, project) or job["status"] != "completed":
                continue
            if view in {'geometry','mesh'} and job['kind']!='example' and study_for_job(job['kind'],job['payload'].get('study','static'))!=study:
                continue
            directory = self.job_directory(job["id"])
            if view == "modal" and job["kind"] == "modal":
                if isinstance(mode, bool) or not isinstance(mode, int) or not 1 <= mode <= job["result"]["mode_count"]:
                    raise ValueError("Selected mode is outside the completed result range")
                return directory / "modal" / f"mode-{mode}.html"
            if view == "results" and job["kind"] == "solve":
                return directory / "solve" / "results.html"
            if view == "thermal" and job["kind"] == "thermal":
                return directory / "thermal" / "results.html"
            if view in {'cfd','cfd_slice','cfd_report'} and job['kind'] in {'cfd','cfd_validation'}:
                folder=directory/job['kind'];name='report.html' if view=='cfd_report' or job['kind']=='cfd_validation' else 'slice.html' if view=='cfd_slice' and (folder/'slice.html').is_file() else 'results.html'
                candidate=folder/name
                if not candidate.is_file():candidate=folder/'report.html'
                return candidate
            if view in {"geometry", "mesh"}:
                if view=='geometry' and job['kind']=='cfd_mesh' and (directory/'preview-body.html').is_file():return directory/'preview-body.html'
                relative = "modal/mode-1.html" if job["kind"] == "modal" else "thermal/results.html" if job["kind"] == "thermal" else "solve/results.html" if job["kind"] == "solve" else "preview.html"
                candidate = directory / relative
                if candidate.is_file():
                    return candidate
        return None

    def get_results(self, project_id: str) -> dict:
        project = self.get_project(project_id)
        for job in self.list_jobs(project_id,kinds=['solve'],status="completed"):
            if job_is_current(job, project) and job["kind"] == "solve" and job["status"] == "completed":
                return {"job_id": job["id"], "summary": job["result"],
                        "artifacts": {name: str(self.job_directory(job["id"]) / "solve" / name)
                                      for name in ("results.html", "results.vtk", "model.frd", "manifest.json")}}
        raise ValueError("No completed solve for the current project inputs")

    def get_convergence_results(self, project_id: str) -> dict:
        project = self.get_project(project_id)
        for job in self.list_jobs(project_id,kinds=['convergence'],status="completed"):
            if job_is_current(job, project) and job["kind"] == "convergence" and job["status"] == "completed":
                directory = self.job_directory(job["id"]) / "convergence"
                return {"job_id": job["id"], "summary": job["result"],
                        "artifacts": {name: str(directory / name) for name in ("report.html", "convergence.json", "convergence.csv")},
                        "meshes": [{"mesh": level["level"], "tetrahedra": level["tetrahedra"], "viewer": str(directory / level["viewer"])}
                                   for level in job["result"]["levels"]]}
        raise ValueError("No completed convergence study for the current project inputs")

    def get_cfd_results(self, project_id: str) -> dict:
        project = self.get_project(project_id)
        for job in self.list_jobs(project_id,kinds=['cfd', 'cfd_validation'],status="completed"):
            if job_is_current(job, project) and job['kind'] in {'cfd', 'cfd_validation'} and job['status'] == 'completed':
                directory = self.job_directory(job['id']) / job['kind']
                return {'job_id': job['id'], 'summary': job['result'], 'artifacts': {
                    name: str(directory/name) for name in ('report.html', 'plot.png', 'data.csv', 'flow.npz', 'manifest.json', 'report.json', 'results.html','slice.html','results.vtk','history.csv','solver.log') if (directory/name).is_file()
                }}
        raise ValueError('No completed CFD study for the current project inputs')

    def get_thermal_results(self, project_id: str) -> dict:
        project = self.get_project(project_id)
        for job in self.list_jobs(project_id,kinds=['thermal'],status="completed"):
            if job_is_current(job, project) and job["kind"] == "thermal" and job["status"] == "completed":
                directory = self.job_directory(job["id"]) / "thermal"
                return {"job_id": job["id"], "summary": job["result"], "artifacts": {name: str(directory / name)
                        for name in ("thermal.npz", "results.html", "results.vtk", "temperatures.csv", "model.frd", "manifest.json")}}
        raise ValueError("No completed thermal solve for the current project inputs")

    def get_modal_results(self, project_id: str) -> dict:
        project = self.get_project(project_id)
        for job in self.list_jobs(project_id,kinds=['modal'],status="completed"):
            if job_is_current(job, project) and job["kind"] == "modal" and job["status"] == "completed":
                directory = self.job_directory(job["id"]) / "modal"
                return {"job_id": job["id"], "summary": job["result"],
                        "artifacts": {name: str(directory / name) for name in ("modes.npz", "model.frd", "manifest.json")},
                        "modes": [{"mode": index, "frequency_Hz": frequency, "viewer": str(directory / f"mode-{index}.html"),
                                   "vtk": str(directory / f"mode-{index}.vtk")}
                                  for index, frequency in enumerate(job["result"]["frequencies_Hz"], start=1)]}
        raise ValueError("No completed modal solve for the current project inputs")
