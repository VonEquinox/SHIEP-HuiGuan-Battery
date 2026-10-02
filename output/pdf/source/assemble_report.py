"""Assemble detailed evidence pages and purpose-built visual summaries."""
from pathlib import Path
import json

HERE=Path(__file__).resolve().parent
def load(name):return json.loads((HERE/'parts'/f'{name}_pages.json').read_text())
def p(text):return {'type':'p','text':text}
def h(text):return {'type':'h2','text':text}
def f(text,label='公式与口径'):return {'type':'formula','label':label,'text':text}
def note(label,text):return {'type':'callout','label':label,'text':text}
def table(headers,rows,widths):return {'type':'table','headers':headers,'rows':rows,'widths':widths}
def visual(ty,kind,height=235):return {'type':ty,'kind':kind,'height':height}
def page(section,title,subtitle,blocks,sources):return {'section':section,'title':title,'subtitle':subtitle,'blocks':blocks,'sources':sources}

feature,model,agent,carbon=[load(n) for n in ['feature','model','agent','carbon']]
# Independent source review clarified these statements without changing measurements.
for b in agent[3]['blocks']:
    if b['type']=='table':b['headers']=[v.replace('Sealed云报告','严格有效报告') for v in b['headers']]
carbon[0]['blocks'][1]['text']='E = Σᵢ σᵢ aᵢ fᵢ；B = E基准 − E候选；σᵢ=+1一般活动，−1合格回收抵扣'
carbon[0]['blocks'][2]['text']+=' 活动量非负；回收抵扣单列，必须保留allocation_method与material_flow_id，同一材料流禁止重复抵扣。'
for item in carbon[3]['blocks']:
    if item['type']=='formula':item['text']=item['text'].replace('^(tΔ)','^{tΔ}').replace('^(HΔ)','^{HΔ}')
carbon[1]['blocks'][6]['text']='R/L 是旧剩余/新寿命离散PMF，F_X(h)=Σₛ≤h X(s)，m(0)=0。PMF缺失质量须显式声明存活至计算期限，不能由右删失自动推断。更换进入年龄0的新cohort并增加制造。R=L=确定2期时，6期内更换3次；延期不能声称永久避免制造。最后1000周期未观察到EOL，只提供寿命下界。'
carbon[2]['blocks'][2]['text']='hΓ(c) = Σⱼ₌₁ᵏ |c|排序ⱼ + (Γ−k)|c|排序ₖ₊₁；k=floor(Γ)，0≤Γ≤n；k=n时下一项取0。E∈[E₀−hΓ，E₀+hΓ]'
carbon[5]['blocks'][4]['rows'][0]=['独立数学fixture：40−10','净额30kg；非当前冲销API能力']
carbon[5]['blocks'][3]['text']+=' 当前API仅全额冲销：原40、冲销−40，再以新更正情景/版本入账30。'
carbon[7]['blocks'][4]['text']=carbon[7]['blocks'][4]['text'].replace('失败和费用量记录','失败和token usage记录')

sources_model=['battery_platform/research/f01_channel_validity_20261002_qualified/development_model_comparison.json','battery_platform/research/joint_xjtu_matr/summary/joint_benchmark_summary_20261002.json']
sources_agent=['battery_platform/reports/v2_agent/cloud_pilot_v2_20261001/summary.json','docs/V2_AGENT_IMPLEMENTATION.md']
# Use the precise pilot source already checked by the evidence author.
sources_agent=agent[3]['sources']
sources_carbon=carbon[0]['sources']+carbon[5]['sources']

