"""Built-in examples create independent CAD without overwriting a changed project."""
import gmsh
from opensim.geometry import gmsh_session,make_box


def create_example(workspace,job,directory,progress):
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
            (str(cad), job["project_id"], job["revision"], job["id"])).rowcount
    if not updated:
        return None  # A stopped example must not overwrite newly imported geometry.

    return cad
