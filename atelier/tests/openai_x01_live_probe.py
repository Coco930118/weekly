"""Threads01 P3 v1: VP return -> business stop -> Coco answer -> same T01 -> VP pass.

This probe intentionally remains on current Threads canon v1.
No canon/rule mutation is performed here.
"""
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))

from atelier.server.server import Workspace
from atelier.server.ai_runtime import AIRuntime
from atelier.server.routing import RoutingEngine


def require_live_env():
    if os.environ.get("ATELIER_OPENAI_LIVE")!="1":
        raise SystemExit("ATELIER_OPENAI_LIVE=1 is required")
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is missing")


tmp=tempfile.TemporaryDirectory()
root=Path(tmp.name)
for folder in ["posts","notes","atelier/config","atelier/canon"]:
    (root/folder).mkdir(parents=True,exist_ok=True)
for copy_path in [
    "atelier/config/employees.json",
    "atelier/config/workflow.json",
    "atelier/canon/threads_post.md",
    "atelier/canon/threads_post_v2.md",
    "atelier/canon/x_post_v2.md",
    "atelier/config/canon_versions.json",
]:
    target=root/copy_path
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_bytes((ROOT/copy_path).read_bytes())

material=(
    "2026年10月3日、友人から相談を受けた。"
    "私は映画を観た。"
    "次に会う予定は入れなかった。"
    "そのあと、翌週に友人から「話せる？」と連絡が来た。"
)
coco_answer="この案件は「〜のに」を使わず、素材原文どおり二文に分けてよい。逆向きの事実は足さない。"
coco_answer_fifth="5段目は読んだ人への一手として提案形で書く。Cocoがした行動のように読める形（「〜をひとつ。」で言い切る等）は使わない。"

fixtures=[{
    "id":"TP3",
    "platform":"Threads",
    "content":"",
    "quote":"",
    "theme":"距離の取り方",
    "axis":"感情と関係の「ん？」",
    "_probe_required_facts":["日付","場面","わたしがしたこと","そのあと起きたこと"],
    "material":material,
}]
(root/"posts/index.json").write_text(json.dumps({"weeks":["probe.json"]}))
(root/"posts/probe.json").write_text(json.dumps({"week":"threads-p3-v1-resume","posts":fixtures},ensure_ascii=False))
(root/"notes/index.json").write_text(json.dumps({"notes":[]}))

workspace=Workspace(root,root/"work.sqlite3")
routing=RoutingEngine(workspace)
runtime=AIRuntime(workspace)
key="posts/probe.json#0"

routing.register_case(key,"Threads","T01","素材確認・事実固定")
state=workspace.get(key)
if not state["theme"] or not state["axis"]:
    workspace.mutate(key,state["revision"],"basis",{"theme":fixtures[0]["theme"],"axis":fixtures[0]["axis"]})


def employee_run():
    state=workspace.get(key)
    result = runtime.execute(key,"A","T01",state["revision"],state["candidates"]["A"]["revision"])
    for continuation in range(3):
        if result["kind"] != "incomplete":
            break
        print(json.dumps({"process_incomplete": result.get("format_failures"), "continue_stage": result.get("continue_stage"), "retry": continuation + 1}, ensure_ascii=False), flush=True)
        state = workspace.get(key)
        result = runtime.execute(key,"A","T01",state["revision"],state["candidates"]["A"]["revision"])
    return result


def vp_run():
    routing.complete(key)
    vp=runtime.review_vp(key,"A")
    routed=routing.vp_gate(
        key,
        vp["finding"] if vp["decision"]=="戻す" else None,
        source_quote=vp.get("source_quote",""),
        post_quote=vp.get("post_quote",""),
    )
    return vp,routed


def assert_no_side_effects():
    with workspace.transaction() as db:
        codes=[row["code"] for row in db.execute("SELECT code FROM executions ORDER BY id")]
    for forbidden in {"PUBLISH","X_06","E567"}:
        if forbidden in codes:
            raise AssertionError(f"Forbidden operation recorded: {forbidden}")



