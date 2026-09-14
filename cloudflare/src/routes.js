function num(obj,key,fallback,min,max) {
  const v=obj[key]===undefined?fallback:obj[key];
  if(typeof v!=='number'||!Number.isFinite(v)||v<min||v>max)throw Error(key+' 超出范围');return v;
}
export function routeEntry(data) {
  const id=data.id||crypto.randomUUID().replaceAll('-','');
  if(typeof id!=='string'||! /^[A-Za-z0-9_-]{1,80}$/.test(id))throw Error('轨迹标识无效');
  if(typeof data.name!=='string'||!data.name.trim()||data.name.length>80)throw Error('轨迹名称需要 1–80 个字符');
  const r=data.route;
  if(!r||!Array.isArray(r.points)||r.points.length<2||r.points.length>10000)throw Error('需要 2–10000 个路径点');
  const points=r.points.map(p=>({lat:num(p,'lat',undefined,-85,85),lon:num(p,'lon',undefined,-180,180)}));
  const speed=num(r,'speed',2.5,.2,20),loops=num(r,'loops',1,0,10000),interval=num(r,'interval',1,.2,10);
  if(!Number.isInteger(loops))throw Error('圈数必须为整数');
  const rad=Math.PI/180;let length=0;
  const measure=(a,b)=>{const v=Math.sin((b.lat-a.lat)*rad/2)**2+Math.cos(a.lat*rad)*Math.cos(b.lat*rad)*Math.sin((b.lon-a.lon)*rad/2)**2;return 6371008.8*2*Math.asin(Math.sqrt(Math.min(1,v)));};
  for(let i=1;i<points.length;i++){const d=measure(points[i-1],points[i]);if(d>1000000)throw Error('相邻路径点距离过大');length+=d;}
  if(loops!==1){const d=measure(points.at(-1),points[0]);if(d>1000000)throw Error('闭合路径距离过大');length+=d;}
  if(length<1)throw Error('路线必须至少 1 米');
  const m=data.motion||{},mode=m.mode||'fixed';if(!['fixed','smooth','alternating'].includes(mode))throw Error('速度方式无效');
  const low=num(m,'low',speed,.2,20);
  return {id,name:data.name.trim(),route:{points,speed,loops,interval},motion:{mode,speed:num(m,'speed',speed,.2,20),low,high:num(m,'high',speed,low,20),period:num(m,'period',10,2,120),sway:num(m,'sway',0,0,3),swayPeriod:num(m,'swayPeriod',4,2,30)}};
}