intro=page('阅读起点 / EXECUTIVE VIEW','这次升级改变了什么','基准是真实main实现；当前快照为DEV 0d9a53de；不是把所有已有功能重复算为新增。',[
    p('main 已有资产、数据、冻结SOH预测、告警、工单与独立验收等运维底座。DEV在其上新增多来源数值研究、可追溯诊断、单云端Agent、Skills/Memory/ACE/GEPA、约束派单、现场微信TEST工程，以及独立碳排与经济工作区。'),
    table(['维度','main / 继承能力','当前DEV / 新增或增强'],[
      ['产品工作区','7个基础区域；5类角色','新增关联、诊断、进化、Carbon，合计11区域'],
      ['电池预测','XJTU冻结TabICL + ExtraTrees','XJTU+MATR、DyAD/CH独立研究；H-M1开发首选'],
      ['诊断与进化','数值健康、规则告警与工单','10工具云执行器、16Skills、反馈Memory、受限GEPA'],
      ['碳排与经济','没有独立V2 Carbon工作区','同服务量活动核算、状态更新、Γ鲁棒、NPV、Pareto、台账'],
      ['验证','原V1的软件与模型验收','当前604 Python + 13界面合同 + 2真实浏览器通过']],[.18,.36,.46]),
    h('最值得关注的三个结果'),
    p('可比V2对象从21增至56（2.667倍）；H-M1开发集XJTU/MATR MAE为0.3841/1.5290 pp，相比MLP误差降低47.36%/71.32%。历史Agent A2 sealed程序分0.8556，高于static 0.7000；A4为0.3111，负结果完整保留。'),
    note('如何理解证据','H-M1提升是开发集模型选择结果，尚无本轮新final；Agent观察升分没有证明Self Evolve因果收益；Carbon数值是合成数学验算，不是现场减排或政策收入。各章同时给出结果和适用边界。')],
    ['main:battery_platform/README.md','docs/V2_DELIVERY_ACCEPTANCE.md','docs/V2_F01_F07_REPAIR_20261002.md']+sources_model+sources_agent)

toc=page('阅读导航 / CONTENTS','从功能、模型，到进化与碳排','每个章节包含用户视角、实现方式、关键公式与实测结果；末尾附逐页来源索引。',[],[])

architecture=page('系统图 / RESPONSIBILITIES','四类计算怎样配合','数值预测回答测量含义；Agent组织证据与检查；业务人员批准行动；Carbon计算情景后果。',[
 visual('diagram','architecture',235),
 p('页面里出现一个AI报告，不代表一个LLM承担全部任务。数值服务加载版本化模型包，确定性代码执行权限/事实/计量检查，云端语言模型提出分析与下一步检查，人工角色完成审批和独立验收。开发过程的多个协作Agent也不等于产品中同时运行多个自治Agent。'),
 table(['输入','到哪个模块','产物'],[['可见曲线/测量','数值模型与适用域检查','SOH分位数、受支持头或unsupported'],['已到达反馈','ACE局部经验更新 / GEPA受限候选','版本化Context；dev门控；CAS发布'],['活动清单/因子/情景','独立Carbon引擎','排放边界、经济分账、前沿及台账']],[.25,.38,.37]),
 note('身份与时间贯穿所有环节','报告引用绑定来源、安装与可见时间；数值包绑定特征schema、来源域与校准状态；行动继续受到角色、材料、工具、时窗和验收约束。')],
 ['docs/V2_AGENT_IMPLEMENTATION.md','battery_platform/docs/V2_BACKEND_IMPLEMENTATION.md','battery_platform/docs/V2_CARBON_IMPLEMENTATION.md'])

workflow=page('用户闭环 / FIELD WORKFLOW','从诊断到现场，再回到经验','新增能力连接已有工单和独立验收，而不是停留在一个聊天框。',[
 visual('diagram','workflow',230),
 p('研究员/观察员可以查看适用数值、证据和诊断报告；调度员审查提案、人员资格与排程草案；技术员在获授权的工单上执行检查、扫码关联安装、提交原文与测量；另一身份完成验收。执行身份、反馈作者、来源版本和审批记录都保留。'),
 p('补测到达后，Agent从再评估继续，更新候选解释、未知项和检查排序。结果可成为Memory来源，但不能把未测到当成阴性、把干预后没有故障当成误报，也不能将技术员自由文字自动升级为确诊。'),
 note('人看到和决定什么','用户看到具体数值/缺失项、证据编号、支持与反证、下一项检查的理由及未批准提案。批准工单、确认CP-SAT草案和独立验收属于明确业务动作；LLM报告本身不具备派单权限。')],
 ['docs/V2_AGENT_IMPLEMENTATION.md','battery_platform/docs/V2_DISPATCH_IMPLEMENTATION.md','battery_platform/docs/V2_MINIPROGRAM_IMPLEMENTATION.md'])

