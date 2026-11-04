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
      b.type='button';b.innerHTML=`<i class="organ-color" style="background:${item.color}"></i><span></span><span class="organ-arrow">›</span>`;
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
    $('m-baseline').textContent=fmt(data.baseline_ml,2)+' mL';
    $('m-current').textContent=fmt(data.current_ml,2)+' mL';
    $('m-delta').textContent=(data.delta_pct>=0?'+':'')+fmt(data.delta_pct,2)+'%';
    $('m-delta').classList.toggle('negative',data.delta_pct<0);
    $('m-voxels').textContent=fmt(data.voxels,0);
    $('offset-value').textContent=signed(state.offset);
    const desc=state.offset===0 ? 'The original segmentation is unchanged.' :
      `${Math.abs(state.offset).toFixed(1)} mm ${state.offset>0?'outward':'inward'} boundary perturbation changes the measured mask volume by ${data.delta_pct>=0?'+':''}${data.delta_pct.toFixed(2)}%.`;
    $('insight-detail').textContent=desc;
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
      paper_bgcolor:'#1A1953',plot_bgcolor:'#1A1953',showlegend:false,
      margin:{l:0,r:0,t:0,b:0},uirevision:'constant-camera',
      scene:{bgcolor:'#1A1953',aspectmode:'data',
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
      paper_bgcolor:'#1A1953',plot_bgcolor:'#1A1953',showlegend:false,
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
      const url='/api/slice?'+params({organ,axis,index,offset,i,j,k});
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
    $('organ-label').value=name.replaceAll('_',' ');
    state.organ=name;state.offset=0;$('offset').value=0;state.curve=null;
    ++state.renderToken;
    setOrganButtons();$('mesh-title').textContent=name.replaceAll('_',' ').replace(/\b\w/g,c=>c.toUpperCase());
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
    const img=event.currentTarget,rect=img.getBoundingClientRect(),naturalWidth=img.naturalWidth,naturalHeight=img.naturalHeight;
    if(!naturalWidth||!naturalHeight)return;
    const scale=Math.min(rect.width/naturalWidth,rect.height/naturalHeight);
    const dw=naturalWidth*scale,dh=naturalHeight*scale;
    const dx=(rect.width-dw)/2,dy=(rect.height-dh)/2;
    const x=Math.floor((event.clientX-rect.left-dx)/scale),y=Math.floor((event.clientY-rect.top-dy)/scale);
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
  function bindControls(){
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
  async function init(){
    try {
      state.meta=await fetchJSON('/api/meta');
      $('structure-count').textContent=String(state.meta.structures.length).padStart(2,'0');
      $('source-name').textContent=state.meta.source==='synthetic'?'SYNTHETIC DEMO':'LOCAL CT SCAN';
      $('source-detail').textContent=state.meta.source==='synthetic'?'No patient data included':'Loaded from local disk';
      for(const [key,idx] of [['slice-i',0],['slice-j',1],['slice-k',2]]) $(key).max=state.meta.shape[idx]-1;
      if(!state.bound){bindControls();state.bound=true;}
      await selectOrgan(state.meta.structures.some(s=>s.name==='liver')?'liver':state.meta.structures[0].name);
    }catch(e){err('Initialization error: '+e.message);}
  }
  window.addEventListener('load',init);
})();
