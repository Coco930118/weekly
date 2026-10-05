import sys,threading,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_atelier import WorkspaceTests
from atelier.server.server import serve
from atelier.server.ai_runtime import AIRuntime
from playwright.sync_api import sync_playwright
case=WorkspaceTests();case.setUp()
os.environ['ATELIER_TOKEN']='fixture-only-token'
server=serve(0,case.root/'http.sqlite3');server.workspace=case.w;server.runtime=AIRuntime(case.w)
thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
errors=[]
try:
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
  page=browser.new_page(viewport={'width':1440,'height':1100});page.on('pageerror',lambda e:errors.append(str(e)))
  page.goto(f'http://127.0.0.1:{server.server_port}/atelier/');page.wait_for_selector('.candidates article')
  assert page.locator('#employees .employee').count()==58
  assert page.locator('.candidates article').count()==3
  cards=page.locator('.candidates article');a=cards.nth(0).bounding_box();b=cards.nth(1).bounding_box()
  assert abs(a['y']-b['y'])<5,'A/B not simultaneous horizontal'
  def dialog(d):
   if d.type=='prompt':d.accept('fixture-only-token')
   else:d.accept()
  page.on('dialog',dialog);page.get_by_role('button',name='Coco操作の認証').click()
  page.locator('input[placeholder="投稿のtheme"]').fill('fixture theme');page.locator('input[placeholder="投稿のaxis"]').fill('fixture axis')
  page.get_by_role('button',name='Cocoの基準値を保存').click();page.wait_for_function("() => document.querySelector('#editor h2').textContent.includes('revision 1')")
  card=page.locator('.candidates article').nth(0);card.locator('textarea').nth(0).fill('Coco編集テスト')
  card.get_by_role('button',name='直接編集を保存').click();page.wait_for_function("() => document.querySelector('#editor h2').textContent.includes('revision 2')")
  assert case.w.get(case.key)['candidates']['A']['fields']['content']=='Coco編集テスト'
  page.locator('.candidates article').nth(0).get_by_role('button',name='Coco採用',exact=True).click();page.wait_for_function("() => document.querySelector('#editor h2').textContent.includes('revision 3')")
  page.get_by_role('button',name='revision 0への復元diffを確認',exact=True).click();page.get_by_role('button',name='このdiffで復元').click();page.wait_for_function("() => document.querySelector('#editor h2').textContent.includes('revision 4')")
  assert case.w.get(case.key)['candidates']['A']['fields']['content']=='本文'
  page.screenshot(path='/tmp/coco-atelier-desktop.png',full_page=True)
  page.set_viewport_size({'width':390,'height':844});page.screenshot(path='/tmp/coco-atelier-mobile.png',full_page=True)
  assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
  assert not errors,errors
  browser.close()
 print('Browser checks passed: 58 employees, simultaneous A/B/C, authenticated edit, adoption, preview/revert, mobile overflow, no JS errors')
finally:
 server.shutdown();server.server_close();thread.join();case.tearDown()
