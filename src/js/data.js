/* ============================================================
   2. DATA MODEL, single source of truth
   ============================================================ */
const VILLAS = {};
VILLAS.villa08 = {
  property:{ developer:"Adani Realty", project:"The North Park", name:"Villa No. 08", client:"Rajesh & Meera Shah", type:"4 BHK Villa", location:"Shantigram, Ahmedabad", configuration:"4 BHK", overallProgress:68, asOf:"29 Oct 2026", isDemoData:true },
  stages:["Foundation","Structure","Finishing","Ready"],
  zones:{
    basement:{ id:"basement", name:"Basement", progress:65, stage:"Finishing", scheduleStatus:"On track", targetDate:"30 Nov 2026",
      description:"The lower level, your future home theatre, gym or games room, is enclosed, with finishing work now underway on its surfaces and fittings.",
      selections:[
        {name:"Multipurpose room flooring", option:"Premium stone finish", status:"Approved", note:"A premium natural stone finish approved for the lower-level multipurpose room."},
        {name:"Home theatre acoustic treatment", option:null, status:"Pending", note:"Your preferred acoustic treatment for the home theatre is yet to be finalised."},
        {name:"Ceiling treatment", option:"Concealed lighting design", status:"Selected", note:"A concealed, layered ceiling lighting design selected for a calm ambience."},
        {name:"Internal doors", option:"Veneer finish", status:"Installed", note:"Veneer-finished internal doors crafted and installed."}
      ]},
    groundFloor:{ id:"groundFloor", name:"Ground Floor", progress:90, stage:"Finishing", scheduleStatus:"On track", targetDate:"20 Nov 2026",
      description:"Most of the main construction is complete. The remaining work focuses on interior finishes, fittings and final detailing across the living, dining, kitchen and pooja spaces.",
      selections:[
        {name:"Living room flooring", option:"Italian marble, warm ivory", status:"Approved", note:"A warm ivory Italian marble selected for the main living spaces, approved for installation."},
        {name:"Kitchen fittings", option:null, status:"Pending", note:"Your preferred kitchen fittings are yet to be finalised."},
        {name:"Dining area lighting", option:"Architectural recessed lighting", status:"Selected", note:"A discreet architectural recessed scheme chosen to wash the dining area in soft light."},
        {name:"Internal joinery", option:"Natural oak veneer", status:"Installed", note:"Natural oak veneer joinery has been crafted and installed."},
        {name:"Pooja room finish", option:"Natural stone and timber detailing", status:"Approved", note:"Natural stone with warm timber detailing approved for the pooja room."}
      ]},
    firstFloor:{ id:"firstFloor", name:"First Floor", progress:55, stage:"Structure", scheduleStatus:"On track", targetDate:"30 Nov 2026",
      description:"Structural work on the bedroom level is progressing. The next steps will bring the master suite and bedrooms closer to their finished form.",
      selections:[
        {name:"Bedroom flooring", option:"Engineered oak, natural finish", status:"Selected", note:"Engineered oak with a natural matte finish chosen for the bedrooms."},
        {name:"Master bathroom stone", option:"Calacatta marble", status:"Selected", note:"Calacatta marble selected for the master bathroom surfaces."},
        {name:"Wardrobe finish", option:null, status:"Pending", note:"Your preferred wardrobe finish is yet to be finalised."},
        {name:"Bedroom lighting", option:"Warm recessed lighting", status:"Approved", note:"A warm, layered recessed lighting scheme approved for the bedrooms."}
      ]},
    facade:{ id:"facade", name:"Façade", progress:70, stage:"Finishing", scheduleStatus:"On track", targetDate:"25 Nov 2026",
      description:"The exterior is taking shape, with finishing work bringing together the stone cladding, glazing and architectural details of the elevation.",
      selections:[
        {name:"Exterior stone", option:"Light beige natural stone", status:"Approved", note:"Light beige natural stone cladding approved for the exterior."},
        {name:"Window frames", option:"Dark bronze aluminium", status:"Installed", note:"Slimline dark bronze aluminium frames installed throughout."},
        {name:"Exterior paint finish", option:"Warm neutral palette", status:"Selected", note:"A warm neutral exterior palette selected to complement the natural stone."},
        {name:"Architectural lighting", option:null, status:"Pending", note:"Your preferred façade wash lighting is yet to be finalised."}
      ]},
    decks:{ id:"decks", name:"Decks & Terraces", progress:60, stage:"Structure", scheduleStatus:"On track", targetDate:"05 Dec 2026",
      description:"The decks, balconies and rooftop terrace are taking structural shape, ready to become your expansive indoor-outdoor living spaces.",
      selections:[
        {name:"Deck flooring", option:"Natural stone finish", status:"Selected", note:"A natural stone deck finish selected for the terraces."},
        {name:"Outdoor railing", option:"Glass and metal detailing", status:"Approved", note:"Frameless glass with fine metal detailing approved for the terrace railings."},
        {name:"Outdoor lighting", option:null, status:"Pending", note:"Your preferred outdoor lighting approach is yet to be finalised."},
        {name:"Seating arrangement", option:"Landscape-integrated seating", status:"Selected", note:"Landscape-integrated seating selected to frame the terrace views."}
      ]},
    landscape:{ id:"landscape", name:"Garden & Driveway", progress:30, stage:"Foundation", scheduleStatus:"On track", targetDate:"15 Dec 2026",
      description:"Ground preparation and early landscape work are underway across the private garden and the cobblestone driveway. Planting and finishing will follow.",
      selections:[
        {name:"Garden planting", option:"Layered landscape palette", status:"Selected", note:"A layered landscape planting palette selected for year-round texture and privacy."},
        {name:"Driveway paving", option:"Cobblestone finish", status:"Approved", note:"A cobblestone driveway finish approved for the private entrance."},
        {name:"Landscape lighting", option:null, status:"Pending", note:"Your preferred landscape lighting approach is yet to be finalised."},
        {name:"Garden pathway", option:"Natural stone", status:"Installed", note:"Natural stone garden pathways have been laid."}
      ]},
    servantsQuarter:{ id:"servantsQuarter", name:"Servants' Quarters", progress:45, stage:"Structure", scheduleStatus:"On track", targetDate:"10 Dec 2026",
      description:"The separate servants' quarters are rising in structure, with the walls and slabs now taking shape.",
      selections:[
        {name:"Flooring", option:null, status:"Pending", note:"Your preferred flooring for the servants' quarters is yet to be finalised."},
        {name:"Storage joinery", option:"Functional laminate finish", status:"Selected", note:"A durable functional laminate finish selected for the storage joinery."},
        {name:"Lighting", option:"Recessed fixtures", status:"Approved", note:"Minimal recessed lighting fixtures approved."}
      ]}
  },
  milestones:[
    {id:"m1", name:"Architectural design finalisation", state:"completed", date:"15 Feb 2026", desc:"Your architectural design and principal specifications were finalised together."},
    {id:"m2", name:"Foundation work", state:"completed", date:"28 Mar 2026", desc:"The foundations and ground works were completed, setting the base for your home."},
    {id:"m3", name:"Main structural work", state:"completed", date:"30 Jun 2026", desc:"The principal structure of the villa was completed across the basement, ground and first floors."},
    {id:"m4", name:"Interior and exterior finishing", state:"inprogress", date:"Target 20 Nov 2026", desc:"Work is progressing on surfaces, fittings and the details that bring your home together, inside and out."},
    {id:"m5", name:"Final inspection", state:"upcoming", date:"Target 15 Dec 2026", desc:"A thorough quality and handover inspection before your home is ready to receive you."},
    {id:"m6", name:"Home handover", state:"upcoming", date:"Target 22 Dec 2026", desc:"The moment your finished home is handed over and the keys become yours."}
  ]
};

