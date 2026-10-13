/* Planning guidance only; no access to third-party check-in or result records. */
(function(root){
  'use strict';
  function inWindow(date){const m=date.getHours()*60+date.getMinutes();return (m>=360&&m<1020)||(m>=1140&&m<1320);}
  function durationLimit(km){return km<=3?3600:7200;}
  function plan(points,km,pace){
    if(!Number.isFinite(km)||km<3||km>10||!Number.isFinite(pace)||pace<3||pace>10)throw Error('距离需为 3–10 公里，配速需为 3–10 分钟/公里');
    const distance=(a,b)=>{const r=Math.PI/180,x=Math.sin((b.lat-a.lat)*r/2),y=Math.sin((b.lon-a.lon)*r/2);return 12742017.6*Math.asin(Math.sqrt(Math.min(1,x*x+Math.cos(a.lat*r)*Math.cos(b.lat*r)*y*y)));};
    let lap=0;for(let i=1;i<points.length;i++)lap+=distance(points[i-1],points[i]);
    if(points.length>1)lap+=distance(points[points.length-1],points[0]);
    if(lap<1)throw Error('请先在地图上规划路线');
    const loops=Math.ceil(km*1000/lap);
    if(loops>10000)throw Error('路线太短，请增加路线长度');
    const total=lap*loops/1000,speed=1000/(pace*60);
    return {loops,total,speed,seconds:total*pace*60,overLimit:total>10};
  }
  const api={inWindow,durationLimit,plan};root.RunRules=api;if(typeof module!=='undefined')module.exports=api;
})(typeof window==='undefined'?globalThis:window);
