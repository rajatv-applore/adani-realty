/* ============================================================
   3. UI, header, ring, timeline
   ============================================================ */
const $=s=>document.querySelector(s);
const stageDot={Foundation:"sd-foundation",Structure:"sd-structure",Finishing:"sd-finishing",Ready:"sd-ready"};
const schedClass={"On track":"s-ontrack","Delayed":"s-delayed","Completed":"s-completed"};
const statusClass={Pending:"st-pending",Selected:"st-selected",Approved:"st-approved",Installed:"st-installed"};
function setRingArc(p,animate){const r=52,C=2*Math.PI*r,arc=$("#ringArc");arc.setAttribute("stroke-dasharray",C.toFixed(1));const target=C*(1-p/100);const reduce=matchMedia("(prefers-reduced-motion:reduce)").matches;if(reduce||animate===false){arc.style.transition="none";arc.setAttribute("stroke-dashoffset",target.toFixed(1));}else{requestAnimationFrame(()=>{arc.style.transition="stroke-dashoffset 1100ms cubic-bezier(.22,.61,.36,1)";requestAnimationFrame(()=>arc.setAttribute("stroke-dashoffset",target.toFixed(1)));});}}

/* apply the active residence (identity + overall progress) from villaData.property */
function applyResidence(){
  const p=villaData.property;
  $("#resTitle").textContent=p.name;
  $("#resLoc").textContent=p.project+" · "+p.location;
  $("#ringBig").textContent=p.overallProgress;
  const ch=$("#compHead"); if(ch) ch.textContent="This home is "+p.overallProgress+"% complete";
  const cc=$("#villaClient"); if(cc) cc.textContent=p.client||"";
  const de=$("#drawerEyebrow"); if(de) de.textContent=(p.client?p.client+" · ":"")+p.name;
  setRingArc(p.overallProgress,true);
}
applyResidence();

function renderTimeline(){const list=$("#tlList");list.innerHTML="";const bd={completed:["tb-completed","Completed"],inprogress:["tb-inprogress","In progress"],upcoming:["tb-upcoming","Upcoming"]};
const SPECTRUM=["#3E9BA6","#4B82CE","#5564B8","#7261B4","#C793BE","#B24F8E"];
villaData.milestones.forEach((m,i)=>{const it=document.createElement("button");it.type="button";it.className="tl-item";it.setAttribute("data-state",m.state);it.style.setProperty("--sp",SPECTRUM[i%SPECTRUM.length]);it.setAttribute("aria-expanded","false");const[bc,bl]=bd[m.state];
it.innerHTML='<div class="tl-rail"><span class="tl-dot"></span></div><div class="tl-main"><div class="t-name">'+m.name+'</div><div class="t-meta"><span class="t-badge '+bc+'">'+bl+'</span><span class="t-date">'+m.date+'</span></div><div class="tl-detail"><p>'+m.desc+'</p></div></div>';
it.addEventListener("click",()=>{const o=it.classList.contains("sel");document.querySelectorAll(".tl-item.sel").forEach(i=>{i.classList.remove("sel");i.setAttribute("aria-expanded","false");});if(!o){it.classList.add("sel");it.setAttribute("aria-expanded","true");}});
list.appendChild(it);});}
renderTimeline();

function renderAttention(){
  const pend=[];Object.values(villaData.zones).forEach(z=>z.selections.forEach(s=>{if(s.status==="Pending")pend.push({zone:z.id,zoneName:z.name,name:s.name});}));
  $("#attCount").textContent=pend.length;
  $("#attList").innerHTML=pend.length?pend.map(p=>'<button type="button" class="att-item" data-zone="'+p.zone+'" aria-label="'+p.name+' in '+p.zoneName+', decision pending"><span class="att-amber"></span><span class="att-main"><span class="att-nm">'+p.name+'</span><span class="att-zn">'+p.zoneName+' · Decision pending</span></span><svg viewBox="0 0 24 24" width="13" height="13" fill="none" aria-hidden="true"><path d="M9 6l6 6-6 6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg></button>').join(""):'<div class="att-none">All selections are in progress, nothing awaiting your preference.</div>';
  $("#attList").querySelectorAll(".att-item").forEach(b=>b.addEventListener("click",()=>openZone(b.dataset.zone)));
}
renderAttention();

