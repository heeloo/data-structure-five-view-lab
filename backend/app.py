from __future__ import annotations

import json
import os
import resource
import subprocess
import tempfile
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel

APP_VERSION = "0.3.0"
app = FastAPI(title="Data Structure Five-View Lab API", version=APP_VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://heeloo.github.io",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
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


DEMOS = {
    "linked-list-insert": {
        "title": "单链表：头插一个新结点",
        "pseudo": [
            "1. 创建原结点 a，并令 head = a",
            "2. 申请新结点 s",
            "3. s->next = head",
            "4. head = s",
        ],
        "display_source": """typedef struct Node {\n    int data;\n    struct Node *next;\n} Node;\n\nint main(void) {\n    Node *head = NULL;\n    Node *a = malloc(sizeof(Node));\n    Node *s = NULL;\n\n    a->data = 10;\n    a->next = NULL;\n    head = a;\n\n    s = malloc(sizeof(Node));\n    s->data = 20;\n    s->next = head;\n    head = s;\n}\n""",
        "source": r'''
#include <stdio.h>
#include <stdlib.h>

typedef struct Node {
    int data;
    struct Node *next;
} Node;

/*
 * The three Node** parameters are addresses of the local variables in main.
 * This means stack.head_var/a_var/s_var are the real main-frame storage
 * addresses, not addresses of copied parameters inside snap().
 */
static void snap(const char *step, Node **head_var, Node **a_var, Node **s_var) {
    Node *head = *head_var;
    Node *a = *a_var;
    Node *s = *s_var;

    printf("{\"step\":\"%s\",", step);
    printf("\"stack\":{\"head_var\":\"%p\",\"a_var\":\"%p\",\"s_var\":\"%p\"},", (void*)head_var, (void*)a_var, (void*)s_var);
    printf("\"values\":{\"head\":\"%p\",\"a\":\"%p\",\"s\":\"%p\"},", (void*)head, (void*)a, (void*)s);
    printf("\"heap\":[");
    if (a) printf("{\"name\":\"a\",\"address\":\"%p\",\"data\":%d,\"next\":\"%p\"}", (void*)a, a->data, (void*)a->next);
    if (a && s) printf(",");
    if (s) printf("{\"name\":\"s\",\"address\":\"%p\",\"data\":%d,\"next\":\"%p\"}", (void*)s, s->data, (void*)s->next);
    printf("],");
    printf("\"pointer_edges\":[");
    int emitted = 0;
    if (head) {
        printf("{\"from\":\"head\",\"to\":\"%p\"}", (void*)head);
        emitted = 1;
    }
    if (s && s->next) {
        if (emitted) printf(",");
        printf("{\"from\":\"s.next\",\"to\":\"%p\"}", (void*)s->next);
    }
    printf("]}\n");
}

int main(void) {
    Node *head = NULL;
    Node *a = (Node*)malloc(sizeof(Node));
    Node *s = NULL;
    if (!a) return 2;

    a->data = 10;
    a->next = NULL;
    head = a;
    snap("原始链表", &head, &a, &s);

    s = (Node*)malloc(sizeof(Node));
    if (!s) return 3;
    s->data = 20;
    s->next = NULL;
    snap("已分配新结点 s", &head, &a, &s);

    s->next = head;
    snap("s->next = head", &head, &a, &s);

    head = s;
    snap("head = s（插入完成）", &head, &a, &s);

    printf("STDOUT: final head=%d -> %d\n", head->data, head->next->data);
    free(s);
    free(a);
    return 0;
}
''',
    }
}


LLDB_PROBE_SOURCE = r'''
#include <stdio.h>

__attribute__((noinline)) static int probe(int x) {
    volatile int y = x + 1;
    return y;
}

int main(void) {
    int answer = probe(41);
    printf("%d\n", answer);
    return answer == 42 ? 0 : 1;
}
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
    td_path = Path(td)
    src = td_path / f"{name}.c"
    exe = td_path / name
    src.write_text(source, encoding="utf-8")
    proc = subprocess.run(
        ["clang", "-std=c11", "-O0", "-g", "-fno-omit-frame-pointer", str(src), "-o", str(exe)],
        cwd=td,
        capture_output=True,
        text=True,
        timeout=8,
        env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
    )
    return exe, proc


def _run_demo(demo_id: str) -> dict:
    demo = DEMOS.get(demo_id)
    if demo is None:
        raise HTTPException(status_code=404, detail="Unknown demo_id")

    with tempfile.TemporaryDirectory(prefix="fiveview-") as td:
        exe, compile_proc = _clang_compile(demo["source"], td)
        if compile_proc.returncode != 0:
            raise HTTPException(status_code=500, detail={"compile_error": compile_proc.stderr[-4000:]})

        run_proc = subprocess.run(
            [str(exe)],
            cwd=td,
            capture_output=True,
            text=True,
            timeout=3,
            preexec_fn=_limit_child,
            env={"PATH": "/usr/bin:/bin"},
        )
        if run_proc.returncode != 0:
            raise HTTPException(status_code=500, detail={"runtime_error": run_proc.stderr[-4000:]})

        snapshots = []
        stdout_lines = []
        for line in run_proc.stdout.splitlines():
            if line.startswith("STDOUT:"):
                stdout_lines.append(line.removeprefix("STDOUT:").strip())
                continue
            try:
                snapshots.append(json.loads(line))
            except json.JSONDecodeError:
                stdout_lines.append(line)

        return {
            "demo_id": demo_id,
            "title": demo["title"],
            "pseudo": demo["pseudo"],
            "display_source": demo["display_source"],
            "compiler": "clang",
            "debug_build": True,
            "storage_semantics": "stack.*_var 是 main() 局部指针变量本身的真实存储地址；values.* 是这些变量当前保存的指针值。",
            "address_note": "地址来自本次 Render 容器内真实 C 进程；每次运行受 ASLR 影响可能不同。",
            "snapshots": snapshots,
            "stdout": "\n".join(stdout_lines),
        }


def _debugger_capability() -> dict:
    result = {
        "available": False,
        "clang": False,
        "lldb_installed": False,
        "ptrace_or_launch": False,
        "lldb_version": "",
        "summary": "LLDB capability test did not complete.",
    }

    try:
        ver = subprocess.run(
            ["lldb", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
            env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
        )
        result["lldb_installed"] = ver.returncode == 0
        result["lldb_version"] = (ver.stdout or ver.stderr).splitlines()[0][:300] if (ver.stdout or ver.stderr) else ""
    except Exception as exc:
        result["summary"] = f"lldb --version failed: {type(exc).__name__}"
        return result

    with tempfile.TemporaryDirectory(prefix="fiveview-lldb-") as td:
        try:
            exe, compile_proc = _clang_compile(LLDB_PROBE_SOURCE, td, name="probe")
        except Exception as exc:
            result["summary"] = f"Clang probe failed: {type(exc).__name__}"
            return result

        result["clang"] = compile_proc.returncode == 0
        if compile_proc.returncode != 0:
            result["summary"] = "Clang could not compile the LLDB probe."
            result["stderr"] = compile_proc.stderr[-1500:]
            return result

        try:
            dbg = subprocess.run(
                [
                    "lldb",
                    "--batch",
                    "-o", "breakpoint set --name probe",
                    "-o", "run",
                    "-o", "frame variable x",
                    "-o", "bt",
                    str(exe),
                ],
                cwd=td,
                capture_output=True,
                text=True,
                timeout=12,
                env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
            )
        except subprocess.TimeoutExpired:
            result["summary"] = "LLDB probe timed out; debugger launch/ptrace may be restricted."
            return result
        except Exception as exc:
            result["summary"] = f"LLDB probe failed: {type(exc).__name__}"
            return result

        combined = f"{dbg.stdout}\n{dbg.stderr}"
        stopped = "stop reason = breakpoint" in combined.lower()
        saw_x = "(int) x = 41" in combined or "x = 41" in combined
        result["ptrace_or_launch"] = stopped
        result["available"] = dbg.returncode == 0 and stopped and saw_x
        result["summary"] = (
            "LLDB can launch the fixed debug binary, stop at a breakpoint, and read a frame variable."
            if result["available"]
            else "LLDB is installed, but breakpoint/frame-variable debugging was not confirmed in this container."
        )
        result["probe_stdout"] = dbg.stdout[-2500:]
        result["probe_stderr"] = dbg.stderr[-1500:]
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
    raise HTTPException(
        status_code=403,
        detail="Arbitrary C execution is disabled. Use /api/run-demo with a whitelisted teaching demo.",
    )