/* ---- builder for the other directory residences (distinct per-villa data) ---- */
const STAGES4=["Foundation","Structure","Finishing","Ready"];
function bandStage(p){return p>=100?"Ready":p>=65?"Finishing":p>=35?"Structure":"Foundation";}
const STAGE_DESC={
  Foundation:"ground preparation and early works are underway.",
  Structure:"structural work is progressing, with walls and slabs taking shape.",
  Finishing:"finishing work is underway, surfaces, fittings and final detailing.",
  Ready:"complete and ready."
};
const ZONE_ORDER=[["basement","Basement"],["groundFloor","Ground Floor"],["firstFloor","First Floor"],["facade","Façade"],["decks","Decks & Terraces"],["landscape","Garden & Driveway"],["servantsQuarter","Servants' Quarters"]];
const CATALOG={
  basement:[["Multipurpose room flooring","Premium stone finish"],["Home theatre acoustic treatment","Acoustic panelling"],["Ceiling treatment","Concealed lighting design"],["Internal doors","Veneer finish"]],
  groundFloor:[["Living room flooring","Italian marble, warm ivory"],["Kitchen fittings","Modular premium fittings"],["Dining area lighting","Architectural recessed lighting"],["Internal joinery","Natural oak veneer"],["Pooja room finish","Natural stone and timber detailing"]],
  firstFloor:[["Bedroom flooring","Engineered oak, natural finish"],["Master bathroom stone","Calacatta marble"],["Wardrobe finish","Smoked oak"],["Bedroom lighting","Warm recessed lighting"]],
  facade:[["Exterior stone","Light beige natural stone"],["Window frames","Dark bronze aluminium"],["Exterior paint finish","Warm neutral palette"],["Architectural lighting","Façade wash lighting"]],
  decks:[["Deck flooring","Natural stone finish"],["Outdoor railing","Glass and metal detailing"],["Outdoor lighting","Warm ambient fixtures"],["Seating arrangement","Landscape-integrated seating"]],
  landscape:[["Garden planting","Layered landscape palette"],["Driveway paving","Cobblestone finish"],["Landscape lighting","Low-glare fixtures"],["Garden pathway","Natural stone"]],
  servantsQuarter:[["Flooring","Neutral stone tile"],["Storage joinery","Functional laminate finish"],["Lighting","Recessed fixtures"]]
};
function deriveStatus(i,n,p){const t=(i+0.5)/n*100;if(p>=t+22)return "Installed";if(p>=t+6)return "Approved";if(p>=t-16)return "Selected";return "Pending";}
function deriveSelections(zoneId,p){const cat=CATALOG[zoneId]||[],n=cat.length;return cat.map((c,i)=>{const status=deriveStatus(i,n,p),pend=status==="Pending";
  return {name:c[0],option:pend?null:c[1],status,note:pend?("Your preferred "+c[0].toLowerCase()+" is yet to be finalised."):(c[1]+", "+status.toLowerCase()+".")};});}
