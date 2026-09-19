(function (root) {
  'use strict';
  const PI = Math.PI, A = 6378245.0, EE = 0.006693421622965943;
  function outsideChina(lat, lon) { return lon < 72.004 || lon > 137.8347 || lat < 0.8293 || lat > 55.8271; }
  function transformLat(x, y) {
    let v = -100 + 2*x + 3*y + .2*y*y + .1*x*y + .2*Math.sqrt(Math.abs(x));
    v += (20*Math.sin(6*x*PI)+20*Math.sin(2*x*PI))*2/3;
    v += (20*Math.sin(y*PI)+40*Math.sin(y/3*PI))*2/3;
    return v + (160*Math.sin(y/12*PI)+320*Math.sin(y*PI/30))*2/3;
  }
  function transformLon(x, y) {
    let v = 300 + x + 2*y + .1*x*x + .1*x*y + .1*Math.sqrt(Math.abs(x));
    v += (20*Math.sin(6*x*PI)+20*Math.sin(2*x*PI))*2/3;
    v += (20*Math.sin(x*PI)+40*Math.sin(x/3*PI))*2/3;
    return v + (150*Math.sin(x/12*PI)+300*Math.sin(x/30*PI))*2/3;
  }
  function wgsToGcj(p) {
    const lat=Number(p.lat),lon=Number(p.lon); if(outsideChina(lat,lon))return {lat,lon};
    let dLat=transformLat(lon-105,lat-35),dLon=transformLon(lon-105,lat-35),rad=lat/180*PI,magic=Math.sin(rad);
    magic=1-EE*magic*magic;const rootMagic=Math.sqrt(magic);
    dLat=dLat*180/((A*(1-EE))/(magic*rootMagic)*PI);dLon=dLon*180/(A/rootMagic*Math.cos(rad)*PI);
    return {lat:lat+dLat,lon:lon+dLon};
  }
  function gcjToWgs(p) {
    const lat=Number(p.lat),lon=Number(p.lon);if(outsideChina(lat,lon))return {lat,lon};let g={lat,lon};
    for(let i=0;i<8;i++){const s=wgsToGcj(g);g={lat:g.lat+lat-s.lat,lon:g.lon+lon-s.lon};}return g;
  }
  root.CampusCoords={wgsToGcj,gcjToWgs,outsideChina};
})(typeof globalThis==='object'?globalThis:window);
