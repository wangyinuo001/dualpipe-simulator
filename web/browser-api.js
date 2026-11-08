// GitHub Pages has no Python server: execute the same source in a Web Worker.
(() => {
 const nativeFetch=window.fetch.bind(window),base=new URL('.',document.currentScript.src);
 let worker=null,sequence=0;
 const pending=new Map();
 function request(path,values){
  if(!worker){
   worker=new Worker(new URL('python-worker.mjs',base),{type:'module'});
   worker.onmessage=({data})=>{const p=pending.get(data.id);if(p){pending.delete(data.id);p.resolve(data);}};
   worker.onerror=()=>{for(const p of pending.values())p.reject(Error('运行环境加载失败，请检查网络后重试。'));pending.clear();worker.terminate();worker=null;};
  }
  return new Promise((resolve,reject)=>{const id=++sequence;pending.set(id,{resolve,reject});worker.postMessage({id,path,values});});
 }
 window.fetch=async(input,options={})=>{
  const path=typeof input==='string'?input:'';
  if(!['/api/debug','/api/run','/api/source'].includes(path))return nativeFetch(input,options);
  if(path==='/api/source'){
   const response=await nativeFetch(new URL('python/dualpipe_a/simulator.py',base));
   if(!response.ok)return response;
   return new Response(JSON.stringify({source:await response.text()}),{headers:{'Content-Type':'application/json'}});
  }
  const status=document.querySelector('#status');if(status&&!worker)status.textContent='首次加载运行环境，随后开始计算…';
  const result=await request(path,JSON.parse(options.body||'{}'));
  return new Response(JSON.stringify(result.error?{error:result.error}:result.result),{status:result.error?400:200,headers:{'Content-Type':'application/json'}});
 };
})();
