import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
from urllib.error import HTTPError
from urllib.request import urlopen

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from atelier.server.server import Workspace,serve
from atelier.server.ai_runtime import AIRuntime
from atelier.server.routing import RoutingEngine
from playwright.sync_api import sync_playwright

TOKEN='fixture-only-token'

tmp=tempfile.TemporaryDirectory()
root=Path(tmp.name)
for folder in ['posts','notes','atelier/config']:
    (root/folder).mkdir(parents=True,exist_ok=True)
for name in ['employees.json','workflow.json']:
    (root/'atelier/config'/name).write_bytes((ROOT/'atelier/config'/name).read_bytes())

(root/'posts/index.json').write_text(json.dumps({'weeks':['fixture.json']}))
(root/'posts/fixture.json').write_text(json.dumps({
    'week':'fixture',
    'posts':[
        {'id':'desk_x','platform':'X','content':'X本文','quote':'Xひとこと','x_short':'X短文','public_ok':True},
        {'id':'desk_t','platform':'Threads','content':'Threads本文','quote':'Threadsひとこと','public_ok':True},
    ]
},ensure_ascii=False))
(root/'notes/index.json').write_text(json.dumps({'notes':[]}))

workspace=Workspace(root,root/'work.sqlite3')
routing=RoutingEngine(workspace)
xkey='posts/fixture.json#0';tkey='posts/fixture.json#1'

# Completed items: X yields X + X短文, Threads yields Threads.
for key in [xkey,tkey]:
    workspace.mutate(key,0,'basis',{'theme':'fixture theme','axis':'fixture axis'})
    workspace.mutate(key,1,'adopt',{'candidate':'A','candidate_revision':0})

# G/H seed: three stop items and one proposal.
for case_id,dept,employee,stage,issue,question in [
    ('G_STOP_1','X','X01','②','日付がない','この出来事の日付はいつですか？'),
    ('H_STOP_2','Threads','T03','③','事実が矛盾','どちらが実際の事実ですか？'),
    ('H_STOP_3','X','X05','素材確認','写真の指示は担当外','写真対応を別工程にしますか？'),
]:
    routing.register_case(case_id,dept,employee,stage)
    routing.stop(case_id,'素材不足' if case_id!='H_STOP_3' else '指示外',{
        '部門':dept,'投稿番号':case_id,'停止工程':stage,'不足・不明点':issue,
        '現在確認できる事実':'固定テスト用の確認済み事実','Cocoへの質問':question,
    })

proposal=workspace.enqueue_secretary('仕組み提案','副社長','X',{
    '現象':'4行目が予定に見える','回数':3,'原因工程':'④',
    '変更案':'予定表現を禁止条件へ追加','影響範囲':'X部門',
    '旧ルール':'現行④','新ルール':'予定表現を禁止','理由':'同種修正3回',
})

# K seed.
with workspace.transaction() as db:
    for dept,reason,n in [('X','事実',3),('Threads','声',2),('X短文','禁止表現',1)]:
        for i in range(n):
            db.execute('INSERT INTO corrections(key,department,reason,diff) VALUES (?,?,?,?)',
                       (f'{dept}-{i}',dept,reason,json.dumps({'before':'旧','after':'新'},ensure_ascii=False)))
    for dept,direction,n in [('X','過去ルールと逆方向',3),('Threads','距離表現の例外',1),('X短文','片側選択の例外',2)]:
        for i in range(n):
            db.execute('INSERT INTO exceptions(key,department,note) VALUES (?,?,?)',
                       (f'{dept}-ex-{i}',dept,direction))

# L4: event targeted to Coco but not in secretary queue must not surface.
routing.register_case('L4_GHOST','X','X11','④')
with workspace.transaction() as db:
    routing._event(db,'L4_GHOST','副社長','テスト直送','Coco',note='秘書キュー外')

os.environ['ATELIER_TOKEN']=TOKEN
server=serve(0,root/'work.sqlite3');server.workspace=workspace;server.runtime=AIRuntime(workspace);server.token=TOKEN
thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
base=f'http://127.0.0.1:{server.server_port}'

dialog_pages=set()
def auth(page):
    key=id(page)
    if key not in dialog_pages:
        def dialog(d):
            if d.type=='prompt': d.accept(TOKEN)
            else: d.accept()
        page.on('dialog',dialog)
        dialog_pages.add(key)
    page.get_by_role('button',name='Coco操作の認証').click()

def action_names(card):
    return card.locator('.stop-actions > button').all_text_contents()

