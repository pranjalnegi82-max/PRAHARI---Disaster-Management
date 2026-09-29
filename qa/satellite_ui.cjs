/* Browser regression for the live scene-discovery UI. Network sources are intercepted. */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');

const base=process.env.PRAHARI_UI_URL||'http://127.0.0.1:5173';
const out=process.env.PRAHARI_UI_OUTPUT||path.resolve(__dirname,'../test-results');
fs.mkdirSync(out,{recursive:true});

(async()=>{
  const browser=await chromium.launch({headless:true});
  try{
    const page=await browser.newPage({viewport:{width:1280,height:900}});
    const errors=[];
    page.on('pageerror',e=>errors.push(e.message));
    await page.addInitScript(()=>{
      sessionStorage.setItem('prahari_portal','ADMIN');
      sessionStorage.setItem('prahari_operator_key','test-only');
    });

    const locations=[
      {id:6,name:'Manali',state:'Himachal Pradesh',lat:32.2396,lon:77.1887,data_state:'CURRENT',risk_level:'UNKNOWN',risk_percent:null,sources:[],factors:[]},
      {id:17,name:'Munnar',state:'Kerala',lat:10.0889,lon:77.0595,data_state:'CURRENT',risk_level:'UNKNOWN',risk_percent:null,sources:[],factors:[]},
    ];
    const reference={id:'S2_REFERENCE',datetime:'2026-09-15T05:30:00Z',cloud_cover_pct:8,thumbnail:'https://example.invalid/ref.jpg'};
    const recent={id:'S2_RECENT',datetime:'2026-09-28T05:30:00Z',cloud_cover_pct:11,thumbnail:'https://example.invalid/recent.jpg'};

    await page.route('**/*',async route=>{
      const u=new URL(route.request().url());
      if(!u.pathname.startsWith('/api/')){
        if(u.origin===new URL(base).origin)return route.continue();
        return route.abort();
      }
      let body={};
      if(u.pathname==='/api/auth/status')body={current_role:'ADMIN',auth_required:true};
      else if(u.pathname==='/api/live/locations')body=locations;
      else if(u.pathname==='/api/alerts'||u.pathname==='/api/reports')body=[];
      else if(u.pathname==='/api/system/status')body={api:'online'};
      else if(u.pathname==='/api/data/sources')body={sources:{}};
      else if(u.pathname.startsWith('/api/satellite/sentinel2/'))body={
        status:'AVAILABLE',provider:'Element 84 Earth Search',max_cloud_pct:35,scene_count:6,
        pair:{status:'PAIR_READY',reference,recent,days_between:13}
      };
      else if(u.pathname==='/api/locations/search')body=[];
      await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(body)});
    });

    await page.goto(base);
    await page.getByRole('button',{name:'Risk Map',exact:true}).click();
    await page.getByRole('button',{name:'Sentinel-2',exact:true}).click();
    await page.getByRole('heading',{name:'Manali, Himachal Pradesh',exact:true}).waitFor();
    await page.getByText('6',{exact:true}).first().waitFor();
    assert.equal(await page.getByRole('button',{name:/Run segmentation|Prepare patch/i}).count(),0);
    assert.equal(await page.getByText(/experimental analysis|trained weights|repository/i).count(),0);

    for(const width of [320,390,1280]){
      await page.setViewportSize({width,height:844});
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true,`overflow at ${width}`);
    }
    await page.screenshot({path:path.join(out,'satellite-live-scenes.png'),fullPage:true});
    assert.deepEqual(errors,[]);
    console.log('Satellite UI passed: live scene discovery only, no experimental inference controls, responsive layout.');
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
