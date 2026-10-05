import copy
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from atelier.server.server import Workspace,WorkspaceError,ROOT,serve,field_diff
from atelier.server.ai_runtime import AIRuntime
from atelier.server.openai_driver import OpenAIDriver,ProviderUnavailable

class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        for folder in ['posts','notes','atelier/config']:(self.root/folder).mkdir(parents=True)
        for file in ['employees.json','workflow.json']:(self.root/'atelier/config'/file).write_bytes((ROOT/'atelier/config'/file).read_bytes())
        (self.root/'posts/index.json').write_text(json.dumps({'weeks':['fixture.json']}))
        (self.root/'posts/fixture.json').write_text(json.dumps({'week':'fixture','posts':[{'id':'fixture_1','platform':'X','content':'本文','quote':'ひとこと','x_short':'短文','self_replies':['導線'],'public_ok':True},{'id':'fixture_2','platform':'Threads','content':'別投稿','quote':'別ひとこと'}]}))
        (self.root/'notes/index.json').write_text(json.dumps({'notes':['fixture.json']}))
        (self.root/'notes/fixture.json').write_text(json.dumps({'title':'fixture note','markdown':'本文','maai_axis':{'温度':'高','距離':'低'}}))
        self.w=Workspace(self.root,self.root/'work.sqlite3');self.key='posts/fixture.json#0'
    def tearDown(self):self.tmp.cleanup()
    def basis(self):return self.w.mutate(self.key,0,'basis',{'theme':'fixture theme','axis':'fixture axis'})
    def result(self,**extra):return {'theme':'fixture theme','axis':'fixture axis','status':'変更なし',**extra}
    def assert_error(self,code,fn):
        with self.assertRaises(WorkspaceError) as e:fn()
        self.assertEqual(e.exception.code,code)

    def test_read_sources_and_public_separation(self):
        before=(self.root/'posts/fixture.json').read_bytes();state=self.basis()
        self.assertEqual(set(state['candidates']),{'A','B','C'});self.assertTrue(state['source_public_ok'])
        self.w.mutate(self.key,1,'adopt',{'candidate':'B','candidate_revision':0})
        self.assertEqual(before,(self.root/'posts/fixture.json').read_bytes())
        self.assertEqual(self.w.get('notes/fixture.json#0')['candidates'].keys(),{'A','B'})

    def test_employee_count_and_roles(self):
        self.assertEqual(len(self.w.employees),58)
        ids={e['id'] for e in self.w.employees}
        self.assertIn('X01',ids);self.assertIn('T21',ids);self.assertIn('XS14',ids)
        self.assertEqual(self.w.employee('BOARD_EDIT')['name'],'TOP OF 敏腕編集者')
        self.assertEqual(self.w.employee('VP')['company_stop_only'],['事実が曲がった','声が混ざった','工程に戻っていない'])

    def test_workflow(self):
        workflow=json.loads((self.root/'atelier/config/workflow.json').read_text())
        stages=workflow['stages']
        self.assertEqual([s['id'] for s in stages],['post_owner','board_or_complete','coco'])
        self.assertEqual(stages[1]['employees'],['BOARD_EDIT','BOARD_WORD','BOARD_SNS'])
        self.assertEqual(workflow['note']['status'],'保留・未稼働')
        self.assertEqual(workflow['ai']['status'],'未接続・再開しない')

    def test_direct_edit_history_and_conflict(self):
        self.basis();state=self.w.mutate(self.key,1,'edit',{'candidate':'A','candidate_revision':0,'fields':{'content':'Cocoの本文'},'reason':'表現修正'})
        self.assertEqual(state['revision'],2);self.assertEqual(state['candidates']['A']['revision'],1)
        self.assertIn('content',state['candidates']['A']['protected'])
        self.assertEqual(self.w.history(self.key)[0]['actor'],'Coco')
        self.assert_error('CONFLICT',lambda:self.w.mutate(self.key,1,'edit',{'candidate':'A','candidate_revision':0,'fields':{'content':'上書き'},'reason':'表現修正'}))
        self.assertEqual(self.w.get(self.key),state)

    def test_candidate_revision_conflict(self):
        self.basis();self.assert_error('CONFLICT',lambda:self.w.mutate(self.key,1,'edit',{'candidate':'A','candidate_revision':99,'fields':{'content':'修正'},'reason':'表現修正'}))

    def test_coco_correction_audit_and_threshold(self):
        self.basis()
        self.w.mutate(self.key,1,'edit',{'candidate':'A','candidate_revision':0,'fields':{'content':'修正A'},'reason':'4行目の戦略'})
        self.w.mutate(self.key,2,'edit',{'candidate':'B','candidate_revision':0,'fields':{'content':'修正B'},'reason':'4行目の戦略'})
        self.w.mutate(self.key,3,'edit',{'candidate':'C','candidate_revision':0,'fields':{'content':'修正C'},'reason':'4行目の戦略'})
        row=self.w.audit_summary()['rankings'][0]
        self.assertEqual(row['department'],'X');self.assertEqual(row['count'],3);self.assertTrue(row['rule_change_candidate'])

    def test_coco_correction_requires_reason(self):
        self.basis()
        self.assert_error('CORRECTION_REASON',lambda:self.w.mutate(self.key,1,'edit',{'candidate':'A','candidate_revision':0,'fields':{'content':'修正'}}))

    def test_basis_not_candidate_and_public_fields_not_editable(self):
        self.basis()
        for field in ['theme','axis','public_ok','episode_id','axis_map','maai_axis']:
            self.assert_error('FIELD',lambda:self.w.mutate(self.key,1,'edit',{'candidate':'A','candidate_revision':0,'fields':{field:'変更'},'reason':'表現修正'}))
        self.assert_error('VALIDATION',lambda:self.w.mutate(self.key,1,'basis',{'theme':'','axis':'x'}))

    def test_review_adoption_invalidated_on_basis_change(self):
        self.basis();self.w.save_ai_result(self.key,'A','BOARD_EDIT',1,0,self.result())
        self.w.mutate(self.key,2,'adopt',{'candidate':'A','candidate_revision':0})
        state=self.w.mutate(self.key,3,'basis',{'theme':'new theme','axis':'new axis'})
        self.assertIsNone(state['adopted']);self.assertTrue(state['reviews'][0]['stale'])
        self.assertEqual(state['candidates']['A']['fields'],state['candidates']['B']['fields'])

    def test_needs_split_preserves_candidates_and_basis(self):
        before=self.basis();after=self.w.save_ai_result(self.key,'A','BOARD_EDIT',1,0,self.result(theme='different',split_at='第2段落',fields={'content':'改稿'}))
        self.assertEqual(after['theme'],before['theme']);self.assertEqual(after['candidates'],before['candidates'])
        self.assertEqual(after['status'],'NEEDS_SPLIT');self.assertEqual(after['needs_split']['split_at'],'第2段落')
        self.assert_error('NEEDS_SPLIT',lambda:self.w.mutate(self.key,2,'adopt',{'candidate':'A','candidate_revision':0}))
        self.assert_error('NEEDS_SPLIT',lambda:self.w.save_ai_result(self.key,'A','X01',2,0,self.result(fields={'content':'別案'})))

    def test_split_requires_position(self):
        self.basis();self.assert_error('VALIDATION',lambda:self.w.save_ai_result(self.key,'A','BOARD_EDIT',1,0,self.result(theme='other')))
        self.assertEqual(self.w.get(self.key)['revision'],1)

    def test_coco_protection_blocks_ai_and_logs(self):
        self.basis();self.w.mutate(self.key,1,'edit',{'candidate':'A','candidate_revision':0,'fields':{'content':'Coco修正'},'reason':'事実'})
        self.assert_error('COCO_PROTECTED',lambda:self.w.save_ai_result(self.key,'A','X01',2,1,self.result(fields={'content':'AI変更'})))
        self.assertEqual(self.w.get(self.key)['candidates']['A']['fields']['content'],'Coco修正')
        self.assertEqual(self.w.executions(self.key)[0]['code'],'COCO_PROTECTED')

    def test_stale_ai_result(self):
        self.basis();self.w.mutate(self.key,1,'edit',{'candidate':'B','candidate_revision':0,'fields':{'content':'修正'},'reason':'表現修正'})
        self.assert_error('CONFLICT',lambda:self.w.save_ai_result(self.key,'A','X01',1,0,self.result(fields={'content':'古いAI結果'})))

    def test_permissions(self):
        self.basis()
        for employee,fields in [('BOARD_EDIT',{'content':'変更'}),('AUDIT',{'quote':'変更'}),('T01',{'content':'変更'}),('XS01',{'quote':'変更'})]:
            self.assert_error('PERMISSION',lambda:self.w.save_ai_result(self.key,'A',employee,1,0,self.result(fields=fields)))
        self.assert_error('PERMISSION',lambda:self.w.save_ai_result(self.key,'A','UNKNOWN',1,0,self.result()))
        state=self.w.save_ai_result(self.key,'A','X01',1,0,self.result(fields={'content':'テスト候補'}))
        self.assertEqual(state['candidates']['A']['fields']['content'],'テスト候補')
        self.assertIsNone(state['adopted'])

    def test_board_cannot_rewrite_post(self):
        self.basis();state=self.w.save_ai_result(self.key,'A','BOARD_EDIT',1,0,self.result())
        self.assertEqual(state['candidates']['A']['revision'],0)
        self.assert_error('PERMISSION',lambda:self.w.save_ai_result(self.key,'A','BOARD_EDIT',2,0,self.result(fields={'content':'全面改稿'})))

    def test_top_of_no_ranking(self):
        self.basis()
        for k in ['score','rank','winner','ranking']:
            self.assert_error('NO_RANKING',lambda:self.w.save_ai_result(self.key,'A','BOARD_EDIT',1,0,self.result(**{k:1})))
        self.assertEqual(self.w.get(self.key)['revision'],1)

    def test_revert_post_only_monotonic_revision(self):
        self.basis();other=self.w.get('posts/fixture.json#1')
        self.w.mutate(self.key,1,'edit',{'candidate':'A','candidate_revision':0,'fields':{'content':'修正'},'reason':'表現修正'})
        preview=self.w.revert_preview(self.key,0)
        self.assertEqual(preview['revision'],2);self.assertIn('candidates',preview['diff'])
        state=self.w.mutate(self.key,2,'revert',{'target_revision':0})
        self.assertEqual(state['revision'],3);self.assertEqual(state['candidates']['A']['revision'],2)
        self.assertEqual(state['candidates']['A']['fields']['content'],'本文')
        self.assertEqual(self.w.get('posts/fixture.json#1'),other)
        self.assert_error('CONFLICT',lambda:self.w.save_ai_result(self.key,'A','X01',1,0,self.result(fields={'content':'古い結果'})))

    def test_db_reopen(self):
        state=self.basis();again=Workspace(self.root,self.root/'work.sqlite3');self.assertEqual(again.get(self.key),state)

    def test_source_conflict(self):
        self.basis();p=self.root/'posts/fixture.json';data=json.loads(p.read_text());data['posts'][0]['content']='GitHubで変更';p.write_text(json.dumps(data))
        self.assert_error('SOURCE_CONFLICT',lambda:self.w.get(self.key))

    def test_concurrent_edits_one_winner(self):
        self.basis();outcomes=[]
        def edit(text):
            try:self.w.mutate(self.key,1,'edit',{'candidate':'A','candidate_revision':0,'fields':{'content':text},'reason':'表現修正'});outcomes.append('saved')
            except WorkspaceError as e:outcomes.append(e.code)
        threads=[threading.Thread(target=edit,args=(text,)) for text in ['一','二']]
        for t in threads:t.start()
        for t in threads:t.join()
        self.assertCountEqual(outcomes,['saved','CONFLICT'])

    def test_disabled_provider_never_called(self):
        self.basis();runtime=AIRuntime(self.w)
        with patch.object(runtime.provider,'execute',side_effect=AssertionError('must not send')) as call:
            with self.assertRaises(ProviderUnavailable):runtime.execute(self.key,'A','X01',1,0)
            call.assert_not_called()
        self.assertEqual(self.w.executions(self.key)[0]['code'],'AI_DISABLED')
        self.assertEqual(self.w.get(self.key)['revision'],1)
        with self.assertRaises(ProviderUnavailable):OpenAIDriver().execute({})

    def test_runtime_permission_failure_is_logged(self):
        self.basis();runtime=AIRuntime(self.w)
        self.assert_error('PERMISSION',lambda:runtime.execute(self.key,'A','T01',1,0))
        self.assertEqual(self.w.executions(self.key)[0]['code'],'PERMISSION')

    def test_review_findings_preserved_and_status_validated(self):
        self.basis()
        self.assert_error('VALIDATION',lambda:self.w.save_ai_result(self.key,'A','X01',1,0,self.result(status='公開済み')))
        state=self.w.save_ai_result(self.key,'A','BOARD_EDIT',1,0,self.result(findings=['素材外の会話を確認']))
        self.assertEqual(state['reviews'][0]['findings'],['素材外の会話を確認'])

    def test_ranges_and_diff(self):
        self.assertEqual(self.w.changed_ranges('abc','aBc'),[[1,2]])
        diff=field_diff({'quote':'前'},{'quote':'後'});self.assertEqual(diff['quote']['before'],'前');self.assertIn('+"後"',diff['quote']['diff'])

