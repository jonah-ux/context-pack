import tempfile,pathlib
from context_pack.cli import main
with tempfile.TemporaryDirectory() as d:
 root=pathlib.Path(d); (root/'hello.py').write_text('print("hello context")\n'); (root/'README.md').write_text('# tiny project\n')
 print('Context Pack demo: tiny, bounded, deterministic')
 main(['build',str(root),'--max-bytes','2000','--out',str(root/'pack.md')])
