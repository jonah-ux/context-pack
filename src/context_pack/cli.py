import argparse,hashlib,json,pathlib

def main(argv=None):
 p=argparse.ArgumentParser(prog='context-pack'); p.add_argument('command',choices=['build']); p.add_argument('root',nargs='?',default='.'); p.add_argument('--max-bytes',type=int,default=12000); p.add_argument('--out',default='context-pack.md'); a=p.parse_args(argv)
 root=pathlib.Path(a.root).resolve(); files=[]; total=0
 for f in sorted(root.rglob('*')):
  if not f.is_file() or any(x in f.parts for x in ('.git','__pycache__','node_modules')): continue
  b=f.read_bytes()
  if total+len(b)>a.max_bytes: continue
  try: text=b.decode()
  except UnicodeDecodeError: continue
  files.append((f.relative_to(root).as_posix(),text)); total+=len(b)
 body='\n\n'.join(f'## {n}\n\n```text\n{t}\n```' for n,t in files); out={'schema':'context-pack/v1','root':str(root),'files':[n for n,_ in files],'bytes':total,'sha256':hashlib.sha256(body.encode()).hexdigest()}; pathlib.Path(a.out).write_text('# Context pack\n\n'+body+'\n'); print(json.dumps(out,indent=2,sort_keys=True)); return 0
