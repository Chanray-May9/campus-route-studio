const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const assert=require('node:assert/strict');
const samples=[
  {lat:29.51264659,lon:106.69253011},
  {lat:29.51185,lon:106.69285},
  {lat:30.2741,lon:120.1551},
  {lat:39.9042,lon:116.4074},
  {lat:31.2304,lon:121.4737},
  {lat:51.5074,lon:-.1278}
];
function load(relative){const context={};vm.runInNewContext(fs.readFileSync(path.resolve(__dirname,'..',relative),'utf8'),context);return context.CampusCoords;}
const desktop=load('route_studio/web/vendor/coord.js');
const mobile=load('mobile/assets/vendor/coord.js');
let maxMeters=0;
for(const point of samples){
  const a=desktop.wgsToGcj(point),b=mobile.wgsToGcj(point);
  assert.ok(Math.abs(a.lat-b.lat)<1e-12&&Math.abs(a.lon-b.lon)<1e-12,'frontends disagree');
  for(const converter of [desktop,mobile]){
    let current={...point};
    for(let i=0;i<100;i++)current=converter.gcjToWgs(converter.wgsToGcj(current));
    const error=Math.hypot((current.lat-point.lat)*111320,(current.lon-point.lon)*111320*Math.cos(point.lat*Math.PI/180));
    maxMeters=Math.max(maxMeters,error);
    assert.ok(error<.001,'coordinate drift after repeated map edits: '+error+' m');
  }
  if(point.lon<0)assert.ok(a.lat===point.lat&&a.lon===point.lon,'coordinates outside China changed');
}
console.log('PASS: desktop/mobile coordinates agree; 100 map round trips at six landmarks, maximum numeric drift '+maxMeters.toFixed(8)+' m. This does not measure imagery accuracy.');
