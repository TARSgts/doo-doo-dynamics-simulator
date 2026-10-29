"""Cross-study dependencies, legacy snapshots and scalable history reads."""
import importlib
import json
import sqlite3
import time
import uuid
import pytest
from opensim.application.studies import STUDIES,input_signature,input_values
from opensim.workspace import Workspace,DEFAULT_PARAMETERS


def completed(w,pid,kind,*,parameters=None,payload=True):
    project=w.get_project(pid);jid=uuid.uuid4().hex;now=time.time()
    data={'cad':project['cad'],'parameters':parameters or project['parameters'],'study':{'solve':'static'}.get(kind,kind)} if payload else {}
    summary={'mode_count':1,'frequencies_Hz':[100.]}
    with w.connect() as con:
        con.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?)',(jid,pid,kind,'completed',project['revision'],json.dumps(data),json.dumps(summary),None,now,now))
    return w.get_job(jid)


@pytest.mark.parametrize('changes,stale',[
    ({'cfd_speed_m_s':20.},{'cfd'}),
    ({'thermal_conductivity_W_mK':20.},{'thermal'}),
    ({'load_N':50.},{'solve','convergence'}),
    ({'mode_count':8},{'modal'}),
    ({'density_kg_m3':1000.},{'modal'}),
    ({'young_Pa':70e9},{'solve','modal','convergence'}),
    ({'convergence_tolerance_percent':5.},{'convergence'}),
    ({'mesh_size_m':.003},{'solve','modal','thermal','convergence'}),
    ({'cfd_mesh_size_m':.003},{'cfd'}),
    ({'material_name':'A different display label'},set()),
    ({'impact_drop_height_m':.005},set()),
])
def test_only_dependent_studies_become_stale(tmp_path,changes,stale):
    w=Workspace(tmp_path);pid=w.create_project('Independent studies')['id']
    w.set_parameters(pid,{'cfd_case':'cad','cfd_backend':'su2','cfd_domain_mode':'external'})
    jobs=[completed(w,pid,kind) for kind in ('solve','modal','thermal','convergence','cfd')]
    w.set_parameters(pid,changes)
    assert {job['kind'] for job in jobs if not w.job_is_current(job)}==stale
    # Reopening a preexisting workspace preserves the same validity decisions.
    reopened=Workspace(tmp_path)
    assert {job['kind'] for job in reopened.list_jobs(pid) if not reopened.job_is_current(job)}==stale


def test_geometry_replacement_invalidates_real_studies_but_keeps_reference_checks(tmp_path):
    w=Workspace(tmp_path/'ws');pid=w.create_project('Geometry')['id'];cad=tmp_path/'part.step';cad.write_text('first')
    w.import_cad(pid,str(cad));w.set_parameters(pid,{'cfd_case':'cad','cfd_backend':'su2','cfd_domain_mode':'external'})
    jobs=[completed(w,pid,kind) for kind in ('solve','modal','thermal','cfd','cfd_validation')]
    cad.write_text('second');w.import_cad(pid,str(cad))
    assert {j['kind'] for j in jobs if w.job_is_current(j)}=={'cfd_validation'}


def test_relevant_input_change_can_restore_a_saved_result(tmp_path):
    w=Workspace(tmp_path);pid=w.create_project('Restore')['id'];job=completed(w,pid,'solve')
    w.set_parameters(pid,{'load_N':10.});assert not w.job_is_current(job)
    w.set_parameters(pid,{'load_N':1000.});assert w.job_is_current(job)
    assert w.get_results(pid)['job_id']==job['id']


def test_unused_inputs_and_numeric_representation_do_not_change_signature():
    p=DEFAULT_PARAMETERS|{'load_cases':[{'kind':'force','components_N':[1,2,0]}]}
    assert input_signature('static','cad.step',p)==input_signature('static','cad.step',p|{'load_N':500.,'density_kg_m3':1000.})
    assert input_signature('modal',None,DEFAULT_PARAMETERS)==input_signature('modal',None,DEFAULT_PARAMETERS|{'element_order':1.})
    assert 'load_N' not in input_values('modal',DEFAULT_PARAMETERS)
    assert 'young_Pa' not in input_values('thermal',DEFAULT_PARAMETERS)


def test_history_is_one_query_and_supports_pagination_and_filters(tmp_path,monkeypatch):
    w=Workspace(tmp_path);pid=w.create_project('History')['id']
    for kind in ('solve','modal','thermal','cfd'):completed(w,pid,kind)
    queries=[];original=w.connect
    def traced():
        connection=original();connection.set_trace_callback(queries.append);return connection
    monkeypatch.setattr(w,'connect',traced)
    jobs=w.list_jobs(pid,limit=2,offset=1)
    assert len(jobs)==2 and len([q for q in queries if q.startswith('SELECT')])==1
    assert all(j['kind']=='modal' for j in w.list_jobs(pid,kinds=['modal'],status='completed'))
    for kwargs in ({'limit':0},{'limit':True},{'offset':-1}):
        with pytest.raises(ValueError):w.list_jobs(pid,**kwargs)


def test_legacy_incomplete_job_is_conservative_and_registry_handlers_load(tmp_path):
    w=Workspace(tmp_path);pid=w.create_project('Legacy')['id'];job=completed(w,pid,'solve',payload=False)
    assert w.job_is_current(job)
    w.set_parameters(pid,{'load_N':100.});assert not w.job_is_current(job)
    for study,definition in STUDIES.items():
        module,handler=definition.handler.split(':')
        assert callable(getattr(importlib.import_module(module),handler))
        scoped=w.study_settings(pid,study)
        assert scoped['title']==definition.title and len(scoped['input_signature'])==64


def test_legacy_schema_reopens_without_changing_project_or_history(tmp_path):
    w=Workspace(tmp_path);project=w.create_project('Keep my project');job=completed(w,project['id'],'solve')
    with w.connect() as con:con.execute('DROP TABLE project_studies')
    reopened=Workspace(tmp_path)
    assert reopened.get_project(project['id'])==project
    assert reopened.get_job(job['id'])==job


def test_connection_context_releases_handles_and_rolls_back_failed_changes(tmp_path):
    w=Workspace(tmp_path);project=w.create_project('Original')
    with pytest.raises(RuntimeError):
        with w.connect() as con:
            con.execute('UPDATE projects SET name=? WHERE id=?',('Do not save',project['id']))
            raise RuntimeError('Interrupted edit')
    with pytest.raises(sqlite3.ProgrammingError):con.execute('SELECT 1')
    assert w.get_project(project['id'])['name']=='Original'
