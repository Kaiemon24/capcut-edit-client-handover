#!/usr/bin/env python3
"""Portable preview-first installation; no overwrite, network or automatic OS-route edits."""
from pathlib import Path,PurePosixPath
import argparse,hashlib,json,stat,sys
GROUPS={'AI Automation','Visual','Content','Research','Documents','Business'}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def relative(value):
 p=PurePosixPath(value)
 if p.is_absolute()or not p.parts or any(x in ['..','.','']or ':'in x or '\\'in x for x in p.parts):raise ValueError('Unsafe relative path')
 return p
def no_links(p):
 for x in[p,*p.parents]:
  if x.exists()and(x.is_symlink()or getattr(x.lstat(),'st_file_attributes',0)&getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',1024)):raise ValueError('Linked source/target refused')
def route(source,dest,layout):
 s=relative(source);d=relative(dest)
 if s.parts[:2]==('source','skill')and len(s.parts)>3:
  name=s.parts[2];suffix='/'.join(s.parts[3:]);native='.agents/skills/'+name+'/'+suffix
  legacy_prefix='.codex/skills/'
  if dest!=native and not(dest.startswith(legacy_prefix)and len(d.parts)>4 and d.parts[2]in GROUPS and d.parts[3]==name and '/'.join(d.parts[4:])==suffix):raise ValueError('Undeclared skill route')
  if layout=='codex':return native
  if dest.startswith(legacy_prefix):return dest
  raise ValueError('Custom OS layout requires explicitly declared semantic group; inspect client OS first')
 if s.parts[:2]==('source','html-ui')and len(s.parts)>3:
  name=s.parts[2];suffix='/'.join(s.parts[3:]);allowed=['Application/'+name+'/'+suffix,'.codex/tool/HTML/'+name+'/'+suffix,'Brand asset/'+name+'/Design system/'+suffix]
  if dest not in allowed:raise ValueError('Undeclared HTML/brand route')
  return dest
 raise ValueError('Unknown source route')
def plan_actions(package_root,target_root,manifest,layout='codex'):
 checks={x[66:]:x[:64]for x in(package_root/'checksums.sha256').read_text(encoding='utf-8').splitlines()if len(x)>66};items=[]
 if 'installFiles'in manifest:items=manifest['installFiles']
 else:
  for t in manifest.get('installTargets',[]):
   src=package_root.joinpath(*relative(t['sourcePath']).parts);no_links(src)
   if not src.is_dir():raise ValueError('Missing declared source folder')
   for p in sorted(src.rglob('*')):
    no_links(p)
    if p.is_file():
     rel=p.relative_to(package_root).as_posix();suffix=p.relative_to(src).as_posix();items.append(dict(source=rel,target=t['targetPath']+'/'+suffix,sha256=checks.get(rel)))
 if not items:raise ValueError('Empty install inventory')
 result=[];seen=set()
 for x in items:
  src=package_root.joinpath(*relative(x['source']).parts);dest=route(x['source'],x['target'],layout);dst=target_root.joinpath(*relative(dest).parts);no_links(src);no_links(dst)
  if not src.resolve().is_relative_to(package_root)or not dst.resolve().is_relative_to(target_root):raise ValueError('Route escape')
  if not src.is_file()or sha(src)!=x['sha256']or checks.get(x['source'])!=x['sha256']:raise ValueError('Source/manifest/checksum mismatch')
  if dest.casefold()in seen:raise ValueError('Duplicate target')
  seen.add(dest.casefold());status='CREATE'if not dst.exists()else'UNCHANGED'if dst.is_file()and sha(dst)==x['sha256']else'CONFLICT';result.append(dict(source=x['source'],target=dest,sha256=x['sha256'],status=status))
 return result
def main(argv=None):
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--target-root',required=True);p.add_argument('--skill-layout',choices=['codex','kai-os'],default='codex');p.add_argument('--preview',action='store_true');p.add_argument('--apply',action='store_true');p.add_argument('--confirm',action='store_true');a=p.parse_args(argv)
 if a.preview and a.apply:raise ValueError('Choose preview or apply')
 root=Path(__file__).resolve().parents[1];target=Path(a.target_root).expanduser();no_links(target)
 if not target.is_absolute()or not target.is_dir():raise ValueError('Choose an existing absolute client workspace')
 target=target.resolve();no_links(root)
 if target.is_relative_to(root):raise ValueError('Target cannot be inside package')
 manifest=json.loads((root/'manifest.json').read_text(encoding='utf-8'));rows=plan_actions(root,target,manifest,a.skill_layout);state=dict(schema='client-install-preview/v2',manifestSha256=sha(root/'manifest.json'),checksumSha256=sha(root/'checksums.sha256'),targetRoot=str(target),skillLayout=a.skill_layout,files=rows,conflicts=sum(x['status']=='CONFLICT'for x in rows));preview=root/'installer/install-preview.json'
 if not a.apply:
  preview.write_text(json.dumps(state,ensure_ascii=False,indent=2),'utf-8');(root/'installer/install-preview.md').write_text('# Install preview\n\nTarget: '+str(target)+'\n\nNo target files changed. OS routing is a separate agent-guided client decision.\n\n| Action | Target |\n|---|---|\n'+'\n'.join('| '+x['status']+' | '+x['target']+' |'for x in rows)+'\n','utf-8');print(json.dumps(dict(preview=True,conflicts=state['conflicts'],files=len(rows))));return 1 if state['conflicts']else 0
 if not a.confirm or not preview.is_file()or json.loads(preview.read_text(encoding='utf-8'))!=state:raise ValueError('Exact current preview and client confirmation required')
 if state['conflicts']:raise ValueError('Existing foreign content retained; plan upgrade separately')
 created=[]
 try:
  for x in rows:
   if x['status']!='CREATE':continue
   src=root.joinpath(*relative(x['source']).parts);dst=target.joinpath(*relative(x['target']).parts);no_links(dst);data=src.read_bytes()
   if hashlib.sha256(data).hexdigest()!=x['sha256']:raise ValueError('Source changed')
   dst.parent.mkdir(parents=True,exist_ok=True);no_links(dst.parent)
   with dst.open('xb')as f:f.write(data)
   created.append(x)
   if sha(dst)!=x['sha256']:raise ValueError('Destination changed')
  for x in rows:
   if sha(target.joinpath(*relative(x['target']).parts))!=x['sha256']:raise ValueError('Final readback mismatch')
 except (OSError,ValueError):
  for x in reversed(created):
   dst=target.joinpath(*relative(x['target']).parts)
   if dst.is_file()and sha(dst)==x['sha256']:no_links(dst);dst.unlink()
  raise
 (root/'installer/install-receipt.json').write_text(json.dumps(state,ensure_ascii=False,indent=2),'utf-8');print(json.dumps(dict(applied=True,created=len(created),unchanged=len(rows)-len(created),destinationHashesVerified=True,osRouting='Not changed; agent/client review required')));return 0
if __name__=='__main__':
 try:sys.exit(main())
 except(OSError,ValueError,KeyError)as e:print(json.dumps(dict(ok=False,error=str(e))));sys.exit(2)
