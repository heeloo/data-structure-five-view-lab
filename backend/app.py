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
try:
    from .extended_demos import EXTENDED_DEMOS, EXTENDED_DETAILS
except ImportError:  # Render starts uvicorn from backend/ as `app:app`.
    from extended_demos import EXTENDED_DEMOS, EXTENDED_DETAILS

APP_VERSION = "1.6.0"
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

LINKED_COMPLETE_SOURCE = r'''#include <stdio.h>
#include <stdlib.h>
typedef struct Node { int data; struct Node *next; } Node;
static void print_node(const char *name,Node *n,int *first){if(!n)return;if(!*first)printf(",");*first=0;printf("{\"name\":\"%s\",\"address\":\"%p\",\"data\":%d,\"next\":\"%p\"}",name,(void*)n,n->data,(void*)n->next);}
__attribute__((noinline)) static void snap(const char *step,Node *head,Node *tail,Node *prev,Node *current,Node *next,Node *s,Node *x,int pos,Node *a,Node *b,Node *c){
    printf("SNAPSHOT:{\"step\":\"%s\",\"values\":{\"head\":\"%p\",\"tail\":\"%p\",\"prev\":\"%p\",\"current\":\"%p\",\"next\":\"%p\",\"s\":\"%p\",\"x\":\"%p\",\"pos\":%d},\"heap\":[",step,(void*)head,(void*)tail,(void*)prev,(void*)current,(void*)next,(void*)s,(void*)x,pos);int first=1;print_node("a",a,&first);print_node("b",b,&first);print_node("c",c,&first);print_node("x",x,&first);printf("]}\n");
}
static Node *make_node(int value){Node *n=(Node*)malloc(sizeof(Node));if(!n)exit(2);n->data=value;n->next=NULL;return n;}
int main(void){
    setvbuf(stdout,NULL,_IONBF,0);Node *a=make_node(10),*b=make_node(20),*c=NULL,*x=NULL,*head=a,*tail=b,*prev=NULL,*current=NULL,*next=NULL,*s=NULL;int pos=1;a->next=b;
    snap("初始链表：10 -> 20",head,tail,prev,current,next,s,x,pos,a,b,c); /* TRACE_STAGE_1 */
    s=c=make_node(30);tail->next=s;tail=s;snap("尾插 30：tail->next = s，tail 移到新结点",head,tail,prev,current,next,s,x,pos,a,b,c); /* TRACE_STAGE_2 */
    x=make_node(15);prev=head;snap("指定位置插入：prev 定位到下标 0",head,tail,prev,current,next,s,x,pos,a,b,c); /* TRACE_STAGE_3 */
    x->next=prev->next;snap("x->next = prev->next，保存后半段",head,tail,prev,current,next,s,x,pos,a,b,c); /* TRACE_STAGE_4 */
    prev->next=x;snap("prev->next = x，在下标 1 插入 15",head,tail,prev,current,next,s,x,pos,a,b,c); /* TRACE_STAGE_5 */
    prev=NULL;current=head;next=NULL;snap("开始迭代反转：prev=NULL，current=head",head,tail,prev,current,next,s,x,pos,a,b,c); /* TRACE_STAGE_6 */
    next=current->next;current->next=prev;prev=current;current=next;snap("反转结点 10：prev=10，current=15",head,tail,prev,current,next,s,x,pos,a,b,c); /* TRACE_STAGE_7 */
    next=current->next;current->next=prev;prev=current;current=next;snap("反转结点 15：prev=15，current=20",head,tail,prev,current,next,s,x,pos,a,b,c); /* TRACE_STAGE_8 */
    next=current->next;current->next=prev;prev=current;current=next;snap("反转结点 20：prev=20，current=30",head,tail,prev,current,next,s,x,pos,a,b,c); /* TRACE_STAGE_9 */
    next=current->next;current->next=prev;prev=current;current=next;snap("反转结点 30：current=NULL，prev 指向新表头",head,tail,prev,current,next,s,x,pos,a,b,c); /* TRACE_STAGE_10 */
    tail=head;head=prev;snap("反转完成：head=prev，原表头成为 tail",head,tail,prev,current,next,s,x,pos,a,b,c); /* TRACE_STAGE_11 */
    printf("PROGRAM_STDOUT:tail_insert=30 position_insert=15 reversed=30 20 15 10\n");for(Node *p=head,*q;p;p=q){q=p->next;free(p);}return 0;
}
'''

LINKED_COMPLETE_DISPLAY = """// 尾插
tail->next = s;
tail = s;

// 在下标 pos=1 插入
prev = head;
x->next = prev->next;
prev->next = x;

// 迭代反转
prev = NULL;
current = head;
while (current != NULL) {
    next = current->next;
    current->next = prev;
    prev = current;
    current = next;
}
tail = head;
head = prev;
"""

MERGE_SORTED_SOURCE = r'''#include <stdio.h>
#include <stdlib.h>
typedef struct Node { int data; struct Node *next; } Node;
static Node *g_nodes[6];

static int is_sorted(Node *head){for(Node *p=head;p&&p->next;p=p->next)if(p->data>p->next->data)return 0;return 1;}
static int has_cycle(Node *head){Node *slow=head,*fast=head;while(fast&&fast->next){slow=slow->next;fast=fast->next->next;if(slow==fast)return 1;}return 0;}
static int count_unique(Node *a,Node *b,Node *result){
    Node *roots[3]={a,b,result},*seen[6]={0};int count=0;
    for(int r=0;r<3;r++)for(Node *p=roots[r];p;p=p->next){for(int i=0;i<count;i++)if(seen[i]==p)return -1;if(count>=6)return -1;seen[count++]=p;}
    return count;
}
__attribute__((noinline)) static void snap(const char *step,Node *p1,Node *p2,Node *result,Node *tail,Node *selected,int origin,int merged_count){
    int unique=count_unique(p1,p2,result);
    printf("SNAPSHOT:{\"step\":\"%s\",",step);
    printf("\"values\":{\"result\":\"%p\",\"p1\":\"%p\",\"p2\":\"%p\",\"tail\":\"%p\",\"selected\":\"%p\",\"origin\":%d,\"merged_count\":%d,\"total_nodes\":6},",(void*)result,(void*)p1,(void*)p2,(void*)tail,(void*)selected,origin,merged_count);
    printf("\"checks\":{\"all_nodes_accounted\":%s,\"unique_nodes\":%d,\"result_sorted\":%s,\"result_acyclic\":%s,\"allocations_during_merge\":0},",unique==6?"true":"false",unique,is_sorted(result)?"true":"false",has_cycle(result)?"false":"true");
    printf("\"heap\":[");
    for(int i=0;i<6;i++){Node *n=g_nodes[i];if(i)printf(",");printf("{\"name\":\"%c%d\",\"address\":\"%p\",\"data\":%d,\"next\":\"%p\"}",i<3?'A':'B',i<3?i+1:i-2,(void*)n,n->data,(void*)n->next);}
    printf("]}\n");
}
static Node *make_node(int value){Node *n=(Node*)malloc(sizeof(Node));if(!n)exit(2);n->data=value;n->next=NULL;return n;}
static Node *merge_sorted(Node *head1,Node *head2){
    Node *p1=head1,*p2=head2,*result=NULL,*tail=NULL,*selected=NULL,*next=NULL;int origin=0,merged_count=0;
    snap("初始：两条升序链表尚未合并",p1,p2,result,tail,selected,origin,merged_count); /* TRACE_STAGE_1 */
    while(p1&&p2){
        if(p1->data<=p2->data){selected=p1;next=p1->next;p1=next;origin=1;}
        else{selected=p2;next=p2->next;p2=next;origin=2;}
        selected->next=NULL;
        if(!result)result=tail=selected;else{tail->next=selected;tail=selected;}
        merged_count++;char step[120];snprintf(step,sizeof(step),"选择 %d：从链表 %c 摘下并接到结果尾部",selected->data,origin==1?'A':'B');
        snap(step,p1,p2,result,tail,selected,origin,merged_count); /* TRACE_STAGE_2 */
    }
    Node *rest=p1?p1:p2;origin=p1?1:2;if(!result)result=rest;else tail->next=rest;
    while(rest){tail=rest;rest=rest->next;merged_count++;}p1=NULL;p2=NULL;selected=tail;
    snap("一条链表耗尽：直接串接剩余有序段，原地合并完成",p1,p2,result,tail,selected,origin,merged_count); /* TRACE_STAGE_3 */
    return result;
}
int main(void){
    setvbuf(stdout,NULL,_IONBF,0);int a_values[3]={1,4,7},b_values[3]={2,3,8};
    for(int i=0;i<3;i++){g_nodes[i]=make_node(a_values[i]);g_nodes[i+3]=make_node(b_values[i]);}
    for(int i=0;i<2;i++){g_nodes[i]->next=g_nodes[i+1];g_nodes[i+3]->next=g_nodes[i+4];}
    Node *result=merge_sorted(g_nodes[0],g_nodes[3]);
    printf("PROGRAM_STDOUT:merged=");for(Node *p=result;p;p=p->next)printf("%d%s",p->data,p->next?" ":"");printf(" nodes=6 allocations_during_merge=0\n");
    for(Node *p=result,*next_node;p;p=next_node){next_node=p->next;free(p);}return 0;
}
'''