const DATE_POOL=["18 Nov 2026","20 Nov 2026","25 Nov 2026","30 Nov 2026","05 Dec 2026","10 Dec 2026","15 Dec 2026","22 Dec 2026"];
function buildMilestones(ov){const m=[
  {name:"Architectural design finalisation",date:"15 Feb 2026",state:"completed",desc:"Your architectural design and principal specifications were finalised together."},
  {name:"Foundation work",date:"28 Mar 2026",state:ov>=20?"completed":"inprogress",desc:"The foundations and ground works for your home."},
  {name:"Main structural work",date:"30 Jun 2026",state:ov>=48?"completed":(ov>=20?"inprogress":"upcoming"),desc:"The principal structure across the basement, ground and first floors."},
  {name:"Interior and exterior finishing",date:"Target 20 Nov 2026",state:ov>=95?"completed":(ov>=40?"inprogress":"upcoming"),desc:"Surfaces, fittings and the details that bring your home together."},
  {name:"Final inspection",date:"Target 15 Dec 2026",state:ov>=98?"completed":"upcoming",desc:"A thorough quality and handover inspection before your home is ready."},
  {name:"Home handover",date:"Target 22 Dec 2026",state:"upcoming",desc:"The moment your finished home is handed over and the keys become yours."}];
  return m.map((x,i)=>Object.assign({id:"m"+(i+1)},x));}
