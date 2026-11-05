(() => {
  'use strict';
  const $=id=>document.getElementById(id), KEY='anatomy.stability-profiles.v1';
  let profiles=[],removed=null,version=0,storageOK=true;
  const status=text=>$('fp-status').textContent=text;
  const escape=text=>String(text).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  async function post(url,body){const r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const result=await r.json();if(r.status===404)throw new Error('Fingerprint service unavailable. Restart the Python server and refresh this page; your segment selection is valid.');if(!r.ok)throw new Error(typeof result.detail==='string'?result.detail:'Invalid or unsupported profile format.');return result;}
  function persist(next){if(!storageOK)throw new Error('Browser storage is unavailable or contains unreadable data. Export existing profiles before clearing site storage.');if(next.length>50)throw new Error('Library is limited to 50 profiles. Export and remove an old profile first.');localStorage.setItem(KEY,JSON.stringify(next));profiles=next;}
  function selectors(a,b){for(const id of ['fp-a','fp-b']){const select=$(id);select.replaceChildren();for(const p of profiles){const option=document.createElement('option');option.value=p.id;option.textContent=p.name+' · '+new Date(p.created_at).toLocaleString();select.append(option);}}$('fp-a').value=a || profiles[0]?.id || '';$('fp-b').value=b || profiles.at(-1)?.id || '';render();}
  function get(id){return profiles.find(p=>p.id===$(id).value);}
  function card(id,p,s){const node=$(id);node.replaceChildren();const title=document.createElement('h3');title.textContent=p.name;node.append(title);for(const text of [`Captured displacement: ${(p.captured_offset_mm||0)>=0?'+':''}${(p.captured_offset_mm||0).toFixed(1)} mm`,`${p.source==='synthetic'?'Synthetic demo':'Imported scan'} · ${new Date(p.created_at).toLocaleString()}`,`Baseline ${s.baseline_ml.toFixed(3)} mL · ${p.spacing_mm.map(x=>x.toFixed(2)).join(' × ')} mm voxels`,`${p.region_count} regions · ${p.small_region_count} with fewer than 50 voxels`,`±2 mm span ${s.fixed[1].span_pct.toFixed(2)}% · gain−loss asymmetry ${s.fixed[1].asymmetry_pp.toFixed(2)} pp`]){const line=document.createElement('p');line.textContent=text;node.append(line);}}
  const layout=(title,extra={})=>({title:{text:title,font:{size:14}},paper_bgcolor:'#1A1953',plot_bgcolor:'#1A1953',font:{color:'#c2c8ec',size:11},margin:{l:65,r:25,t:45,b:50},...extra});
  const config={responsive:true,displaylogo:false};
  async function render(){const token=++version,a=get('fp-a'),b=get('fp-b');for(const id of ['fp-export-a','fp-export-b','fp-remove'])$(id).disabled=!a||!b;
    for(const id of ['fp-curves','fp-heatmap','fp-regions','fp-delta'])Plotly.purge($(id));$('fp-card-a').replaceChildren();$('fp-card-b').replaceChildren();
    if(!a||!b){$('fp-compatibility').textContent='Save a profile to begin. Save another after editing to compare snapshots.';return;}
    $('fp-compatibility').textContent='Checking profiles…';
    try{const result=await post('/api/fingerprints/compare',{a,b});if(token!==version)return;
      $('fp-compatibility').textContent=(result.same_mask?'Identical mask snapshots. ':result.same_scan?'Same scan and voxel grid. ':'Different scan or grid. ')+result.warnings.join(' ');
      card('fp-card-a',a,result.a);card('fp-card-b',b,result.b);
      const colors=['#8da3ff','#53d9bd'], ps=[a,b],ss=[result.a,result.b],x=a.curve.map(p=>p.offset_mm);
      Plotly.react($('fp-curves'),ps.map((p,i)=>({x,y:ss[i].changes_pct,name:(i?'B · ':'A · ')+escape(p.name),type:'scatter',mode:'lines+markers',line:{color:colors[i],shape:'hv'},hovertemplate:'%{x} mm: %{y:.2f}%<extra>%{fullData.name}</extra>'})),layout('Boundary response · relative to each baseline',{xaxis:{title:'Boundary offset (mm)'},yaxis:{title:'Volume change (%)'},legend:{orientation:'h',y:-.3},margin:{l:65,r:25,t:55,b:90}}),config);
      const rows=ss.map(s=>s.fixed.flatMap(f=>[f.loss_pct,f.gain_pct]));
      Plotly.react($('fp-heatmap'),[{type:'heatmap',z:rows,x:['−1 mm loss','+1 mm gain','−2 mm loss','+2 mm gain','−3 mm loss','+3 mm gain'],y:['A','B'],zmin:0,zmax:Math.max(1,...rows.flat()),colorscale:[[0,'#181b48'],[.5,'#6279f2'],[1,'#53d9bd']],colorbar:{title:'%'},hovertemplate:'%{y} · %{x}: %{z:.2f}%<extra></extra>'}],layout('Sensitivity at fixed offsets',{margin:{l:35,r:55,t:45,b:85}}),config);
      Plotly.react($('fp-regions'),ps.map((p,i)=>({type:'bar',x:['0–<20%','20–<40%','40–<60%','60–<80%','80–100%'],y:p.regional_volume_pct,name:i?'B':'A',marker:{color:colors[i]},hovertemplate:'%{x} regional loss<br>%{y:.2f}% of baseline volume<extra>%{fullData.name}</extra>'})),layout('Regional loss distribution at −2 mm',{barmode:'group',yaxis:{title:'Baseline volume (%)',range:[0,100]},xaxis:{title:'Regional erosion loss'}}),config);
      Plotly.react($('fp-delta'),[{type:'scatter',x,y:result.delta_pp,mode:'lines+markers',line:{color:'#f0c478',shape:'hv'},fill:'tozeroy',hovertemplate:'%{x} mm: %{y:.2f} pp<extra>B − A</extra>'}],layout('Difference in normalized response · B − A',{xaxis:{title:'Boundary offset (mm)'},yaxis:{title:'Percentage points',zeroline:true}}),config);
    }catch(error){if(token===version)$('fp-compatibility').textContent=error.message;}}
  function download(id){const p=get(id);if(!p)return;const url=URL.createObjectURL(new Blob([JSON.stringify(p,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='stability-profile-'+p.id+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
  window.addEventListener('load',async()=>{
    try{const saved=JSON.parse(localStorage.getItem(KEY)||'[]');if(!Array.isArray(saved)||saved.length>50)throw new Error('Invalid library');profiles=await Promise.all(saved.map(p=>post('/api/fingerprints/validate',p)));selectors();}
    catch(error){storageOK=false;status('Saved library could not be loaded: '+error.message+'. Existing browser data has been preserved.');}
    function current(){const selected=document.querySelector('#organ-list .active');const offset=Number($('offset').value);$('fp-current').textContent=selected?`Capture source: ${selected.querySelector("span").textContent.trim()} · ${offset>=0?'+':''}${offset.toFixed(1)} mm. The captured mask becomes the new zero-offset baseline.`:'Select or create a segment first.';}
    document.addEventListener('anatomy-selection',current);$('offset').addEventListener('input',current);current();
    async function capture(update){
      const organ=document.querySelector('#organ-list .active')?.dataset.organ,name=$('fp-name').value.trim(),offset=Number($('offset').value),target=update?get('fp-b'):null;
      if(!organ||!name){status('Select a segment and enter a profile name.');return;}if(update&&!target){status('Choose profile B to update.');return;}
      $('fp-save').disabled=true;$('fp-update').disabled=true;
      status(`Capturing mask at ${offset>=0?'+':''}${offset.toFixed(1)} mm…`);
      try{const p=await post('/api/fingerprints',{organ,name,offset});const reference=$('fp-a').value;
        if(update){p.id=target.id;persist(profiles.map(x=>x.id===target.id?p:x));removed=target;$('fp-undo').disabled=false;status('Profile B updated. Undo library change restores its previous version.');}
        else{persist([...profiles,p]);status('Saved displaced-mask snapshot. Later edits do not change it.');}
        selectors(reference,p.id);
      }catch(error){status(error.message);}finally{$('fp-save').disabled=false;$('fp-update').disabled=false;}
    }
    $('fp-save').onclick=()=>capture(false);$('fp-update').onclick=()=>capture(true);
    $('fp-a').onchange=render;$('fp-b').onchange=render;
    $('fp-export-a').onclick=()=>download('fp-a');$('fp-export-b').onclick=()=>download('fp-b');
    $('fp-remove').onclick=()=>{const p=get('fp-b');if(!p)return;try{persist(profiles.filter(x=>x.id!==p.id));removed=p;$('fp-undo').disabled=false;selectors();status('Profile removed from this browser. Undo is available until this page closes.');}catch(error){status(error.message);}};
    $('fp-undo').onclick=()=>{if(!removed)return;try{persist([...profiles.filter(p=>p.id!==removed.id),removed]);selectors(null,removed.id);removed=null;$('fp-undo').disabled=true;status('Previous profile restored to your library.');}catch(error){status(error.message);}};
    $('fp-import').onchange=async e=>{const file=e.target.files[0];if(!file)return;try{if(file.size>1000000)throw new Error('Profile JSON must be smaller than 1 MB.');const p=await post('/api/fingerprints/validate',JSON.parse(await file.text()));if(profiles.some(x=>x.id===p.id))throw new Error('That profile is already in your library.');persist([...profiles,p]);selectors($('fp-a').value,p.id);status('Imported profile. Imported measurements are not independently verified against source masks.');}catch(error){status(error.message);}finally{e.target.value='';}};
  });
})();
