from __future__ import annotations

import json
import os
import re
import resource
import subprocess
import tempfile
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel

APP_VERSION = "0.5.0"
app = FastAPI(title="Data Structure Five-View Lab API", version=APP_VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://heeloo.github.io", "http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


def utf8_json(data, status_code: int = 200) -> Response:
    return Response(
        content=json.dumps(data, ensure_ascii=False, separators=(",", ":")),
        status_code=status_code,
        media_type="application/json; charset=utf-8",
    )


DEMO_SOURCE = r'''#include <stdio.h>
#include <stdlib.h>

typedef struct Node {
    int data;
    struct Node *next;
} Node;

__attribute__((noinline))
static void snap(const char *step, Node **head_var, Node **a_var, Node **s_var) {
    Node *head = *head_var;
    Node *a = *a_var;
    Node *s = *s_var;
    printf("SNAPSHOT:{\"step\":\"%s\",", step);
    printf("\"stack\":{\"head_var\":\"%p\",\"a_var\":\"%p\",\"s_var\":\"%p\"},", (void*)head_var, (void*)a_var, (void*)s_var);
    printf("\"values\":{\"head\":\"%p\",\"a\":\"%p\",\"s\":\"%p\"},", (void*)head, (void*)a, (void*)s);
    printf("\"heap\":[");
    if (a) printf("{\"name\":\"a\",\"address\":\"%p\",\"data\":%d,\"next\":\"%p\"}", (void*)a, a->data, (void*)a->next);
    if (a && s) printf(",");
    if (s) printf("{\"name\":\"s\",\"address\":\"%p\",\"data\":%d,\"next\":\"%p\"}", (void*)s, s->data, (void*)s->next);
    printf("],\"pointer_edges\":[");
    int emitted = 0;
    if (head) { printf("{\"from\":\"head\",\"to\":\"%p\"}", (void*)head); emitted = 1; }
    if (s && s->next) { if (emitted) printf(","); printf("{\"from\":\"s.next\",\"to\":\"%p\"}", (void*)s->next); }
    printf("]}\n");
}

int main(void) {
    setvbuf(stdout, NULL, _IONBF, 0);
    Node *head = NULL;
    Node *a = (Node*)malloc(sizeof(Node));
    Node *s = NULL;
    if (!a) return 2;

    a->data = 10;
    a->next = NULL;
    head = a;
    snap("原始链表", &head, &a, &s); /* TRACE_STAGE_1 */

    s = (Node*)malloc(sizeof(Node));
    if (!s) return 3;
    s->data = 20;
    s->next = NULL;
    snap("已分配新结点 s", &head, &a, &s); /* TRACE_STAGE_2 */

    s->next = head;
    snap("s->next = head", &head, &a, &s); /* TRACE_STAGE_3 */

    head = s;
    snap("head = s（插入完成）", &head, &a, &s); /* TRACE_STAGE_4 */

    printf("PROGRAM_STDOUT:final head=%d -> %d\n", head->data, head->next->data);
    free(s);
    free(a);
    return 0;
}
'''

DISPLAY_SOURCE = """typedef struct Node {
    int data;
    struct Node *next;
} Node;

int main(void) {
    Node *head = NULL;
    Node *a = malloc(sizeof(Node));
    Node *s = NULL;

    a->data = 10;
    a->next = NULL;
    head = a;

    s = malloc(sizeof(Node));
    s->data = 20;
    s->next = NULL;

    s->next = head;
    head = s;
}
"""

DISPLAY_STAGE_LINES = [14, 18, 20, 21]
DISPLAY_STAGE_TEXT = ["head = a;", "s->next = NULL;", "s->next = head;", "head = s;"]

DEMOS = {
    "linked-list-insert": {
        "title": "单链表：头插一个新结点",
        "pseudo": ["1. 创建原结点 a，并令 head = a", "2. 申请新结点 s", "3. s->next = head", "4. head = s"],
        "display_source": DISPLAY_SOURCE,
        "source": DEMO_SOURCE,
    }
}

LLDB_PROBE_SOURCE = r'''#include <stdio.h>
__attribute__((noinline)) static int probe(int x) { volatile int y = x + 1; return y; }
int main(void) { int answer = probe(41); printf("%d\n", answer); return answer == 42 ? 0 : 1; }
'''


class DemoRequest(BaseModel):
    demo_id: str = "linked-list-insert"


def _limit_child() -> None:
    resource.setrlimit(resource.RLIMIT_CPU, (2, 2))
    resource.setrlimit(resource.RLIMIT_AS, (128 * 1024 * 1024, 128 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_FSIZE, (2 * 1024 * 1024, 2 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
    resource.setrlimit(resource.RLIMIT_NPROC, (16, 16))


def _clang_compile(source: str, td: str, name: str = "demo") -> tuple[Path, subprocess.CompletedProcess]:
    src = Path(td) / f"{name}.c"
    exe = Path(td) / name
    src.write_text(source, encoding="utf-8")
    proc = subprocess.run(
        ["clang", "-std=c11", "-O0", "-g", "-fno-omit-frame-pointer", str(src), "-o", str(exe)],
        cwd=td, capture_output=True, text=True, timeout=8,
        env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
    )
    return exe, proc


def _trace_lines(source: str) -> list[int]:
    lines = source.splitlines()
    return [next(i for i, line in enumerate(lines, 1) if f"TRACE_STAGE_{stage}" in line) for stage in range(1, 5)]


def _parse_program_output(text: str) -> tuple[list[dict], str]:
    snapshots, stdout_lines = [], []
    for line in text.splitlines():
        if "SNAPSHOT:" in line:
            try:
                snapshots.append(json.loads(line.split("SNAPSHOT:", 1)[1].strip()))
            except json.JSONDecodeError:
                pass
        if "PROGRAM_STDOUT:" in line:
            stdout_lines.append(line.split("PROGRAM_STDOUT:", 1)[1].strip())
    return snapshots, "\n".join(stdout_lines)


def _run_demo_instrumented(exe: Path, td: str) -> tuple[list[dict], str]:
    proc = subprocess.run([str(exe)], cwd=td, capture_output=True, text=True, timeout=3, preexec_fn=_limit_child, env={"PATH": "/usr/bin:/bin"})
    if proc.returncode != 0:
        raise HTTPException(status_code=500, detail={"runtime_error": proc.stderr[-4000:]})
    return _parse_program_output(proc.stdout)


def _extract_frame_blocks(text: str) -> list[str]:
    marker = "FIVEVIEW_FRAME_BEGIN"
    return [part.split("FIVEVIEW_FRAME_END", 1)[0].strip() for part in text.split(marker)[1:] if "FIVEVIEW_FRAME_END" in part]


def _run_demo_lldb(exe: Path, td: str, source: str) -> dict:
    trace_lines = _trace_lines(source)
    commands = []
    for line in trace_lines:
        commands.append(f"breakpoint set --file demo.c --line {line}")
    commands.append("run")
    for i in range(4):
        commands.extend([
            "script print('FIVEVIEW_FRAME_BEGIN')",
            "frame info",
            "frame variable head a s",
            "expression -- &head",
            "expression -- &a",
            "expression -- &s",
            "bt 3",
            "script print('FIVEVIEW_FRAME_END')",
            "continue",
        ])

    argv = ["lldb", "--batch"]
    for cmd in commands:
        argv.extend(["-o", cmd])
    argv.append(str(exe))
    dbg = subprocess.run(argv, cwd=td, capture_output=True, text=True, timeout=18, env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")})
    combined = f"{dbg.stdout}\n{dbg.stderr}"
    snapshots, program_stdout = _parse_program_output(combined)
    frame_blocks = _extract_frame_blocks(combined)
    breakpoint_hits = len(re.findall(r"stop reason = breakpoint", combined, flags=re.IGNORECASE))

    for i, snap in enumerate(snapshots[:4]):
        block = frame_blocks[i] if i < len(frame_blocks) else ""
        snap["debugger"] = {
            "engine": "lldb",
            "breakpoint_hit": i + 1,
            "compiled_source_line": trace_lines[i],
            "display_source_line": DISPLAY_STAGE_LINES[i],
            "display_source_text": DISPLAY_STAGE_TEXT[i],
            "frame_variables_read": all(name in block for name in ["head", "a", "s"]),
            "frame_excerpt": block[-1800:],
        }

    success = dbg.returncode == 0 and breakpoint_hits >= 4 and len(snapshots) == 4 and len(frame_blocks) >= 4
    return {
        "success": success,
        "snapshots": snapshots,
        "stdout": program_stdout,
        "breakpoint_hits": breakpoint_hits,
        "frame_reads": len(frame_blocks),
        "returncode": dbg.returncode,
        "trace": combined[-9000:],
    }


def _run_demo(demo_id: str) -> dict:
    demo = DEMOS.get(demo_id)
    if demo is None:
        raise HTTPException(status_code=404, detail="Unknown demo_id")
    with tempfile.TemporaryDirectory(prefix="fiveview-") as td:
        exe, compile_proc = _clang_compile(demo["source"], td)
        if compile_proc.returncode != 0:
            raise HTTPException(status_code=500, detail={"compile_error": compile_proc.stderr[-4000:]})
        lldb_result = _run_demo_lldb(exe, td, demo["source"])
        if lldb_result["success"]:
            snapshots, program_stdout, engine, fallback = lldb_result["snapshots"], lldb_result["stdout"], "lldb-source-line", False
        else:
            snapshots, program_stdout = _run_demo_instrumented(exe, td)
            for i, snap in enumerate(snapshots[:4]):
                snap["debugger"] = {"engine": "instrumentation-fallback", "display_source_line": DISPLAY_STAGE_LINES[i], "display_source_text": DISPLAY_STAGE_TEXT[i]}
            engine, fallback = "instrumentation-fallback", True
        return {
            "demo_id": demo_id,
            "title": demo["title"],
            "pseudo": demo["pseudo"],
            "display_source": demo["display_source"],
            "compiler": "clang",
            "debug_build": True,
            "execution_engine": engine,
            "lldb_breakpoint_hits": lldb_result["breakpoint_hits"],
            "lldb_frame_reads": lldb_result["frame_reads"],
            "lldb_fallback": fallback,
            "lldb_trace": lldb_result["trace"],
            "timeline_mode": "source-line",
            "storage_semantics": "LLDB 在 main() 的关键源码行停止并直接读取 head、a、s；结构化快照来自同一被调试进程。",
            "address_note": "地址来自本次 Render 容器中的真实 C 调试进程；ASLR 会使不同运行地址变化。",
            "snapshots": snapshots,
            "stdout": program_stdout,
        }


def _debugger_capability() -> dict:
    result = {"available": False, "clang": False, "lldb_installed": False, "ptrace_or_launch": False, "lldb_version": "", "summary": "LLDB capability test did not complete."}
    try:
        ver = subprocess.run(["lldb", "--version"], capture_output=True, text=True, timeout=5, env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")})
        result["lldb_installed"] = ver.returncode == 0
        result["lldb_version"] = (ver.stdout or ver.stderr).splitlines()[0][:300] if (ver.stdout or ver.stderr) else ""
    except Exception as exc:
        result["summary"] = f"lldb --version failed: {type(exc).__name__}"
        return result
    with tempfile.TemporaryDirectory(prefix="fiveview-lldb-") as td:
        exe, compile_proc = _clang_compile(LLDB_PROBE_SOURCE, td, "probe")
        result["clang"] = compile_proc.returncode == 0
        if compile_proc.returncode != 0:
            return result
        try:
            dbg = subprocess.run(["lldb", "--batch", "-o", "breakpoint set --name probe", "-o", "run", "-o", "frame variable x", "-o", "bt", str(exe)], cwd=td, capture_output=True, text=True, timeout=12, env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")})
        except subprocess.TimeoutExpired:
            result["summary"] = "LLDB probe timed out."
            return result
        combined = f"{dbg.stdout}\n{dbg.stderr}"
        stopped, saw_x = "stop reason = breakpoint" in combined.lower(), "x = 41" in combined
        result["ptrace_or_launch"] = stopped
        result["available"] = dbg.returncode == 0 and stopped and saw_x
        result["summary"] = "LLDB can launch, stop at breakpoints, and read frame variables." if result["available"] else "LLDB installed but source debugging not confirmed."
        return result


@app.get("/")
def root():
    return utf8_json({"service": "five-view-lab-backend", "status": "ok", "docs": "/docs"})

@app.get("/health")
def health():
    return utf8_json({"status": "ok", "service": "five-view-lab-backend", "version": APP_VERSION})

@app.get("/api/demos")
def list_demos():
    return utf8_json([{"id": key, "title": value["title"]} for key, value in DEMOS.items()])

@app.get("/api/debugger-capability")
def debugger_capability():
    return utf8_json(_debugger_capability())

@app.post("/api/run-demo")
def run_demo(req: DemoRequest):
    return utf8_json(_run_demo(req.demo_id))

@app.post("/api/execute")
def execute_disabled():
    raise HTTPException(status_code=403, detail="Arbitrary C execution is disabled. Use /api/run-demo with a whitelisted teaching demo.")
