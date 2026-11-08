const $=s=>document.querySelector(s),esc=t=>String(t).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const colors={F:'#2e67ac',B:'#278468',W:'#cc8329',COMM:'#8870bd'},fmt=n=>Number(n).toFixed(2);
const titles=['1F1B','简化双向调度'],policies=['单向注入 · 阶段队列约束','双向注入 · 就绪任务优先级'];
let data=null,frames=[],index=0,timer=null,version=0,caches=[],displayTime=0,computing=false;
$('#comparison').innerHTML=titles.map((name,i)=>`<section class="comparison-row" id="row-${i}"><div class="row-heading"><h2>${name}</h2><span class="policy">${policies[i]}</span><span class="row-progress" id="progress-${i}">等待运行</span></div><div class="row-body"><section class="code-pane"><div class="code-header"><span>simulator.py · simulate()</span><span id="position-${i}"></span></div><div class="code" id="code-${i}" tabindex="0"><div class="placeholder">运行后显示实际调度代码。</div></div><div class="variables" id="variables-${i}">started = 0　completed = 0</div></section><section class="execution"><div class="action" id="action-${i}">等待运行</div><div class="gpus" id="gpus-${i}"></div><div class="history" id="history-${i}"></div></section></div></section>`).join('');
function updateRunButton(){
 const button=$('#run');button.disabled=computing;
 const ended=data&&displayTime>=Math.max(...data.runs.map(r=>r.metrics.makespan))-1e-8;
 button.textContent=computing?'计算中…':timer!==null?'暂停':!data?'运行并播放':ended?'重新播放':displayTime>0?'继续播放':'开始播放';
}
function stop(){cancelAnimationFrame(timer);timer=null;updateRunButton();}
function controls(value){for(const id of ['previous','next','overlap','first-finish','end','download'])$('#'+id).disabled=!value;}
function invalidate(){version++;stop();data=null;frames=[];caches=[];displayTime=0;controls(false);updateRunButton();$('#status').textContent='参数已改变，请重新运行。';$('#status').className='';$('#clock').textContent='t = 0.00';$('#comparison-result').textContent='等待运行';for(let i=0;i<2;i++){for(const key of ['gpus','history','position'])$('#'+key+'-'+i).innerHTML='';$('#code-'+i).innerHTML='<div class="placeholder">等待新的执行记录。</div>';$('#progress-'+i).textContent='等待运行';$('#action-'+i).textContent='等待运行';$('#variables-'+i).textContent='started = 0　completed = 0';}}
// Merge by model time, never by percentage or independent per-method frame count.
// At a shared timestamp, preserve every method's own sequential mutations.
function mergeFrames(runs){
 const result=[{time:0,indices:[0,0],changed:[true,true]}],pos=[1,1],current=[0,0];
 while(pos.some((v,i)=>v<runs[i].steps.length)){
  const t=Math.min(...runs.map((r,i)=>r.steps[pos[i]]?.time??Infinity));
  const buckets=runs.map((r,i)=>{const a=[];while(pos[i]<r.steps.length&&Math.abs(r.steps[pos[i]].time-t)<1e-8)a.push(pos[i]++);return a;});
  for(let k=0;k<Math.max(...buckets.map(a=>a.length));k++){
   const changed=buckets.map(a=>k<a.length);
   for(let i=0;i<2;i++)if(changed[i])current[i]=buckets[i][k];
   result.push({time:t,indices:[...current],changed});
  }
 }
 return result;
}
function accept(result){stop();data=result;index=0;frames=mergeFrames(data.runs);caches=data.runs.map(r=>({events:new Map(r.events.map(e=>[e.id,e]))}));$('#focus').innerHTML='<option value="all">全部</option>'+Array.from({length:data.config.microbatches},(_,i)=>`<option value="${i}">微批 ${i}</option>`).join('');for(let i=0;i<2;i++)$('#code-'+i).innerHTML=data.runs[i].source.map(l=>`<div class="code-line" data-line="${l.number}"><span class="line-number">${l.number}</span><span>${esc(l.text)}</span></div>`).join('');$('#durations').textContent=`F=${data.config.forward}　B=${data.config.backward_input}　W=${data.config.weight}`;controls(true);$('#status').textContent='';paint();}
$('#case').onchange=()=>{const name=$('#case').value;$('#pp').value=4;$('#mb').value=name==='more_microbatches'?16:8;$('#comm').value=name==='high_comm'?1:.1;invalidate();};
for(const id of ['pp','mb','comm','resources'])$('#'+id).oninput=invalidate;
$('#experiment').onsubmit=async ev=>{
 ev.preventDefault();if(computing)return;
 if(data){togglePlayback();return;}
 invalidate();const current=version;computing=true;updateRunButton();$('#status').textContent='正在运行两种调度…';
 try{
  const response=await fetch('/api/debug',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({pp:Number($('#pp').value),microbatches:Number($('#mb').value),comm:Number($('#comm').value),overlap:$('#resources').value==='true'})});
  const result=await response.json();if(current!==version)return;
  if(!response.ok)throw Error(result.error);
  accept(result);togglePlayback();
 }catch(e){if(current===version){$('#status').textContent=e.message;$('#status').className='error';}}
 finally{computing=false;updateRunButton();}
};
function move(direction){if(!data)return;index=Math.max(0,Math.min(frames.length-1,index+direction));paint();}
$('#next').onclick=()=>{stop();move(1);};$('#previous').onclick=()=>{stop();move(-1);};$('#focus').onchange=()=>paint(displayTime);
// 1× advances 0.1 model time units per real second; 30× advances 3.
// Wall-clock playback depends only on model time, never on trace step density.
function seekTime(time){
 const end=Math.max(...data.runs.map(r=>r.metrics.makespan));
 displayTime=Math.max(0,Math.min(end,time));
 let low=0,high=frames.length-1;
 while(low<high){const middle=Math.ceil((low+high)/2);if(frames[middle].time<=displayTime+1e-8)low=middle;else high=middle-1;}
 index=low;paint(displayTime);
}
function togglePlayback(){
 if(timer!==null){stop();return;}if(!data)return;
 const end=Math.max(...data.runs.map(r=>r.metrics.makespan));
 if(displayTime>=end-1e-8){index=0;paint();}
 let previous=performance.now();
 const tick=now=>{
  const elapsed=(now-previous)/1000;previous=now;
  const multiplier=650/Number($('#pace').value);
  seekTime(displayTime+elapsed*.1*multiplier);
  if(displayTime>=end-1e-8){stop();return;}
  timer=requestAnimationFrame(tick);
 };
 timer=requestAnimationFrame(tick);updateRunButton();
}
$('#first-finish').onclick=()=>{if(!data)return;stop();seekTime(Math.min(...data.runs.map(r=>r.metrics.makespan)));};

