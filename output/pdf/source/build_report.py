# /// script
# requires-python = ">=3.12"
# dependencies = ["reportlab==4.4.9", "pillow==12.3.0"]
# ///
"""Build the source-bound DEV/main comparison as a vector PDF.

Run with Codex bundled Python (reportlab, Pillow, pypdf).
All charts are generated from archived repository numbers, not LLM estimates.
"""
from __future__ import annotations
import argparse, hashlib, json, math, re
from pathlib import Path
from xml.sax.saxutils import escape
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, Table, TableStyle, Spacer, Flowable, Image
from reportlab.lib.styles import ParagraphStyle

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'output/pdf'
PAGE_W,PAGE_H=595.276,841.89
M=46
CW=PAGE_W-2*M
C={'navy':'#132C40','teal':'#078C80','ink':'#243D4F','muted':'#637685','pale':'#EDF5F6','line':'#D8E3E7','paper':'#F8FAFB','amber':'#BD6D16','red':'#B34A45','blue':'#337DA8'}
MODEL_DATA=json.loads((OUT/'source/data/model_score_data.json').read_text())
def col(k):return colors.HexColor(C.get(k,k))

def init_fonts():
    candidates=[('Han','/System/Library/Fonts/STHeiti Light.ttc'),('HanBold','/System/Library/Fonts/STHeiti Medium.ttc')]
    for name,path in candidates:
        if Path(path).exists():pdfmetrics.registerFont(TTFont(name,path,subfontIndex=0))
        else:pdfmetrics.registerFont(TTFont(name,'/System/Library/Fonts/Supplemental/Arial Unicode.ttf'))
    pdfmetrics.registerFontFamily('Han',normal='Han',bold='HanBold',italic='Han',boldItalic='HanBold')


def norm(t):
    # Stable PDF punctuation; use a simple hyphen for typographic dash variants.
    return str(t).replace('\u2011','-').replace('\u2013','-').replace('\u2014','-')

def para(t,kind='body',scale=1):
    settings={'title':(23,31,'navy',0,0),'subtitle':(10,14.5,'muted',0,0),'body':(10.6,17.1,'ink',0,7),'h2':(12.1,18.5,'navy',8,6),'small':(8.6,13,'muted',0,4),'cell':(9.2,13.7,'ink',0,0),'header':(9.3,14,'#FFFFFF',0,0),'call':(10.3,16.4,'ink',0,0),'formula':(10.6,17.5,'navy',0,0)}
    fs,leading,co,before,after=settings[kind]
    style=ParagraphStyle(kind,fontName='HanBold' if kind in ('title','h2','header') else 'Han',fontSize=fs*scale,leading=leading*scale,textColor=col(co),wordWrap='CJK',spaceBefore=before*scale,spaceAfter=after*scale,alignment=TA_LEFT,allowWidows=0,allowOrphans=0)
    txt=escape(norm(t)).replace('\n','<br/>')
    txt=re.sub(r'\*\*(.+?)\*\*',r'<b>\1</b>',txt)
    if kind=='formula':
        txt=re.sub(r'_\{([^}]+)\}',r'<sub>\1</sub>',txt)
        txt=re.sub(r'\^\{([^}]+)\}',r'<super>\1</super>',txt)
    # Typeset indices instead of relying on absent Unicode modifier glyphs.
    submap=dict(zip('₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐₑₒₓₕₖₗₘₙₚₛₜᵢᵦⱼ','0123456789+-=()aeoxhklmnpstiβj'))
    supermap={'ʰ':'h','ᵏ':'k','⁰':'0','¹':'1','²':'2','³':'3','⁴':'4','⁵':'5','⁶':'6','⁷':'7','⁸':'8','⁹':'9'}
    txt=re.sub('['+''.join(submap)+']+',lambda m:'<sub>'+''.join(submap[ch] for ch in m.group())+'</sub>',txt)
    txt=re.sub('['+''.join(supermap)+']+',lambda m:'<super>'+''.join(supermap[ch] for ch in m.group())+'</super>',txt)
    return Paragraph(txt,style)

