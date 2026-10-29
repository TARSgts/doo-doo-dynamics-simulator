import json
import time
import numpy as np
import pytest
from opensim.cfd_parameters import CFD_DEFAULTS
from opensim.geometry import make_box,import_and_mesh
from opensim.flow_preview import flow_preview_data
from opensim.results import write_viewer_data


def test_preview_records_preserve_actual_outward_boundary_geometry(tmp_path):
    cad=tmp_path/'duct.step';make_box(cad,(1.,.6,.4))
    mesh=import_and_mesh(cad,.2,1.,tmp_path/'mesh.msh')
    preview=flow_preview_data(mesh,CFD_DEFAULTS)
    records=np.array(preview['boundaries'])
    # Area vectors form a closed boundary; inlet normals point out of the volume.
    np.testing.assert_allclose(records[:,4:].sum(0),0,atol=1e-12)
    inlet=records[np.isclose(records[:,1],0)]
    assert len(inlet)>0 and np.all(inlet[:,4]<0)
    assert set(records[:,0])=={int(tag) for tag in mesh.surface_groups}


def test_flow_arrows_update_live_warn_about_tangent_inlet_and_follow_draft_picks(tmp_path):
    import os
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    pytest.importorskip('PySide6')
    from PySide6.QtWidgets import QApplication
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtCore import QUrl
    app=QApplication.instance() or QApplication([])
    cad=tmp_path/'duct.step';make_box(cad,(1.,.6,.4));mesh=import_and_mesh(cad,.2,1.,tmp_path/'mesh.msh')
    settings=CFD_DEFAULTS|{'cfd_backend':'su2','cfd_flow_axis':'x'}
    preview=flow_preview_data(mesh,settings)
    path=tmp_path/'preview.html'
    write_viewer_data(path,{'points':mesh.points.tolist(),'faces':mesh.boundary_faces(),'face_ids':mesh.boundary_face_ids(),
        'displacement':np.zeros_like(mesh.points).tolist(),'velocity_m_s':np.zeros_like(mesh.points).tolist(),
        'pressure_Pa':np.zeros(len(mesh.points)).tolist(),'flow_preview':preview,
        'summary':{'analysis':'cfdcad','view':'mesh'}})
    view=QWebEngineView();view.resize(1000,700);view.show()
    def js(code):
        received=[];view.page().runJavaScript(code,lambda value:received.append(value))
        deadline=time.monotonic()+10
        while not received and time.monotonic()<deadline:app.processEvents();time.sleep(.01)
        assert received,'Viewer JavaScript did not respond'
        return received[0]
    def state():
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            value=js("typeof flowPreviewState==='undefined'?'':JSON.stringify(flowPreviewState)")
            if value:
                data=json.loads(value)
                if data['arrows']:return data
            app.processEvents();time.sleep(.02)
        pytest.fail('Flow preview did not initialize')
    try:
        view.setUrl(QUrl.fromLocalFile(str(path)).toString()+'?desktop=1&canvas2d=1')
        first=state();assert first['arrows'] and not first['warnings']
        assert all(a['direction']==[1,0,0] for a in first['arrows'] if a['role']=='Inlet')
        side=next(int(r[0]) for r in preview['boundaries'] if abs(r[2])<1e-9)
        bad=settings|{'cfd_inlet_region':{'faces':[side]}}
        js('setFlowPreview('+json.dumps(bad)+');updateFlowPreview();')
        assert any('does not face' in warning for warning in state()['warnings'])
        fixed=bad|{'cfd_flow_axis':'y','cfd_outlet_region':{}}
        js('setFlowPreview('+json.dumps(fixed)+');updateFlowPreview();')
        assert not state()['warnings']
        assert all(a['direction']==[0,1,0] for a in state()['arrows'] if a['role']=='Inlet')
        # Camera changes do not change the physical setup vectors.
        physical=state()['arrows']
        for camera in ['front','top','isometric']:
            js('setViewOrientation('+json.dumps(camera)+');')
            assert state()['arrows']==physical
        js('setFlowPreview('+json.dumps(settings)+');setFacePicking("support",['+str(side)+']);updateFlowPreview();')
        assert any('does not face' in warning for warning in state()['warnings'])
        js('setFacePicking(null);setFlowPreview('+json.dumps(settings)+');updateFlowPreview();')
        assert not state()['warnings']
    finally:
        view.close();view.setPage(None);view.deleteLater();app.processEvents()
