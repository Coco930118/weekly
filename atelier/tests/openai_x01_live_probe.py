"""Live OpenAI X01 probe: P1 only.

Requires OPENAI_API_KEY and ATELIER_OPENAI_LIVE=1.
P2/P3 remain unexecuted until P1 completes.
No publish/x_06/E567 code is called. Generated prose is never printed.
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
        raise SystemExit("ATELIER_OPENAI_LIVE=1 is required for the live X01 probe")
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is missing; live X01 probe did not run")


tmp=tempfile.TemporaryDirectory()
root=Path(tmp.name)
for folder in ["posts","notes","atelier/config","atelier/canon"]:
    (root/folder).mkdir(parents=True,exist_ok=True)
for path in [
    "atelier/config/employees.json",
    "atelier/config/workflow.json",
    "atelier/canon/x_post.md",
]:
    target=root/path
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_bytes((ROOT/path).read_bytes())

fixtures=[
    {
        "id":"P1",
        "platform":"X",
        "content":"",
        "quote":"",
        "theme":"現場の判断",
        "axis":"仕事・現場の「ん？」",
        "_probe_required_facts":["日付","誰が何を言ったか","わたしがしたこと","そのあと現場で起きたこと"],
        "material":"2026年10月5日、店長が「この判断は自分で決めたい」と言った。私は条件と予算だけ伝え、最後の判断を店長に任せた。そのあと、店長から「この案で進めます」と返事があった。"
    },
]
(root/"posts/index.json").write_text(json.dumps({"weeks":["probe.json"]}))
(root/"posts/probe.json").write_text(json.dumps({"week":"openai-x01-probe","posts":fixtures},ensure_ascii=False))
(root/"notes/index.json").write_text(json.dumps({"notes":[]}))

workspace=Workspace(root,root/"work.sqlite3")
routing=RoutingEngine(workspace)
runtime=AIRuntime(workspace)


def key_at(i):
    return f"posts/probe.json#{i}"


def init_case(i):
    key=key_at(i)
    routing.register_case(key,"X","X01","素材確認・事実固定")
    state=workspace.get(key)
    if not state["theme"] or not state["axis"]:
        workspace.mutate(key,state["revision"],"basis",{"theme":fixtures[i]["theme"],"axis":fixtures[i]["axis"]})
    return key


def execute_case(i):
    key=init_case(i)
    state=workspace.get(key)
    result=runtime.execute(key,"A","X01",state["revision"],state["candidates"]["A"]["revision"])
    return key,result


require_live_env()

# P1 only. P2/P3 must not run until P1 completes successfully.
key,result=execute_case(0)
if result["kind"]!="complete":
    raise AssertionError(f"P1 expected complete, got {result['kind']} / {result.get('stop_reason')}")
routing.complete(key)
routing.vp_gate(key,None)
events=routing.events(key)
desk=workspace.desk()
if not any(x.get("key")==key and x.get("department")=="X" for x in desk["completed"]):
    raise AssertionError("P1 did not appear in president desk completed posts")
if [e["action"] for e in events][-2:]!=["完成","3点確認OK"]:
    raise AssertionError("P1 route did not pass completion -> VP gate")

provider=result.get("provider",{})
print(json.dumps({
    "status":provider.get("status"),
    "reasoning_tokens":provider.get("reasoning_tokens"),
    "output_tokens":provider.get("output_tokens"),
    "max_output_tokens":provider.get("max_output_tokens"),
},ensure_ascii=False))
tmp.cleanup()
