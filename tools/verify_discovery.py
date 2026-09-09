"""Read-only Codex app-server skill discovery; schema checked against local CLI."""
import argparse
import json
import queue
import shutil
import subprocess
import threading
import time
import sys
from pathlib import Path


def main():
    a=argparse.ArgumentParser()
    a.add_argument('--cwd',default=str(Path.cwd()))
    a.add_argument('--output',default='artifacts/discovery.json')
    args=a.parse_args()
    executable = shutil.which('codex')
    if executable is None:
        print(json.dumps({'error':'Codex CLI not found on PATH'}),file=sys.stderr)
        return 2
    p=subprocess.Popen([executable,'app-server','--stdio'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,encoding='utf-8')
    q=queue.Queue()
    def reader():
        for line in p.stdout:
            try:q.put(json.loads(line))
            except json.JSONDecodeError:pass
    threading.Thread(target=reader,daemon=True).start()
    def rpc(i,method,params):
        p.stdin.write(json.dumps({'id':i,'method':method,'params':params})+'\n');p.stdin.flush()
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            try:msg=q.get(timeout=1)
            except queue.Empty:
                if p.poll() is not None:
                    raise RuntimeError(f'Codex app-server exited with code {p.returncode}')
                continue
            if msg.get('id')==i:
                if 'error' in msg:raise RuntimeError(msg['error'])
                return msg['result']
        raise TimeoutError(method)
    try:
        init=rpc(1,'initialize',{'clientInfo':{'name':'lottery-skill-check','version':'1.0.0'}})
        p.stdin.write(json.dumps({'method':'initialized'})+'\n');p.stdin.flush()
        result=rpc(2,'skills/list',{'cwds':[str(Path(args.cwd).resolve())],'forceReload':True})
        matches=[s for entry in result['data'] for s in entry['skills'] if s['name']=='lottery-analyst']
        errors=[e for entry in result['data'] for e in entry.get('errors',[]) if 'lottery' in str(e)]
        # Public-safe summary; raw paths, userAgent, and errors stay out of output.
        output={'matches':[{'name':s['name'],'scope':s['scope'],'enabled':s['enabled']} for s in matches],
                'error_count':len(errors)}
        Path(args.output).parent.mkdir(parents=True,exist_ok=True)
        Path(args.output).write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(output,ensure_ascii=True,indent=2))
        return 0 if matches and not errors and all(x['enabled'] for x in matches) else 1
    except (RuntimeError, TimeoutError, OSError, KeyError, TypeError) as e:
        print(json.dumps({'error':type(e).__name__,
                          'hint':'Check Codex CLI, local user configuration, and app-server protocol compatibility.'}),file=sys.stderr)
        return 2
    finally:
        p.terminate()
        try:p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait()


if __name__=='__main__':raise SystemExit(main())