function buildVilla(meta){const zones={};
  ZONE_ORDER.forEach((zd,idx)=>{const id=zd[0],name=zd[1],p=meta.profile[id],stage=bandStage(p),delayed=(meta.delayed||[]).indexOf(id)>=0;
    zones[id]={id,name,progress:p,stage,scheduleStatus:p>=100?"Completed":(delayed?"Delayed":"On track"),targetDate:DATE_POOL[(idx+(meta.di||0))%DATE_POOL.length],description:name+", "+STAGE_DESC[stage],selections:deriveSelections(id,p)};});
  return {property:{developer:"Adani Realty",project:meta.project||"The North Park",name:meta.villa,client:meta.client,type:meta.type,configuration:meta.type,location:meta.location,overallProgress:meta.overall,asOf:"29 Oct 2026",isDemoData:true},stages:STAGES4,zones,milestones:buildMilestones(meta.overall)};}
VILLAS.villa12=buildVilla({villa:"Villa No. 12",client:"Anita Desai",type:"4 BHK Villa",location:"Shantigram, Ahmedabad",overall:54,di:1,delayed:["landscape"],profile:{basement:70,groundFloor:75,firstFloor:45,facade:60,decks:40,landscape:25,servantsQuarter:50}});
VILLAS.villa21=buildVilla({villa:"Villa No. 21",client:"Vikram & Leela Patel",type:"5 BHK Villa",location:"Shantigram, Ahmedabad",overall:82,di:2,profile:{basement:90,groundFloor:95,firstFloor:80,facade:85,decks:75,landscape:60,servantsQuarter:85}});
VILLAS.villa05=buildVilla({villa:"Villa No. 05",client:"The Nair Family",type:"4 BHK Villa",location:"Shantigram, Ahmedabad",overall:41,di:3,delayed:["firstFloor"],profile:{basement:55,groundFloor:50,firstFloor:35,facade:45,decks:30,landscape:20,servantsQuarter:40}});
VILLAS.villa33=buildVilla({villa:"Villa No. 33",client:"S. Krishnan",type:"6 BHK Villa",location:"Shantigram, Ahmedabad",overall:73,di:4,profile:{basement:80,groundFloor:88,firstFloor:65,facade:75,decks:62,landscape:55,servantsQuarter:70}});
VILLAS.villa02=buildVilla({villa:"Villa No. 02",client:"Aarav & Diya Mehta",type:"4 BHK Villa",location:"Shantigram, Ahmedabad",overall:19,di:5,delayed:["decks"],profile:{basement:25,groundFloor:22,firstFloor:12,facade:18,decks:10,landscape:8,servantsQuarter:20}});

let villaData = VILLAS.villa08;

/* ---- validation (console only) ---- */
(function(){const st=villaData.stages,sc=["On track","Delayed","Completed"],se=["Pending","Selected","Approved","Installed"],w=[];
Object.values(villaData.zones).forEach(z=>{if(z.progress<0||z.progress>100)w.push(z.id+" progress");if(!st.includes(z.stage))w.push(z.id+" stage");if(!sc.includes(z.scheduleStatus))w.push(z.id+" sched");z.selections.forEach(s=>{if(!se.includes(s.status))w.push(z.id+"/"+s.name);if(s.status==="Pending"&&s.option)w.push(z.id+"/"+s.name+" pending+option");});const b=z.progress===100?"Ready":z.progress>=65?"Finishing":z.progress>=35?"Structure":"Foundation";if(b!==z.stage)w.push(z.id+" band");});
console[w.length?"warn":"info"]("[villa validation]",w.length?w:"all checks passed");})();