MERGE_SORTED_DISPLAY = """Node *merge_sorted(Node *head1, Node *head2) {
    Node *p1 = head1, *p2 = head2;
    Node *result = NULL, *tail = NULL;

    while (p1 != NULL && p2 != NULL) {
        Node *selected;
        if (p1->data <= p2->data) {
            selected = p1;
            p1 = p1->next;
        } else {
            selected = p2;
            p2 = p2->next;
        }

        selected->next = NULL;
        if (result == NULL) result = selected;
        else tail->next = selected;
        tail = selected;
    }

    Node *rest = p1 != NULL ? p1 : p2;
    if (tail != NULL) tail->next = rest;
    else result = rest;
    return result;
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

ARRAY_APPEND_SOURCE = r'''#include <stdio.h>
__attribute__((noinline)) static void snap(const char *step,int *arr,int length,int capacity,int pos,int value,int i){
    printf("SNAPSHOT:{\"step\":\"%s\",\"values\":{\"length\":%d,\"capacity\":%d,\"pos\":%d,\"value\":%d,\"i\":%d},\"array\":[",step,length,capacity,pos,value,i);
    for(int k=0;k<capacity;k++){if(k)printf(",");printf("{\"index\":%d,\"address\":\"%p\",\"value\":%d,\"active\":%s}",k,(void*)&arr[k],arr[k],k<length?"true":"false");}
    printf("]}\n");
}
int main(void){
    setvbuf(stdout,NULL,_IONBF,0);int arr[6]={10,20,30,40,0,0};int length=4,capacity=6,pos=length,value=50,i=pos;
    snap("尾插前：表尾空闲位置为 arr[length]",arr,length,capacity,pos,value,i); /* TRACE_STAGE_1 */
    arr[pos]=value; snap("写入 arr[length] = 50",arr,length,capacity,pos,value,i); /* TRACE_STAGE_2 */
    length++; snap("length++，尾插完成",arr,length,capacity,pos,value,i); /* TRACE_STAGE_3 */
    printf("PROGRAM_STDOUT:10 20 30 40 50\n");return 0;
}
'''

ARRAY_APPEND_DISPLAY = """int main(void) {
    int arr[6] = {10, 20, 30, 40, 0, 0};
    int length = 4;
    int capacity = 6;
    int pos = length;
    int value = 50;

    arr[pos] = value;
    length++;
}
"""

ARRAY_COMPLETE_SOURCE = r'''#include <stdio.h>
__attribute__((noinline)) static void snap(const char *step,int *arr,int length,int capacity,int pos,int value,int i,int found,int status){
    printf("SNAPSHOT:{\"step\":\"%s\",\"values\":{\"length\":%d,\"capacity\":%d,\"pos\":%d,\"value\":%d,\"i\":%d,\"found\":%d,\"status\":%d},\"array\":[",step,length,capacity,pos,value,i,found,status);
    for(int k=0;k<capacity;k++){if(k)printf(",");printf("{\"index\":%d,\"address\":\"%p\",\"value\":%d,\"active\":%s}",k,(void*)&arr[k],arr[k],k<length?"true":"false");}printf("]}\n");
}
int main(void){
    setvbuf(stdout,NULL,_IONBF,0);int arr[6]={10,20,30,40,50,60};int length=6,capacity=6,pos=2,value=30,i=0,found=-1,status=0;
    snap("满容量顺序表：准备顺序查找 30",arr,length,capacity,pos,value,i,found,status); /* TRACE_STAGE_1 */
    for(i=0;i<length;i++)if(arr[i]==value){found=i;break;}snap("查找成功：30 位于下标 2",arr,length,capacity,pos,value,i,found,status); /* TRACE_STAGE_2 */
    for(i=pos;i<length-1;i++){arr[i]=arr[i+1];snap(i==2?"删除搬移：arr[2] = arr[3]":i==3?"删除搬移：arr[3] = arr[4]":"删除搬移：arr[4] = arr[5]",arr,length,capacity,pos,value,i,found,status);} /* TRACE_STAGE_3 */
    length--;status=1;snap("length--：删除 30 完成，释放一个逻辑槽位",arr,length,capacity,pos,value,i,found,status); /* TRACE_STAGE_4 */
    value=99;pos=length;i=pos;arr[length++]=value;status=2;snap("容量重新可用：尾插 99，表再次装满",arr,length,capacity,pos,value,i,found,status); /* TRACE_STAGE_5 */
    value=100;pos=length;i=-1;if(length>=capacity)status=-1;snap("容量边界：length == capacity，拒绝尾插 100",arr,length,capacity,pos,value,i,found,status); /* TRACE_STAGE_6 */
    printf("PROGRAM_STDOUT:found=2 after_delete_append=10 20 40 50 60 99 overflow_rejected=1\n");return 0;
}
'''

ARRAY_COMPLETE_DISPLAY = """// 顺序查找
for (i = 0; i < length; i++)
    if (arr[i] == value) { found = i; break; }

// 删除下标 pos
for (i = pos; i < length - 1; i++)
    arr[i] = arr[i + 1];
length--;

// 容量边界
if (length < capacity)
    arr[length++] = 99;
if (length == capacity)
    reject_append(100);
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

TREE_SOURCE = r'''#include <stdio.h>
#include <stdlib.h>
typedef struct Node { int data; struct Node *left,*right; } Node;
static Node *make_node(int value){Node *n=(Node*)malloc(sizeof(Node));if(!n)exit(2);n->data=value;n->left=n->right=NULL;return n;}
static int contains(Node *root,Node *needle){return root&&(root==needle||contains(root->left,needle)||contains(root->right,needle));}
static void print_node(Node *n,int *first){if(!n)return;if(!*first)printf(",");*first=0;printf("{\"address\":\"%p\",\"data\":%d,\"left\":\"%p\",\"right\":\"%p\",\"detached\":false}",(void*)n,n->data,(void*)n->left,(void*)n->right);print_node(n->left,first);print_node(n->right,first);}
__attribute__((noinline)) static void snap(const char *step,Node *root,Node *current,Node *new_node,int target,int depth,int direction){
    printf("SNAPSHOT:{\"step\":\"%s\",\"values\":{\"root\":\"%p\",\"current\":\"%p\",\"new_node\":\"%p\",\"target\":%d,\"depth\":%d,\"direction\":%d},\"tree\":[",step,(void*)root,(void*)current,(void*)new_node,target,depth,direction);
    int first=1;print_node(root,&first);if(new_node&&!contains(root,new_node)){if(!first)printf(",");printf("{\"address\":\"%p\",\"data\":%d,\"left\":\"%p\",\"right\":\"%p\",\"detached\":true}",(void*)new_node,new_node->data,(void*)new_node->left,(void*)new_node->right);}
    printf("]}\n");
}
__attribute__((noinline)) static Node *bst_insert(Node *current,int target,Node *root,Node **new_node,int depth){
    int direction=0;
    if(current==NULL){*new_node=make_node(target);snap("到达 NULL：分配新结点 60",root,current,*new_node,target,depth,direction); /* TRACE_STAGE_4 */ return *new_node;}
    direction=target<current->data?-1:1;
    if(depth==0){snap("访问根结点 50：60 > 50，进入右子树",root,current,*new_node,target,depth,direction); /* TRACE_STAGE_2 */}
    else{snap("访问结点 70：60 < 70，进入左子树",root,current,*new_node,target,depth,direction); /* TRACE_STAGE_3 */}
    if(direction<0){current->left=bst_insert(current->left,target,root,new_node,depth+1);if(depth==1){snap("递归回溯：70->left 指向新结点 60",root,current,*new_node,target,depth,direction); /* TRACE_STAGE_5 */}}
    else current->right=bst_insert(current->right,target,root,new_node,depth+1);
    return current;
}
static void free_tree(Node *n){if(!n)return;free_tree(n->left);free_tree(n->right);free(n);}
int main(void){
    setvbuf(stdout,NULL,_IONBF,0);Node *root=make_node(50),*current=NULL,*new_node=NULL;int target=60,depth=0,direction=0;
    root->left=make_node(30);root->right=make_node(70);current=root;snap("原始二叉搜索树：30, 50, 70",root,current,new_node,target,depth,direction); /* TRACE_STAGE_1 */
    root=bst_insert(root,target,root,&new_node,0);current=new_node;depth=2;snap("插入完成：中序序列为 30, 50, 60, 70",root,current,new_node,target,depth,direction); /* TRACE_STAGE_6 */
    printf("PROGRAM_STDOUT:inorder=30 50 60 70 root=%d inserted=%d\n",root->data,new_node->data);free_tree(root);return 0;
}
'''

TREE_DISPLAY = """typedef struct Node {
    int data;
    struct Node *left, *right;
} Node;

Node *bst_insert(Node *current, int target) {
    if (current == NULL)
        return make_node(target);

    if (target < current->data)
        current->left = bst_insert(current->left, target);
    else
        current->right = bst_insert(current->right, target);

    return current;
}

int main(void) {
    Node *root = make_node(50);
    root->left = make_node(30);
    root->right = make_node(70);

    root = bst_insert(root, 60);
}
"""

BST_COMPLETE_SOURCE = r'''#include <stdio.h>
#include <stdlib.h>
typedef struct Node { int data; struct Node *left,*right; } Node;
static Node *make_node(int value){Node *n=(Node*)malloc(sizeof(Node));if(!n)exit(2);n->data=value;n->left=n->right=NULL;return n;}
static int contains(Node *root,Node *needle){return root&&(root==needle||contains(root->left,needle)||contains(root->right,needle));}
static void print_node(Node *n,int *first){if(!n)return;if(!*first)printf(",");*first=0;printf("{\"address\":\"%p\",\"data\":%d,\"left\":\"%p\",\"right\":\"%p\",\"detached\":false}",(void*)n,n->data,(void*)n->left,(void*)n->right);print_node(n->left,first);print_node(n->right,first);}
__attribute__((noinline)) static void snap(const char *step,Node *root,Node *current,Node *new_node,int target,int depth,int direction){printf("SNAPSHOT:{\"step\":\"%s\",\"values\":{\"root\":\"%p\",\"current\":\"%p\",\"new_node\":\"%p\",\"target\":%d,\"depth\":%d,\"direction\":%d},\"tree\":[",step,(void*)root,(void*)current,(void*)new_node,target,depth,direction);int first=1;print_node(root,&first);if(new_node&&!contains(root,new_node)){if(!first)printf(",");printf("{\"address\":\"%p\",\"data\":%d,\"left\":\"%p\",\"right\":\"%p\",\"detached\":true}",(void*)new_node,new_node->data,(void*)new_node->left,(void*)new_node->right);}printf("]}\n");}
static void free_tree(Node *n){if(!n)return;free_tree(n->left);free_tree(n->right);free(n);}
int main(void){
    setvbuf(stdout,NULL,_IONBF,0);Node *root=make_node(50),*current=root,*new_node=NULL;int target=60,depth=0,direction=0;root->left=make_node(30);root->right=make_node(70);root->right->left=make_node(60);root->right->right=make_node(80);
    snap("初始 BST：准备搜索 60",root,current,new_node,target,depth,direction); /* TRACE_STAGE_1 */
    direction=1;snap("60 > 50：搜索进入右子树",root,current,new_node,target,depth,direction); /* TRACE_STAGE_2 */
    current=current->right;depth=1;direction=-1;snap("60 < 70：搜索进入左子树",root,current,new_node,target,depth,direction); /* TRACE_STAGE_3 */
    current=current->left;depth=2;direction=0;snap("搜索成功：current 指向 60",root,current,new_node,target,depth,direction); /* TRACE_STAGE_4 */
    target=70;current=root->right;depth=1;direction=0;snap("删除 70：命中具有两个孩子的结点",root,current,new_node,target,depth,direction); /* TRACE_STAGE_5 */
    Node *successor=current->right;new_node=successor;direction=1;snap("在右子树找到中序后继 80",root,current,new_node,target,depth,direction); /* TRACE_STAGE_6 */
    current->data=successor->data;snap("用后继值 80 覆盖待删结点的数据域",root,current,new_node,target,depth,direction); /* TRACE_STAGE_7 */
    current->right=successor->right;snap("父指针越过后继结点，80 原结点已脱链",root,current,new_node,target,depth,direction); /* TRACE_STAGE_8 */
    free(successor);new_node=NULL;current=root->right;direction=0;snap("释放后继原结点：BST 删除完成",root,current,new_node,target,depth,direction); /* TRACE_STAGE_9 */
    printf("PROGRAM_STDOUT:search_60=found inorder_after_delete=30 50 60 80\n");free_tree(root);return 0;
}
'''

