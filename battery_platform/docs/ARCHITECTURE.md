# 独立应用架构与数据契约

## 模块

`app/main.py` 提供同源FastAPI/静态应用与生命周期。`api_core.py` 管理身份、资产、人员账户、总览；`api_data.py` 管理数据/模型/任务/评估比较；`api_ops.py` 管理策略、事件、告警、工单、人员、附件、反馈。`services.py` 放置跨对象规则；`jobs.py` 监督本地计算子进程；`security.py` 统一认证和角色检查；`backup.py` 提供停机一致性备份。

前端位于 `frontend/src/`，采用React/TypeScript；页面分为Foundation、Intelligence、Operations三组，复用统一API错误处理、模态框、指标、表格和SVG图表。系统字体和打包后的图标不依赖外部字体/CDN。位置视图是固定坐标示意，不伪称在线GPS。

API独立依赖环境 `.venv/`；ML子进程使用原 `model_lab/.venv/bin/python`，不向原模型环境安装新包。新增桥接程序 `ml_bridge.py` 负责哈希校验、输入验证、原始冻结模型调用，以及可重载的平台ET训练版本。

## 对象关系

```text
DatasetVersion → Samples → immutable input hashes
       │             │
       │             └→ Job → Prediction ← ModelVersion
       └→ TrainingJob → ModelVersion + cell split + validation predictions

Site → Cabinet → Module → Cell slot → InstallationIdentity
                                      │
                    explicit demo binding to experimental source cell
                                      │
Prediction + VersionedPolicy → HealthEvent → Alert → WorkOrder
       │                                           │
       └← append-only Feedback                StateHistory + Attachments

User / Role → PersonnelEligibility → Assignment
Every mutation → Audit; workflow changes → private in-app Notifications
```

资产槽位与安装身份分开。更换只产生新身份；历史预测指向旧身份，不会被新模型或设备更换覆盖。推理启动前捕获绑定快照；计算期间更换资产不会把旧预测错记到新安装上。

## 持久化和并发

SQLite WAL启用外键；状态修改使用显式事务。应用采用SQLAlchemy连接管理和参数化SQL，业务标识符不拼接到SQL。事务 `BEGIN IMMEDIATE` 串行化本机业务写入；这不是水平扩展方案。

工单/资产/告警的请求带版本号，过期版本返回409。活动告警有部分唯一索引；同一告警只能建一张工单。重复模型请求使用用户级Idempotency-Key和请求指纹，改变请求内容却复用同一键会被拒绝。

任务先入库再进入计算。监督线程只做调度，实际模型运行在独立进程；任务容量12、单次推理256条、运行时限15分钟、日志4MiB、结果32MiB。取消和正常关闭会终止子进程；异常重启不静默重放。计算子进程持有共享锁，不同测试/应用运行目录不能同时抢占模型计算；父进程消失时子进程退出。

## 预测和评估

源视图71维按固定索引与单位处理，字段详见 `/api/schema`。不可用的温度特征允许缺失，必要电压窗口/电流/电量特征不允许用任意常数兜底。完整放电容量只作标签，禁止作为当前预测输入。

冻结混合规则：先平均各分支三个种子的对数SOH，再将两个分支对数结果等权平均后指数还原。快速ET是另一个明确选择的模型，不是混合模型失败后的隐式替代。

平台训练：固定随机种子2047对电芯分组划分；约四分之一电芯作为验证；三个ET种子为0/1/2；默认每种子100树、min leaf=3；可配置范围严格限制。训练期填补、标准化、目标缩放和等电芯权重，只用训练电芯。保存所有验证样本的预测、标签和来源，权重重载结果需数值一致。

评估对比只接受2–5个已完成evaluation任务；核对全部样本ID和输入快照一致，然后从保存预测重算电芯宏MAE和宏RMSE。不同集合返回409；没有标签不生成“精度”。训练重叠独立显示，不把同样本比较当作泛化证明。

## 事件与状态机

健康策略是不可变版本。持续性要求不同源样本，重跑同一样本不增加次数。事件保存SOH、模型ID、输入哈希、阈值、样本证据与策略ID。超出训练范围表示适用性复核，不等于设备故障；历史样本回放不是实时采集。

工单主路径：CREATED → ASSIGNED → ACCEPTED → IN_PROGRESS → RESOLVED → VERIFIED → CLOSED。分支允许限定状态下退回、取消、重开。派发前过滤有效维修账号、技能、值班及负载，再按负载、距离、用户ID确定排序，展示依据而非生成“AI推荐分”。

维修人员只能处理本人获派工单。提交结果至少5字，且必须由本人上传本次开始处理之后的证据；重开工单不能用旧附件直接结束。验收由另外一位调度/管理员完成；关闭不改写模型结果或资产健康。

## 安全边界

Argon2id密码哈希、8小时随机服务端会话、HttpOnly/SameSite cookie；状态修改统一检查CSRF和请求来源。固定失败窗口登录限流，账户停用/改角色/改密码撤销已有会话。最后管理员不可被移除，持有活动工单的维修人员不可直接停用或改成其他角色。

CSV最多8MiB/5000行，只接受声明的数值特征；不反序列化用户上传模型。证据最多5MiB，PNG/JPEG须通过内容验证，TXT须为UTF-8；固定存储目录、随机存储名、访问授权和下载附件响应。原始文件名不能指定路径。

所有原模型文件在反序列化前核对SHA256。应用不读取用户密钥、旧.env或旧数据库；不上传电池数据到外部服务。该版本只接受localhost回环Host，启动命令仅绑定127.0.0.1。

## 尚未代表的能力

并未接生产BMS、现场GIS、外部短信邮件、工业高可用数据库、硬件控制或认证安全诊断；未证明任意厂牌/化学体系适用。用户自行上传的电芯身份真实性也不能仅靠CSV格式验证保证。测试覆盖是软件行为证据，不是零缺陷或零过拟合保证。
