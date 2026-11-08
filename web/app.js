const $=s=>document.querySelector(s);
const defaults={pp:4,microbatches:8,forward:1,backward_input:1,weight:1,comm:.1};
const cases={baseline:{title:'基础对照',description:'固定 4 张 GPU、8 个微批，先观察同一工作量怎样排进时间轴。',config:{...defaults}},high_comm:{title:'只改变通信耗时',description:'与基础组相比，只把 C 从 0.1 增加到 1.0，观察等待与覆盖怎样变化。',config:{...defaults,comm:1}},more_microbatches:{title:'只改变微批数量',description:'通信恢复到 0.1，只把 M 从 8 增加到 16，观察首尾空闲的相对占比。',config:{...defaults,microbatches:16}}};
const colors={F:'#2e67ac',B:'#278468',W:'#cc8329',COMM:'#8870bd'};
let currentCase='baseline',data=null,playing=false,time=0,horizon=1,last=0,requestVersion=0,busy=false;
const history={};
const fmt=n=>Number(n).toFixed(2),pct=n=>(100*n).toFixed(1)+'%';
function config(){return Object.fromEntries([...$('#parameters').elements].filter(x=>x.name).map(x=>[x.name,Number(x.value)]));}
function updateCode(){let c=config();$('#code').textContent=`from dualpipe_a import Config, simulate\n\nfor overlap in (False, True):\n    config = Config(\n        pp=${c.pp}, microbatches=${c.microbatches},\n        forward=${c.forward},\n        backward_input=${c.backward_input},\n        weight=${c.weight}, comm=${c.comm},\n        allow_compute_comm_overlap=overlap\n    )\n    runs = [simulate(config, method)\n            for method in ("1f1b", "dualpipe")]`}
function clearResult(message){requestVersion++;data=null;playing=false;time=0;$('#timelines').hidden=true;$('#empty').hidden=false;$('#results').hidden=true;$('#event-inspector').hidden=true;$('#clock').textContent='t = 0.00';$('#scrub').value=0;for(let id of ['play','finish','scrub','save-json','save-svg','save-png','next-event','previous-event'])$('#'+id).disabled=true;$('#status').className='';$('#status').textContent=message;}
function selectCase(name){currentCase=name;for(let [k,v] of Object.entries(cases[name].config))$('#parameters').elements[k].value=v;document.querySelectorAll('[data-case]').forEach(b=>b.classList.toggle('selected',b.dataset.case===name));$('#case-title').textContent=cases[name].title;$('#case-description').textContent=cases[name].description;clearResult('本组参数已就绪，点击运行生成新的事件记录。');updateCode();}
document.querySelectorAll('[data-case]').forEach(b=>b.onclick=()=>selectCase(b.dataset.case));
$('#parameters').addEventListener('input',()=>{clearResult('参数已改变，请重新运行；旧结果已清除。');updateCode()});
$('#parameters').onsubmit=async ev=>{ev.preventDefault();if(busy)return;let params=config();if(params.microbatches%2){$('#status').textContent='双向对照需要偶数个微批。';$('#status').className='error';return;}clearResult('正在运行 Python 调度器，并校验任务依赖、资源冲突和工作量…');const version=requestVersion,caseKey=currentCase;busy=true;$('#run').disabled=true;$('#run').textContent='运行与校验中…';try{let response=await fetch('/api/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(params)});let result=await response.json();if(!response.ok)throw new Error(result.error||'运行失败');if(version!==requestVersion)return;data=result;if(Object.keys(defaults).every(k=>params[k]===cases[caseKey].config[k]))history[caseKey]=result;$('#status').textContent='本次计算已完成，依赖与资源校验通过；正在播放生成的事件记录。';$('#empty').hidden=true;$('#timelines').hidden=false;for(let id of ['play','finish','scrub','save-json','save-svg','save-png','next-event','previous-event'])$('#'+id).disabled=false;buildPlots();playing=true;$('#play').textContent='暂停';}catch(error){if(version===requestVersion){$('#status').textContent=error.message;$('#status').className='error';}}finally{busy=false;$('#run').disabled=false;$('#run').textContent='▶ 运行本组实验';}};
function svgElement(tag,attrs={},text){const e=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const [k,v]of Object.entries(attrs))e.setAttribute(k,v);if(text!==undefined)e.textContent=text;return e;}
function buildPlot(run,index){let width=1000,left=76,right=20,top=14,row=49,bottom=31,height=top+run.config.pp*row+bottom,span=width-left-right;let svg=svgElement('svg',{viewBox:`0 0 ${width} ${height}`,role:'img','aria-label':`${run.method} 调度时间轴`});let defs=svgElement('defs'),clip=svgElement('clipPath',{id:`reveal-${index}`}),rect=svgElement('rect',{x:left,y:0,width:0,height:height,'data-clip':index});clip.append(rect);defs.append(clip);svg.append(defs);svg.append(svgElement('rect',{width,height,fill:'white'}));
 for(let tick=0;tick<=8;tick++){let x=left+span*tick/8;svg.append(svgElement('line',{x1:x,y1:top,x2:x,y2:height-bottom,stroke:'#e3e8ef','stroke-width':1}));svg.append(svgElement('text',{x,y:height-10,fill:'#30475f','font-size':11,'text-anchor':'middle'},fmt(horizon*tick/8)));}
 for(let gpu=0;gpu<run.config.pp;gpu++){let y=top+gpu*row;svg.append(svgElement('text',{x:0,y:y+17,fill:'#203c66','font-size':13,'font-weight':600},`GPU ${gpu}`));svg.append(svgElement('text',{x:left-8,y:y+14,fill:'#3b536c','font-size':9,'text-anchor':'end'},'计算'));svg.append(svgElement('text',{x:left-8,y:y+33,fill:'#3b536c','font-size':9,'text-anchor':'end'},'通信'));svg.append(svgElement('rect',{x:left,y,width:span,height:19,fill:'#f3f6fa'}));svg.append(svgElement('rect',{x:left,y:y+23,width:span,height:12,fill:'#f7f7fa'}));}
 let events=svgElement('g',{'clip-path':`url(#reveal-${index})`});
 for(let event of run.events){let gpus=event.kind==='COMM'?[event.stage,event.peer]:[event.stage];for(let gpu of gpus){let y=top+gpu*row+(event.kind==='COMM'?23:0),x=left+span*event.start/horizon,w=span*event.duration/horizon,h=event.kind==='COMM'?12:19;let group=svgElement('g',{'data-event-id':event.id});let r=svgElement('rect',{x,y,width:Math.max(.3,w-.4),height:h,fill:colors[event.kind],stroke:event.direction===1?'#172b43':'white','stroke-width':event.direction===1?1.3:.4,'stroke-dasharray':event.direction===1?'4 2':'none',class:'event'});r.append(svgElement('title',{},`${event.kind} · 微批 ${event.microbatch} · ${event.direction===0?'GPU 0 端进入':'GPU '+(run.config.pp-1)+' 端进入'}\n${event.kind==='COMM'?`GPU ${event.stage} → GPU ${event.peer}`:`GPU ${event.stage}`}\n时间 ${fmt(event.start)}—${fmt(event.finish)}\n依赖：${event.deps.join(', ')||'无'}`));group.append(r);if(w>19&&event.kind!=='COMM')group.append(svgElement('text',{x:x+w/2,y:y+13,'text-anchor':'middle','font-size':w>35?10:9,fill:'white','pointer-events':'none'},w>35?`${event.kind}${event.microbatch}`:event.kind));events.append(group);}}
 svg.append(events);svg.append(svgElement('line',{x1:left,x2:left,y1:0,y2:height-bottom,stroke:'#be3652','stroke-width':2,'data-cursor':index}));const endX=left+span*run.metrics.makespan/horizon;svg.append(svgElement('line',{x1:endX,x2:endX,y1:top,x2:endX,y2:height-bottom,stroke:'#203c66','stroke-dasharray':'3 3','data-end':index,visibility:'hidden'}));$('#plot-'+index).replaceChildren(svg);}
function buildPlots(){selectedTask=null;const focus=$('#microbatch-focus');focus.innerHTML='<option value="all">全部</option>'+Array.from({length:data.config.microbatches},(_,i)=>`<option value="${i}">微批 ${i}</option>`).join('');$('#event-inspector').hidden=false;const runs=data.groups[$('#mode').value];horizon=Math.max(...runs.map(r=>r.metrics.makespan));time=0;$('#scrub').value=0;$('#results').hidden=true;runs.forEach((r,i)=>buildPlot(r,i+1));$('#mode-description').textContent=$('#mode').value==='overlap'?'两种调度均允许计算与通信并行，采用相同资源条件。':'两种调度均让通信占用两端 GPU，采用相同资源条件。';paint();}
function paint(){if(!data)return;let ratio=time/horizon;document.querySelectorAll('[data-clip]').forEach(e=>e.setAttribute('width',904*ratio));document.querySelectorAll('[data-cursor]').forEach(e=>{e.setAttribute('x1',76+904*ratio);e.setAttribute('x2',76+904*ratio)});data.groups[$('#mode').value].forEach((run,i)=>{const active=run.events.filter(e=>e.start<=time&&e.finish>time);$('#active-'+(i+1)).textContent=time>=run.metrics.makespan?'已完成':`计算 ${active.filter(e=>e.kind!=='COMM').length} 项 · 通信 ${active.filter(e=>e.kind==='COMM').length} 项`;document.querySelector(`[data-end="${i+1}"]`).setAttribute('visibility',time>=run.metrics.makespan?'visible':'hidden')});$('#clock').textContent=`t = ${fmt(time)}`;$('#scrub').value=1000*ratio;inspectEvents();if(time>=horizon-1e-8){playing=false;$('#play').textContent='重新播放';renderMetrics();}else{$('#results').hidden=true;}}
function renderMetrics(){let [a,b]=data.groups[$('#mode').value].map(r=>r.metrics),speed=a.makespan/b.makespan,delta=a.makespan-b.makespan;$('#results').innerHTML=`<div class="metrics"><div><div class="metric-label">1F1B 总完成时间</div><div class="metric-number">${fmt(a.makespan)}</div><div class="metric-detail">计算空闲 ${pct(1-a.compute_gpu_fraction)}</div></div><div><div class="metric-label">简化双向 总完成时间</div><div class="metric-number">${fmt(b.makespan)}</div><div class="metric-detail">计算空闲 ${pct(1-b.compute_gpu_fraction)}</div></div><div><div class="metric-label">相对 1F1B 加速比</div><div class="metric-number">${fmt(speed)}×</div><div class="metric-detail">${delta>=0?'少用':'多用'} ${fmt(Math.abs(delta))} 个时间单位</div></div></div><p class="result-line">同 GPU 上的通信时间覆盖比例：1F1B ${pct(a.communication_overlap_fraction)}；简化双向 ${pct(b.communication_overlap_fraction)}。</p><p class="metric-help">计算空闲 = 1 − 计算占用时间 /（GPU 数 × 总完成时间），包含通信等待；通信覆盖按事件时间交集计算，不等于消除了同样比例的总耗时。</p>`;$('#results').hidden=false;$('#status').textContent='播放完成。可以拖动时间轴回看，或切换下一组参数。';}
function loop(now){if(playing&&data){time=Math.min(horizon,time+(now-last)/1000*(horizon/12)*Number($('#speed').value));paint();}last=now;requestAnimationFrame(loop);}requestAnimationFrame(loop);
$('#play').onclick=()=>{if(!data)return;if(time>=horizon){time=0;playing=true;paint();}else playing=!playing;$('#play').textContent=playing?'暂停':'继续';};
$('#finish').onclick=()=>{time=horizon;playing=false;paint();};
$('#scrub').oninput=()=>{playing=false;time=horizon*Number($('#scrub').value)/1000;$('#play').textContent='继续';paint();};
$('#mode').onchange=()=>{if(data){playing=false;buildPlots();$('#play').textContent='播放';}};
function download(content,name,type){const blob=content instanceof Blob?content:new Blob([content],{type});const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
$('#save-json').onclick=()=>download(JSON.stringify(data,null,2),`events-${currentCase}-${data.run_id}.json`,'application/json');
function exportSVG(){const nodes=[...document.querySelectorAll('#timelines svg')];const heights=nodes.map(n=>Number(n.getAttribute('viewBox').split(' ')[3]));let total=140+heights[0]+heights[1]+115;const svg=svgElement('svg',{xmlns:'http://www.w3.org/2000/svg',width:1100,height:total,viewBox:`0 0 1100 ${total}`});svg.append(svgElement('style',{},'text { font-family: Arial, Microsoft YaHei, sans-serif; }'));svg.append(svgElement('rect',{width:1100,height:total,fill:'white'}));svg.append(svgElement('text',{x:24,y:35,'font-size':23,fill:'#203c66'},`1F1B 与简化双向调度 · ${$('#mode').selectedOptions[0].text}`));let c=data.config;svg.append(svgElement('text',{x:24,y:61,'font-size':14,fill:'#172b43'},`P=${c.pp}  M=${c.microbatches}  F=${c.forward}  B=${c.backward_input}  W=${c.weight}  C=${c.comm}；时间为抽象单位`));svg.append(svgElement('text',{x:24,y:83,'font-size':12,fill:'#172b43'},'蓝色 F 前向 · 绿色 B 输入梯度 · 橙色 W 权重梯度 · 紫色通信；虚线边框表示另一方向'));let y=110;nodes.forEach((node,i)=>{svg.append(svgElement('text',{x:24,y,'font-size':17,fill:'#203c66'},i===0?'1F1B':'简化双向调度（DualPipe 思路）'));const copy=node.cloneNode(true);copy.setAttribute('x',24);copy.setAttribute('y',y+10);copy.setAttribute('width',1050);copy.setAttribute('height',heights[i]);copy.querySelectorAll('[data-clip]').forEach(r=>r.setAttribute('width',904));copy.querySelectorAll('[data-cursor]').forEach(r=>r.remove());copy.querySelectorAll('[data-end]').forEach(r=>r.setAttribute('visibility','visible'));svg.append(copy);y+=heights[i]+45;});const [a,b]=data.groups[$('#mode').value].map(r=>r.metrics);svg.append(svgElement('text',{x:24,y:y+2,'font-size':16,fill:'#203c66'},`总完成时间：${fmt(a.makespan)} / ${fmt(b.makespan)}　加速比：${fmt(a.makespan/b.makespan)}×`));svg.append(svgElement('text',{x:24,y:y+28,'font-size':12,fill:'#172b43'},'简化事件模型；独立计算/通信资源模式未模拟 SM、显存带宽争用，不代表真实 GPU 实测。'));return new XMLSerializer().serializeToString(svg);}
$('#save-svg').onclick=()=>download(exportSVG(),`pipeline-${currentCase}-${$('#mode').value}.svg`,'image/svg+xml');
$('#save-png').onclick=()=>{const source=new Blob([exportSVG()],{type:'image/svg+xml'}),url=URL.createObjectURL(source),im=new Image();im.onload=()=>{const canvas=document.createElement('canvas');canvas.width=im.width*2;canvas.height=im.height*2;canvas.getContext('2d').drawImage(im,0,0,canvas.width,canvas.height);canvas.toBlob(b=>{download(b,`pipeline-${currentCase}-${$('#mode').value}.png`,'image/png');URL.revokeObjectURL(url);});};im.onerror=()=>{$('#status').textContent='PNG 导出失败，可使用 SVG 导出。';URL.revokeObjectURL(url);};im.src=url;};
function summaryRows(){return Object.entries(cases).map(([key,c])=>{let d=history[key];if(!d)return {name:c.title,values:null};let [a,b]=d.groups[$('#mode').value].map(r=>r.metrics);return {name:c.title,values:[fmt(a.makespan),fmt(b.makespan),fmt(a.makespan/b.makespan),pct(1-a.compute_gpu_fraction),pct(1-b.compute_gpu_fraction)]};});}
$('#summary-button').onclick=()=>{let rows=summaryRows();$('#summary-content').innerHTML=`<p>当前资源模式：${$('#mode').selectedOptions[0].text}</p><table><thead><tr><th>实验组</th><th>1F1B 耗时</th><th>双向耗时</th><th>加速比</th><th>1F1B 计算空闲</th><th>双向计算空闲</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${r.name}</td>${r.values?r.values.map(v=>`<td>${v}</td>`).join(''):'<td colspan="5">尚未运行</td>'}</tr>`).join('')}</tbody></table>`;$('#summary').showModal();};
$('#close-summary').onclick=()=>$('#summary').close();
$('#summary-csv').onclick=()=>{let rows=summaryRows().filter(r=>r.values);download('\ufeff'+'实验组,1F1B耗时,双向耗时,加速比,1F1B计算空闲,双向计算空闲,资源模式\n'+rows.map(r=>[r.name,...r.values,$('#mode').value].join(',')).join('\n'),'三组实验汇总.csv','text/csv;charset=utf-8');};
if(!window.TRACE_DATA)fetch('/api/source').then(r=>r.json()).then(d=>$('#source').textContent=d.source).catch(()=>$('#source').textContent='源码位于 dualpipe_a/simulator.py');updateCode();

let selectedTask=null;
function eventTimes(){return [...new Set(data.groups[$('#mode').value].flatMap(r=>r.events.flatMap(e=>[e.start,e.finish])))].sort((a,b)=>a-b);}
function stepEvent(direction){if(!data)return;playing=false;let points=eventTimes();time=direction>0?(points.find(t=>t>time+1e-8)??horizon):([...points].reverse().find(t=>t<time-1e-8)??0);$('#play').textContent='继续';paint();}
$('#next-event').onclick=()=>stepEvent(1);$('#previous-event').onclick=()=>stepEvent(-1);
$('#microbatch-focus').onchange=()=>inspectEvents();
$('#timelines').onclick=ev=>{const g=ev.target.closest('[data-event-id]');if(!g||!data)return;const index=g.closest('#plot-1')?0:1;selectedTask={index,id:g.dataset.eventId};playing=false;$('#play').textContent='继续';inspectEvents();};
function inspectEvents(){
 if(!data)return;const runs=data.groups[$('#mode').value],focus=$('#microbatch-focus').value;
 runs.forEach((run,i)=>document.querySelectorAll(`#plot-${i+1} [data-event-id]`).forEach(g=>{
  const event=run.events.find(e=>e.id===g.dataset.eventId);
  g.setAttribute('opacity',focus==='all'||event.microbatch===Number(focus)?1:.13);
 }));
 const lines=[];
 for(const [i,run] of runs.entries()){
  const name=i?'简化双向':'1F1B';
  for(const e of run.events){
   if(Math.abs(e.finish-time)<1e-7)lines.push(`${name} 完成 ${e.id}`);
   if(Math.abs(e.start-time)<1e-7)lines.push(`${name} 开始 ${e.id}`);
  }
 }
 $('#event-log').textContent=lines.length?`t = ${fmt(time)}\n`+lines.join('\n'):`t = ${fmt(time)}\n位于两个事件时刻之间。\n点击“下一事件”查看状态变化。`;
 if(!selectedTask)selectedTask={index:1,id:runs[1].events[0].id};
 const run=runs[selectedTask.index],event=run.events.find(e=>e.id===selectedTask.id);
 if(!event)return;
 $('#task-title').textContent=(selectedTask.index?'简化双向':'1F1B')+' · '+event.id;
 const deps=event.deps.map(id=>run.events.find(e=>e.id===id));
 $('#task-detail').textContent=`task_id = "${event.id}"\n微批 ${event.microbatch}，GPU ${event.stage}${event.peer===null?'':` → GPU ${event.peer}`}\nstart = ${fmt(event.start)}, finish = ${fmt(event.finish)}\nresources = ${JSON.stringify(event.resources)}\n\n依赖任务：\n`+(deps.length?deps.map(e=>`${e.id}：${fmt(e.finish)} 完成${e.finish<=time+1e-8?' ✓':'（尚未完成）'}`).join('\n'):'无前置依赖');
 let reason;
 if(time>=event.finish-1e-8)reason='该任务已完成，后续任务还需检查其他依赖及资源是否就绪。';
 else if(time>=event.start-1e-8)reason='该任务正在执行。它开始时所有输入依赖均已完成，所需资源均可用。';
 else{
  const missing=deps.filter(e=>e.finish>time+1e-8);
  const holders=run.events.filter(e=>e.start<=time+1e-8&&e.finish>time+1e-8&&e.resources.some(r=>event.resources.includes(r)));
  reason=missing.length?'尚未开始：等待 '+missing.map(e=>e.id).join('、')+' 完成。':holders.length?'输入已就绪，但资源仍被 '+holders.map(e=>e.id).join('、')+' 占用。':'输入依赖和资源已就绪，启动时机还受该方法的队列或优先级规则约束。';
 }
 $('#task-reason').textContent=reason;
}

// Offline mode is created by a real execution of 课堂演示.py. It does not
// simulate or change parameters: it only reads the exact embedded event file.
if(window.TRACE_DATA){
 data=window.TRACE_DATA;document.body.classList.add('trace-only');
 document.title='流水线调度对比';$('h1').textContent='流水线调度对比';
 $('.eyebrow').remove();
 $('.header-right').remove();
 $('#empty').hidden=true;$('#timelines').hidden=false;
 for(const id of ['play','finish','scrub','save-json','save-svg','save-png','next-event','previous-event'])$('#'+id).disabled=false;
 buildPlots();playing=false;$('#play').textContent='播放记录';
}
