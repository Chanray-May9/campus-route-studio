/* Both apps use GCJ-02 tiles. Route storage and output remain WGS84. */
(function(root){
  'use strict';
  root.CampusBasemap={attach(map,options={}){
    const satellite=L.tileLayer('https://webst01.is.autonavi.com/appmaptile?style=6&x={x}&y={y}&z={z}',{maxZoom:19,attribution:'© 高德地图'});
    const labels=L.tileLayer('https://webst01.is.autonavi.com/appmaptile?style=8&x={x}&y={y}&z={z}',{maxZoom:19,attribution:'© 高德地图'});
    const streets=L.tileLayer('https://webrd01.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=7&x={x}&y={y}&z={z}',{maxZoom:19,attribution:'© 高德地图'});
    const imagery=L.layerGroup([satellite,labels]);
    L.control.layers({'卫星地图':imagery,'普通地图':streets},null,{position:'topleft',collapsed:false}).addTo(map);
    let fallback=false,errors=0,loaded=0;
    satellite.on('loading',()=>{errors=0;loaded=0;});
    const useStreets=()=>{if(!map.hasLayer(imagery)||fallback)return;fallback=true;map.removeLayer(imagery);streets.addTo(map);options.onFallback?.('卫星地图暂不可用，已切换为普通地图。');};
    satellite.on('tileload',()=>{loaded++;});
    satellite.on('tileerror',()=>{if(++errors>=3&&loaded===0)useStreets();});
    satellite.on('load',()=>{if(errors>loaded)useStreets();});
    let streetErrors=0,streetLoaded=0;
    streets.on('loading',()=>{streetErrors=0;streetLoaded=0;});
    streets.on('tileerror',()=>{if(++streetErrors>=3&&!streetLoaded)options.onUnavailable?.(true);});
    streets.on('tileload',()=>{streetLoaded++;options.onUnavailable?.(false);});
    map.on('baselayerchange',()=>{fallback=false;options.onUnavailable?.(false);});
    window.addEventListener('offline',()=>options.onUnavailable?.(true));
    window.addEventListener('online',()=>{if(map.hasLayer(imagery)){satellite.redraw();labels.redraw();}else streets.redraw();});
    imagery.addTo(map);
    return {satellite,labels,streets,imagery};
  }};
})(window);
