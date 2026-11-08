import {loadPyodide} from './vendor/pyodide/pyodide.mjs';
let ready;
function runtime(){
 if(!ready)ready=(async()=>{
  const py=await loadPyodide({indexURL:new URL('./vendor/pyodide/',import.meta.url).href});
  py.FS.mkdirTree('/app/dualpipe_a');
  for(const path of ['dualpipe_a/__init__.py','dualpipe_a/simulator.py','debug_trace.py','browser_bridge.py']){
   const response=await fetch(new URL('./python/'+path,import.meta.url));
   if(!response.ok)throw Error('无法加载调度源码：'+path);
   py.FS.writeFile('/app/'+path,await response.text());
  }
  py.runPython("import sys\nsys.path.insert(0, '/app')\nfrom browser_bridge import execute_json");
  return py;
 })().catch(e=>{ready=null;throw e;});
 return ready;
}
let queue=Promise.resolve();
self.onmessage=({data})=>{
 queue=queue.then(async()=>{
  try{
   const py=await runtime();
   py.globals.set('_request_json',JSON.stringify({path:data.path,values:data.values}));
   const result=JSON.parse(py.runPython('execute_json(_request_json)'));
   self.postMessage({id:data.id,result});
  }catch(e){self.postMessage({id:data.id,error:String(e.message||e)});}
 });
};
