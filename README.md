# 数据结构五维教学实验室

GitHub Pages 前端 + Render 后端的数据结构可视化实验室。

五个同步视角：PSEUDO / C / STORAGE / POINTER / EXECUTION。

## v1.2 演示

- 单链表头插、删除首元结点
- 顺序表指定位置插入（中间插入，需要搬移元素）
- 顺序表尾插法 append（容量充足时无需搬移）
- 顺序栈 push / pop
- 循环队列 enqueue / dequeue（含 `rear` 回绕）
- 二叉搜索树递归插入（含真实 LLDB 调用栈）
- 图的广度优先搜索 BFS（队列联动）
- 图的深度优先搜索 DFS（递归栈联动）

每个演示都由后端使用 Clang `-O0 -g` 编译，并优先通过 LLDB 源码断点采集真实运行状态。统一 Snapshot Model 同时驱动 ALGORITHM、SOURCE、MEMORY、STRUCTURE、EXECUTION 五个视图。

页面会为每个算法明确显示操作方法、操作位置、存储结构、初始状态、目标结果、时间复杂度、辅助空间、前置条件和关键规则，并支持持久化的明暗主题切换。
