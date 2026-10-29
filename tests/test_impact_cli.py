import json
import subprocess
import sys
from pathlib import Path


def test_drop_cli_creates_report_and_rejects_unknown_settings(tmp_path):
    settings=tmp_path/'drop.json';settings.write_text(json.dumps({'impact_duration_s':.005,'impact_modes':1}))
    result=subprocess.run([sys.executable,'-m','opensim.cli','impact','--parameters',str(settings),'--out',str(tmp_path/'run')],capture_output=True,text=True,timeout=45)
    assert result.returncode==0,result.stdout+result.stderr
    assert json.loads(result.stdout)['analysis']=='impact'
    assert (tmp_path/'run/report.html').is_file()
    settings.write_text('{"unknown":1}')
    bad=subprocess.run([sys.executable,'-m','opensim.cli','impact','--parameters',str(settings),'--out',str(tmp_path/'bad')],capture_output=True,text=True,timeout=15)
    assert bad.returncode and not (tmp_path/'bad').exists()