function overlaps(r,s,t){const active=s.running.map(id=>r.tasks[id]).filter(task=>caches[data.runs.indexOf(r)].events.get(task.id).finish>t+1e-8);return active.some(a=>a.kind!=='COMM'&&active.some(b=>b.kind==='COMM'&&(b.stage===a.stage||b.peer===a.stage)));}
$('#overlap').onclick=()=>{if(!data)return;stop();const eligible=f=>data.runs.some((r,i)=>{const s=r.steps[f.indices[i]];return f.changed[i]&&s.phase==='start'&&overlaps(r,s,f.time);});let target=frames.findIndex((f,j)=>j>index&&eligible(f));if(target<0)target=frames.findIndex(eligible);if(target<0){$('#status').textContent='当前资源模式下未出现计算与通信重叠。';return;}index=target;$('#status').textContent='';paint();};
function paint(time){if(!data)return;displayTime=typeof time==='number'?time:frames[index].time;const frame={...frames[index],time:displayTime};updateRunButton();$('#clock').textContent='t = '+fmt(frame.time);for(let i=0;i<2;i++)paintRow(i,frame);const [a,b]=data.runs.map(r=>r.metrics);if(frame.indices.every((n,i)=>data.runs[i].steps[n].phase==='done')){$('#comparison-result').innerHTML=`<strong>1F1B：${fmt(a.makespan)}</strong><strong>简化双向：${fmt(b.makespan)}</strong>相对加速比 ${(a.makespan/b.makespan).toFixed(3)}×　｜　计算空闲 ${(100*(1-a.compute_gpu_fraction)).toFixed(1)}% / ${(100*(1-b.compute_gpu_fraction)).toFixed(1)}%`;}else{const done=data.runs.map((r,i)=>r.steps[frame.indices[i]].phase==='done');if(done.some(Boolean)){const first=done[0]?0:1,other=1-first;$('#comparison-result').innerHTML=`<strong>${titles[first]}已于 ${fmt(data.runs[first].metrics.makespan)} 完成</strong>${titles[other]}继续执行，还需 ${fmt(Math.max(0,data.runs[other].metrics.makespan-frame.time))} 个时间单位`;}else $('#comparison-result').textContent='同一仿真时钟 · 相同工作量与资源条件 · 上下时间轴使用同一尺度';}}
function paintRow(i,frame){
 const r=data.runs[i],s=r.steps[frame.indices[i]],task=s.task?r.tasks[s.task]:null,eventMap=caches[i].events;
 const finished=s.phase==='done';const difference=r.metrics.makespan-data.runs[1-i].metrics.makespan;const order=Math.abs(difference)<1e-8?'同时完成':difference<0?'先完成':'后完成';$('#row-'+i).classList.toggle('finished',finished);const container=$('#code-'+i);container.querySelectorAll('.code-line').forEach(el=>el.classList.toggle('active',s.source_lines.includes(Number(el.dataset.line))));
 const target=container.querySelector('.active');if(target&&(frame.changed[i]||target.offsetTop<container.scrollTop||target.offsetTop>container.scrollTop+container.clientHeight-24))container.scrollTop=target.offsetTop-25;
 $('#position-'+i).textContent=finished?'完成':`行 ${s.source_lines.join(', ')}`;
 $('#progress-'+i).textContent=finished?`${order} · T = ${fmt(r.metrics.makespan)}`:`完成 ${s.completed_count} / ${r.events.length}`;$('#progress-'+i).classList.toggle('done-label',finished);
 $('#variables-'+i).textContent=`started = ${s.started_count}　completed = ${s.completed_count}　occupied = ${s.occupied.length}`;
 const label=task?`${task.kind} · 微批 ${task.microbatch} · GPU ${task.stage}${task.peer==null?'':` → ${task.peer}`}`:'';
 const descriptions={initialize:'建立依赖图，等待启动',choose:'选中 '+label,start:'启动 '+label,complete:'完成 '+label,advance:'无其他可启动任务，推进到下一完成事件',done:`${order} · 已停在 ${fmt(r.metrics.makespan)}，本组不再执行任务`};
 $('#action-'+i).textContent=finished?descriptions.done:frame.changed[i]?descriptions[s.phase]:'本时刻无新动作，保留当前资源状态';
 $('#action-'+i).title=task?`任务 ${task.id}；依赖：${task.deps.join(', ')||'无'}；资源：${task.resources.join(', ')}`:'';
 const active=s.running.map(id=>r.tasks[id]);
 $('#gpus-'+i).innerHTML=Array.from({length:data.config.pp},(_,gpu)=>{
  const compute=active.find(t=>t.kind!=='COMM'&&t.stage===gpu),comm=active.find(t=>t.kind==='COMM'&&(t.stage===gpu||t.peer===gpu));
  function cell(t,kind){const pending=frame.changed[i]&&s.phase==='choose'&&task&&((kind==='compute'&&task.kind!=='COMM'&&task.stage===gpu)||(kind==='comm'&&task.kind==='COMM'&&(task.stage===gpu||task.peer===gpu)));if(!t)return `<div class="resource ${pending?'pending':''}" title="${kind==='compute'?'计算':'通信'}资源">${pending?'待启动 '+esc(task.id):finished?'已结束':kind==='compute'?'计算空闲':'通信空闲'}</div>`;const due=eventMap.get(t.id).finish<=frame.time+1e-8;return `<div class="resource busy ${t.kind.toLowerCase()} ${frame.changed[i]&&s.phase==='start'&&s.task===t.id?'fresh':''}" title="${esc(t.id)} ${fmt(eventMap.get(t.id).start)}—${fmt(eventMap.get(t.id).finish)}">${t.kind==='COMM'?`通信 ${t.stage}→${t.peer}`:t.kind} · 微批 ${t.microbatch}${due?' · 待释放':''}</div>`;}
  return `<div class="gpu-row"><span class="gpu-name">GPU ${gpu}</span>${cell(compute,'compute')}${cell(comm,'comm')}</div>`;
 }).join('');
 const started=new Set(),completed=new Set();for(let j=0;j<=frame.indices[i];j++){const step=r.steps[j];if(step.phase==='start')started.add(step.task);if(step.phase==='complete')completed.add(step.task);}drawHistory(i,r,started,completed,frame.time,frame.changed[i]?s.task:null);
}
function drawHistory(i,r,started,completed,time,selected){
 const width=720,left=43,row=23,height=10+data.config.pp*row+19,end=Math.max(...data.runs.map(x=>x.metrics.makespan)),scale=(width-left-10)/end,focus=$('#focus').value;
 let parts=[`<svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" role="img" aria-label="${titles[i]}任务时间轴" data-axis-end="${end}">`];
 for(let gpu=0;gpu<data.config.pp;gpu++)parts.push(`<text x="0" y="${gpu*row+21}" font-size="10">GPU ${gpu}</text><line x1="${left}" x2="${width-10}" y1="${gpu*row+28}" y2="${gpu*row+28}" stroke="#e2e8ef"/>`);
 for(let tick=0;tick<=4;tick++){const x=left+(width-left-10)*tick/4;parts.push(`<line x1="${x}" x2="${x}" y1="7" y2="${height-16}" stroke="#eef1f6"/><text x="${x}" y="${height-2}" text-anchor="${tick===0?'start':tick===4?'end':'middle'}" font-size="9">${fmt(end*tick/4)}</text>`);}
 for(const e of r.events){if(!started.has(e.id))continue;for(const gpu of e.kind==='COMM'?[e.stage,e.peer]:[e.stage]){const y=9+gpu*row+(e.kind==='COMM'?13:0),h=e.kind==='COMM'?5:11,opacity=focus==='all'||e.microbatch===Number(focus)?1:.15;parts.push(`<rect x="${left+e.start*scale}" y="${y}" width="${Math.max(.3,e.duration*scale-.3)}" height="${h}" fill="${completed.has(e.id)?colors[e.kind]:'white'}" stroke="${e.id===selected?'#b98416':colors[e.kind]}" stroke-width="${e.id===selected?1.8:1}" opacity="${opacity}"><title>${esc(e.id)} ${fmt(e.start)}—${fmt(e.finish)}</title></rect>`);}}
 if(completed.size===r.events.length){const x=left+r.metrics.makespan*scale;parts.push(`<line class="finish-marker" data-finish="${r.metrics.makespan}" x1="${x}" x2="${x}" y1="4" y2="${height-15}" stroke="#278468" stroke-width="2" stroke-dasharray="3 2"/><text x="${x-3}" y="11" text-anchor="end" font-size="10" fill="#176c51">完成 ${fmt(r.metrics.makespan)}</text>`);}
 const cursorTime=Math.min(time,r.metrics.makespan);
 parts.push(`<line class="shared-clock" data-time="${cursorTime}" x1="${left+cursorTime*scale}" x2="${left+cursorTime*scale}" y1="5" y2="${height-15}" stroke="${completed.size===r.events.length?'#278468':'#be3f50'}" stroke-width="1"/></svg>`);$('#history-'+i).innerHTML=parts.join('');
}
$('#end').onclick=()=>{if(!data)return;stop();index=frames.length-1;paint();};
$('#download').onclick=()=>{if(!data)return;const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'})),a=document.createElement('a');a.href=url;a.download=`comparison-${data.run_id}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
if(window.DEBUG_DATA){const payload=window.DEBUG_DATA;function loadOffline(){const overlap=$('#resources').value==='true';accept({config:{...payload.config,allow_compute_comm_overlap:overlap},runs:payload.groups[overlap?'overlap':'serial'],run_id:payload.run_id});}$('#pp').value=payload.config.pp;$('#mb').value=payload.config.microbatches;$('#comm').value=payload.config.comm;$('#case').value=payload.provenance.case;for(const id of ['case','pp','mb','comm'])$('#'+id).disabled=true;$('#resources').oninput=null;$('#resources').onchange=loadOffline;loadOffline();}
$('#fullscreen').onclick=async()=>{try{if(document.fullscreenElement)await document.exitFullscreen();else await document.documentElement.requestFullscreen();}catch(e){$('#status').textContent='可使用浏览器的全屏菜单。';}};document.addEventListener('fullscreenchange',()=>{$('#fullscreen').textContent=document.fullscreenElement?'退出全屏':'全屏';});
