/* ============================================================
   6. SCREEN FLOW, login → villa directory → 3D experience
   ============================================================ */
(function(){
  /* directory derived from the per-villa data model (each villa has its own zones) */
  const directory=Object.keys(VILLAS).map(id=>{const p=VILLAS[id].property;return {id,client:p.client,villa:p.name,project:p.project,type:p.type,location:p.location,progress:p.overallProgress};});
  const gid=id=>document.getElementById(id);
  function showScreen(id){
    gid("loginScreen").style.display=id==="login"?"flex":"none";
    gid("searchScreen").style.display=id==="search"?"flex":"none";
    gid("app").style.display=id==="villa"?"grid":"none";
  }
  function closeAndReset(){ try{ if(typeof closeZone==="function") closeZone(); }catch(_){ } if(typeof window.__resetControls==="function") window.__resetControls(); if(typeof window.__exitFullscreen==="function") window.__exitFullscreen(); }

  /* ---- login ---- */
  gid("loginForm").addEventListener("submit",e=>{
    e.preventDefault();
    const email=(gid("loginEmail").value||"priya.sharma@adani.com").trim();
    const base=email.split("@")[0]||"relationship manager";
    const name=base.split(/[._\-]/).filter(Boolean).map(s=>s[0].toUpperCase()+s.slice(1)).join(" ")||"Relationship Manager";
    gid("sbName").textContent=name;
    gid("sbAvatar").textContent=name.split(" ").map(w=>w[0]).join("").slice(0,2).toUpperCase();
    renderResults(); showScreen("search");
  });
  gid("signOut").addEventListener("click",()=>{ closeAndReset(); showScreen("login"); });

  /* ---- search / filters ---- */
  const fClient=gid("fClient"),fProject=gid("fProject"),fType=gid("fType"),fLoc=gid("fLocation");
  function filtered(){
    const q=fClient.value.trim().toLowerCase();
    return directory.filter(e=>
      (!q||e.client.toLowerCase().includes(q)||e.villa.toLowerCase().includes(q))&&
      (fProject.value==="all"||e.project===fProject.value)&&
      (fType.value==="all"||e.type===fType.value)&&
      (fLoc.value==="all"||e.location===fLoc.value));
  }
  const arrow='<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  function renderResults(){
    const r=filtered(),res=gid("sbResults");
    gid("sbCount").textContent=r.length+" "+(r.length===1?"residence":"residences");
    if(!r.length){res.innerHTML='<div class="sb-empty">No residences match your search. Try clearing a filter.</div>';return;}
    res.innerHTML=r.map(e=>{const i=directory.indexOf(e);return '<button type="button" class="villa-card" data-i="'+i+'" aria-label="Open '+e.client+', '+e.villa+'">'
      +'<div class="vc-top"><div><div class="vc-client">'+e.client+'</div><div class="vc-villa">'+e.villa+' · '+e.project+'</div></div>'
      +'<div class="vc-badge" style="--p:'+e.progress+'"><b>'+e.progress+'</b><i>%</i></div></div>'
      +'<div class="vc-meta"><span class="vc-tag">'+e.type+'</span><span class="vc-tag">'+e.location+'</span></div>'
      +'<div class="vc-prog"><i style="width:'+e.progress+'%"></i></div>'
      +'<div class="vc-open">Open experience '+arrow+'</div></button>';}).join("");
    res.querySelectorAll(".villa-card").forEach(b=>b.addEventListener("click",()=>openVilla(directory[+b.dataset.i])));
  }
  [fClient].forEach(el=>el.addEventListener("input",renderResults));
  [fProject,fType,fLoc].forEach(el=>el.addEventListener("change",renderResults));
  gid("doSearch").addEventListener("click",renderResults);

  /* ---- open a villa experience (switch the active villa data) ---- */
  async function openVilla(e){
    if(VILLAS[e.id]) villaData=VILLAS[e.id];
    applyResidence(); renderTimeline(); renderAttention();
    closeAndReset();
    showScreen("villa");
    await ensureScene();
    if(scene3d&&scene3d.refreshZones) scene3d.refreshZones();
    if(scene3d&&scene3d.reset) scene3d.reset();
  }
  const back=gid("villaBack"); if(back) back.addEventListener("click",()=>{ closeAndReset(); showScreen("search"); });

  /* ---- init ---- */
  showScreen("login");
})();
