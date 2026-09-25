import{i as le}from"./index-42bccb0d.js";import{i as ve,j as _e,k as de}from"./index-c69aab96.js";import{f as k,h as Me,g as pe,i as we,j as Ae,r as A,o as C,c as R,b as t,w as l,E as P,a as d,d as h,t as f,F as Y,k as q,O as Ee,U as Se}from"./index-ab872604.js";import{_ as ke}from"./_plugin-vue_export-helper-c27b6911.js";import"./request-0a75b6f9.js";const Ce={name:"ResultsAnalysis",setup(){const ae=()=>{const o=Se();return(o==null?void 0:o.id)||null},e=k(["baseline","bilstm","deepphm"]),G=k(["rmspe","mse","r2"]),r=k("algorithm"),oe=k(!1),re=k([]),S=k([]),$=k([]),N=k([]),z=()=>{if($.value.length===0){N.value=[],E.value=[];return}const o=$.value.filter(p=>{const i=p.algorithm.toLowerCase();return e.value.some(n=>{const s=n.toLowerCase();return i.includes(s)||s.includes(i)})});N.value=o,E.value=o,ee(o),te(o),K(),console.log(`筛选后显示 ${o.length} 个模型`)};Me([e,G,r],()=>{console.log("筛选条件变化:",{algorithms:e.value,metrics:G.value,type:r.value}),z()},{deep:!0});const j=k(null),Q=async()=>{try{console.log("开始获取性能统计数据...");const o=await ve();if(console.log("API 响应:",o),o.data&&o.data.success&&o.data.data){const p=o.data.data;console.log(`成功获取 ${p.length} 个模型的数据`),$.value=p,z(),P.success(`成功加载 ${p.length} 个模型的分析数据`)}else console.warn("API 返回数据为空，使用模拟数据"),P.warning("暂无训练数据，显示示例数据"),$.value=[],N.value=[],ee(),te(),K();try{const p=await _e({bins:20,max_error:.05});p.data&&p.data.success&&p.data.data&&(j.value=p.data.data,K())}catch(p){console.warn("获取误差分布失败，使用示例数据:",(p==null?void 0:p.message)||p)}}catch(o){console.error("获取结果数据失败:",o),P.error("获取数据失败，显示示例数据"),$.value=[],N.value=[],ee(),te(),K()}},T=k(null),H=k(null),D=k(null),W=k(null);let B=null,v=null,I=null,O=null;const E=k([{algorithm:"baseline",rmspe:.0324,mse:8e-4,r2:.9456,mae:.0187,mape:.0123,smape:.0115,trainingTime:125.67,parameters:2.4,memoryUsage:512,convergenceEpoch:87,bestValLoss:.0012},{algorithm:"bilstm",rmspe:.0218,mse:5e-4,r2:.9723,mae:.0152,mape:.0087,smape:.0082,trainingTime:287.43,parameters:4.2,memoryUsage:1024,convergenceEpoch:156,bestValLoss:8e-4},{algorithm:"deepphm",rmspe:.0156,mse:3e-4,r2:.9876,mae:.0123,mape:.0065,smape:.0061,trainingTime:456.78,parameters:6.8,memoryUsage:2048,convergenceEpoch:234,bestValLoss:5e-4}]),X=k(!1),b=pe({}),J=k(!1),Z=pe({title:"电池寿命预测算法性能分析报告",type:"detailed",content:["charts","tables","statistics","conclusion"]}),ie=o=>{switch(o){case"baseline":return"info";case"bilstm":return"success";case"deepphm":return"warning";default:return"info"}},a=o=>({baseline:"Baseline",bilstm:"BiLSTM",deepphm:"DeepHPM"})[o]||o,_=o=>{Object.assign(b,o),X.value=!0,setTimeout(()=>{W.value&&!O&&(O=le(W.value)),xe()},100)},me=o=>{re.value=o.map(p=>p.id),S.value=o},ce=async()=>{if(S.value.length<2){P.warning("请至少选择2个模型进行对比");return}try{const o=ae();if(o){const p={comparison_name:`模型对比_${S.value.map(i=>a(i.algorithm)).join("_vs_")}_${new Date().toISOString().slice(0,10)}`,compared_models:JSON.stringify(S.value.map(i=>i.id).filter(i=>i)),comparison_metrics:JSON.stringify(["rmspe","mse","r2","mae"]),comparison_results:JSON.stringify(S.value.map(i=>({id:i.id,algorithm:i.algorithm,algorithmName:i.algorithmName,rmspe:i.rmspe,mse:i.mse,r2:i.r2,mae:i.mae,trainingTime:i.trainingTime,parameters:i.parameters}))),statistical_tests:null,visualization_data:JSON.stringify({comparison_type:"manual_selection",selected_count:S.value.length}),created_by:o,is_active:!0};await de(p),console.log("模型对比记录已保存到数据库"),P.success("模型对比记录已保存")}else console.warn("无法获取当前用户ID，跳过保存模型比较记录")}catch(o){console.error("保存模型比较记录失败:",o)}oe.value=!0},ue=o=>{o()},ge=()=>{J.value=!0},he=async()=>{var o,p;try{const i=Z;if(!E.value||E.value.length===0){P.warning("暂无数据，无法生成报告");return}console.log("生成报告，数据条数:",E.value.length);try{const c=ae();if(c){const w={};E.value.forEach(g=>{const V=g.algorithm;(!w[V]||g.id&&g.id>w[V].id)&&(w[V]=g)});const L=Object.values(w),U={comparison_name:i.title||`模型性能分析报告_${new Date().toISOString().slice(0,10)}`,compared_models:JSON.stringify(L.map(g=>g.id).filter(g=>g)),comparison_metrics:JSON.stringify(["rmspe","mse","r2","mae","mape"]),comparison_results:JSON.stringify(L.map(g=>({id:g.id,algorithm:g.algorithm,rmspe:g.rmspe,mse:g.mse,r2:g.r2,mae:g.mae,mape:g.mape}))),statistical_tests:null,visualization_data:JSON.stringify({performance_chart:G.value,comparison_type:r.value}),created_by:c,is_active:!0};await de(U),console.log("模型比较记录已保存到数据库")}else console.warn("无法获取当前用户ID，跳过保存模型比较记录")}catch(c){console.error("保存模型比较记录失败:",c)}console.log("选中内容:",i.content),console.log("报告类型:",i.type),console.log("detailedResults 数据:",E.value.map(c=>({algorithm:c.algorithm,id:c.id})));let n=E.value,s="";const u={};E.value.forEach(c=>{const w=c.algorithm;(!u[w]||c.id>u[w].id)&&(u[w]=c)});const m=Object.values(u);console.log("去重后算法数量:",m.length,m.map(c=>c.algorithm)),i.type==="summary"?(n=m,s=`本报告提供 ${m.length} 种算法的核心性能指标摘要`):i.type==="detailed"?(n=m,s=`本报告包含 ${m.length} 种算法的详细性能分析和对比`):i.type==="comparison"&&(n=m.slice(0,3),s=`本报告对比了 ${n.length} 种代表性算法的性能差异`);let y=`
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${i.title}</title>
  <style>
    * {
      margin: 0;
      padding: 0;
      box-sizing: border-box;
    }
    body {
      font-family: 'Microsoft YaHei', 'Segoe UI', Arial, sans-serif;
      max-width: 1400px;
      margin: 0 auto;
      padding: 30px;
      background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
      min-height: 100vh;
    }
    .report-header {
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      color: white;
      padding: 50px;
      border-radius: 20px;
      margin-bottom: 40px;
      text-align: center;
      box-shadow: 0 10px 40px rgba(102, 126, 234, 0.4);
      position: relative;
      overflow: hidden;
    }
    .report-header::before {
      content: '';
      position: absolute;
      top: -50%;
      right: -50%;
      width: 200%;
      height: 200%;
      background: radial-gradient(circle, rgba(255,255,255,0.1) 0%, transparent 70%);
      animation: pulse 15s infinite;
    }
    @keyframes pulse {
      0%, 100% { transform: scale(1); }
      50% { transform: scale(1.1); }
    }
    .report-header h1 {
      margin: 0 0 15px 0;
      font-size: 36px;
      font-weight: 700;
      text-shadow: 2px 2px 4px rgba(0,0,0,0.2);
      position: relative;
      z-index: 1;
    }
    .report-header p {
      margin: 8px 0;
      opacity: 0.95;
      font-size: 16px;
      position: relative;
      z-index: 1;
    }
    .section {
      background: white;
      padding: 35px;
      margin-bottom: 25px;
      border-radius: 15px;
      box-shadow: 0 4px 15px rgba(0,0,0,0.08);
      transition: transform 0.3s ease, box-shadow 0.3s ease;
    }
    .section:hover {
      transform: translateY(-5px);
      box-shadow: 0 8px 25px rgba(0,0,0,0.12);
    }
    .section h2 {
      color: #2c3e50;
      border-bottom: 3px solid transparent;
      border-image: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
      border-image-slice: 1;
      padding-bottom: 15px;
      margin-bottom: 25px;
      font-size: 24px;
      display: flex;
      align-items: center;
      gap: 10px;
    }
    table {
      width: 100%;
      border-collapse: separate;
      border-spacing: 0;
      margin: 25px 0;
      border-radius: 10px;
      overflow: hidden;
      box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    }
    th, td {
      padding: 16px;
      text-align: left;
      border-bottom: 1px solid #e8e8e8;
    }
    th {
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      color: white;
      font-weight: 600;
      text-transform: uppercase;
      font-size: 14px;
      letter-spacing: 0.5px;
    }
    td {
      font-size: 15px;
      color: #555;
    }
    tr:nth-child(even) {
      background: #f8f9fa;
    }
    tr:hover {
      background: #e3f2fd;
      transition: background 0.3s ease;
    }
    tr:last-child td {
      border-bottom: none;
    }
    .summary-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 25px;
      margin: 25px 0;
    }
    .summary-card {
      background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
      padding: 25px;
      border-radius: 12px;
      border-left: 5px solid #667eea;
      transition: all 0.3s ease;
      position: relative;
      overflow: hidden;
    }
    .summary-card::before {
      content: '';
      position: absolute;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      background: linear-gradient(135deg, rgba(102, 126, 234, 0.05) 0%, transparent 100%);
      opacity: 0;
      transition: opacity 0.3s ease;
    }
    .summary-card:hover::before {
      opacity: 1;
    }
    .summary-card:hover {
      transform: translateY(-3px);
      box-shadow: 0 6px 20px rgba(102, 126, 234, 0.2);
    }
    .summary-card h3 {
      margin: 0 0 12px 0;
      color: #667eea;
      font-size: 15px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }
    .summary-card .value {
      font-size: 32px;
      font-weight: 700;
      color: #2c3e50;
      text-shadow: 1px 1px 2px rgba(0,0,0,0.05);
    }
    .conclusion {
      background: linear-gradient(135deg, #e8f5e9 0%, #c8e6c9 100%);
      padding: 25px;
      border-radius: 12px;
      border-left: 5px solid #4caf50;
      margin: 25px 0;
      box-shadow: 0 3px 10px rgba(76, 175, 80, 0.15);
    }
    .conclusion h3 {
      color: #2e7d32;
      margin: 0 0 15px 0;
      font-size: 20px;
    }
    .conclusion p {
      margin: 12px 0;
      line-height: 1.8;
      color: #333;
      font-size: 15px;
    }
    .conclusion strong {
      color: #1b5e20;
      font-weight: 600;
    }
    .footer {
      text-align: center;
      color: #999;
      padding: 30px;
      margin-top: 50px;
      font-size: 14px;
      border-top: 2px solid #e0e0e0;
    }
  </style>
</head>
<body>
  <div class="report-header">
    <h1>${i.title}</h1>
    <p>生成时间：${new Date().toLocaleString("zh-CN")}</p>
    <p>报告类型：${i.type==="summary"?"摘要报告":i.type==="detailed"?"详细报告":"对比报告"}</p>
    ${s?`<p style="font-size: 14px; margin-top: 10px; opacity: 0.9;">${s}</p>`:""}
  </div>
`;if(i.content.includes("statistics")){const c=(n.reduce((g,V)=>g+(V.rmspe||0),0)/n.length).toFixed(6),w=(n.reduce((g,V)=>g+(V.r2||0),0)/n.length).toFixed(6),L=(n.reduce((g,V)=>g+(V.trainingTime||0),0)/n.length).toFixed(2),U=n.reduce((g,V)=>(V.r2||0)>(g.r2||0)?V:g);y+=`
  <div class="section">
    <h2>📊 统计数据</h2>
    <div class="summary-grid">
      <div class="summary-card">
        <h3>模型数量</h3>
        <div class="value">${n.length}</div>
      </div>
      <div class="summary-card">
        <h3>平均 RMSPE</h3>
        <div class="value">${c}</div>
      </div>
      <div class="summary-card">
        <h3>平均 R²</h3>
        <div class="value">${w}</div>
      </div>
      <div class="summary-card">
        <h3>平均训练时间</h3>
        <div class="value">${L}s</div>
      </div>
      <div class="summary-card">
        <h3>最佳模型</h3>
        <div class="value">${a(U.algorithm)}</div>
      </div>
    </div>
  </div>
`}if(i.content.includes("tables")&&i.type!=="summary"&&(y+=`
  <div class="section">
    <h2>📋 性能对比表</h2>
    <table>
      <thead>
        <tr>
          <th>算法</th>
          <th>RMSPE</th>
          <th>MSE</th>
          <th>R²</th>
          <th>MAE</th>
          <th>训练时间(s)</th>
          <th>参数量(M)</th>
        </tr>
      </thead>
      <tbody>
`,n.forEach(c=>{var w,L,U,g,V,se;y+=`
        <tr>
          <td><strong>${a(c.algorithm)}</strong></td>
          <td>${((w=c.rmspe)==null?void 0:w.toFixed(6))||"N/A"}</td>
          <td>${((L=c.mse)==null?void 0:L.toExponential(4))||"N/A"}</td>
          <td>${((U=c.r2)==null?void 0:U.toFixed(6))||"N/A"}</td>
          <td>${((g=c.mae)==null?void 0:g.toFixed(6))||"N/A"}</td>
          <td>${((V=c.trainingTime)==null?void 0:V.toFixed(2))||"N/A"}</td>
          <td>${((se=c.parameters)==null?void 0:se.toFixed(2))||"N/A"}</td>
        </tr>
`}),y+=`
      </tbody>
    </table>
  </div>
`),i.content.includes("conclusion")){const c=n.reduce((U,g)=>(g.r2||0)>(U.r2||0)?g:U),w=n.reduce((U,g)=>(g.trainingTime||1/0)<(U.trainingTime||1/0)?g:U);let L="";i.type==="summary"?L=`在全部 ${n.length} 个模型中，${a(c.algorithm)} 表现最佳，建议优先选用。`:i.type==="comparison"?L=`在对比的 ${n.length} 个模型中，${a(c.algorithm)} 的 R² 指标最高，而 ${a(w.algorithm)} 训练速度最快。根据实际需求选择合适的模型。`:L=`如果追求高精度，建议使用 ${a(c.algorithm)}；如果需要快速训练，可选择 ${a(w.algorithm)}。`,y+=`
  <div class="section">
    <h2>📝 结论分析</h2>
    <div class="conclusion">
      <h3>性能评价</h3>
      <p><strong>最佳性能模型：</strong>${a(c.algorithm)} (R² = ${(o=c.r2)==null?void 0:o.toFixed(6)})</p>
      <p><strong>最快训练速度：</strong>${a(w.algorithm)} (${(p=w.trainingTime)==null?void 0:p.toFixed(2)}s)</p>
      <p><strong>综合建议：</strong>${L}</p>
    </div>
  </div>
`}y+=`
  <div class="footer">
    <p>电池寿命预测系统 - 结果分析报告</p>
  </div>
</body>
</html>
`;const M=new Blob([y],{type:"text/html;charset=utf-8;"}),F=URL.createObjectURL(M),x=document.createElement("a");x.setAttribute("href",F),x.setAttribute("download",`${i.title}_${new Date().toISOString().slice(0,10)}.html`),x.style.visibility="hidden",document.body.appendChild(x),x.click(),document.body.removeChild(x),URL.revokeObjectURL(F),P.success("报告生成成功"),J.value=!1}catch(i){console.error("生成报告失败:",i),P.error("生成报告失败")}},fe=()=>{try{if(E.value.length===0){P.warning("暂无数据可导出");return}let o="\uFEFF";o+=`"算法","RMSPE","MSE","R²","MAE","MAPE","SMAPE","训练时间(s)","参数量(M)"
`,E.value.forEach(s=>{var u,m,y,M,F,x;o+=`"${a(s.algorithm)}",`,o+=`"${((u=s.rmspe)==null?void 0:u.toFixed(6))||"N/A"}",`,o+=`"${((m=s.mse)==null?void 0:m.toExponential(4))||"N/A"}",`,o+=`"${((y=s.r2)==null?void 0:y.toFixed(6))||"N/A"}",`,o+=`"${((M=s.mae)==null?void 0:M.toFixed(6))||"N/A"}",`,o+=`"${s.mape?(s.mape*100).toFixed(4)+"%":"N/A"}",`,o+=`"${s.smape?(s.smape*100).toFixed(4)+"%":"N/A"}",`,o+=`"${((F=s.trainingTime)==null?void 0:F.toFixed(2))||"N/A"}",`,o+=`"${((x=s.parameters)==null?void 0:x.toFixed(2))||"N/A"}"
`});const p=new Blob([o],{type:"text/csv;charset=utf-8;"}),i=URL.createObjectURL(p),n=document.createElement("a");n.setAttribute("href",i),n.setAttribute("download",`模型性能对比报告_${new Date().toISOString().slice(0,10)}.csv`),n.style.visibility="hidden",document.body.appendChild(n),n.click(),document.body.removeChild(n),URL.revokeObjectURL(i),P.success(`成功导出 ${E.value.length} 条数据`)}catch(o){console.error("导出失败:",o),P.error("导出失败")}},be=()=>{var o,p,i,n,s,u,m;try{const y={算法名称:a(b.algorithm),RMSPE:((o=b.rmspe)==null?void 0:o.toFixed(6))||"N/A",MSE:((p=b.mse)==null?void 0:p.toExponential(6))||"N/A","R²":((i=b.r2)==null?void 0:i.toFixed(6))||"N/A",MAE:((n=b.mae)==null?void 0:n.toFixed(6))||"N/A",MAPE:b.mape?`${(b.mape*100).toFixed(4)}%`:"N/A",SMAPE:b.smape?`${(b.smape*100).toFixed(4)}%`:"N/A",训练时间:`${((s=b.trainingTime)==null?void 0:s.toFixed(2))||0}秒`,参数量:`${((u=b.parameters)==null?void 0:u.toFixed(2))||0}M`,内存占用:`${b.memoryUsage||0}MB`,收敛轮数:b.convergenceEpoch||"N/A",最佳验证损失:((m=b.bestValLoss)==null?void 0:m.toExponential(6))||"N/A"};let M="\uFEFF";M+=`指标,数值
`,Object.entries(y).forEach(([w,L])=>{M+=`"${w}","${L}"
`});const F=new Blob([M],{type:"text/csv;charset=utf-8;"}),x=URL.createObjectURL(F),c=document.createElement("a");c.setAttribute("href",x),c.setAttribute("download",`${a(b.algorithm)}_性能报告_${new Date().toISOString().slice(0,10)}.csv`),c.style.visibility="hidden",document.body.appendChild(c),c.click(),document.body.removeChild(c),URL.revokeObjectURL(x),P.success("结果导出成功")}catch(y){console.error("导出失败:",y),P.error("导出失败")}},ee=(o=null)=>{if(B){let p=["Baseline","BiLSTM","DeepHPM"],i=[];if(o&&o.length>0){p=o.map(u=>{const m=u.algorithm||"";return m.includes("baseline")?"Baseline":m.includes("bilstm")||m.includes("lstm")?"BiLSTM":m.includes("deepphm")||m.includes("deephpm")?"DeepHPM":u.algorithmName||m});const s={rmspe:{name:"RMSPE",color:"#ee6666",key:"rmspe"},mse:{name:"MSE",color:"#fac858",key:"mse"},r2:{name:"R²",color:"#73c0de",key:"r2"},mae:{name:"MAE",color:"#91cc75",key:"mae"},mape:{name:"MAPE",color:"#5470c6",key:"mape"}};G.value.forEach(u=>{const m=s[u];m&&i.push({name:m.name,type:"bar",data:o.map(y=>y[m.key]||0),itemStyle:{color:m.color}})})}else{const s={rmspe:{name:"RMSPE",color:"#ee6666",data:[.0324,.0218,.0156]},mse:{name:"MSE",color:"#fac858",data:[8e-4,5e-4,3e-4]},r2:{name:"R²",color:"#73c0de",data:[.9456,.9723,.9876]},mae:{name:"MAE",color:"#91cc75",data:[.0187,.0152,.0123]},mape:{name:"MAPE",color:"#5470c6",data:[.0123,.0087,.0065]}};G.value.forEach(u=>{const m=s[u];m&&i.push({name:m.name,type:"bar",data:m.data,itemStyle:{color:m.color}})})}const n=r.value==="algorithm";B.setOption({title:{text:n?"算法性能指标对比":"指标间对比",subtext:n?"不同算法在各项指标上的表现":"同一算法在不同指标上的表现"},tooltip:{trigger:"axis",axisPointer:{type:"shadow"}},legend:{data:i.map(s=>s.name)},grid:{left:"3%",right:"4%",bottom:"3%",containLabel:!0},xAxis:{type:n?"value":"category",boundaryGap:n?[0,.01]:!0,data:n?void 0:i.map(s=>s.name)},yAxis:{type:n?"category":"value",data:n?p:void 0},series:n?i:p.map((s,u)=>({name:s,type:"bar",data:i.map(m=>m.data[u]||0),itemStyle:{color:["#5470c6","#91cc75","#fac858"][u]}}))})}},te=(o=null)=>{if(v){let p=Array.from({length:100},(n,s)=>s+1),i=[];if(o&&o.length>0)o.forEach(n=>{const s=n.algorithm||"";let u="Unknown",m="#5470c6";s.includes("baseline")?(u="Baseline",m="#5470c6"):s.includes("bilstm")||s.includes("lstm")?(u="BiLSTM",m="#91cc75"):(s.includes("deepphm")||s.includes("deephpm"))&&(u="DeepHPM",m="#fac858");const y=n.convergenceEpoch||n.epochs||50,M=n.bestValLoss||.001,F=p.map(x=>x>y?M+Math.random()*1e-4:M*Math.exp(-x/(y/3))+Math.random()*1e-4);i.push({name:u,type:"line",data:F,smooth:!0,lineStyle:{color:m},symbol:"none",sampling:"average"})});else{const n=p.map(m=>.5*Math.exp(-m/30)+.001+Math.random()*2e-4),s=p.map(m=>.4*Math.exp(-m/50)+8e-4+Math.random()*15e-5),u=p.map(m=>.3*Math.exp(-m/70)+5e-4+Math.random()*1e-4);i=[{name:"Baseline",type:"line",data:n,smooth:!0,lineStyle:{color:"#5470c6"},symbol:"none"},{name:"BiLSTM",type:"line",data:s,smooth:!0,lineStyle:{color:"#91cc75"},symbol:"none"},{name:"DeepHPM",type:"line",data:u,smooth:!0,lineStyle:{color:"#fac858"},symbol:"none"}]}v.setOption({title:{text:"模型收敛性能对比",subtext:"各算法训练损失随轮数变化"},tooltip:{trigger:"axis",axisPointer:{type:"cross"},formatter:function(n){let s=`Epoch ${n[0].axisValue}<br/>`;return n.forEach(u=>{s+=`${u.marker} ${u.seriesName}: ${u.value.toFixed(6)}<br/>`}),s}},legend:{data:i.map(n=>n.name),top:30},grid:{left:"3%",right:"4%",bottom:"3%",top:"15%",containLabel:!0},xAxis:{type:"category",boundaryGap:!1,data:p,name:"Epoch",nameLocation:"middle",nameGap:30},yAxis:{type:"value",min:0,name:"损失值",nameLocation:"middle",nameGap:50},series:i})}},K=()=>{if(I){const o=j.value;let p=[],i=[],n=[],s=[];if(o&&o.x&&o.series)p=o.x.map(u=>Number(u).toFixed(4)),i=o.series.baseline||new Array(p.length).fill(0),n=o.series.bilstm||new Array(p.length).fill(0),s=o.series.deepphm||new Array(p.length).fill(0);else{const u=Array.from({length:1e3},()=>Math.abs(Math.random()*.05)),m=Array.from({length:1e3},()=>Math.abs(Math.random()*.035)),y=Array.from({length:1e3},()=>Math.abs(Math.random()*.025)),M=20,F=.05/M;i=new Array(M).fill(0),n=new Array(M).fill(0),s=new Array(M).fill(0),u.forEach(x=>{const c=Math.min(Math.floor(x/F),M-1);i[c]++}),m.forEach(x=>{const c=Math.min(Math.floor(x/F),M-1);n[c]++}),y.forEach(x=>{const c=Math.min(Math.floor(x/F),M-1);s[c]++}),p=Array.from({length:M},(x,c)=>(c*F+F/2).toFixed(4))}I.setOption({title:{text:"预测误差分布对比",subtext:"不同算法预测误差的分布情况"},tooltip:{trigger:"axis"},legend:{data:["Baseline","BiLSTM","DeepHPM"]},grid:{left:"3%",right:"4%",bottom:"3%",containLabel:!0},xAxis:{type:"category",data:p},yAxis:{type:"value"},series:[{name:"Baseline",type:"bar",data:i,itemStyle:{color:"rgba(84, 112, 198, 0.7)"}},{name:"BiLSTM",type:"bar",data:n,itemStyle:{color:"rgba(145, 204, 117, 0.7)"}},{name:"DeepHPM",type:"bar",data:s,itemStyle:{color:"rgba(250, 200, 88, 0.7)"}}]})}},xe=()=>{if(O){const o=Array.from({length:100},(i,n)=>n+1),p=o.map(i=>b.bestValLoss*Math.exp(-i/(b.convergenceEpoch/3))+Math.random()*1e-4);O.setOption({title:{text:"训练趋势",subtext:"损失值随训练轮数的变化"},tooltip:{trigger:"axis"},grid:{left:"3%",right:"4%",bottom:"3%",containLabel:!0},xAxis:{type:"category",boundaryGap:!1,data:o},yAxis:{type:"value"},series:[{name:"验证损失",type:"line",data:p,smooth:!0,lineStyle:{color:"#5470c6"}}]})}},ye=()=>{T.value&&(B=le(T.value)),H.value&&(v=le(H.value)),D.value&&(I=le(D.value)),ee(),te(),K()},ne=()=>{B&&B.resize(),v&&v.resize(),I&&I.resize(),O&&O.resize()};return we(async()=>{ye(),window.addEventListener("resize",ne),await Q()}),Ae(()=>{B&&B.dispose(),v&&v.dispose(),I&&I.dispose(),O&&O.dispose(),window.removeEventListener("resize",ne)}),{selectedAlgorithms:e,selectedMetrics:G,comparisonType:r,performanceChartRef:T,convergenceChartRef:H,distributionChartRef:D,trendChartRef:W,detailedResults:E,detailsDialogVisible:X,currentDetail:b,reportDialogVisible:J,reportForm:Z,compareDialogVisible:oe,selectedRowIds:re,selectedModels:S,handleSelectionChange:me,showCompareDialog:ce,getAlgorithmTagType:ie,getAlgorithmLabel:a,viewDetails:_,handleClose:ue,generateReport:ge,confirmGenerateReport:he,exportAll:fe,exportSingleResult:be}}},Re={class:"results-analysis"},De={class:"control-item"},Fe={class:"control-item"},Ve={class:"control-item"},Ne={class:"control-item"},Le={ref:"performanceChartRef",style:{height:"400px"}},Te={ref:"convergenceChartRef",style:{height:"400px"}},Pe={ref:"distributionChartRef",style:{height:"400px"}},Ue={class:"chart-header"},ze={ref:"trendChartRef",style:{height:"300px"}},Oe={key:0,style:{"max-height":"500px",overflow:"auto"}},Be={style:{width:"100%","border-collapse":"collapse","font-size":"14px"}},Ie={style:{position:"sticky",top:"0",background:"#f5f7fa","z-index":"1"}};function $e(ae,e,G,r,oe,re){const S=A("el-option"),$=A("el-select"),N=A("el-card"),z=A("el-col"),j=A("el-radio"),Q=A("el-radio-group"),T=A("el-button"),H=A("el-row"),D=A("el-table-column"),W=A("el-tag"),B=A("el-table"),v=A("el-descriptions-item"),I=A("el-descriptions"),O=A("el-divider"),E=A("el-dialog"),X=A("el-input"),b=A("el-form-item"),J=A("el-checkbox"),Z=A("el-checkbox-group"),ie=A("el-form");return C(),R("div",Re,[t(N,{class:"card-container"},{header:l(()=>[...e[12]||(e[12]=[d("div",{class:"card-header"},[d("span",null,"结果分析")],-1)])]),default:l(()=>[t(H,{gutter:20,style:{"margin-bottom":"20px"}},{default:l(()=>[t(z,{span:6},{default:l(()=>[t(N,{shadow:"hover"},{default:l(()=>[d("div",De,[e[13]||(e[13]=d("div",{class:"control-label"},"选择算法",-1)),t($,{modelValue:r.selectedAlgorithms,"onUpdate:modelValue":e[0]||(e[0]=a=>r.selectedAlgorithms=a),placeholder:"选择算法",multiple:"","collapse-tags":"","collapse-tags-tooltip":"",style:{width:"100%"}},{default:l(()=>[t(S,{label:"Baseline",value:"baseline"}),t(S,{label:"BiLSTM",value:"bilstm"}),t(S,{label:"DeepHPM",value:"deepphm"})]),_:1},8,["modelValue"])])]),_:1})]),_:1}),t(z,{span:6},{default:l(()=>[t(N,{shadow:"hover"},{default:l(()=>[d("div",Fe,[e[14]||(e[14]=d("div",{class:"control-label"},"选择指标",-1)),t($,{modelValue:r.selectedMetrics,"onUpdate:modelValue":e[1]||(e[1]=a=>r.selectedMetrics=a),placeholder:"选择指标",multiple:"","collapse-tags":"","collapse-tags-tooltip":"",style:{width:"100%"}},{default:l(()=>[t(S,{label:"RMSPE",value:"rmspe"}),t(S,{label:"MSE",value:"mse"}),t(S,{label:"R²",value:"r2"}),t(S,{label:"MAE",value:"mae"}),t(S,{label:"MAPE",value:"mape"})]),_:1},8,["modelValue"])])]),_:1})]),_:1}),t(z,{span:6},{default:l(()=>[t(N,{shadow:"hover"},{default:l(()=>[d("div",Ve,[e[17]||(e[17]=d("div",{class:"control-label"},"比较类型",-1)),t(Q,{modelValue:r.comparisonType,"onUpdate:modelValue":e[2]||(e[2]=a=>r.comparisonType=a),style:{display:"block"}},{default:l(()=>[t(j,{value:"algorithm"},{default:l(()=>[...e[15]||(e[15]=[h("算法间比较",-1)])]),_:1}),t(j,{value:"metric"},{default:l(()=>[...e[16]||(e[16]=[h("指标间比较",-1)])]),_:1})]),_:1},8,["modelValue"])])]),_:1})]),_:1}),t(z,{span:6},{default:l(()=>[t(N,{shadow:"hover"},{default:l(()=>[d("div",Ne,[e[20]||(e[20]=d("div",{class:"control-label"},"操作",-1)),t(T,{type:"primary",onClick:r.generateReport},{default:l(()=>[...e[18]||(e[18]=[h("生成报告",-1)])]),_:1},8,["onClick"]),t(T,{onClick:r.exportAll},{default:l(()=>[...e[19]||(e[19]=[h("导出全部",-1)])]),_:1},8,["onClick"])])]),_:1})]),_:1})]),_:1}),t(H,{gutter:20},{default:l(()=>[t(z,{span:12},{default:l(()=>[t(N,{shadow:"hover"},{header:l(()=>[...e[21]||(e[21]=[d("div",{class:"chart-header"},[d("span",null,"性能指标对比图")],-1)])]),default:l(()=>[d("div",Le,null,512)]),_:1})]),_:1}),t(z,{span:12},{default:l(()=>[t(N,{shadow:"hover"},{header:l(()=>[...e[22]||(e[22]=[d("div",{class:"chart-header"},[d("span",null,"收敛性能分析")],-1)])]),default:l(()=>[d("div",Te,null,512)]),_:1})]),_:1})]),_:1}),t(H,{gutter:20,style:{"margin-top":"20px"}},{default:l(()=>[t(z,{span:24},{default:l(()=>[t(N,{shadow:"hover"},{header:l(()=>[...e[23]||(e[23]=[d("div",{class:"chart-header"},[d("span",null,"预测精度分布图")],-1)])]),default:l(()=>[d("div",Pe,null,512)]),_:1})]),_:1})]),_:1}),t(H,{gutter:20,style:{"margin-top":"20px"}},{default:l(()=>[t(z,{span:24},{default:l(()=>[t(N,{shadow:"hover"},{header:l(()=>[d("div",Ue,[e[24]||(e[24]=d("span",null,"详细性能数据",-1)),d("div",null,[t(T,{size:"small",type:"primary",disabled:r.selectedRowIds.length<2,onClick:r.showCompareDialog},{default:l(()=>[h(" 对比选中模型 ("+f(r.selectedRowIds.length)+") ",1)]),_:1},8,["disabled","onClick"])])])]),default:l(()=>[t(B,{data:r.detailedResults,stripe:"",style:{width:"100%"},height:"400",onSelectionChange:r.handleSelectionChange},{default:l(()=>[t(D,{type:"selection",width:"55"}),t(D,{prop:"algorithm",label:"算法",width:"150"},{default:l(({row:a})=>[t(W,{type:r.getAlgorithmTagType(a.algorithm),size:"small"},{default:l(()=>[h(f(r.getAlgorithmLabel(a.algorithm)),1)]),_:2},1032,["type"])]),_:1}),t(D,{prop:"rmspe",label:"RMSPE",width:"120"},{default:l(({row:a})=>[d("span",null,f(a.rmspe.toFixed(6)),1)]),_:1}),t(D,{prop:"mse",label:"MSE",width:"120"},{default:l(({row:a})=>[d("span",null,f(a.mse.toExponential(4)),1)]),_:1}),t(D,{prop:"r2",label:"R²",width:"120"},{default:l(({row:a})=>[d("span",null,f(a.r2.toFixed(6)),1)]),_:1}),t(D,{prop:"mae",label:"MAE",width:"120"},{default:l(({row:a})=>[d("span",null,f(a.mae.toFixed(6)),1)]),_:1}),t(D,{prop:"mape",label:"MAPE",width:"120"},{default:l(({row:a})=>[d("span",null,f((a.mape*100).toFixed(4))+"%",1)]),_:1}),t(D,{prop:"smape",label:"SMAPE",width:"120"},{default:l(({row:a})=>[d("span",null,f((a.smape*100).toFixed(4))+"%",1)]),_:1}),t(D,{prop:"trainingTime",label:"训练时间(s)",width:"120"},{default:l(({row:a})=>[d("span",null,f(a.trainingTime.toFixed(2)),1)]),_:1}),t(D,{prop:"parameters",label:"参数量(M)",width:"120"},{default:l(({row:a})=>[d("span",null,f(a.parameters.toFixed(2)),1)]),_:1}),t(D,{label:"操作",fixed:"right",width:"100"},{default:l(({row:a})=>[t(T,{size:"small",onClick:_=>r.viewDetails(a)},{default:l(()=>[...e[25]||(e[25]=[h("查看详情",-1)])]),_:1},8,["onClick"])]),_:1})]),_:1},8,["data","onSelectionChange"])]),_:1})]),_:1})]),_:1})]),_:1}),t(E,{modelValue:r.detailsDialogVisible,"onUpdate:modelValue":e[4]||(e[4]=a=>r.detailsDialogVisible=a),title:"算法详情",width:"800px","before-close":r.handleClose},{footer:l(()=>[t(T,{onClick:e[3]||(e[3]=a=>r.detailsDialogVisible=!1)},{default:l(()=>[...e[26]||(e[26]=[h("关闭",-1)])]),_:1}),t(T,{type:"primary",onClick:r.exportSingleResult},{default:l(()=>[...e[27]||(e[27]=[h("导出此结果",-1)])]),_:1},8,["onClick"])]),default:l(()=>[t(I,{column:2,border:""},{default:l(()=>[t(v,{label:"算法名称"},{default:l(()=>[t(W,{type:r.getAlgorithmTagType(r.currentDetail.algorithm)},{default:l(()=>[h(f(r.getAlgorithmLabel(r.currentDetail.algorithm)),1)]),_:1},8,["type"])]),_:1}),t(v,{label:"RMSPE"},{default:l(()=>[h(f(r.currentDetail.rmspe.toFixed(6)),1)]),_:1}),t(v,{label:"MSE"},{default:l(()=>[h(f(r.currentDetail.mse.toExponential(6)),1)]),_:1}),t(v,{label:"R²"},{default:l(()=>[h(f(r.currentDetail.r2.toFixed(6)),1)]),_:1}),t(v,{label:"MAE"},{default:l(()=>[h(f(r.currentDetail.mae.toFixed(6)),1)]),_:1}),t(v,{label:"MAPE"},{default:l(()=>[h(f((r.currentDetail.mape*100).toFixed(4))+"%",1)]),_:1}),t(v,{label:"SMAPE"},{default:l(()=>[h(f((r.currentDetail.smape*100).toFixed(4))+"%",1)]),_:1}),t(v,{label:"训练时间"},{default:l(()=>[h(f(r.currentDetail.trainingTime.toFixed(2))+"秒",1)]),_:1}),t(v,{label:"参数量"},{default:l(()=>[h(f(r.currentDetail.parameters.toFixed(2))+"M",1)]),_:1}),t(v,{label:"内存占用"},{default:l(()=>[h(f(r.currentDetail.memoryUsage)+"MB",1)]),_:1}),t(v,{label:"收敛轮数"},{default:l(()=>[h(f(r.currentDetail.convergenceEpoch),1)]),_:1}),t(v,{label:"最佳验证损失"},{default:l(()=>[h(f(r.currentDetail.bestValLoss.toExponential(6)),1)]),_:1})]),_:1}),t(O),d("div",ze,null,512)]),_:1},8,["modelValue","before-close"]),t(E,{modelValue:r.compareDialogVisible,"onUpdate:modelValue":e[6]||(e[6]=a=>r.compareDialogVisible=a),title:"模型对比",width:"70%"},{footer:l(()=>[t(T,{onClick:e[5]||(e[5]=a=>r.compareDialogVisible=!1)},{default:l(()=>[...e[35]||(e[35]=[h("关闭",-1)])]),_:1})]),default:l(()=>[r.selectedModels.length>0?(C(),R("div",Oe,[d("table",Be,[d("thead",Ie,[d("tr",null,[e[28]||(e[28]=d("th",{style:{padding:"10px",border:"1px solid #ddd","text-align":"left"}},"指标",-1)),(C(!0),R(Y,null,q(r.selectedModels,a=>(C(),R("th",{key:a.id,style:{padding:"10px",border:"1px solid #ddd","text-align":"center"}},f(r.getAlgorithmLabel(a.algorithm)),1))),128))])]),d("tbody",null,[d("tr",null,[e[29]||(e[29]=d("td",{style:{padding:"10px",border:"1px solid #ddd","font-weight":"bold"}},"RMSPE",-1)),(C(!0),R(Y,null,q(r.selectedModels,a=>{var _;return C(),R("td",{key:a.id,style:{padding:"10px",border:"1px solid #ddd","text-align":"center"}},f(((_=a.rmspe)==null?void 0:_.toFixed(6))||"N/A"),1)}),128))]),d("tr",null,[e[30]||(e[30]=d("td",{style:{padding:"10px",border:"1px solid #ddd","font-weight":"bold"}},"MSE",-1)),(C(!0),R(Y,null,q(r.selectedModels,a=>{var _;return C(),R("td",{key:a.id,style:{padding:"10px",border:"1px solid #ddd","text-align":"center"}},f(((_=a.mse)==null?void 0:_.toExponential(4))||"N/A"),1)}),128))]),d("tr",null,[e[31]||(e[31]=d("td",{style:{padding:"10px",border:"1px solid #ddd","font-weight":"bold"}},"R²",-1)),(C(!0),R(Y,null,q(r.selectedModels,a=>{var _;return C(),R("td",{key:a.id,style:{padding:"10px",border:"1px solid #ddd","text-align":"center"}},f(((_=a.r2)==null?void 0:_.toFixed(6))||"N/A"),1)}),128))]),d("tr",null,[e[32]||(e[32]=d("td",{style:{padding:"10px",border:"1px solid #ddd","font-weight":"bold"}},"MAE",-1)),(C(!0),R(Y,null,q(r.selectedModels,a=>{var _;return C(),R("td",{key:a.id,style:{padding:"10px",border:"1px solid #ddd","text-align":"center"}},f(((_=a.mae)==null?void 0:_.toFixed(6))||"N/A"),1)}),128))]),d("tr",null,[e[33]||(e[33]=d("td",{style:{padding:"10px",border:"1px solid #ddd","font-weight":"bold"}},"训练时间(s)",-1)),(C(!0),R(Y,null,q(r.selectedModels,a=>{var _;return C(),R("td",{key:a.id,style:{padding:"10px",border:"1px solid #ddd","text-align":"center"}},f(((_=a.trainingTime)==null?void 0:_.toFixed(2))||"N/A"),1)}),128))]),d("tr",null,[e[34]||(e[34]=d("td",{style:{padding:"10px",border:"1px solid #ddd","font-weight":"bold"}},"参数量(M)",-1)),(C(!0),R(Y,null,q(r.selectedModels,a=>{var _;return C(),R("td",{key:a.id,style:{padding:"10px",border:"1px solid #ddd","text-align":"center"}},f(((_=a.parameters)==null?void 0:_.toFixed(2))||"N/A"),1)}),128))])])])])):Ee("",!0)]),_:1},8,["modelValue"]),t(E,{modelValue:r.reportDialogVisible,"onUpdate:modelValue":e[11]||(e[11]=a=>r.reportDialogVisible=a),title:"生成分析报告",width:"600px"},{footer:l(()=>[t(T,{onClick:e[10]||(e[10]=a=>r.reportDialogVisible=!1)},{default:l(()=>[...e[43]||(e[43]=[h("取消",-1)])]),_:1}),t(T,{type:"primary",onClick:r.confirmGenerateReport},{default:l(()=>[...e[44]||(e[44]=[h("生成报告",-1)])]),_:1},8,["onClick"])]),default:l(()=>[t(ie,{model:r.reportForm,"label-width":"120px"},{default:l(()=>[t(b,{label:"报告标题"},{default:l(()=>[t(X,{modelValue:r.reportForm.title,"onUpdate:modelValue":e[7]||(e[7]=a=>r.reportForm.title=a),placeholder:"请输入报告标题"},null,8,["modelValue"])]),_:1}),t(b,{label:"报告类型"},{default:l(()=>[t(Q,{modelValue:r.reportForm.type,"onUpdate:modelValue":e[8]||(e[8]=a=>r.reportForm.type=a)},{default:l(()=>[t(j,{value:"summary"},{default:l(()=>[...e[36]||(e[36]=[h("摘要报告",-1)])]),_:1}),t(j,{value:"detailed"},{default:l(()=>[...e[37]||(e[37]=[h("详细报告",-1)])]),_:1}),t(j,{value:"comparison"},{default:l(()=>[...e[38]||(e[38]=[h("对比报告",-1)])]),_:1})]),_:1},8,["modelValue"])]),_:1}),t(b,{label:"包含内容"},{default:l(()=>[t(Z,{modelValue:r.reportForm.content,"onUpdate:modelValue":e[9]||(e[9]=a=>r.reportForm.content=a)},{default:l(()=>[t(J,{label:"charts"},{default:l(()=>[...e[39]||(e[39]=[h("图表",-1)])]),_:1}),t(J,{label:"tables"},{default:l(()=>[...e[40]||(e[40]=[h("表格",-1)])]),_:1}),t(J,{label:"statistics"},{default:l(()=>[...e[41]||(e[41]=[h("统计数据",-1)])]),_:1}),t(J,{label:"conclusion"},{default:l(()=>[...e[42]||(e[42]=[h("结论分析",-1)])]),_:1})]),_:1},8,["modelValue"])]),_:1})]),_:1},8,["model"])]),_:1},8,["modelValue"])])}const qe=ke(Ce,[["render",$e],["__scopeId","data-v-322179ac"]]);export{qe as default};