expansion=page('数据图 / SCALE','不是只下载更多文件，而是形成可训练对象','下面比较同一V2 30D前缀协议的人口；原始循环、曲线窗口和物理电芯分别统计。',[
 visual('chart','expansion',240),
 f('扩容倍数 = N联合 / N原来源；新增比例 = (N联合−N原来源)/N原来源 ×100%'),
 p('完整比较人口21→56个电芯、168→448个前缀行，增166.67%；实际拟合train 11→28个电芯、88→224行，增154.55%；non-final开发人口18→47个电芯、144→376行，增161.11%。同一电芯的多个前缀没有被当作独立电芯。'),
 p('覆盖来源从XJTU NCM扩展到XJTU NCM与MATR LFP。来源/化学体系增多是可以核对的覆盖事实；尚未定义几何分布体积，因此不把2.667倍人口包装成“分布覆盖能力2.667倍”。main的2058条曲线窗口与这里448条前缀不是同一单位。')],sources_model)

hm1=page('模型图 / H-M1','为什么最终研究首选是 H-M1','协议内共享规律，来源间保留边界；残差补偿之后输出有序分位数。',[
 visual('diagram','hm1',235),
 f('z = [log(SOH) − μ_{source,train}]/σ_{source,train}；z预测_{τ} = g_{source,τ}(x) + λr_{source,τ}(x)；SOH预测_{τ} = exp(μ_{source,train} + σ_{source,train}·z预测_{τ})，τ∈{0.05,0.50,0.95}'),
 p('每个来源单独拟合量化GBDT主干与来源残差，来源内部合并协议数据。主干160棵、深度3、最小叶5；残差80棵、深度2；两级学习率0.03、λ=1。训练中位数填补、均值/缩放和来源目标中心均只由train计算，按电芯平衡权重。反变换后逐行排序，排序结果的中间值为点预测。'),
 p('选择规则要求XJTU优于联合MLP，MATR优于原M1，同时保留分布输出及来源门控；没有只选XJTU最低分。ExtraTrees候选虽有低XJTU误差，却未同时满足MATR/量化契约。H-M1是已安全JSON重放的研究原型，还没有替代完整多任务生产包。')],['battery_platform/docs/HM1_OPTIMIZATION_RESULTS_20261002.md']+sources_model)

devchart=page('性能图 / DEVELOPMENT','两个来源的误差都下降了','电芯宏平均SOH MAE，单位百分点(pp)；三种子0/1/2，误差线为种子样本标准差。',[
 visual('chart','dev',275),
 f('相对误差降低 = (MAE基线−MAE候选)/MAE基线 ×100%；分母始终是所标基线'),
 p('H-M1相比MLP：XJTU降低47.36%、MATR降低71.32%；相比M1：XJTU降低36.98%、MATR降低10.18%；相比LightGBM：69.68%/62.39%；相比LSTM：91.45%/87.32%。正值表示误差更低，不是把准确率与MAE相加。'),
 note('比较的具体边界','本图使用相同开发人口和原始30D特征。H-M1/M1为新schema独立重训；MLP/LightGBM/LSTM是原标量协议参考，标量输入与标签逐位不变，但没有冒称为新六通道artifact。开发集只有XJTU3、MATR6个电芯，多次选择后不等价盲测。')],sources_model+['battery_platform/research/joint_xjtu_matr/baselines/development/v2_30d_domain_20261002.json'])