BST_COMPLETE_DISPLAY = """// 搜索 target
while (current != NULL && current->data != target) {
    if (target < current->data) current = current->left;
    else current = current->right;
}

// 删除具有两个孩子的结点
Node *successor = current->right;
while (successor->left != NULL)
    successor = successor->left;
current->data = successor->data;
current->right = successor->right;
free(successor);
"""

RB_TREE_SOURCE = r'''#include <stdio.h>
#include <stdlib.h>
typedef enum { BLACK=0, RED=1 } Color;
typedef struct Node { int data; Color color; struct Node *left,*right,*parent; } Node;
static Node *g_root=NULL,*g_current=NULL,*g_new_node=NULL;
static int g_target=0,g_case=0;
static Node *make_node(int value,Color color){Node *n=(Node*)malloc(sizeof(Node));if(!n)exit(2);n->data=value;n->color=color;n->left=n->right=n->parent=NULL;return n;}
static int node_depth(Node *n){int d=0;while(n&&n->parent){d++;n=n->parent;}return d;}
static void print_node(Node *n,int *first){if(!n)return;if(!*first)printf(",");*first=0;printf("{\"address\":\"%p\",\"data\":%d,\"color\":\"%s\",\"left\":\"%p\",\"right\":\"%p\",\"parent\":\"%p\",\"detached\":false}",(void*)n,n->data,n->color==RED?"red":"black",(void*)n->left,(void*)n->right,(void*)n->parent);print_node(n->left,first);print_node(n->right,first);}
__attribute__((noinline)) static void snap(const char *step){
    printf("SNAPSHOT:{\"step\":\"%s\",\"values\":{\"root\":\"%p\",\"current\":\"%p\",\"new_node\":\"%p\",\"target\":%d,\"depth\":%d,\"direction\":0,\"case_code\":%d},\"tree\":[",step,(void*)g_root,(void*)g_current,(void*)g_new_node,g_target,node_depth(g_current),g_case);
    int first=1;print_node(g_root,&first);printf("]}\n");
}
static void rotate_right(Node **root,Node *grand){Node *parent=grand->left;grand->left=parent->right;if(parent->right)parent->right->parent=grand;parent->parent=grand->parent;if(!grand->parent)*root=parent;else if(grand==grand->parent->left)grand->parent->left=parent;else grand->parent->right=parent;parent->right=grand;grand->parent=parent;}
static void rotate_left(Node **root,Node *grand){Node *parent=grand->right;grand->right=parent->left;if(parent->left)parent->left->parent=grand;parent->parent=grand->parent;if(!grand->parent)*root=parent;else if(grand==grand->parent->left)grand->parent->left=parent;else grand->parent->right=parent;parent->left=grand;grand->parent=parent;}
static Node *bst_attach(Node **root,int value){Node *parent=NULL,*cursor=*root;while(cursor){parent=cursor;cursor=value<cursor->data?cursor->left:cursor->right;}Node *node=make_node(value,RED);node->parent=parent;if(!parent)*root=node;else if(value<parent->data)parent->left=node;else parent->right=node;return node;}
__attribute__((noinline)) static void rb_fixup(Node **root,Node *node){
    while(node!=*root&&node->parent->color==RED){Node *parent=node->parent,*grand=parent->parent,*uncle=NULL;
        if(parent==grand->left){uncle=grand->right;if(uncle&&uncle->color==RED){
                if(g_target==1){g_case=1;g_current=parent;snap("红父红叔：准备将父结点和叔结点染黑");} /* TRACE_STAGE_3 */
                parent->color=BLACK;uncle->color=BLACK;grand->color=RED;
                if(g_target==1){g_current=grand;snap("重染色完成：祖父暂时变红，继续向上检查");} /* TRACE_STAGE_4 */
                node=grand;
            }else{
                if(node==parent->right){node=parent;rotate_left(root,node);parent=node->parent;grand=parent->parent;}
                if(g_target==0){g_case=2;g_current=grand;snap("红父黑叔且为 LL 外侧：准备右旋祖父 5");} /* TRACE_STAGE_7 */
                parent->color=BLACK;grand->color=RED;rotate_right(root,grand);
                if(g_target==0){g_case=3;g_current=parent;snap("右旋并重染色完成：1 成为该子树的新根");} /* TRACE_STAGE_8 */
            }
        }else{uncle=grand->left;if(uncle&&uncle->color==RED){parent->color=BLACK;uncle->color=BLACK;grand->color=RED;node=grand;}else{if(node==parent->left){node=parent;rotate_right(root,node);parent=node->parent;grand=parent->parent;}parent->color=BLACK;grand->color=RED;rotate_left(root,grand);}}
    }
    (*root)->color=BLACK;
    if(g_target==1){g_case=4;g_current=*root;snap("根结点恢复为黑色：第一次插入完成");} /* TRACE_STAGE_5 */
}
static Node *rb_insert(Node **root,int value){g_target=value;g_case=0;g_new_node=bst_attach(root,value);g_root=*root;g_current=g_new_node;
    if(value==1)snap("插入 1：新结点按 BST 规则作为红色叶子连接到 5"); /* TRACE_STAGE_2 */
    else snap("插入 0：新结点为红色，父结点 1 也是红色，发生冲突"); /* TRACE_STAGE_6 */
    rb_fixup(root,g_new_node);g_root=*root;return g_new_node;}
static void free_tree(Node *n){if(!n)return;free_tree(n->left);free_tree(n->right);free(n);}
int main(void){setvbuf(stdout,NULL,_IONBF,0);g_root=make_node(10,BLACK);g_root->left=make_node(5,RED);g_root->right=make_node(15,RED);g_root->left->parent=g_root;g_root->right->parent=g_root;g_current=g_root;g_target=1;g_case=0;
    snap("初始合法红黑树：根 10 黑，孩子 5 和 15 红"); /* TRACE_STAGE_1 */
    rb_insert(&g_root,1);rb_insert(&g_root,0);g_target=0;g_case=4;g_current=g_new_node;snap("插入完成：根黑、无连续红结点、各路径黑高一致"); /* TRACE_STAGE_9 */
    printf("PROGRAM_STDOUT:root=10 left=1 colors=black,black,red,red,black\n");free_tree(g_root);return 0;}
'''

RB_TREE_DISPLAY = """void rb_insert(int target) {
    Node *node = bst_attach(target);
    node->color = RED;

    while (node->parent->color == RED) {
        Node *uncle = sibling(node->parent);
        if (uncle->color == RED) {
            node->parent->color = BLACK;
            uncle->color = BLACK;
            node->parent->parent->color = RED;
            node = node->parent->parent;
        } else {
            node->parent->color = BLACK;
            node->parent->parent->color = RED;
            rotate_right(node->parent->parent);
        }
    }
    root->color = BLACK;
}

rb_insert(1);
rb_insert(0);
"""

