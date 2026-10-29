"""Surface and true tetrahedron/plane intersections for the main CFD viewport."""
from pathlib import Path
import numpy as np
from opensim.results import write_viewer_data


def clip_polygon(values,axis,bound,keep_above):
    """Clip a slice polygon while preserving its linearly interpolated fields."""
    result=[]
    for previous,current in zip(values[-1:]+values[:-1],values):
        a,b=previous[0][axis]-bound,current[0][axis]-bound
        inside_a=a>=0 if keep_above else a<=0
        inside_b=b>=0 if keep_above else b<=0
        if inside_a!=inside_b:
            weight=a/(a-b)
            result.append(tuple(x+weight*(y-x) for x,y in zip(previous,current)))
        if inside_b:result.append(current)
    return result


def surface_view(path,points,faces,velocity,pressure,summary,face_ids=None):
    used=np.unique(faces);inverse=np.full(len(points),-1,dtype=int);inverse[used]=np.arange(len(used))
    write_viewer_data(Path(path),{'points':points[used].tolist(),'faces':inverse[np.array(faces)].tolist(),
        'face_ids':face_ids or [0]*len(faces),'displacement':np.zeros((len(used),3)).tolist(),
        'velocity_m_s':velocity[used].tolist(),'pressure_Pa':pressure[used].tolist(),'summary':summary})


def write_flow_views(directory,mesh,velocity,pressure,summary,groups):
    directory=Path(directory)
    faces=groups['wall'] if summary.get('domain',{}).get('mode')=='external' else mesh.boundary_faces()
    ids={tuple(sorted(f[:3])):int(tag) for tag,ff in mesh.surface_groups.items() for f in ff}
    surface_view(directory/'results.html',mesh.points,faces,velocity,pressure,summary,[ids.get(tuple(sorted(f[:3])),0) for f in faces])
    normal=1 if summary.get('flow_axis','x')!='y' else 0
    body=summary.get('domain',{}).get('body_bounds_m')
    plane=float(np.mean(np.array(body)[:,normal])) if body else float(np.mean([mesh.points[:,normal].min(),mesh.points[:,normal].max()]))
    signed=mesh.points[:,normal]-plane;t=mesh.tetrahedra
    candidates=np.flatnonzero((signed[t].min(1)<=0)&(signed[t].max(1)>=0))
    points=[];vel=[];pr=[];triangles=[]
    edges=((0,1),(0,2),(0,3),(1,2),(1,3),(2,3))
    axes=[a for a in range(3) if a!=normal]
    for element in t[candidates]:
        polygon={}
        for a,b in edges:
            i,j=element[a],element[b];si,sj=signed[i],signed[j]
            if si*sj>0 or abs(si-sj)<1e-20:continue
            weight=si/(si-sj);point=mesh.points[i]+weight*(mesh.points[j]-mesh.points[i])
            polygon[tuple(np.round(point,13))]=(point,velocity[i]+weight*(velocity[j]-velocity[i]),pressure[i]+weight*(pressure[j]-pressure[i]))
        if len(polygon)<3:continue
        values=list(polygon.values());center=np.mean([v[0] for v in values],axis=0)
        values.sort(key=lambda v:np.arctan2(v[0][axes[1]]-center[axes[1]],v[0][axes[0]]-center[axes[0]]))
        if body:
            low,high=np.array(body);padding=summary['domain']['body_span_m']
            for axis in axes:
                values=clip_polygon(values,axis,low[axis]-padding,True)
                values=clip_polygon(values,axis,high[axis]+padding,False)
            if len(values)<3:continue
        first=len(points)
        for point,u,p in values:points.append(point);vel.append(u);pr.append(p)
        for i in range(1,len(values)-1):triangles.append([first,first+i,first+i+1])
    if triangles:
        # Add the actual solid wall to the slice; no triangles are invented inside the solid.
        offset=len(points);points.extend(mesh.points);vel.extend(velocity);pr.extend(pressure)
        triangles.extend((np.array(groups['wall'])+offset).tolist())
        surface_view(directory/'slice.html',np.array(points),triangles,np.array(vel),np.array(pr),summary|{'display':'Near-model fluid center slice + solid walls' if body else 'Fluid center slice + solid walls'})
