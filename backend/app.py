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

APP_VERSION = "0.9.0"
app = FastAPI(title="Data Structure Five-View Lab API", version=APP_VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://heeloo.github.io", "http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


def utf8_json(data, status_code: int = 200) -> Response:
    return Response(content=json.dumps(data, ensure_ascii=False, separators=(",", ":")), status_code=status_code, media_type="application/json; charset=utf-8")


INSERT_SOURCE = r'''#include <stdio.h>
#include <stdlib.h>
typedef struct Node { int data; struct Node *next; } Node;
__attribute__((noinline)) static void snap(const char *step, Node **head_var, Node **a_var, Node **s_var) {
    Node *head=*head_var,*a=*a_var,*s=*s_var;
    printf("SNAPSHOT:{\"step\":\"%s\",",step);
    printf("\"stack\":{\"head_var\":\"%p\",\"a_var\":\"%p\",\"s_var\":\"%p\"},",(void*)head_var,(void*)a_var,(void*)s_var);
    printf("\"values\":{\"head\":\"%p\",\"a\":\"%p\",\"s\":\"%p\"},",(void*)head,(void*)a,(void*)s);
    printf("\"heap\":[");
    if(a) printf("{\"name\":\"a\",\"address\":\"%p\",\"data\":%d,\"next\":\"%p\"}",(void*)a,a->data,(void*)a->next);
    if(a&&s) printf(",");
    if(s) printf("{\"name\":\"s\",\"address\":\"%p\",\"data\":%d,\"next\":\"%p\"}",(void*)s,s->data,(void*)s->next);
    printf("]}\n");
}
int main(void){
    setvbuf(stdout,NULL,_IONBF,0); Node *head=NULL,*a=(Node*)malloc(sizeof(Node)),*s=NULL; if(!a)return 2;
    a->data=10;a->next=NULL;head=a; snap("原始链表",&head,&a,&s); /* TRACE_STAGE_1 */
    s=(Node*)malloc(sizeof(Node));if(!s)return 3;s->data=20;s->next=NULL; snap("已分配新结点 s",&head,&a,&s); /* TRACE_STAGE_2 */
    s->next=head; snap("s->next = head",&head,&a,&s); /* TRACE_STAGE_3 */
    head=s; snap("head = s（插入完成）",&head,&a,&s); /* TRACE_STAGE_4 */
    printf("PROGRAM_STDOUT:final head=%d -> %d\n",head->data,head->next->data);free(s);free(a);return 0;
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
__attribute__((noinline)) static void snap(const char *step, Node **head_var, Node **a_var, Node **b_var, Node **p_var) {
    Node *head=*head_var,*a=*a_var,*b=*b_var,*p=*p_var;
    printf("SNAPSHOT:{\"step\":\"%s\",",step);
    printf("\"stack\":{\"head_var\":\"%p\",\"a_var\":\"%p\",\"b_var\":\"%p\",\"p_var\":\"%p\"},",(void*)head_var,(void*)a_var,(void*)b_var,(void*)p_var);
    printf("\"values\":{\"head\":\"%p\",\"a\":\"%p\",\"b\":\"%p\",\"p\":\"%p\"},",(void*)head,(void*)a,(void*)b,(void*)p);
    printf("\"heap\":[");
    if(a) printf("{\"name\":\"a\",\"address\":\"%p\",\"data\":%d,\"next\":\"%p\"}",(void*)a,a->data,(void*)a->next);
    if(a&&b) printf(",");if(b) printf("{\"name\":\"b\",\"address\":\"%p\",\"data\":%d,\"next\":\"%p\"}",(void*)b,b->data,(void*)b->next);
    printf("]}\n");
}
int main(void){
    setvbuf(stdout,NULL,_IONBF,0);Node *a=(Node*)malloc(sizeof(Node)),*b=(Node*)malloc(sizeof(Node)),*head=NULL,*p=NULL;if(!a||!b)return 2;
    a->data=10;b->data=20;a->next=b;b->next=NULL;head=a; snap("原始链表 10 -> 20",&head,&a,&b,&p); /* TRACE_STAGE_1 */
    p=head; snap("p = head，保存待删除结点",&head,&a,&b,&p); /* TRACE_STAGE_2 */
    head=head->next; snap("head = head->next，链表越过原首结点",&head,&a,&b,&p); /* TRACE_STAGE_3 */
    free(p);p=NULL;a=NULL; snap("free(p)，原首结点释放",&head,&a,&b,&p); /* TRACE_STAGE_4 */
    printf("PROGRAM_STDOUT:final head=%d\n",head->data);free(b);return 0;
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

ARRAY_SOURCE = r'''#include <stdio.h>
__attribute__((noinline)) static void snap(const char *step,int *arr,int length,int capacity,int pos,int value,int i){
    printf("SNAPSHOT:{\"step\":\"%s\",\"values\":{\"length\":%d,\"capacity\":%d,\"pos\":%d,\"value\":%d,\"i\":%d},\"array\":[",step,length,capacity,pos,value,i);
    for(int k=0;k<capacity;k++){if(k)printf(",");printf("{\"index\":%d,\"address\":\"%p\",\"value\":%d,\"active\":%s}",k,(void*)&arr[k],arr[k],k<length?"true":"false");}
    printf("]}\n");
}
int main(void){
    setvbuf(stdout,NULL,_IONBF,0);int arr[6]={10,20,30,40,0,0};int length=4,capacity=6,pos=2,value=99,i=4;
    snap("原始顺序表",arr,length,capacity,pos,value,i); /* TRACE_STAGE_1 */
    arr[4]=arr[3];i=3; snap("右移：arr[4] = arr[3]",arr,length,capacity,pos,value,i); /* TRACE_STAGE_2 */
    arr[3]=arr[2];i=2; snap("右移：arr[3] = arr[2]",arr,length,capacity,pos,value,i); /* TRACE_STAGE_3 */
    arr[2]=value;length=5; snap("写入 arr[2] = 99，插入完成",arr,length,capacity,pos,value,i); /* TRACE_STAGE_4 */
    printf("PROGRAM_STDOUT:10 20 99 30 40\n");return 0;
}
'''

ARRAY_DISPLAY = """int main(void) {
    int arr[6] = {10, 20, 30, 40, 0, 0};
    int length = 4;
    int pos = 2;
    int value = 99;
    int i = 4;

    arr[4] = arr[3];
    i = 3;
    arr[3] = arr[2];
    i = 2;
    arr[2] = value;
    length = 5;
}
"""

STACK_SOURCE = r'''#include <stdio.h>
__attribute__((noinline)) static void snap(const char *step,int *data,int top,int capacity,int value,int popped){
    printf("SNAPSHOT:{\"step\":\"%s\",\"values\":{\"top\":%d,\"capacity\":%d,\"value\":%d,\"popped\":%d},\"stack_array\":[",step,top,capacity,value,popped);
    for(int k=0;k<capacity;k++){if(k)printf(",");printf("{\"index\":%d,\"address\":\"%p\",\"value\":%d,\"occupied\":%s}",k,(void*)&data[k],data[k],k<=top?"true":"false");}
    printf("]}\n");
}
int main(void){
    setvbuf(stdout,NULL,_IONBF,0);int data[5]={10,20,0,0,0};int top=1,capacity=5,value=30,popped=-1;
    snap("原始栈：栈顶元素为 20",data,top,capacity,value,popped); /* TRACE_STAGE_1 */
    top++; snap("push：top 先上移一格",data,top,capacity,value,popped); /* TRACE_STAGE_2 */
    data[top]=value; snap("push：data[top] = 30，入栈完成",data,top,capacity,value,popped); /* TRACE_STAGE_3 */
    popped=data[top]; snap("pop：读取栈顶元素 30",data,top,capacity,value,popped); /* TRACE_STAGE_4 */
    top--; snap("pop：top 下移，30 留在物理内存但已不属于栈",data,top,capacity,value,popped); /* TRACE_STAGE_5 */
    printf("PROGRAM_STDOUT:pushed=%d popped=%d final_top=%d\n",value,popped,data[top]);return 0;
}
'''

STACK_DISPLAY = """int main(void) {
    int data[5] = {10, 20, 0, 0, 0};
    int top = 1;
    int value = 30;
    int popped = -1;

    // push(30)
    top++;
    data[top] = value;

    // pop()
    popped = data[top];
    top--;
}
"""

QUEUE_SOURCE = r'''#include <stdio.h>
static int occupied_index(int index,int front,int size,int capacity){for(int n=0;n<size;n++)if((front+n)%capacity==index)return 1;return 0;}
__attribute__((noinline)) static void snap(const char *step,int *queue,int front,int rear,int size,int capacity,int value,int removed){
    printf("SNAPSHOT:{\"step\":\"%s\",\"values\":{\"front\":%d,\"rear\":%d,\"size\":%d,\"capacity\":%d,\"value\":%d,\"removed\":%d},\"queue\":[",step,front,rear,size,capacity,value,removed);
    for(int k=0;k<capacity;k++){if(k)printf(",");int logical=-1;for(int n=0;n<size;n++)if((front+n)%capacity==k)logical=n;printf("{\"index\":%d,\"address\":\"%p\",\"value\":%d,\"occupied\":%s,\"logical_index\":%d}",k,(void*)&queue[k],queue[k],occupied_index(k,front,size,capacity)?"true":"false",logical);}
    printf("]}\n");
}
int main(void){
    setvbuf(stdout,NULL,_IONBF,0);int queue[5]={0,0,20,30,0};int front=2,rear=4,size=2,capacity=5,value=40,removed=-1;
    snap("原始循环队列：front=2，rear=4",queue,front,rear,size,capacity,value,removed); /* TRACE_STAGE_1 */
    queue[rear]=value; snap("enqueue：在 rear 指向的下标 4 写入 40",queue,front,rear,size,capacity,value,removed); /* TRACE_STAGE_2 */
    rear=(rear+1)%capacity;size++; snap("enqueue：rear 回绕到 0，入队完成",queue,front,rear,size,capacity,value,removed); /* TRACE_STAGE_3 */
    removed=queue[front]; snap("dequeue：读取 front 指向的 20",queue,front,rear,size,capacity,value,removed); /* TRACE_STAGE_4 */
    front=(front+1)%capacity;size--; snap("dequeue：front 前移，20 留在物理内存但已出队",queue,front,rear,size,capacity,value,removed); /* TRACE_STAGE_5 */
    printf("PROGRAM_STDOUT:enqueued=%d dequeued=%d front=%d rear=%d size=%d\n",value,removed,front,rear,size);return 0;
}
'''

QUEUE_DISPLAY = """int main(void) {
    int queue[5] = {0, 0, 20, 30, 0};
    int front = 2;
    int rear = 4;
    int size = 2;
    int value = 40;
    int removed = -1;

    // enqueue(40)
    queue[rear] = value;
    rear = (rear + 1) % 5;
    size++;

    // dequeue()
    removed = queue[front];
    front = (front + 1) % 5;
    size--;
}
"""

DEMOS = {
    "linked-list-insert": {"title":"单链表：头插一个新结点","subtitle":"节点与指针关系视图","category":"linked-list","renderer":"singly-linked-list","pseudo":["1. 建立原链表 head -> a","2. 申请新结点 s","3. s->next = head","4. head = s"],"display_source":INSERT_DISPLAY,"source":INSERT_SOURCE,"display_stage_lines":[14,18,20,21],"display_stage_text":["head = a;","s->next = NULL;","s->next = head;","head = s;"],"frame_vars":["head","a","s"],"pointer_names":["head","a","s"]},
    "linked-list-delete-head": {"title":"单链表：删除首元结点","subtitle":"脱链与 free 分开显示","category":"linked-list","renderer":"singly-linked-list","pseudo":["1. 原链表 head -> a -> b","2. p = head 保存待删除结点","3. head = head->next 越过 a","4. free(p) 释放原首结点"],"display_source":DELETE_DISPLAY,"source":DELETE_SOURCE,"display_stage_lines":[16,17,18,19],"display_stage_text":["p = head;","head = head->next;","free(p);","p = NULL;"],"frame_vars":["head","a","b","p"],"pointer_names":["head","a","b","p"]},
    "sequence-list-insert": {"title":"顺序表：指定位置插入","subtitle":"连续内存格、下标与元素搬移视图","category":"array","renderer":"array","pseudo":["1. 原数组 [10,20,30,40]，在下标 2 插入 99","2. 从尾部开始向右搬移 arr[3]","3. 继续搬移 arr[2]","4. arr[2] = 99，length++"],"display_source":ARRAY_DISPLAY,"source":ARRAY_SOURCE,"display_stage_lines":[7,8,10,12],"display_stage_text":["int i = 4;","arr[4] = arr[3];","arr[3] = arr[2];","arr[2] = value;"],"frame_vars":["arr","length","capacity","pos","value","i"],"pointer_names":[]},
    "stack-push-pop": {"title":"顺序栈：push 与 pop","subtitle":"栈顶移动、有效区间与残留内存值同步显示","category":"stack","renderer":"stack","pseudo":["1. 原栈自底向上为 [10, 20]","2. top++，为新元素预留栈顶位置","3. data[top] = 30，push 完成","4. popped = data[top]，读取栈顶","5. top--，pop 完成（物理槽位仍保留 30）"],"display_source":STACK_DISPLAY,"source":STACK_SOURCE,"display_stage_lines":[3,8,9,12,13],"display_stage_text":["int top = 1;","top++;","data[top] = value;","popped = data[top];","top--;"],"frame_vars":["data","top","capacity","value","popped"],"pointer_names":[]},
    "circular-queue-enqueue-dequeue": {"title":"循环队列：enqueue 与 dequeue","subtitle":"队首、队尾、有效元素与 rear 回绕同步显示","category":"queue","renderer":"circular-queue","pseudo":["1. 原队列 front=2、rear=4，逻辑内容 [20, 30]","2. queue[rear] = 40，写入待入队元素","3. rear = (rear + 1) % capacity，回绕到 0","4. removed = queue[front]，读取队首 20","5. front 前移且 size--，dequeue 完成"],"display_source":QUEUE_DISPLAY,"source":QUEUE_SOURCE,"display_stage_lines":[3,10,11,15,16],"display_stage_text":["int front = 2;","queue[rear] = value;","rear = (rear + 1) % 5;","removed = queue[front];","front = (front + 1) % 5;"],"frame_vars":["queue","front","rear","size","capacity","value","removed"],"pointer_names":[]},
}

LLDB_PROBE_SOURCE = r'''#include <stdio.h>
__attribute__((noinline)) static int probe(int x){volatile int y=x+1;return y;}
int main(void){int answer=probe(41);printf("%d\n",answer);return answer==42?0:1;}
'''

class DemoRequest(BaseModel):
    demo_id: str = "linked-list-insert"


def _limit_child()->None:
    resource.setrlimit(resource.RLIMIT_CPU,(2,2));resource.setrlimit(resource.RLIMIT_AS,(128*1024*1024,128*1024*1024));resource.setrlimit(resource.RLIMIT_FSIZE,(2*1024*1024,2*1024*1024));resource.setrlimit(resource.RLIMIT_NOFILE,(32,32));resource.setrlimit(resource.RLIMIT_NPROC,(16,16))


def _clang_compile(source:str,td:str,name:str="demo"):
    src=Path(td)/f"{name}.c";exe=Path(td)/name;src.write_text(source,encoding="utf-8")
    proc=subprocess.run(["clang","-std=c11","-O0","-g","-fno-omit-frame-pointer",str(src),"-o",str(exe)],cwd=td,capture_output=True,text=True,timeout=8,env={"PATH":os.environ.get("PATH","/usr/bin:/bin")});return exe,proc


def _trace_lines(source:str)->list[int]:
    lines=source.splitlines();found=[];stage=1
    while True:
        marker=f"TRACE_STAGE_{stage}";match=next((i for i,line in enumerate(lines,1) if marker in line),None)
        if match is None:break
        found.append(match);stage+=1
    return found


def _parse_program_output(text:str):
    snapshots=[];stdout_lines=[]
    for line in text.splitlines():
        clean=line.strip()
        if clean.startswith("SNAPSHOT:"):
            try:snapshots.append(json.loads(clean.removeprefix("SNAPSHOT:").strip()))
            except json.JSONDecodeError:pass
        if clean.startswith("PROGRAM_STDOUT:"):stdout_lines.append(clean.removeprefix("PROGRAM_STDOUT:").strip())
    return snapshots,"\n".join(stdout_lines)


def _run_demo_instrumented(exe:Path,td:str):
    proc=subprocess.run([str(exe)],cwd=td,capture_output=True,text=True,timeout=3,preexec_fn=_limit_child,env={"PATH":"/usr/bin:/bin"})
    if proc.returncode!=0:raise HTTPException(status_code=500,detail={"runtime_error":proc.stderr[-4000:]})
    return _parse_program_output(proc.stdout)


def _extract_frame_blocks(text:str)->list[str]:
    return [part.split("FIVEVIEW_FRAME_END",1)[0].strip() for part in text.split("FIVEVIEW_FRAME_BEGIN")[1:] if "FIVEVIEW_FRAME_END" in part]


def _run_demo_lldb(exe:Path,td:str,demo:dict)->dict:
    trace_lines=_trace_lines(demo["source"]);count=len(trace_lines);vars_=demo["frame_vars"]
    commands=[f"breakpoint set --file demo.c --line {line}" for line in trace_lines]+["run"]
    for _ in range(count):commands += ["script print('FIVEVIEW_FRAME_BEGIN')","frame info",f"frame variable {' '.join(vars_)}","bt 3","script print('FIVEVIEW_FRAME_END')","continue"]
    argv=["lldb","--batch"]
    for cmd in commands:argv.extend(["-o",cmd])
    argv.append(str(exe));dbg=subprocess.run(argv,cwd=td,capture_output=True,text=True,timeout=18,env={"PATH":os.environ.get("PATH","/usr/bin:/bin")})
    combined=f"{dbg.stdout}\n{dbg.stderr}";snapshots,program_stdout=_parse_program_output(combined);blocks=_extract_frame_blocks(combined);hits=min(count,len(snapshots),len(blocks))
    for i,snap in enumerate(snapshots[:count]):
        block=blocks[i] if i<len(blocks) else "";snap["debugger"]={"engine":"lldb","breakpoint_hit":i+1,"compiled_source_line":trace_lines[i],"display_source_line":demo["display_stage_lines"][i],"display_source_text":demo["display_stage_text"][i],"frame_variables_read":all(name in block for name in vars_),"frame_excerpt":block[-1800:]}
    return {"success":dbg.returncode==0 and hits>=count and len(snapshots)==count and len(blocks)>=count,"snapshots":snapshots,"stdout":program_stdout,"breakpoint_hits":hits,"frame_reads":len(blocks),"trace":combined[-9000:]}


def _normalize_snapshot(raw:dict,demo:dict)->dict:
    renderer=demo["renderer"];variables=[];objects=[];relations=[]
    if renderer=="singly-linked-list":
        values=raw.get("values",{});heap=raw.get("heap",[]);by_addr={str(n.get("address")):n for n in heap}
        for name,value in values.items():variables.append({"name":name,"type":"Node *","value":value,"kind":"pointer"})
        for node in heap:
            objects.append({"id":str(node.get("address")),"type":"Node","address":node.get("address"),"label":node.get("name"),"fields":{"data":node.get("data"),"next":node.get("next")}})
            nxt=node.get("next")
            if nxt and str(nxt) in by_addr:relations.append({"from":str(node.get("address")),"field":"next","to":str(nxt),"kind":"pointer"})
        for name in demo.get("pointer_names",[]):
            value=values.get(name)
            if value and str(value) in by_addr:relations.append({"from":name,"to":str(value),"kind":"variable-pointer"})
    elif renderer=="array":
        values=raw.get("values",{});array=raw.get("array",[])
        for name,value in values.items():variables.append({"name":name,"type":"int","value":value,"kind":"scalar"})
        for cell in array:objects.append({"id":f"cell-{cell['index']}","type":"int","address":cell.get("address"),"label":str(cell["index"]),"fields":{"value":cell.get("value"),"active":cell.get("active")}})
    elif renderer=="stack":
        values=raw.get("values",{});cells=raw.get("stack_array",[])
        for name,value in values.items():variables.append({"name":name,"type":"int","value":value,"kind":"index" if name=="top" else "scalar"})
        for cell in cells:objects.append({"id":f"stack-cell-{cell['index']}","type":"int","address":cell.get("address"),"label":str(cell["index"]),"fields":{"value":cell.get("value"),"occupied":cell.get("occupied")}})
        top=values.get("top")
        if isinstance(top,int) and top>=0:relations.append({"from":"top","to":f"stack-cell-{top}","kind":"index-pointer"})
    elif renderer=="circular-queue":
        values=raw.get("values",{});cells=raw.get("queue",[])
        for name,value in values.items():variables.append({"name":name,"type":"int","value":value,"kind":"index" if name in {"front","rear"} else "scalar"})
        for cell in cells:objects.append({"id":f"queue-cell-{cell['index']}","type":"int","address":cell.get("address"),"label":str(cell["index"]),"fields":{"value":cell.get("value"),"occupied":cell.get("occupied"),"logical_index":cell.get("logical_index")}})
        for name in ("front","rear"):
            index=values.get(name)
            if isinstance(index,int):relations.append({"from":name,"to":f"queue-cell-{index}","kind":"index-pointer"})
    raw["model"]={"schema":"five-view.snapshot.v1","variables":variables,"objects":objects,"relations":relations,"execution":raw.get("debugger",{}),"visualization":{"renderer":renderer,"category":demo["category"]}}
    return raw


def _run_demo(demo_id:str)->dict:
    demo=DEMOS.get(demo_id)
    if demo is None:raise HTTPException(status_code=404,detail="Unknown demo_id")
    with tempfile.TemporaryDirectory(prefix="fiveview-") as td:
        exe,cp=_clang_compile(demo["source"],td)
        if cp.returncode!=0:raise HTTPException(status_code=500,detail={"compile_error":cp.stderr[-4000:]})
        lr=_run_demo_lldb(exe,td,demo);count=len(demo["display_stage_lines"])
        if lr["success"]:snapshots,program_stdout,engine,fallback=lr["snapshots"],lr["stdout"],"lldb-source-line",False
        else:
            snapshots,program_stdout=_run_demo_instrumented(exe,td)
            for i,snap in enumerate(snapshots[:count]):snap["debugger"]={"engine":"instrumentation-fallback","display_source_line":demo["display_stage_lines"][i],"display_source_text":demo["display_stage_text"][i]}
            engine,fallback="instrumentation-fallback",True
        snapshots=[_normalize_snapshot(s,demo) for s in snapshots]
        return {"demo_id":demo_id,"title":demo["title"],"subtitle":demo["subtitle"],"category":demo["category"],"renderer":demo["renderer"],"pseudo":demo["pseudo"],"display_source":demo["display_source"],"pointer_names":demo.get("pointer_names",[]),"snapshot_schema":"five-view.snapshot.v1","compiler":"clang","debug_build":True,"execution_engine":engine,"lldb_breakpoint_hits":lr["breakpoint_hits"],"lldb_frame_reads":lr["frame_reads"],"lldb_fallback":fallback,"timeline_mode":"source-line","storage_semantics":"LLDB 负责真实源码断点与局部变量读取；结构化快照归一化为统一 snapshot model，再由数据结构专用 Renderer 解释。","address_note":"地址来自本次 Render 容器中的真实 C 调试进程；ASLR 会使不同运行地址变化。","snapshots":snapshots,"stdout":program_stdout}


def _debugger_capability()->dict:
    result={"available":False,"clang":False,"lldb_installed":False,"ptrace_or_launch":False,"lldb_version":"","summary":"LLDB capability test did not complete."}
    try:
        ver=subprocess.run(["lldb","--version"],capture_output=True,text=True,timeout=5,env={"PATH":os.environ.get("PATH","/usr/bin:/bin")});result["lldb_installed"]=ver.returncode==0;result["lldb_version"]=(ver.stdout or ver.stderr).splitlines()[0][:300] if (ver.stdout or ver.stderr) else ""
    except Exception as exc:result["summary"]=f"lldb --version failed: {type(exc).__name__}";return result
    with tempfile.TemporaryDirectory(prefix="fiveview-lldb-") as td:
        exe,cp=_clang_compile(LLDB_PROBE_SOURCE,td,"probe");result["clang"]=cp.returncode==0
        if cp.returncode!=0:return result
        try:dbg=subprocess.run(["lldb","--batch","-o","breakpoint set --name probe","-o","run","-o","frame variable x","-o","bt",str(exe)],cwd=td,capture_output=True,text=True,timeout=12,env={"PATH":os.environ.get("PATH","/usr/bin:/bin")})
        except subprocess.TimeoutExpired:result["summary"]="LLDB probe timed out.";return result
        combined=f"{dbg.stdout}\n{dbg.stderr}";stopped="stop reason = breakpoint" in combined.lower();saw_x="x = 41" in combined;result["ptrace_or_launch"]=stopped;result["available"]=dbg.returncode==0 and stopped and saw_x;result["summary"]="LLDB can launch, stop at breakpoints, and read frame variables." if result["available"] else "LLDB installed but source debugging not confirmed.";return result

@app.get("/")
def root():return utf8_json({"service":"five-view-lab-backend","status":"ok","docs":"/docs"})
@app.get("/health")
def health():return utf8_json({"status":"ok","service":"five-view-lab-backend","version":APP_VERSION,"snapshot_schema":"five-view.snapshot.v1"})
@app.get("/api/demos")
def list_demos():return utf8_json([{"id":k,"title":v["title"],"subtitle":v["subtitle"],"category":v["category"],"renderer":v["renderer"]} for k,v in DEMOS.items()])
@app.get("/api/debugger-capability")
def debugger_capability():return utf8_json(_debugger_capability())
@app.post("/api/run-demo")
def run_demo(req:DemoRequest):return utf8_json(_run_demo(req.demo_id))
@app.post("/api/execute")
def execute_disabled():raise HTTPException(status_code=403,detail="Arbitrary C execution is disabled. Use /api/run-demo with a whitelisted teaching demo.")
