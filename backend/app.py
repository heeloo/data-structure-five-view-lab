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

APP_VERSION = "1.1.0"
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

DEMOS = {
    "linked-list-insert": {"title":"单链表：头插一个新结点","subtitle":"节点与指针关系视图","category":"linked-list","renderer":"singly-linked-list","pseudo":["1. 建立原链表 head -> a","2. 申请新结点 s","3. s->next = head","4. head = s"],"display_source":INSERT_DISPLAY,"source":INSERT_SOURCE,"display_stage_lines":[14,18,20,21],"display_stage_text":["head = a;","s->next = NULL;","s->next = head;","head = s;"],"frame_vars":["head","a","s"],"pointer_names":["head","a","s"]},
    "linked-list-delete-head": {"title":"单链表：删除首元结点","subtitle":"脱链与 free 分开显示","category":"linked-list","renderer":"singly-linked-list","pseudo":["1. 原链表 head -> a -> b","2. p = head 保存待删除结点","3. head = head->next 越过 a","4. free(p) 释放原首结点"],"display_source":DELETE_DISPLAY,"source":DELETE_SOURCE,"display_stage_lines":[16,17,18,19],"display_stage_text":["p = head;","head = head->next;","free(p);","p = NULL;"],"frame_vars":["head","a","b","p"],"pointer_names":["head","a","b","p"]},
    "sequence-list-insert": {"title":"顺序表：指定位置插入","subtitle":"连续内存格、下标与元素搬移视图","category":"array","renderer":"array","pseudo":["1. 原数组 [10,20,30,40]，在下标 2 插入 99","2. 从尾部开始向右搬移 arr[3]","3. 继续搬移 arr[2]","4. arr[2] = 99，length++"],"display_source":ARRAY_DISPLAY,"source":ARRAY_SOURCE,"display_stage_lines":[7,8,10,12],"display_stage_text":["int i = 4;","arr[4] = arr[3];","arr[3] = arr[2];","arr[2] = value;"],"frame_vars":["arr","length","capacity","pos","value","i"],"pointer_names":[]},
    "stack-push-pop": {"title":"顺序栈：push 与 pop","subtitle":"栈顶移动、有效区间与残留内存值同步显示","category":"stack","renderer":"stack","pseudo":["1. 原栈自底向上为 [10, 20]","2. top++，为新元素预留栈顶位置","3. data[top] = 30，push 完成","4. popped = data[top]，读取栈顶","5. top--，pop 完成（物理槽位仍保留 30）"],"display_source":STACK_DISPLAY,"source":STACK_SOURCE,"display_stage_lines":[3,8,9,12,13],"display_stage_text":["int top = 1;","top++;","data[top] = value;","popped = data[top];","top--;"],"frame_vars":["data","top","capacity","value","popped"],"pointer_names":[]},
    "circular-queue-enqueue-dequeue": {"title":"循环队列：enqueue 与 dequeue","subtitle":"队首、队尾、有效元素与 rear 回绕同步显示","category":"queue","renderer":"circular-queue","pseudo":["1. 原队列 front=2、rear=4，逻辑内容 [20, 30]","2. queue[rear] = 40，写入待入队元素","3. rear = (rear + 1) % capacity，回绕到 0","4. removed = queue[front]，读取队首 20","5. front 前移且 size--，dequeue 完成"],"display_source":QUEUE_DISPLAY,"source":QUEUE_SOURCE,"display_stage_lines":[3,10,11,15,16],"display_stage_text":["int front = 2;","queue[rear] = value;","rear = (rear + 1) % 5;","removed = queue[front];","front = (front + 1) % 5;"],"frame_vars":["queue","front","rear","size","capacity","value","removed"],"pointer_names":[]},
    "bst-insert": {"title":"二叉搜索树：递归插入 60","subtitle":"树形拓扑、比较方向与真实 LLDB 递归调用栈同步显示","category":"tree","renderer":"binary-tree","pseudo":["1. 建立二叉搜索树：根 50，左 30，右 70","2. 比较 60 > 50，递归进入右子树","3. 比较 60 < 70，递归进入左子树","4. 到达 NULL，分配结点 60","5. 递归回溯，将 70->left 指向 60","6. 插入完成，中序序列为 30, 50, 60, 70"],"display_source":TREE_DISPLAY,"source":TREE_SOURCE,"display_stage_lines":[21,13,11,8,11,23],"display_stage_text":["root->right = make_node(70);","current->right = bst_insert(...);","current->left = bst_insert(...);","return make_node(target);","current->left = bst_insert(...);","root = bst_insert(root, 60);"],"frame_vars":["root","current","new_node","target","depth","direction"],"pointer_names":["root","current","new_node"],"breakpoint_mode":"snap-caller"},
    "graph-bfs": {"title":"图：广度优先搜索 BFS","subtitle":"结点状态、生成树边与真实循环队列同步显示","category":"graph","renderer":"graph","graph_mode":"bfs","pseudo":["1. A 入队，标记为 frontier","2. A 出队并标记 visited","3. 扫描 A，发现 B、C 并入队","4. B 出队，发现 D、E 并入队","5. C 出队，相邻结点均已发现","6. 继续处理 D、E，BFS 完成"],"display_source":BFS_DISPLAY,"source":BFS_SOURCE,"display_stage_lines":[3,6,11,15,11,5],"display_stage_text":["queue[rear++] = start;","current = queue[front++];","扫描 A 的相邻结点","queue[rear++] = next;","扫描 C 的相邻结点","while (front < rear)"],"frame_vars":["state","parent","distance","queue","front","rear","current","order","order_len"],"pointer_names":[]},
    "graph-dfs": {"title":"图：深度优先搜索 DFS","subtitle":"活动结点、完成结点与真实 LLDB 递归栈同步显示","category":"graph","renderer":"graph","graph_mode":"dfs","pseudo":["1. 初始化：所有结点均为 unseen","2. 进入 A，压入递归栈","3. 从 A 进入 B","4. 从 B 进入 D","5. 回溯后从 B 进入 E","6. 从 E 进入 C","7. 全部递归返回，DFS 完成"],"display_source":DFS_DISPLAY,"source":DFS_SOURCE,"display_stage_lines":[19,2,9,9,9,9,14],"display_stage_text":["dfs(A, 0);","state[current] = ACTIVE;","dfs(next, depth + 1);","dfs(next, depth + 1);","dfs(next, depth + 1);","dfs(next, depth + 1);","state[current] = FINISHED;"],"frame_vars":["current","depth","state","parent","metric","stack","stack_size","order","order_len"],"pointer_names":[],"breakpoint_mode":"snap-caller"},
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
    elif renderer=="binary-tree":
        values=raw.get("values",{});nodes=raw.get("tree",[]);by_addr={str(n.get("address")):n for n in nodes}
        for name,value in values.items():variables.append({"name":name,"type":"Node *" if name in {"root","current","new_node"} else "int","value":value,"kind":"pointer" if name in {"root","current","new_node"} else "scalar"})
        for node in nodes:
            address=str(node.get("address"));objects.append({"id":address,"type":"Node","address":address,"label":str(node.get("data")),"fields":{"data":node.get("data"),"left":node.get("left"),"right":node.get("right"),"detached":node.get("detached",False)}})
            for field in ("left","right"):
                child=str(node.get(field))
                if child in by_addr:relations.append({"from":address,"field":field,"to":child,"kind":"tree-edge"})
        for name in demo.get("pointer_names",[]):
            value=str(values.get(name))
            if value in by_addr:relations.append({"from":name,"to":value,"kind":"variable-pointer"})
    elif renderer=="graph":
        values=raw.get("values",{});graph=raw.get("graph",{});vertices=graph.get("vertices",[])
        for name,value in values.items():variables.append({"name":name,"type":"int","value":value,"kind":"vertex-index" if name=="current" else "scalar"})
        for vertex in vertices:objects.append({"id":f"vertex-{vertex['id']}","type":"GraphVertex","address":vertex.get("address"),"label":vertex.get("label"),"fields":{"state":vertex.get("state"),"parent":vertex.get("parent"),"metric":vertex.get("metric")}})
        for edge in graph.get("edges",[]):relations.append({"from":f"vertex-{edge['from']}","to":f"vertex-{edge['to']}","kind":"graph-edge"})
        for vertex in vertices:
            if vertex.get("parent",-1)>=0:relations.append({"from":f"vertex-{vertex['parent']}","to":f"vertex-{vertex['id']}","kind":"traversal-tree"})
    visualization={"renderer":renderer,"category":demo["category"]}
    if renderer=="graph":visualization["mode"]=demo.get("graph_mode")
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
        return {"demo_id":demo_id,"title":demo["title"],"subtitle":demo["subtitle"],"category":demo["category"],"renderer":demo["renderer"],"graph_mode":demo.get("graph_mode"),"pseudo":demo["pseudo"],"display_source":demo["display_source"],"pointer_names":demo.get("pointer_names",[]),"snapshot_schema":"five-view.snapshot.v1","compiler":"clang","debug_build":True,"execution_engine":engine,"lldb_breakpoint_hits":lr["breakpoint_hits"],"lldb_frame_reads":lr["frame_reads"],"lldb_fallback":fallback,"timeline_mode":"source-line","storage_semantics":"LLDB 负责真实源码断点与局部变量读取；结构化快照归一化为统一 snapshot model，再由数据结构专用 Renderer 解释。","address_note":"地址来自本次 Render 容器中的真实 C 调试进程；ASLR 会使不同运行地址变化。","snapshots":snapshots,"stdout":program_stdout}


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
