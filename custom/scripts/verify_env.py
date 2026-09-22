from pathlib import Path
import json, os, uuid, io, urllib.request
ROOT=Path(__file__).resolve().parents[2]
LOCAL=ROOT/'.local-dev'
os.environ.update(json.loads((LOCAL/'config/runtime.json').read_text()))
config=json.loads((ROOT/'conf/local.service_conf.yaml').read_text())
import numpy as np, cv2, scipy, xgboost, onnxruntime as ort
print('Python scientific imports:',np.__version__,cv2.__version__,scipy.__version__,xgboost.__version__,ort.__version__,flush=True)
xgboost.DMatrix(np.ones((2,3),dtype=np.float32))
print('XGBoost NumPy input: OK',flush=True)
import mysql.connector
c=config['mysql'];db=mysql.connector.connect(host=c['host'],port=c['port'],user=c['user'],password=c['password'],database=c['name'])
cur=db.cursor();cur.execute('SELECT 1');assert cur.fetchone()==(1,);cur.close();db.close();print('MySQL authentication: OK',flush=True)
from valkey import Valkey
r=Valkey(host='127.0.0.1',port=16379,password=config['redis']['password'],db=1);key='ragflow-env-check:'+uuid.uuid4().hex
r.set(key,'ok',ex=30);assert r.get(key)==b'ok';r.delete(key);print('Redis read/write: OK',flush=True)
from minio import Minio
c=config['minio'];m=Minio(c['host'],access_key=c['user'],secret_key=c['password'],secure=False);bucket='ragflow-env-check-'+uuid.uuid4().hex
m.make_bucket(bucket)
try:
 m.put_object(bucket,'check.txt',io.BytesIO(b'local environment check'),23)
 resp=m.get_object(bucket,'check.txt')
 try:assert resp.read()==b'local environment check'
 finally:resp.close();resp.release_conn()
 m.remove_object(bucket,'check.txt')
finally:m.remove_bucket(bucket)
print('MinIO authenticated read/write: OK',flush=True)
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
with opener.open('http://127.0.0.1:19200/_cluster/health') as resp:assert json.load(resp)['status'] in ['green','yellow']
print('Elasticsearch health: OK',flush=True)
opts=ort.SessionOptions();opts.intra_op_num_threads=2;opts.inter_op_num_threads=1
for name in ['det.onnx','rec.onnx','layout.onnx','tsr.onnx']:
 sess=ort.InferenceSession(str(ROOT/'rag/res/deepdoc'/name),sess_options=opts,providers=['CPUExecutionProvider']);del sess
 print('ONNX model:',name,'OK',flush=True)
print('Environment checks passed',flush=True)
