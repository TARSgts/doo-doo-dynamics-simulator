"""Build the actual fluid mesh around user solids without replacing their CAD."""
from pathlib import Path
import tempfile
import gmsh
import numpy as np
from opensim.geometry import gmsh_session,import_and_mesh,_mesh_volume,_rebuild_solid_from_surface
from opensim.mesh_import import MESH_SUFFIXES,clean_surface,read_triangles


def geo_box(lo,hi):
    points=[gmsh.model.geo.addPoint(*(lo+(hi-lo)*np.array(v))) for v in
            [(0,0,0),(1,0,0),(1,1,0),(0,1,0),(0,0,1),(1,0,1),(1,1,1),(0,1,1)]]
    edges={}
    def edge(a,b):
        if (b,a) in edges:return -edges[b,a]
        if (a,b) not in edges:edges[a,b]=gmsh.model.geo.addLine(points[a],points[b])
        return edges[a,b]
    surfaces=[]
    for face in [(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]:
        loop=gmsh.model.geo.addCurveLoop([edge(face[i],face[(i+1)%4]) for i in range(4)])
        surfaces.append(gmsh.model.geo.addPlaneSurface([loop]))
    return gmsh.model.geo.addSurfaceLoop(surfaces)


def prepare_flow_mesh(cad,p,output):
    cad=Path(cad);output=Path(output)
    size=p['cfd_mesh_size_m'];scale=p['cfd_cad_scale']
    if p.get('cfd_domain_mode','fluid')=='fluid':
        return import_and_mesh(cad,size,scale,output,order=1),{'mode':'fluid'}
    with gmsh_session(),tempfile.TemporaryDirectory() as scratch:
        gmsh.model.add('fluid_around_user_model')
        surface=cad.suffix.lower() in MESH_SUFFIXES
        if surface:
            points,faces=clean_surface(read_triangles(cad)*scale,cad.name,repair=True)
            _rebuild_solid_from_surface(points,faces,Path(scratch)/'body.stl',size,{'attempts':[]})
        else:
            gmsh.model.occ.importShapes(str(cad.resolve()));gmsh.model.occ.synchronize()
            bodies=gmsh.model.getEntities(3)
            if not bodies:raise ValueError('The imported model needs a closed solid to create surrounding fluid')
            gmsh.model.occ.dilate(bodies,0,0,0,scale,scale,scale);gmsh.model.occ.synchronize()
        bodies=gmsh.model.getEntities(3)
        if not surface:
            # Build tight bounds only after scaling. Gmsh 4.15's Windows OCC
            # bridge can dereference stale triangulations if scaled afterward.
            gmsh.option.setNumber('Geometry.OCCBoundsUseStl',1)
            bounds=np.array([gmsh.model.occ.getBoundingBox(*body) for body in bodies])
            gmsh.option.setNumber('Geometry.OCCBoundsUseStl',0)
        else:bounds=np.array([gmsh.model.getBoundingBox(*body) for body in bodies])
        lo=bounds[:,:3].min(0);hi=bounds[:,3:].max(0);span=float(np.max(hi-lo))
        if span<=0:raise ValueError('Model has zero size')
        axis='xyz'.index(p.get('cfd_flow_axis','x'));padding=p.get('cfd_padding',3.)*span
        lower=lo-padding;upper=hi+padding;upper[axis]+=padding
        if surface:
            body_surfaces=[tag for _,tag in gmsh.model.getBoundary(bodies,oriented=False)]
            gmsh.model.geo.remove(bodies,recursive=False)
            outer=geo_box(lower,upper);inner=gmsh.model.geo.addSurfaceLoop(body_surfaces)
            gmsh.model.geo.addVolume([outer,inner]);gmsh.model.geo.synchronize()
        else:
            box=gmsh.model.occ.addBox(*lower,*(upper-lower))
            volumes,_=gmsh.model.occ.cut([(3,box)],bodies,removeObject=True,removeTool=True)
            gmsh.model.occ.synchronize()
            if not volumes:raise ValueError('Could not subtract the model from its fluid enclosure')
            # Closed disconnected pockets inside a body do not belong to the outside fluid.
            keep=max(volumes,key=lambda v:gmsh.model.occ.getMass(*v))
            gmsh.model.occ.remove([v for v in volumes if v!=keep],recursive=True);gmsh.model.occ.synchronize()
            body_surfaces=[]
            for _,tag in gmsh.model.getBoundary([keep],oriented=False):
                b=gmsh.model.getBoundingBox(2,tag)
                if not any(abs(b[i]-b[i+3])<span*1e-5 and (abs(b[i]-lower[i])<span*1e-5 or abs(b[i]-upper[i])<span*1e-5) for i in range(3)):
                    body_surfaces.append(tag)
        distance=gmsh.model.mesh.field.add('Distance');gmsh.model.mesh.field.setNumbers(distance,'SurfacesList',body_surfaces)
        threshold=gmsh.model.mesh.field.add('Threshold')
        for key,value in {'InField':distance,'SizeMin':size,'SizeMax':max(size,span),'DistMin':span*.15,'DistMax':span*2}.items():gmsh.model.mesh.field.setNumber(threshold,key,value)
        gmsh.model.mesh.field.setAsBackgroundMesh(threshold)
        gmsh.option.setNumber('Mesh.MeshSizeExtendFromBoundary',0)
        gmsh.option.setNumber('Mesh.MeshSizeFromPoints',0)
        mesh=_mesh_volume(size,1,output,max_size=max(size,span))
        if len(mesh.tetrahedra)>500000:raise ValueError('Fluid mesh exceeds 500000 cells; increase the near-model mesh size')
    return mesh,{'mode':'external','body_bounds_m':[lo.tolist(),hi.tolist()],'enclosure_bounds_m':[lower.tolist(),upper.tolist()],
                 'body_span_m':span,'flow_axis':p.get('cfd_flow_axis','x')}


def classify_external(mesh,groups,domain):
    if domain.get('mode')!='external':return groups
    lo,hi=np.array(domain['enclosure_bounds_m']);tol=np.max(hi-lo)*1e-6
    wall=[];far=[]
    for face in groups['wall']:
        points=mesh.points[face]
        outer=any(np.all(abs(points[:,i]-lo[i])<tol) or np.all(abs(points[:,i]-hi[i])<tol) for i in range(3))
        (far if outer else wall).append(face)
    return groups|{'wall':wall,'farfield':far}
