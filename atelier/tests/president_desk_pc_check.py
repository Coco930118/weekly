import json
import os
from pathlib import Path
import sys
import tempfile
import threading

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
        {'id':'pc_x','platform':'X','content':'X本文','quote':'Xひとこと','x_short':'X短文','public_ok':True},
        {'id':'pc_t','platform':'Threads','content':'Threads本文','quote':'Threadsひとこと','public_ok':True},
    ]
},ensure_ascii=False))
(root/'notes/index.json').write_text(json.dumps({'notes':[]}))

workspace=Workspace(root,root/'work.sqlite3')
routing=RoutingEngine(workspace)

# Seed completed items and audit data.
for key in ['posts/fixture.json#0','posts/fixture.json#1']:
    workspace.mutate(key,0,'basis',{'theme':'fixture theme','axis':'fixture axis'})
    workspace.mutate(key,1,'adopt',{'candidate':'A','candidate_revision':0})

with workspace.transaction() as db:
    for dept,reason,n in [('X','事実',3),('Threads','声',2),('X短文','禁止表現',1)]:
        for i in range(n):
            db.execute('INSERT INTO corrections(key,department,reason,diff) VALUES (?,?,?,?)',
                       (f'{dept}-{i}',dept,reason,'{}'))

def seed_stop(case_id='PC_STOP',dept='X',employee='X01',stage='②'):
    routing.register_case(case_id,dept,employee,stage)
    return routing.stop(case_id,'素材不足',{
        '部門':dept,'投稿番号':case_id,'停止工程':stage,
        '不足・不明点':'日付がない',
        '現在確認できる事実':'固定テスト用の確認済み事実。Cocoへの質問と同時に比較するための内容。',
        'Cocoへの質問':'この出来事の日付はいつですか？',
    })

q=seed_stop()
proposal=workspace.enqueue_secretary('仕組み提案','副社長','X',{
    '現象':'同種修正','回数':3,'原因工程':'④','変更案':'条件を追加','影響範囲':'X部門'
},key='PC_PROPOSAL')

os.environ['ATELIER_TOKEN']=TOKEN
server=serve(0,root/'work.sqlite3');server.workspace=workspace;server.runtime=AIRuntime(workspace);server.token=TOKEN
thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
base=f'http://127.0.0.1:{server.server_port}'

def auth(page):
    page.once('dialog',lambda d:d.accept(TOKEN))
    page.get_by_role('button',name='Coco操作の認証').click()

def section_y(page,section):
    return page.locator(f'[data-section="{section}"]').bounding_box()['y']

def assert_pc_layout(page,width,height):
    page.set_viewport_size({'width':width,'height':height})
    page.goto(base+'/atelier/')
    page.wait_for_selector('[data-section="stops"]')
    auth(page)

    # M1: exact vertical order, same single content column.
    names=['stops','proposals','completed','records']
    ys=[section_y(page,n) for n in names]
    assert ys==sorted(ys),f'M1 section order broken at {width}: {ys}'
    boxes=[page.locator(f'[data-section="{n}"]').bounding_box() for n in names]
    lefts=[round(b['x']) for b in boxes]
    widths=[round(b['width']) for b in boxes]
    assert max(lefts)-min(lefts)<=2,f'M1 sections form columns at {width}: {lefts}'
    assert max(widths)-min(widths)<=2,f'M1 unequal widths suggest columns at {width}: {widths}'

    # M2: audit stays collapsed.
    records=page.locator('[data-section="records"]')
    assert records.get_attribute('open') is None,'M2 records unexpectedly open'

    # M4: no desktop-only bulk operations.
    stop=page.locator('.stop-card').first
    actions=stop.locator('.stop-actions > button').all_text_contents()
    assert actions==['回答する','このまま進める','仕組み提案へ回す'],actions
    all_buttons=page.get_by_role('button').all_text_contents()
    for forbidden in ['一括処理','全件承認','編集','削除','保留']:
        assert forbidden not in all_buttons,f'M4 forbidden desktop action: {forbidden}'

    # N1 (optional, used if space permits): question + facts visible together after opening facts.
    stop.locator('.confirmed-facts summary').click()
    question=stop.locator('.desk-field').filter(has_text='Cocoへの質問')
    facts=stop.locator('.confirmed-facts p')
    assert question.is_visible() and facts.is_visible(),'N1 question/facts not simultaneously visible'

    # N3 optional: four ranking columns fit without wrapping at PC width.
    records.locator('summary').click()
    table=records.locator('h3',has_text='X 修正ランキング').locator('xpath=following-sibling::table[1]')
    assert table.locator('th').all_text_contents()==['修正理由','回数','直近発生日','ルール変更候補']
    assert table.bounding_box()['width'] <= width-20
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    return page

