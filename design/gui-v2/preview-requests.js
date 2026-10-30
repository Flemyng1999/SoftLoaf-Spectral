/* Keep one frame in flight and one newest pending request. The caller owns
 * generation checks, so project/input changes never present an obsolete frame. */
function createLatestPreviewTask(run){
 let pending=null,worker=null;
 async function drain(){
  let result;
  try{while(pending!==null){const next=pending;pending=null;result=await run(next);}return result;}
  finally{worker=null;}
 }
 return {submit(value){pending=value;if(!worker)worker=drain();return worker;},busy:()=>!!worker};
}
