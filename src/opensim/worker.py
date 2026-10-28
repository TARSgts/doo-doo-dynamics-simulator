import argparse
import os
from pathlib import Path
import threading
import time
import traceback

import gmsh
import numpy as np

from opensim.cli import solve
from opensim.geometry import gmsh_session, import_and_mesh, make_box
from opensim.results import write_viewer
from opensim.solver import cancel_active_solvers
from opensim.workspace import Workspace

CANCEL_POLL_SECONDS = 0.3
CANCELLED_EXIT_CODE = 3


def watch_for_cancel(workspace: Workspace, job_id: str, stop: threading.Event, exit_process=os._exit):
    """Poll the shared workspace; when the job is stopped, end CalculiX and this worker.

    Meshing runs inside Gmsh's native code and cannot be interrupted politely,
    so the worker process exits immediately instead of waiting for it.
    """
    while not stop.wait(CANCEL_POLL_SECONDS):
        try:
            status = workspace.get_job(job_id)["status"]
        except Exception:
            continue  # A briefly locked database must not kill a healthy job.
        if status == "cancelled":
            killed = cancel_active_solvers()
            print(f"Stop requested; ended {killed} solver process(es) and exiting worker.", flush=True)
            exit_process(CANCELLED_EXIT_CODE)
            return


def execute(workspace: Workspace, job_id: str):
    job = workspace.get_job(job_id)
    directory = workspace.job_directory(job_id)
    parameters = job["payload"]["parameters"]
    with workspace.connect() as connection:
        started = connection.execute("UPDATE jobs SET status='running',updated=? WHERE id=? AND status='queued'",
                                     (time.time(), job_id)).rowcount
    if not started:
        print("Job was stopped before the worker started.", flush=True)
        return
    stop_watching = threading.Event()
    threading.Thread(target=watch_for_cancel, args=(workspace, job_id, stop_watching), daemon=True).start()
    try:
        def progress(stage):
            workspace.set_job_progress(job_id, stage)
        progress("starting")
        cad = Path(job["payload"]["cad"]) if job["payload"]["cad"] else None
        if job["kind"] == "example":
            progress("creating")
            cad = directory / ("heat-sink.step" if job['payload']['example'] == 'heat_sink' else "test-object.step")
            if job['payload']['example'] == 'heat_sink':
                from opensim.heat_sink import make_heat_sink
                make_heat_sink(cad)
            elif job["payload"]["example"] == "cantilever_beam":
                make_box(cad, (1.0, 0.02, 0.02))
            elif job["payload"]["example"] == "axial_bar":
                make_box(cad, (0.1, 0.02, 0.02))
            else:
                with gmsh_session():
                    gmsh.model.add("perforated_plate")
                    plate = gmsh.model.occ.addBox(0, 0, 0, 0.1, 0.04, 0.005)
                    hole = gmsh.model.occ.addCylinder(0.05, 0.02, -0.001, 0, 0, 0.007, 0.006)
                    gmsh.model.occ.cut([(3, plate)], [(3, hole)])
                    gmsh.model.occ.synchronize()
                    gmsh.write(str(cad))
            with workspace.connect() as connection:
                updated = connection.execute(
                    "UPDATE projects SET cad=? WHERE id=? AND revision=? AND EXISTS (SELECT 1 FROM jobs WHERE id=? AND status='running')",
                    (str(cad), job["project_id"], job["revision"], job_id)).rowcount
            if not updated:
                return  # A stopped example must not overwrite a newly imported model.
        if job['kind'] == 'cfd_validation':
            from opensim.cfd_validation import run_cfd_validation
            result = run_cfd_validation(directory / 'cfd_validation', progress=progress)
        elif job['kind'] == 'cfd':
            from opensim.cfd import run_cfd
            result = run_cfd(directory / 'cfd', parameters, progress=progress)
        elif job["kind"] == "thermal":
            from opensim.thermal import solve_thermal
            result = solve_thermal(cad, directory / "thermal", size=parameters["mesh_size_m"], scale=parameters["cad_scale"],
                                   order=parameters["element_order"], parameters=parameters, progress=progress)
        elif job["kind"] == "modal":
            from opensim.modal import solve_modal
            result = solve_modal(cad, directory / "modal", size=parameters["mesh_size_m"],
                                 scale=parameters["cad_scale"], young=parameters["young_Pa"],
                                 poisson=parameters["poisson"], density=parameters["density_kg_m3"],
                                 mode_count=parameters["mode_count"], order=parameters["element_order"], support_region=parameters["support_region"], progress=progress)
        elif job["kind"] == "convergence":
            from opensim.convergence import run_convergence
            result = run_convergence(cad, directory / "convergence", size=parameters["mesh_size_m"],
                                     scale=parameters["cad_scale"], young=parameters["young_Pa"], poisson=parameters["poisson"],
                                     load=parameters["load_N"], order=parameters["element_order"], load_axis=parameters["load_axis"],
                                     load_kind=parameters["load_kind"], load_surface=parameters["load_surface"],
                                     support_region=parameters["support_region"], load_region=parameters["load_region"],
                                     levels=int(parameters["convergence_levels"]), ratio=parameters["convergence_ratio"],
                                     tolerance_percent=parameters["convergence_tolerance_percent"],
                                     target=parameters["convergence_target"], progress=progress)
        elif job["kind"] == "solve":
            result = solve(cad, directory / "solve", size=parameters["mesh_size_m"],
                           scale=parameters["cad_scale"], young=parameters["young_Pa"],
                           poisson=parameters["poisson"], load=parameters["load_N"], order=parameters["element_order"],
                           load_axis=parameters["load_axis"], load_kind=parameters["load_kind"], load_surface=parameters["load_surface"],
                           support_region=parameters["support_region"], load_region=parameters["load_region"], progress=progress)
        else:
            progress("meshing")
            mesh = import_and_mesh(cad, parameters["mesh_size_m"], parameters["cad_scale"], directory / "mesh.msh",
                                   order=parameters["element_order"], tip_point=parameters["load_kind"] == "point" and job['payload'].get('study') != 'thermal')
            result = {"nodes": len(mesh.points), "tetrahedra": len(mesh.tetrahedra), "view": "mesh",
                      "mesh_repair": mesh.repair_report,
                      "cad_faces": mesh.surface_catalog(),
                      "element_type": mesh.element_type,
                      "bounds_m": [mesh.points.min(axis=0).tolist(), mesh.points.max(axis=0).tolist()]}
            progress("exporting")
            write_viewer(directory / "preview.html", mesh, np.zeros_like(mesh.points), result)
        workspace.finish_job(job_id, result=result)
    except Exception as error:
        traceback.print_exc()
        workspace.finish_job(job_id, error=str(error))
    finally:
        stop_watching.set()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--job", required=True)
    arguments = parser.parse_args()
    execute(Workspace(arguments.workspace), arguments.job)


if __name__ == "__main__":
    main()