errors=[]
try:
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        # Mobile first.
        page=browser.new_page(viewport={'width':390,'height':844})
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(base+'/atelier/')
        page.wait_for_selector('[data-section="stops"]')
        auth(page)

        # G1-G3.
        stops=page.locator('[data-section="stops"]')
        assert '停止中（3）' in stops.locator('h2').inner_text()
        first=stops.locator('.stop-card').first
        visible=first.locator('.desk-field').all_text_contents()
        assert len(visible)==5 and all(x.strip() for x in visible)
        assert first.bounding_box()['y']+first.bounding_box()['height'] <= 844, 'G2 first stop card not readable in first viewport'
        records=page.locator('[data-section="records"]')
        assert not records.get_attribute('open'), 'G3 records must start closed'

        # H4 exactly three initial stop operations.
        assert action_names(first)==['回答する','このまま進める','仕組み提案へ回す']

        # H1 answer: one input, queue disappears, event returns to manager.
        first.get_by_role('button',name='回答する').click()
        assert first.locator('textarea[aria-label="Cocoの回答"]').count()==1
        first.locator('textarea[aria-label="Cocoの回答"]').fill('2026年10月5日です')
        first.get_by_role('button',name='送信').click()
        page.wait_for_function("() => document.querySelector('[data-section=stops] h2').textContent.includes('2')")
        assert page.evaluate('scrollY')==0
        ev=routing.events('G_STOP_1')
        assert any(e['actor']=='秘書' and e['action']=='回答返却' and e['target']=='課長' for e in ev)

        # H2 no confirmation dialog and disappears.
        second=page.locator('.stop-card').first
        assert 'H_STOP_2' in second.inner_text()
        second.get_by_role('button',name='このまま進める').click()
        page.wait_for_function("() => document.querySelector('[data-section=stops] h2').textContent.includes('1')")
        assert page.evaluate('scrollY')==0
        assert any(e['action']=='停止案件回答' for e in routing.events('H_STOP_2'))

        # H3: route to VP then inject fixed VP response, so it appears in confirmation.
        third=page.locator('.stop-card').first
        third.get_by_role('button',name='仕組み提案へ回す').click()
        page.wait_for_function("() => document.querySelector('[data-section=stops] h2').textContent.includes('0')")
        with workspace.transaction() as db:
            row=db.execute("SELECT id FROM improvement_flags WHERE 0").fetchone()
        fixed=workspace.enqueue_secretary('仕組み提案','副社長','X',{
            '現象':'写真指示が担当外','回数':1,'原因工程':'素材確認',
            '変更案':'写真対応の担当工程を別途定義','影響範囲':'X部門'
        },key='H_STOP_3')
        page.reload();page.wait_for_selector('[data-section="proposals"]');auth(page)
        assert '確認待ち（2）' in page.locator('[data-section="proposals"] h2').inner_text()

        # G4 after clearing waiting items: today nothing, no red.
        # First test I1/I2 on original proposal.
        proposal_card=page.locator('.proposal-card').filter(has_text='4行目が予定に見える')
        labels=proposal_card.locator('.desk-field > span').all_text_contents()
        assert labels==['現象','回数','原因工程','変更案','影響範囲']
        proposal_card.get_by_role('button',name='承認').click()
        page.wait_for_timeout(100)
        audit=workspace.audit_summary()
        approved=[r for r in audit['rule_changes'] if r['coco_approval']=='承認'][0]
        assert all(approved[k] for k in ['old_rule','new_rule','reason','coco_approval','approval_date','effective_from','impact'])
        assert approved['effective_from']=='次の新規案件'

        # I3 reject fixed proposal, history remains and rule not applied.
        remaining=page.locator('.proposal-card').first
        remaining.get_by_role('button',name='却下').click()
        page.wait_for_function("() => document.querySelector('[data-section=proposals] h2').textContent.includes('0')")
        rejected=[r for r in workspace.audit_summary()['rule_changes'] if r['coco_approval']=='却下'][0]
        assert rejected['effective_from']=='適用なし'
        assert '今日は何もありません。' in page.locator('.desk-heading').inner_text()
        assert '停止なし' in page.locator('[data-section=stops]').inner_text()
        assert '確認待ちなし' in page.locator('[data-section=proposals]').inner_text()
        assert page.locator('.desk').evaluate("e => getComputedStyle(e).color") != 'rgb(255, 0, 0)'

        # J1 grouped completed posts.
        for dept in ['X','Threads','X短文']:
            group=page.locator('.completed-group').filter(has_text=dept).first
            assert group.count()==1 and '（1）' in group.locator('summary').inner_text()

        # J2/J3 open X, reason is select-only, save logs before/after.
        xbutton=page.locator('.completed-link[data-department="X"]').first
        xbutton.click();page.wait_for_selector('#editor .candidates article')
        editor=page.locator('#editor')
        reason=editor.locator('select[aria-label="修正理由カテゴリ"]').first
        options=reason.locator('option').all_text_contents()
        assert '停止中の直接修正' in options and 'その他' not in options
        card=editor.locator('.candidates article').first
        card.locator('textarea').first.fill('Cocoがブラウザで直接修正')
        reason.select_option(label='事実')
        card.get_by_role('button',name='直接編集を保存').click()
        page.wait_for_function("() => document.querySelector('#editor h2').textContent.includes('revision 3')")
        row=[r for r in workspace.audit_summary()['rankings'] if r['department']=='X' and r['reason']=='事実'][0]
        assert row['count']>=4
        with workspace.transaction() as db:
            diff=json.loads(db.execute("SELECT diff FROM corrections WHERE key=? ORDER BY id DESC LIMIT 1",(xkey,)).fetchone()['diff'])
        assert diff['content']['before']=='X本文' and diff['content']['after']=='Cocoがブラウザで直接修正'

        # J4 re-adopt then final confirmation; item disappears from completed list.
        card=page.locator('#editor .candidates article').first
        card.get_by_role('button',name='Coco採用',exact=True).click()
        page.wait_for_function("() => document.querySelector('#editor h2').textContent.includes('Coco採用済み')")
        page.get_by_role('button',name='最終確認OK').click()
        page.wait_for_function("() => document.querySelector('#editor h2').textContent.includes('完了')")
        page.dispatch_event('body','atelier:desk-refresh');page.wait_for_timeout(100)
        assert page.locator('.completed-link[data-department="X"]').count()==0
        assert page.locator('.completed-link[data-department="X短文"]').count()==0

        # K1-K4.
        records=page.locator('[data-section="records"]');records.locator('summary').click()
        for dept in ['X','Threads','X短文']:
            table=records.locator('h3',has_text=f'{dept} 修正ランキング').locator('xpath=following-sibling::table[1]')
            assert table.locator('th').all_text_contents()==['修正理由','回数','直近発生日','ルール変更候補']
        assert '過去ルールと逆方向｜3回' in records.inner_text()
        history_text=records.inner_text()
        assert '承認' in history_text and '却下' in history_text and '次の新規案件' in history_text
        assert records.locator('button').count()==0

        # L1 two tabs, stale second answer cannot double-process.
        # Seed another stop.
        routing.register_case('L1_STOP','X','X12','②')
        q=routing.stop('L1_STOP','素材不足',{'部門':'X','投稿番号':'L1_STOP','停止工程':'②','不足・不明点':'素材不足','現在確認できる事実':'事実','Cocoへの質問':'確認？'})
        p1=browser.new_page(viewport={'width':390,'height':844});p2=browser.new_page(viewport={'width':390,'height':844})
        for pp in [p1,p2]:
            pp.goto(base+'/atelier/');pp.wait_for_selector('.stop-card');auth(pp)
        c1=p1.locator('.stop-card').filter(has_text='L1_STOP');c2=p2.locator('.stop-card').filter(has_text='L1_STOP')
        c1.get_by_role('button',name='このまま進める').click();p1.wait_for_timeout(100)
        c2.get_by_role('button',name='このまま進める').click();p2.wait_for_timeout(100)
        with workspace.transaction() as db:
            row=db.execute("SELECT status,response FROM secretary_queue WHERE id=?",(q['id'],)).fetchone()
        assert row['status']=='解決済み' and row['response']=='このまま進める'
        assert len([e for e in routing.events('L1_STOP') if e['action']=='停止案件回答'])==1

        # L2 close mid-answer preserves queue.
        routing.register_case('L2_STOP','X','X13','②')
        q2=routing.stop('L2_STOP','素材不足',{'部門':'X','投稿番号':'L2_STOP','停止工程':'②','不足・不明点':'素材不足','現在確認できる事実':'事実','Cocoへの質問':'確認？'})
        p3=browser.new_page(viewport={'width':390,'height':844});p3.goto(base+'/atelier/');p3.wait_for_selector('.stop-card');auth(p3)
        c3=p3.locator('.stop-card').filter(has_text='L2_STOP');c3.get_by_role('button',name='回答する').click();c3.locator('textarea').fill('入力途中');p3.close()
        with workspace.transaction() as db:
            row=db.execute("SELECT status FROM secretary_queue WHERE id=?",(q2['id'],)).fetchone()
        assert row['status']=='Coco確認待ち'

        # L3 no role screens.
        for path in ['/atelier/director/','/atelier/vice-president/','/atelier/manager/']:
            try:
                urlopen(base+path)
                raise AssertionError(f'{path} unexpectedly exists')
            except HTTPError as e:
                assert e.code==404

        # L4 event sent to Coco outside secretary queue is not rendered.
        page.reload();page.wait_for_selector('[data-section="stops"]')
        assert 'L4_GHOST' not in page.locator('.desk').inner_text()

        # H5 and mobile overflow.
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        assert not errors,errors
        page.screenshot(path='/tmp/coco-president-desk-mobile.png',full_page=True)
        browser.close()
    print('President desk browser checks passed: G1-G4, H1-H5, I1-I4, J1-J4, K1-K4, L1-L4')
finally:
    server.shutdown();server.server_close();thread.join();tmp.cleanup()