RB_ROTATION_CASES_SOURCE = r'''#include <stdio.h>
#include <stdlib.h>
typedef enum { BLACK=0, RED=1 } Color;
typedef struct Node { int data; Color color; struct Node *left,*right,*parent; } Node;
static Node *g_root=NULL,*g_current=NULL,*g_new_node=NULL;static int g_target=0,g_case=0,valid_count=0;
static Node *node(int value,Color color){Node *n=(Node*)malloc(sizeof(Node));if(!n)exit(2);n->data=value;n->color=color;n->left=n->right=n->parent=NULL;return n;}
static void link_left(Node *p,Node *c){p->left=c;if(c)c->parent=p;}static void link_right(Node *p,Node *c){p->right=c;if(c)c->parent=p;}
static void print_node(Node *n,int *first){if(!n)return;if(!*first)printf(",");*first=0;printf("{\"address\":\"%p\",\"data\":%d,\"color\":\"%s\",\"left\":\"%p\",\"right\":\"%p\",\"parent\":\"%p\",\"detached\":false}",(void*)n,n->data,n->color==RED?"red":"black",(void*)n->left,(void*)n->right,(void*)n->parent);print_node(n->left,first);print_node(n->right,first);}
__attribute__((noinline)) static void snap(const char *step){printf("SNAPSHOT:{\"step\":\"%s\",\"values\":{\"root\":\"%p\",\"current\":\"%p\",\"new_node\":\"%p\",\"target\":%d,\"depth\":2,\"direction\":0,\"case_code\":%d},\"tree\":[",step,(void*)g_root,(void*)g_current,(void*)g_new_node,g_target,g_case);int first=1;print_node(g_root,&first);printf("]}\n");}
static void rotate_left(Node **root,Node *x){Node *y=x->right;x->right=y->left;if(y->left)y->left->parent=x;y->parent=x->parent;if(!x->parent)*root=y;else if(x==x->parent->left)x->parent->left=y;else x->parent->right=y;y->left=x;x->parent=y;}
static void rotate_right(Node **root,Node *x){Node *y=x->left;x->left=y->right;if(y->right)y->right->parent=x;y->parent=x->parent;if(!x->parent)*root=y;else if(x==x->parent->left)x->parent->left=y;else x->parent->right=y;y->right=x;x->parent=y;}
static int black_height(Node *n){if(!n)return 1;int l=black_height(n->left),r=black_height(n->right);if(!l||l!=r)return 0;if(n->color==RED&&((n->left&&n->left->color==RED)||(n->right&&n->right->color==RED)))return 0;return l+(n->color==BLACK);}
static int valid(Node *root){return root&&root->color==BLACK&&black_height(root)>0;}
static void free_tree(Node *n){if(!n)return;free_tree(n->left);free_tree(n->right);free(n);}
static void run_ll(void){Node *g=node(30,BLACK),*p=node(20,RED),*n=node(10,RED);link_left(g,p);link_left(p,n);g_root=g;g_current=n;g_new_node=n;g_target=10;g_case=10;snap("LL：10 插在红父 20 的左侧，形成外侧冲突"); /* TRACE_STAGE_1 */ p->color=BLACK;g->color=RED;g_case=11;g_current=g;snap("LL：父染黑、祖父染红，准备右旋 30"); /* TRACE_STAGE_2 */ rotate_right(&g_root,g);g_case=12;g_current=g_root;snap("LL 修复完成：20 成为黑色子树根"); /* TRACE_STAGE_3 */ valid_count+=valid(g_root);free_tree(g_root);}
static void run_rr(void){Node *g=node(10,BLACK),*p=node(20,RED),*n=node(30,RED);link_right(g,p);link_right(p,n);g_root=g;g_current=n;g_new_node=n;g_target=30;g_case=20;snap("RR：30 插在红父 20 的右侧，形成外侧冲突"); /* TRACE_STAGE_4 */ p->color=BLACK;g->color=RED;g_case=21;g_current=g;snap("RR：父染黑、祖父染红，准备左旋 10"); /* TRACE_STAGE_5 */ rotate_left(&g_root,g);g_case=22;g_current=g_root;snap("RR 修复完成：20 成为黑色子树根"); /* TRACE_STAGE_6 */ valid_count+=valid(g_root);free_tree(g_root);}
static void run_lr(void){Node *g=node(30,BLACK),*p=node(10,RED),*n=node(20,RED);link_left(g,p);link_right(p,n);g_root=g;g_current=n;g_new_node=n;g_target=20;g_case=30;snap("LR：20 是红父 10 的右孩子，先处理内侧结构"); /* TRACE_STAGE_7 */ rotate_left(&g_root,p);g_case=31;g_current=n;snap("LR 第一步：左旋父结点 10，转换为 LL"); /* TRACE_STAGE_8 */ n->color=BLACK;g->color=RED;rotate_right(&g_root,g);g_case=32;g_current=g_root;snap("LR 第二步：右旋祖父 30，修复完成"); /* TRACE_STAGE_9 */ valid_count+=valid(g_root);free_tree(g_root);}
static void run_rl(void){Node *g=node(10,BLACK),*p=node(30,RED),*n=node(20,RED);link_right(g,p);link_left(p,n);g_root=g;g_current=n;g_new_node=n;g_target=20;g_case=40;snap("RL：20 是红父 30 的左孩子，先处理内侧结构"); /* TRACE_STAGE_10 */ rotate_right(&g_root,p);g_case=41;g_current=n;snap("RL 第一步：右旋父结点 30，转换为 RR"); /* TRACE_STAGE_11 */ n->color=BLACK;g->color=RED;rotate_left(&g_root,g);g_case=42;g_current=g_root;snap("RL 第二步：左旋祖父 10，修复完成"); /* TRACE_STAGE_12 */ valid_count+=valid(g_root);free_tree(g_root);}
int main(void){setvbuf(stdout,NULL,_IONBF,0);run_ll();run_rr();run_lr();run_rl();printf("PROGRAM_STDOUT:rotation_cases=LL RR LR RL valid=%d/4\n",valid_count);return valid_count==4?0:3;}
'''

RB_ROTATION_CASES_DISPLAY = """if (parent == grandparent->left) {
    if (node == parent->right) {       // LR
        rotate_left(parent);
        node = parent;
        parent = node->parent;
    }
    parent->color = BLACK;             // LL
    grandparent->color = RED;
    rotate_right(grandparent);
} else {
    if (node == parent->left) {        // RL
        rotate_right(parent);
        node = parent;
        parent = node->parent;
    }
    parent->color = BLACK;             // RR
    grandparent->color = RED;
    rotate_left(grandparent);
}
"""

BFS_SOURCE = r'''#include <stdio.h>
#define N 5
static const char labels[N]={'A','B','C','D','E'};
static const int edge_u[5]={0,0,1,1,2},edge_v[5]={1,2,3,4,4};
__attribute__((noinline)) static void snap(const char *step,int state[N],int parent[N],int distance[N],int queue[N],int front,int rear,int current,int order[N],int order_len){
    printf("SNAPSHOT:{\"step\":\"%s\",\"values\":{\"current\":%d,\"front\":%d,\"rear\":%d,\"visit_count\":%d},\"graph\":{\"directed\":false,\"vertices\":[",step,current,front,rear,order_len);
    for(int k=0;k<N;k++){if(k)printf(",");printf("{\"id\":%d,\"label\":\"%c\",\"address\":\"%p\",\"state\":%d,\"parent\":%d,\"metric\":%d}",k,labels[k],(void*)&state[k],state[k],parent[k],distance[k]);}
    printf("],\"edges\":[");for(int k=0;k<5;k++){if(k)printf(",");printf("{\"from\":%d,\"to\":%d}",edge_u[k],edge_v[k]);}
    printf("]},\"worklist\":{\"kind\":\"queue\",\"items\":[");for(int k=0;k<N;k++){if(k)printf(",");printf("{\"slot\":%d,\"address\":\"%p\",\"vertex\":%d,\"active\":%s}",k,(void*)&queue[k],queue[k],k>=front&&k<rear?"true":"false");}
    printf("]},\"order\":[");for(int k=0;k<order_len;k++){if(k)printf(",");printf("%d",order[k]);}printf("]}\n");
}
static void discover(int current,int adj[N][N],int state[N],int parent[N],int distance[N],int queue[N],int *rear){for(int next=0;next<N;next++)if(adj[current][next]&&state[next]==0){state[next]=1;parent[next]=current;distance[next]=distance[current]+1;queue[(*rear)++]=next;}}
int main(void){
    setvbuf(stdout,NULL,_IONBF,0);int adj[N][N]={{0,1,1,0,0},{1,0,0,1,1},{1,0,0,0,1},{0,1,0,0,0},{0,1,1,0,0}};
    int state[N]={0},parent[N]={-1,-1,-1,-1,-1},distance[N]={-1,-1,-1,-1,-1},queue[N]={-1,-1,-1,-1,-1},order[N]={-1,-1,-1,-1,-1};int front=0,rear=0,current=-1,order_len=0;
    state[0]=1;distance[0]=0;queue[rear++]=0;snap("BFS 初始化：A 入队并标记为 frontier",state,parent,distance,queue,front,rear,current,order,order_len); /* TRACE_STAGE_1 */
    current=queue[front++];state[current]=2;order[order_len++]=current;snap("A 出队：标记 visited",state,parent,distance,queue,front,rear,current,order,order_len); /* TRACE_STAGE_2 */
    discover(current,adj,state,parent,distance,queue,&rear);snap("扫描 A：发现 B、C 并入队",state,parent,distance,queue,front,rear,current,order,order_len); /* TRACE_STAGE_3 */
    current=queue[front++];state[current]=2;order[order_len++]=current;discover(current,adj,state,parent,distance,queue,&rear);snap("B 出队：发现 D、E 并入队",state,parent,distance,queue,front,rear,current,order,order_len); /* TRACE_STAGE_4 */
    current=queue[front++];state[current]=2;order[order_len++]=current;discover(current,adj,state,parent,distance,queue,&rear);snap("C 出队：相邻结点均已发现",state,parent,distance,queue,front,rear,current,order,order_len); /* TRACE_STAGE_5 */
    while(front<rear){current=queue[front++];state[current]=2;order[order_len++]=current;discover(current,adj,state,parent,distance,queue,&rear);}snap("BFS 完成：访问序列 A, B, C, D, E",state,parent,distance,queue,front,rear,current,order,order_len); /* TRACE_STAGE_6 */
    printf("PROGRAM_STDOUT:bfs=A B C D E visited=%d\n",order_len);return 0;
}
'''

BFS_DISPLAY = """void bfs(int start) {
    state[start] = FRONTIER;
    queue[rear++] = start;

    while (front < rear) {
        int current = queue[front++];
        state[current] = VISITED;
        order[order_len++] = current;

        for (int next = 0; next < N; next++) {
            if (adj[current][next] && state[next] == UNSEEN) {
                state[next] = FRONTIER;
                parent[next] = current;
                distance[next] = distance[current] + 1;
                queue[rear++] = next;
            }
        }
    }
}
"""

