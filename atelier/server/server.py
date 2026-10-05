"""weeklyを読取り、Atelier作業情報だけをSQLiteへ保存するローカルサーバー。"""
import argparse
import contextlib
import copy
import difflib
import hashlib
import hmac
import json
import os
from pathlib import Path
import sqlite3
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from .ai_runtime import AIRuntime
from .openai_driver import ProviderUnavailable

ROOT = Path(__file__).resolve().parents[2]
EDITABLE = {'content','quote','x_short','self_replies','title','body','markdown',
            'frame','comment','reply_1','takeaway_line','bridge_line','choices'}

class WorkspaceError(Exception):
    def __init__(self, code, message, details=None):
        self.code, self.details = code, details
        super().__init__(message)


def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True).encode()).hexdigest()


def field_diff(before, after):
    result = {}
    for field in sorted(set(before)|set(after)):
        if before.get(field) != after.get(field):
            old, new = before.get(field), after.get(field)
            result[field] = {'before':old,'after':new,'diff': '\n'.join(difflib.unified_diff(
                json.dumps(old,ensure_ascii=False,indent=2).splitlines(),
                json.dumps(new,ensure_ascii=False,indent=2).splitlines(),lineterm=''))}
    return result


class Workspace:
    def __init__(self, root=ROOT, db_path=None):
        self.root = Path(root)
        self.db_path = str(db_path or self.root/'atelier/.local/work.sqlite3')
        Path(self.db_path).parent.mkdir(parents=True,exist_ok=True)
        self.lock = threading.RLock()
        self.employees = json.loads((self.root/'atelier/config/employees.json').read_text())
        with self.transaction() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS states (key TEXT PRIMARY KEY, state TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS history (id INTEGER PRIMARY KEY, key TEXT NOT NULL,
              revision INTEGER NOT NULL, actor TEXT NOT NULL, action TEXT NOT NULL,
              before_state TEXT NOT NULL, after_state TEXT NOT NULL, at TEXT DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS executions (id INTEGER PRIMARY KEY, key TEXT NOT NULL,
              employee TEXT, candidate TEXT, status TEXT, code TEXT, at TEXT DEFAULT CURRENT_TIMESTAMP);
            ''')

    @contextlib.contextmanager
    def transaction(self):
        with self.lock:
            db = sqlite3.connect(self.db_path)
            db.row_factory = sqlite3.Row
            try:
                db.execute('BEGIN IMMEDIATE')
                yield db
                db.commit()
            except Exception:
                db.rollback()
                raise
            finally:
                db.close()

    def employee(self, employee):
        matches = [p for p in self.employees if str(p['id'])==str(employee)]
        if not matches: raise WorkspaceError('PERMISSION','社員IDが不明です')
        return matches[0]

    def sources(self):
        rows=[]
        for folder,index_key in [('posts','weeks'),('notes','notes')]:
            index=json.loads((self.root/folder/'index.json').read_text())
            filenames=index.get(index_key,[])
            if folder=='posts':filenames+=index.get('linestamps',[])
            for filename in dict.fromkeys(filenames):
                if not isinstance(filename,str) or Path(filename).name!=filename:continue
                path=self.root/folder/filename
                data=json.loads(path.read_text())
                posts=data.get('posts')
                if posts is None:posts=[data]
                for pos,post in enumerate(posts):
                    key=f'{folder}/{filename}#{pos}'
                    rows.append({'key':key,'source':post,'platform':post.get('platform','note' if folder=='notes' else data.get('type','不明')),
                        'label':post.get('id') or post.get('title') or post.get('date') or filename,
                        'week':data.get('week',post.get('source_week',''))})
        return rows

    def source(self,key):
        for row in self.sources():
            if row['key']==key:return row
        raise WorkspaceError('NOT_FOUND','投稿が見つかりません')

    def _load(self,db,key):
        row=self.source(key)
        saved=db.execute('SELECT state FROM states WHERE key=?',(key,)).fetchone()
        if saved:
            state=json.loads(saved['state'])
            if state['source_digest']!=digest(row['source']):
                raise WorkspaceError('SOURCE_CONFLICT','weekly正本が変更されています。作業状態を自動上書きしません')
            return state
        base={k:v for k,v in row['source'].items() if k in EDITABLE}
        return {'key':key,'platform':row['platform'],'revision':0,'source_digest':digest(row['source']),
            'theme':row['source'].get('theme',''),'axis':row['source'].get('axis',''),'source_public_ok':row['source'].get('public_ok'),
            'candidates':{c:{'fields':copy.deepcopy(base),'revision':0,'protected':{},'status':'未着手'}
                          for c in (['A','B'] if row['platform']=='note' or '診断' in row['platform'] else ['A','B','C'])},
            'reviews':[],'adopted':None,'status':'未着手','needs_split':None}

    def get(self,key):
        with self.transaction() as db:return self._load(db,key)

    @staticmethod
    def check_revision(state,expected):
        if type(expected)!=int or state['revision']!=expected:
            raise WorkspaceError('CONFLICT','revisionが変わりました。現在版と自分の変更を比較してください',state)

    @staticmethod
    def check_candidate_revision(state,candidate,expected):
        if candidate not in state['candidates']:raise WorkspaceError('CANDIDATE','この媒体では指定候補を扱いません')
        if type(expected)!=int or state['candidates'][candidate]['revision']!=expected:
            raise WorkspaceError('CONFLICT','候補revisionが変わりました',state)

    def persist(self,db,before,state,actor,action):
        state['revision']=before['revision']+1
        db.execute('INSERT OR REPLACE INTO states VALUES (?,?)',(state['key'],json.dumps(state,ensure_ascii=False)))
        db.execute('INSERT INTO history(key,revision,actor,action,before_state,after_state) VALUES (?,?,?,?,?,?)',
            (state['key'],state['revision'],str(actor),action,json.dumps(before,ensure_ascii=False),json.dumps(state,ensure_ascii=False)))
        return state

    @staticmethod
    def invalidate(state):
        for review in state['reviews']:review['stale']=True
        for proposal in state.get('proposals',[]):proposal['status']='再確認対象'
        state['adopted']=None
        state['status']='再確認対象'

    def mutate(self,key,expected,action,payload):
        with self.transaction() as db:
            state=self._load(db,key);self.check_revision(state,expected);before=copy.deepcopy(state)
            if action=='basis':
                if set(payload)!={'theme','axis'} or not all(isinstance(v,str) and v.strip() for v in payload.values()):
                    raise WorkspaceError('VALIDATION','theme／axisは投稿単位の文字列です')
                state.update(payload);state['needs_split']=None;self.invalidate(state)
            elif action=='edit':
                c=payload.get('candidate');self.check_candidate_revision(state,c,payload.get('candidate_revision'))
                fields=payload.get('fields',{});self.validate_fields(state,c,fields)
                cand=state['candidates'][c]
                for field,value in fields.items():
                    old=cand['fields'].get(field)
                    if old!=value:
                        cand['protected'][field]={'revision':before['revision']+1,'candidate_revision':cand['revision']+1,
                            'ranges':self.changed_ranges(old,value),'value_digest':digest(value)}
                        cand['fields'][field]=value
                cand['revision']+=1;cand['status']='Coco修正中';self.invalidate(state)
            elif action=='adopt':
                c=payload.get('candidate');self.check_candidate_revision(state,c,payload.get('candidate_revision'))
                if state['needs_split']:raise WorkspaceError('NEEDS_SPLIT','別テーマ箇所を確認してください')
                if not state['theme'] or not state['axis']:raise WorkspaceError('BASIS_REQUIRED','theme／axisを確認してください')
                state['adopted']=c;state['status']='Coco採用済み'
            elif action=='revert':
                row=db.execute('SELECT after_state FROM history WHERE key=? AND revision=?',(key,payload.get('target_revision'))).fetchone()
                if payload.get('target_revision')==0:
                    row=db.execute('SELECT before_state FROM history WHERE key=? ORDER BY id LIMIT 1',(key,)).fetchone()
                    target=json.loads(row['before_state']) if row else None
                else:target=json.loads(row['after_state']) if row else None
                if not target:raise WorkspaceError('NOT_FOUND','復元対象がありません')
                state=target;state['source_digest']=before['source_digest'];self.invalidate(state)
                # 復元もCoco操作。以前のAI結果が一致revisionで適用されないよう単調増加。
                for c,cand in state['candidates'].items():
                    cand['revision']=before['candidates'][c]['revision']+1
                    cand['protected']={f:{'revision':before['revision']+1,'candidate_revision':cand['revision'],
                        'ranges':[[0,len(v)]] if isinstance(v,str) else [[0,1]],'value_digest':digest(v)} for f,v in cand['fields'].items()}
            else:raise WorkspaceError('ACTION','操作が不明です')
            return self.persist(db,before,state,'Coco',action)

    @staticmethod
    def changed_ranges(old,new):
        if not isinstance(old,str) or not isinstance(new,str):return [[0,1]]
        return [[j1,j2] for op,i1,i2,j1,j2 in difflib.SequenceMatcher(None,old,new,autojunk=False).get_opcodes() if op!='equal']

    @staticmethod
    def validate_fields(state,c,fields):
        if not isinstance(fields,dict) or not fields or not set(fields)<=EDITABLE:
            raise WorkspaceError('FIELD','編集可能フィールド以外は変更できません')
        for f,v in fields.items():
            old=state['candidates'][c]['fields'].get(f)
            if f not in state['candidates'][c]['fields'] or type(v)!=type(old):
                raise WorkspaceError('FIELD','存在しないフィールド・型変更はできません')

    def log(self,db,key,employee,status,code,candidate=None):
        # 本文、素材、例外文、キー、provider応答はログへ保存しない。
        db.execute('INSERT INTO executions(key,employee,candidate,status,code) VALUES (?,?,?,?,?)',
                   (key,str(employee),candidate,status,code))

    def save_ai_result(self,key,candidate,employee,expected,expected_candidate,result):
        error=None;output=None
        with self.transaction() as db:
            try:
                state=self._load(db,key);self.check_revision(state,expected)
                self.check_candidate_revision(state,candidate,expected_candidate)
                person=self.employee(employee);before=copy.deepcopy(state)
                if not isinstance(result,dict):raise WorkspaceError('VALIDATION','結果形式が不正です')
                if result.get('status','変更なし') not in {'変更なし','要確認','OK','NG','NEEDS_SPLIT'}:
                    raise WorkspaceError('VALIDATION','レビュー状態が不明です')
                if 'findings' in result and not isinstance(result['findings'],list):
                    raise WorkspaceError('VALIDATION','監査指摘は配列で指定してください')
                if result.get('theme')!=state['theme'] or result.get('axis')!=state['axis'] or result.get('status')=='NEEDS_SPLIT':
                    if not isinstance(result.get('split_at'),str) or not result['split_at'].strip():
                        raise WorkspaceError('VALIDATION','別テーマの開始箇所を指定してください')
                    state['needs_split']={'candidate':candidate,'split_at':result['split_at'],'employee':person['id']}
                    self.invalidate(state);state['status']='NEEDS_SPLIT'
                    output=self.persist(db,before,state,employee,'NEEDS_SPLIT')
                    self.log(db,key,employee,'stopped','NEEDS_SPLIT',candidate)
                else:
                    if state['needs_split']:raise WorkspaceError('NEEDS_SPLIT','Cocoによる基準確認が必要です')
                    if not state['theme'] or not state['axis']:raise WorkspaceError('BASIS_REQUIRED','投稿の基準が未確認です')
                    fields=result.get('fields',{})
                    if fields:
                        self.validate_fields(state,candidate,fields)
                        if 'candidate' not in person['permissions'] or state['platform'] not in person['media'] or not set(fields)<=set(person['fields']):
                            raise WorkspaceError('PERMISSION','担当媒体・フィールドの権限がありません')
                        cand=state['candidates'][candidate]
                        for f,v in fields.items():
                            if v==cand['fields'][f]:continue
                            # 保護対象フィールドへのAI変更は停止。位置を保存し、曖昧な再対応付けは行わない。
                            if f in cand['protected']:raise WorkspaceError('COCO_PROTECTED','Coco修正フィールドへの変更を停止しました')
                        if person.get('minimal_diff_only'):
                            if result.get('change_kind')!='minimal_expression':raise WorkspaceError('MINIMAL_DIFF','ID20は最小の表現変更だけを提案できます')
                            # 意味・事実の保護は機械で保証できないため自動保存せずCoco確認で止める。
                            state.setdefault('proposals',[]).append({'employee':20,'candidate':candidate,'revision':before['revision']+1,'candidate_revision':cand['revision'],'diff':field_diff(cand['fields'],{**cand['fields'],**fields}),'fields':fields,'status':'Coco確認待ち'})
                            fields={}
                        if fields:
                            cand['fields'].update(fields);cand['revision']+=1;cand['status']='レビュー中';self.invalidate(state)
                    if person.get('no_ranking') and any(k in result for k in ['score','rank','winner','ranking']):
                        raise WorkspaceError('NO_RANKING','三者会議は点数・ランキング・勝者を決めません')
                    state['reviews'].append({'employee':person['id'],'candidate':candidate,
                        'candidate_revision':state['candidates'][candidate]['revision'],'basis_revision':before['revision'],
                        'status':result.get('status','変更なし'),'findings':result.get('findings',[]),'stale':False})
                    output=self.persist(db,before,state,employee,'ai_result')
                    self.log(db,key,employee,'saved','SAVED',candidate)
            except WorkspaceError as exc:
                error=exc;self.log(db,key,employee,'blocked',exc.code,candidate)
        if error:raise error
        return output

    def revert_preview(self,key,target_revision):
        with self.transaction() as db:
            current=self._load(db,key)
            if target_revision==0:
                row=db.execute('SELECT before_state FROM history WHERE key=? ORDER BY id LIMIT 1',(key,)).fetchone()
                target=json.loads(row['before_state']) if row else None
            else:
                row=db.execute('SELECT after_state FROM history WHERE key=? AND revision=?',(key,target_revision)).fetchone()
                target=json.loads(row['after_state']) if row else None
            if not target:raise WorkspaceError('NOT_FOUND','復元対象がありません')
            return {'revision':current['revision'],'diff':field_diff(current,target)}

    def history(self,key):
        with self.transaction() as db:
            rows=db.execute('SELECT * FROM history WHERE key=? ORDER BY id DESC',(key,)).fetchall()
        result=[]
        for row in rows:
            item=dict(row);before=json.loads(item.pop('before_state'));after=json.loads(item.pop('after_state'))
            item['diff']=field_diff(before,after);result.append(item)
        return result

    def executions(self,key):
        with self.transaction() as db:
            return [dict(r) for r in db.execute('SELECT * FROM executions WHERE key=? ORDER BY id DESC',(key,))]


class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass

    def send_json(self,value,status=200):
        raw=json.dumps(value,ensure_ascii=False).encode()
        self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(raw)

    def do_GET(self):
        url=urlparse(self.path);params=parse_qs(url.query);key=params.get('key',[''])[0]
        try:
            if url.path=='/api/posts':return self.send_json(self.server.workspace.sources())
            if url.path=='/api/state':return self.send_json(self.server.workspace.get(key))
            if url.path=='/api/revert-preview':return self.send_json(self.server.workspace.revert_preview(key,int(params.get('revision',['0'])[0])))
            if url.path=='/api/history':return self.send_json(self.server.workspace.history(key))
            if url.path=='/api/logs':return self.send_json(self.server.workspace.executions(key))
            if url.path=='/api/status':return self.send_json({'ai':'未接続','enabled':False,'publish':'未実装','db':'SQLite作業DB','write_enabled':bool(self.server.token)})
            allowed={'/':'atelier/index.html','/atelier/':'atelier/index.html'}
            path=allowed.get(url.path,url.path.lstrip('/'))
            if path not in ['atelier/index.html','atelier/config/employees.json','atelier/config/workflow.json'] and not path.startswith('atelier/assets/'):
                return self.send_json({'error':'NOT_FOUND'},404)
            resolved=(ROOT/path).resolve();assets=(ROOT/'atelier').resolve()
            if not resolved.is_relative_to(assets) or not resolved.is_file():return self.send_json({'error':'NOT_FOUND'},404)
            raw=resolved.read_bytes();self.send_response(200)
            mime={'.html':'text/html','.mjs':'text/javascript','.css':'text/css','.json':'application/json'}.get(resolved.suffix,'application/octet-stream')
            self.send_header('Content-Type',mime+'; charset=utf-8');self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Security-Policy',"default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'")
            self.end_headers();self.wfile.write(raw)
        except WorkspaceError as exc:self.send_json({'error':exc.code,'message':str(exc),'current':exc.details},409)
        except (ValueError,TypeError):self.send_json({'error':'VALIDATION','message':'入力形式を確認してください'},400)

    def do_POST(self):
        try:
            origin=self.headers.get('Origin')
            if origin and origin!=f'http://127.0.0.1:{self.server.server_port}':raise WorkspaceError('AUTH','同一originで操作してください')
            token=self.headers.get('Authorization','').removeprefix('Bearer ')
            if not self.server.token or not hmac.compare_digest(token,self.server.token):raise WorkspaceError('AUTH','Coco操作用tokenが必要です')
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=1_000_000:raise WorkspaceError('VALIDATION','リクエストサイズが不正です')
            data=json.loads(self.rfile.read(length));path=urlparse(self.path).path
            if path=='/api/mutate':
                result=self.server.workspace.mutate(data['key'],data['revision'],data['action'],data['payload'])
            elif path=='/api/execute':
                result=self.server.runtime.execute(data['key'],data['candidate'],data['employee'],data['revision'],data['candidate_revision'])
            else:raise WorkspaceError('NOT_FOUND','操作が見つかりません')
            self.send_json(result)
        except ProviderUnavailable as exc:self.send_json({'error':'AI_DISABLED','message':str(exc)},409)
        except WorkspaceError as exc:self.send_json({'error':exc.code,'message':str(exc),'current':exc.details},403 if exc.code=='AUTH' else 409)
        except (KeyError,ValueError,TypeError):self.send_json({'error':'VALIDATION','message':'入力形式を確認してください'},400)


def serve(port=8765,db_path=None):
    workspace=Workspace(db_path=db_path)
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    server.workspace=workspace;server.runtime=AIRuntime(workspace);server.token=os.environ.get('ATELIER_TOKEN','')
    return server

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8765);parser.add_argument('--db')
    args=parser.parse_args();serve(args.port,args.db).serve_forever()
