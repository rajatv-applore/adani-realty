/* ============================================================
   2. DATA MODEL, single source of truth
      The North Park, Phase 8: 28 villas (D-15 … D-38), 4 BHK, ground + two floors
      with a terrace garden. Finishes follow Adani's published specification.
      Owners, progress and dates are demo data.
   ============================================================ */
const VILLAS = {};
VILLAS.d28 = {
  property:{ developer:"Adani Realty", project:"The North Park", name:"Villa D-28", client:"Rajesh & Meera Shah", type:"4 BHK Villa", location:"Shantigram, Ahmedabad", configuration:"4 BHK", overallProgress:54, asOf:"29 Oct 2026", isDemoData:true },
  stages:["Foundation","Structure","Finishing","Ready"],
  zones:{
    groundFloor:{ id:"groundFloor", name:"Ground Floor", progress:82, stage:"Finishing", scheduleStatus:"On track", targetDate:"15 Jan 2027",
      description:"The drawing room, dining and family area, guest bedroom, kitchen and puja room are built and plastered. Flooring, fittings and joinery are now going in.",
      selections:[
        {name:"Drawing and dining flooring", option:"Italian marble", status:"Installed", note:"Italian marble laid across the drawing room, dining and family area, foyer and staircase."},
        {name:"Guest bedroom flooring", option:"Large-format vitrified tiles", status:"Approved", note:"Large-format vitrified tiles approved for the guest bedroom."},
        {name:"Kitchen counter and sink", option:null, status:"Pending", note:"Your preferred kitchen counter and sink are yet to be finalised."},
        {name:"Main door", option:"Veneer flush door with timber moulding", status:"Selected", note:"A veneer-finished flush door with timber moulding and architrave selected for the entrance."},
        {name:"Puja room finish", option:"Italian marble", status:"Approved", note:"Italian marble approved for the puja room."}
      ]},
    firstFloor:{ id:"firstFloor", name:"First Floor", progress:68, stage:"Finishing", scheduleStatus:"On track", targetDate:"28 Feb 2027",
      description:"Both master suites, their dressing rooms and toilets, and the lounge and library are enclosed and plastered. Finishing work has started.",
      selections:[
        {name:"Bedroom flooring", option:"Italian marble", status:"Selected", note:"Italian marble selected for both master bedrooms."},
        {name:"Bathroom fittings", option:"Kohler or equivalent", status:"Approved", note:"Kohler (or equivalent) fittings with wall-hung WCs and glass shower cubicles approved."},
        {name:"Wardrobe finish", option:null, status:"Pending", note:"Your preferred wardrobe finish for the dressing rooms is yet to be finalised."},
        {name:"Lounge flooring", option:"Large-format vitrified tiles", status:"Selected", note:"Large-format vitrified tiles selected for the lounge and library."}
      ]},
    secondFloor:{ id:"secondFloor", name:"Second Floor", progress:52, stage:"Structure", scheduleStatus:"On track", targetDate:"30 Apr 2027",
      description:"The top floor, with the third master suite, the lounge and the study area, is rising in concrete and blockwork.",
      selections:[
        {name:"Bedroom flooring", option:"Italian marble", status:"Selected", note:"Italian marble selected for the third master bedroom."},
        {name:"Terrace doors", option:"Aluminium sliding doors, powder-coated", status:"Approved", note:"Full-height powder-coated aluminium sliding doors approved between the lounge and the terrace."},
        {name:"Bathroom fittings", option:null, status:"Pending", note:"Your preferred fittings for the second-floor bathroom are yet to be finalised."}
      ]},
    facade:{ id:"facade", name:"Façade", progress:45, stage:"Structure", scheduleStatus:"On track", targetDate:"31 May 2027",
      description:"The exterior walls are up. The sand and charcoal textured finish, the deep window frames and the car-porch canopy follow once plastering is complete.",
      selections:[
        {name:"Exterior colour scheme", option:"Sand and charcoal textured finish", status:"Approved", note:"The sand and charcoal textured exterior finish has been approved."},
        {name:"Window frames", option:"Aluminium, powder-coated", status:"Selected", note:"Powder-coated aluminium window frames selected throughout."},
        {name:"Car-porch canopy", option:"Steel louvred canopy", status:"Selected", note:"A steel louvred canopy selected over the car porch."},
        {name:"Façade lighting", option:null, status:"Pending", note:"Your preferred façade lighting is yet to be finalised."}
      ]},
    decks:{ id:"decks", name:"Balcony & Terrace Garden", progress:40, stage:"Structure", scheduleStatus:"On track", targetDate:"30 Jun 2027",
      description:"The first-floor balcony, the dining deck and the second-floor terrace garden are cast. Waterproofing, railings and landscaping come next.",
      selections:[
        {name:"Terrace finish", option:"Artificial lawn with a timber deck", status:"Selected", note:"An artificial lawn with a timber deck selected for the terrace garden."},
        {name:"Railings", option:"Frameless glass, timber handrail", status:"Approved", note:"Frameless glass railings with a timber handrail approved for the balcony and terrace."},
        {name:"Pergola", option:null, status:"Pending", note:"Your preferred pergola for the terrace deck is yet to be finalised."},
        {name:"Outdoor lighting", option:null, status:"Pending", note:"Your preferred outdoor lighting is yet to be finalised."}
      ]},
    landscape:{ id:"landscape", name:"Garden & Driveway", progress:20, stage:"Foundation", scheduleStatus:"On track", targetDate:"31 Jul 2027",
      description:"Ground preparation is underway for the front lawn, the side garden and the two-car driveway. Boundary walls, paving and planting will follow.",
      selections:[
        {name:"Garden planting", option:"Layered tropical palette", status:"Selected", note:"A layered tropical planting palette selected for the front lawn and side garden."},
        {name:"Driveway paving", option:"Interlocking pavers", status:"Approved", note:"Interlocking pavers approved for the driveway and side passage."},
        {name:"Gates", option:null, status:"Pending", note:"Your preferred gate design is yet to be finalised."},
        {name:"Landscape lighting", option:null, status:"Pending", note:"Your preferred landscape lighting is yet to be finalised."}
      ]},
    servantsQuarter:{ id:"servantsQuarter", name:"Servant Quarter", progress:70, stage:"Finishing", scheduleStatus:"On track", targetDate:"31 Jan 2027",
      description:"The servant room, toilet and hand-wash area at the rear are built and plastered, with flooring and fittings now underway.",
      selections:[
        {name:"Flooring", option:"Vitrified tiles", status:"Approved", note:"Vitrified tiles approved for the servant room."},
        {name:"Door", option:"Laminate flush door", status:"Selected", note:"A laminate-finished flush door selected for the servant room."},
        {name:"Toilet fittings", option:null, status:"Pending", note:"Your preferred toilet fittings are yet to be finalised."}
      ]}
  },
  milestones:[
    {id:"m1", name:"Design and approvals", state:"completed", date:"10 Jun 2025", desc:"The villa design, specifications and RERA registration were completed."},
    {id:"m2", name:"Foundation work", state:"completed", date:"30 Sep 2025", desc:"The foundations and plinth were completed, setting the base for your home."},
    {id:"m3", name:"Main structural work", state:"inprogress", date:"Target 15 Dec 2026", desc:"The concrete frame and walls across the ground, first and second floors."},
    {id:"m4", name:"Interior and exterior finishing", state:"inprogress", date:"Target 30 Jun 2027", desc:"Surfaces, fittings and the details that bring your home together, inside and out."},
    {id:"m5", name:"Final inspection", state:"upcoming", date:"Target 15 Sep 2027", desc:"A thorough quality and handover inspection before your home is ready to receive you."},
    {id:"m6", name:"Home handover", state:"upcoming", date:"Target 30 Oct 2027", desc:"The moment your finished home is handed over and the keys become yours."}
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
const ZONE_ORDER=[["groundFloor","Ground Floor"],["firstFloor","First Floor"],["secondFloor","Second Floor"],["facade","Façade"],["decks","Balcony & Terrace Garden"],["landscape","Garden & Driveway"],["servantsQuarter","Servant Quarter"]];
const CATALOG={
  groundFloor:[["Drawing and dining flooring","Italian marble"],["Guest bedroom flooring","Large-format vitrified tiles"],["Kitchen counter and sink","Vitrified top, stainless steel sink"],["Main door","Veneer flush door with timber moulding"],["Puja room finish","Italian marble"]],
  firstFloor:[["Bedroom flooring","Italian marble"],["Bathroom fittings","Kohler or equivalent"],["Wardrobe finish","Smoked oak laminate"],["Lounge flooring","Large-format vitrified tiles"]],
  secondFloor:[["Bedroom flooring","Italian marble"],["Terrace doors","Aluminium sliding doors, powder-coated"],["Bathroom fittings","Kohler or equivalent"]],
  facade:[["Exterior colour scheme","Sand and charcoal textured finish"],["Window frames","Aluminium, powder-coated"],["Car-porch canopy","Steel louvred canopy"],["Façade lighting","Warm wall washers"]],
  decks:[["Terrace finish","Artificial lawn with a timber deck"],["Railings","Frameless glass, timber handrail"],["Pergola","Steel pergola with timber slats"],["Outdoor lighting","Warm ambient fixtures"]],
  landscape:[["Garden planting","Layered tropical palette"],["Driveway paving","Interlocking pavers"],["Gates","Timber-slat sliding gate"],["Landscape lighting","Low-glare fixtures"]],
  servantsQuarter:[["Flooring","Vitrified tiles"],["Door","Laminate flush door"],["Toilet fittings","Kohler or equivalent"]]
};
function deriveStatus(i,n,p){const t=(i+0.5)/n*100;if(p>=t+22)return "Installed";if(p>=t+6)return "Approved";if(p>=t-16)return "Selected";return "Pending";}
function deriveSelections(zoneId,p){const cat=CATALOG[zoneId]||[],n=cat.length;return cat.map((c,i)=>{const status=deriveStatus(i,n,p),pend=status==="Pending";
  return {name:c[0],option:pend?null:c[1],status,note:pend?("Your preferred "+c[0].toLowerCase()+" is yet to be finalised."):(c[1]+", "+status.toLowerCase()+".")};});}
const DATE_POOL=["15 Jan 2027","31 Jan 2027","28 Feb 2027","31 Mar 2027","30 Apr 2027","31 May 2027","30 Jun 2027","31 Jul 2027"];
function buildMilestones(ov){const m=[
  {name:"Design and approvals",date:"10 Jun 2025",state:"completed",desc:"The villa design, specifications and RERA registration were completed."},
  {name:"Foundation work",date:"30 Sep 2025",state:ov>=20?"completed":"inprogress",desc:"The foundations and plinth for your home."},
  {name:"Main structural work",date:"Target 15 Dec 2026",state:ov>=60?"completed":(ov>=20?"inprogress":"upcoming"),desc:"The concrete frame and walls across the ground, first and second floors."},
  {name:"Interior and exterior finishing",date:"Target 30 Jun 2027",state:ov>=95?"completed":(ov>=40?"inprogress":"upcoming"),desc:"Surfaces, fittings and the details that bring your home together."},
  {name:"Final inspection",date:"Target 15 Sep 2027",state:ov>=98?"completed":"upcoming",desc:"A thorough quality and handover inspection before your home is ready."},
  {name:"Home handover",date:"Target 30 Oct 2027",state:"upcoming",desc:"The moment your finished home is handed over and the keys become yours."}];
  return m.map((x,i)=>Object.assign({id:"m"+(i+1)},x));}
function buildVilla(meta){const zones={};
  ZONE_ORDER.forEach((zd,idx)=>{const id=zd[0],name=zd[1],p=meta.profile[id],stage=bandStage(p),delayed=(meta.delayed||[]).indexOf(id)>=0;
    zones[id]={id,name,progress:p,stage,scheduleStatus:p>=100?"Completed":(delayed?"Delayed":"On track"),targetDate:DATE_POOL[(idx+(meta.di||0))%DATE_POOL.length],description:name+", "+STAGE_DESC[stage],selections:deriveSelections(id,p)};});
  return {property:{developer:"Adani Realty",project:meta.project||"The North Park",name:meta.villa,client:meta.client,type:"4 BHK Villa",configuration:"4 BHK",location:"Shantigram, Ahmedabad",overallProgress:meta.overall,asOf:"29 Oct 2026",isDemoData:true},stages:STAGES4,zones,milestones:buildMilestones(meta.overall)};}
VILLAS.d17=buildVilla({villa:"Villa D-17",client:"Anita Desai",overall:63,di:1,delayed:["landscape"],profile:{groundFloor:85,firstFloor:72,secondFloor:66,facade:55,decks:50,landscape:25,servantsQuarter:90}});
VILLAS.d23=buildVilla({villa:"Villa D-23",client:"Vikram & Leela Patel",overall:79,di:2,profile:{groundFloor:95,firstFloor:88,secondFloor:80,facade:75,decks:68,landscape:55,servantsQuarter:95}});
VILLAS.d30=buildVilla({villa:"Villa D-30",client:"The Nair Family",overall:41,di:3,delayed:["secondFloor"],profile:{groundFloor:66,firstFloor:52,secondFloor:30,facade:36,decks:28,landscape:15,servantsQuarter:60}});
VILLAS.d35=buildVilla({villa:"Villa D-35",client:"S. Krishnan",overall:70,di:4,profile:{groundFloor:90,firstFloor:80,secondFloor:70,facade:66,decks:55,landscape:40,servantsQuarter:85}});
VILLAS.d19a=buildVilla({villa:"Villa D-19A",client:"Aarav & Diya Mehta",overall:24,di:5,delayed:["decks"],profile:{groundFloor:45,firstFloor:30,secondFloor:12,facade:20,decks:10,landscape:8,servantsQuarter:40}});

let villaData = VILLAS.d28;

/* ---- validation (console only) ---- */
(function(){const st=villaData.stages,sc=["On track","Delayed","Completed"],se=["Pending","Selected","Approved","Installed"],w=[];
Object.values(villaData.zones).forEach(z=>{if(z.progress<0||z.progress>100)w.push(z.id+" progress");if(!st.includes(z.stage))w.push(z.id+" stage");if(!sc.includes(z.scheduleStatus))w.push(z.id+" sched");z.selections.forEach(s=>{if(!se.includes(s.status))w.push(z.id+"/"+s.name);if(s.status==="Pending"&&s.option)w.push(z.id+"/"+s.name+" pending+option");});const b=z.progress===100?"Ready":z.progress>=65?"Finishing":z.progress>=35?"Structure":"Foundation";if(b!==z.stage)w.push(z.id+" band");});
console[w.length?"warn":"info"]("[villa validation]",w.length?w:"all checks passed");})();
