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

APP_VERSION = "0.7.0"
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


INSERT_SOURCE = r'''#include <stdio.h>
#include <stdlib.h>

typedef struct Node { int data; struct Node *next; } Node;

__attribute__((noinline))
static void snap(const char *step, Node **head_var, Node **a_var, Node **s_var) {
    Node *head = *head_var, *a = *a_var, *s = *s_var;
    printf("SNAPSHOT:{\"step\":\"%s\",", step);
    printf("\"stack\":{\"head_var\":\"%p\",\"a_var\":\"%p\",\"s_var\":\"%p\"},", (void*)head_var,(void*)a_var,(void*)s_var);
    printf("\"values\":{\"head\":\"%p\",\"a\":\"%p\",\"s\":\"%p\"},", (void*)head,(void*)a,(void*)s);
    printf("\"heap\":[");
    if (a) printf("{\"name\":\"a\",\"address\":\"%p\",\"data\":%d,\"next\":\"%p\"}",(void*)a,a->data,(void*)a->next);
    if (a && s) printf(",");
    if (s) printf("{\"name\":\"s\",\"address\":\"%p\",\"data\":%d,\"next\":\"%p\"}",(void*)s,s->data,(void*)s->next);
    printf("],\"pointer_edges\":[");
    int e=0;
    if (head) { printf("{\"from\":\"head\",\"to\":\"%p\"}",(void*)head); e=1; }
    if (s && s->next) { if(e)printf(","); printf("{\"from\":\"s.next\",\"to\":\"%p\"}",(void*)s->next); }
    printf("]}\n");
}

int main(void) {
    setvbuf(stdout,NULL,_IONBF,0);
    Node *head=NULL;
    Node *a=(Node*)malloc(sizeof(Node));
    Node *s=NULL;
    if(!a) return 2;
    a->data=10; a->next=NULL; head=a;
    snap("原始链表",&head,&a,&s); /* TRACE_STAGE_1 */
    s=(Node*)malloc(sizeof(Node));
    if(!s) return 3;
    s->data=20; s->next=NULL;
    snap("已分配新结点 s",&head,&a,&s); /* TRACE_STAGE_2 */
    s->next=head;
    snap("s->next = head",&head,&a,&s); /* TRACE_STAGE_3 */
    head=s;
    snap("head = s（插入完成）",&head,&a,&s); /* TRACE_STAGE_4 */
    printf("PROGRAM_STDOUT:final head=%d -> %d\n",head->data,head->next->data);
    free(s); free(a); return 0;
}
'''

INSERT_DISPLAY = """typedef struct Node {
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

DELETE_SOURCE = r'''#include <stdio.h>
#include <stdlib.h>

typedef struct Node { int data; struct Node *next; } Node;

__attribute__((noinline))
static void snap(const char *step, Node **head_var, Node **a_var, Node **b_var, Node **p_var) {
    Node *head=*head_var, *a=*a_var, *b=*b_var, *p=*p_var;
    printf("SNAPSHOT:{\"step\":\"%s\",",step);
    printf("\"stack\":{\"head_var\":\"%p\",\"a_var\":\"%p\",\"b_var\":\"%p\",\"p_var\":\"%p\"},",(void*)head_var,(void*)a_var,(void*)b_var,(void*)p_var);
    printf("\"values\":{\"head\":\"%p\",\"a\":\"%p\",\"b\":\"%p\",\"p\":\"%p\"},",(void*)head,(void*)a,(void*)b,(void*)p);
    printf("\"heap\":[");
    if(a) printf("{\"name\":\"a\",\"address\":\"%p\",\"data\":%d,\"next\":\"%p\"}",(void*)a,a->data,(void*)a->next);
    if(a&&b) printf(",");
    if(b) printf("{\"name\":\"b\",\"address\":\"%p\",\"data\":%d,\"next\":\"%p\"}",(void*)b,b->data,(void*)b->next);
    printf("],\"pointer_edges\":[");
    int e=0;
    if(head){printf("{\"from\":\"head\",\"to\":\"%p\"}",(void*)head);e=1;}
    if(a&&a->next){if(e)printf(",");printf("{\"from\":\"a.next\",\"to\":\"%p\"}",(void*)a->next);e=1;}
    if(p){if(e)printf(",");printf("{\"from\":\"p\",\"to\":\"%p\"}",(void*)p);}
    printf("]}\n");
}

int main(void) {
    setvbuf(stdout,NULL,_IONBF,0);
    Node *a=(Node*)malloc(sizeof(Node));
    Node *b=(Node*)malloc(sizeof(Node));
    Node *head=NULL;
    Node *p=NULL;
    if(!a||!b) return 2;
    a->data=10; b->data=20; a->next=b; b->next=NULL; head=a;
    snap("原始链表 10 -> 20",&head,&a,&b,&p); /* TRACE_STAGE_1 */
    p=head;
    snap("p = head，保存待删除结点",&head,&a,&b,&p); /* TRACE_STAGE_2 */
    head=head->next;
    snap("head = head->next，链表越过原首结点",&head,&a,&b,&p); /* TRACE_STAGE_3 */
    free(p); p=NULL; a=NULL;
    snap("free(p)，原首结点释放",&head,&a,&b,&p); /* TRACE_STAGE_4 */
    printf("PROGRAM_STDOUT:final head=%d\n",head->data);
    free(b); return 0;
}
'''

DELETE_DISPLAY = """typedef struct Node {
    int data;
    struct Node *next;
} Node;

