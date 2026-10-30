/* Chart diagnostics have their own result. Photo input, selection and exports
 * continue to use the workbench's unchanged image evaluation. */
function createDiagnosticSampler(hooks){
  // BabelColor Average patch 22: neutral 5 (.70 D).
  let selected='cc22',serial=0,cached=null,pendingKey=null,pending=null,error='';
  const signature=recipe=>JSON.stringify(recipe);
  const get=()=>selected&&cached?.sampleId===selected&&cached.recipeKey===signature(hooks.getState().active)?cached.data:null;
  async function refresh(){
    const state=hooks.getState();if(!selected||!state.computable||state.visible===false)return;
    const recipe=JSON.parse(JSON.stringify(state.active)),recipeKey=signature(recipe),sampleId=selected,requestKey=recipeKey+'|'+sampleId;
    if(get())return;if(pendingKey===requestKey)return pending;
    const request=++serial;pendingKey=requestKey;error='';hooks.render();
    pending=(async()=>{
      try{
        const data=await hooks.api('/api/evaluate',{recipe,baseline:null,input:{id:'chart',exposure_ev:0},selection:{sample_id:sampleId}});
        if(request!==serial||selected!==sampleId||signature(hooks.getState().active)!==recipeKey)return;
        cached={recipeKey,sampleId,data};
      }catch(e){if(request===serial)error=e.message;}
      finally{if(request===serial){pendingKey=null;pending=null;hooks.render();}}
    })();
    return pending;
  }
  async function select(id){
    if(id!==null&&!hooks.getState().samples.some(s=>s.id===id))return;
    if(id===selected)return refresh();
    selected=id;serial++;cached=null;pendingKey=null;pending=null;error='';hooks.render();
    return refresh();
  }
  return {select,refresh,get,selected:()=>selected,status:()=>({pending:!!pendingKey,error})};
}
