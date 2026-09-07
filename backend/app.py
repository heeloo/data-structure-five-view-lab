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

APP_VERSION = "1.3.0"
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
    "sequence-list-insert": {"title":"顺序表：指定位置插入（中间插入）","subtitle":"下标 2 插入；从后向前搬移元素，并非尾插法","category":"array","renderer":"array","pseudo":["1. 原数组 [10,20,30,40]，在下标 2 插入 99","2. 从尾部开始向右搬移 arr[3]","3. 继续搬移 arr[2]","4. arr[2] = 99，length++"],"display_source":ARRAY_DISPLAY,"source":ARRAY_SOURCE,"display_stage_lines":[7,8,10,12],"display_stage_text":["int i = 4;","arr[4] = arr[3];","arr[3] = arr[2];","arr[2] = value;"],"frame_vars":["arr","length","capacity","pos","value","i"],"pointer_names":[]},
    "sequence-list-append": {"title":"顺序表：尾插法（append）","subtitle":"在下标 length 直接写入；容量充足时无需搬移元素","category":"array","renderer":"array","pseudo":["1. 检查 length < capacity，确认表尾有空闲容量","2. pos = length，定位第一个空闲槽位","3. arr[pos] = 50，写入表尾","4. length++，新元素纳入有效区间"],"display_source":ARRAY_APPEND_DISPLAY,"source":ARRAY_APPEND_SOURCE,"display_stage_lines":[5,8,9],"display_stage_text":["int pos = length;","arr[pos] = value;","length++;"],"frame_vars":["arr","length","capacity","pos","value","i"],"pointer_names":[]},
    "stack-push-pop": {"title":"顺序栈：push 与 pop","subtitle":"栈顶移动、有效区间与残留内存值同步显示","category":"stack","renderer":"stack","pseudo":["1. 原栈自底向上为 [10, 20]","2. top++，为新元素预留栈顶位置","3. data[top] = 30，push 完成","4. popped = data[top]，读取栈顶","5. top--，pop 完成（物理槽位仍保留 30）"],"display_source":STACK_DISPLAY,"source":STACK_SOURCE,"display_stage_lines":[3,8,9,12,13],"display_stage_text":["int top = 1;","top++;","data[top] = value;","popped = data[top];","top--;"],"frame_vars":["data","top","capacity","value","popped"],"pointer_names":[]},
    "circular-queue-enqueue-dequeue": {"title":"循环队列：enqueue 与 dequeue","subtitle":"队首、队尾、有效元素与 rear 回绕同步显示","category":"queue","renderer":"circular-queue","pseudo":["1. 原队列 front=2、rear=4，逻辑内容 [20, 30]","2. queue[rear] = 40，写入待入队元素","3. rear = (rear + 1) % capacity，回绕到 0","4. removed = queue[front]，读取队首 20","5. front 前移且 size--，dequeue 完成"],"display_source":QUEUE_DISPLAY,"source":QUEUE_SOURCE,"display_stage_lines":[3,10,11,15,16],"display_stage_text":["int front = 2;","queue[rear] = value;","rear = (rear + 1) % 5;","removed = queue[front];","front = (front + 1) % 5;"],"frame_vars":["queue","front","rear","size","capacity","value","removed"],"pointer_names":[]},
    "bst-insert": {"title":"二叉搜索树：递归插入 60","subtitle":"树形拓扑、比较方向与真实 LLDB 递归调用栈同步显示","category":"tree","renderer":"binary-tree","pseudo":["1. 建立二叉搜索树：根 50，左 30，右 70","2. 比较 60 > 50，递归进入右子树","3. 比较 60 < 70，递归进入左子树","4. 到达 NULL，分配结点 60","5. 递归回溯，将 70->left 指向 60","6. 插入完成，中序序列为 30, 50, 60, 70"],"display_source":TREE_DISPLAY,"source":TREE_SOURCE,"display_stage_lines":[21,13,11,8,11,23],"display_stage_text":["root->right = make_node(70);","current->right = bst_insert(...);","current->left = bst_insert(...);","return make_node(target);","current->left = bst_insert(...);","root = bst_insert(root, 60);"],"frame_vars":["root","current","new_node","target","depth","direction"],"pointer_names":["root","current","new_node"],"breakpoint_mode":"snap-caller"},
    "red-black-tree-insert": {"title":"红黑树：插入 1、0（重染色 + 右旋）","subtitle":"验证红黑性质、父叔颜色分支、重染色与旋转后的拓扑变化","category":"tree","renderer":"red-black-tree","tree_mode":"red-black","pseudo":["1. 初始合法树：10(B) 的孩子为 5(R)、15(R)","2. 插入 1(R)，作为 5 的左孩子","3. 检测到父结点 5 与叔结点 15 均为红色","4. 父叔染黑、祖父 10 暂时染红","5. 根结点恢复黑色，第一次插入完成","6. 插入 0(R)，与红色父结点 1 冲突","7. 叔结点为黑色且形成 LL 外侧结构","8. 父结点 1 染黑、祖父 5 染红并右旋","9. 验证根黑、红结点子女黑、各根叶路径黑高一致"],"display_source":RB_TREE_DISPLAY,"source":RB_TREE_SOURCE,"display_stage_lines":[21,3,7,10,18,3,12,15,18],"display_stage_text":["rb_insert(1);","node->color = RED;","if (uncle->color == RED)","grandparent->color = RED;","root->color = BLACK;","node->color = RED;","else // uncle is BLACK","rotate_right(grandparent);","root->color = BLACK;"],"frame_vars":["g_root","g_current","g_new_node","g_target","g_case"],"pointer_names":["root","current","new_node"],"breakpoint_mode":"snap-caller"},
    "graph-bfs": {"title":"图：广度优先搜索 BFS","subtitle":"结点状态、生成树边与真实循环队列同步显示","category":"graph","renderer":"graph","graph_mode":"bfs","pseudo":["1. A 入队，标记为 frontier","2. A 出队并标记 visited","3. 扫描 A，发现 B、C 并入队","4. B 出队，发现 D、E 并入队","5. C 出队，相邻结点均已发现","6. 继续处理 D、E，BFS 完成"],"display_source":BFS_DISPLAY,"source":BFS_SOURCE,"display_stage_lines":[3,6,11,15,11,5],"display_stage_text":["queue[rear++] = start;","current = queue[front++];","扫描 A 的相邻结点","queue[rear++] = next;","扫描 C 的相邻结点","while (front < rear)"],"frame_vars":["state","parent","distance","queue","front","rear","current","order","order_len"],"pointer_names":[],"breakpoint_mode":"snap-caller"},
    "graph-dfs": {"title":"图：深度优先搜索 DFS","subtitle":"活动结点、完成结点与真实 LLDB 递归栈同步显示","category":"graph","renderer":"graph","graph_mode":"dfs","pseudo":["1. 初始化：所有结点均为 unseen","2. 进入 A，压入递归栈","3. 从 A 进入 B","4. 从 B 进入 D","5. 回溯后从 B 进入 E","6. 从 E 进入 C","7. 全部递归返回，DFS 完成"],"display_source":DFS_DISPLAY,"source":DFS_SOURCE,"display_stage_lines":[18,2,9,9,9,9,13],"display_stage_text":["dfs(A, 0);","state[current] = ACTIVE;","dfs(next, depth + 1);","dfs(next, depth + 1);","dfs(next, depth + 1);","dfs(next, depth + 1);","state[current] = FINISHED;"],"frame_vars":["current","depth","state","parent","metric","stack","stack_size","order","order_len"],"pointer_names":[],"breakpoint_mode":"snap-caller"},
}