int main(void) {
    Node *a = malloc(sizeof(Node));
    Node *b = malloc(sizeof(Node));
    Node *head = a;
    Node *p = NULL;

    a->data = 10;
    a->next = b;
    b->data = 20;
    b->next = NULL;

    p = head;
    head = head->next;
    free(p);
    p = NULL;
}
"""

DEMOS = {
    "linked-list-insert": {
        "title": "单链表：头插一个新结点",
        "subtitle": "新结点 s 插入到链表头部",
        "pseudo": ["1. 建立原链表 head -> a", "2. 申请新结点 s", "3. s->next = head", "4. head = s"],
        "display_source": INSERT_DISPLAY,
        "source": INSERT_SOURCE,
        "display_stage_lines": [14,18,20,21],
        "display_stage_text": ["head = a;","s->next = NULL;","s->next = head;","head = s;"],
        "frame_vars": ["head","a","s"],
        "pointer_names": ["head","s"],
    },
    "linked-list-delete-head": {
        "title": "单链表：删除首元结点",
        "subtitle": "用临时指针 p 保存旧 head，再移动 head 并释放旧结点",
        "pseudo": ["1. 原链表 head -> a -> b", "2. p = head 保存待删除结点", "3. head = head->next 越过 a", "4. free(p) 释放原首结点"],
        "display_source": DELETE_DISPLAY,
        "source": DELETE_SOURCE,
        "display_stage_lines": [16,17,18,19],
        "display_stage_text": ["p = head;","head = head->next;","free(p);","p = NULL;"],
        "frame_vars": ["head","a","b","p"],
        "pointer_names": ["head","p"],
    },
}

LLDB_PROBE_SOURCE = r'''#include <stdio.h>
__attribute__((noinline)) static int probe(int x){volatile int y=x+1;return y;}
int main(void){int answer=probe(41);printf("%d\n",answer);return answer==42?0:1;}
'''


class DemoRequest(BaseModel):
    demo_id: str = "linked-list-insert"


def _limit_child() -> None:
    resource.setrlimit(resource.RLIMIT_CPU,(2,2))
    resource.setrlimit(resource.RLIMIT_AS,(128*1024*1024,128*1024*1024))
    resource.setrlimit(resource.RLIMIT_FSIZE,(2*1024*1024,2*1024*1024))
    resource.setrlimit(resource.RLIMIT_NOFILE,(32,32))
    resource.setrlimit(resource.RLIMIT_NPROC,(16,16))


def _clang_compile(source:str, td:str, name:str="demo") -> tuple[Path,subprocess.CompletedProcess]:
    src=Path(td)/f"{name}.c"; exe=Path(td)/name
    src.write_text(source,encoding="utf-8")
    proc=subprocess.run(["clang","-std=c11","-O0","-g","-fno-omit-frame-pointer",str(src),"-o",str(exe)],cwd=td,capture_output=True,text=True,timeout=8,env={"PATH":os.environ.get("PATH","/usr/bin:/bin")})
    return exe,proc


def _trace_lines(source:str) -> list[int]:
    lines=source.splitlines(); found=[]; stage=1
    while True:
        marker=f"TRACE_STAGE_{stage}"
        match=next((i for i,line in enumerate(lines,1) if marker in line),None)
        if match is None: break
        found.append(match); stage+=1
    return found


def _parse_program_output(text:str) -> tuple[list[dict],str]:
    snapshots=[]; stdout_lines=[]
    for line in text.splitlines():
        if "SNAPSHOT:" in line:
            try: snapshots.append(json.loads(line.split("SNAPSHOT:",1)[1].strip()))
            except json.JSONDecodeError: pass
        if "PROGRAM_STDOUT:" in line: stdout_lines.append(line.split("PROGRAM_STDOUT:",1)[1].strip())
    return snapshots,"\n".join(stdout_lines)


def _run_demo_instrumented(exe:Path,td:str) -> tuple[list[dict],str]:
    proc=subprocess.run([str(exe)],cwd=td,capture_output=True,text=True,timeout=3,preexec_fn=_limit_child,env={"PATH":"/usr/bin:/bin"})
    if proc.returncode!=0: raise HTTPException(status_code=500,detail={"runtime_error":proc.stderr[-4000:]})
    return _parse_program_output(proc.stdout)


def _extract_frame_blocks(text:str) -> list[str]:
    return [part.split("FIVEVIEW_FRAME_END",1)[0].strip() for part in text.split("FIVEVIEW_FRAME_BEGIN")[1:] if "FIVEVIEW_FRAME_END" in part]


def _run_demo_lldb(exe:Path,td:str,demo:dict) -> dict:
    trace_lines=_trace_lines(demo["source"]); count=len(trace_lines); vars_=demo["frame_vars"]
    commands=[f"breakpoint set --file demo.c --line {line}" for line in trace_lines]+["run"]
    for _ in range(count):
        commands += ["script print('FIVEVIEW_FRAME_BEGIN')","frame info",f"frame variable {' '.join(vars_)}","bt 3","script print('FIVEVIEW_FRAME_END')","continue"]
    argv=["lldb","--batch"]
    for cmd in commands: argv.extend(["-o",cmd])
    argv.append(str(exe))
    dbg=subprocess.run(argv,cwd=td,capture_output=True,text=True,timeout=18,env={"PATH":os.environ.get("PATH","/usr/bin:/bin")})
    combined=f"{dbg.stdout}\n{dbg.stderr}"; snapshots,program_stdout=_parse_program_output(combined); blocks=_extract_frame_blocks(combined)
    hits=len(re.findall(r"stop reason = breakpoint",combined,flags=re.IGNORECASE))
    for i,snap in enumerate(snapshots[:count]):
        block=blocks[i] if i<len(blocks) else ""
        snap["debugger"]={"engine":"lldb","breakpoint_hit":i+1,"compiled_source_line":trace_lines[i],"display_source_line":demo["display_stage_lines"][i],"display_source_text":demo["display_stage_text"][i],"frame_variables_read":all(name in block for name in vars_),"frame_excerpt":block[-1800:]}
    success=dbg.returncode==0 and hits>=count and len(snapshots)==count and len(blocks)>=count
    return {"success":success,"snapshots":snapshots,"stdout":program_stdout,"breakpoint_hits":hits,"frame_reads":len(blocks),"returncode":dbg.returncode,"trace":combined[-9000:]}


def _run_demo(demo_id:str) -> dict:
    demo=DEMOS.get(demo_id)
    if demo is None: raise HTTPException(status_code=404,detail="Unknown demo_id")
    with tempfile.TemporaryDirectory(prefix="fiveview-") as td:
        exe,compile_proc=_clang_compile(demo["source"],td)
        if compile_proc.returncode!=0: raise HTTPException(status_code=500,detail={"compile_error":compile_proc.stderr[-4000:]})
        lldb_result=_run_demo_lldb(exe,td,demo); count=len(demo["display_stage_lines"])
        if lldb_result["success"]:
            snapshots,program_stdout,engine,fallback=lldb_result["snapshots"],lldb_result["stdout"],"lldb-source-line",False
        else:
            snapshots,program_stdout=_run_demo_instrumented(exe,td)
            for i,snap in enumerate(snapshots[:count]): snap["debugger"]={"engine":"instrumentation-fallback","display_source_line":demo["display_stage_lines"][i],"display_source_text":demo["display_stage_text"][i]}
            engine,fallback="instrumentation-fallback",True
        return {"demo_id":demo_id,"title":demo["title"],"subtitle":demo["subtitle"],"pseudo":demo["pseudo"],"display_source":demo["display_source"],"pointer_names":demo["pointer_names"],"compiler":"clang","debug_build":True,"execution_engine":engine,"lldb_breakpoint_hits":lldb_result["breakpoint_hits"],"lldb_frame_reads":lldb_result["frame_reads"],"lldb_fallback":fallback,"lldb_trace":lldb_result["trace"],"timeline_mode":"source-line","storage_semantics":"LLDB 在 main() 的关键源码行停止并读取当前局部指针变量；结构化内存快照来自同一被调试 C 进程。","address_note":"地址来自本次 Render 容器中的真实 C 调试进程；ASLR 会使不同运行地址变化。","snapshots":snapshots,"stdout":program_stdout}


def _debugger_capability() -> dict:
    result={"available":False,"clang":False,"lldb_installed":False,"ptrace_or_launch":False,"lldb_version":"","summary":"LLDB capability test did not complete."}
    try:
        ver=subprocess.run(["lldb","--version"],capture_output=True,text=True,timeout=5,env={"PATH":os.environ.get("PATH","/usr/bin:/bin")}); result["lldb_installed"]=ver.returncode==0; result["lldb_version"]=(ver.stdout or ver.stderr).splitlines()[0][:300] if (ver.stdout or ver.stderr) else ""
    except Exception as exc:
        result["summary"]=f"lldb --version failed: {type(exc).__name__}"; return result
    with tempfile.TemporaryDirectory(prefix="fiveview-lldb-") as td:
        exe,cp=_clang_compile(LLDB_PROBE_SOURCE,td,"probe"); result["clang"]=cp.returncode==0
        if cp.returncode!=0: return result
        try: dbg=subprocess.run(["lldb","--batch","-o","breakpoint set --name probe","-o","run","-o","frame variable x","-o","bt",str(exe)],cwd=td,capture_output=True,text=True,timeout=12,env={"PATH":os.environ.get("PATH","/usr/bin:/bin")})
        except subprocess.TimeoutExpired: result["summary"]="LLDB probe timed out."; return result
        combined=f"{dbg.stdout}\n{dbg.stderr}"; stopped="stop reason = breakpoint" in combined.lower(); saw_x="x = 41" in combined
        result["ptrace_or_launch"]=stopped; result["available"]=dbg.returncode==0 and stopped and saw_x; result["summary"]="LLDB can launch, stop at breakpoints, and read frame variables." if result["available"] else "LLDB installed but source debugging not confirmed."; return result


@app.get("/")
def root(): return utf8_json({"service":"five-view-lab-backend","status":"ok","docs":"/docs"})

@app.get("/health")
def health(): return utf8_json({"status":"ok","service":"five-view-lab-backend","version":APP_VERSION})

@app.get("/api/demos")
def list_demos(): return utf8_json([{"id":k,"title":v["title"],"subtitle":v["subtitle"]} for k,v in DEMOS.items()])

@app.get("/api/debugger-capability")
def debugger_capability(): return utf8_json(_debugger_capability())

@app.post("/api/run-demo")
def run_demo(req:DemoRequest): return utf8_json(_run_demo(req.demo_id))

@app.post("/api/execute")
def execute_disabled(): raise HTTPException(status_code=403,detail="Arbitrary C execution is disabled. Use /api/run-demo with a whitelisted teaching demo.")