DFS_SOURCE = r'''#include <stdio.h>
#define N 5
static const char labels[N]={'A','B','C','D','E'};
static const int edge_u[5]={0,0,1,1,2},edge_v[5]={1,2,3,4,4};
__attribute__((noinline)) static void snap(const char *step,int state[N],int parent[N],int metric[N],int current,int stack[N],int stack_size,int order[N],int order_len){
    printf("SNAPSHOT:{\"step\":\"%s\",\"values\":{\"current\":%d,\"stack_size\":%d,\"visit_count\":%d},\"graph\":{\"directed\":false,\"vertices\":[",step,current,stack_size,order_len);
    for(int k=0;k<N;k++){if(k)printf(",");printf("{\"id\":%d,\"label\":\"%c\",\"address\":\"%p\",\"state\":%d,\"parent\":%d,\"metric\":%d}",k,labels[k],(void*)&state[k],state[k],parent[k],metric[k]);}
    printf("],\"edges\":[");for(int k=0;k<5;k++){if(k)printf(",");printf("{\"from\":%d,\"to\":%d}",edge_u[k],edge_v[k]);}
    printf("]},\"worklist\":{\"kind\":\"stack\",\"items\":[");for(int k=0;k<N;k++){if(k)printf(",");printf("{\"slot\":%d,\"address\":\"%p\",\"vertex\":%d,\"active\":%s}",k,(void*)&stack[k],stack[k],k<stack_size?"true":"false");}
    printf("]},\"order\":[");for(int k=0;k<order_len;k++){if(k)printf(",");printf("%d",order[k]);}printf("]}\n");
}
__attribute__((noinline)) static void dfs(int current,int depth,int adj[N][N],int state[N],int parent[N],int metric[N],int stack[N],int *stack_size,int order[N],int *order_len){
    char step[96];state[current]=1;metric[current]=depth;stack[(*stack_size)++]=current;order[(*order_len)++]=current;snprintf(step,sizeof(step),"DFS 进入 %c：压入递归栈",labels[current]);snap(step,state,parent,metric,current,stack,*stack_size,order,*order_len); /* TRACE_STAGE_2 */
    for(int next=0;next<N;next++)if(adj[current][next]&&state[next]==0){parent[next]=current;dfs(next,depth+1,adj,state,parent,metric,stack,stack_size,order,order_len);}
    state[current]=2;(*stack_size)--;
}
int main(void){
    setvbuf(stdout,NULL,_IONBF,0);int adj[N][N]={{0,1,1,0,0},{1,0,0,1,1},{1,0,0,0,1},{0,1,0,0,0},{0,1,1,0,0}};
    int state[N]={0},parent[N]={-1,-1,-1,-1,-1},metric[N]={-1,-1,-1,-1,-1},stack[N]={-1,-1,-1,-1,-1},order[N]={-1,-1,-1,-1,-1};int stack_size=0,order_len=0,current=-1,depth=-1;
    snap("DFS 初始化：所有结点均为 unseen",state,parent,metric,current,stack,stack_size,order,order_len); /* TRACE_STAGE_1 */
    dfs(0,0,adj,state,parent,metric,stack,&stack_size,order,&order_len);
    current=-1;snap("DFS 完成：先序访问 A, B, D, E, C",state,parent,metric,current,stack,stack_size,order,order_len); /* TRACE_STAGE_3 */
    printf("PROGRAM_STDOUT:dfs=A B D E C visited=%d\n",order_len);return 0;
}
'''

DFS_DISPLAY = """void dfs(int current, int depth) {
    state[current] = ACTIVE;
    stack[stack_size++] = current;
    order[order_len++] = current;

    for (int next = 0; next < N; next++) {
        if (adj[current][next] && state[next] == UNSEEN) {
            parent[next] = current;
            dfs(next, depth + 1);
        }
    }

    state[current] = FINISHED;
    stack_size--;
}

int main(void) {
    dfs(A, 0);
}
"""

ADJACENCY_LIST_SOURCE = r'''#include <stdio.h>
#include <stdlib.h>
#define N 4
typedef struct Edge { int to; struct Edge *next; } Edge;
static const char labels[N]={'A','B','C','D'};
static Edge *edge_node(int to,Edge *next){Edge *e=(Edge*)malloc(sizeof(Edge));if(!e)exit(2);e->to=to;e->next=next;return e;}
static void add_edge(Edge *heads[N],int adj[N][N],int u,int v){heads[u]=edge_node(v,heads[u]);heads[v]=edge_node(u,heads[v]);adj[u][v]=adj[v][u]=1;}
static void erase_one(Edge **head,int to){while(*head&&(*head)->to!=to)head=&(*head)->next;if(*head){Edge *dead=*head;*head=dead->next;free(dead);}}
static void remove_edge(Edge *heads[N],int adj[N][N],int u,int v){erase_one(&heads[u],v);erase_one(&heads[v],u);adj[u][v]=adj[v][u]=0;}
__attribute__((noinline)) static void snap(const char *step,Edge *heads[N],int adj[N][N],int edge_count,int current,int operation){
    printf("SNAPSHOT:{\"step\":\"%s\",\"values\":{\"current\":%d,\"edge_count\":%d,\"operation\":%d},\"graph\":{\"directed\":false,\"vertices\":[",step,current,edge_count,operation);
    for(int i=0;i<N;i++){if(i)printf(",");printf("{\"id\":%d,\"label\":\"%c\",\"address\":\"%p\",\"state\":0,\"parent\":-1,\"metric\":-1}",i,labels[i],(void*)&heads[i]);}
    printf("],\"edges\":[");int first=1;for(int u=0;u<N;u++)for(int v=u+1;v<N;v++)if(adj[u][v]){if(!first)printf(",");first=0;printf("{\"from\":%d,\"to\":%d}",u,v);}printf("]},\"adjacency\":[");
    for(int i=0;i<N;i++){if(i)printf(",");printf("{\"vertex\":%d,\"label\":\"%c\",\"head_address\":\"%p\",\"edges\":[",i,labels[i],(void*)heads[i]);int ef=1;for(Edge *e=heads[i];e;e=e->next){if(!ef)printf(",");ef=0;printf("{\"address\":\"%p\",\"to\":%d,\"next\":\"%p\"}",(void*)e,e->to,(void*)e->next);}printf("]}");}printf("]}\n");
}
static void free_graph(Edge *heads[N]){for(int i=0;i<N;i++)while(heads[i]){Edge *next=heads[i]->next;free(heads[i]);heads[i]=next;}}
int main(void){
    setvbuf(stdout,NULL,_IONBF,0);Edge *heads[N]={NULL};int adj[N][N]={{0}},edge_count=0,current=-1,operation=0;
    snap("建立邻接表：A、B、C、D 的表头均为 NULL",heads,adj,edge_count,current,operation); /* TRACE_STAGE_1 */
    add_edge(heads,adj,0,1);edge_count++;current=0;operation=1;snap("添加无向边 A-B：两个表头分别插入边结点",heads,adj,edge_count,current,operation); /* TRACE_STAGE_2 */
    add_edge(heads,adj,0,2);edge_count++;current=0;snap("添加无向边 A-C：A 的邻接链发生头插",heads,adj,edge_count,current,operation); /* TRACE_STAGE_3 */
    add_edge(heads,adj,1,3);edge_count++;current=1;snap("添加无向边 B-D",heads,adj,edge_count,current,operation); /* TRACE_STAGE_4 */
    add_edge(heads,adj,2,3);edge_count++;current=2;snap("添加无向边 C-D：图形成一个环",heads,adj,edge_count,current,operation); /* TRACE_STAGE_5 */
    operation=2;remove_edge(heads,adj,0,2);edge_count--;current=0;snap("删除无向边 A-C：释放两侧邻接链中的边结点",heads,adj,edge_count,current,operation); /* TRACE_STAGE_6 */
    printf("PROGRAM_STDOUT:vertices=4 edges=3 adjacency=A:B B:D,A C:D D:C,B\n");free_graph(heads);return 0;
}
'''

ADJACENCY_LIST_DISPLAY = """typedef struct Edge {
    int to;
    struct Edge *next;
} Edge;

Edge *heads[4] = {NULL};
int edge_count = 0;

void add_edge(int u, int v) {
    heads[u] = new_edge(v, heads[u]);
    heads[v] = new_edge(u, heads[v]);
}

void remove_edge(int u, int v) {
    erase_one(&heads[u], v);
    erase_one(&heads[v], u);
}

add_edge(A, B);
add_edge(A, C);
add_edge(B, D);
add_edge(C, D);
remove_edge(A, C);
"""