finalchart=page('性能图 / HISTORICAL FINAL','保留历史 final 的真实胜负','同一历史比较协议里，M1在MATR领先；MLP在XJTU更好。此页不是H-M1的新final。',[
 visual('chart','final',270),
 p('MATR：M1 2.4528 pp，MLP 4.5717，LightGBM 3.8754，LSTM 10.3116，M2 9.3918。M1相对MLP降低46.35%、LightGBM降低36.71%、LSTM降低76.21%。'),
 p('XJTU：M1 1.1768 pp，而MLP 0.6338 pp；M1未同时获胜。M1仍比LightGBM 1.5716 pp低25.12%，这一比较方向在旧文档中曾写反，PDF汇编已按机器回执纠正。'),
 note('一次性结果与历史暴露','MATR final为6个对象；XJTU comparison final为3个已在V1开发中暴露的对象。XJTU *-5保护集仍封存。本轮H-M1没有读取新final标签，也没有把开发分数换名写为final。')],sources_model)

transfer=page('性能图 / TRANSFER','MATR 数据带来的增益有直接对照','使用相同方法：只训练XJTU后跨域推断，与XJTU+MATR联合训练后比较。',[
 visual('chart','transfer',235),
 p('MLP的MATR误差从23.6047降至4.5717 pp（降低80.63%，误差缩小5.16倍）；LightGBM从9.8597降至3.8754（降低60.69%，2.54倍）；LSTM从10.7994降至10.3116（降低4.52%，1.05倍）。不同方法能从新增来源中获得的收益明显不同。'),
 p('XJTU-only M1没有合法MATR domain head，返回unsupported，无法给一个真实跨域loss。原M1加入MATR后保留独立XJTU分支，因此XJTU误差不变；这证明分支保护，不是跨来源共享权重带来的提升。M2共享编码器保留了SOH负迁移结果，不能因为结构更复杂就优先上线。'),
 note('数据扩容与模型收益分开证明','扩容倍率是对象计数；上图是同方法在同MATR比较集的实际误差下降。H-M1选择依赖另一个开发协议，不能从本图推导它的新盲测提升。')],sources_model)

multi=page('补充研究 / MULTI-SOURCE','DyAD 多任务实验：异常任务受益，SOH负迁移保留','这组固定损失实验独立于联合H-M1选择；15个训练模型，三种子完整归档。',[
 table(['方法','MATR dev / final MAE pp','DyAD dev / final AUCPR'],[
 ['M1 per-domain','1.702±0.008 / 2.453±0.007','0.750±0 / 0.333±0'],
 ['M2 joint','10.175±0.563 / 9.920±0.780','0.861±0.127 / 0.833±0.289'],
 ['无domain adapter','10.239±0.278 / 10.169±0.326','0.750±0 / 0.667±0.289'],
 ['无history','11.756±1.757 / 11.407±1.736','0.861±0.127 / 0.833±0.289'],
 ['仅SOH任务','11.552±1.148 / 11.240±1.186','unsupported / unsupported']],[.23,.4,.37]),
 p('DyAD标签为车辆异常二分类，不是电芯根因。final仅15个独立车辆，14正常、1异常；120个landmark另列，不能当作120辆车。独立校准10车辆中只有1异常，Platt保持insufficient_calibration_class_objects，未伪造校准系数。'),
 h('高覆盖率也可能来自极宽区间'),
 p('MATR六个独立校准对象允许80% object-max CQR。M1 final landmark/整轨迹覆盖为95.83%/66.67%，宽13.419±0.728 pp；M2为100%/100%，但宽105.861±25.972 pp。区间更宽不是模型更好，覆盖与宽度必须同时展示。'),
 note('为什么不直接采用M2','M2在DyAD上观察到较高AUCPR，但SOH明显落后，而且异常正样本极少。这种跨任务权衡不能支持“所有来源全面提升”；当前没有用这组final反复调参。')],['model_lab/docs/V2_IMPLEMENTATION.md','model_lab/reports/v2/multisource_fixed_loss_20261002/final_summary.json'])

