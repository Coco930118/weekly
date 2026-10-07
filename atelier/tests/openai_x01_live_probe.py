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

# Reproduce the already-confirmed P3 B state under v1.
previous_body=(
    "友人から相談を受けたのに、私は映画を観た。\n"
    "2026年10月3日だった。\n\n"
    "次に会う予定は入れなかった。\n\n"
    "そのあと翌週、友人から「話せる？」と連絡が来た。\n\n"
    "次に会う予定の有無と、相手の気持ちの有無は、別のこと。\n\n"
    "友人から相談を受けたあとを見直すため、予定と連絡を分けて書くメモをひとつ。\n\n"
    "感情はある。依存はしない。"
)
state=workspace.get(key)
workspace.save_ai_result(
    key,"A","T01",state["revision"],state["candidates"]["A"]["revision"],
    {
        "theme":state["theme"],"axis":state["axis"],"status":"OK","findings":[],
        "fields":{"content":previous_body,"quote":""},
    }
)
routing.complete(key)
first_vp=runtime.review_vp(key,"A")
if first_vp["decision"]!="戻す":
    raise AssertionError(f"Expected first VP return, got {first_vp}")
routing.vp_gate(
    key,first_vp["finding"],
    source_quote=first_vp["source_quote"],
    post_quote=first_vp["post_quote"],
)

# Preserve the two already-approved first audit counts.
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
    raise AssertionError(f"Expected separate first audit counts: {a1}, {a2}")

# Same T01 rerun after VP return must discover the v1 shape/source conflict and stop.
stopped=employee_run()
if stopped["kind"]!="stop" or stopped.get("stop_stage")!="④":
    raise AssertionError(f"Expected v1 T01 stop at ④, got {stopped}")
six={
    "部門":"Threads",
    "投稿番号":"TP3",
    "停止工程":stopped["stop_stage"],
    "不足・不明点":stopped["missing_or_unknown"],
    "現在確認できる事実":stopped.get("confirmed_facts") or "素材原文の明示事実のみ",
    "Cocoへの質問":stopped["question_for_coco"],
}
queued=routing.stop(key,stopped["stop_reason"],six)

# Coco answers the actual stop. Same employee/stage resumes.
resumed=routing.resume(key,queued["id"],coco_answer)
if resumed["employee"]!="T01" or resumed["stage"]!="素材確認・事実固定" or resumed["status"]!="稼働中":
    raise AssertionError(f"Same T01 did not resume correctly: {resumed}")

exception=routing.record_exception(
    key,"Threads","型外し（Threads・1段目「〜のに」）"
)
if exception["count"]!=1:
    raise AssertionError(f"Expected first type-off exception: {exception}")

# Current v1 canon + Coco case instruction. No v2 files exist yet.
completed=employee_run()
if completed["kind"]!="complete":
    raise AssertionError(f"T01 did not complete after Coco answer: {completed}")
if not (completed.get("completion_check") or {}).get("ok"):
    raise AssertionError(f"v1 completion gate failed: {completed.get('completion_check')}")

body=completed["state"]["candidates"]["A"]["fields"].get("content","")
if "相談を受けたのに" in body:
    raise AssertionError("Coco answer was ignored; forbidden v1 case-specific のに remains")

vp,routed=vp_run()
vp_history=[{
    "decision":vp["decision"],
    "finding":vp["finding"],
    "source_quote":vp.get("source_quote",""),
    "post_quote":vp.get("post_quote",""),
    "body":body,
}]

