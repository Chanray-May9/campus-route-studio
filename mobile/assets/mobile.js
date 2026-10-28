(() => {
  'use strict';
  const $=id=>document.getElementById(id);
  const toMap=p=>CampusCoords.wgsToGcj(p),fromMap=p=>CampusCoords.gcjToWgs(p);
  let points=[],entries=[],map=null,layer=null,markers=null,current=null,active=false,paused=false,busy=false;
  function notice(text,error=false){$('notice').textContent=text;$('notice').hidden=!text;$('notice').classList.toggle('error',error);}
  function native(action,data={}){if(!window.Native)throw Error('请在校园乐跑助手安卓 App 中使用此功能。');const response=JSON.parse(Native.request(action,JSON.stringify(data)));if(!response.ok)throw Error(response.error);return response.data;}
  function action(work){try{work();}catch(e){notice(e.message,true);}}
  function simplePlan(){return RunRules.plan(points,Number($('goal').value),Number($('pace').value));}
  function applyPreset(){
    if($('preset-mode').value!=='simple')return;
    const p=simplePlan();$('speed').value=p.speed;$('loops').value=p.loops;$('loop-mode').value='finite';$('speed-mode').value='fixed';$('low').value=p.speed;$('high').value=p.speed;$('sway').value=0;
  }
  function previewPlan(){
    if($('preset-mode').value==='simple'){
      try{const p=simplePlan();$('plan-summary').textContent='自动闭合路线 · '+p.loops+' 圈 · 约 '+p.total.toFixed(2)+' 公里 · 约 '+Math.ceil(p.seconds/60)+' 分钟'+(p.overLimit?'；整圈超过 10 公里，请调整路线。':'');}catch(e){$('plan-summary').textContent=e.message;}
    }else $('plan-summary').textContent='使用高级设置中的速度与圈数。请自行核对距离、配速和时长。';
  }
  function settings(){
    applyPreset();
    const speed=Number($('speed').value),loops=$('loop-mode').value==='infinite'?0:Number($('loops').value);
    if(!Number.isFinite(speed)||speed<.2||speed>20||!Number.isInteger(loops)||loops<0||loops>10000||(loops===0&&$('loop-mode').value!=='infinite'))throw Error('速度或圈数超出范围');
    return {route:{points:($('preset-mode').value==='simple'&&points.length&&(points[points.length-1].lat!==points[0].lat||points[points.length-1].lon!==points[0].lon)?[...points,points[0]]:points).map(p=>({...p})),speed,loops},motion:motion(),acknowledged:$('ack').checked};
  }
  function motion(){const result={mode:$('speed-mode').value,speed:Number($('speed').value),low:Number($('low').value),high:Number($('high').value),period:Number($('period').value),sway:Number($('sway').value),swayPeriod:Number($('sway-period').value)};if(Object.values(result).some(v=>typeof v==='number'&&!Number.isFinite(v)))throw Error('请填写有效运动参数');return result;}
  function validate(list){if(!Array.isArray(list)||list.length<2||list.length>10000)throw Error('路线需要 2–10000 个路径点');return list.map(p=>{const lat=Number(p.lat),lon=Number(p.lon);if(!Number.isFinite(lat)||!Number.isFinite(lon)||Math.abs(lat)>85||Math.abs(lon)>180)throw Error('坐标无效');return {lat,lon};});}
  function length(){let sum=0;for(let i=1;i<points.length;i++)sum+=L.latLng(points[i-1].lat,points[i-1].lon).distanceTo(L.latLng(points[i].lat,points[i].lon));return sum;}
  function render(fit=false){layer.setLatLngs(points.map(p=>{const d=toMap(p);return[d.lat,d.lon];}));markers.clearLayers();points.forEach((p,i)=>{const d=toMap(p),m=L.marker([d.lat,d.lon],{draggable:!active,icon:L.divIcon({className:'point',html:String(i+1),iconSize:[24,24],iconAnchor:[12,12]})}).addTo(markers);m.on('dragend',()=>{if(!active){const ll=m.getLatLng(),w=fromMap({lat:ll.lat,lon:ll.lng});points[i]={lat:w.lat,lon:((w.lon+180)%360+360)%360-180};render();}});});$('route-summary').textContent=`${points.length} 个路径点 · ${Math.round(length())} 米`;previewPlan();if(fit&&points.length>1)map.fitBounds(layer.getBounds(),{padding:[24,24],maxZoom:18});}
  function refreshLibrary(){entries=native('library').entries;const selected=$('saved-routes').value;$('saved-routes').replaceChildren(new Option('请选择路线',''));entries.forEach(e=>$('saved-routes').append(new Option(e.name,e.id)));if(entries.some(e=>e.id===selected))$('saved-routes').value=selected;}
  function restore(e){if(active)throw Error('请先停止跑步再载入路线');$('preset-mode').value='custom';points=validate(e.route.points);$('speed').value=e.route.speed;$('loop-mode').value=e.route.loops===0?'infinite':'finite';$('loops').value=e.route.loops||1;const m=e.motion||{};for(const [id,key,def] of [['low','low',2],['high','high',3],['period','period',10],['sway','sway',0],['sway-period','swayPeriod',4]])$(id).value=m[key]??def;$('speed-mode').value=m.mode||'fixed';$('speed').value=m.speed??e.route.speed;$('route-name').value=e.name||'';$('ack').checked=false;render(true);updateControls();}
  function updateControls(){['clear','undo','close-loop','sample','add-coordinate','import','load','remote'].forEach(id=>$(id).disabled=active);$('start').disabled=active;$('pause').disabled=!active;$('stop').disabled=!active;$('tune').disabled=!active;$('pause').textContent=paused?'继续跑步':'暂停跑步';['preset-mode','goal','pace'].forEach(id=>$(id).disabled=active);const simple=$('preset-mode').value==='simple';['speed','speed-mode','low','high','period','sway','sway-period'].forEach(id=>$(id).disabled=simple);$('loops').disabled=active||simple||$('loop-mode').value==='infinite';$('loop-mode').disabled=active||simple;}
  function status(){if(busy)return;try{const run=native('status');active=['starting','running','paused'].includes(run.state);paused=run.state==='paused';const names={idle:'尚未开始',starting:'正在启动',running:'跑步中',paused:'已暂停',completed:'已完成',interrupted:'等待系统恢复',error:'跑步出错'};$('status').textContent=`${names[run.state]||run.state} · 累计 ${Math.round(run.distance||0)} 米 · 完成 ${run.laps||0} 圈${run.infinite?' · 无限循环':''}${run.providers?.length?' · '+run.providers.join('+'):''}`;if(run.point){const confirmed=run.observedPoint&&run.observedAge<2.5,shown=confirmed?run.observedPoint:run.point;$('position').textContent=`${confirmed?'系统位置':'路线位置（待系统确认）'} ${shown.lat.toFixed(7)}, ${shown.lon.toFixed(7)} · ${run.point.speed.toFixed(2)} m/s（设定速度） · 已发送 ${run.sent} 次`;const d=toMap(shown);if(!current)current=L.circleMarker([d.lat,d.lon],{radius:8,color:'#fff',fillColor:'#ed995b',fillOpacity:1,weight:3}).addTo(map);else current.setLatLng([d.lat,d.lon]);}$('window-status').textContent=(RunRules.inWindow(new Date())?'当前处于参考跑步时段。':'当前不在参考跑步时段（06:00–17:00 / 19:00–22:00）。')+' 时段按手机本地时间显示。';
    if(run.setup){
      const setup=run.setup,missing=[];
      if(setup.developerEnabled===false&&!setup.mockSelected)missing.push('开发者选项尚未开启');
      if(!setup.mockSelected)missing.push('尚未选择校园乐跑助手为模拟位置应用');
      if(!setup.finePermission)missing.push('尚未授予精确位置权限');
      if(!setup.locationEnabled)missing.push('系统定位开关未开启');
      $('setup-status').textContent=missing.length?'开始前需完成：'+missing.join('；'):'手机定位设置已就绪；请在乐跑核对实际位置。';
      const background=[];
      if(setup.backgroundRestricted)background.push('系统限制后台运行，请在应用设置解除限制');
      if(setup.batteryExempt===false)background.push('尚未豁免电池优化，可在电池设置中选择不限制');
      if(setup.backgroundPermission===false)background.push('未授权始终访问位置；如后台更新异常，可在后台位置设置中授权');
      if(setup.notificationsEnabled===false)background.push('通知已关闭，无法从通知栏查看和停止服务');
      $('background-status').textContent=background.join('；');
      $('restart-enabled').checked=setup.restartEnabled!==false;$('restart-enabled').disabled=active;
      $('developer').textContent=setup.developerEnabled===false&&!setup.mockSelected?'开启开发者选项':'选择模拟位置应用';
      if(setup.developerEnabled===false&&!setup.mockSelected)$('developer-help').open=true;
    }
    const warnings=Object.entries(run.providerErrors||{}).map(([p,e])=>p+'：'+e);
    if(active&&(run.sendAge>5||run.maxSendGap>5))warnings.push('后台发送曾中断，最长间隔 '+Math.round(Math.max(run.sendAge||0,run.maxSendGap||0))+' 秒，请解除后台和电池限制');
    $('diagnostic').textContent=active||run.state==='completed'?('GPS/网络回调 '+(run.received||0)+' 次 · 系统融合回调 '+(run.fusedReceived||0)+' 次 · 系统坐标累计移动 '+Math.round(run.receivedMovement||0)+' 米 · 含暂停 '+Math.floor((run.wallElapsed||0)/60)+' 分钟'+((run.wallElapsed||0)>10&&((run.received||0)===0||(run.observedAge||0)>10)?'；系统定位回调尚未更新，请检查定位与后台设置。':'')+((run.total||run.distance||0)<10000&&(run.wallElapsed||0)>RunRules.durationLimit((run.total||run.distance||0)/1000)?'；已超过参考时长限制。':'')+(run.restores?' · 系统恢复 '+run.restores+' 次':'')+(warnings.length?'；部分定位通道异常：'+warnings.join('；'):'')):'';
    if(run.error||run.cleanupError)notice([run.error,run.cleanupError].filter(Boolean).join('\n'),true);updateControls();}catch(e){notice(e.message,true);}}
  function setupMap(){const p=toMap({lat:30.2741,lon:120.1551});map=L.map('map',{worldCopyJump:true}).setView([p.lat,p.lon],15);CampusBasemap.attach(map,{onFallback:text=>{$('map-message').textContent=text;},onUnavailable:value=>{$('map-message').textContent=value?'地图暂不可用，仍可输入坐标或导入路线。':'点击地图添加路线点，拖动调整。';}});layer=L.polyline([],{color:'#0c7464',weight:4}).addTo(map);markers=L.layerGroup().addTo(map);map.on('click',e=>{if(!active&&points.length<10000){const w=fromMap({lat:e.latlng.lat,lon:e.latlng.lng});points.push({lat:w.lat,lon:((w.lon+180)%360+360)%360-180});render();}});}
  $('permission').onclick=()=>action(()=>native('permissions'));$('developer').onclick=()=>action(()=>{const result=native('developerSettings');notice(result.message);if(!result.openedDeveloper)$('developer-help').open=true;});$('about-phone').onclick=()=>action(()=>{native('aboutPhone');notice('在关于手机或软件信息中找到版本号，连续点击约 7 次。开启后返回设置搜索开发者选项。');});
  $('background-settings').onclick=()=>action(()=>{native('backgroundSettings');notice('在应用权限中打开位置，若有“始终允许”可选则按需授权；厂商的后台运行和自启动开关也需手动检查。');});
  $('battery-settings').onclick=()=>action(()=>{const result=native('batterySettings');notice(result.alreadyGranted?'已豁免系统电池优化；仍需检查厂商的后台运行和自启动开关。':'请在系统弹窗允许电池优化豁免；若没有弹窗，请在应用设置中将电池策略设为不限制。');});
  $('restart-enabled').onchange=()=>action(()=>{native('restartPreference',{enabled:$('restart-enabled').checked});status();});
  $('start').onclick=()=>action(()=>{if(points.length<2||length()<1)throw Error('请先规划至少 1 米的路线');if(!$('ack').checked)throw Error('请先核对学校场地要求并勾选确认');const config=settings();if($('preset-mode').value==='simple'&&simplePlan().overLimit)throw Error('整圈距离超过 10 公里，请缩短路线或使用自定义参数');const started=native('start',config);if(started.state!=='running'||!started.point||!(started.sent>0))throw Error('尚未确认首个坐标发送成功');active=true;render();status();updateControls();notice('首个坐标已发送。先确认目标 App 的位置已更新，再在目标 App 开始跑步；发送成功不代表目标 App 已接收。');});
  $('pause').onclick=()=>action(()=>{native(paused?'resume':'pause');status();});$('stop').onclick=()=>action(()=>{native('stop');status();render();notice('已结束跑步，已移除本次模拟定位。');});$('tune').onclick=()=>action(()=>{applyPreset();native('tune',motion());notice('新速度和摆动参数已应用。');});
  $('locate').onclick=()=>action(()=>{const p=native('location'),d=toMap(p);map.setView([d.lat,d.lon],16);notice(`已定位到近期手机位置，精度约 ${Math.round(p.accuracy)} 米。`);});
  $('clear').onclick=()=>{if(!active){points=[];render();}};$('undo').onclick=()=>{if(!active){points.pop();render();}};$('close-loop').onclick=()=>{if(!active&&points.length>1){points.push({...points[0]});render();}};
  $('sample').onclick=()=>{if(!active){points=[{lat:30.274,lon:120.155},{lat:30.275,lon:120.155},{lat:30.275,lon:120.156},{lat:30.274,lon:120.156},{lat:30.274,lon:120.155}];render(true);notice('示例仅用于编辑演示，请按实际学校位置重新规划。');}};
  $('add-coordinate').onclick=()=>action(()=>{if(active)return;if(!$('lat').value||!$('lon').value)throw Error('请填写经纬度');const p={lat:Number($('lat').value),lon:Number($('lon').value)};validate([p,p]);points.push(p);render(true);});$('loop-mode').onchange=updateControls;['preset-mode','goal','pace'].forEach(id=>$(id).onchange=()=>{previewPlan();updateControls();});
  function save(update){const data=settings();data.name=$('route-name').value;if(update){data.id=$('saved-routes').value;if(!data.id)throw Error('请选择要更新的路线');}const saved=native('save',data);refreshLibrary();$('saved-routes').value=saved.id;notice(`“${saved.name}”已保存。`);}
  $('save').onclick=()=>action(()=>save(false));$('update').onclick=()=>action(()=>save(true));$('load').onclick=()=>action(()=>{const e=entries.find(e=>e.id===$('saved-routes').value);if(!e)throw Error('请选择路线');restore(e);notice('路线和运动参数已恢复。');});
  $('delete').onclick=()=>action(()=>{const e=entries.find(e=>e.id===$('saved-routes').value);if(!e)throw Error('请选择路线');if(confirm(`删除“${e.name}”？`)){native('delete',{id:e.id});refreshLibrary();}});
  $('export').onclick=()=>action(()=>{$('route-json').value=JSON.stringify({...settings(),name:$('route-name').value},null,2);notice('备份文本已生成，可长按复制保存。');});
  $('import').onclick=()=>action(()=>{if(active)return;const text=$('route-json').value;if(text.length>2000000)throw Error('文本过大');if(text.trim().startsWith('<')){const xml=new DOMParser().parseFromString(text,'text/xml');if(xml.querySelector('parsererror')||/<!DOCTYPE|<!ENTITY/i.test(text))throw Error('GPX 格式无效');const list=Array.from(xml.getElementsByTagNameNS('*','trkpt'));const routes=Array.from(xml.getElementsByTagNameNS('*','rtept'));points=validate((list.length?list:routes).map(n=>({lat:n.getAttribute('lat'),lon:n.getAttribute('lon')})));render(true);return;}let e=JSON.parse(text);if(e.type==='Feature')e=e.geometry;if(e.type==='LineString'){points=validate(e.coordinates.map(p=>({lon:p[0],lat:p[1]})));render(true);}else if(e.route)restore(e);else{points=validate(e.points||e);render(true);}notice('路线已导入，请核对场地和坐标。');});
  $('remote').onclick=()=>action(()=>{busy=true;try{const remote=native('remoteRoutes').entries;let count=0;for(const e of remote){native('save',{...e,id:'remote-'+e.id});count++;}refreshLibrary();notice(`已同步 ${count} 条开发者路线。`);}finally{busy=false;}});
  setupMap();action(()=>{refreshLibrary();const preset=entries.find(e=>e.default===true);if(preset){$('saved-routes').value=preset.id;restore(preset);$('preset-mode').value='simple';previewPlan();updateControls();notice('已载入默认路线“重庆建筑工程职业学院东站校区操场”。');}});status();setInterval(status,1000);
})();