ch=page('补充研究 / GENERATED FAULT','CH 四类故障：探索性参考，不冒充真实车辆泛化','normal / high_resistance / low_capacity / self_discharge；作者公开生成数据，与LLM合成分开。',[
 table(['范围','dev可评分类宏AUPRC','探索性final可评分类宏AUPRC'],[['LFP','0.455±0.014','0.964±0.041'],['NCM','0.746±0.010','0.852±0.028'],['合并VIN','0.702±0','0.938±0.060']],[.2,.4,.4]),
 p('保守按48个VIN根分组；两化学体系96条记录不是96个独立电池。train/dev/calibration/final为29/7/5/7根，58/14/10/14记录。三种子GBDT完成，train-only预处理、每化学体系温度缩放、安全JSON导出与逐条预测重放最大绝对差0。'),
 p('dev没有high_resistance，final没有normal，完整四分类宏AUPRC均为null。表中仅统计当时可评分、有正负样本的类；不能把0.702→0.938说成同一指标提升33.69%。作者没有母本身份，分组独立性仍有限，五个校准根也不足以证明校准可靠。'),
 f('按类计算AP后，对可评类别求宏平均；完整四类有不可评类时full_macro_AUPRC=null'),
 note('为什么仍保留这个实验','它验证公开生成来源的导入、标签遮罩、有限数据训练和安全重载，并提供故障分类工具参考。它不参与H-M1 SOH门控，不支撑真实电芯根因准确率或公开SOTA。')],['model_lab/docs/V2_IMPLEMENTATION.md','model_lab/reports/v2/ch_generated_20261002/inference_validation.json'])

agentchart=page('AGENT图 / SEALED PILOT','A2 的观察收益清楚，A4 的退化也清楚','同一冻结pilot的程序质量评分；严格无效报告以0计入原始分母。',[
 visual('chart','agent',238),
 f('Q = 0.4状态 + 0.3引用完整 + 0.2首项检查/适当拒判 + 0.1/(1+检查数)；严格契约无效则Q=0'),
 p('static 0.7000，A2 0.8556（+22.22%），A3 0.7778（+11.11%），A4 0.3111（−55.56%）。A0规则0.9250且全部保守拒判，说明高程序分不等于确诊率。该0.7是DEV pilot内部静态Agent基线，main没有这个云Agent，不能写成main被提升至0.85。'),
 note('Self Evolve 是否已证明有效','尚未形成因果证明：样本12根，安装作用域限制导致A2未取到可比的跨根经验，四次GEPA激活选择分均持平，A4 sealed明显变差。F02-F07修复后无新云端评分，不能把604软件测试包装成0.9诊断效果。')],sources_agent)

gepa=page('进化图 / UPDATE GATES','自进化更新的全过程与失败边界','ACE处理局部反馈；GEPA提出受限文本候选；独立dev比较与CAS保护发布。',[
 visual('diagram','gepa',235),
 p('默认50个不同反馈根触发，最多200 rollout；历史pilot每批2根、单候选，baseline/candidate各2根dev。候选仅改允许文本字段，不能改工具schema、数值模型、预算或授权范围。'),
 p('当前修复按root/feedback/version记录预留与消费。临时provider失败和CAS冲突可有界恢复，同代最多3次、60/120秒退避；无Key等待配置变化。主动取消、重启中断需要显式幂等retry，原费用与预算保留，不能静默自动重试消耗额度。'),
 note('效果门与产品门','已发布Context还要与上一版在固定dev根回归；有分数下界、硬门和来源版本检查。样本不足标no_check，不当作通过。实现保证可以检验和拒绝更新，提升效果仍需要另行实验。')],['docs/V2_AGENT_IMPLEMENTATION.md','battery_platform/docs/GEPA_RECOVERY.md','docs/V2_F01_F07_REPAIR_20261002.md'])

