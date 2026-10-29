"""Independent simultaneous surface forces (N) and normal pressures (Pa)."""
import numpy as np
from opensim.load_case_parameters import validate_load_cases
from opensim.loads import AppliedLoad, assemble_load


def assemble_load_cases(mesh, cases):
    validate_load_cases(cases)
    total = np.zeros_like(mesh.points)
    parts = []
    for i, item in enumerate(cases):
        if not item.get('enabled',True): continue
        region, surface = item.get('region',{}), item.get('surface','x-max')
        name = item.get('name') or f'Load {i+1}'
        if item['kind']=='pressure':
            # Unit inward force yields area and local directions. Pressure then
            # integrates over the actual selected area; it is never treated as N.
            part = assemble_load(mesh, 1., 'normal-in','traction',surface,region)
            value = item['pressure_Pa']*part.area
            part.forces *= value
            part.face_directions = [v*np.sign(value) for v in part.face_directions]
            label = f'{name}: {item["pressure_Pa"]:g} Pa (positive inward)'
        else:
            vector = np.array(item['components_N'], dtype=float)
            part = None
            for axis, value in zip('xyz',vector):
                if not value: continue
                component = assemble_load(mesh,value,axis,'traction',surface,region)
                if part is None: part = component
                else: part.forces += component.forces
            part.face_directions = [vector/np.linalg.norm(vector) for _ in part.faces]
            label = f'{name}: ({vector[0]:g}, {vector[1]:g}, {vector[2]:g}) N'
        total += part.forces
        parts.append((item,part,label))
    if not parts: raise ValueError('No independent loads selected')
    result = AppliedLoad(total,np.mean([p.centroid for _,p,_ in parts],axis=0),sum(p.area for _,p,_ in parts),[],[])
    result.parts = parts
    result.force_scale = sum(float(np.linalg.norm(p.forces,axis=1).sum()) for _,p,_ in parts)
    return result


def preview_markers(mesh, loading, displacement=None):
    displacement = np.zeros_like(mesh.points) if displacement is None else displacement
    markers = []
    colors = ['#ffbf69','#b28bff','#69d2ff','#ff7d9c','#8ee89f']
    for i, (_,part,label) in enumerate(loading.parts):
        for j in np.linspace(0,len(part.faces)-1,min(18,len(part.faces)),dtype=int):
            face = part.faces[j]
            markers.append({'point_m':mesh.points[face[:3]].mean(0).tolist(),
                            'displacement_m':displacement[face].mean(0).tolist(),
                            'direction':np.asarray(part.face_directions[j]).tolist(),
                            'label':label if j==0 else '', 'color':colors[i%len(colors)], 'load_index':i})
        # Always label at least one arrow, regardless of face-sampling indices.
        markers[-min(18,len(part.faces))]['label'] = label
    return markers


def build_load_preview(mesh,p,include_loads=True):
    from opensim.regions import support_nodes
    result={}
    try:result['support_point_m']=mesh.points[support_nodes(mesh,p['support_region'])].mean(0).tolist()
    except ValueError as error:result.update(support_preview_valid=False,support_preview_warning=str(error))
    if not include_loads:return result
    if p['load_cases']:
        loading=assemble_load_cases(mesh,p['load_cases'])
        result.update(load_cases=p['load_cases'],load_point_m=loading.centroid.tolist(),load_markers=preview_markers(mesh,loading),applied_force_N=loading.forces.sum(0).tolist())
    else:
        try:
            loading=assemble_load(mesh,p['load_N'],p['load_axis'],p['load_kind'],p['load_surface'],p['load_region'])
            markers=[]
            if loading.faces:
                for i in np.linspace(0,len(loading.faces)-1,min(18,len(loading.faces)),dtype=int):
                    markers.append({'point_m':mesh.points[loading.faces[i][:3]].mean(0).tolist(),'direction':np.asarray(loading.face_directions[i]).tolist(),'displacement_m':[0,0,0]})
            else:
                indices=np.flatnonzero(np.linalg.norm(loading.forces,axis=1)>0)
                for node in indices[np.linspace(0,len(indices)-1,min(18,len(indices)),dtype=int)]:
                    vector=loading.forces[node];markers.append({'point_m':mesh.points[node].tolist(),'direction':(vector/np.linalg.norm(vector)).tolist(),'displacement_m':[0,0,0]})
            markers[0]['label']=f"{p['load_N']:g} N total · {p['load_axis']} · {p['load_kind']}"
            result.update(load_point_m=loading.centroid.tolist(),load_markers=markers,load_N=p['load_N'],load_axis=p['load_axis'],load_kind=p['load_kind'])
        except ValueError as error:result['load_preview_warning']=str(error)
    return result
