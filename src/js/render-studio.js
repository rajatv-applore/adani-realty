/* ============================================================
   4b. PHOTOREAL RENDER (Blender), non-destructive overlay
   ============================================================ */
(function(){
  const modal=$("#renderModal"),note=$("#rmNote"),go=$("#rmGo");
  const statusEl=$("#rmStatus"),bar=$("#rmBarI"),msg=$("#rmMsg"),errEl=$("#rmErr"),stage=$("#rmStage"),img=$("#rmImg"),cap=$("#rmCap"),dl=$("#rmDl");
  let poll=null;
  function reset(){statusEl.classList.remove("show");errEl.classList.remove("show");stage.classList.remove("show");bar.style.width="0";}
  function open(){modal.classList.add("show");modal.setAttribute("aria-hidden","false");reset();capability();}
  function close(){modal.classList.remove("show");modal.setAttribute("aria-hidden","true");if(poll){clearInterval(poll);poll=null;}}
  async function capability(){
    note.style.display="none";go.disabled=false;
    try{
      const r=await fetch("/api/render",{cache:"no-store"});if(!r.ok)throw 0;
      const c=await r.json();
      if(!c.blenderAvailable){
        note.style.display="block";note.className="rm-note warn";
        note.innerHTML='Blender isn’t installed on this machine yet, so renders can’t run. Install it and restart the server:<br><code>brew install --cask blender</code><br>…or point the server at an existing install with the <code>BLENDER_PATH</code> env var. The interactive 3D view works regardless.';
        go.disabled=true;
      }
    }catch(e){
      note.style.display="block";note.className="rm-note warn";
      note.innerHTML='Photoreal rendering needs the local render server. Open the app at <code>http://localhost:8770/</code> (run <code>npm run dev</code>), it can’t render from a <code>file://</code> page. The interactive 3D view still works.';
      go.disabled=true;
    }
  }
  function zonesPayload(){const z={};Object.values(villaData.zones).forEach(x=>{z[x.id]={stage:x.stage,progress:x.progress};});return z;}
  async function start(){
    reset();go.disabled=true;statusEl.classList.add("show");msg.textContent="Queued…";let id;
    try{
      const samples=+$("#rmSamples").value;
      const res=samples>=128?"1600x1000":samples>=64?"1280x800":"960x600";
      const r=await fetch("/api/render",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({view:$("#rmView").value,engine:$("#rmEngine").value,time:$("#rmTime").value,villaNo:(villaData.property.name||"").replace(/^villa\s*(no\.?\s*)?/i,""),samples,res,zones:zonesPayload()})});
      const j=await r.json();if(!j.jobId)throw new Error(j.error||"could not start render");id=j.jobId;
    }catch(e){fail("Could not start render: "+(e.message||e));return;}
    poll=setInterval(async()=>{
      try{
        const r=await fetch("/api/render/"+id,{cache:"no-store"});const j=await r.json();
        if(typeof j.progress==="number")bar.style.width=j.progress+"%";
        if(j.message)msg.textContent=j.message;
        if(j.status==="done"){clearInterval(poll);poll=null;done(j);}
        else if(j.status==="error"){clearInterval(poll);poll=null;fail(j.error||"render failed");}
      }catch(e){}
    },1200);
  }
  function done(j){statusEl.classList.remove("show");go.disabled=false;const src=j.image+"?t="+Date.now();img.src=src;dl.href=src;cap.textContent="Rendered with Blender"+(j.ms?" · "+(j.ms/1000).toFixed(1)+"s":"");stage.classList.add("show");}
  function fail(m){statusEl.classList.remove("show");go.disabled=false;errEl.textContent=m;errEl.classList.add("show");}
  const rb=$("#renderBtn");if(rb)rb.addEventListener("click",open);
  $("#rmClose").addEventListener("click",close);
  modal.addEventListener("click",e=>{if(e.target===modal)close();});
  go.addEventListener("click",start);
  document.addEventListener("keydown",e=>{if(e.key==="Escape"&&modal.classList.contains("show"))close();});
})();

