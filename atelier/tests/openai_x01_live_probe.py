"""Threads01 P3 with independent VP gate.

Order:
1) T01 handles the implicit-hole material.
2) If completed, mechanical completion gate must pass.
3) Independent AI VP sees source + completed post + three criteria only.
4) Classify B (VP returns for fact distortion) or C (VP passes).
5) Record the first "fact-fixed text combined/rephrased" correction reason.
6) Record "completed without consultation content" as Coco judgment pending.
No canon/rule changes and no publish/x_06/E567 calls.
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

fixtures=[{
    "id":"TP3",
    "platform":"Threads",
    "content":"",
    "quote":"",
    "theme":"距離の取り方",
    "axis":"感情と関係の「ん？」",
    "_probe_required_facts":["日付","誰が何を言い何をしたか","わたしがしたこと","そのあと起きたこと"],
    "material":material,
}]
(root/"posts/index.json").write_text(json.dumps({"weeks":["probe.json"]}))
(root/"posts/probe.json").write_text(json.dumps({"week":"openai-threads01-p3-vp","posts":fixtures},ensure_ascii=False))
(root/"notes/index.json").write_text(json.dumps({"notes":[]}))

workspace=Workspace(root,root/"work.sqlite3")
routing=RoutingEngine(workspace)
runtime=AIRuntime(workspace)
key="posts/probe.json#0"

routing.register_case(key,"Threads","T01","素材確認・事実固定")
state=workspace.get(key)
if not state["theme"] or not state["axis"]:
    workspace.mutate(key,state["revision"],"basis",{"theme":fixtures[0]["theme"],"axis":fixtures[0]["axis"]})

require_live_env()
state=workspace.get(key)
result=runtime.execute(key,"A","T01",state["revision"],state["candidates"]["A"]["revision"])

with workspace.transaction() as db:
    codes=[row["code"] for row in db.execute("SELECT code FROM executions ORDER BY id")]
for forbidden in {"PUBLISH","X_06","E567"}:
    if forbidden in codes:
        raise AssertionError(f"Forbidden operation recorded: {forbidden}")

if result["kind"]=="stop":
    six={
        "部門":"Threads",
        "投稿番号":"TP3",
        "停止工程":result.get("stop_stage") or "②",
        "不足・不明点":result.get("missing_or_unknown") or "不足・不明点あり",
        "現在確認できる事実":result.get("confirmed_facts") or "素材内の明示事実のみ",
        "Cocoへの質問":result.get("question_for_coco") or "不足している事実を教えてください。",
    }
    queued=routing.stop(key,result.get("stop_reason") or "事実不明",six)
    print(json.dumps({
        "Threads01_P3_result":"A",
        "material":material,
        "employee_output":None,
        "stop_reason":result.get("stop_reason"),
        "stop_stage":result.get("stop_stage"),
        "missing_or_unknown":six["不足・不明点"],
        "question_for_coco":six["Cocoへの質問"],
        "vp_gate":"not reached because employee stopped",
        "publish":"not called","x_06":"not called","E567":"not called",
    },ensure_ascii=False))
else:
    if result["kind"]!="complete":
        raise AssertionError(f"Unexpected Threads P3 result: {result['kind']}")
    check=result.get("completion_check") or {}
    if not check.get("ok"):
        raise AssertionError(f"Threads P3 completion gate failed: {check}")

    body=result["state"]["candidates"]["A"]["fields"].get("content","")
    facts_used=result.get("facts_used",[])

    # Only after the mechanical completion gate passes does the independent VP see it.
    routing.complete(key)
    vp=runtime.review_vp(key,"A")
    if vp["decision"]=="戻す":
        routing.vp_gate(key,vp["finding"],excerpt=vp["excerpt"])
        classification="B" if vp["finding"]=="事実が曲がった" else "VP_RETURNED_OTHER"
    else:
        routing.vp_gate(key,None,excerpt=vp["excerpt"])
        classification="C"

    # Record item 2 as the first audit occurrence; do not change canon/rules.
    audit=routing.record_correction(
        key,"Threads","事実固定で素材の文を結合・言い換えた"
    )
    if audit["count"]!=1:
        raise AssertionError(f"Expected first audit count=1, got {audit}")

    # Item 3 is not judged here. It remains explicitly pending Coco's decision.
    pending=routing.record_coco_judgment_pending(
        key,
        "相談内容なしで完成した件",
        "止まるべきだったか、相談内容を使わず進めてよかったかはCoco判断。"
    )
    if not pending["recorded"]:
        raise AssertionError("Coco judgment pending issue was not recorded")

    events=routing.events(key)
    if not any(e["action"]=="3点レビュー" and e["actor"]=="副社長" for e in events):
        raise AssertionError("Independent VP review event missing")
    if not any(e["action"]=="修正記録" and e["detail"].get("reason")=="事実固定で素材の文を結合・言い換えた" for e in events):
        raise AssertionError("Fact-fixed rephrase audit event missing")
    if not any(e["action"]=="Coco判断待ち" and e["detail"].get("issue")=="相談内容なしで完成した件" for e in events):
        raise AssertionError("Coco judgment pending event missing")

    print(json.dumps({
        "Threads01_P3_result":classification,
        "material":material,
        "employee_output":body,
        "facts_used":facts_used,
        "completion_check":check,
        "vp_decision":vp["decision"],
        "vp_finding":vp["finding"],
        "vp_excerpt":vp["excerpt"],
        "audit_reason":"事実固定で素材の文を結合・言い換えた",
        "audit_count":audit["count"],
        "coco_judgment_pending":"相談内容なしで完成した件",
        "canon_changed":False,
        "publish":"not called","x_06":"not called","E567":"not called",
    },ensure_ascii=False))

tmp.cleanup()