carbonmap=page('CARBON图 / DECISION CHAIN','碳模块不是一个黑箱预测模型','它把可追溯活动、物理情景、误差集合和财务资格连接成明确计算链。',[
 visual('diagram','carbon',235),
 p('建立这一模块的原因，是延长使用寿命的收益不能只看减少制造。旧电池效率低、维护频繁或服务不足，都可能抵消制造收益；购买新电池也不必然在每个计算期限内更好。系统要求共同功能单位，并展示各活动对总量和比较减排的贡献。'),
 table(['用户看到','来自哪里'],[['名义排放 / 上下界 / 活动贡献','活动清单×因子；同源误差预算'],['继续使用、维修、更换候选的可行性','状态效率、剩余寿命、显式制造及服务量约束'],['成本/碳排前沿与切换条件','有限候选Pareto、ε约束、单参数敏感性'],['可审计台账与正式导出','claim类型、来源冻结、审核及全额冲销']],[.4,.6]),
 note('与电池模型的接线边界','当前SOH尚未形成经过验证的寿命/效率状态适配器；validated_model路径不接受虚构输入。可以用明确测量或用户声明的情景核算，不能说H-M1已经自动预测实际减排。')],sources_carbon)

gammachart=page('CARBON图 / ROBUSTNESS','看见不确定性，也看见决策权衡','两图均为合成数学演示；参数Γ不是概率，Pareto不是自动采购许可。',[
 visual('chart','gamma',218),visual('chart','pareto',218),
 p('Γ扫描展示偏差集合扩大后的上界；预算支持函数对固定仿射活动精确。Pareto先剔除不可行D，再保留A/C；B成本与碳排均不优于A，因此被支配。前沿只覆盖输入候选，不宣称已经搜索全部现实方案。')],carbon[2]['sources']+carbon[4]['sources'])

benefit=page('CARBON图 / POSITIVE AND NEGATIVE','延用是否减排，答案由边界与效率决定','同为1000 kWh交付、0.5 kg/kWh电网因子；新/旧效率为0.9/0.8。',[
 visual('chart','carbonbenefit',210),
 f('基准 E新 = M制造 + D/η新 × fgrid；候选 E延用 = D/η旧 × fgrid；B=E新−E延用'),
 table(['新电池制造排放','B减排','相对基准变化'],[['100 kg','+30.556 kg','降低4.66%'],['20 kg','−49.444 kg','增加8.59%']],[.37,.3,.33]),
 p('制造排放高时，在这个期限内延用有收益；制造排放较低时，旧电池额外用电导致净增排。系统保留负数，不用“绿色”标签替代数学结果。另一个鲁棒案例名义收益5 kg、Γ=1偏差20 kg，范围[−15,25]，也不能确认始终更好。'),
 note('这类图能证明什么','能验证具体算例的核算和正负方向，不能证明真实项目节省了这些排放。真实结论还需要实际活动、有效因子、共同服务边界、审核和对应资格。')],carbon[5]['sources']+carbon[2]['sources'])

f01=page('修复专题 / F01','缺温与真实 0°C，现在是不同输入','缺失标记、通道有效性、特征schema、模型权重和新旧指标一起管理。',[
 table(['情况','当前处理'],[['完全缺温 / 全NaN','填充值伴随无效通道；温度统计缺失'],['短温度数组 / 局部NaN','保留合格部分；不跨缺失间隙伪插值；标记部分覆盖'],['每点真实0°C','温度值0且通道有效，能与缺失区分'],['旧schema + 新权重或反向','显式拒绝，避免沿用旧指标']],[.33,.67]),
 p('准入后统计六类来源表：4744条V/I/time合格分段、5965256个基础有效点未触发旧缺温置零。MATR摘要与DyAD缺少合格曲线另列不适用；CH有限数组不证明真实传感器来源。这个统计不等于所有下载数据无缺温，更不证明温度就是此前负迁移原因。'),
 p('重建376行开发包，train/dev/calibration=224/72/80。物理人口、30D原始标量与标签逐位一致，M1/H-M1/M2各三种子共9次独立重训，旧artifact SHA不变。M1/H-M1开发分相同；M2 XJTU 2.6719→4.8088变差，MATR 9.7474→8.5294改善，未选用。'),
 note('新旧证据保持可追溯','新H-M1绑定schema/data/bundle/code SHA，JSON重放误差0。旧final、保护集和云pilot均未重评分；MLP输入与预处理未变，但明确保留为原标量参考。')],['battery_platform/docs/F01_CHANNEL_VALIDITY_RETRAIN_20261002.md','docs/V2_F01_F07_REPAIR_20261002.md']+sources_model)

