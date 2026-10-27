import argparse
from pathlib import Path
import time
import traceback

import gmsh
import numpy as np

from opensim.cli import solve
from opensim.geometry import gmsh_session, import_and_mesh, make_box
from opensim.results import write_viewer
from opensim.workspace import Workspace


def execute(workspace: Workspace, job_id: str):
    job = workspace.get_job(job_id)
    directory = workspace.job_directory(job_id)
    parameters = job["payload"]["parameters"]
    with workspace.connect() as connection:
        connection.execute("UPDATE jobs SET status='running',updated=? WHERE id=?", (time.time(), job_id))
    try:
        cad = Path(job["payload"]["cad"]) if job["payload"]["cad"] else None
        if job["kind"] == "example":
            cad = directory / "test-object.step"
            if job["payload"]["example"] == "axial_bar":
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
                connection.execute("UPDATE projects SET cad=? WHERE id=?", (str(cad), job["project_id"]))
        if job["kind"] == "solve":
            result = solve(cad, directory / "solve", size=parameters["mesh_size_m"],
                           scale=parameters["cad_scale"], young=parameters["young_Pa"],
                           poisson=parameters["poisson"], load=parameters["load_N"])
        else:
            mesh = import_and_mesh(cad, parameters["mesh_size_m"], parameters["cad_scale"], directory / "mesh.msh")
            result = {"nodes": len(mesh.points), "tetrahedra": len(mesh.tetrahedra), "view": "mesh",
                      "bounds_m": [mesh.points.min(axis=0).tolist(), mesh.points.max(axis=0).tolist()]}
            write_viewer(directory / "preview.html", mesh, np.zeros_like(mesh.points), result)
        workspace.finish_job(job_id, result=result)
    except Exception as error:
        traceback.print_exc()
        workspace.finish_job(job_id, error=str(error))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--job", required=True)
    arguments = parser.parse_args()
    execute(Workspace(arguments.workspace), arguments.job)


if __name__ == "__main__":
    main()
