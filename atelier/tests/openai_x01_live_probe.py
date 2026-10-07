"""Threads01 P3: VP return -> same T01 rerun -> VP pass.

Also verifies:
- VP evidence is source/post quote pairs.
- "事実固定で素材の文を結合・言い換えた" is count 1.
- "素材にない事実を足した" is a separate count 1 for the memo sentence.
- If the VP returns twice and a third review also returns, routing escalates to manager stop.
No canon changes and no publish/x_06/E567 calls.
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
(root/"posts/probe.json").write_text(json.dumps({"week":"openai-threads01-p3-vp-rerun","posts":fixtures},ensure_ascii=False))
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
    return runtime.execute(key,"A","T01",state["revision"],state["candidates"]["A"]["revision"])

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

# First pass: this is the previously observed P3 case. It should reach the VP,
# and the independent VP should return it for a 3-point reason.
first=employee_run()
if first["kind"]!="complete":
    raise AssertionError(f"P3 first employee run should complete for VP review, got {first['kind']}")
if not (first.get("completion_check") or {}).get("ok"):
    raise AssertionError("P3 first run did not pass mechanical completion gate")

first_body=first["state"]["candidates"]["A"]["fields"].get("content","")
first_vp,_=vp_run()
if first_vp["decision"]!="戻す":
    raise AssertionError(f"P3 expected first VP return, got {first_vp}")
if first_vp["finding"] not in {"事実が曲がった","声が混ざった","工程に戻っていない"}:
    raise AssertionError(f"Unexpected VP finding: {first_vp}")
if first_vp["source_quote"] not in material:
    raise AssertionError(f"VP source quote is not verbatim source: {first_vp}")
if first_vp["post_quote"] not in first_body:
    raise AssertionError(f"VP post quote is not verbatim post: {first_vp}")

# Record the two distinct audit reasons as first occurrences. The second item is
# the exact previously observed invented action requested by Coco.
a1=routing.record_correction(
    key,"Threads","事実固定で素材の文を結合・言い換えた",
    diff={
        "source":"私は映画を観た。次に会う予定は入れなかった。",
        "observed":"私は映画を観て、次に会う予定は入れなかった。"
    }
)
a2=routing.record_correction(
    key,"Threads","素材にない事実を足した",
    diff={
        "source":"素材原文に該当なし",
        "observed":"予定と連絡を分けて書くメモをひとつ。"
    }
)
if a1["count"]!=1 or a2["count"]!=1:
    raise AssertionError(f"Audit counts must be separate first occurrences: {a1}, {a2}")

# "相談内容なしで完成した件" remains Coco judgment pending, not a correction count.
routing.record_coco_judgment_pending(
    key,
    "相談内容なしで完成した件",
    "止まるべきだったか、相談内容を使わず進めてよかったかはCoco判断。"
)

# Rerun the same T01 after the VP return. The runtime reads the latest VP return
# pair from workflow_events and uses it only as per-case correction feedback.
attempts=[]
passed=None
for rerun_no in (1,2):
    case=routing.case(key)
    if case["employee"]!="T01" or case["status"]!="稼働中":
        raise AssertionError(f"Returned case is not assigned back to same T01: {case}")

    run=employee_run()
    if run["kind"]!="complete":
        raise AssertionError(f"T01 rerun {rerun_no} did not complete: {run.get('kind')}")
    body=run["state"]["candidates"]["A"]["fields"].get("content","")
    vp,routed=vp_run()
    attempts.append({
        "rerun":rerun_no,
        "body":body,
        "vp_decision":vp["decision"],
        "vp_finding":vp["finding"],
        "source_quote":vp.get("source_quote",""),
        "post_quote":vp.get("post_quote",""),
        "route_status":routed["status"],
    })
    if vp["decision"]=="通す":
        passed=(run,vp)
        break

    # On a return, the pair must again be real quotations.
    if vp["source_quote"] not in material or vp["post_quote"] not in body:
        raise AssertionError(f"VP rerun quote pair invalid: {vp}")

    # If this was the second return, the next review is the allowed third check.
    # A third return would be routed to manager stop by vp_gate; do not bypass it.

if passed is None:
    case=routing.case(key)
    if case["status"]=="停止中":
        desk=workspace.desk()
        stop=next((x for x in desk["queue"] if x["kind"]=="停止案件" and x.get("key")==key),None)
        raise AssertionError(
            "T01 was not cleared by VP; third return correctly escalated to manager stop: "
            + json.dumps(stop,ensure_ascii=False)
        )
    raise AssertionError(f"T01 was not cleared by VP after reruns: {attempts}")

final_run,final_vp=passed
final_body=final_run["state"]["candidates"]["A"]["fields"].get("content","")
case=routing.case(key)
if case["status"]!="Coco確認待ち":
    raise AssertionError(f"VP pass did not route to Coco: {case}")

# Confirm audit categories remain separate and both are count 1.
summary=workspace.audit_summary()["rankings"]
counts={(x["department"],x["reason"]):x["count"] for x in summary}
if counts.get(("Threads","事実固定で素材の文を結合・言い換えた"))!=1:
    raise AssertionError(f"Fact-rephrase count mismatch: {counts}")
if counts.get(("Threads","素材にない事実を足した"))!=1:
    raise AssertionError(f"Invented-fact count mismatch: {counts}")

events=routing.events(key)
if not any(e["action"]=="Coco判断待ち" and e["detail"].get("issue")=="相談内容なしで完成した件" for e in events):
    raise AssertionError("Coco judgment pending record missing")

assert_no_side_effects()

print(json.dumps({
    "Threads01_P3":"passed_after_VP_return",
    "first_vp":{
        "decision":first_vp["decision"],
        "finding":first_vp["finding"],
        "source_quote":first_vp["source_quote"],
        "post_quote":first_vp["post_quote"],
    },
    "reruns":attempts,
    "final_body":final_body,
    "final_vp":"通す",
    "final_route_status":case["status"],
    "audit_counts":{
        "事実固定で素材の文を結合・言い換えた":1,
        "素材にない事実を足した":1,
    },
    "coco_judgment_pending":"相談内容なしで完成した件",
    "canon_changed":False,
    "publish":"not called","x_06":"not called","E567":"not called",
},ensure_ascii=False))
tmp.cleanup()