fixes=page('修复专题 / F02–F07','反馈、Memory、GEPA 与指标已修复','这些是当前软件行为的修复验收，不能自动折算成新的LLM质量分数。',[
 table(['发现','修复后的行为','关键验收'],[
 ['F02 小数断句','数值友好切句，保留原文span','小数/负数/科学记数/范围/日期/单位'],
 ['F03 六句截断','完整事实引用；语义优先摘要；溢出按需检索','末尾测量/结论、晚反证、文字测量冲突'],
 ['F04 来源永久消费','版本化预留与消费；有界失败恢复；主动取消保护','临时失败、无Key、CAS、改版、重启'],
 ['F05 no_memory泄漏','执行层禁用初始/历史/工具Memory及外部回调','禁用组全部memory_ids为空；对照可检索'],
 ['F06 指标错名/曲线混合','严格共用Metrics；计数、比率和分母分开','真实API→worker→列表→浏览器'],
 ['F07 零相关检索','区分事件历史与相似经验；中文相关性与空结果','无关/通用/空查询为空，正反例仅在相关候选']],[.23,.44,.33]),
 p('ExperimentMetrics真实字段包括grounded_assertion_ratio、diagnosis_accuracy、false_alarms、misses。没有独立正负标签分母时不生成率；未测量字段显示unsupported。普通ReplayEvaluator没有可假定的顶层score。曲线按协议、split、方法、案例集、口径及真实云/规则执行方式分组。'),
 note('回归与旧指标','604 Python通过、13界面合同和2真实浏览器通过。旧云端报告、失败成本和实验分数保留；修复后没有新增云请求或重新给sealed改分。')],['docs/V2_F01_F07_REPAIR_20261002.md','battery_platform/app/agent/experiment_metrics.py'])

ui=page('真实界面 / ACCEPTANCE','数值与拒绝边界，在界面上都看得见','本截图来自已归档真实Chrome/API验收；这是单样例界面，不是总体性能图。',[
 {'type':'image','path':'output/pdf/source/figures/numeric-profile-crop.png','max_height':265,'caption':'真实数值页局部：SOH 95.32%；无界校准与不支持头原样展示。'},
 p('用户可绑定模型包与输入周期，看到SOH、寿命、效率和风险各头的支持状态及来源。此样例SOH约95.32%，校准区间无界，其他头明确unsupported；不能将它改成所有模型头均可用的演示。诊断页另归档rule_baseline报告，缺云Key时不假称云端结果。'),
 table(['验证层','当前证据'],[['Python','604 passed / 82.61s'],['Web','TypeScript typecheck与Vite build通过'],['浏览器','13/13受控响应界面合同；2/2真实服务浏览器 / 14.250s'],['微信TEST','历史11项行为验证；原生AppID/设备外部验收待完成']],[.25,.75]),
 note('不同验证回答不同问题','软件测试证明合同与业务边界，数值重放证明模型加载一致性，云pilot证明实际接口可运行；专业盲评、真实故障泛化、现场使用和真实减排仍须独立证据。')],['docs/V2_F01_F07_REPAIR_20261002.md','docs/evidence/v2/actual-numeric-profile.png','docs/evidence/v2/actual-diagnostic-report.png'])

