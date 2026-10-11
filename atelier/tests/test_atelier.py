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
from atelier.server.anthropic_driver import AnthropicDriver
from atelier.server.openai_driver import OpenAIDriver,ProviderUnavailable,ProviderError

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
        self.assertIn('X01',ids);self.assertIn('T21',ids);self.assertIn('XS14',ids);self.assertIn('MATERIAL',ids)
        self.assertEqual(self.w.employee('BOARD_EDIT')['name'],'TOP OF 敏腕編集者')
        self.assertEqual(self.w.employee('VP')['company_stop_only'],['事実が曲がった','声が混ざった','工程に戻っていない'])
        self.assertEqual(self.w.employee('MATERIAL')['prompt_ref'],'atelier/canon/interview.md')

    def test_workflow(self):
        workflow=json.loads((self.root/'atelier/config/workflow.json').read_text())
        stages=workflow['stages']
        self.assertEqual([s['id'] for s in stages],['material_interview','post_owner','board_or_complete','vice_president_gate','coco'])
        self.assertEqual(stages[0]['employees'],['MATERIAL'])
        self.assertEqual(stages[2]['employees'],['BOARD_EDIT','BOARD_WORD','BOARD_SNS'])
        self.assertEqual(stages[3]['employees'],['VP'])
        self.assertEqual(workflow['note']['status'],'保留・未稼働')
        self.assertEqual(workflow['ai']['role_providers']['post_owner'],'anthropic')
        self.assertEqual(workflow['ai']['role_providers']['management'],'openai')
        self.assertIsNone(workflow['ai']['role_providers']['audit'])

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

    def test_secretary_queue_is_single_queue(self):
        stop=self.w.enqueue_secretary('停止案件','課長','X',{'投稿番号':'X01','停止工程':'②','不足・不明点':'現場で起きたこと','現在確認できる事実':'場面と行動','Cocoへの質問':'そのあと何が起きましたか？'},key=self.key,stage='②')
        proposal=self.w.enqueue_secretary('仕組み提案','副社長','X',{'現象':'同じ修正','回数':3,'原因工程':'④','変更案':'条件を追加','影響範囲':'X部門'})
        queue=self.w.desk()['queue']
        self.assertEqual([q['kind'] for q in queue],['停止案件','仕組み提案'])
        self.w.resolve_secretary(stop['id'],'回答')
        self.assertEqual(len(self.w.desk()['queue']),1)
        self.w.resolve_secretary(proposal['id'],'承認')
        self.assertEqual(self.w.desk()['queue'],[])

    def test_route_stop_to_proposal(self):
        stop=self.w.enqueue_secretary('停止案件','課長','X',{'投稿番号':'X01','停止工程':'②','不足・不明点':'現場で起きたこと','現在確認できる事実':'場面と行動','Cocoへの質問':'そのあと何が起きましたか？'},key=self.key,stage='②')
        result=self.w.route_stop_to_proposal(stop['id'])
        self.assertEqual(result['status'],'副社長整理待ち')
        self.assertEqual(self.w.desk()['queue'],[])

    def test_direct_stop_edit_counts_as_resolution_and_correction(self):
        self.basis()
        stop=self.w.enqueue_secretary('停止案件','課長','X',{'投稿番号':'X01','停止工程':'②','不足・不明点':'現場で起きたこと','現在確認できる事実':'場面と行動','Cocoへの質問':'そのあと何が起きましたか？'},key=self.key,stage='②')
        self.w.mutate(self.key,1,'edit',{'candidate':'A','candidate_revision':0,'fields':{'content':'Cocoが直接修正'},'reason':'任意','stop_queue_id':stop['id']})
        row=self.w.audit_summary()['rankings'][0]
        self.assertEqual(row['reason'],'停止中の直接修正')
        self.assertEqual(self.w.desk()['queue'],[])

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
        # X01 is kind=post_owner, routed to the anthropic provider (role->provider
        # config in ai_runtime.py). Neither provider is connected without its
        # live-flag env var and API key, so execute() must block before calling out.
        self.basis();runtime=AIRuntime(self.w)
        with patch.object(runtime.providers['anthropic'],'execute',side_effect=AssertionError('must not send')) as anthropic_call,\
             patch.object(runtime.providers['openai'],'execute',side_effect=AssertionError('must not send')) as openai_call:
            with self.assertRaises(ProviderUnavailable):runtime.execute(self.key,'A','X01',1,0)
            anthropic_call.assert_not_called();openai_call.assert_not_called()
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

