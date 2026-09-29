/* UI regressions use synthetic API fixtures, never operational data. */
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
 const basin={name:'Synthetic test catchment',context_status:'DEMO',provenance:'Synthetic fixture, no surveyed catchment.',thresholds_mm:{1:30,3:60,6:100},villages:[{name:'Demo village',lat:27.33,lon:88.61}],slope_context:'Demo terrain',historical_events_source:'No verified inventory',station_id:null,danger_stage_m:null};
 let saved=false,mode='live';
 const result=()=>({level:'HIGH',status:'SCREENED',mode,location:'Gangtok',data_state:mode==='live'?'CURRENT':'HISTORICAL_REPLAY',source:'SYNTHETIC TEST DATA',valid_time:'TEST ONLY',fetched_at:1,created_at:1,basin,windows:[1,3,6].map(hours=>({hours,rainfall_mm:40,screening_threshold_mm:30,exceedance_ratio:1.33,level:'HIGH'})),missing:[],soil_wetness_proxy_pct:80,antecedent_rainfall_72h_mm:240,sensor:null,limitations:['Synthetic test fixture'],version:'flood-screen-v1.0'});
 await page.route('**/api/**',async route=>{
 const u=new URL(route.request().url()); let body={};
 if(u.pathname==='/api/auth/status')body={current_role:'ADMIN',portal:'ADMIN',authenticated:true};
 else if(u.pathname==='/api/live/locations')body=[location];
 else if(['/api/alerts','/api/reports'].includes(u.pathname))body=[];
 else if(u.pathname.startsWith('/api/flood/screen/')){mode=u.searchParams.get('mode');body=result();}
 else if(u.pathname.startsWith('/api/flood/history/'))body=saved?[{id:1,assessment:result()}]:[];
 else if(u.pathname.startsWith('/api/flood/assessments/')){saved=true;body={id:1,assessment:result()};}
 else if(u.pathname.startsWith('/api/flood/basins/'))body=basin;
 await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(body)});
 });
 await page.goto(process.env.PRAHARI_UI_URL||'http://127.0.0.1:5173');
 await page.getByRole('heading',{name:'Flash Floods',exact:true}).waitFor();
 await page.getByRole('button',{name:'Record flood assessment',exact:true}).click();
 await page.getByRole('status').filter({hasText:'recorded'}).waitFor();
 assert.equal(await page.getByRole('button',{name:'Create reviewed-workflow draft'}).isDisabled(),true);
 await page.getByRole('button',{name:'Replay',exact:true}).click();
 await page.getByText('Synthetic storm scenario',{exact:true}).waitFor();
 fs.mkdirSync('test-results',{recursive:true});
 await page.screenshot({path:'test-results/flood-desktop.png',fullPage:true});
 for(const width of [390,320]){
 await page.setViewportSize({width,height:844});
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true,`overflow at ${width}`);
 }
 await page.screenshot({path:'test-results/flood-mobile.png',fullPage:true});
 assert.deepEqual(errors,[]);
 console.log('Flood UI passed: admin landing, recording, replay, demo draft guard, 390/320px layouts, no page errors.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