repro=page('交付与复现 / REPRODUCTION','一次性安装，逐层复现，保留失败与版本','依赖、命令、材料和阶段日志均在仓库中；原始大数据与密钥保持本机管理。',[
 table(['阶段/提交','可复核的工作'],[['5aaee397 / 69b7a548','UV锁定与原子迁移；2400情景与16Skills'],['ad837321 / 1bcadd66','Carbon鲁棒核算；约束派单'],['0addea66 / 7ac492c8','单Agent与Context进化；真实API/现场闭环'],['ce4f87fc / 6f9a9274','多源实际模型；冻结云Agent比较与tokens'],['956e5b59 / cc8eb1ab','MATR物理续接/删失寿命；自动回归/分组/包输入'],['4a4913bc / d9cf67a3','XJTU+MATR基线；H-M1开发优化'],['fa3273b9 / 0d9a53de','F01有效性与独立重训；F02–F07及统一验收']],[.34,.66]),
 p('根pyproject.toml与uv.lock保留冻结环境，scripts/v2提供install/bootstrap/demo/serve/test入口。实验配置、来源manifest、数据hash、逐seed JSON、导出模型和独立文档分别归档；PDF source目录保留全部章节JSON、图表数据、构建脚本、排版和QA回执。'),
 p('复现先检查数据许可/路径与冻结依赖，再按对应独立协议构造train/dev/calibration并运行。历史final是保存结果，不由PDF构建触发重评分。PDF生成不调用云API，图表从已保存回执取数；此报告不含测试Key，也不推测账单金额。'),
 note('版本比较与后续条件','报告固定比较main c4203014与DEV实现0d9a53de。当前文档提交只汇编、纠错并归档PDF；待完成的H-M1生产多任务接入、新独立盲测、Self Evolve因果实验、微信原生验证和真实Carbon核验均明确保留。')],['README.md','docs/V2_IMPLEMENTATION_LOG.md','docs/V2_DELIVERY_ACCEPTANCE.md','pyproject.toml','uv.lock'])

# Reading order: overview -> functions -> models -> Skills -> Agent -> Carbon -> repairs/QA.
pages=[intro,toc,architecture]+feature[:5]+[workflow]+feature[5:]+[expansion,model[0],hm1,model[1],model[2],devchart,model[3],finalchart,model[4],transfer,model[5],model[6],multi,ch,model[7]]+carbon[6:]+[agent[0],agent[1],gepa,agent[2],agentchart,agent[3],agent[4],carbonmap]+carbon[:3]+[gammachart]+carbon[3:5]+[benefit,carbon[5],f01,fixes,ui,repro]

chapter_targets=[('功能与操作闭环',feature[0]['title']),('电池数据、公式与模型选择',expansion['title']),('Skills与合成数据',carbon[6]['title']),('Agent与Self Evolve实验',agent[0]['title']),('Carbon与经济决策',carbonmap['title']),('修复、真实界面与复现',f01['title'])]
toc['blocks']=[table(['章节','正文页码','内容重点'],[[name,str(next(i+2 for i,item in enumerate(pages) if item['title']==title)),desc] for (name,title),desc in zip(chapter_targets,['继承/新增对照、系统、数据、诊断、群组、派单、Web/微信、工程','物理对象、split、结构/超参、损失、MAE/区间、开发/final、负迁移','16目录、示例、母模板隔离、云请求与token、重建','执行器、ACE/Memory、GEPA门控、A0-A4全阶段结果与证明边界','活动、效率/更新、Γ、NPV、Pareto、敏感性、台账与算例','F01-F07、604回归、浏览器实样、提交与运行入口'])],[.32,.12,.56]),p('建议先阅读结果总览与性能图，再进入对应公式页。每页页脚提供来源编号，附录映射到仓库具体文件；历史main文件通过Git固定提交复原。软件通过、开发选择、冻结pilot观察、合成数学fixture与现场验证均使用各自标签。'),note('分数阅读规则','MAE越低越好，AUCPR/覆盖和Agent程序分通常越高越好，但区间还必须看宽度。提升比例写清基线分母；不同split/任务/类别/特征版本不画一条增长曲线。')]

for item in pages:item['sources']=list(dict.fromkeys(item.get('sources',[])))

(HERE/'report_content.json').write_text(json.dumps(pages,ensure_ascii=False,indent=2)+'\n')
print(f'Assembled {len(pages)} body pages + cover + source index.')