class AIRuntimeRoutingTests(unittest.TestCase):
    """Role->provider selection and the stage-calling skeleton (v2.3 port)."""

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        for folder in ['posts','notes','atelier/config','atelier/canon']:(self.root/folder).mkdir(parents=True)
        for file in ['employees.json','workflow.json']:(self.root/'atelier/config'/file).write_bytes((ROOT/'atelier/config'/file).read_bytes())
        for file in ['x_post.md','threads_post.md','interview.md']:(self.root/'atelier/canon'/file).write_bytes((ROOT/'atelier/canon'/file).read_bytes())
        (self.root/'posts/index.json').write_text(json.dumps({'weeks':['fixture.json']}))
        (self.root/'posts/fixture.json').write_text(json.dumps({'week':'fixture','posts':[
            {'id':'fixture_1','platform':'X','content':'','quote':'','material':'素材本文'},
        ]}))
        (self.root/'notes/index.json').write_text(json.dumps({'notes':['fixture.json']}))
        (self.root/'notes/fixture.json').write_text(json.dumps({'title':'fixture note','markdown':'本文','maai_axis':{'温度':'高','距離':'低'}}))
        self.w=Workspace(self.root,self.root/'work.sqlite3');self.key='posts/fixture.json#0'
    def tearDown(self):self.tmp.cleanup()

    def test_role_provider_mapping(self):
        runtime=AIRuntime(self.w)
        self.assertIs(runtime._provider_for('X01'),runtime.providers['anthropic'])
        self.assertIs(runtime._provider_for('T01'),runtime.providers['anthropic'])
        self.assertIs(runtime._provider_for('MANAGER'),runtime.providers['openai'])
        self.assertIs(runtime._provider_for('VP'),runtime.providers['openai'])
        self.assertIs(runtime._provider_for('BOARD_EDIT'),runtime.providers['openai'])
        self.assertIsNone(runtime._provider_for('AUDIT'))
        self.assertIsNone(runtime._provider_for('SECRETARY'))
        # 取材社員は投稿社員と同じprovider(anthropic)だが、モデルを別に設定できるよう
        # 専用インスタンスを持つ（同一オブジェクトではない）。
        self.assertIs(runtime._provider_for('MATERIAL'),runtime.material_driver)
        self.assertIsNot(runtime.material_driver,runtime.providers['anthropic'])

    def test_role_model_env_fallback_chain(self):
        runtime=AIRuntime(self.w)
        # 既定：役専用の環境変数も共通ANTHROPIC_MODELも無ければdriverの既定モデル
        with patch.dict(os.environ,{},clear=False):
            for var in ('ANTHROPIC_MODEL','ANTHROPIC_MODEL_MATERIAL','ANTHROPIC_MODEL_POST_OWNER'):
                os.environ.pop(var,None)
            self.assertEqual(runtime.material_driver.model,'claude-sonnet-5-5')
            self.assertEqual(runtime.providers['anthropic'].model,'claude-sonnet-5-5')
        # 共通ANTHROPIC_MODELがあれば両方それを使う
        with patch.dict(os.environ,{'ANTHROPIC_MODEL':'claude-common-model'}):
            self.assertEqual(runtime.material_driver.model,'claude-common-model')
            self.assertEqual(runtime.providers['anthropic'].model,'claude-common-model')
        # 役専用の変数があれば、役ごとに別モデルへ切り替えられる（投稿社員だけ上位モデルに等）
        with patch.dict(os.environ,{'ANTHROPIC_MODEL':'claude-common-model','ANTHROPIC_MODEL_POST_OWNER':'claude-opus-5-5'}):
            self.assertEqual(runtime.material_driver.model,'claude-common-model')
            self.assertEqual(runtime.providers['anthropic'].model,'claude-opus-5-5')

    def test_canon_stage_headers_resolve_against_real_canon(self):
        # Canary: if a future canon edit renames a §0 heading, this fails loudly
        # instead of ai_runtime.py silently skipping a stage.
        runtime=AIRuntime(self.w)
        for canon_file in ['atelier/canon/x_post.md','atelier/canon/threads_post.md']:
            text=(ROOT/canon_file).read_text()
            stages=runtime._canon_stages(text)
            names=[name for name,_ in stages]
            self.assertEqual(names,['一般化','①','ひとこと選び','②','④','③',"④'",'⑧'])
            for name,body in stages:
                self.assertTrue(body.strip(),f'{canon_file}:{name} section was empty')

    def test_execute_runs_stages_in_order_and_saves_final_candidate(self):
        self.w.mutate(self.key,0,'basis',{'theme':'fixture theme','axis':'fixture axis'})
        runtime=AIRuntime(self.w)
        expected_order=['一般化','①','ひとこと選び','②','④','③',"④'",'⑧']
        calls=[]

        def fake_execute(request):
            calls.append(request['stage_name'])
            result={'decision':'complete','stop_reason':'none','stop_stage':'','missing_or_unknown':'',
                    'confirmed_facts':'','question_for_coco':'','content':'','quote':'','facts_used':[],
                    'checklist':[],'public_material':'','source_map':[],'candidates':[],'selection':'',
                    'audit_tags':[],'material_suggestions':[],'final_check_round':0,
                    '_provider':{'status':'end_turn','output_tokens':10}}
            if request['stage_name']=='一般化':
                result['public_material']='公開用素材';result['source_map']=['原文 => 公開用']
            if request['stage_name']=='④':
                result['content']='本文候補';result['candidates']=['本文候補'];result['quote']='ひとこと'
            return result

        with patch.object(AnthropicDriver,'connected',True),\
             patch.object(runtime.providers['anthropic'],'execute',side_effect=fake_execute):
            outcome=runtime.execute(self.key,'A','X01',1,0)
        self.assertEqual(calls,expected_order)
        self.assertEqual(outcome['kind'],'complete')
        self.assertEqual(outcome['public_material'],'公開用素材')
        self.assertEqual(outcome['state']['candidates']['A']['fields']['content'],'本文候補')
        self.assertEqual(outcome['state']['candidates']['A']['fields']['quote'],'ひとこと')

    def test_execute_stops_without_calling_later_stages(self):
        self.w.mutate(self.key,0,'basis',{'theme':'fixture theme','axis':'fixture axis'})
        runtime=AIRuntime(self.w)
        calls=[]

        def fake_execute(request):
            calls.append(request['stage_name'])
            if request['stage_name']=='②':
                return {'decision':'stop','stop_reason':'素材不足','stop_stage':'②',
                        'missing_or_unknown':'現場で起きたこと','confirmed_facts':'場面のみ',
                        'question_for_coco':'そのあと何が起きましたか？','material_suggestions':[],
                        '_provider':{'status':'end_turn'}}
            return {'decision':'complete','stop_reason':'none','stop_stage':'','missing_or_unknown':'',
                    'confirmed_facts':'','question_for_coco':'','content':'','quote':'','facts_used':[],
                    'checklist':[],'public_material':'公開用素材' if request['stage_name']=='一般化' else '',
                    'source_map':['原文 => 公開用'] if request['stage_name']=='一般化' else [],
                    'candidates':[],'selection':'','audit_tags':[],'material_suggestions':[],
                    'final_check_round':0,'_provider':{'status':'end_turn'}}

        with patch.object(AnthropicDriver,'connected',True),\
             patch.object(runtime.providers['anthropic'],'execute',side_effect=fake_execute):
            outcome=runtime.execute(self.key,'A','X01',1,0)
        self.assertEqual(calls,['一般化','①','ひとこと選び','②'])
        self.assertEqual(outcome['kind'],'stop')
        self.assertEqual(outcome['stop_reason'],'素材不足')

    def test_material_interview_output_feeds_execute_instead_of_source_file(self):
        # A.5: 取材社員の出力をそのまま投稿社員の入力にする。素材ファイル経由はやめる。
        from atelier.server.routing import RoutingEngine
        routing=RoutingEngine(self.w)
        points={k:f'{k}の回答' for k in routing.MATERIAL_POINTS}
        routing.material_start(self.key,'X','MATERIAL','原文テキスト（ファイルの素材とは別）',points)
        routing.material_finalize(self.key,{
            '日付':'2026-10-11','媒体と置き換え先':'X・仕事上の関係のまま',
            '場面':'取材社員が渡した場面','わたしがしたこと':'取材社員が渡した行動',
            'そのあと起きたこと':'取材社員が渡した結果',
            '【必ず残す事実】3点':['事実1','事実2','事実3'],'対応表':['原文 => 公開用'],
            '原文':'取材社員が渡した原文',
        },next_employee='X01')
        self.w.mutate(self.key,0,'basis',{'theme':'fixture theme','axis':'fixture axis'})
        runtime=AIRuntime(self.w)
        seen_material=[]
        def fake_execute(request):
            seen_material.append(request['material'])
            return {'decision':'complete','stop_reason':'none','stop_stage':'','missing_or_unknown':'',
                    'confirmed_facts':'','question_for_coco':'','content':'本文' if request['stage_name']=='④' else '',
                    'quote':'ひとこと' if request['stage_name']=='④' else '','facts_used':[],'checklist':[],
                    'public_material':'公開用素材' if request['stage_name']=='一般化' else '',
                    'source_map':['原文 => 公開用'] if request['stage_name']=='一般化' else [],
                    'candidates':['本文'] if request['stage_name']=='④' else [],'selection':'','audit_tags':[],
                    'material_suggestions':[],'final_check_round':0,'_provider':{'status':'end_turn'}}
        with patch.object(AnthropicDriver,'connected',True),\
             patch.object(runtime.providers['anthropic'],'execute',side_effect=fake_execute):
            runtime.execute(self.key,'A','X01',1,0)
        # Only the first stage (一般化) sees raw material; later stages work from
        # the public_material that stage itself returns. The point of this test is
        # that the FIRST material ai_runtime sends is the interview's, not the
        # source file's ('fixture theme'/'fixture axis' never appear).
        self.assertIn('取材社員が渡した場面',seen_material[0])
        self.assertTrue(all('fixture' not in m for m in seen_material))

    def _fake_interview_result(self,**overrides):
        from atelier.server.routing import RoutingEngine
        # 「日付」はAIに求めない（MATERIAL_AI_GATE_FIELDS=MATERIAL_GATE_FIELDSから日付を除いた7項目）。
        result={'decision':'continue','stop_reason':'','points':{k:'' for k in RoutingEngine.MATERIAL_POINTS},
                'missing':[],'drafts':[],'public_material':{f:'' for f in RoutingEngine.MATERIAL_AI_GATE_FIELDS},
                'smell_flags':{},RoutingEngine.MATERIAL_TIME_EXPRESSION_FIELD:'',
                '_provider':{'status':'end_turn','output_tokens':12}}
        result.update(overrides)
        return result

    def test_interview_fill_points_caps_missing_at_three_and_uses_interview_canon(self):
        from atelier.server.routing import RoutingEngine
        runtime=AIRuntime(self.w)
        seen=[]
        def fake_run(canon_text,stage_instruction,raw_material,context,schema):
            seen.append((canon_text,stage_instruction,raw_material,context))
            points={k:f'{k}の回答' for k in RoutingEngine.MATERIAL_POINTS}
            return self._fake_interview_result(points=points,missing=list(RoutingEngine.MATERIAL_POINTS[:5]))
        with patch.object(AnthropicDriver,'connected',True),\
             patch.object(runtime.material_driver,'run_interview_stage',side_effect=fake_run):
            result=runtime.interview_fill_points('case#1','原文テキスト')
        self.assertEqual(len(result['missing']),3)
        self.assertIn('取材社員の正典',seen[0][0])
        self.assertEqual(seen[0][2],'原文テキスト')

    def test_interview_propose_drafts_caps_at_three(self):
        from atelier.server.routing import RoutingEngine
        runtime=AIRuntime(self.w)
        def fake_run(canon_text,stage_instruction,raw_material,context,schema):
            return self._fake_interview_result(drafts=[
                {'軸':f'軸{i}','場面':'場面','わたしがしたこと':'行動','そのあと起きたこと':'結果','この案で足りない問い':''}
                for i in range(5)
            ])
        with patch.object(AnthropicDriver,'connected',True),\
             patch.object(runtime.material_driver,'run_interview_stage',side_effect=fake_run):
            result=runtime.interview_propose_drafts('case#1','原文テキスト',{})
        self.assertEqual(len(result['drafts']),3)

    def test_interview_generalize_passes_through_public_material(self):
        from atelier.server.routing import RoutingEngine
        runtime=AIRuntime(self.w)
        def fake_run(canon_text,stage_instruction,raw_material,context,schema):
            self.assertEqual(context['媒体'],'Threads')
            # AIは「日付」を返さない。原文中の時期の表現は別枠（トップレベル）で返る。
            return self._fake_interview_result(
                public_material={'媒体と置き換え先':'Threads・お相手さまへ置き換え済み'},
                smell_flags={'場面':['常連']},
                **{RoutingEngine.MATERIAL_TIME_EXPRESSION_FIELD:'先週の火曜日'},
            )
        with patch.object(AnthropicDriver,'connected',True),\
             patch.object(runtime.material_driver,'run_interview_stage',side_effect=fake_run):
            result=runtime.interview_generalize('case#1','原文テキスト',{},'Threads',{'選択':'A'})
        self.assertNotIn('日付',result['public_material'])
        self.assertEqual(result['public_material']['媒体と置き換え先'],'Threads・お相手さまへ置き換え済み')
        self.assertEqual(result['smell_flags']['場面'],['常連'])
        self.assertEqual(result[RoutingEngine.MATERIAL_TIME_EXPRESSION_FIELD],'先週の火曜日')

    def test_interview_technical_error_is_logged_and_reraised_without_touching_case_state(self):
        # tool_use不在などの技術エラーは、2回再試行してもなおAnthropicDriver側が
        # ProviderError(technical=True)で送出してくる（_call内で吸収しきれなかった場合）。
        # ai_runtime側はこれをworkflow_eventsに記録したうえで再送出し、課長・社長の机には
        # 何も作らない（material_interviews行も作らない）。
        from atelier.server.routing import RoutingEngine
        routing=RoutingEngine(self.w)  # workflow_eventsテーブルを先に作る（実運用はserve()が先に作る）
        runtime=AIRuntime(self.w)
        case_id='posts/fixture.json#0'

        def fake_run_fails(canon_text,stage_instruction,raw_material,context,schema):
            raise ProviderError('Anthropic response did not contain a coco_atelier_interview tool_use block',
                                 attempts=[{'attempt':1,'status':'end_turn','error_type':'tool_use_missing',
                                            'output_tokens':9,'reasoning_tokens':None,'max_output_tokens':8000}])

        with patch.object(AnthropicDriver,'connected',True),\
             patch.object(runtime.material_driver,'run_interview_stage',side_effect=fake_run_fails):
            with self.assertRaises(ProviderError):
                runtime.interview_fill_points(case_id,'原文テキスト')

        self.assertEqual(routing.material_pending(),[])
        events=routing.events(case_id)
        self.assertEqual(len(events),1)
        self.assertEqual(events[0]['action'],'技術エラー')
        self.assertEqual(events[0]['detail']['エラー種別'],'tool_use_missing')

    def test_server_orchestration_sequence_end_to_end_with_mocked_claude(self):
        # server.pyの/api/material/*ハンドラが実際に行う順番（取材社員のAI呼び出し→
        # routingの決定的な記録）を、HTTPを介さずに同じ順番で再現する。
        from atelier.server.routing import RoutingEngine
        routing=RoutingEngine(self.w)
        runtime=AIRuntime(self.w)
        case_id='posts/fixture.json#0'

        def fake_run(canon_text,stage_instruction,raw_material,context,schema):
            if stage_instruction.startswith('工程2'):
                points={k:f'{k}の回答' for k in RoutingEngine.MATERIAL_POINTS}
                return self._fake_interview_result(points=points,missing=[])
            if stage_instruction.startswith('工程3'):
                return self._fake_interview_result(drafts=[
                    {'軸':'軸A','場面':'場面A','わたしがしたこと':'行動A','そのあと起きたこと':'結果A','この案で足りない問い':''},
                ])
            # 「日付」は返さない（システム側で入れる）。原文中の時期の表現は別枠で返す。
            return self._fake_interview_result(
                public_material={
                    '媒体と置き換え先':'X・仕事上の関係のまま','場面':'場面A',
                    'わたしがしたこと':'行動A','そのあと起きたこと':'結果A',
                    '【必ず残す事実】3点':['事実1','事実2','事実3'],'対応表':['原文 => 公開用'],'原文':raw_material,
                },
                **{RoutingEngine.MATERIAL_TIME_EXPRESSION_FIELD:'先週の火曜日'},
            )

        with patch.object(AnthropicDriver,'connected',True),\
             patch.object(runtime.material_driver,'run_interview_stage',side_effect=fake_run):
            # /api/material/start
            ai=runtime.interview_fill_points(case_id,'原文テキスト')
            start=routing.material_start(case_id,'X','MATERIAL','原文テキスト',ai['points'])
            routing.record_provider_usage(case_id,'工程2',ai.get('_provider'))
            self.assertEqual(start['missing'],[])

            # /api/material/propose
            summary=routing.material_summary(case_id)
            ai=runtime.interview_propose_drafts(case_id,summary['raw_material'],summary['organized_material'])
            routing.material_propose(case_id,ai['drafts'])
            routing.record_provider_usage(case_id,'工程3',ai.get('_provider'))

            # Coco selects A
            routing.material_select(case_id,'A')

            # /api/material/generalize-preview（server.pyと同じく、ここで「日付」と原文中の
            # 時期の表現をシステム側から注入する）
            summary=routing.material_summary(case_id)
            ai=runtime.interview_generalize(case_id,summary['raw_material'],summary['organized_material'],summary['department'],
                                             {'選択':'A','選んだ案':summary['drafts'][0],'追記':''})
            routing.record_provider_usage(case_id,'工程5',ai.get('_provider'))
            preview_public_material={
                **ai['public_material'],'日付':routing.material_entered_date(case_id),
                RoutingEngine.MATERIAL_TIME_EXPRESSION_FIELD:ai.get(RoutingEngine.MATERIAL_TIME_EXPRESSION_FIELD,''),
            }

            # /api/material/finalize（Cocoがそのまま確定）
            final=routing.material_finalize(case_id,preview_public_material,next_employee='X01')

        self.assertTrue(final['complete'])
        self.assertEqual(final['public_material']['日付'],routing.material_entered_date(case_id))
        self.assertEqual(final['public_material'][RoutingEngine.MATERIAL_TIME_EXPRESSION_FIELD],'先週の火曜日')
        case=routing.case(case_id)
        self.assertEqual(case['stage'],'①')
        self.assertEqual(case['employee'],'X01')
        provider_events=[e for e in routing.events(case_id) if e['action']=='provider呼び出し']
        self.assertEqual(len(provider_events),3)
        self.assertEqual({e['target'] for e in provider_events},{'工程2','工程3','工程5'})

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
    def test_atelier_origin_env_overrides_expected_origin_for_cloud(self):
        # クラウド配置（HTTPSの実ドメイン）では、ブラウザのOriginがhttp://127.0.0.1:portと
        # 一致しない。ATELIER_ORIGINで期待originを上書きできることを確認する。
        with patch.dict(os.environ,{'ATELIER_ORIGIN':'https://coco-atelier.fly.dev'}):
            req=Request(self.url+'/api/mutate',data=b'{}',
                        headers={'Authorization':'Bearer fixture-only-token','Origin':'https://coco-atelier.fly.dev'})
            with self.assertRaises(HTTPError) as e:urlopen(req)
            self.assertEqual(e.exception.code,400)  # originは通る。'key'が無いのでVALIDATION(400)。
            req2=Request(self.url+'/api/mutate',data=b'{}',
                         headers={'Authorization':'Bearer fixture-only-token','Origin':self.url})
            with self.assertRaises(HTTPError) as e2:urlopen(req2)
            self.assertEqual(e2.exception.code,403)  # ATELIER_ORIGIN設定中は旧既定originが逆に拒否される。

if __name__=='__main__':unittest.main()
