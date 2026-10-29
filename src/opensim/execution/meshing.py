"""Meshing and previews shared by background study jobs."""
import numpy as np
from opensim.geometry import import_and_mesh
from opensim.results import write_viewer


def mesh_job(job,cad,directory,parameters,progress):
    progress("meshing")
    domain={}
    if job['kind']=='cfd_mesh':
        from opensim.flow_domain import prepare_flow_mesh
        mesh,domain=prepare_flow_mesh(cad,parameters,directory/'mesh.msh')
    else:
        mesh = import_and_mesh(cad, parameters["mesh_size_m"], parameters["cad_scale"], directory / "mesh.msh",
                               order=parameters["element_order"], tip_point=parameters["load_kind"] == "point" and not parameters['load_cases'] and job['payload'].get('study') != 'thermal')
    result = {"nodes": len(mesh.points), "tetrahedra": len(mesh.tetrahedra), "view": "mesh",
              "mesh_repair": mesh.repair_report,
              "cad_faces": mesh.surface_catalog(),
              "element_type": mesh.element_type,
              "bounds_m": [mesh.points.min(axis=0).tolist(), mesh.points.max(axis=0).tolist()]}
    progress("exporting")
    if job['payload'].get('study')!='thermal' and job['kind']!='cfd_mesh':
        from opensim.load_cases import build_load_preview
        result.update(build_load_preview(mesh,parameters,include_loads=job['payload'].get('study')!='modal'))
    if job['kind']=='cfd_mesh':
        from opensim.results import write_viewer_data
        from opensim.flow_preview import flow_preview_data
        flow_preview=flow_preview_data(mesh,parameters,domain)
        result.update(analysis='cfdcad',limitations='Setup arrows show prescribed inlet flow and outward outlet direction, not solved streamlines. External enclosure side faces are farfield; body surfaces are no-slip walls.')
        write_viewer_data(directory/'preview.html',{'points':mesh.points.tolist(),'faces':mesh.boundary_faces(),'face_ids':mesh.boundary_face_ids(),
            'displacement':np.zeros_like(mesh.points).tolist(),'velocity_m_s':np.zeros_like(mesh.points).tolist(),'pressure_Pa':np.zeros(len(mesh.points)).tolist(),'summary':result,'flow_preview':flow_preview})
        if domain.get('mode')=='external':
            from opensim.su2_flow import boundary_groups
            from opensim.flow_domain import classify_external
            from opensim.flow_results import surface_view
            groups=classify_external(mesh,boundary_groups(mesh,parameters),domain)
            ids={tuple(sorted(f[:3])):int(tag) for tag,ff in mesh.surface_groups.items() for f in ff}
            surface_view(directory/'preview-body.html',mesh.points,groups['wall'],np.zeros_like(mesh.points),np.zeros(len(mesh.points)),result,[ids.get(tuple(sorted(f[:3])),0) for f in groups['wall']],flow_preview)
    else:
        write_viewer(directory / "preview.html", mesh, np.zeros_like(mesh.points), result)

    return result