class Chart(Flowable):
    def __init__(self,kind,height=220):super().__init__();self.kind=kind;self.width=CW;self.height=height
    def draw(self):
        c=self.canv;c.saveState()
        c.setFillColor(col('paper'));c.roundRect(0,0,self.width,self.height,9,fill=1,stroke=0)
        getattr(self,'draw_'+self.kind)(c)
        c.restoreState()
    def txt(self,c,x,y,t,size=9,color='ink',bold=False):
        c.setFillColor(col(color));c.setFont('HanBold' if bold else 'Han',size);c.drawString(x,y,norm(t))
    def bars(self,c,x,y,w,h,names,values,maximum,highlight=(),errors=None):
        label_w=68;plotw=w-label_w-55
        step=h/len(names); bh=min(15,step*.53)
        for j,(name,value) in enumerate(zip(names,values)):
            yy=y+h-(j+.55)*step
            self.txt(c,x,yy-2,name,8.6,'teal' if name in highlight else 'ink',name in highlight)
            c.setFillColor(col('line'));c.roundRect(x+label_w,yy-4,plotw,bh,2,fill=1,stroke=0)
            c.setFillColor(col('teal' if name in highlight else 'blue'));c.roundRect(x+label_w,yy-4,max(.2,plotw*value/maximum),bh,2,fill=1,stroke=0)
            if errors:
                xx=x+label_w+plotw*value/maximum;ee=plotw*errors[j]/maximum
                c.setStrokeColor(col('navy'));c.setLineWidth(.8);c.line(xx-ee,yy+bh/2-4,xx+ee,yy+bh/2-4)
            self.txt(c,x+w-48,yy-2,f'{value:.3f}',8.8,'teal' if name in highlight else 'ink')
    def draw_dev(self,c):
        self.txt(c,16,self.height-25,'开发集 SOH MAE / 电芯宏平均 / 越低越好',11,'navy',True)
        self.txt(c,16,self.height-49,'XJTU',10,'navy',True);self.txt(c,270,self.height-49,'MATR',10,'navy',True)
        names=['H-M1','M1','MLP','LightGBM','LSTM'];keys=['H-M1','M1','MLP','LIGHTGBM','LSTM']
        models=MODEL_DATA['development']['models']
        for src,x,w in [('xjtu',16,230),('matr',270,220)]:
            maximum=max(models[k]['metrics'][src]['mean']+models[k]['metrics'][src]['sample_sd'] for k in keys)*1.10
            self.bars(c,x,29,w,self.height-92,names,[models[k]['metrics'][src]['mean'] for k in keys],maximum,('H-M1',),[models[k]['metrics'][src]['sample_sd'] for k in keys])
        self.txt(c,16,12,'单位：SOH 百分点；两图横轴范围不同；H-M1 新版 / 其余原标量协议参考。',7.8,'muted')
    def draw_final(self,c):
        self.txt(c,16,self.height-25,'历史 comparison final / 3 seed 均值 / 越低越好',11,'navy',True)
        self.txt(c,16,self.height-49,'XJTU（3 电芯；历史暴露）',9.7,'navy',True);self.txt(c,270,self.height-49,'MATR（6 电芯）',9.7,'navy',True)
        names=['M1','MLP','LightGBM','LSTM','M2'];keys=['M1_joint','MLP_JOINT','LIGHTGBM_JOINT','LSTM_JOINT','M2_joint']
        models=MODEL_DATA['historical_final']['models']
        for src,x,w,highlight in [('xjtu',16,230,('MLP',)),('matr',270,220,('M1',))]:
            maximum=max(models[k][src]['mae_pp_mean']+models[k][src]['mae_pp_sd'] for k in keys)*1.10
            self.bars(c,x,29,w,self.height-92,names,[models[k][src]['mae_pp_mean'] for k in keys],maximum,highlight,[models[k][src]['mae_pp_sd'] for k in keys])
        self.txt(c,16,12,'H-M1 本轮没有新 final 分数；不可把此图与开发集横向混排。',7.8,'muted')
    def draw_agent(self,c):
        self.txt(c,16,self.height-25,'冻结云 pilot sealed 程序质量 / n=12 根事件',11,'navy',True)
        names=['static v0','A2 Memory','A3 ACE','A4 GEPA']
        vals=[.7,.8555555556,.7777777778,.3111111111]
        x=102;pw=325;step=34
        for j,(name,value) in enumerate(zip(names,vals)):
            y=self.height-60-j*step
            self.txt(c,16,y,name,9.3,'ink')
            c.setFillColor(col('line'));c.roundRect(x,y-5,pw,17,3,fill=1,stroke=0)
            c.setFillColor(col('amber' if j==3 else 'teal' if j==1 else 'blue'));c.roundRect(x,y-5,pw*value,17,3,fill=1,stroke=0)
            self.txt(c,442,y,f'{value:.4f}',10,'amber' if j==3 else 'ink',True)
        c.setStrokeColor(col('muted'));c.setDash(3,3);c.line(x+pw*.925,40,x+pw*.925,self.height-44);c.setDash()
        self.txt(c,16,24,'虚线 A0 规则=0.9250；高程序分不等于根因确诊率。',8.4,'muted')
        self.txt(c,16,10,'A2 相对 static 观察 +22.22%；自进化因果提升尚未证明。',8.4,'muted')
    def draw_expansion(self,c):
        self.txt(c,16,self.height-25,'V2 可比包的对象级扩容',11,'navy',True)
        rows=[('完整比较人口',21,56,'2.667x'),('拟合 train 人口',11,28,'2.545x'),('non-final 开发人口',18,47,'2.611x')]
        for j,(label,a,b,ratio) in enumerate(rows):
            y=self.height-65-j*50
            self.txt(c,16,y+13,label,9.5,'ink');self.txt(c,436,y+13,ratio,11,'teal',True)
            c.setFillColor(col('line'));c.roundRect(125,y-2,285*a/56,11,2,fill=1,stroke=0)
            c.setFillColor(col('teal'));c.roundRect(125,y-16,285*b/56,11,2,fill=1,stroke=0)
            self.txt(c,125+285*a/56+6,y-1,str(a),8.4,'muted');self.txt(c,125+285*b/56+6,y-15,str(b),8.4,'teal')
        self.txt(c,16,12,'灰：V2 XJTU-only；绿：V2 XJTU+MATR。不同于 main 的 2,058 窗口协议。',7.8,'muted')
    def draw_transfer(self,c):
        self.txt(c,16,self.height-25,'加入 MATR：同类方法的 MATR OOD 误差下降',11,'navy',True)
        data=MODEL_DATA['historical_final']['XJTU_only_OOD_to_joint_MATR']
        rows=[(name,data[key]['baseline_mae_pp'],data[key]['candidate_mae_pp'],f"{data[key]['relative_error_reduction_pct']:.2f}%") for name,key in [('MLP','mlp'),('LightGBM','lightgbm'),('LSTM','lstm')]]
        for j,(name,a,b,ratio) in enumerate(rows):
            y=self.height-64-j*45
            self.txt(c,16,y,name,10,'ink',True)
            for k,(v,co) in enumerate([(a,'line'),(b,'teal')]):
                c.setFillColor(col(co));c.roundRect(104,y-k*15-4,280*v/24,11,2,fill=1,stroke=0)
                self.txt(c,104+280*v/24+5,y-k*15-2,f'{v:.3f}',8.4,'muted')
            self.txt(c,432,y-4,ratio,11,'teal',True)
        self.txt(c,16,12,'灰：只训 XJTU；绿：联合 source-aware。MAE 单位 pp，越低越好。',8,'muted')
    def draw_gamma(self,c):
        self.txt(c,16,self.height-25,'预算鲁棒算例：Γ 增大，最坏排放上界上升',11,'navy',True)
        px,py,pw,ph=54,46,395,self.height-97
        c.setStrokeColor(col('line'))
        for v in [100,110,120,130]:
            y=py+(v-100)/30*ph;c.line(px,y,px+pw,y);self.txt(c,16,y-3,str(v),8,'muted')
        pts=[(px+g/2*pw,py+(v-100)/30*ph) for g,v in [(0,100),(1,120),(1.5,125),(2,130)]]
        c.setStrokeColor(col('teal'));c.setLineWidth(2)
        for a,b in zip(pts,pts[1:]):c.line(*a,*b)
        for (x,y),(g,v) in zip(pts,[(0,100),(1,120),(1.5,125),(2,130)]):
            c.setFillColor(col('teal'));c.circle(x,y,4,fill=1,stroke=0);self.txt(c,x-8,py-17,str(g),9,'ink');self.txt(c,x-12,y+8,str(v),9,'teal',True)
        self.txt(c,16,10,'名义100 kg，误差系数20/10 kg；Γ 是误差预算，不是置信概率。',8.3,'muted')
    def draw_carbonbenefit(self,c):
        self.txt(c,16,self.height-25,'同服务量：延用可能减排，也可能反而增排',11,'navy',True)
        zx=290;scale=3.15
        c.setStrokeColor(col('muted'));c.line(zx,43,zx,self.height-46)
        for label,value,y,co in [('制造100kg，延用有益',275/9,self.height-70,'teal'),('制造20kg，延用增排',-445/9,self.height-121,'amber')]:
            self.txt(c,16,y+17,label,10,'ink')
            c.setFillColor(col(co));x=zx+min(0,value)*scale;c.roundRect(x,y-8,abs(value)*scale,20,3,fill=1,stroke=0)
            self.txt(c,415,y-3,f'{value:+.3f} kg',10,co,True)
        self.txt(c,16,24,'正值：候选相对基准减排；负值：候选增排。仅为数学演示。',8.4,'muted')
        self.txt(c,16,10,'两种方案必须有相同1,000 kWh输出、边界和终端处理。',8.4,'muted')
    def draw_pareto(self,c):
        self.txt(c,16,self.height-25,'有限候选的成本 / 碳排 Pareto 前沿',11,'navy',True)
        px,py,pw,ph=63,49,390,self.height-101
        c.setStrokeColor(col('line'))
        for v in [0,5,10,15,20]:
            x=px+v/25*pw;y=py+v/20*ph;c.line(x,py,x,py+ph);c.line(px,y,px+pw,y)
            self.txt(c,x-4,py-15,str(v),8,'muted');self.txt(c,36,y-3,str(v),8,'muted')
        self.txt(c,px+pw-80,py-32,'成本（示例）',8,'muted');self.txt(c,16,self.height-47,'碳排',8,'muted')
        for name,x,y,co in [('A',10,10,'teal'),('C',20,5,'teal'),('B',15,15,'amber'),('D',0,0,'muted')]:
            xx=px+x/25*pw;yy=py+y/20*ph;c.setFillColor(col(co));c.circle(xx,yy,4,fill=1,stroke=0)
            self.txt(c,xx+8,yy+3,name+(' 不可行' if name=='D' else ' 被支配' if name=='B' else ' 前沿'),9,co,True)
        c.setStrokeColor(col('teal'));c.setDash(3,3);c.line(px+10/25*pw,py+10/20*ph,px+20/25*pw,py+5/20*ph);c.setDash()
        self.txt(c,16,10,'仅计算已列举且可行的候选；连线示意权衡，不代表可任意插值的可实施方案。',7.8,'muted')

