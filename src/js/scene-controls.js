/* ============================================================
   4c. SCENE CONTROLS, floor explorer, camera presets, reveal, evening
   ============================================================ */
(function(){
  const floorNav=$("#floorNav"),viewPresets=$("#viewPresets"),revealBtn=$("#revealBtn"),eveningBtn=$("#eveningBtn");
  const fnBtns=[...floorNav.querySelectorAll(".fn-btn")],vpBtns=[...viewPresets.querySelectorAll(".vp-btn")];
  const fullBtn=floorNav.querySelector(".fn-full");
  const evLabel=[...eveningBtn.childNodes].find(n=>n.nodeType===3);
  function setFloorActive(floor){fnBtns.forEach(b=>b.classList.toggle("active",b.dataset.floor===floor&&floor!==""));fullBtn.disabled=!floor;$("#sceneWrap").classList.toggle("floor-mode",!!floor);}
  function setViewActive(v){vpBtns.forEach(b=>b.classList.toggle("active",b.dataset.view===v));}
  function clearReveal(){revealBtn.setAttribute("aria-pressed","false");}
  fnBtns.forEach(b=>b.addEventListener("click",()=>{if(!scene3d)return;const f=b.dataset.floor;closeZone();clearReveal();
    if(f){scene3d.explodeFloor(f);setFloorActive(f);setViewActive("");}else{scene3d.fullVilla();setFloorActive("");setViewActive("overall");}}));
  vpBtns.forEach(b=>b.addEventListener("click",()=>{if(!scene3d)return;const v=b.dataset.view;closeZone();clearReveal();scene3d.goTo(v);setViewActive(v);setFloorActive("");}));
  revealBtn.addEventListener("click",()=>{if(!scene3d)return;const on=revealBtn.getAttribute("aria-pressed")!=="true";revealBtn.setAttribute("aria-pressed",String(on));if(on){setFloorActive("");}scene3d.setReveal(on);});
  eveningBtn.addEventListener("click",()=>{if(!scene3d)return;const on=eveningBtn.getAttribute("aria-pressed")!=="true";eveningBtn.setAttribute("aria-pressed",String(on));if(evLabel)evLabel.nodeValue=on?"Day":"Evening";scene3d.setEvening(on);});
  window.__resetControls=function(){setFloorActive("");setViewActive("overall");clearReveal();setCleanView(false);};

  /* ---- only-building toggle: hides every overlay on the 3D view, click again to bring it back ---- */
  const cleanBtn=$("#cleanViewBtn"),sceneWrap=$("#sceneWrap");
  function setCleanView(on){
    if(on&&$("#drawer").classList.contains("show"))closeZone();
    sceneWrap.classList.toggle("clean-view",on);
    cleanBtn.setAttribute("aria-pressed",String(on));
    cleanBtn.setAttribute("aria-label",on?"Show the details again":"Hide everything except the building");
    cleanBtn.title=on?"Show details":"Show only the building";
  }
  cleanBtn.addEventListener("click",()=>setCleanView(!sceneWrap.classList.contains("clean-view")));
})();

/* ---- full screen: real browser fullscreen where supported (desktop, Android, iPad),
       CSS-only immersive mode as fallback (iPhone Safari has no element fullscreen) ---- */
(function(){
  const app=$("#app"),btn=$("#fullscreenBtn"),label=btn.querySelector(".fs-label");
  const fsEl=()=>document.fullscreenElement||document.webkitFullscreenElement;
  const canNative=!!(app.requestFullscreen||app.webkitRequestFullscreen);
  function apply(on){
    app.classList.toggle("is-full",on);
    btn.setAttribute("aria-pressed",String(on));
    btn.setAttribute("aria-label",on?"Exit full screen":"View the villa full screen");
    label.textContent=on?"Exit full screen":"Full screen";
    btn.title=on?"Exit full screen (Esc)":"Full screen";
  }
  async function enter(){
    apply(true);
    if(canNative&&!fsEl()){try{await (app.requestFullscreen?app.requestFullscreen():app.webkitRequestFullscreen());}catch(_){/* fallback stays CSS-only */}}
  }
  function exit(){
    if(fsEl()){(document.exitFullscreen||document.webkitExitFullscreen).call(document);}  // fullscreenchange calls apply(false)
    else apply(false);
  }
  btn.addEventListener("click",()=>app.classList.contains("is-full")?exit():enter());
  const onChange=()=>{if(!fsEl())apply(false);};
  document.addEventListener("fullscreenchange",onChange);
  document.addEventListener("webkitfullscreenchange",onChange);
  /* Esc for the CSS-only fallback (native fullscreen handles Esc itself). Capture phase, so an
     open drawer/modal is seen before its own Esc handler closes it: Esc closes that first. */
  document.addEventListener("keydown",e=>{if(e.key==="Escape"&&!fsEl()&&app.classList.contains("is-full")&&!document.querySelector(".drawer.show,.render-modal.show"))apply(false);},true);
  window.__exitFullscreen=exit;
})();

