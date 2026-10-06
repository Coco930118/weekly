"""Live OpenAI X01 probe: P1-P3 only.

Requires OPENAI_API_KEY and ATELIER_OPENAI_LIVE=1.
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


def require_live_env()

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
