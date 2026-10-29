"""Resolve registered handlers without importing every solver into the desktop."""
from importlib import import_module
from opensim.application.studies import STUDIES,JOB_STUDIES


def run_job(workspace,job,directory,progress):
    from pathlib import Path
    payload=job['payload'];cad=Path(payload['cad']) if payload.get('cad') else None
    if job['kind']=='example':
        from opensim.execution.examples import create_example
        cad=create_example(workspace,job,directory,progress)
        if cad is None:return None
    if job['kind'] in {'mesh','cfd_mesh','example'}:
        from opensim.execution.meshing import mesh_job
        return mesh_job(job,cad,directory,payload['parameters'],progress)
    path='opensim.execution.analyses:cfd_validation' if job['kind']=='cfd_validation' else STUDIES[JOB_STUDIES[job['kind']]].handler
    module,name=path.split(':')
    return getattr(import_module(module),name)(cad,directory,payload['parameters'],progress)