class Diagram(Flowable):
    def __init__(self,kind,height=230):super().__init__();self.kind=kind;self.width=CW;self.height=height
    def draw(self):
        c=self.canv;c.saveState();getattr(self,'draw_'+self.kind)(c);c.restoreState()
    def box(self,c,x,y,w,h,title,text,co='pale'):
        c.setFillColor(col(co));c.roundRect(x,y,w,h,7,stroke=0,fill=1)
        p=para(title,'h2',.94);_,ph=p.wrap(w-20,h);p.drawOn(c,x+10,y+h-ph-9)
        p=para(text,'small');_,ph=p.wrap(w-20,h);p.drawOn(c,x+10,y+9)
    def arrow(self,c,x1,y1,x2,y2):
        c.setStrokeColor(col('teal'));c.setLineWidth(1.4);c.line(x1,y1,x2,y2)
        ang=math.atan2(y2-y1,x2-x1);s=6
        c.line(x2,y2,x2-s*math.cos(ang-.5),y2-s*math.sin(ang-.5));c.line(x2,y2,x2-s*math.cos(ang+.5),y2-s*math.sin(ang+.5))
    def draw_architecture(self,c):
        w=150;gap=26
        self.box(c,0,145,w,75,'数值模型服务','真实来源 / SOH分布\n校准 / support边界')
        self.box(c,176,145,w,75,'单个云端 Agent','静态Skills + Memory\n工具 / 引用 / 报告')
        self.box(c,352,145,w,75,'人工运维闭环','提案批准 / CP-SAT\n现场测量 / 独立验收')
        self.arrow(c,151,180,175,180);self.arrow(c,327,180,351,180)
        self.box(c,65,38,170,76,'ACE / GEPA 进化','反馈局部更新 + dev回归\n版本CAS / 有界恢复')
        c.setStrokeColor(col('teal'));c.setLineWidth(1.4)
        c.line(427,143,427,130);c.line(427,130,150,130);self.arrow(c,150,130,150,115)
        c.line(236,76,260,76);self.arrow(c,260,76,260,143)
        self.box(c,285,38,200,76,'独立 Carbon / 经济','活动清单 / 状态场景 / 因子\n鲁棒边界 / NPV / 台账')
        p=para('Carbon 使用版本化结构数据，与 Agent 的工具权限和排程目标分别计算。','small');_,h=p.wrap(CW,20);p.drawOn(c,0,4)
    def draw_hm1(self,c):
        self.box(c,0,144,145,78,'可见30D标量输入','统计值 / 缺失标记\ntrain-only标准化')
        self.box(c,174,144,150,78,'分source合并训练','XJTU协议共享\nMATR来源独立')
        self.box(c,353,144,150,78,'q05 / q50 / q95','主干160棵树\n深度3 / 叶5')
        self.arrow(c,146,184,173,184);self.arrow(c,325,184,352,184)
        self.box(c,171,35,153,78,'来源残差量化树','80棵树 / 深度2\n残差权重1.0')
        self.box(c,353,35,150,78,'反变换与排序','exp还原SOH\n行内排序保证区间序')
        self.arrow(c,428,140,248,117);self.arrow(c,325,74,352,74)
        p=para('按电芯平衡加权；所有拟合仅使用train，结构选择只使用development。','small');_,h=p.wrap(CW,25);p.drawOn(c,0,3)
    def draw_workflow(self,c):
        items=[('1 诊断','数值+证据，形成报告'),('2 提案','授权检查/处置建议'),('3 人批准','管理员/调度员确认'),('4 排程','CP-SAT草案+人确认'),('5 现场','技术员原文与测量'),('6 验收','另一身份+反馈进化')]
        for i,(title,text) in enumerate(items):
            x=(i%3)*176;y=139 if i<3 else 35
            self.box(c,x,y,151,75,title,text)
            if i in (0,1,3,4):self.arrow(c,x+152,y+37,x+174,y+37)
        c.setStrokeColor(col('teal'));c.setLineWidth(1.4);c.line(429,137,429,123);c.line(429,123,76,123);self.arrow(c,76,123,76,111)
    def draw_gepa(self,c):
        self.box(c,0,141,155,79,'版本化反馈批次','50个根（默认）\n来源root/id/version')
        self.box(c,174,141,155,79,'LLM 受限候选','可改说明/路由/证据\n禁止工具schema/增权')
        self.box(c,348,141,155,79,'独立 dev 比较','baseline + candidate\nscore门槛 / hard gates')
        self.arrow(c,156,180,173,180);self.arrow(c,330,180,347,180)
        self.box(c,348,36,155,78,'CAS发布 / NO_UPDATE','版本匹配 / 自动回归\n不合格拒绝，费用保留')
        self.box(c,0,36,295,78,'有界恢复与取消意图','同版本每代最多3次，60/120秒退避\n取消或重启中断需显式幂等恢复')
        self.arrow(c,426,138,426,116)
    def draw_carbon(self,c):
        self.box(c,0,143,150,78,'共同功能单位','相同服务量/期间/边界\n基准与候选起始状态')
        self.box(c,176,143,150,78,'结构化清单','制造/用电/运输/维护\n单位与因子版本')
        self.box(c,352,143,150,78,'物理排放','活动×因子\n状态效率/更新过程')
        self.arrow(c,151,183,175,183);self.arrow(c,327,183,351,183)
        self.box(c,0,35,150,78,'鲁棒比较','共享误差先作差\nΓ预算/收益上下界')
        self.box(c,176,35,150,78,'经济分账','经营NPV / 合格现金\n影子价值单列')
        self.box(c,352,35,150,78,'决策与台账','Pareto/敏感性\n审阅/冲销/导出')
        self.arrow(c,429,139,429,123);self.arrow(c,429,123,76,123);self.arrow(c,76,123,76,115)
        self.arrow(c,151,73,175,73);self.arrow(c,327,73,351,73)


