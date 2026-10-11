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
from .openai_driver import ProviderUnavailable, ProviderError
from .routing import RoutingEngine, RoutingError

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
            CREATE TABLE IF NOT EXISTS corrections (id INTEGER PRIMARY KEY, key TEXT NOT NULL,
              department TEXT NOT NULL, reason TEXT NOT NULL, diff TEXT NOT NULL,
              at TEXT DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS exceptions (id INTEGER PRIMARY KEY, key TEXT NOT NULL,
              department TEXT NOT NULL, note TEXT NOT NULL, at TEXT DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS secretary_queue (id INTEGER PRIMARY KEY,
              kind TEXT NOT NULL, source_role TEXT NOT NULL, department TEXT NOT NULL,
              key TEXT, stage TEXT, payload TEXT NOT NULL,
              status TEXT NOT NULL DEFAULT 'Coco確認待ち',
              response TEXT, at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS rule_changes (id INTEGER PRIMARY KEY, department TEXT NOT NULL,
              old_rule TEXT NOT NULL, new_rule TEXT NOT NULL, reason TEXT NOT NULL,
              coco_approval TEXT NOT NULL, approval_date TEXT NOT NULL,
              effective_from TEXT NOT NULL, impact TEXT NOT NULL, at TEXT DEFAULT CURRENT_TIMESTAMP);
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
                reason=payload.get('reason')
                if not isinstance(reason,str) or not reason.strip():
                    raise WorkspaceError('CORRECTION_REASON','Coco修正の理由を入力してください')
                cand=state['candidates'][c];changed={}
                for field,value in fields.items():
                    old=cand['fields'].get(field)
                    if old!=value:
                        changed[field]={'before':old,'after':value}
                        cand['protected'][field]={'revision':before['revision']+1,'candidate_revision':cand['revision']+1,
                            'ranges':self.changed_ranges(old,value),'value_digest':digest(value)}
                        cand['fields'][field]=value
                if not changed:raise WorkspaceError('NO_CHANGE','変更がありません')
                cand['revision']+=1;cand['status']='Coco修正中';self.invalidate(state)
                stop_queue_id=payload.get('stop_queue_id')
                audit_reason=reason.strip()
                if stop_queue_id is not None:
                    row=db.execute("SELECT kind,status FROM secretary_queue WHERE id=?",(int(stop_queue_id),)).fetchone()
                    if not row or row['kind']!='停止案件' or row['status']!='Coco確認待ち':
                        raise WorkspaceError('STOP_QUEUE','停止中の秘書キューが見つかりません')
                    db.execute("UPDATE secretary_queue SET status='解決済み',response=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                               ('Cocoが直接修正して通過',int(stop_queue_id)))
                    audit_reason='停止中の直接修正'
                self.record_correction(db,state,audit_reason,changed)
            elif action=='adopt':
                c=payload.get('candidate');self.check_candidate_revision(state,c,payload.get('candidate_revision'))
                if state['needs_split']:raise WorkspaceError('NEEDS_SPLIT','別テーマ箇所を確認してください')
                if not state['theme'] or not state['axis']:raise WorkspaceError('BASIS_REQUIRED','theme／axisを確認してください')
                state['adopted']=c;state['status']='Coco採用済み'
            elif action=='finalize':
                c=payload.get('candidate')
                if not state.get('adopted') or c!=state.get('adopted'):
                    raise WorkspaceError('FINALIZE','採用済み候補だけ最終確認できます')
                state['status']='完了'
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

    @staticmethod
    def department_for(state,fields=None):
        fields=set(fields or [])
        if 'x_short' in fields:return 'X短文'
        if state.get('platform')=='Threads':return 'Threads'
        if state.get('platform')=='X':return 'X'
        return '対象外'

    def record_correction(self,db,state,reason,changed):
        department=self.department_for(state,changed.keys())
        if department=='対象外':return
        db.execute('INSERT INTO corrections(key,department,reason,diff) VALUES (?,?,?,?)',
                   (state['key'],department,reason,json.dumps(changed,ensure_ascii=False)))

    def audit_summary(self):
        with self.transaction() as db:
            rankings=[dict(r) for r in db.execute(
                '''SELECT department,reason,COUNT(*) AS count,MAX(at) AS last_at
                   FROM corrections GROUP BY department,reason
                   ORDER BY department,count DESC,last_at DESC''')]
            for row in rankings:row['rule_change_candidate']=row['count']>=3
            exceptions=[dict(r) for r in db.execute('SELECT * FROM exceptions ORDER BY id DESC')]
            exception_summary=[dict(r) for r in db.execute(
                '''SELECT department,note AS direction,COUNT(*) AS count,MAX(at) AS last_at
                   FROM exceptions GROUP BY department,note
                   ORDER BY department,count DESC,last_at DESC''')]
            rule_changes=[dict(r) for r in db.execute('SELECT * FROM rule_changes ORDER BY id DESC')]
        return {'rankings':rankings,'exceptions':exceptions,'exception_summary':exception_summary,'rule_changes':rule_changes}

    def desk(self):
        with self.transaction() as db:
            queue=[dict(r) for r in db.execute(
                """SELECT * FROM secretary_queue WHERE status='Coco確認待ち'
                   ORDER BY CASE WHEN kind='停止案件' THEN 0 ELSE 1 END, id""")]
            for item in queue:item['payload']=json.loads(item['payload'])
            completed=[]
            for row in db.execute('SELECT key,state FROM states ORDER BY key'):
                state=json.loads(row['state'])
                if state.get('status')=='Coco採用済み':
                    adopted=state.get('adopted');fields=(state.get('candidates',{}).get(adopted,{}).get('fields',{}) if adopted else {})
                    label=self.source(row['key']).get('label',row['key'])
                    platform=state.get('platform')
                    department='Threads' if platform=='Threads' else ('X' if platform=='X' else platform)
                    if department in {'X','Threads'}:
                        completed.append({'key':row['key'],'platform':platform,'department':department,'label':label,
                                          'revision':state.get('revision'),'adopted':adopted})
                    if platform=='X' and 'x_short' in fields:
                        completed.append({'key':row['key'],'platform':platform,'department':'X短文','label':label,
                                          'revision':state.get('revision'),'adopted':adopted})
        return {'queue':queue,'completed':completed,'audit':self.audit_summary()}

    def record_exception(self,key,note):
        if not isinstance(note,str) or not note.strip():raise WorkspaceError('VALIDATION','例外通過の理由を入力してください')
        with self.transaction() as db:
            state=self._load(db,key);department=self.department_for(state)
            if department=='対象外':raise WorkspaceError('VALIDATION','対象部門ではありません')
            db.execute('INSERT INTO exceptions(key,department,note) VALUES (?,?,?)',(key,department,note.strip()))
        return {'saved':True}

    def enqueue_secretary(self,kind,source_role,department,payload,key=None,stage=None):
        if kind not in {'停止案件','仕組み提案'}:raise WorkspaceError('VALIDATION','秘書キュー種別が不正です')
        if source_role not in {'課長','副社長'}:raise WorkspaceError('VALIDATION','秘書キューの送信元が不正です')
        if not isinstance(payload,dict):raise WorkspaceError('VALIDATION','秘書キュー内容が不正です')
        required={'停止案件':{'投稿番号','停止工程','不足・不明点','現在確認できる事実','Cocoへの質問'},
                  '仕組み提案':{'現象','回数','原因工程','変更案','影響範囲'}}[kind]
        if not required<=set(payload):raise WorkspaceError('VALIDATION','秘書キューの必須項目が不足しています')
        with self.transaction() as db:
            cur=db.execute('INSERT INTO secretary_queue(kind,source_role,department,key,stage,payload) VALUES (?,?,?,?,?,?)',
                (kind,source_role,department,key,stage,json.dumps(payload,ensure_ascii=False)))
            return {'id':cur.lastrowid,'status':'Coco確認待ち'}

    @staticmethod
    def _workflow_event_if_available(db,case_id,actor,action,target=None,detail=None):
        exists=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='workflow_events'").fetchone()
        if exists and case_id:
            db.execute("INSERT INTO workflow_events(case_id,actor,action,target,detail) VALUES (?,?,?,?,?)",
                       (case_id,actor,action,target,json.dumps(detail or {},ensure_ascii=False)))

    def resolve_secretary(self,item_id,response):
        if not isinstance(response,str) or not response.strip():raise WorkspaceError('VALIDATION','Cocoの回答・承認が必要です')
        with self.transaction() as db:
            row=db.execute("SELECT * FROM secretary_queue WHERE id=? AND status='Coco確認待ち'",(item_id,)).fetchone()
            if not row:raise WorkspaceError('NOT_FOUND','確認待ちの秘書キューが見つかりません')
            db.execute("UPDATE secretary_queue SET status='解決済み',response=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                       (response.strip(),item_id))
            if row['kind']=='停止案件':
                self._workflow_event_if_available(db,row['key'],'Coco','停止案件回答','秘書',{'response':response.strip(),'queue_id':item_id})
                self._workflow_event_if_available(db,row['key'],'秘書','回答返却','課長',{'queue_id':item_id})
        return {'id':item_id,'status':'解決済み'}

    def route_stop_to_proposal(self,item_id):
        with self.transaction() as db:
            row=db.execute("SELECT * FROM secretary_queue WHERE id=? AND kind='停止案件' AND status='Coco確認待ち'",(item_id,)).fetchone()
            if not row:raise WorkspaceError('NOT_FOUND','確認待ちの停止案件が見つかりません')
            db.execute("UPDATE secretary_queue SET status='副社長整理待ち',response='仕組み提案へ回す',updated_at=CURRENT_TIMESTAMP WHERE id=?",
                       (item_id,))
            self._workflow_event_if_available(db,row['key'],'Coco','仕組み提案へ回す','副社長',{'queue_id':item_id})
        return {'id':item_id,'status':'副社長整理待ち'}

    def decide_proposal(self,item_id,decision):
        if decision not in {'承認','却下'}:raise WorkspaceError('VALIDATION','承認か却下を指定してください')
        with self.transaction() as db:
            row=db.execute("SELECT * FROM secretary_queue WHERE id=? AND kind='仕組み提案' AND status='Coco確認待ち'",(item_id,)).fetchone()
            if not row:raise WorkspaceError('NOT_FOUND','確認待ちの仕組み提案が見つかりません')
            payload=json.loads(row['payload'])
            effective='次の新規案件' if decision=='承認' else '適用なし'
            db.execute("UPDATE secretary_queue SET status='解決済み',response=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",(decision,item_id))
            db.execute('''INSERT INTO rule_changes(department,old_rule,new_rule,reason,coco_approval,approval_date,effective_from,impact)
                          VALUES (?,?,?,?,?,date('now'),?,?)''',
                       (row['department'],payload.get('旧ルール','現行ルール'),payload.get('新ルール',payload.get('変更案','')),
                        payload.get('理由',payload.get('現象','')),decision,effective,payload.get('影響範囲','')))
            self._workflow_event_if_available(db,row['key'],'Coco',f'仕組み提案{decision}','秘書',{'queue_id':item_id,'effective_from':effective})
        return {'id':item_id,'status':'解決済み','decision':decision,'effective_from':effective}

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
            if url.path=='/api/desk':return self.send_json(self.server.workspace.desk())
            if url.path=='/api/audit':return self.send_json(self.server.workspace.audit_summary())
            if url.path=='/api/material/pending':return self.send_json(self.server.routing.material_pending(params.get('department',[None])[0]))
            if url.path=='/api/material/summary':return self.send_json(self.server.routing.material_summary(key))
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
        except RoutingError as exc:self.send_json({'error':exc.code,'message':str(exc)},404 if exc.code=='NOT_FOUND' else 409)
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
            elif path=='/api/exception':
                result=self.server.workspace.record_exception(data['key'],data['note'])
            elif path=='/api/secretary/enqueue':
                result=self.server.workspace.enqueue_secretary(data['kind'],data['source_role'],data['department'],data['payload'],data.get('key'),data.get('stage'))
            elif path=='/api/secretary/resolve':
                result=self.server.workspace.resolve_secretary(int(data['id']),data['response'])
            elif path=='/api/secretary/route-proposal':
                result=self.server.workspace.route_stop_to_proposal(int(data['id']))
            elif path=='/api/secretary/decision':
                result=self.server.workspace.decide_proposal(int(data['id']),data['decision'])
            elif path=='/api/execute':
                result=self.server.runtime.execute(data['key'],data['candidate'],data['employee'],data['revision'],data['candidate_revision'])
            elif path=='/api/material/start':
                # Cocoが打つのは原文だけ。9問を埋めるのは取材社員（Claude）。
                ai=self.server.runtime.interview_fill_points(data['case_id'],data['raw_material'])
                result=self.server.routing.material_start(data['case_id'],data['department'],'MATERIAL',data['raw_material'],ai['points'])
                self.server.routing.record_provider_usage(data['case_id'],'工程2',ai.get('_provider'))
                result['missing']=ai['missing']
            elif path=='/api/material/answer':
                result=self.server.routing.material_answer(data['case_id'],data['answers'])
            elif path=='/api/material/propose':
                # Cocoは案を選ぶだけ。案を作るのは取材社員（Claude）。
                summary=self.server.routing.material_summary(data['case_id'])
                ai=self.server.runtime.interview_propose_drafts(data['case_id'],summary['raw_material'],summary['organized_material'])
                result=self.server.routing.material_propose(data['case_id'],ai['drafts'])
                self.server.routing.record_provider_usage(data['case_id'],'工程3',ai.get('_provider'))
            elif path=='/api/material/select':
                result=self.server.routing.material_select(data['case_id'],data['selection'],data.get('addendum'))
            elif path=='/api/material/generalize-preview':
                # 一般化・公開用素材の下書きを取材社員（Claude）が作る。Cocoが直せる形で返す
                # だけで、まだ確定（finalize）はしない。
                summary=self.server.routing.material_summary(data['case_id'])
                selection=summary.get('selected_option')
                selected_draft=None
                if selection in ('A','B','C') and summary.get('drafts'):
                    selected_draft=summary['drafts'][{'A':0,'B':1,'C':2}[selection]]
                decision_context={'選択':selection,'選んだ案':selected_draft,'追記':summary.get('addendum') or ''}
                ai=self.server.runtime.interview_generalize(data['case_id'],summary['raw_material'],summary['organized_material'],summary['department'],decision_context)
                self.server.routing.record_provider_usage(data['case_id'],'工程5',ai.get('_provider'))
                # 「日付」は取材社員に求めていない。Cocoが原文を打った日時をここでシステム側から入れる
                # （material_finalizeでも同じ値に上書きするため、ここで入れ忘れても確定時に揃う）。
                public_material={**ai['public_material'],'日付':self.server.routing.material_entered_date(data['case_id']),
                                  RoutingEngine.MATERIAL_TIME_EXPRESSION_FIELD:ai.get(RoutingEngine.MATERIAL_TIME_EXPRESSION_FIELD,'')}
                result={'public_material':public_material,'smell_flags':ai.get('smell_flags',{}),'provider':ai.get('_provider')}
            elif path=='/api/material/finalize':
                result=self.server.routing.material_finalize(data['case_id'],data['public_material'],data.get('next_employee'))
            else:raise WorkspaceError('NOT_FOUND','操作が見つかりません')
            self.send_json(result)
        except ProviderUnavailable as exc:self.send_json({'error':'AI_DISABLED','message':str(exc)},409)
        except ProviderError as exc:
            technical=getattr(exc,'technical',True)
            self.send_json({'error':'AI_TECHNICAL_ERROR' if technical else 'AI_INVALID_INPUT','message':str(exc)},502 if technical else 400)
        except WorkspaceError as exc:self.send_json({'error':exc.code,'message':str(exc),'current':exc.details},403 if exc.code=='AUTH' else 409)
        except RoutingError as exc:self.send_json({'error':exc.code,'message':str(exc)},409 if exc.code!='NOT_FOUND' else 404)
        except (KeyError,ValueError,TypeError):self.send_json({'error':'VALIDATION','message':'入力形式を確認してください'},400)


def serve(port=8765,db_path=None):
    workspace=Workspace(db_path=db_path)
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    server.workspace=workspace;server.runtime=AIRuntime(workspace);server.routing=RoutingEngine(workspace);server.token=os.environ.get('ATELIER_TOKEN','')
    return server

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8765);parser.add_argument('--db')
    args=parser.parse_args();serve(args.port,args.db).serve_forever()