class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        with patch.dict(os.environ,{'ATELIER_TOKEN':'fixture-only-token'}):cls.server=serve(0,Path(cls.tmp.name)/'work.sqlite3')
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start();cls.url=f'http://127.0.0.1:{cls.server.server_port}'
    @classmethod
    def tearDownClass(cls):cls.server.shutdown();cls.server.server_close();cls.thread.join();cls.tmp.cleanup()
    def test_read_ui_and_real_data(self):
        with urlopen(self.url+'/atelier/') as response:self.assertIn(b'app.mjs',response.read())
        with urlopen(self.url+'/api/posts') as response:rows=json.load(response)
        self.assertTrue(any(p['platform']=='X' for p in rows));self.assertTrue(any(p['platform']=='Threads' for p in rows));self.assertTrue(any(p['platform']=='note' for p in rows));self.assertTrue(any('診断' in p['platform'] for p in rows))
    def test_unauthenticated_write_rejected(self):
        req=Request(self.url+'/api/mutate',data=b'{}',headers={'Content-Type':'application/json'})
        with self.assertRaises(HTTPError) as e:urlopen(req)
        self.assertEqual(e.exception.code,403)
    def test_cross_origin_rejected(self):
        req=Request(self.url+'/api/mutate',data=b'{}',headers={'Authorization':'Bearer fixture-only-token','Origin':'https://example.invalid'})
        with self.assertRaises(HTTPError) as e:urlopen(req)
        self.assertEqual(e.exception.code,403)
    def test_source_and_secret_paths_not_served(self):
        for path in ['/atelier/server/server.py','/atelier/.local/work.sqlite3','/atelier/assets/../../CLAUDE.md','/posts/week_2026_10_06_2026_10_12.json']:
            with self.assertRaises(HTTPError):urlopen(self.url+path)
    def test_status_disabled(self):
        with urlopen(self.url+'/api/status') as response:status=json.load(response)
        self.assertFalse(status['enabled']);self.assertEqual(status['ai'],'未接続')

if __name__=='__main__':unittest.main()