def blockflow(block,scale=1):
    ty=block['type']
    if ty in ('p','h2'):return [para(block['text'],'body' if ty=='p' else 'h2',scale)]
    if ty=='space':return [Spacer(1,block.get('height',8))]
    if ty=='table':
        hdr=[para(v,'header',scale) for v in block['headers']]
        rows=[[para(v,'cell',scale) for v in row] for row in block['rows']]
        fractions=block.get('widths',[1/len(hdr)]*len(hdr))
        if abs(sum(fractions)-1)>.02:fractions=[v/sum(fractions) for v in fractions]
        t=Table([hdr]+rows,colWidths=[CW*v for v in fractions],hAlign='LEFT')
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),col('navy')),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),9),('RIGHTPADDING',(0,0),(-1,-1),9),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7),('ROWBACKGROUNDS',(0,1),(-1,-1),[col('paper'),colors.white]),('LINEBELOW',(0,1),(-1,-1),.35,col('line'))]))
        return [t,Spacer(1,9)]
    if ty in ('callout','formula'):
        txt=block.get('text','');lab=block.get('label','公式与口径' if ty=='formula' else '关键说明')
        p=para(lab,'h2',scale);q=para(txt,'formula' if ty=='formula' else 'call',scale)
        t=Table([[p],[q]],colWidths=[CW]);t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),col('pale')),('LEFTPADDING',(0,0),(-1,-1),12),('RIGHTPADDING',(0,0),(-1,-1),12),('TOPPADDING',(0,0),(-1,0),3),('BOTTOMPADDING',(0,0),(-1,0),0),('TOPPADDING',(0,1),(-1,1),0),('BOTTOMPADDING',(0,1),(-1,1),11)]));return [t,Spacer(1,9)]
    if ty=='chart':return [Chart(block['kind'],block.get('height',220)),Spacer(1,11)]
    if ty=='diagram':return [Diagram(block['kind'],block.get('height',235)),Spacer(1,10)]
    if ty=='image':
        path=ROOT/block['path'];im=Image(str(path));im.drawWidth=CW;im.drawHeight=CW*im.imageHeight/im.imageWidth
        if im.drawHeight>block.get('max_height',440):im.drawHeight=block.get('max_height',440);im.drawWidth=im.drawHeight*im.imageWidth/im.imageHeight
        return [im,Spacer(1,8),para(block.get('caption',''),'small',scale)]
    raise ValueError(ty)


