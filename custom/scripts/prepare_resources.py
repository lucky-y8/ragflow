from pathlib import Path
import os, json, subprocess, concurrent.futures, zipfile
ROOT=Path(__file__).resolve().parents[2]
LOCAL=ROOT/'.local-dev'
ENV=dict(os.environ,**json.loads((LOCAL/'config/runtime.json').read_text()))
def fetch(url,target):
 target=Path(target);target.parent.mkdir(parents=True,exist_ok=True)
 if target.exists() and target.stat().st_size>0:return
 subprocess.run(['curl','-fsSL','--retry','3','--connect-timeout','15','--max-time','600','-o',str(target)+'.part',url],env=ENV,check=True)
 Path(str(target)+'.part').replace(target)
 print('downloaded',target.name,flush=True)
def files(repo):
 raw=subprocess.check_output(['curl','-fsSL','--retry','3','--max-time','60','https://huggingface.co/api/models/'+repo],env=ENV)
 return [x['rfilename'] for x in json.loads(raw)['siblings']]
def main():
 tasks=[]
 for repo in ['InfiniFlow/deepdoc','InfiniFlow/text_concat_xgb_v1.0']:
  for name in files(repo):
   if name.endswith(('.onnx','.res','.model')):
    tasks.append((f'https://huggingface.co/{repo}/resolve/main/{name}?download=true',ROOT/'rag/res/deepdoc'/name))
 tasks.extend([
 ('https://repo1.maven.org/maven2/org/apache/tika/tika-server-standard/3.3.0/tika-server-standard-3.3.0.jar',ROOT/'ragflow_deps/tika-server-standard-3.3.0.jar'),
 ('https://repo1.maven.org/maven2/org/apache/tika/tika-server-standard/3.3.0/tika-server-standard-3.3.0.jar.md5',ROOT/'ragflow_deps/tika-server-standard-3.3.0.jar.md5'),
 ('https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken',ROOT/'ragflow_deps/cl100k_base.tiktoken')])
 for category,name in [('corpora','wordnet'),('corpora','omw-1.4'),('tokenizers','punkt'),('tokenizers','punkt_tab')]:
  tasks.append((f'https://raw.githubusercontent.com/nltk/nltk_data/gh-pages/packages/{category}/{name}.zip',ROOT/'ragflow_deps/nltk_data'/category/(name+'.zip')))
 with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
  jobs=[pool.submit(fetch,*args) for args in tasks]
  for job in jobs:job.result()
 for archive in (ROOT/'ragflow_deps/nltk_data').rglob('*.zip'):
  with zipfile.ZipFile(archive) as z:z.extractall(archive.parent)
 print('Runtime models, NLTK and Tika ready',flush=True)
if __name__=='__main__':main()