errors=[]
try:
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)

        # Test both requested desktop widths against the same seed state.
        p1280=browser.new_page(viewport={'width':1280,'height':800})
        p1280.on('pageerror',lambda e:errors.append(str(e)))
        assert_pc_layout(p1280,1280,800)

        p1920=browser.new_page(viewport={'width':1920,'height':1080})
        p1920.on('pageerror',lambda e:errors.append(str(e)))
        assert_pc_layout(p1920,1920,1080)

        # O1 mobile -> PC: answer on mobile, newly opened desktop no longer shows it.
        mobile=browser.new_page(viewport={'width':390,'height':844})
        mobile.goto(base+'/atelier/');mobile.wait_for_selector('.stop-card');auth(mobile)
        mcard=mobile.locator('.stop-card').filter(has_text='PC_STOP')
        mcard.get_by_role('button',name='このまま進める').click()
        mobile.wait_for_function("() => !document.body.innerText.includes('PC_STOP')")

        after=browser.new_page(viewport={'width':1280,'height':800})
        after.goto(base+'/atelier/');after.wait_for_selector('[data-section="stops"]')
        assert 'PC_STOP' not in after.locator('[data-section="stops"]').inner_text(),'O1 mobile answer remained on newly opened PC'

        # O1 reverse: process on PC, newly opened mobile no longer shows it.
        q_reverse=seed_stop('O1_REVERSE','Threads','T03','③')
        pc_new=browser.new_page(viewport={'width':1920,'height':1080})
        pc_new.goto(base+'/atelier/');pc_new.wait_for_selector('.stop-card');auth(pc_new)
        pcard=pc_new.locator('.stop-card').filter(has_text='O1_REVERSE')
        pcard.get_by_role('button',name='このまま進める').click()
        pc_new.wait_for_function("() => !document.body.innerText.includes('O1_REVERSE')")
        mobile_after=browser.new_page(viewport={'width':390,'height':844})
        mobile_after.goto(base+'/atelier/');mobile_after.wait_for_selector('[data-section="stops"]')
        assert 'O1_REVERSE' not in mobile_after.locator('[data-section="stops"]').inner_text(),'O1 PC answer remained on newly opened mobile'

        # O2 PC remains stale while mobile processes; stale PC cannot process twice.
        q2=seed_stop('O2_STOP','X','X02','②')
        stale_pc=browser.new_page(viewport={'width':1280,'height':800})
        stale_pc.goto(base+'/atelier/');stale_pc.wait_for_selector('.stop-card');auth(stale_pc)
        stale_card=stale_pc.locator('.stop-card').filter(has_text='O2_STOP')
        mobile2=browser.new_page(viewport={'width':390,'height':844})
        mobile2.goto(base+'/atelier/');mobile2.wait_for_selector('.stop-card');auth(mobile2)
        mobile2.locator('.stop-card').filter(has_text='O2_STOP').get_by_role('button',name='このまま進める').click()
        mobile2.wait_for_function("() => !document.body.innerText.includes('O2_STOP')")

        # PC still displays stale card, but server rejects second processing.
        assert stale_card.count()==1
        stale_card.get_by_role('button',name='このまま進める').click()
        stale_pc.wait_for_timeout(200)
        with workspace.transaction() as db:
            row=db.execute('SELECT status,response FROM secretary_queue WHERE id=?',(q2['id'],)).fetchone()
        assert row['status']=='解決済み' and row['response']=='このまま進める'
        events=[e for e in routing.events('O2_STOP') if e['action']=='停止案件回答']
        assert len(events)==1,f'O2 double processed: {len(events)}'

        # M3: clear remaining proposal and verify quiet empty state, no graph/stat fill.
        workspace.resolve_secretary(proposal['id'],'却下')
        empty=browser.new_page(viewport={'width':1920,'height':1080})
        empty.goto(base+'/atelier/');empty.wait_for_selector('[data-section="stops"]')
        assert '停止なし' in empty.locator('[data-section="stops"]').inner_text()
        assert '確認待ちなし' in empty.locator('[data-section="proposals"]').inner_text()
        assert '今日は何もありません。' in empty.locator('.desk-heading').inner_text()
        assert empty.locator('.desk canvas').count()==0 and empty.locator('.desk svg').count()==0,'M3 graph/stat visualization appeared'

        assert not errors,errors
        p1280.screenshot(path='/tmp/coco-president-desk-pc-1280.png',full_page=True)
        p1920.screenshot(path='/tmp/coco-president-desk-pc-1920.png',full_page=True)
        browser.close()

    print('President desk PC checks passed: M1-M4 at 1280x800 and 1920x1080; N1/N3; O1-O2')
finally:
    server.shutdown();server.server_close();thread.join();tmp.cleanup()