if vp["decision"]=="戻す":
    # This is the second VP return for this same post. Route it back to the same
    # T01 once more. A further return is the third check and must be escalated by
    # routing.vp_gate instead of looping again.
    if routed["status"]!="稼働中":
        raise AssertionError(f"Second VP return did not go back to T01: {routed}")

    completed2=employee_run()
    if completed2["kind"]!="complete":
        if completed2["kind"]=="stop":
            six2={
                "部門":"Threads",
                "投稿番号":"TP3",
                "停止工程":completed2.get("stop_stage") or routing.case(key)["stage"],
                "不足・不明点":completed2.get("missing_or_unknown") or "副社長戻し後の再作成で停止",
                "現在確認できる事実":completed2.get("confirmed_facts") or "素材原文の明示事実のみ",
                "Cocoへの質問":completed2.get("question_for_coco") or "再作成に必要な判断をお願いします。",
            }
            q2=routing.stop(key,completed2.get("stop_reason") or "事実不明",six2)
            assert_no_side_effects()
            print(json.dumps({
                "Threads01_P3_v1":"stopped_after_second_VP_return",
                "vp_history":vp_history,
                "stop":six2,
                "queue_id":q2["id"],
                "canon_version":"v1",
                "canon_changed":False,
                "publish":"not called","x_06":"not called","E567":"not called",
            },ensure_ascii=False))
            tmp.cleanup()
            raise SystemExit(0)
        raise AssertionError(f"T01 after second VP return did not complete: {completed2}")

    body2=completed2["state"]["candidates"]["A"]["fields"].get("content","")
    vp2,routed2=vp_run()
    vp_history.append({
        "decision":vp2["decision"],
        "finding":vp2["finding"],
        "source_quote":vp2.get("source_quote",""),
        "post_quote":vp2.get("post_quote",""),
        "body":body2,
    })
    if vp2["decision"]=="戻す":
        # vp_gate has already applied the approved third-check escalation.
        case2=routing.case(key)
        if case2["status"]!="停止中":
            raise AssertionError(f"Third VP return should become manager stop: {case2}")
        desk=workspace.desk()
        stop_item=next((x for x in desk["queue"] if x["kind"]=="停止案件" and x.get("key")==key),None)
        if not stop_item:
            raise AssertionError("Third VP return did not create manager stop")

        # The P1 memo plus these two VP returns are the same fifth-paragraph
        # phenomenon. Record the latter two as occurrences 2 and 3.
        a2b=routing.record_correction(
            key,"Threads","素材にない事実を足した",
            diff={
                "source":vp.get("source_quote",""),
                "observed":vp.get("post_quote",""),
                "location":"5段目",
            }
        )
        a2c=routing.record_correction(
            key,"Threads","素材にない事実を足した",
            diff={
                "source":vp2.get("source_quote",""),
                "observed":vp2.get("post_quote",""),
                "location":"5段目",
            }
        )
        if a2b["count"]!=2 or a2c["count"]!=3:
            raise AssertionError(f"Expected fifth-paragraph audit count to reach 3: {a2b}, {a2c}")

        # Coco answers the manager stop to close v1 without changing canon.
        resumed2=routing.resume(key,stop_item["id"],coco_answer_fifth)
        if resumed2["employee"]!="T01" or resumed2["status"]!="稼働中":
            raise AssertionError(f"Manager-stop answer did not resume same T01: {resumed2}")

        completed3=employee_run()
        if completed3["kind"]!="complete":
            raise AssertionError(f"T01 did not complete after fifth-paragraph Coco answer: {completed3}")
        body3=completed3["state"]["candidates"]["A"]["fields"].get("content","")
        vp3,routed3=vp_run()
        vp_history.append({
            "decision":vp3["decision"],
            "finding":vp3["finding"],
            "source_quote":vp3.get("source_quote",""),
            "post_quote":vp3.get("post_quote",""),
            "body":body3,
        })
        if vp3["decision"]!="通す":
            raise AssertionError(f"T01 v1 still did not pass VP after Coco fifth-paragraph answer: {vp3}")
        vp=vp3
        routed=routed3
        body=body3
    else:
        vp=vp2
        routed=routed2
        body=body2

if routed["status"]!="Coco確認待ち":
    raise AssertionError(f"VP pass did not reach president desk: {routed}")

# This resolves the previously pending judgment for this test case as an allowed
# per-case exception, not a canon mutation.
events=routing.events(key)
assert any(e["action"]=="例外通過記録" for e in events)
assert any(e["actor"]=="Coco" and e["action"]=="回答" for e in events)

assert_no_side_effects()

print(json.dumps({
    "Threads01_P3_v1":"completed_after_Coco_answer",
    "coco_answer":coco_answer,
    "coco_answer_fifth":coco_answer_fifth,
    "exception":{
        "direction":"型外し（Threads・1段目「〜のに」）",
        "count":exception["count"],
    },
    "first_vp":{
        "decision":first_vp["decision"],
        "finding":first_vp["finding"],
        "source_quote":first_vp["source_quote"],
        "post_quote":first_vp["post_quote"],
    },
    "vp_history":vp_history,
    "final_body":body,
    "final_vp":{
        "decision":vp["decision"],
        "finding":vp["finding"],
    },
    "final_route_status":routed["status"],
    "audit_counts":{
        "事実固定で素材の文を結合・言い換えた":1,
        "素材にない事実を足した":3,
    },
    "canon_version":"v1",
    "canon_changed":False,
    "publish":"not called","x_06":"not called","E567":"not called",
},ensure_ascii=False))
tmp.cleanup()