DEMOS = {
    "linked-list-insert": {"title":"单链表：头插一个新结点","subtitle":"节点与指针关系视图","category":"linked-list","renderer":"singly-linked-list","pseudo":["1. 建立原链表 head -> a","2. 申请新结点 s","3. s->next = head","4. head = s"],"display_source":INSERT_DISPLAY,"source":INSERT_SOURCE,"display_stage_lines":[14,18,20,21],"display_stage_text":["head = a;","s->next = NULL;","s->next = head;","head = s;"],"frame_vars":["head","a","s"],"pointer_names":["head","a","s"],"breakpoint_mode":"snap-caller"},
    "linked-list-delete-head": {"title":"单链表：删除首元结点","subtitle":"脱链与 free 分开显示","category":"linked-list","renderer":"singly-linked-list","pseudo":["1. 原链表 head -> a -> b","2. p = head 保存待删除结点","3. head = head->next 越过 a","4. free(p) 释放原首结点"],"display_source":DELETE_DISPLAY,"source":DELETE_SOURCE,"display_stage_lines":[16,17,18,19],"display_stage_text":["p = head;","head = head->next;","free(p);","p = NULL;"],"frame_vars":["head","a","b","p"],"pointer_names":["head","a","b","p"],"breakpoint_mode":"snap-caller"},
    "linked-list-complete-operations": {"title":"单链表：尾插、指定位置插入与迭代反转","subtitle":"补全 tail、prev/current/next 指针协作与反转全过程","category":"linked-list","renderer":"singly-linked-list","pseudo":["1. 初始链表 10 → 20","2. 使用 tail 在表尾插入 30","3. prev 定位下标 0，准备在下标 1 插入 15","4. x->next 保存原后继，再令 prev->next = x","5. 令 prev=NULL、current=head，开始迭代反转","6. 依次反转 10、15、20、30 的 next 指针","7. head=prev，原表头成为 tail，得到 30 → 20 → 15 → 10"],"display_source":LINKED_COMPLETE_DISPLAY,"source":LINKED_COMPLETE_SOURCE,"display_stage_lines":[1,3,6,7,8,12,14,14,14,14,20],"display_stage_text":["初始链表 10 -> 20","tail = s;","prev = head;","x->next = prev->next;","prev->next = x;","current = head;","反转结点 10","反转结点 15","反转结点 20","反转结点 30","head = prev;"],"frame_vars":["head","tail","prev","current","next","s","x","pos"],"pointer_names":["head","tail","prev","current","next","s","x"],"breakpoint_mode":"snap-caller"},
    "merge-two-sorted-lists-in-place": {"title":"算法题：两个有序链表原地合并","subtitle":"复用全部原结点；比较、摘接、尾指针推进与剩余段串接同步显示","category":"algorithm","renderer":"multi-linked-list","problem_mode":"linked-list-merge","pseudo":["1. 输入 A: 1 → 4 → 7，B: 2 → 3 → 8","2. 比较 p1 与 p2，摘下较小结点 1 接到 result","3. 摘下 2，再摘下 3，tail 持续后移","4. 摘下 4、7，此时链表 A 耗尽","5. 将链表 B 的剩余有序段 8 直接串接到 tail","6. 验证结果 1 → 2 → 3 → 4 → 7 → 8：有序、无环、6 个原结点各出现一次"],"display_source":MERGE_SORTED_DISPLAY,"source":MERGE_SORTED_SOURCE,"display_stage_lines":[2,8,11,11,8,8,22],"display_stage_text":["Node *p1 = head1, *p2 = head2;","selected = p1;  // 选择 1","selected = p2;  // 选择 2","selected = p2;  // 选择 3","selected = p1;  // 选择 4","selected = p1;  // 选择 7","tail->next = rest;  // 串接剩余的 8"],"frame_vars":["p1","p2","result","tail","selected","next","origin","merged_count"],"pointer_names":["result","p1","p2","tail","selected"],"breakpoint_mode":"snap-caller"},
    "sequence-list-insert": {"title":"顺序表：指定位置插入（中间插入）","subtitle":"下标 2 插入；从后向前搬移元素，并非尾插法","category":"array","renderer":"array","pseudo":["1. 原数组 [10,20,30,40]，在下标 2 插入 99","2. 从尾部开始向右搬移 arr[3]","3. 继续搬移 arr[2]","4. arr[2] = 99，length++"],"display_source":ARRAY_DISPLAY,"source":ARRAY_SOURCE,"display_stage_lines":[7,8,10,12],"display_stage_text":["int i = 4;","arr[4] = arr[3];","arr[3] = arr[2];","arr[2] = value;"],"frame_vars":["arr","length","capacity","pos","value","i"],"pointer_names":[],"breakpoint_mode":"snap-caller"},
    "sequence-list-append": {"title":"顺序表：尾插法（append）","subtitle":"在下标 length 直接写入；容量充足时无需搬移元素","category":"array","renderer":"array","pseudo":["1. 检查 length < capacity，确认表尾有空闲容量","2. pos = length，定位第一个空闲槽位","3. arr[pos] = 50，写入表尾","4. length++，新元素纳入有效区间"],"display_source":ARRAY_APPEND_DISPLAY,"source":ARRAY_APPEND_SOURCE,"display_stage_lines":[5,8,9],"display_stage_text":["int pos = length;","arr[pos] = value;","length++;"],"frame_vars":["arr","length","capacity","pos","value","i"],"pointer_names":[],"breakpoint_mode":"snap-caller"},
    "sequence-list-complete-operations": {"title":"顺序表：查找、删除与容量边界","subtitle":"顺序查找、删除左移、重新填满以及满容量拒绝写入","category":"array","renderer":"array","pseudo":["1. 在满容量顺序表 [10,20,30,40,50,60] 中查找 30","2. 命中下标 2，从该位置开始逐项左移","3. length--，删除完成并释放一个逻辑槽位","4. 尾插 99，顺序表再次装满","5. 尝试尾插 100，因 length == capacity 被拒绝"],"display_source":ARRAY_COMPLETE_DISPLAY,"source":ARRAY_COMPLETE_SOURCE,"display_stage_lines":[2,3,7,7,7,8,12,14],"display_stage_text":["开始顺序查找 30","found = 2;","arr[2] = arr[3];","arr[3] = arr[4];","arr[4] = arr[5];","length--;","arr[length++] = 99;","reject_append(100);"],"frame_vars":["arr","length","capacity","pos","value","i","found","status"],"breakpoint_mode":"snap-caller"},
    "stack-push-pop": {"title":"顺序栈：push 与 pop","subtitle":"栈顶移动、有效区间与残留内存值同步显示","category":"stack","renderer":"stack","pseudo":["1. 原栈自底向上为 [10, 20]","2. top++，为新元素预留栈顶位置","3. data[top] = 30，push 完成","4. popped = data[top]，读取栈顶","5. top--，pop 完成（物理槽位仍保留 30）"],"display_source":STACK_DISPLAY,"source":STACK_SOURCE,"display_stage_lines":[3,8,9,12,13],"display_stage_text":["int top = 1;","top++;","data[top] = value;","popped = data[top];","top--;"],"frame_vars":["data","top","capacity","value","popped"],"pointer_names":[],"breakpoint_mode":"snap-caller"},
    "circular-queue-enqueue-dequeue": {"title":"循环队列：enqueue 与 dequeue","subtitle":"队首、队尾、有效元素与 rear 回绕同步显示","category":"queue","renderer":"circular-queue","pseudo":["1. 原队列 front=2、rear=4，逻辑内容 [20, 30]","2. queue[rear] = 40，写入待入队元素","3. rear = (rear + 1) % capacity，回绕到 0","4. removed = queue[front]，读取队首 20","5. front 前移且 size--，dequeue 完成"],"display_source":QUEUE_DISPLAY,"source":QUEUE_SOURCE,"display_stage_lines":[3,10,11,15,16],"display_stage_text":["int front = 2;","queue[rear] = value;","rear = (rear + 1) % 5;","removed = queue[front];","front = (front + 1) % 5;"],"frame_vars":["queue","front","rear","size","capacity","value","removed"],"pointer_names":[],"breakpoint_mode":"snap-caller"},
    "bst-insert": {"title":"二叉搜索树：递归插入 60","subtitle":"树形拓扑、比较方向与真实 LLDB 递归调用栈同步显示","category":"tree","renderer":"binary-tree","pseudo":["1. 建立二叉搜索树：根 50，左 30，右 70","2. 比较 60 > 50，递归进入右子树","3. 比较 60 < 70，递归进入左子树","4. 到达 NULL，分配结点 60","5. 递归回溯，将 70->left 指向 60","6. 插入完成，中序序列为 30, 50, 60, 70"],"display_source":TREE_DISPLAY,"source":TREE_SOURCE,"display_stage_lines":[21,13,11,8,11,23],"display_stage_text":["root->right = make_node(70);","current->right = bst_insert(...);","current->left = bst_insert(...);","return make_node(target);","current->left = bst_insert(...);","root = bst_insert(root, 60);"],"frame_vars":["root","current","new_node","target","depth","direction"],"pointer_names":["root","current","new_node"],"breakpoint_mode":"snap-caller"},
    "bst-search-delete": {"title":"二叉搜索树：搜索与双孩子结点删除","subtitle":"比较路径、中序后继替换、脱链与 free 分阶段显示","category":"tree","renderer":"binary-tree","pseudo":["1. 初始 BST：30, 50, 60, 70, 80","2. 搜索 60：从 50 向右，再从 70 向左","3. 命中结点 60","4. 删除具有两个孩子的 70","5. 找到右子树最小结点 80 作为中序后继","6. 复制后继值、越过后继结点并释放原结点","7. 最终中序序列为 30, 50, 60, 80"],"display_source":BST_COMPLETE_DISPLAY,"source":BST_COMPLETE_SOURCE,"display_stage_lines":[1,4,3,2,7,8,11,12,13],"display_stage_text":["准备搜索 target","current = current->right;","current = current->left;","current->data == target","删除具有两个孩子的 70","successor = current->right;","current->data = successor->data;","current->right = successor->right;","free(successor);"],"frame_vars":["root","current","new_node","target","depth","direction"],"pointer_names":["root","current","new_node"],"breakpoint_mode":"snap-caller"},
    "red-black-tree-insert": {"title":"红黑树：插入 1、0（重染色 + 右旋）","subtitle":"验证红黑性质、父叔颜色分支、重染色与旋转后的拓扑变化","category":"tree","renderer":"red-black-tree","tree_mode":"red-black","pseudo":["1. 初始合法树：10(B) 的孩子为 5(R)、15(R)","2. 插入 1(R)，作为 5 的左孩子","3. 检测到父结点 5 与叔结点 15 均为红色","4. 父叔染黑、祖父 10 暂时染红","5. 根结点恢复黑色，第一次插入完成","6. 插入 0(R)，与红色父结点 1 冲突","7. 叔结点为黑色且形成 LL 外侧结构","8. 父结点 1 染黑、祖父 5 染红并右旋","9. 验证根黑、红结点子女黑、各根叶路径黑高一致"],"display_source":RB_TREE_DISPLAY,"source":RB_TREE_SOURCE,"display_stage_lines":[21,3,7,10,18,3,12,15,18],"display_stage_text":["rb_insert(1);","node->color = RED;","if (uncle->color == RED)","grandparent->color = RED;","root->color = BLACK;","node->color = RED;","else // uncle is BLACK","rotate_right(grandparent);","root->color = BLACK;"],"frame_vars":["g_root","g_current","g_new_node","g_target","g_case"],"pointer_names":["root","current","new_node"],"breakpoint_mode":"snap-caller"},
    "red-black-tree-rotation-cases": {"title":"红黑树：LL、RR、LR、RL 插入旋转全集","subtitle":"四种红父黑叔结构逐一执行单旋或双旋，并验证红黑性质","category":"tree","renderer":"red-black-tree","tree_mode":"red-black","pseudo":["1. LL：父染黑、祖父染红，右旋祖父","2. RR：父染黑、祖父染红，左旋祖父","3. LR：先左旋父结点转换为 LL，再右旋祖父","4. RL：先右旋父结点转换为 RR，再左旋祖父","5. 每种修复后验证根黑、无连续红结点、黑高一致"],"display_source":RB_ROTATION_CASES_DISPLAY,"source":RB_ROTATION_CASES_SOURCE,"display_stage_lines":[1,7,9,10,16,18,2,3,9,11,12,18],"display_stage_text":["LL red-red conflict","parent->color = BLACK;","rotate_right(grandparent);","RR red-red conflict","parent->color = BLACK;","rotate_left(grandparent);","LR inner case","rotate_left(parent);","rotate_right(grandparent);","RL inner case","rotate_right(parent);","rotate_left(grandparent);"],"frame_vars":["g_root","g_current","g_new_node","g_target","g_case"],"pointer_names":["root","current","new_node"],"breakpoint_mode":"snap-caller"},
    "graph-bfs": {"title":"图：广度优先搜索 BFS","subtitle":"结点状态、生成树边与真实循环队列同步显示","category":"graph","renderer":"graph","graph_mode":"bfs","pseudo":["1. A 入队，标记为 frontier","2. A 出队并标记 visited","3. 扫描 A，发现 B、C 并入队","4. B 出队，发现 D、E 并入队","5. C 出队，相邻结点均已发现","6. 继续处理 D、E，BFS 完成"],"display_source":BFS_DISPLAY,"source":BFS_SOURCE,"display_stage_lines":[3,6,11,15,11,5],"display_stage_text":["queue[rear++] = start;","current = queue[front++];","扫描 A 的相邻结点","queue[rear++] = next;","扫描 C 的相邻结点","while (front < rear)"],"frame_vars":["state","parent","distance","queue","front","rear","current","order","order_len"],"pointer_names":[],"breakpoint_mode":"snap-caller"},
    "graph-dfs": {"title":"图：深度优先搜索 DFS","subtitle":"活动结点、完成结点与真实 LLDB 递归栈同步显示","category":"graph","renderer":"graph","graph_mode":"dfs","pseudo":["1. 初始化：所有结点均为 unseen","2. 进入 A，压入递归栈","3. 从 A 进入 B","4. 从 B 进入 D","5. 回溯后从 B 进入 E","6. 从 E 进入 C","7. 全部递归返回，DFS 完成"],"display_source":DFS_DISPLAY,"source":DFS_SOURCE,"display_stage_lines":[18,2,9,9,9,9,13],"display_stage_text":["dfs(A, 0);","state[current] = ACTIVE;","dfs(next, depth + 1);","dfs(next, depth + 1);","dfs(next, depth + 1);","dfs(next, depth + 1);","state[current] = FINISHED;"],"frame_vars":["current","depth","state","parent","metric","stack","stack_size","order","order_len"],"pointer_names":[],"breakpoint_mode":"snap-caller"},
    "adjacency-list-build-edit": {"title":"邻接表：建图、添加边与删除边","subtitle":"表头数组、边结点 next 指针和无向边双份存储同步显示","category":"graph","renderer":"graph","graph_mode":"edit","pseudo":["1. 建立 A、B、C、D 四个空表头","2. 添加无向边 A-B、A-C、B-D、C-D","3. 每条无向边在两个邻接链中各分配一个边结点","4. 删除 A-C，同时从 A、C 两条邻接链摘除并释放边结点","5. 最终边集合为 A-B、B-D、C-D"],"display_source":ADJACENCY_LIST_DISPLAY,"source":ADJACENCY_LIST_SOURCE,"display_stage_lines":[6,19,20,21,22,23],"display_stage_text":["初始化 heads[]","add_edge(A, B);","add_edge(A, C);","add_edge(B, D);","add_edge(C, D);","remove_edge(A, C);"],"frame_vars":["heads","adj","edge_count","current","operation"],"breakpoint_mode":"snap-caller"},
}

