/* Browser regression fixtures are isolated from operational data. */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
(async()=>{
 const browser=await chromium.launch({headless:true});
 try{
 const page=await browser.newPage({viewport:{width:1366,height:900}});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.addInitScript(()=>{sessionStorage.setItem('prahari_portal','ADMIN');sessionStorage.setItem('prahari_operator_key','test');});
 const location={id:1,name:'Gangtok',state:'Sikkim',lat:27.3314,lon:88.6138,data_state:'CURRENT',risk_level:'UNKNOWN',sources:[],factors:[]};
 const basin={name:'Verified test catchment',context_status:'CONFIGURED',provenance:'QA fixture',thresholds_mm:{1:30,3:60,6:100},villages:[{name:'Test settlement',lat:27.33,lon:88.61}],slope_context:'QA terrain',historical_events_source:'QA inventory',station_id:null,danger_stage_m:null};
 let saved=false;
 const result=()=>({level:'HIGH',status:'SCREENED',mode:'live',location:'Gangtok',data_state:'CURRENT',source:'QA live provider fixture',valid_time:'TEST',valid_at_epoch:1,fetched_at:1,created_at:1,basin,windows:[1,3,6].map(hours=>({hours,rainfall_mm:40,screening_threshold_mm:30,exceedance_ratio:1.33,level:'HIGH'})),missing:[],soil_wetness_proxy_pct:80,antecedent_rainfall_72h_mm:240,sensor:null,sensor_used:false,version:'flood-screen-v1.0'});
 await page.route('**/api/**',async route=>{
   const u=new URL(route.request().url()); let body={};
   if(u.pathname==='/api/auth/status')body={current_role:'ADMIN',portal:'ADMIN',authenticated:true};
   else if(u.pathname==='/api/live/locations')body=[location];
   else if(['/api/alerts','/api/reports'].includes(u.pathname))body=[];
   else if(u.pathname.startsWith('/api/flood/basins/'))body=basin;
   else if(u.pathname.startsWith('/api/flood/screen/'))body=result();
   else if(u.pathname.startsWith('/api/flood/history/'))body=saved?[{id:1,assessment:result()}]:[];
   else if(u.pathname.startsWith('/api/flood/assessments/')){saved=true;body={id:1,assessment:result()};}
   await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(body)});
 });
 await page.goto(process.env.PRAHARI_UI_URL||'http://127.0.0.1:5173');
 await page.getByRole('heading',{name:'Flash Flood Intelligence',exact:true}).waitFor();
 await page.getByRole('button',{name:'Run assessment',exact:true}).click();
 await page.getByRole('status').filter({hasText:'recorded'}).waitFor();
 await page.getByText('Threshold windows',{exact:true}).waitFor();
 fs.mkdirSync('test-results',{recursive:true});
 await page.screenshot({path:'test-results/flood-desktop.png',fullPage:true});
 for(const width of [390,320]){
   await page.setViewportSize({width,height:844});
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true,`overflow at ${width}`);
 }
 await page.screenshot({path:'test-results/flood-mobile.png',fullPage:true});
 assert.deepEqual(errors,[]);
 console.log('Flood UI passed: live configured workflow, assessment history, and responsive layouts.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
