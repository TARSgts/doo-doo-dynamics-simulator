"""Undeformed boundary geometry for inexpensive, live CFD setup arrows."""
import numpy as np
from opensim.cad_flow import face_geometry
from opensim.loads import boundary_owners


def flow_preview_data(mesh,parameters,domain=None):
    faces=mesh.boundary_elements()
    centers=mesh.points[np.array(faces)[:,:3]].mean(1)
    areas=face_geometry(mesh,faces,boundary_owners(mesh))
    ids={tuple(sorted(f[:3])):int(tag) for tag,ff in mesh.surface_groups.items() for f in ff}
    return {'settings':{key:parameters[key] for key in ('cfd_backend','cfd_flow_axis','cfd_speed_m_s','cfd_pressure_drop_Pa','cfd_inlet_region','cfd_outlet_region')},
            'bounds_m':[mesh.points.min(0).tolist(),mesh.points.max(0).tolist()],
            'domain':domain or {'mode':'fluid'},
            'boundaries':[[ids.get(tuple(sorted(f[:3])),0),*c,*a] for f,c,a in zip(faces,centers,areas)]}