DEMO_DETAILS = {
    "linked-list-insert": {"method":"头插法","position":"链表表头","storage":"动态单链表（堆结点 + next 指针）","initial":"10 → NULL","result":"20 → 10 → NULL","time":"O(1)","space":"O(1)，另分配 1 个新结点","precondition":"内存分配成功","key":"先令 s->next = head，再修改 head，避免原链表丢失"},
    "linked-list-delete-head": {"method":"删除首元结点","position":"链表表头","storage":"动态单链表（堆结点 + next 指针）","initial":"10 → 20 → NULL","result":"20 → NULL","time":"O(1)","space":"O(1)","precondition":"head != NULL","key":"先保存待删结点，再移动 head，最后 free 原结点"},
    "linked-list-complete-operations": {"method":"尾插 + 指定位置插入 + 迭代反转","position":"表尾、下标 1、整条链表","storage":"动态单链表（head/tail 与 prev/current/next）","initial":"10 → 20","result":"尾插和中间插入后反转为 30 → 20 → 15 → 10","time":"尾插 O(1)，定位插入 O(n)，反转 O(n)","space":"O(1)，插入各分配 1 个结点","precondition":"tail 指向末结点；pos 合法；链表无环","key":"插入先保存后继；反转每轮必须先保存 next，最后交换 head/tail"},
    "merge-two-sorted-lists-in-place": {"method":"双指针原地有序合并","position":"每轮比较 p1->data 与 p2->data，接到 tail 后方","storage":"两条输入单链表 + 一条结果链，共用原有 6 个堆结点","initial":"A: 1 → 4 → 7；B: 2 → 3 → 8","result":"result: 1 → 2 → 3 → 4 → 7 → 8","time":"O(m + n)","space":"O(1)，合并阶段不分配数据结点","precondition":"两条输入链均升序、无环且不共享结点","key":"先保存 next，再摘下 selected；一条链耗尽后直接串接剩余段。每个原结点必须恰好出现一次"},
    "sequence-list-insert": {"method":"指定位置插入（中间插入，非尾插）","position":"下标 pos = 2","storage":"顺序存储（连续数组）","initial":"[10, 20, 30, 40]，length=4","result":"[10, 20, 99, 30, 40]，length=5","time":"O(n)","space":"O(1)","precondition":"0 ≤ pos ≤ length 且 length < capacity","key":"必须从后向前搬移 [pos, length-1]，否则会覆盖尚未复制的元素"},
    "sequence-list-append": {"method":"尾插法（append）","position":"表尾 pos = length = 4","storage":"顺序存储（连续数组）","initial":"[10, 20, 30, 40]，length=4","result":"[10, 20, 30, 40, 50]，length=5","time":"O(1)（本演示容量充足）","space":"O(1)","precondition":"length < capacity；若容量不足需先扩容","key":"写入 arr[length] 后再执行 length++，不需要搬移已有元素"},
    "sequence-list-complete-operations": {"method":"顺序查找 + 指定位置删除 + 容量检查","position":"查找值 30；删除下标 2；表尾写入","storage":"固定容量连续数组","initial":"[10,20,30,40,50,60]，length=capacity=6","result":"[10,20,40,50,60,99]；尾插 100 被拒绝","time":"查找 O(n)，删除 O(n)，容量检查 O(1)","space":"O(1)","precondition":"删除位置合法；写入前检查 length < capacity","key":"删除必须从前向后左移；满容量时不能写 arr[length]"},
    "stack-push-pop": {"method":"顺序栈入栈 + 出栈","position":"仅操作栈顶 top","storage":"顺序栈（连续数组，LIFO）","initial":"栈底 [10, 20] 栈顶","result":"push 30 后再 pop，逻辑栈恢复为 [10, 20]","time":"push O(1)，pop O(1)","space":"O(1)","precondition":"push 前栈未满；pop 前栈非空","key":"top 决定逻辑有效区；pop 后槽位中的 30 只是物理残留"},
    "circular-queue-enqueue-dequeue": {"method":"循环队列入队 + 出队","position":"rear 写入，front 读取","storage":"循环数组（FIFO）","initial":"front=2，rear=4，逻辑队列 [20, 30]","result":"入队 40、出队 20，得到 [30, 40]","time":"enqueue O(1)，dequeue O(1)","space":"O(1)","precondition":"入队前队列未满；出队前队列非空","key":"索引用 (index + 1) % capacity 回绕；物理下标不等于逻辑顺序"},
    "bst-insert": {"method":"二叉搜索树递归插入","position":"按比较结果定位叶子空位","storage":"链式二叉树（堆结点）","initial":"根 50，左 30，右 70","result":"60 成为 70 的左孩子","time":"平均 O(log n)，最坏 O(n)","space":"递归栈平均 O(log n)，最坏 O(n)","precondition":"满足 BST：左子树 < 根 < 右子树","key":"比较决定递归方向；返回时把新子树根重新连接给父结点"},
    "bst-search-delete": {"method":"BST 迭代搜索 + 双孩子结点删除","position":"搜索 60；删除 70","storage":"链式二叉搜索树","initial":"中序 30,50,60,70,80","result":"找到 60；删除 70 后中序为 30,50,60,80","time":"平均 O(log n)，最坏 O(n)","space":"O(1)","precondition":"输入满足 BST 次序；删除目标存在","key":"双孩子删除用中序后继替换数据，再删除至多一个孩子的后继原结点"},
    "red-black-tree-insert": {"method":"红黑树插入修复（重染色 + 单旋）","position":"按 BST 插入 1、0，再自底向上修复","storage":"带 parent 与 color 元数据的链式二叉搜索树","initial":"10(B)，左 5(R)，右 15(R)","result":"10(B) 的左子树变为 1(B)，其孩子为 0(R)、5(R)","time":"每次插入 O(log n)","space":"迭代修复 O(1)","precondition":"输入树满足 BST 次序和 5 条红黑性质","key":"新结点先染红；红叔重染色，黑叔按内外侧结构旋转；根最终强制为黑"},
    "red-black-tree-rotation-cases": {"method":"红父黑叔的四类插入旋转修复","position":"LL、RR、LR、RL 局部三结点子树","storage":"带 parent 与 color 的链式红黑树","initial":"四个独立的红红冲突局部树","result":"每种均变为黑色中值根、两个红色孩子","time":"每次修复 O(1)，完整插入 O(log n)","space":"O(1)","precondition":"叔结点为黑色或 NIL；祖父存在","key":"外侧 LL/RR 单旋；内侧 LR/RL 先旋父再旋祖父；旋转前后同步重染色"},
    "graph-bfs": {"method":"广度优先搜索（BFS）","position":"从顶点 A 开始，按层扩展","storage":"邻接矩阵 + 循环队列","initial":"5 个顶点均为 unseen","result":"访问序列 A → B → C → D → E","time":"邻接矩阵 O(V²)","space":"O(V)","precondition":"发现顶点时立即标记 frontier，避免重复入队","key":"FIFO 队列保证按距离层次访问；parent 边组成 BFS 生成树"},
    "graph-dfs": {"method":"深度优先搜索（DFS）","position":"从顶点 A 开始，递归深入","storage":"邻接矩阵 + 递归调用栈","initial":"5 个顶点均为 unseen","result":"先序访问 A → B → D → E → C","time":"邻接矩阵 O(V²)","space":"O(V)","precondition":"进入顶点时标记 active，返回前标记 finished","key":"LIFO 递归栈记录当前搜索路径；回溯后继续扫描未访问邻接点"},
    "adjacency-list-build-edit": {"method":"无向图邻接表建图、加边、删边","position":"heads[A..D] 对应的边链表","storage":"表头数组 + 动态 Edge(to,next) 结点","initial":"4 个顶点，0 条边","result":"删除 A-C 后保留 A-B、B-D、C-D","time":"头插加边 O(1)，删除 O(deg(u)+deg(v))","space":"O(V+E)","precondition":"顶点编号合法；演示不允许重复边","key":"无向边必须在两条邻接链各存一份；删除时两侧都要摘除并 free"},
}

