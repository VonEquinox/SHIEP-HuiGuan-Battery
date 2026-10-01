# DEV GitHub 上传回执

实际核对时间：2026-10-02 03:26:13 Asia/Shanghai（2026-10-01 19:26:13 UTC）。

本次上传已获用户明确授权：在DEV协作实现、逐阶段Commit并上传GitHub。操作通过本机7897代理，
只创建/更新DEV，不合并main、不强推、不建立PR。

```bash
git -c http.proxy=http://127.0.0.1:7897 push -u origin DEV
git -c http.proxy=http://127.0.0.1:7897 ls-remote --heads origin DEV main
```

首次实际推送返回 new branch `DEV -> DEV`，本地建立origin/DEV上游。随后独立远端核对：

| Ref | 实际SHA |
| --- | --- |
| 首次上传与本地HEAD | 40a149aa277633a26580ec7368abb8debd73f3ec |
| 远端DEV | 40a149aa277633a26580ec7368abb8debd73f3ec |
| 远端main | c4203014c4c6999c2d176b1402d596813a072f73 |

首次上传包含基线后的19个实施提交，覆盖代码、合成内容、模型开发产物、独立说明和验收证据。
入口：[GitHub DEV](https://github.com/VonEquinox/SHIEP-HuiGuan-Battery/tree/DEV)。
本回执作为第20次提交单独归档并继续上传DEV；最终分支tip以Git记录为准。

上传前最终检查1240个新/改候选文件，用户测试Key逐字节匹配为0；最大文件16,596,026bytes。
凭据留在忽略的本机.env；任务临时API环境文件已删除。原始MATR大包、final输入和runtime未上传。
测试服务与训练进程均已退出，工作区在首次推送后干净。

验证与外部限制见 [最终交付验收](V2_DELIVERY_ACCEPTANCE.md)；逐次改动见
[实施总记录](V2_IMPLEMENTATION_LOG.md)。本次上传不改变未完成的微信原生/真机视频及专业盲评状态。