def height_of(story):
    height=0
    for f in story:
        w,h=f.wrap(CW,10000);height+=h+f.getSpaceBefore()+f.getSpaceAfter()
    return height


def page_chrome(c,p,n,total,sources):
    c.setFillColor(colors.white);c.rect(0,0,PAGE_W,PAGE_H,fill=1,stroke=0)
    c.setFillColor(col('teal'));c.rect(M,795,23,3,fill=1,stroke=0)
    c.setFillColor(col('muted'));c.setFont('Helvetica',8);c.drawString(M+32,793,'HUIGUAN  /  VERSION REVIEW  /  2026.10.02')
    c.setFont('Helvetica',8);c.drawRightString(PAGE_W-M,793,'main c4203014  ->  DEV 0d9a53de')
    c.setFillColor(col('teal'));c.setFont('HanBold',10);c.drawString(M,765,norm(p.get('section','')))
    title=para(p['title'],'title')
    _,hh=title.wrap(CW,100);title.drawOn(c,M,729-hh+24)
    subt=para(p.get('subtitle',''),'subtitle')
    _,sh=subt.wrap(CW,50);sy=718-hh+24-sh;subt.drawOn(c,M,sy)
    top=sy-14
    c.setStrokeColor(col('line'));c.setLineWidth(.55);c.line(M,51,PAGE_W-M,51)
    c.setFont('Han',7.2);c.setFillColor(col('muted'))
    ref='  '.join(f'[{sources[v]}]' for v in p.get('sources',[]))
    c.drawString(M,36,'慧管电池 | 技术版本与实测结果报告  '+ref)
    c.setFont('Helvetica',8);c.drawRightString(PAGE_W-M,36,f'{n:02d} / {total:02d}')
    return top


