/* Browser regressions use intercepted API fixtures only. */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');

(async()=>{
 const browser=await chromium.launch({headless:true});
 try{
   const page=await browser.newPage({viewport:{width:1366,height:900}});
   const errors=[];
   page.on('pageerror',e=>errors.push(e.message));
   await page.addInitScript(()=>{
     sessionStorage.setItem('prahari_portal','ADMIN');
     sessionStorage.setItem('prahari_operator_key','test');
   });

   const location={
     id:6,name:'Manali',state:'Himachal Pradesh',country:'India',lat:32.2396,lon:77.1887,
     data_state:'CURRENT',risk_level:'UNKNOWN',risk_percent:null,sources:[],factors:[],
     assessment_status:'NOT_ASSESSED',data_completeness_pct:0
   };
   const basin={
     name:'Upper Beas test catchment',context_status:'CONFIGURED',provenance:'QA threshold reference',
     thresholds_mm:{1:30,3:60,6:100},villages:[{name:'Manali Ward',lat:32.2396,lon:77.1887}],
     slope_context:'',historical_events_source:'',station_id:null,danger_stage_m:null
   };
   let saved=false;
   const result=()=>({
     level:'HIGH',status:'SCREENED',mode:'live',location:'Manali',state:'Himachal Pradesh',
     data_state:'CURRENT',source:'Open-Meteo test provider',valid_time:'2026-09-30T10:00',
     fetched_at:1790752800,created_at:1790752800,basin,
     windows:[
       {hours:1,rainfall_mm:38,screening_threshold_mm:25,exceedance_ratio:1.52,level:'CRITICAL'},
       {hours:3,rainfall_mm:82,screening_threshold_mm:50,exceedance_ratio:1.64,level:'CRITICAL'},
       {hours:6,rainfall_mm:95,screening_threshold_mm:84,exceedance_ratio:1.13,level:'HIGH'}
     ],
     missing:[],soil_wetness_proxy_pct:80,antecedent_rainfall_72h_mm:240,
     threshold_adjustment_factor:.84,sensor:null,sensor_used:false,limitations:[],version:'flood-screen-v1.1'
   });

   await page.route('**/api/**',async route=>{
     const req=route.request();
     const u=new URL(req.url());
     let body={};
     let status=200;
     if(u.pathname==='/api/auth/status')body={current_role:'ADMIN',portal:'ADMIN',authenticated:true,auth_required:true};
     else if(u.pathname==='/api/live/locations')body=[location];
     else if(u.pathname==='/api/alerts'||u.pathname==='/api/reports')body=[];
     else if(u.pathname==='/api/system/status')body={version:'11.0.0',risk_engine:'transparent-screening',auth_required:true};
     else if(u.pathname==='/api/data/sources')body={sources:{},policy:''};
     else if(u.pathname.startsWith('/api/flood/screen/'))body=result();
     else if(u.pathname.startsWith('/api/flood/history/'))body=saved?[{id:1,assessment:result()}]:[];
     else if(u.pathname.startsWith('/api/flood/assessments/')){saved=true;status=201;body={id:1,assessment:result()};}
     else if(u.pathname==='/api/flood/records/1/draft')body={alert:{id:7}};
     else if(u.pathname.startsWith('/api/flood/basins/'))body=basin;
     else if(u.pathname==='/api/locations/search')body=[];
     else body={};
     await route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});
   });

   await page.goto(process.env.PRAHARI_UI_URL||'http://127.0.0.1:5173');
   await page.getByRole('heading',{name:'Flash Flood Monitor',exact:true}).waitFor();
   assert.equal(await page.getByRole('button',{name:'Replay',exact:true}).count(),0);
   assert.equal(await page.getByText(/SIH26192/).count(),0);
   assert.equal(await page.getByText(/demo|prototype/i).count(),0);
   assert.equal(await page.getByText('Manali, Himachal Pradesh',{exact:true}).count()>0,true);

   await page.getByRole('button',{name:'Record assessment',exact:true}).click();
   await page.getByRole('status').filter({hasText:'Assessment #1 recorded'}).waitFor();
   assert.equal(await page.getByRole('button',{name:'Create draft'}).isEnabled(),true);

   fs.mkdirSync('test-results',{recursive:true});
   await page.screenshot({path:'test-results/flood-desktop.png',fullPage:true});
   for(const width of [390,320]){
     await page.setViewportSize({width,height:844});
     assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true,`overflow at ${width}`);
   }
   await page.screenshot({path:'test-results/flood-mobile.png',fullPage:true});
   assert.deepEqual(errors,[]);
   console.log('Flood UI passed: live dashboard, record/draft flow, no replay/demo copy, responsive layout.');
 } finally {
   await browser.close();
 }
})().catch(e=>{console.error(e);process.exit(1)});