require_live_env()
# v1 is sealed by the earlier successful independent live VP run.
v1 = json.loads(r'''{"Threads01_P3_v1":"completed_after_Coco_answer","coco_answer":"この案件は「〜のに」を使わず、素材原文どおり二文に分けてよい。逆向きの事実は足さない。","coco_answer_fifth":"5段目は読んだ人への一手として提案形で書く。Cocoがした行動のように読める形（「〜をひとつ。」で言い切る等）は使わない。","exception":{"direction":"型外し（Threads・1段目「〜のに」）","count":1},"first_vp":{"decision":"戻す","finding":"事実が曲がった","source_quote":"2026年10月3日、友人から相談を受けた。私は映画を観た。","post_quote":"友人から相談を受けたのに、私は映画を観た。"},"vp_history":[{"decision":"通す","finding":null,"source_quote":"","post_quote":"","body":"2026年10月3日、友人から相談を受けた。\n私は映画を観た。\n\n次に会う予定は入れなかった。\n\nそのあと、翌週に\n友人から「話せる？」と連絡が来た。\n\n次に会う予定の有無と、\n相手の気持ちの有無は、別のこと。\n\n相談を受けたあと、\n自分を急かさないために、\n映画を観る時間を選んでみては。\n\n感情はある。依存はしない。"}],"final_body":"2026年10月3日、友人から相談を受けた。\n私は映画を観た。\n\n次に会う予定は入れなかった。\n\nそのあと、翌週に\n友人から「話せる？」と連絡が来た。\n\n次に会う予定の有無と、\n相手の気持ちの有無は、別のこと。\n\n相談を受けたあと、\n自分を急かさないために、\n映画を観る時間を選んでみては。\n\n感情はある。依存はしない。","final_vp":{"decision":"通す","finding":null},"final_route_status":"Coco確認待ち","audit_counts":{"事実固定で素材の文を結合・言い換えた":1,"素材にない事実を足した":1},"canon_version":"v1","canon_changed":false,"publish":"not called","x_06":"not called","E567":"not called"}''')
historical = [
    "予定と連絡を分けて書くメモをひとつ。",
    "次に会う予定を確認する言葉をひとつ。",
    "映画を観た時間を、自分のために守る予定をひとつ。",
]
for observed in historical:
    audit = routing.record_correction(key,"Threads","素材にない事実を足した",
        diff={"location":"5段目","observed":observed,"provenance":"Final Editor2でCocoが確認した過去3回。今回の生成回数ではない"})
proposal = "5段目（Threads）／4行目の一手（X）は、読んだ人への提案であり事実の記述ではない。提案形で書かれている限り「素材にない出来事を足した」には当たらない。ただし、Coco自身の行動・予定・決意として読める書き方になっている場合は、「事実が曲がった」として戻す。"
q = routing.vp_prepare_proposal(audit["flag_id"],key,"5段目",proposal,"Threads・Xの次の新規投稿。v1完成済み案件へ遡及しない")
routing.decide_proposal(key,q["id"],"承認",rule_key="canon_v2",old_rule="公開用素材にない出来事の追加は戻す",new_rule=proposal,reason="5段目の同方向3回。Coco承認済み補足")
completed=employee_run()
if completed["kind"] != "complete":
    print(json.dumps({"v1":v1,"v2":completed,"audit":audit,"events":routing.events(key),"publish":"not called","x_06":"not called","E567":"not called"},ensure_ascii=False),flush=True)
    assert_no_side_effects()
    raise SystemExit(0)
vp,routed=vp_run()
print(json.dumps({"v1":v1,"v2":{"final_body":completed["state"]["candidates"]["A"]["fields"]["content"],"final_quote":completed["state"]["candidates"]["A"]["fields"]["quote"],"final_vp":vp,"status":routed["status"],"public_material":completed["public_material"],"source_map":completed["source_map"],"stage_outputs":completed["stage_outputs"],"candidates":completed["candidates"]},"audit":audit,"events":routing.events(key),"publish":"not called","x_06":"not called","E567":"not called"},ensure_ascii=False),flush=True)
assert_no_side_effects()
tmp.cleanup()