def cover(c,total):
    c.setFillColor(col('navy'));c.rect(0,0,PAGE_W,PAGE_H,fill=1,stroke=0)
    c.setStrokeColor(col('#1D4359'));c.setLineWidth(1)
    for i in range(12):
        path=c.beginPath();path.moveTo(255,-30+i*25);path.curveTo(470,200+i*18,230,425+i*12,680,710+i*12);c.drawPath(path)
    c.setFillColor(col('teal'));c.roundRect(46,740,167,29,6,fill=1,stroke=0)
    c.setFillColor(colors.white);c.setFont('Helvetica-Bold',11);c.drawString(60,750,'DEV  /  VERSION 2.0')
    c.setFillColor(colors.white);c.setFont('HanBold',39);c.drawString(46,628,'慧管电池')
    c.setFont('HanBold',27);c.drawString(46,576,'从单源预测到专业诊断闭环')
    c.setFont('Han',17);c.drawString(46,536,'main 与当前 DEV 的功能、模型及实验对比')
    c.setFillColor(col('#AFCDD6'));c.setFont('Han',11)
    for y,t in [(478,'多源概率模型  /  云端单 Agent  /  Context 自进化'),(454,'现场反馈与约束排程  /  独立碳排与经济决策'),(430,'完整公式、选择依据、分数对照与可追溯证据')]:c.drawString(46,y,t)
    cards=[('2.667x','V2 比较人口扩容'),('47.36%','H-M1 对 MLP\nXJTU 开发 MAE 降低'),('604','当前 Python\n回归全部通过')]
    for i,(value,label) in enumerate(cards):
        x=46+i*172;c.setFillColor(col('#203F52'));c.roundRect(x,258,158,115,8,fill=1,stroke=0)
        c.setFillColor(col('#5BD0BE'));c.setFont('Helvetica-Bold',27);c.drawString(x+13,333,value)
        c.setFillColor(colors.white);c.setFont('Han',10)
        for j,line in enumerate(label.split('\n')):c.drawString(x+13,305-j*16,line)
    c.setFillColor(col('#AFCDD6'));c.setFont('Han',10)
    c.drawString(46,207,'比较基准 main：c4203014  |  当前实现 DEV：0d9a53de')
    c.drawString(46,184,'报告日期：2026年10月2日  |  数据与分数截至上述版本')
    c.drawString(46,161,'程序质量、开发误差和历史 comparison final 分开呈现。')
    c.setStrokeColor(col('#426171'));c.line(46,108,549,108)
    c.setFillColor(colors.white);c.setFont('Han',9);c.drawString(46,84,'项目技术报告  ·  可用于演示、评审与后续实验规划')
    c.setFont('Helvetica',8);c.drawRightString(549,84,f'01 / {total:02d}')
    c.bookmarkPage('cover');c.addOutlineEntry('封面','cover',0)
    c.showPage()


