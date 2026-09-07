# 数据结构五维教学实验室

GitHub Pages 前端 + Render 后端的数据结构可视化实验室。

五个同步视角：PSEUDO / C / STORAGE / POINTER / EXECUTION。

## v1.1 演示

- 单链表头插、删除首元结点
- 顺序表指定位置插入
- 顺序栈 push / pop
- 循环队列 enqueue / dequeue（含 `rear` 回绕）
- 二叉搜索树递归插入（含真实 LLDB 调用栈）
- 图的广度优先搜索 BFS（队列联动）
- 图的深度优先搜索 DFS（递归栈联动）

每个演示都由后端使用 Clang `-O0 -g` 编译，并优先通过 LLDB 源码断点采集真实运行状态。统一 Snapshot Model 同时驱动 ALGORITHM、SOURCE、MEMORY、STRUCTURE、EXECUTION 五个视图。