DEMOS.update(EXTENDED_DEMOS)
DEMO_DETAILS.update(EXTENDED_DETAILS)
for _demo_id, _details in DEMO_DETAILS.items():
    DEMOS[_demo_id]["details"] = _details

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


def _extract_call_stack(block:str)->list[dict]:
    frames={}
    for line in block.splitlines():
        match=re.search(r"frame #(\d+):.*?`([A-Za-z_][A-Za-z0-9_]*)",line)
        if match:frames[int(match.group(1))]=match.group(2)
    result=[]
    for index in sorted(frames):
        result.append({"index":index,"function":frames[index]})
        if frames[index]=="main":break
    return result


def _run_demo_lldb(exe:Path,td:str,demo:dict)->dict:
    caller_mode=demo.get("breakpoint_mode")=="snap-caller"
    trace_lines=_trace_lines(demo["source"]);count=len(demo["display_stage_lines"]);vars_=demo["frame_vars"]
    commands=(["breakpoint set --name snap"] if caller_mode else [f"breakpoint set --file demo.c --line {line}" for line in trace_lines])+["run"]
    for _ in range(count):
        commands += ["script print('FIVEVIEW_FRAME_BEGIN')"]
        if caller_mode:commands += ["frame select 1"]
        commands += ["frame info",f"frame variable {' '.join(vars_)}","bt 8" if caller_mode else "bt 3","script print('FIVEVIEW_FRAME_END')","continue"]
    argv=["lldb","--batch"]
    for cmd in commands:argv.extend(["-o",cmd])
    argv.append(str(exe));dbg=subprocess.run(argv,cwd=td,capture_output=True,text=True,timeout=18,env={"PATH":os.environ.get("PATH","/usr/bin:/bin")})
    combined=f"{dbg.stdout}\n{dbg.stderr}";snapshots,program_stdout=_parse_program_output(combined);blocks=_extract_frame_blocks(combined);hits=min(count,len(snapshots),len(blocks))
    for i,snap in enumerate(snapshots[:count]):
        block=blocks[i] if i<len(blocks) else "";compiled_line=trace_lines[min(i,len(trace_lines)-1)] if trace_lines else 0;snap["debugger"]={"engine":"lldb","breakpoint_hit":i+1,"compiled_source_line":compiled_line,"display_source_line":demo["display_stage_lines"][i],"display_source_text":demo["display_stage_text"][i],"frame_variables_read":all(name in block for name in vars_),"call_stack":_extract_call_stack(block),"frame_excerpt":block[-2400:]}
    return {"success":dbg.returncode==0 and hits>=count and len(snapshots)==count and len(blocks)>=count,"snapshots":snapshots,"stdout":program_stdout,"breakpoint_hits":hits,"frame_reads":len(blocks),"trace":combined[-9000:]}


def _normalize_snapshot(raw:dict,demo:dict)->dict:
    renderer=demo["renderer"];variables=[];objects=[];relations=[]
    if renderer in {"singly-linked-list","multi-linked-list"}:
        values=raw.get("values",{});heap=raw.get("heap",[]);by_addr={str(n.get("address")):n for n in heap}
        pointer_names=set(demo.get("pointer_names",[]))
        for name,value in values.items():variables.append({"name":name,"type":"Node *" if name in pointer_names else "int","value":value,"kind":"pointer" if name in pointer_names else "scalar"})
        for node in heap:
            objects.append({"id":str(node.get("address")),"type":"Node","address":node.get("address"),"label":node.get("name"),"fields":{"data":node.get("data"),"next":node.get("next")}})
            nxt=node.get("next")
            if nxt and str(nxt) in by_addr:relations.append({"from":str(node.get("address")),"field":"next","to":str(nxt),"kind":"pointer"})
        for name in demo.get("pointer_names",[]):
            value=values.get(name)
            if value and str(value) in by_addr:relations.append({"from":name,"to":str(value),"kind":"variable-pointer"})
    elif renderer in {"array","binary-heap"}:
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
    elif renderer in {"binary-tree","red-black-tree"}:
        values=raw.get("values",{});nodes=raw.get("tree",[]);by_addr={str(n.get("address")):n for n in nodes}
        for name,value in values.items():variables.append({"name":name,"type":"Node *" if name in {"root","current","new_node"} else "int","value":value,"kind":"pointer" if name in {"root","current","new_node"} else "scalar"})
        for node in nodes:
            address=str(node.get("address"));fields={"data":node.get("data"),"left":node.get("left"),"right":node.get("right"),"detached":node.get("detached",False)}
            for metadata in ("parent","color","height","balance","priority","range","sum"):
                if metadata in node:fields[metadata]=node.get(metadata)
            objects.append({"id":address,"type":"TreeNode","address":address,"label":str(node.get("data")),"fields":fields})
            for field in ("left","right"):
                child=str(node.get(field))
                if child in by_addr:relations.append({"from":address,"field":field,"to":child,"kind":"tree-edge"})
        for name in demo.get("pointer_names",[]):
            value=str(values.get(name))
            if value in by_addr:relations.append({"from":name,"to":value,"kind":"variable-pointer"})
    elif renderer=="hash-table":
        values=raw.get("values",{});slots=raw.get("hash",[])
        for name,value in values.items():variables.append({"name":name,"type":"int","value":value,"kind":"slot-index" if name=="probe" else "scalar"})
        for slot in slots:objects.append({"id":f"hash-slot-{slot['index']}","type":"HashSlot","address":slot.get("address"),"label":str(slot["index"]),"fields":{"key":slot.get("key"),"value":slot.get("value"),"state":slot.get("state")}})
    elif renderer=="union-find":
        values=raw.get("values",{});items=raw.get("dsu",[])
        for name,value in values.items():variables.append({"name":name,"type":"int","value":value,"kind":"element-index" if name in {"current","root_a","root_b"} else "scalar"})
        for item in items:
            objects.append({"id":f"dsu-{item['index']}","type":"DisjointSetNode","address":item.get("address"),"label":str(item["index"]),"fields":{"parent":item.get("parent"),"rank":item.get("rank")}})
            if item.get("parent")!=item.get("index"):relations.append({"from":f"dsu-{item['index']}","to":f"dsu-{item['parent']}","kind":"parent-link"})
    elif renderer=="trie":
        values=raw.get("values",{});trie=raw.get("trie",{})
        for name,value in values.items():variables.append({"name":name,"type":"int","value":value,"kind":"node-index" if name=="current" else "scalar"})
        for node in trie.get("nodes",[]):objects.append({"id":f"trie-{node['id']}","type":"TrieNode","address":node.get("address"),"label":node.get("char"),"fields":{"parent":node.get("parent"),"terminal":node.get("terminal")}})
        for edge in trie.get("edges",[]):relations.append({"from":f"trie-{edge['from']}","to":f"trie-{edge['to']}","field":edge.get("char"),"kind":"character-edge"})
    elif renderer=="graph":
        values=raw.get("values",{});graph=raw.get("graph",{});vertices=graph.get("vertices",[])
        for name,value in values.items():variables.append({"name":name,"type":"int","value":value,"kind":"vertex-index" if name=="current" else "scalar"})
        for vertex in vertices:objects.append({"id":f"vertex-{vertex['id']}","type":"GraphVertex","address":vertex.get("address"),"label":vertex.get("label"),"fields":{"state":vertex.get("state"),"parent":vertex.get("parent"),"metric":vertex.get("metric")}})
        for edge in graph.get("edges",[]):relations.append({"from":f"vertex-{edge['from']}","to":f"vertex-{edge['to']}","kind":"graph-edge"})
        for vertex in vertices:
            if vertex.get("parent",-1)>=0:relations.append({"from":f"vertex-{vertex['parent']}","to":f"vertex-{vertex['id']}","kind":"traversal-tree"})
    visualization={"renderer":renderer,"category":demo["category"]}
    if renderer=="multi-linked-list":visualization["mode"]=demo.get("problem_mode","linked-list-problem")
    if renderer=="graph":visualization["mode"]=demo.get("graph_mode")
    if renderer in {"binary-tree","red-black-tree"}:visualization["mode"]=demo.get("tree_mode","binary-search")
    raw["model"]={"schema":"five-view.snapshot.v1","variables":variables,"objects":objects,"relations":relations,"execution":raw.get("debugger",{}),"visualization":visualization}
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
        return {"demo_id":demo_id,"title":demo["title"],"subtitle":demo["subtitle"],"details":demo.get("details",{}),"category":demo["category"],"renderer":demo["renderer"],"problem_mode":demo.get("problem_mode"),"graph_mode":demo.get("graph_mode"),"tree_mode":demo.get("tree_mode"),"pseudo":demo["pseudo"],"display_source":demo["display_source"],"pointer_names":demo.get("pointer_names",[]),"snapshot_schema":"five-view.snapshot.v1","compiler":"clang","debug_build":True,"execution_engine":engine,"lldb_breakpoint_hits":lr["breakpoint_hits"],"lldb_frame_reads":lr["frame_reads"],"lldb_fallback":fallback,"timeline_mode":"source-line","storage_semantics":"LLDB 负责真实源码断点与局部变量读取；结构化快照归一化为统一 snapshot model，再由数据结构专用 Renderer 解释。","address_note":"地址来自本次 Render 容器中的真实 C 调试进程；ASLR 会使不同运行地址变化。","snapshots":snapshots,"stdout":program_stdout}


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
def list_demos():return utf8_json([{"id":k,"title":v["title"],"subtitle":v["subtitle"],"details":v.get("details",{}),"category":v["category"],"renderer":v["renderer"],"problem_mode":v.get("problem_mode"),"graph_mode":v.get("graph_mode"),"tree_mode":v.get("tree_mode")} for k,v in DEMOS.items()])
@app.get("/api/debugger-capability")
def debugger_capability():return utf8_json(_debugger_capability())
@app.post("/api/run-demo")
def run_demo(req:DemoRequest):return utf8_json(_run_demo(req.demo_id))
@app.post("/api/execute")
def execute_disabled():raise HTTPException(status_code=403,detail="Arbitrary C execution is disabled. Use /api/run-demo with a whitelisted teaching demo.")
