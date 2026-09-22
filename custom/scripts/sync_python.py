#!/usr/bin/env python3
from pathlib import Path
import json, os, subprocess
root=Path(__file__).resolve().parents[2]
local=root/'.local-dev'
env=dict(os.environ,**json.loads((local/'config/install-env.json').read_text()))
env['UV_PROJECT_ENVIRONMENT']=str(root/'.venv')
subprocess.run([str(local/'tools/uv-x86_64-unknown-linux-gnu/uv'),'sync','--frozen','--project',str(local/'python-project'),'--python','3.13','--no-install-project'],cwd=root,env=env,check=True)
