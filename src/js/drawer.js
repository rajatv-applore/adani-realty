/* ============================================================
   4. ZONE DRAWER
   ============================================================ */
let activeZone=null,lastFocus=null;
function openZone(id){const z=villaData.zones[id];if(!z)return;activeZone=id;
  if(scene3d) scene3d.select(id);
  $("#sceneWrap").classList.add("has-sel");
  document.querySelectorAll(".hotspot").forEach(h=>h.classList.toggle("active",h.dataset.for===id));
  $("#drawerTitle").textContent=z.name;$("#drawerPct").textContent=z.progress;
  $("#drawerSub").innerHTML='<span class="chip chip-stage">'+z.stage+'</span><span class="chip chip-sched '+schedClass[z.scheduleStatus]+'"><span class="d"></span>'+z.scheduleStatus+'</span>';
  const si=villaData.stages.indexOf(z.stage);let steps='<div class="stepper">';
  villaData.stages.forEach((s,i)=>{let c="step";const full=z.progress===100;if(i<si)c+=" done";else if(i===si)c+=full?" done current":" current";
    steps+='<div class="'+c+'"><span class="connector"></span><span class="node"><svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M5 12l4 4 10-11" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg></span><span class="sl">'+s+'</span></div>';});
  steps+='</div>';
  let sel='<div class="sel-list">';
  z.selections.forEach((s,i)=>{const p=s.status==="Pending";const opt=p?'<span class="opt opt-pending">Decision pending</span>':'<span class="opt">'+s.option+'</span>';
    sel+='<div class="sel-item'+(p?' pending':'')+'" data-sel="'+i+'" role="button" tabindex="0" aria-expanded="false" aria-label="'+s.name+', '+(p?'decision pending':s.status)+'"><div class="top"><div><div class="nm">'+s.name+'</div>'+opt+'</div><span class="st-tag '+statusClass[s.status]+'"><span class="d"></span>'+s.status+'</span></div><div class="sel-expand"><div class="line"><p>'+s.note+'</p>'+(p?'<button type="button" class="sel-action">Mark as reviewed</button><div class="reviewed-note"><svg viewBox="0 0 24 24" width="12" height="12" fill="none" aria-hidden="true"><path d="M5 12l4 4 10-11" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg>Noted for your review, not yet confirmed with the developer</div>':'')+'</div></div></div>';});
  sel+='</div>';
  const pc=z.selections.filter(s=>s.status==="Pending").length;
  const zatt=pc?'<div class="zone-att"><span class="za-dot"></span><span><b>'+pc+'</b> '+(pc===1?'selection':'selections')+' awaiting your preference</span></div>':'';
  $("#drawerBody").innerHTML='<div class="sec">Construction progress</div><div class="progbar"><i id="zoneBar"></i></div>'+steps+'<p class="cdesc">'+z.description+'</p><div class="target"><svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><rect x="4" y="5" width="16" height="16" rx="2" stroke="currentColor" stroke-width="1.6"/><path d="M4 9h16M8 3v4M16 3v4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>'+(z.progress===100?'Completed':'Target completion')+': <b>'+z.targetDate+'</b></div><div class="sec">Design &amp; selections</div>'+zatt+'<p class="sel-intro">Your chosen finishes and fittings, brought together in one place.</p>'+sel;
  const bar=$("#zoneBar");requestAnimationFrame(()=>requestAnimationFrame(()=>{bar.style.width=z.progress+"%";}));
  $("#drawerBody").querySelectorAll(".sel-item").forEach(el=>{const tg=()=>{const o=el.classList.contains("open");el.classList.toggle("open",!o);el.setAttribute("aria-expanded",String(!o));};
    el.addEventListener("click",e=>{if(e.target.closest(".sel-action"))return;tg();});
    el.addEventListener("keydown",e=>{if(e.target.closest(".sel-action"))return;if(e.key==="Enter"||e.key===" "){e.preventDefault();tg();}});});
  $("#drawerBody").querySelectorAll(".sel-action").forEach(b=>b.addEventListener("click",e=>{e.stopPropagation();const it=b.closest(".sel-item");it.classList.add("reviewed");b.classList.add("reviewed");b.textContent="Reviewed";}));
  drawer.classList.add("show");scrim.classList.add("show");drawer.setAttribute("aria-hidden","false");
  /* preventScroll: the drawer is still off-screen (sliding in) at this moment, and a plain focus()
     scrolls the overflow-hidden .app sideways to reveal it, shifting the whole layout */
  lastFocus=document.activeElement;$("#drawerClose").focus({preventScroll:true});$("#app").scrollLeft=0;
}
function closeZone(){drawer.classList.remove("show");scrim.classList.remove("show");drawer.setAttribute("aria-hidden","true");
  $("#sceneWrap").classList.remove("has-sel");document.querySelectorAll(".hotspot").forEach(h=>h.classList.remove("active"));
  if(scene3d) scene3d.select(null);activeZone=null;if(lastFocus&&lastFocus.focus)lastFocus.focus({preventScroll:true});}
const drawer=$("#drawer"),scrim=$("#scrim");
$("#drawerClose").addEventListener("click",closeZone);scrim.addEventListener("click",closeZone);
document.addEventListener("keydown",e=>{if(e.key==="Escape"){if(drawer.classList.contains("show"))closeZone();else document.querySelectorAll(".tl-item.sel").forEach(i=>{i.classList.remove("sel");i.setAttribute("aria-expanded","false");});}});