def render(pages,out):
    init_fonts()
    source_paths=[]
    for p in pages:
        for v in p.get('sources',[]):
            if v not in source_paths:source_paths.append(v)
    sources={v:i+1 for i,v in enumerate(source_paths)}
    source_pages=[]
    for offset in range(0,len(source_paths),8):
        rows=[]
        for v in source_paths[offset:offset+8]:
            real=v.removeprefix('main:');path=ROOT/real
            purpose='main 历史文件（Git复原）' if v.startswith('main:') else '当前实现/归档证据'
            rows.append([f'[{sources[v]}]',v,purpose])
        source_pages.append({'section':'附录 / SOURCE INDEX','title':'证据索引与复现入口','subtitle':'正文页脚编号对应以下仓库文件；分数来自保存的机器回执和冻结实验。','blocks':[{'type':'table','headers':['编号','仓库相对路径','证据类型'],'rows':rows,'widths':[.09,.7,.21]},{'type':'p','text':'在线仓库：https://github.com/VonEquinox/SHIEP-HuiGuan-Battery/tree/DEV。PDF比较的是2026-10-02的固定实现快照；main基线c4203014，DEV实现0d9a53de。后续文档提交不改变正文所引用的实验代码版本。'}],'sources':[]})
    allpages=pages+source_pages;total=len(allpages)+1
    c=canvas.Canvas(str(out),pagesize=(PAGE_W,PAGE_H),pageCompression=1,invariant=1)
    c.setTitle('慧管电池：main与DEV版本差异及完整实测报告');c.setAuthor('慧管电池项目 / 协作开发团队');c.setSubject('版本功能、概率模型、Agent自进化、碳排与经济决策、验证证据')
    cover(c,total);layout=[]
    for n,p in enumerate(allpages,start=2):
        top=page_chrome(c,p,n,total,sources);available=top-65
        scale=1
        while True:
            story=[f for b in p['blocks'] for f in blockflow(b,scale)]
            required=height_of(story)
            if required<=available:break
            scale-=.025
            if scale<.925:raise ValueError(f'Page {n} overflow: {p["title"]} need={required:.1f} available={available:.1f}')
        y=top
        for f in story:
            y-=f.getSpaceBefore();w,h=f.wrap(CW,y-60);y-=h;f.drawOn(c,M,y);y-=f.getSpaceAfter()
        key=f'p{n}';c.bookmarkPage(key);c.addOutlineEntry(p['title'],key,0)
        layout.append({'page':n,'title':p['title'],'body_font_scale':round(scale,3),'used_height':round(required,2),'available_height':round(available,2),'min_body_y':round(y,2)})
        c.showPage()
    c.save()
    return {'page_count':total,'pages':layout,'source_index':sources,'file':str(out.relative_to(ROOT)),'sha256':hashlib.sha256(out.read_bytes()).hexdigest()}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--content',default=str(OUT/'source/report_content.json'));args=parser.parse_args()
    pages=json.loads(Path(args.content).read_text())
    out=OUT/'HuiGuan_DEV_vs_main_20261002.pdf';OUT.mkdir(parents=True,exist_ok=True)
    receipt=render(pages,out)
    (OUT/'source/layout_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'pdf':str(out),'pages':receipt['page_count'],'bytes':out.stat().st_size},ensure_ascii=False))
if __name__=='__main__':main()
