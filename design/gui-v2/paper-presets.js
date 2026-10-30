/* Paper snapshots are independent of negative material and positive rendering. */
function paperChoice(recipe){
 const custom=recipe.printing?.custom_material;
 return custom?(custom.provenance?.stock_id||'custom-paper'):'Ultra Endura';
}
function replacePaperMaterial(recipe,id,material){
 if(recipe.route!=='print')throw Error('只有光学放大使用相纸。');
 if(id==='Ultra Endura'){recipe.printing.paper=id;delete recipe.printing.custom_material;return;}
 if(material?.provenance?.process!=='RA-4'||material.provenance.density_metric!=='Status A'||material.provenance.stock_id!==id)throw Error('相纸材料身份不匹配。');
 recipe.printing.paper=id;recipe.printing.custom_material=JSON.parse(JSON.stringify(material));
}
