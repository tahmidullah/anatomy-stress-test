(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const state = { meta: null, organ: null, offset: 0, i: 0, j: 0, k: 0,
                  curve: null, renderToken: 0, renderTimer: null, organToken: 0 };
  const err = text => { const t=$('toast'); t.textContent=text; t.style.display='block'; clearTimeout(err.timeout);err.timeout=setTimeout(()=>t.style.display='none',6500);console.error(text); };
  const fetchJSON = async url => { const response=await fetch(url); if(!response.ok) { const text=await response.text();throw new Error(`Request failed (${response.status}): ${text.slice(0,200)}`); }return response.json(); };
  const fmt = (value, decimal=1) => Number(value).toLocaleString('en-US',{minimumFractionDigits:decimal,maximumFractionDigits:decimal});
  const signed = value => `${value>=0?'+':''}${Number(value).toFixed(1)} mm`;
  const params = vars => new URLSearchParams(vars).toString();

  function setOrganButtons() {
    $('organ-list').innerHTML = '';
    for (const item of state.meta.structures) {
      const b=document.createElement('button');b.className='organ-button'+(item.name===state.organ?' active':'');
      b.dataset.organ=item.name;b.type='button';b.innerHTML=`<i class="organ-color" style="background:${item.color}"></i><span></span><span class="organ-arrow">›</span>`;
      b.querySelector('span').textContent=item.label;
      b.addEventListener('click',()=>selectOrgan(item.name));$('organ-list').appendChild(b);
    }
  }
  function updateSliceControls() {
    for (const [axis,key] of [['i','slice-i'],['j','slice-j'],['k','slice-k']]) $(key).value=state[axis];
    $('axial-number').textContent=`SLICE ${state.k+1} / ${state.meta.shape[2]}`;
    $('coronal-number').textContent=`SLICE ${state.j+1} / ${state.meta.shape[1]}`;
    $('sagittal-number').textContent=`SLICE ${state.i+1} / ${state.meta.shape[0]}`;
  }
  function updateMetrics(data) {
    document.dispatchEvent(new Event('anatomy-selection'));
    $('m-baseline').textContent=fmt(data.baseline_ml,2)+' mL';
    $('m-current').textContent=fmt(data.current_ml,2)+' mL';
    $('offset').disabled=data.empty || $('edit-mode').value!=='navigate';
    $('m-delta').textContent=(data.delta_pct>=0?'+':'')+fmt(data.delta_pct,2)+'%';
    if(data.empty)$('m-delta').textContent='—';
    $('m-delta').classList.toggle('negative',data.delta_pct<0);
    $('m-voxels').textContent=fmt(data.voxels,0);
    $('offset-value').textContent=signed(state.offset);
    const desc=state.offset===0 ? 'The original segmentation is unchanged.' :
      `${Math.abs(state.offset).toFixed(1)} mm ${state.offset>0?'outward':'inward'} boundary perturbation changes the measured mask volume by ${data.delta_pct>=0?'+':''}${data.delta_pct.toFixed(2)}%.`;
    $('insight-detail').textContent=data.empty?'Empty segment: paint on a CT slice to define its mask.':desc;
    if(data.touches_fov) $('warning-box').textContent='This mask reaches a scan boundary: apparent organ volume may be truncated by the field of view.';
    else $('warning-box').textContent=state.meta.source==='synthetic'
      ? 'Synthetic demo data does not represent an actual clinical CT scan.'
      : 'Measurements depend on the supplied segmentation and voxel sampling. This experiment does not estimate true segmentation uncertainty.';
  }
  function plotScene(result) {
    const traces=result.traces.map(t=>({
      type:'mesh3d',x:t.mesh.x,y:t.mesh.y,z:t.mesh.z,i:t.mesh.i,j:t.mesh.j,k:t.mesh.k,
      name:t.name,color:t.color,opacity:t.opacity,flatshading:false,hoverinfo:'name',lighting:{ambient:.68,diffuse:.65,roughness:.72,specular:.2},
      lightposition:{x:120,y:180,z:240},showscale:false
    }));
    const layout={
      paper_bgcolor:'#080616',plot_bgcolor:'#080616',showlegend:false,
      margin:{l:0,r:0,t:0,b:0},uirevision:'constant-camera',
      scene:{bgcolor:'#080616',aspectmode:'data',
        xaxis:{visible:false,title:'R-L'},yaxis:{visible:false,title:'A-P'},zaxis:{visible:false,title:'S-I'},
        camera:{eye:{x:1.65,y:1.55,z:1.02}},dragmode:'orbit'},
      annotations:[{text:'RAS+ PHYSICAL COORDINATES · mm',x:.01,y:.03,xref:'paper',yref:'paper',showarrow:false,font:{size:10,color:'#c5c9f1'}}]
    };
    Plotly.react($('mesh-plot'),traces,layout,{responsive:true,displaylogo:false,displayModeBar:false,scrollZoom:true});
  }
  function plotCurve() {
    if(!state.curve) return;
    const pts=state.curve.points;
    const x=pts.map(p=>p.offset_mm), y=pts.map(p=>p.current_ml);
    const base=pts.find(p=>p.offset_mm===0).baseline_ml;
    const active=pts.find(p=>p.offset_mm===state.offset);
    const traces=[
      {type:'scatter',mode:'lines+markers',x,y,line:{color:'#8da3ff',width:3},marker:{size:6,color:'#8da3ff'},name:'Perturbed mask',hovertemplate:'Offset %{x:.1f} mm<br>Volume %{y:.2f} mL<extra></extra>'},
      {type:'scatter',mode:'markers',x:[active.offset_mm],y:[active.current_ml],marker:{size:12,color:'#e0c6ff',line:{color:'#fff4ff',width:2}},showlegend:false,hoverinfo:'skip'}
    ];
    const layout={
      paper_bgcolor:'#080616',plot_bgcolor:'#080616',showlegend:false,
      margin:{l:65,r:25,t:15,b:48},
      font:{color:'#c2c8ec',size:11},
      xaxis:{title:{text:'Boundary offset (mm)',font:{size:11}},range:[-3.3,3.3],dtick:1,gridcolor:'#373a79',zerolinecolor:'#5a63ab'},
      yaxis:{title:{text:'Segmented volume (mL)',font:{size:11}},gridcolor:'#373a79',zeroline:false,tickformat:',.1f'},
      shapes:[{type:'line',x0:-3.3,x1:3.3,y0:base,y1:base,line:{color:'#e0c6ff',dash:'dot',width:1.5}},
        {type:'line',x0:state.offset,x1:state.offset,y0:0,y1:1,yref:'paper',line:{color:'#8195fa',dash:'dot',width:1}}]
    };
    Plotly.react($('curve-plot'),traces,layout,{responsive:true,displayModeBar:false,displaylogo:false});
  }
  async function updateViews({includeScene=true}={}) {
    if(!state.organ)return;
    const token=++state.renderToken, {organ,offset,i,j,k}=state;
    updateSliceControls();
    const metricsP=fetchJSON('/api/metrics?'+params({organ,offset}));
    const sceneP=includeScene?fetchJSON('/api/scene?'+params({organ,offset})):Promise.resolve(null);
    const views=[['axial','axial-image',k],['coronal','coronal-image',j],['sagittal','sagittal-image',i]];
    const imagesP=Promise.all(views.map(async([axis,element,index])=>{
      const url='/api/slice?'+params({organ,axis,index,offset,i,j,k,level:$('window-level').value,width:$('window-width').value,overlay:$('show-overlay').checked,crosshair:$('show-crosshair').checked});
      const response=await fetch(url);if(!response.ok)throw new Error(`Slice request failed: ${axis}`);
      return [element,URL.createObjectURL(await response.blob())];
    }));
    try {
      const [metrics,scene,images]=await Promise.all([metricsP,sceneP,imagesP]);
      if(token!==state.renderToken) {for(const [,url] of images)URL.revokeObjectURL(url);return;}
      updateMetrics(metrics);if(scene)plotScene(scene);
      for(const [id,url] of images){const img=$(id);const old=img.dataset.objectUrl;img.src=url;img.dataset.objectUrl=url;if(old)URL.revokeObjectURL(old);}
      plotCurve();
    }catch(e){if(token===state.renderToken)err(e.message);}
  }
  async function selectOrgan(name) {
    if(state.organ===name && state.curve)return;
    const version=++state.organToken;
    $('organ-label').value=state.meta.structures.find(s=>s.name===name)?.label || name;
    invalidateFragility();
    state.organ=name;state.offset=0;$('offset').value=0;state.curve=null;
    ++state.renderToken;
    setOrganButtons();document.dispatchEvent(new Event('anatomy-selection'));$('mesh-title').textContent=$('organ-label').value;
    try {
      const [measure,curve]=await Promise.all([
        fetchJSON('/api/metrics?'+params({organ:name,offset:0})),
        fetchJSON('/api/curve?'+params({organ:name}))
      ]);
      if(version!==state.organToken)return;
      state.curve=curve;[state.i,state.j,state.k]=measure.centroid_ijk;
      await updateViews();
    }catch(e){if(version===state.organToken)err(e.message);}
  }
  function updateCrosshairFromClick(event,axis){
    if(editBusy || $('edit-mode').value!=='navigate')return;
    const img=event.currentTarget,rect=img.getBoundingClientRect(),naturalWidth=img.naturalWidth,naturalHeight=img.naturalHeight;
    if(!naturalWidth||!naturalHeight)return;
    const x=Math.floor((event.clientX-rect.left)*naturalWidth/rect.width),y=Math.floor((event.clientY-rect.top)*naturalHeight/rect.height);
    if(x<0||y<0||x>=naturalWidth||y>=naturalHeight)return;
    const [ni,nj,nk]=state.meta.shape;
    if(axis==='axial'){state.i=ni-1-x;state.j=nj-1-y;}
    if(axis==='coronal'){state.i=ni-1-x;state.k=nk-1-y;}
    if(axis==='sagittal'){state.j=nj-1-x;state.k=nk-1-y;}
    updateViews({includeScene:false});
  }
  function downloadCSV(){
    if(!state.curve)return;
    const lines=['organ,offset_mm,volume_ml,baseline_ml,delta_ml,delta_pct,voxel_count'];
    for(const p of state.curve.points){lines.push([state.organ,p.offset_mm,p.current_ml,p.baseline_ml,p.delta_ml,p.delta_pct,p.voxels].join(','));}
    const blob=new Blob([lines.join('\n')+'\n'],{type:'text/csv;charset=utf-8'});
    const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=`anatomy_stress_test_${state.organ}.csv`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  let fragilityVersion=0, fragilityReady=false;
  function invalidateFragility(){
    ++fragilityVersion;fragilityReady=false;
    $('fragility-export').disabled=true;$('fragility-run').disabled=false;
    $('fragility-status').textContent='Select displacement, then build the map for the selected organ.';
    $('fragility-regions').replaceChildren();$('fragility-organs').replaceChildren();
    Plotly.purge($('fragility-plot'));
  }
  function makeTable(target, headers, rows){
    const table=document.createElement('table'), head=document.createElement('tr');
    headers.forEach(text=>{const th=document.createElement('th');th.textContent=text;head.appendChild(th);});table.appendChild(head);
    rows.forEach(values=>{const tr=document.createElement('tr');values.forEach(text=>{const td=document.createElement('td');td.textContent=text;tr.appendChild(td);});table.appendChild(tr);});
    $(target).replaceChildren(table);
  }
  async function buildFragility(){
    if(!state.organ)return;
    const version=++fragilityVersion, organ=state.organ, distance=Number($('fragility-distance').value);
    fragilityReady=false;$('fragility-run').disabled=true;$('fragility-export').disabled=true;
    $('fragility-status').textContent='Computing full-resolution regional and organ measurements…';
    try{
      const [result,comparison]=await Promise.all([fetchJSON('/api/fragility?'+params({organ,distance})),fetchJSON('/api/fragility/organs?'+params({distance}))]);
      if(version!==fragilityVersion)return;
      const m=result.mesh;
      await Plotly.react($('fragility-plot'),[{type:'mesh3d',x:m.x,y:m.y,z:m.z,i:m.i,j:m.j,k:m.k,intensity:m.intensity,cmin:0,cmax:100,colorscale:[[0,'#3264d9'],[.5,'#f5d76e'],[1,'#e74b4b']],colorbar:{title:'Loss %'},hovertemplate:'Regional loss: %{intensity:.1f}%<extra></extra>'}],{paper_bgcolor:'#1A1953',font:{color:'#c2c8ec'},margin:{l:0,r:0,t:10,b:0},scene:{aspectmode:'data',xaxis:{title:'R (mm)'},yaxis:{title:'A (mm)'},zaxis:{title:'S (mm)'}}},{responsive:true,displaylogo:false});
      if(version!==fragilityVersion)return;
      const regions=[...result.regions].sort((a,b)=>Number(a.small_sample)-Number(b.small_sample) || b.loss_pct-a.loss_pct || b.lost_ml-a.lost_ml).slice(0,20);
      makeTable('fragility-regions',['Grid cell','Loss %','Lost mL','Baseline voxels'],regions.map(r=>[r.cell.join(', '),fmt(r.loss_pct),fmt(r.lost_ml,3),`${r.baseline_voxels}${r.small_sample?' · small sample':''}`]));
      makeTable('fragility-organs',['Organ','Loss %','Gain %','Span %'],comparison.organs.map(r=>r.error?[r.organ,r.error,'—','—']:[r.organ.replaceAll('_',' ')+(r.touches_fov?' · scan edge':'')+(r.below_voxel_spacing?' · below spacing':''),fmt(r.loss_pct),fmt(r.gain_pct),fmt(r.span_pct)]));
      $('fragility-status').textContent=`${organ.replaceAll('_',' ')} · ${distance} mm inward shift · ${fmt(result.summary.loss_pct)}% whole-organ loss · ${result.regions.length} regions${result.summary.touches_fov?' · Mask touches scan boundary':''}${result.summary.below_voxel_spacing?' · Displacement is smaller than every voxel axis':''}.`;
      fragilityReady=true;$('fragility-export').disabled=false;
    }catch(error){if(version===fragilityVersion)$('fragility-status').textContent=error.message;}
    finally{if(version===fragilityVersion)$('fragility-run').disabled=false;}
  }
  let editBusy=false;
  async function editSegment(payload,keepPosition=false){
    if(editBusy)return;
    editBusy=true;document.querySelectorAll('.segment-edit button').forEach(b=>b.disabled=true);
    const position=[state.i,state.j,state.k];
    $('edit-status').textContent='Applying segment edit…';
    ++state.renderToken;++state.organToken;invalidateFragility();
    try{
      const response=await fetch('/api/segments',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
      const result=await response.json();if(!response.ok)throw new Error(typeof result.detail==='string'?result.detail:'Invalid segment edit.');
      state.meta=await fetchJSON('/api/meta');$('structure-count').textContent=String(state.meta.structures.length).padStart(2,'0');
      state.organ=null;state.curve=null;
      if(result.organ)await selectOrgan(result.organ);
      else {
        setOrganButtons();$('organ-label').value='';$('mesh-title').textContent='No segment selected';
        for(const id of ['m-baseline','m-current','m-delta','m-voxels'])$(id).textContent='—';
        for(const id of ['mesh-plot','curve-plot'])Plotly.purge($(id));
        for(const axis of ['axial','coronal','sagittal'])$(axis+'-image').removeAttribute('src');
        $('offset').disabled=true;document.dispatchEvent(new Event('anatomy-selection'));
      }
      if(keepPosition){[state.i,state.j,state.k]=position;await updateViews();}
      $('edit-status').textContent=payload.operation==='delete'?'Segment deleted. Restore deleted recovers the most recent deletion. Saved fingerprints remain in your library.':'Saved in this session. Download the mask to keep your edits.';
    }catch(error){$('edit-status').textContent=error.message;}
    finally{editBusy=false;document.querySelectorAll('.segment-edit button').forEach(b=>b.disabled=false);}
  }
  function bindEditing(){
    $('segment-delete').onclick=()=>editSegment({operation:'delete',organ:state.organ});
    $('segment-restore').onclick=()=>editSegment({operation:'restore'});
    $('segment-new').onclick=()=>editSegment({operation:'create',label:$('organ-label').value});
    $('segment-copy').onclick=()=>editSegment({operation:'duplicate',organ:state.organ,label:$('organ-label').value+' copy'});
    $('segment-rename').onclick=()=>editSegment({operation:'rename',organ:state.organ,label:$('organ-label').value},true);
    $('segment-undo').onclick=()=>editSegment({operation:'undo',organ:state.organ},true);
    $('edit-mode').onchange=()=>{state.offset=0;$('offset').value=0;$('offset').disabled=$('edit-mode').value!=='navigate';updateViews();};
    for(const axis of ['axial','coronal','sagittal']){
      const img=$(axis+'-image');let stroke=null;
      function point(e){const r=img.getBoundingClientRect();const x=Math.max(0,Math.min(img.naturalWidth-1,Math.floor((e.clientX-r.left)*img.naturalWidth/r.width))), y=Math.max(0,Math.min(img.naturalHeight-1,Math.floor((e.clientY-r.top)*img.naturalHeight/r.height)));return [img.naturalWidth-1-x,img.naturalHeight-1-y];}
      img.addEventListener('dragstart',e=>e.preventDefault());
      img.addEventListener('pointerdown',e=>{
        if(e.button!==0 || editBusy || !state.organ || $('edit-mode').value==='navigate')return;
        e.preventDefault();img.setPointerCapture(e.pointerId);
        stroke={operation:'stroke',organ:state.organ,axis,index:state[{axial:'k',coronal:'j',sagittal:'i'}[axis]],points:[point(e)],radius_mm:Number($('brush-radius').value),erase:$('edit-mode').value==='erase'};
        img.classList.add('painting');$('edit-status').textContent='Drawing stroke… release to apply.';
      });
      img.addEventListener('pointermove',e=>{if(stroke && stroke.points.length<2000)stroke.points.push(point(e));});
      img.addEventListener('pointerup',e=>{if(!stroke)return;if(stroke.points.length<2000)stroke.points.push(point(e));const payload=stroke;stroke=null;img.classList.remove('painting');editSegment(payload,true);});
      img.addEventListener('pointercancel',()=>{stroke=null;img.classList.remove('painting');$('edit-status').textContent='Stroke cancelled.';});
    }
  }
  function bindControls(){
    bindEditing();
    $('fragility-run').addEventListener('click',buildFragility);
    $('fragility-distance').addEventListener('change',invalidateFragility);
    $('fragility-export').addEventListener('click',async()=>{
      if(!fragilityReady)return;
      const button=$('fragility-export');button.disabled=true;
      try{
        const response=await fetch('/api/fragility/export?'+params({organ:state.organ,distance:$('fragility-distance').value}));
        if(!response.ok)throw new Error('Map export failed.');
        const url=URL.createObjectURL(await response.blob()), a=document.createElement('a');a.href=url;a.download='anatomical_fragility.zip';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
      }catch(error){err(error.message);}finally{button.disabled=!fragilityReady;}
    });
    for(const id of ['ct-files','ct-folder']) $(id).addEventListener('change',()=>{
      $(id==='ct-files'?'ct-folder':'ct-files').value='';
      $('series-field').hidden=true;$('series-select').replaceChildren();
    });
    $('import-form').addEventListener('submit',async e=>{
      e.preventDefault();
      const scans=$('ct-folder').files.length ? $('ct-folder').files : $('ct-files').files;
      if(!scans.length){$('import-status').textContent='Choose a CT volume, ZIP, or folder first.';return;}
      const form=new FormData();
      for(const file of scans)form.append('ct',file);
      for(const file of $('mask-files').files)form.append('mask',file);
      if(!$('series-field').hidden)form.append('series_uid',$('series-select').value);
      $('import-btn').disabled=true;$('import-status').textContent='Loading and checking alignment…';
      try {
        const response=await fetch('/api/import',{method:'POST',body:form});
        const result=await response.json();
        if(!response.ok)throw new Error(result.detail || 'Import failed');
        if(result.series){
          $('series-select').replaceChildren();
          result.series.forEach((s,i)=>{const option=document.createElement('option');option.value=s.uid;option.textContent=`Series ${i+1} · ${s.slices} slices · ${s.uid}`;$('series-select').appendChild(option);});
          $('series-field').hidden=false;$('import-status').textContent='Choose a DICOM series, then click Load again.';return;
        }
        state.organ=null;state.curve=null;++state.organToken;++state.renderToken;
        await init();
        $('import-status').textContent='Loaded. Select an organ and inspect its overlay before running the experiment.';
      }catch(error){$('import-status').textContent=error.message;}
      finally{$('import-btn').disabled=false;}
    });
    $('bundle-btn').addEventListener('click',async()=>{
      if(!state.organ)return;
      $('bundle-btn').disabled=true;
      try {
        const response=await fetch('/api/export?'+params({organ:state.organ,offset:state.offset,label:$('organ-label').value}));
        if(!response.ok)throw new Error('Export failed. Try again after loading the organ.');
        const url=URL.createObjectURL(await response.blob());const a=document.createElement('a');a.href=url;a.download='anatomy_stress_test.zip';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
      }catch(error){err(error.message);}finally{$('bundle-btn').disabled=false;}
    });
    $('offset').addEventListener('input', e=>{
      state.offset=Number(e.target.value);$('offset-value').textContent=signed(state.offset);
      clearTimeout(state.renderTimer);state.renderTimer=setTimeout(()=>updateViews(),160);
    });
    for(const [id,key] of [['slice-i','i'],['slice-j','j'],['slice-k','k']]) {
      $(id).addEventListener('input',e=>{state[key]=Number(e.target.value);clearTimeout(state.renderTimer);state.renderTimer=setTimeout(()=>updateViews({includeScene:false}),65);});
    }
    for(const axis of ['axial','coronal','sagittal']) {
      const image = $(axis+'-image');
      image.addEventListener('click',e=>updateCrosshairFromClick(e,axis));
      const frame = image.closest('.scan-frame');
      const key = {axial:'k',coronal:'j',sagittal:'i'}[axis];
      const dimension = {i:0,j:1,k:2}[key];
      const move = amount => {
        if(!state.meta || !state.organ) return;
        const next = Math.max(0,Math.min(state.meta.shape[dimension]-1,state[key]+amount));
        if(next === state[key]) return;
        state[key] = next;
        updateSliceControls();
        clearTimeout(state.renderTimer);
        state.renderTimer = setTimeout(()=>updateViews({includeScene:false}),55);
      };
      frame.addEventListener('wheel',e=>{
        // Capture the wheel only inside a CT view, preserving 3D zoom elsewhere.
        e.preventDefault();
        if(e.deltaY !== 0) move(Math.sign(e.deltaY)*(e.shiftKey?5:1));
      },{passive:false});
      frame.addEventListener('keydown',e=>{
        if(e.key==='ArrowUp'||e.key==='ArrowRight'||e.key==='ArrowDown'||e.key==='ArrowLeft') {
          e.preventDefault();
          const direction = e.key==='ArrowUp'||e.key==='ArrowRight'?1:-1;
          move(direction*(e.shiftKey?5:1));
        }
      });
    }
    $('reset-btn').addEventListener('click',async()=>{
      state.offset=0;$('offset').value=0;
      try{const result=await fetchJSON('/api/metrics?'+params({organ:state.organ,offset:0}));[state.i,state.j,state.k]=result.centroid_ijk;await updateViews();}
      catch(e){err(e.message);}
    });
    $('export-btn').addEventListener('click',downloadCSV);
  }
  function fitSlices(){
    if(!state.meta)return;
    for(const [axis,a,b] of [['axial',0,1],['coronal',0,2],['sagittal',1,2]]){
      const img=$(axis+'-image'), frame=img.closest('.scan-frame');
      const ratio=state.meta.shape[a]*state.meta.spacing_mm[a]/(state.meta.shape[b]*state.meta.spacing_mm[b]);
      const w=Math.min(frame.clientWidth,frame.clientHeight*ratio);
      img.style.width=w+'px';img.style.height=w/ratio+'px';
    }
  }
  function setupWorkstation(){
    const sidebar=document.querySelector('.sidebar'), content=document.querySelector('.content');
    sidebar.querySelector('.brand').innerHTML='<strong>Anatomy Stress Test</strong><small>CT segmentation workspace</small>';
    sidebar.querySelectorAll('h1,.intro,.eyebrow,.sidebar-divider').forEach(el=>el.remove());
    function section(title,node,open=true){const d=document.createElement('details');d.open=open;const summary=document.createElement('summary');summary.textContent=title;d.append(summary,node);sidebar.append(d);return d;}
    const source=sidebar.querySelector('.sidebar-bottom');
    const imports=document.querySelector('.import-panel');section('Load scan and masks',imports,false).id='load-section';
    const segments=document.createElement('div');segments.append(sidebar.querySelector('.sidebar-heading'),$('organ-list'));
    const label=$('organ-label').closest('label');segments.append(label);
    const edit=document.createElement('div');edit.className='segment-edit';
    edit.innerHTML='<div class="segment-actions"><button id="segment-new" type="button">New empty</button><button id="segment-copy" type="button">Duplicate</button><button id="segment-rename" type="button">Rename</button><button id="segment-undo" type="button">Undo stroke</button><button id="segment-delete" type="button">Delete segment</button><button id="segment-restore" type="button">Restore deleted</button></div><label>Slice tool<select id="edit-mode"><option value="navigate">Navigate</option><option value="paint">Paint</option><option value="erase">Erase</option></select></label><label>Brush radius (mm)<input id="brush-radius" type="number" min="0.5" max="30" step="0.5" value="3"></label><p id="edit-status" role="status">Name a new segment above, or select an uploaded segment to edit. Paint/erase affects only the displayed slice.</p>';
    segments.append(edit);section('Segments',segments);
    section('Boundary experiment',document.querySelector('.control-card'));
    const display=document.createElement('div');display.className='display-controls';
    display.innerHTML='<label>CT preset<select id="window-preset"><option value="50,400">Soft tissue</option><option value="400,1800">Bone</option><option value="-600,1500">Lung</option></select></label><label>Window level (HU)<input id="window-level" type="number" value="50" min="-2000" max="4000"></label><label>Window width (HU)<input id="window-width" type="number" value="400" min="1" max="10000"></label><label><input id="show-overlay" type="checkbox" checked> Segmentation overlay</label><label><input id="show-crosshair" type="checkbox" checked> Linked crosshairs</label>';
    section('Display',display);
    sidebar.append($('bundle-btn'),source);
    const topbar=document.querySelector('.topbar');topbar.innerHTML='<div class="work-tabs"><button id="viewer-tab" aria-pressed="true">Four-up viewer</button><button id="analysis-tab" aria-pressed="false">Fragility & analysis</button></div><div class="toolbar-actions"><button id="load-toolbar">Load data</button><button id="fit-views">Fit views</button></div>';
    topbar.querySelector('.toolbar-actions').append($('reset-btn'));
    document.querySelector('.headline-row').remove();
    const workspace=document.querySelector('.workspace'), scanGrid=document.querySelector('.scan-grid');
    const axial=$('axial-image').closest('article'), coronal=$('coronal-image').closest('article'), sagittal=$('sagittal-image').closest('article'), mesh=document.querySelector('.mesh-panel');
    workspace.replaceChildren(axial,mesh,sagittal,coronal);scanGrid.remove();
    for(const [panel,name] of [[axial,'Axial'],[mesh,'3D'],[sagittal,'Sagittal'],[coronal,'Coronal']]){
      panel.dataset.view=name.toLowerCase();const button=document.createElement('button');button.className='maximize-view';button.textContent='⤢';button.setAttribute('aria-label','Maximize '+name+' view');
      button.addEventListener('click',()=>{const active=panel.classList.toggle('maximized');workspace.classList.toggle('has-maximized',active);button.setAttribute('aria-label',(active?'Restore ':'Maximize ')+name+' view');resizeViews();});panel.append(button);
    }
    const analysis=document.createElement('div');analysis.id='analysis-workspace';analysis.hidden=true;analysis.append(document.querySelector('.fingerprint-panel'),document.querySelector('.fragility-panel'),document.querySelector('.analysis-grid'));content.append(analysis);
    const footer=document.querySelector('.footer');footer.innerHTML='<span>Scroll: slices · Click: linked position · Shift+scroll: 5 slices</span><span>Credit to Tahmid Ullah</span>';content.append(footer);
    function resizeViews(){requestAnimationFrame(()=>{fitSlices();for(const id of ['mesh-plot','curve-plot','fragility-plot','fp-curves','fp-heatmap','fp-regions','fp-delta'])if($(id).data && $(id).offsetParent)Plotly.Plots.resize($(id));});}
    function tab(analysisVisible){workspace.hidden=analysisVisible;analysis.hidden=!analysisVisible;$('viewer-tab').setAttribute('aria-pressed',String(!analysisVisible));$('analysis-tab').setAttribute('aria-pressed',String(analysisVisible));resizeViews();}
    $('viewer-tab').onclick=()=>tab(false);$('analysis-tab').onclick=()=>tab(true);
    $('load-toolbar').onclick=()=>{$('load-section').open=true;$('load-section').scrollIntoView({block:'nearest'});};
    $('fit-views').onclick=()=>{workspace.classList.remove('has-maximized');workspace.querySelectorAll('.maximized').forEach(el=>el.classList.remove('maximized'));if($('mesh-plot').data)Plotly.relayout($('mesh-plot'),{'scene.camera':{eye:{x:1.65,y:1.55,z:1.02}}});resizeViews();};
    $('window-preset').onchange=e=>{const [level,width]=e.target.value.split(',');$('window-level').value=level;$('window-width').value=width;updateViews({includeScene:false});};
    for(const id of ['window-level','window-width','show-overlay','show-crosshair'])$(id).onchange=()=>{if($('window-level').checkValidity() && $('window-width').checkValidity())updateViews({includeScene:false});};
    new ResizeObserver(resizeViews).observe(workspace);
  }
  async function init(){
    try {
      if(!state.workstation){setupWorkstation();state.workstation=true;}
      state.meta=await fetchJSON('/api/meta');
      fitSlices();
      $('structure-count').textContent=String(state.meta.structures.length).padStart(2,'0');
      $('source-name').textContent=state.meta.source==='synthetic'?'SYNTHETIC DEMO':'LOCAL CT SCAN';
      $('source-detail').textContent=state.meta.source==='synthetic'?'No patient data included':'Loaded from local disk';
      for(const [key,idx] of [['slice-i',0],['slice-j',1],['slice-k',2]]) $(key).max=state.meta.shape[idx]-1;
      if(!state.bound){bindControls();state.bound=true;}
      if(state.meta.structures.length)await selectOrgan(state.meta.structures.some(s=>s.name==='liver')?'liver':state.meta.structures[0].name);
    }catch(e){err('Initialization error: '+e.message);}
  }
  window.addEventListener('load',init);
})();
