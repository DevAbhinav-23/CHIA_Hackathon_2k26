"""Pilot 4's stage-2 turn, run once in this process, to record what it raises."""
import sqlite3
import sys
import traceback
from pathlib import Path
from types import SimpleNamespace

import chia.trace.profiler as profiler_module
from chia.base.tools.ChiaTool import (ChiaTool, ToolInfo, start_router,
                                      stop_router)

from circt_bug_loop import corpus, generate_task
from circt_bug_loop.contract import schema
from circt_bug_loop.llm import SpendGuard, parse_json_footer

RUN = "f12e7a3e1c7a4b839211387fc450ff78"
SEED = "b3b407b37bb255aee5cfd559dc32988b88c6e43d"
ITER = Path.home() / "bugloop-artefacts" / RUN / f"seed_{SEED}" / "iter_1"
CLONE = str(Path.home() / ".cache" / "chia-pin-smoke" / "circt")
COMMIT = "eade0de61bc5a0d2ba1b9da951b69efcab19f8ce"
MODEL = "gemini-3.8-flash"
DB = Path(__file__).resolve().parents[2] / "circt_bug_loop" / "loop.db"
#: This step's own ceiling, which is not the pilot's, and the pilot's two prices.
CAP_USD, PRICE_IN, PRICE_OUT = 3.0, 0.75, 3.75


def _serve(self) -> None:
    """Start this tool's own uvicorn MCP server here: no Ray actor, no cluster."""
    self.hostname, self.node_id = "127.0.0.1", "node-local"
    self.port = start_router(self, self.hostname)
    self.tool_info = ToolInfo(name=self.name, port=self.port, node_id=self.node_id)


def main(directory: str) -> int:
    """Render pilot 4's stage-2 prompt, run the turn once, and record the outcome."""
    profiler_module.get_profiler = lambda *a, **k: SimpleNamespace(
        enabled=False, add_info=lambda info: None)
    ChiaTool.__post_init__ = _serve
    ChiaTool.stop = lambda self: stop_router(self.name)

    answer = parse_json_footer((ITER / "llm_seed_read.jsonl").read_text("utf-8"),
                               ("root_cause_class", "sibling_sites"))
    sites = corpus.resolve_sites._chia_original(
        CLONE, COMMIT, answer["sibling_sites"][:3])["resolved"]
    probe_dir = str(Path(directory) / "probes")
    cfg = {"model_id": MODEL, "per_seed_probe_cap": 3, "timeout_seconds": 2400,
           "max_tool_iterations": {"stage_2": 12},
           "spend_guard": SpendGuard(CAP_USD, 0.0, PRICE_IN, PRICE_OUT)}
    record, = sqlite3.connect(DB).execute(
        "SELECT record_json FROM seed WHERE run_manifest_id = ? AND seed_sha = ?",
        (RUN, SEED)).fetchone()
    prompt = generate_task.render_probe_write(
        schema.from_json(record, schema.SeedRecord),
        answer["root_cause_class"], sites,
        schema.FeedbackBundle(run_manifest_id=RUN, seed_sha=SEED, arm="seeded",
                              iteration=1, entries=[], abandoned=False),
        probe_dir, cfg)
    assert prompt == (ITER / "llm_probe_write.prompt.md").read_text("utf-8"), (
        "this is not the prompt pilot 4 sent")
    tools = [generate_task.SourceReadTool(name=f"src_{SEED[:12]}_1",
                                          clone_path=CLONE, run_commit=COMMIT),
             generate_task.ProbeWriteTool(name=f"probe_{SEED[:12]}_1",
                                          probe_dir=probe_dir)]
    try:
        turn = generate_task._turn("probe_write", prompt, tools, cfg, directory,
                                   {"usage": {}, "wall_seconds": {}})
        print(f"RETURNED success={turn['success']} usage={turn['usage']} "
              f"probes={sorted(p.name for p in Path(probe_dir).iterdir())}")
    except Exception as error:
        print(f"RAISED {generate_task._failure_detail(error, directory)}")
        traceback.print_exc(file=sys.stdout)
        return 1
    finally:
        for tool in tools:
            tool.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