DEMO_DETAILS = {
    "linked-list-insert": {"method":"头插法","position":"链表表头","storage":"动态单链表（堆结点 + next 指针）","initial":"10 → NULL","result":"20 → 10 → NULL","time":"O(1)","space":"O(1)，另分配 1 个新结点","precondition":"内存分配成功","key":"先令 s->next = head，再修改 head，避免原链表丢失"},
    "linked-list-delete-head": {"method":"删除首元结点","position":"链表表头","storage":"动态单链表（堆结点 + next 指针）","initial":"10 → 20 → NULL","result":"20 → NULL","time":"O(1)","space":"O(1)","precondition":"head != NULL","key":"先保存待删结点，再移动 head，最后 free 原结点"},
    "sequence-list-insert": {"method":"指定位置插入（中间插入，非尾插）","position":"下标 pos = 2","storage":"顺序存储（连续数组）","initial":"[10, 20, 30, 40]，length=4","result":"[10, 20, 99, 30, 40]，length=5","time":"O(n)","space":"O(1)","precondition":"0 ≤ pos ≤ length 且 length < capacity","key":"必须从后向前搬移 [pos, length-1]，否则会覆盖尚未复制的元素"},
    "sequence-list-append": {"method":"尾插法（append）","position":"表尾 pos = length = 4","storage":"顺序存储（连续数组）","initial":"[10, 20, 30, 40]，length=4","result":"[10, 20, 30, 40, 50]，length=5","time":"O(1)（本演示容量充足）","space":"O(1)","precondition":"length < capacity；若容量不足需先扩容","key":"写入 arr[length] 后再执行 length++，不需要搬移已有元素"},
    "stack-push-pop": {"method":"顺序栈入栈 + 出栈","position":"仅操作栈顶 top","storage":"顺序栈（连续数组，LIFO）","initial":"栈底 [10, 20] 栈顶","result":"push 30 后再 pop，逻辑栈恢复为 [10, 20]","time":"push O(1)，pop O(1)","space":"O(1)","precondition":"push 前栈未满；pop 前栈非空","key":"top 决定逻辑有效区；pop 后槽位中的 30 只是物理残留"},
    "circular-queue-enqueue-dequeue": {"method":"循环队列入队 + 出队","position":"rear 写入，front 读取","storage":"循环数组（FIFO）","initial":"front=2，rear=4，逻辑队列 [20, 30]","result":"入队 40、出队 20，得到 [30, 40]","time":"enqueue O(1)，dequeue O(1)","space":"O(1)","precondition":"入队前队列未满；出队前队列非空","key":"索引用 (index + 1) % capacity 回绕；物理下标不等于逻辑顺序"},
    "bst-insert": {"method":"二叉搜索树递归插入","position":"按比较结果定位叶子空位","storage":"链式二叉树（堆结点）","initial":"根 50，左 30，右 70","result":"60 成为 70 的左孩子","time":"平均 O(log n)，最坏 O(n)","space":"递归栈平均 O(log n)，最坏 O(n)","precondition":"满足 BST：左子树 < 根 < 右子树","key":"比较决定递归方向；返回时把新子树根重新连接给父结点"},
    "red-black-tree-insert": {"method":"红黑树插入修复（重染色 + 单旋）","position":"按 BST 插入 1、0，再自底向上修复","storage":"带 parent 与 color 元数据的链式二叉搜索树","initial":"10(B)，左 5(R)，右 15(R)","result":"10(B) 的左子树变为 1(B)，其孩子为 0(R)、5(R)","time":"每次插入 O(log n)","space":"迭代修复 O(1)","precondition":"输入树满足 BST 次序和 5 条红黑性质","key":"新结点先染红；红叔重染色，黑叔按内外侧结构旋转；根最终强制为黑"},
    "graph-bfs": {"method":"广度优先搜索（BFS）","position":"从顶点 A 开始，按层扩展","storage":"邻接矩阵 + 循环队列","initial":"5 个顶点均为 unseen","result":"访问序列 A → B → C → D → E","time":"邻接矩阵 O(V²)","space":"O(V)","precondition":"发现顶点时立即标记 frontier，避免重复入队","key":"FIFO 队列保证按距离层次访问；parent 边组成 BFS 生成树"},
    "graph-dfs": {"method":"深度优先搜索（DFS）","position":"从顶点 A 开始，递归深入","storage":"邻接矩阵 + 递归调用栈","initial":"5 个顶点均为 unseen","result":"先序访问 A → B → D → E → C","time":"邻接矩阵 O(V²)","space":"O(V)","precondition":"进入顶点时标记 active，返回前标记 finished","key":"LIFO 递归栈记录当前搜索路径；回溯后继续扫描未访问邻接点"},
}

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
    elif renderer in {"binary-tree","red-black-tree"}:
        values=raw.get("values",{});nodes=raw.get("tree",[]);by_addr={str(n.get("address")):n for n in nodes}
        for name,value in values.items():variables.append({"name":name,"type":"Node *" if name in {"root","current","new_node"} else "int","value":value,"kind":"pointer" if name in {"root","current","new_node"} else "scalar"})
        for node in nodes:
            address=str(node.get("address"));fields={"data":node.get("data"),"left":node.get("left"),"right":node.get("right"),"detached":node.get("detached",False)}
            for metadata in ("parent","color","height","balance","priority"):
                if metadata in node:fields[metadata]=node.get(metadata)
            objects.append({"id":address,"type":"TreeNode","address":address,"label":str(node.get("data")),"fields":fields})
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
        return {"demo_id":demo_id,"title":demo["title"],"subtitle":demo["subtitle"],"details":demo.get("details",{}),"category":demo["category"],"renderer":demo["renderer"],"graph_mode":demo.get("graph_mode"),"tree_mode":demo.get("tree_mode"),"pseudo":demo["pseudo"],"display_source":demo["display_source"],"pointer_names":demo.get("pointer_names",[]),"snapshot_schema":"five-view.snapshot.v1","compiler":"clang","debug_build":True,"execution_engine":engine,"lldb_breakpoint_hits":lr["breakpoint_hits"],"lldb_frame_reads":lr["frame_reads"],"lldb_fallback":fallback,"timeline_mode":"source-line","storage_semantics":"LLDB 负责真实源码断点与局部变量读取；结构化快照归一化为统一 snapshot model，再由数据结构专用 Renderer 解释。","address_note":"地址来自本次 Render 容器中的真实 C 调试进程；ASLR 会使不同运行地址变化。","snapshots":snapshots,"stdout":program_stdout}


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
def list_demos():return utf8_json([{"id":k,"title":v["title"],"subtitle":v["subtitle"],"details":v.get("details",{}),"category":v["category"],"renderer":v["renderer"],"tree_mode":v.get("tree_mode")} for k,v in DEMOS.items()])
@app.get("/api/debugger-capability")
def debugger_capability():return utf8_json(_debugger_capability())
@app.post("/api/run-demo")
def run_demo(req:DemoRequest):return utf8_json(_run_demo(req.demo_id))
@app.post("/api/execute")
def execute_disabled():raise HTTPException(status_code=403,detail="Arbitrary C execution is disabled. Use /api/run-demo with a whitelisted teaching demo.")
