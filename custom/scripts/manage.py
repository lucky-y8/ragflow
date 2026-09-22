#!/usr/bin/env python3
"""Manage this checkout's isolated services; no global service configuration."""
from pathlib import Path
import json, os, subprocess, sys, socket, time, urllib.request
ROOT = Path(__file__).resolve().parents[2]
LOCAL = ROOT / '.local-dev'
ENV = dict(os.environ, **json.loads((LOCAL/'config/runtime.json').read_text()))
PYTHON = str(ROOT/'.venv/bin/python')
MYSQL = LOCAL/'tools/mysql-8.0.40-linux-glibc2.17-x86_64-minimal'
COMMANDS = {
 'mysql': [str(MYSQL/'bin/mysqld'), f'--defaults-file={LOCAL}/config/mysql.cnf'],
 'redis': ['/usr/bin/redis-server', str(LOCAL/'config/redis.conf')],
 'minio': ['/home/yanilo/.local/bin/minio', 'server', str(LOCAL/'data/minio'), '--address', '127.0.0.1:19000', '--console-address', '127.0.0.1:19001'],
 'elasticsearch': [str(LOCAL/'tools/elasticsearch-8.11.3/bin/elasticsearch')],
 'api': [PYTHON, 'api/ragflow_server.py'],
 'admin': [PYTHON, 'admin/server/admin_server.py'],
 'worker': [PYTHON, 'rag/svr/task_executor.py', '-i', '0'],
 'web': ['/home/yanilo/.nvm/versions/node/v22.23.2/bin/npm', 'run', 'dev', '--', '--host', '127.0.0.1', '--strictPort'],
}
PORTS = {'mysql':13306, 'redis':16379, 'minio':19000, 'elasticsearch':19200, 'api':9380, 'admin':9381, 'web':9222}
DEPS = ['mysql','redis','minio','elasticsearch']
def run(cmd, **kw):
 return subprocess.run(cmd, cwd=ROOT, env=ENV, check=True, **kw)
def active(name):
 return subprocess.run(['systemctl','--user','is-active','--quiet',f'ragflow-local-{name}.service']).returncode == 0
def wait_port(name, timeout=120):
 deadline=time.monotonic()+timeout
 while time.monotonic()<deadline:
  if not active(name): raise RuntimeError(f'{name} stopped: see {LOCAL}/logs/{name}.log')
  try:
   with socket.create_connection(('127.0.0.1',PORTS[name]),timeout=1): return
  except OSError: time.sleep(1)
 raise RuntimeError(f'{name} did not listen on {PORTS[name]} within {timeout}s')
def start(name):
 if active(name): return
 subprocess.run(['systemctl','--user','reset-failed',f'ragflow-local-{name}.service'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 cmd=['systemd-run','--user','--collect',f'--unit=ragflow-local-{name}',f'--working-directory={ROOT / "web" if name=="web" else ROOT}',f'--property=EnvironmentFile={LOCAL}/config/runtime.env',f'--property=StandardOutput=append:{LOCAL}/logs/{name}.log',f'--property=StandardError=append:{LOCAL}/logs/{name}.log','--property=TimeoutStopSec=45','--property=UMask=0077','--']+COMMANDS[name]
 run(cmd)
 if name in PORTS:wait_port(name)
 print(f'{name} started',flush=True)
def dependencies():
 for name in DEPS:start(name)
 opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
 with opener.open('http://127.0.0.1:19200/_cluster/health?wait_for_status=yellow&timeout=60s',timeout=65) as r:
  if json.load(r).get('timed_out'):raise RuntimeError('Elasticsearch not ready')
def migrate():
 run([PYTHON,'-c','from api.db.db_models import init_database_tables; init_database_tables()'])
 run(['bash','tools/scripts/run_migrations.sh','--config',str(ROOT/'conf/local.service_conf.yaml')],stdout=(LOCAL/'logs/migrations.log').open('a'),stderr=subprocess.STDOUT)
def main():
 action=sys.argv[1] if len(sys.argv)>1 else 'status'
 if action=='deps':dependencies()
 elif action=='start':
  dependencies();migrate()
  for name in ['api','admin','worker','web']:start(name)
  print('RAGFlow: http://localhost:9222')
 elif action=='stop':
  for name in reversed(list(COMMANDS)):
   subprocess.run(['systemctl','--user','stop',f'ragflow-local-{name}.service'],stderr=subprocess.DEVNULL)
 elif action=='status':
  for name in COMMANDS: print(f'{name:14} {"running" if active(name) else "stopped":8} {PORTS.get(name, "")}')
 elif action=='logs' and len(sys.argv)==3 and sys.argv[2] in COMMANDS:
  run(['tail','-n','80','-f',str(LOCAL/'logs'/f'{sys.argv[2]}.log')])
 else:raise SystemExit('Usage: custom/scripts/manage.py {deps|start|stop|status|logs SERVICE}')
if __name__=='__main__':main()
