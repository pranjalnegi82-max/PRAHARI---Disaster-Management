export const value=(v,d=1)=>v==null||!Number.isFinite(Number(v))?'—':Number(v).toFixed(d);
export const date=v=>v?new Date(v*1000).toLocaleString():'Unavailable';
export function freshness(result,now=Date.now()/1000){
 if(!result)return 'Loading';
 if(result.data_state==='MISSING')return 'Unavailable';
 const age=now-result.valid_at_epoch;
 if(!result.valid_at_epoch||age<0)return 'Time unverified';
 return result.data_state==='STALE'||age>10800?'Stale':'Current';
}
export function draftEligible(result,recordId,now=Date.now()/1000){
 return !!(recordId&&result?.basin?.context_status==='CONFIGURED'&&freshness(result,now)==='Current'&&result.status==='SCREENED'&&['HIGH','CRITICAL'].includes(result.level)&&now-result.created_at>=0&&now-result.created_at<=900);
}
const names={soil_wetness_proxy_pct:'Soil wetness',antecedent_rainfall_72h_mm:'72-hour rainfall',weather_packet:'Weather feed',current_provider_timestamp:'Provider timestamp',slope:'Terrain gradient'};
export const missingLabel=k=>names[k]||k.replace('rain_forecast_','Next ').replace('h_mm','-hour rainfall').replaceAll('_',' ');
export function historyCsv(rows){
 const cell=v=>`"${String(v??'').replace(/^[=+@-]/,"'$&").replaceAll('"','""')}"`;
 const header=['Record','Area','Recorded UTC','Provider UTC','Level','Data state','Profile','1h rainfall mm','3h rainfall mm','6h rainfall mm','Source'];
 const stamp=v=>v?new Date(v*1000).toISOString():'';
 return [header,...rows.map(({id,assessment:a})=>[id,a.location,stamp(a.created_at),stamp(a.valid_at_epoch),a.level,a.data_state,a.basin?.context_status,...[1,3,6].map(h=>a.windows?.find(w=>w.hours===h)?.rainfall_mm),a.source])].map(r=>r.map(cell).join(',')).join('\r\n');
}
