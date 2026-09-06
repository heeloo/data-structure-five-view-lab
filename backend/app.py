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

app = FastAPI(title="Data Structure Five-View Lab API", version="0.2.1")

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
    """Return JSON with an explicit UTF-8 charset to avoid mojibake in browsers/proxies."""
    return Response(
        content=json.dumps(data, ensure_ascii=False, separators=(",", ":")),
        status_code=status_code,
        media_type="application/json; charset=utf-8",
    )


# Phase 1 deliberately runs only server-owned, whitelisted teaching demos.
# It does NOT accept arbitrary C source from the browser.
DEMOS = {
    "linked-list-insert": {
        "title": "单链表：头插一个新结点",
        "pseudo": [
            "1. 创建原结点 a",
            "2. 申请新结点 s",
            "3. s->next = head",
            "4. head = s",
        ],
        "source": r'''
#include <stdio.h>
#include <stdlib.h>

typedef struct Node {
    int data;
    struct Node *next;
} Node;

static void snap(const char *step, Node *head, Node *a, Node *s) {
    printf("{\"step\":\"%s\",", step);
    printf("\"stack\":{\"head_var\":\"%p\",\"a_var\":\"%p\",\"s_var\":\"%p\"},", (void*)&head, (void*)&a, (void*)&s);
    printf("\"values\":{\"head\":\"%p\",\"a\":\"%p\",\"s\":\"%p\"},", (void*)head, (void*)a, (void*)s);
    printf("\"heap\":[");
    if (a) printf("{\"name\":\"a\",\"address\":\"%p\",\"data\":%d,\"next\":\"%p\"}", (void*)a, a->data, (void*)a->next);
    if (a && s) printf(",");
    if (s) printf("{\"name\":\"s\",\"address\":\"%p\",\"data\":%d,\"next\":\"%p\"}", (void*)s, s->data, (void*)s->next);
    printf("],");
    printf("\"pointer_edges\":[");
    if (head) printf("{\"from\":\"head\",\"to\":\"%p\"}", (void*)head);
    if (s && s->next) printf(", {\"from\":\"s.next\",\"to\":\"%p\"}", (void*)s->next);
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
    snap("原始链表", head, a, s);

    s = (Node*)malloc(sizeof(Node));
    if (!s) return 3;
    s->data = 20;
    s->next = NULL;
    snap("已分配新结点 s", head, a, s);

    s->next = head;
    snap("s->next = head", head, a, s);

    head = s;
    snap("head = s（插入完成）", head, a, s);

    printf("STDOUT: final head=%d -> %d\n", head->data, head->next->data);
    free(s);
    free(a);
    return 0;
}
''',
    }
}


class DemoRequest(BaseModel):
    demo_id: str = "linked-list-insert"


def _limit_child() -> None:
    resource.setrlimit(resource.RLIMIT_CPU, (2, 2))
    resource.setrlimit(resource.RLIMIT_AS, (128 * 1024 * 1024, 128 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_FSIZE, (2 * 1024 * 1024, 2 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
    resource.setrlimit(resource.RLIMIT_NPROC, (16, 16))


def _run_demo(demo_id: str) -> dict:
    demo = DEMOS.get(demo_id)
    if demo is None:
        raise HTTPException(status_code=404, detail="Unknown demo_id")

    with tempfile.TemporaryDirectory(prefix="fiveview-") as td:
        td_path = Path(td)
        src = td_path / "demo.c"
        exe = td_path / "demo"
        src.write_text(demo["source"], encoding="utf-8")

        compile_proc = subprocess.run(
            ["clang", "-std=c11", "-O0", "-g", "-fno-omit-frame-pointer", str(src), "-o", str(exe)],
            cwd=td,
            capture_output=True,
            text=True,
            timeout=8,
            env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
        )
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
            "compiler": "clang",
            "debug_build": True,
            "address_note": "这些地址来自本次 Render 容器内真实 C 进程；每次运行受 ASLR 影响可能不同。",
            "snapshots": snapshots,
            "stdout": "\n".join(stdout_lines),
        }


@app.get("/")
def root():
    return utf8_json({"service": "five-view-lab-backend", "status": "ok", "docs": "/docs"})


@app.get("/health")
def health():
    return utf8_json({"status": "ok", "service": "five-view-lab-backend", "version": "0.2.1"})


@app.get("/api/demos")
def list_demos():
    return utf8_json([{"id": key, "title": value["title"]} for key, value in DEMOS.items()])


@app.post("/api/run-demo")
def run_demo(req: DemoRequest):
    return utf8_json(_run_demo(req.demo_id))


@app.post("/api/execute")
def execute_disabled():
    raise HTTPException(
        status_code=403,
        detail="Arbitrary C execution is disabled. Use /api/run-demo with a whitelisted teaching demo.",
    )
