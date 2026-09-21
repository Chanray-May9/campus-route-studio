(() => {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const toMap = point => window.CampusCoords.wgsToGcj(point);
  const fromMap = point => window.CampusCoords.gcjToWgs(point);
  const STORAGE_KEY = 'campus-route-studio:route:v1';
  const SCHOOL_KEY = 'campus-route-studio:school:v1';
  // 自动保存的完整方案：路线 + 回放参数 + 变速参数 + 设备选项。
  // 自动保存参数用的键。名字保持 v2 不变，这样之前存下的参数升级后还能读到；
  // 记录内部的 version 字段才是真正的格式版本（v2 把参数放在 route 下，v3 放在 params 下）。
  const AUTO_KEY = 'campus-route-studio:settings:v2';
  // 只有“连续输入”（数字框敲键、拖动）才需要防抖把突发合并成一次写盘；
  // 下拉框、复选框、按钮、路线增删等离散操作一律立即写盘，不等这个延迟。
  const AUTO_SAVE_DELAY = 250;
  let libraryEntries = [];
  let libraryBusy = false;

  async function refreshLibrary(selected = $('library-select').value) {
    const data = await api('/api/library');
    libraryEntries = data.entries || [];
    $('library-select').replaceChildren(new Option('请选择已保存轨迹', ''));
    for (const entry of libraryEntries) $('library-select').append(new Option(`${entry.name} · ${entry.points} 点 · ${Math.round(entry.distance)} 米`, entry.id));
    if (libraryEntries.some(e => e.id === selected)) $('library-select').value = selected;
    libraryInfo();
    updateControls();
  }

  function libraryInfo() {
    const entry = libraryEntries.find(e => e.id === $('library-select').value);
    $('library-info').textContent = entry ? `${entry.points} 个路径点 · ${Math.round(entry.distance)} 米 · 更新于 ${new Date(entry.updated).toLocaleString()}` : `共 ${libraryEntries.length} 条轨迹，保存到此电脑，重启后仍可读取。`;
  }

  async function libraryAction(work) {
    if (libraryBusy) return;
    libraryBusy = true;
    updateControls();
    try { await work(); }
    catch (error) { notify(`轨迹库：${error.message}`, true); }
    finally { libraryBusy = false; updateControls(); }
  }

  function restoreLibrary(entry) {
    const restored = validatePoints(entry.route.points);
    if (restored.length < 2) throw new Error('轨迹至少需要两个路径点。');
    const motion = entry.motion || {};
    points = restored;
    $('speed').value = entry.route.speed;
    $('loop-mode').value = entry.route.loops === 0 ? 'infinite' : 'finite';
    $('loops').value = entry.route.loops || 1;
    $('live-speed').value = motion.speed ?? entry.route.speed;
    $('motion-mode').value = motion.mode || 'fixed';
    $('motion-low').value = motion.low ?? entry.route.speed;
    $('motion-high').value = motion.high ?? entry.route.speed;
    $('motion-period').value = motion.period ?? 10;
    $('motion-sway').value = motion.sway ?? 0;
    $('motion-sway-period').value = motion.swayPeriod ?? 4;
    $('library-name').value = entry.name;
    changeCount++;
    renderRoute(true);
    notify(`已载入“${entry.name}”，路线和运动参数均已恢复。`);
  }

  $('library-refresh').addEventListener('click', () => libraryAction(() => refreshLibrary()));
  $('library-select').addEventListener('change', () => { libraryInfo(); updateControls(); });
  $('library-save').addEventListener('click', () => libraryAction(async () => {
    const data = await api('/api/library/save', {name: $('library-name').value, route: settings(), motion: motionSettings()});
    await refreshLibrary(data.id);
    notify(`“${data.name}”已保存到电脑轨迹库。`);
  }));
  $('library-update').addEventListener('click', () => libraryAction(async () => {
    const id = $('library-select').value;
    if (!id) throw new Error('请先选择要更新的轨迹。');
    const data = await api('/api/library/save', {id, name: $('library-name').value, route: settings(), motion: motionSettings()});
    await refreshLibrary(data.id);
    notify(`“${data.name}”已更新。`);
  }));
  $('library-load').addEventListener('click', () => {
    if (editingLocked()) return;
    libraryAction(async () => {
      const data = await api('/api/library/load', {id: $('library-select').value});
      if (editingLocked()) throw new Error('回放已开始，请先停止回放再载入。');
      restoreLibrary(data);
    });
  });
  $('library-delete').addEventListener('click', () => {
    const entry = libraryEntries.find(e => e.id === $('library-select').value);
    if (!entry || !window.confirm(`确定删除“${entry.name}”？此操作只删除已保存的条目，当前编辑路线仍保留。`)) return;
    libraryAction(async () => {
      await api('/api/library/delete', {id: entry.id});
      await refreshLibrary('');
      notify(`已删除“${entry.name}”。`);
    });
  });
  const ACTIVE_STATES = new Set(['starting', 'running', 'paused', 'stopping']);
  const STATE_LABELS = {idle: '尚未开始', starting: '正在启动', running: '回放中', paused: '已暂停', stopping: '正在停止', completed: '回放完成', error: '回放异常'};
  const MODE_DESCRIPTIONS = {
    preview: '先预览路线与速度。预览模式不会向设备发送定位数据。',
    android: '使用 ADB 连接 Android 真机或 MuMu，并通过定位助手回放。请先完成模拟位置应用设置。',
    mumu: '通过本机 MuMu 管理器发送定位。不需要定位助手，支持情况取决于管理器版本。',
    ios: '通过 USB 与 iOS 开发者服务回放定位。需要匹配系统版本的开发环境，无法保证所有 iOS 版本可用。',
    avd: '面向 Android Studio 官方模拟器。可用模拟器控制台同时回放定位与加速度数据。'
  };
  const DEFAULT_POINTS = [{lat:29.51264659,lon:106.69253011},{lat:29.51204124,lon:106.69388141},{lat:29.51191977,lon:106.69394581},{lat:29.51175158,lon:106.69396727},{lat:29.51162077,lon:106.69392434},{lat:29.51150865,lon:106.69381701},{lat:29.51145258,lon:106.69364529},{lat:29.51148061,lon:106.69348430},{lat:29.51214402,lon:106.69223932},{lat:29.51222811,lon:106.69211053},{lat:29.51236827,lon:106.69209980},{lat:29.51254580,lon:106.69212126},{lat:29.51264858,lon:106.69217493},{lat:29.51264659,lon:106.69253011}];
  let points = DEFAULT_POINTS.map(point => ({...point}));
  let map = null;
  let routeLayer = null;
  let markerLayer = null;
  let playbackMarker = null;
  let run = {state: 'idle', elapsed: 0, distance: 0, totalDistance: 0, duration: 0, point: null};
  let busy = false;
  let deviceBusy = false;
  let statusPromise = null;
  let serverOnline = false;
  let lastRunError = '';
  let lastCleanupError = '';
  let deviceData = null;
  let changeCount = 0;
  let locationMarker = null;
  let followPlayback = false;

  // ---- 设置自动保存：改完即存，下次打开自动恢复 ----
  const MOTION_MODES = new Set(['fixed', 'smooth', 'alternating']);
  const OUTPUT_MODES = new Set(['preview', 'android', 'mumu', 'ios', 'avd']);
  const DEFAULT_SETTINGS = {'speed': 2.5, 'loop-mode': 'finite', 'loops': 1, 'motion-mode': 'fixed', 'motion-low': 2, 'motion-high': 3, 'motion-period': 10, 'motion-sway': 0, 'motion-sway-period': 4, 'live-speed': 2.5};
  let autoSaveTimer = null;
  let autoSaveFailed = false;

  function validNumber(value, minimum, maximum) {
    const result = Number(value);
    return Number.isFinite(result) && result >= minimum && result <= maximum ? result : null;
  }

  function validInteger(value, minimum, maximum) {
    const result = Number(value);
    return Number.isInteger(result) && result >= minimum && result <= maximum ? result : null;
  }

  function fieldNumber(id, minimum, maximum, fallback) {
    const result = validNumber($(id).value, minimum, maximum);
    return result === null ? fallback : result;
  }

  function fieldInteger(id, minimum, maximum, fallback) {
    const result = validInteger($(id).value, minimum, maximum);
    return result === null ? fallback : result;
  }

  function setFollow(value) {
    followPlayback = Boolean(value);
    $('follow-button').textContent = `跟随回放：${followPlayback ? '开' : '关'}`;
    $('follow-button').setAttribute('aria-pressed', String(followPlayback));
  }

  function snapshotSettings() {
    const speed = fieldNumber('speed', 0.2, 20, 2.5);
    const low = fieldNumber('motion-low', 0.2, 20, speed);
    const high = fieldNumber('motion-high', 0.2, 20, speed);
    const infinite = $('loop-mode').value === 'infinite';
    return {
      version: 3,
      savedAt: new Date().toISOString(),
      // 只自动保存回放参数，不保存轨迹点：轨迹由「保存到本机」和轨迹库负责。
      params: {
        speed,
        loops: infinite ? 0 : fieldInteger('loops', 1, 10000, 1),
        interval: 1
      },
      motion: {
        mode: MOTION_MODES.has($('motion-mode').value) ? $('motion-mode').value : 'fixed',
        speed: fieldNumber('live-speed', 0.2, 20, speed),
        low: Math.min(low, high),
        high: Math.max(low, high),
        period: fieldNumber('motion-period', 2, 120, 10),
        sway: fieldNumber('motion-sway', 0, 3, 0),
        swayPeriod: fieldNumber('motion-sway-period', 2, 30, 4)
      },
      ui: {
        mode: OUTPUT_MODES.has($('mode').value) ? $('mode').value : 'preview',
        adbAddress: $('adb-address').value.trim().slice(0, 255),
        manager: $('manager').value.trim().slice(0, 500),
        instance: fieldInteger('instance', 0, 9999, 0),
        sensor: $('sensor').checked,
        followPlayback
      }
    };
  }

  function autoSaveHint(message) {
    const node = $('autosave-status');
    if (!node) return;
    node.classList.toggle('error', autoSaveFailed);
    node.textContent = autoSaveFailed
      ? '浏览器无法保存设置：本地存储不可用或已写满，本次修改不会被保留。'
      : message || `已自动保存 ${new Date().toLocaleTimeString()} · 下次打开自动恢复。`;
  }

  function writeSettings() {
    let data;
    try { data = snapshotSettings(); } catch { return false; }
    autoSaveFailed = false;
    try {
      localStorage.setItem(AUTO_KEY, JSON.stringify(data));
    } catch {
      // 路线点极多时退化为只保存参数，保证速度、变速模式与圈数一定保留。
      try {
        data.route = null;
        localStorage.setItem(AUTO_KEY, JSON.stringify(data));
      } catch {
        autoSaveFailed = true;
        autoSaveHint();
        return false;
      }
    }
    autoSaveHint();
    return true;
  }

  function saveNow() {
    if (autoSaveTimer) { clearTimeout(autoSaveTimer); autoSaveTimer = null; }
    return writeSettings();
  }

  function scheduleSave() {
    if (autoSaveTimer) clearTimeout(autoSaveTimer);
    autoSaveTimer = setTimeout(() => { autoSaveTimer = null; writeSettings(); }, AUTO_SAVE_DELAY);
  }

  function flushSave() {
    if (!autoSaveTimer) return;
    clearTimeout(autoSaveTimer);
    autoSaveTimer = null;
    writeSettings();
  }

  function applySavedSettings(saved) {
    if (!saved || typeof saved !== 'object' || (saved.version !== 2 && saved.version !== 3)) return false;
    let restored = false;
    // v2 把参数放在 route 下，v3 放在 params 下；两者的轨迹点都一律忽略，绝不覆盖当前路线。
    const params = (saved.version === 3 ? saved.params : saved.route) || {};
    if (typeof params === 'object') {
      const speed = validNumber(params.speed, 0.2, 20);
      const loops = validInteger(params.loops, 0, 10000);
      if (speed !== null) $('speed').value = speed;
      if (loops !== null) {
        $('loop-mode').value = loops === 0 ? 'infinite' : 'finite';
        $('loops').value = loops || 1;
      }
      if (speed !== null || loops !== null) restored = true;
    }
    const motion = saved.motion;
    if (motion && typeof motion === 'object') {
      if (MOTION_MODES.has(motion.mode)) $('motion-mode').value = motion.mode;
      const fields = [['speed', 'live-speed', 0.2, 20], ['low', 'motion-low', 0.2, 20], ['high', 'motion-high', 0.2, 20], ['period', 'motion-period', 2, 120], ['sway', 'motion-sway', 0, 3], ['swayPeriod', 'motion-sway-period', 2, 30]];
      for (const [key, id, minimum, maximum] of fields) {
        const value = validNumber(motion[key], minimum, maximum);
        if (value !== null) $(id).value = value;
      }
      restored = true;
    }
    const ui = saved.ui;
    if (ui && typeof ui === 'object') {
      if (OUTPUT_MODES.has(ui.mode)) $('mode').value = ui.mode;
      if (typeof ui.adbAddress === 'string') $('adb-address').value = ui.adbAddress.slice(0, 255);
      if (typeof ui.manager === 'string') $('manager').value = ui.manager.slice(0, 500);
      const instance = validInteger(ui.instance, 0, 9999);
      if (instance !== null) $('instance').value = instance;
      $('sensor').checked = ui.sensor === true;
      setFollow(ui.followPlayback === true);
      restored = true;
    }
    // 变速参数恢复后校验上下限，避免出现最低速度大于最高速度。
    if (Number($('motion-low').value) > Number($('motion-high').value)) $('motion-high').value = $('motion-low').value;
    return restored;
  }

  function restoreSettings() {
    let raw = null;
    try { raw = localStorage.getItem(AUTO_KEY); } catch { return false; }
    if (!raw) return false;
    try { return applySavedSettings(JSON.parse(raw)); }
    catch { return false; }
  }

  function motionSettings() {
    const result = {mode: $('motion-mode').value, speed: Number($('live-speed').value), low: Number($('motion-low').value), high: Number($('motion-high').value), period: Number($('motion-period').value), sway: Number($('motion-sway').value), swayPeriod: Number($('motion-sway-period').value)};
    if (Object.values(result).some(v => typeof v === 'number' && !Number.isFinite(v))) throw new Error('运动参数必须填写有效数字。');
    if (result.low > result.high) throw new Error('最低速度不能大于最高速度。');
    return result;
  }
  $('speed').addEventListener('input', () => { if (!isActive()) $('live-speed').value = $('speed').value; });
  $('apply-motion').addEventListener('click', async () => {
    $('apply-motion').disabled = true;
    try { await api('/api/tuning', motionSettings()); notify('新速度和摆动参数已应用，路线进度保持连续。'); }
    catch (error) { notify(error.message, true); }
    finally { updateControls(); }
  });
  $('follow-button').addEventListener('click', () => {
    setFollow(!followPlayback);
    saveNow();
    if (followPlayback && map && run.point) { const p = toMap(run.point); map.setView([p.lat, p.lon], Math.max(18, map.getZoom())); }
  });

  function savedSchool() {
    try {
      const value = JSON.parse(localStorage.getItem(SCHOOL_KEY) || 'null');
      if (!value || !Number.isFinite(value.lat) || !Number.isFinite(value.lon) || Math.abs(value.lat) > 85 || Math.abs(value.lon) > 180) return null;
      return value;
    } catch { return null; }
  }

  function centerLocation(lat, lon, zoom = 16) {
    if (!map) throw new Error('地图未加载，请稍后重试。');
    if (!Number.isFinite(lat) || !Number.isFinite(lon) || Math.abs(lat) > 85 || Math.abs(lon) > 180) throw new Error('定位返回的坐标无效。');
    const display = toMap({lat, lon});
    map.setView([display.lat, display.lon], zoom);
    if (locationMarker) map.removeLayer(locationMarker);
    locationMarker = L.circleMarker([display.lat, display.lon], {radius: 8, color: '#fff', weight: 3, fillColor: '#267be0', fillOpacity: 1, interactive: false}).addTo(map);
  }

  $('locate-button').addEventListener('click', () => {
    if (!map || !navigator.geolocation) { notify('当前环境不支持定位；可移动地图后保存学校位置。', true); return; }
    const button = $('locate-button');
    button.disabled = true;
    $('location-status').textContent = '正在获取电脑当前位置，请允许浏览器定位…';
    navigator.geolocation.getCurrentPosition(position => {
      button.disabled = false;
      try {
        centerLocation(position.coords.latitude, position.coords.longitude);
        $('location-status').textContent = `已定位 · 估计精度 ${Math.round(position.coords.accuracy)} 米。可微调地图后保存学校位置。`;
      } catch (error) { notify(error.message, true); }
    }, error => {
      button.disabled = false;
      const messages = {1: '定位权限被拒绝，请在浏览器地址栏的权限设置中允许定位，并开启 Windows 定位服务。', 2: '暂时无法获取电脑位置，请检查 Windows 定位服务，或手动移动地图后保存学校位置。', 3: '定位超时，请重试，或手动移动地图后保存学校位置。'};
      $('location-status').textContent = messages[error.code] || '定位失败，请重试。';
      notify($('location-status').textContent, true);
    }, {enableHighAccuracy: true, timeout: 15000, maximumAge: 60000});
  });

  $('save-school-button').addEventListener('click', () => {
    if (!map) return;
    try {
      const center = fromMap({lat: map.getCenter().lat, lon: map.getCenter().lng});
      localStorage.setItem(SCHOOL_KEY, JSON.stringify({lat: center.lat, lon: ((center.lon + 180) % 360 + 360) % 360 - 180, zoom: map.getZoom()}));
      $('school-button').disabled = false;
      $('location-status').textContent = '学校位置已保存到此浏览器。下次打开会自动回到这里。';
    } catch { notify('浏览器无法保存位置，请检查本地存储权限。', true); }
  });

  $('school-button').addEventListener('click', () => {
    const school = savedSchool();
    if (!school) { notify('请先把学校移动到地图中心，点击“保存学校位置”。', true); return; }
    try { centerLocation(school.lat, school.lon, Math.max(1, Math.min(19, school.zoom || 16))); $('location-status').textContent = '已回到保存的学校位置。'; }
    catch (error) { notify(error.message, true); }
  });

  const isActive = () => ACTIVE_STATES.has(run.state);
  $('quit-button').addEventListener('click', async () => {
    $('quit-button').disabled = true;
    try {
      await api('/api/quit', {});
      document.body.replaceChildren(Object.assign(document.createElement('p'), {textContent: '工作台正在停止回放并退出。可以关闭此页面。'}));
    } catch (error) {
      $('quit-button').disabled = false;
      notify(error.message, true);
    }
  });
  const editingLocked = () => busy || isActive();
  const finite = (value, fallback = 0) => Number.isFinite(Number(value)) ? Number(value) : fallback;

  function notify(message, error = false) {
    const node = $('notice');
    node.textContent = message;
    node.classList.toggle('error', error);
    node.hidden = !message;
  }

  async function api(path, body, timeout = 30000) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);
    try {
      const options = {signal: controller.signal, credentials: 'same-origin', cache: 'no-store'};
      if (body !== undefined) {
        options.method = 'POST';
        options.headers = {'Content-Type': 'application/json'};
        options.body = JSON.stringify(body);
      }
      const response = await fetch(path, options);
      const text = await response.text();
      let data;
      try { data = JSON.parse(text); } catch { throw new Error('本机服务返回了无效响应。请查看启动窗口中的日志。'); }
      if (!response.ok) throw new Error(data.error || `请求失败（HTTP ${response.status}）`);
      return data;
    } catch (error) {
      if (error.name === 'AbortError') throw new Error('本机服务响应超时。请检查设备连接和启动窗口日志，然后重试。');
      if (error instanceof TypeError) throw new Error('无法连接本机服务。请确认工作台启动程序仍在运行。');
      throw error;
    } finally { clearTimeout(timer); }
  }

  async function action(task) {
    if (busy) return;
    busy = true;
    updateControls();
    try { await task(); } catch (error) { notify(error.message, true); }
    finally { busy = false; updateControls(); }
  }

  function haversine(a, b) {
    const radians = Math.PI / 180;
    const dLat = (b.lat - a.lat) * radians;
    const dLon = (b.lon - a.lon) * radians;
    const h = Math.sin(dLat / 2) ** 2 + Math.cos(a.lat * radians) * Math.cos(b.lat * radians) * Math.sin(dLon / 2) ** 2;
    return 6371000 * 2 * Math.atan2(Math.sqrt(h), Math.sqrt(Math.max(0, 1 - h)));
  }

  function routeDistance() {
    let distance = 0;
    for (let i = 1; i < points.length; i++) distance += haversine(points[i - 1], points[i]);
    return distance;
  }

  function distanceText(distance) {
    return distance >= 1000 ? `${(distance / 1000).toFixed(2)} 公里` : `${Math.round(distance)} 米`;
  }

  function durationText(seconds) {
    if (!Number.isFinite(seconds) || seconds <= 0) return '—';
    const minutes = Math.ceil(seconds / 60);
    if (minutes < 60) return `${minutes} 分钟`;
    return `${Math.floor(minutes / 60)} 小时 ${minutes % 60} 分`;
  }

  function clockText(seconds) {
    const whole = Math.max(0, Math.floor(finite(seconds)));
    const hours = Math.floor(whole / 3600);
    const minutes = Math.floor((whole % 3600) / 60);
    const secs = whole % 60;
    return (hours ? `${String(hours).padStart(2, '0')}:` : '') + `${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
  }

  function validatePoints(value) {
    if (!Array.isArray(value) || value.length > 10000) throw new Error('路线必须是最多 10,000 个点的坐标列表。');
    return value.map((point, index) => {
      if (!point || typeof point.lat !== 'number' || typeof point.lon !== 'number' || !Number.isFinite(point.lat) || !Number.isFinite(point.lon) || Math.abs(point.lat) > 90 || Math.abs(point.lon) > 180) {
        throw new Error(`第 ${index + 1} 个坐标无效：纬度应在 -90 到 90，经度应在 -180 到 180 之间。`);
      }
      return {lat: point.lat, lon: point.lon};
    });
  }

  function settings(requireRoute = true) {
    const speed = Number($('speed').value);
    const loops = $('loop-mode').value === 'infinite' ? 0 : Number($('loops').value);
    if (!Number.isFinite(speed) || speed < 0.2 || speed > 20) throw new Error('速度应为 0.2 到 20 m/s。');
    if (!Number.isInteger(loops) || loops < 0 || loops > 10000 || (loops === 0 && $('loop-mode').value !== 'infinite')) throw new Error('指定圈数应为 1 到 10000 的整数。');
    if (requireRoute && (points.length < 2 || routeDistance() < 1)) throw new Error('请至少添加两个不同的途经点，路线长度须大于 1 米。');
    return {points: validatePoints(points), speed, loops, interval: 1};
  }

  function updateEstimates() {
    const distance = routeDistance();
    $('route-distance').textContent = distance >= 1000 ? (distance / 1000).toFixed(2) : String(Math.round(distance));
    $('route-distance-unit').textContent = distance >= 1000 ? '公里' : '米';
    $('route-point-count').textContent = points.length;
    const speed = Number($('speed').value);
    const loops = Number($('loops').value);
    if (speed > 0) {
      const pace = Math.round(1000 / speed);
      $('pace').textContent = `${Math.floor(pace / 60)}′${String(pace % 60).padStart(2, '0')}″ / 公里`;
      $('estimated-duration').textContent = $('loop-mode').value === 'infinite' ? '无限 · 手动停止' : durationText(distance * loops / speed);
    } else {
      $('pace').textContent = '—';
      $('estimated-duration').textContent = '—';
    }
    if (run.state === 'idle') $('progress-distance').textContent = `0 / ${distanceText(distance * (loops > 0 ? loops : 1))}`;
    updateControls();
  }

  function markerIcon(index, total) {
    return L.divIcon({className: `route-map-marker${index === total - 1 && index > 0 ? ' end-marker' : ''}`, html: String(index + 1), iconSize: [25, 25], iconAnchor: [12.5, 12.5]});
  }

  function drawRoute(fit = false) {
    if (!map) return;
    routeLayer.setLatLngs(points.map(point => { const p = toMap(point); return [p.lat, p.lon]; }));
    markerLayer.clearLayers();
    points.forEach((point, index) => {
      const display = toMap(point);
      const marker = L.marker([display.lat, display.lon], {icon: markerIcon(index, points.length), draggable: !editingLocked(), title: `途经点 ${index + 1}：拖动调整坐标`, keyboard: true}).addTo(markerLayer);
      marker.on('dragend', (event) => {
        if (editingLocked()) { drawRoute(); return; }
        const position = fromMap({lat: event.target.getLatLng().lat, lon: event.target.getLatLng().lng});
        const lat = Math.max(-90, Math.min(90, position.lat));
        const lon = ((position.lon + 180) % 360 + 360) % 360 - 180;
        points[index] = {lat, lon};
        changeCount++;
        renderRoute();
      });
    });
    if (fit && points.length) {
      if (points.length === 1) { const p = toMap(points[0]); map.setView([p.lat, p.lon], 16); }
      else map.fitBounds(routeLayer.getBounds(), {paddingTopLeft: [50, 135], paddingBottomRight: [50, 110], maxZoom: 17, animate: false});
    }
  }

  function renderRoute(fit = false) {
    const list = $('waypoints');
    list.replaceChildren();
    if (!points.length) {
      const empty = document.createElement('li');
      empty.className = 'empty-state';
      empty.append('从第一个点开始', document.createElement('br'));
      const hint = document.createElement('span');
      hint.textContent = '点击地图，或在下方添加坐标';
      empty.append(hint);
      list.append(empty);
    }
    points.forEach((point, index) => {
      const item = document.createElement('li');
      item.className = 'waypoint';
      const number = document.createElement('span');
      number.className = 'waypoint-index';
      number.textContent = index + 1;
      const info = document.createElement('span');
      info.className = 'waypoint-info';
      const title = document.createElement('span');
      title.className = 'waypoint-title';
      title.textContent = index === 0 ? '起点' : index === points.length - 1 ? '终点' : `途经点 ${index + 1}`;
      const coordinates = document.createElement('span');
      coordinates.className = 'waypoint-coordinates';
      coordinates.textContent = `${point.lat.toFixed(5)}, ${point.lon.toFixed(5)}`;
      info.append(title, coordinates);
      const remove = document.createElement('button');
      remove.type = 'button';
      remove.className = 'waypoint-remove';
      remove.textContent = '×';
      remove.disabled = editingLocked();
      remove.setAttribute('aria-label', `删除途经点 ${index + 1}`);
      remove.addEventListener('click', () => {
        if (editingLocked()) return;
        points.splice(index, 1);
        changeCount++;
        renderRoute();
      });
      item.append(number, info, remove);
      list.append(item);
    });
    drawRoute(fit);
    updateEstimates();
    // 路线的增删、导入、载入、拖动结束都是一次性操作，直接落盘。
    saveNow();
  }

  function addPoint(point, fit = false) {
    if (editingLocked()) return;
    try {
      if (points.length >= 10000) throw new Error('路线最多支持 10,000 个点。');
      points.push(...validatePoints([point]));
      changeCount++;
      renderRoute(fit);
      $('waypoints').scrollTop = $('waypoints').scrollHeight;
    } catch (error) { notify(error.message, true); }
  }

  function initializeMap() {
    if (!window.L) {
      $('map').classList.add('map-fallback');
      $('map').textContent = '地图组件未加载。\n请使用坐标输入或导入路线，检查本机 Leaflet 资源是否完整。';
      $('map-offline').hidden = false;
      return;
    }
    const initial = toMap({lat: 30.2741, lon: 120.1551});
    map = L.map('map', {zoomControl: false, attributionControl: true, preferCanvas: true, worldCopyJump: true}).setView([initial.lat, initial.lon], 15);
    L.control.zoom({position: 'topright'}).addTo(map);
    const school = savedSchool();
    $('school-button').disabled = !school;
    if (school) { const p = toMap(school); map.setView([p.lat, p.lon], Math.max(1, Math.min(19, school.zoom || 16))); }
    const tiles = L.tileLayer('https://webrd01.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=7&x={x}&y={y}&z={z}', {maxZoom: 19, attribution: '&copy; 高德地图'}).addTo(map);
    let failed = 0;
    let succeeded = 0;
    tiles.on('loading', () => { failed = 0; succeeded = 0; });
    tiles.on('tileerror', () => { failed++; if (failed >= 3 && !succeeded) $('map-offline').hidden = false; });
    tiles.on('tileload', () => { succeeded++; });
    tiles.on('load', () => { $('map-offline').hidden = !(failed > succeeded || !navigator.onLine); });
    window.addEventListener('offline', () => { $('map-offline').hidden = false; });
    window.addEventListener('online', () => { tiles.redraw(); });
    routeLayer = L.polyline([], {color: '#0d746b', weight: 4, opacity: 0.88, lineJoin: 'round', lineCap: 'round'}).addTo(map);
    markerLayer = L.layerGroup().addTo(map);
    map.on('click', (event) => addPoint(fromMap({lat: event.latlng.lat, lon: event.latlng.lng})));
    if (window.ResizeObserver) new ResizeObserver(() => map.invalidateSize()).observe($('map'));
  }

  function updateControls() {
    const active = isActive();
    const locked = editingLocked();
    $('loop-mode').disabled = locked;
    $('loop-hint').textContent = $('loop-mode').value === 'infinite' ? '路线自动闭合，持续回放直到点击停止；不会因完成一圈而退出。' : '回放指定圈数后自动停止。';
    const librarySelected = Boolean($('library-select').value);
    $('library-refresh').disabled = libraryBusy;
    $('library-save').disabled = libraryBusy || busy || points.length < 2;
    $('library-load').disabled = libraryBusy || locked || !librarySelected;
    $('library-update').disabled = libraryBusy || busy || !librarySelected || points.length < 2;
    $('library-delete').disabled = libraryBusy || !librarySelected;
    $('apply-motion').disabled = busy || !['running', 'paused', 'starting'].includes(run.state);
    ['latitude', 'longitude', 'speed', 'loops', 'mode', 'demo-button', 'import-button', 'load-button', 'android-device', 'ios-device', 'manager', 'instance', 'sensor', 'adb-address'].forEach(id => { $(id).disabled = locked; });
    $('loops').disabled = locked || $('loop-mode').value === 'infinite';
    document.querySelector('.add-button').disabled = locked;
    document.querySelectorAll('.waypoint-remove').forEach(button => { button.disabled = locked; });
    $('undo-button').disabled = locked || !points.length;
    $('clear-button').disabled = locked || !points.length;
    $('close-loop-button').disabled = locked || points.length < 2;
    $('export-button').disabled = busy || points.length < 2;
    $('save-button').disabled = busy || !points.length;
    $('setup-button').disabled = locked || deviceBusy || !$('android-device').value;
    $('connect-button').disabled = locked || deviceBusy;
    document.querySelectorAll('.refresh-button').forEach(button => { button.disabled = locked || deviceBusy; button.textContent = deviceBusy ? '查找中…' : '刷新'; });
    $('start-button').disabled = busy || active || points.length < 2 || !serverOnline;
    $('start-button').querySelector('span').textContent = busy && !active ? '正在处理…' : $('mode').value === 'preview' ? '开始预览' : '开始设备回放';
    $('pause-button').disabled = busy || !['running', 'paused'].includes(run.state);
    $('pause-button').textContent = run.state === 'paused' ? '继续' : '暂停';
    $('stop-button').disabled = busy || !['starting', 'running', 'paused'].includes(run.state);
    $('map-mode-label').textContent = active ? '路线已锁定' : '路线编辑';
    $('map-tip').lastChild.textContent = active ? '路线回放中 · 停止后可继续编辑' : '点击地图添加途经点 · 拖动标记调整位置';
    if (markerLayer) markerLayer.eachLayer(marker => {
      if (!marker.dragging) return;
      if (locked) marker.dragging.disable(); else marker.dragging.enable();
    });
  }

  function renderStatus(next) {
    const previousState = run.state;
    run = {...run, ...next};
    if (!STATE_LABELS[run.state]) run.state = 'error';
    const total = Math.max(0, finite(run.totalDistance));
    const distance = Math.max(0, finite(run.distance));
    const percentage = total > 0 ? Math.min(100, Math.max(0, distance / total * 100)) : 0;
    $('run-state').textContent = STATE_LABELS[run.state];
    $('run-state').dataset.state = run.state;
    $('progress-percent').replaceChildren(document.createTextNode(String(Math.floor(percentage))));
    const percentSymbol = document.createElement('span'); percentSymbol.textContent = '%'; $('progress-percent').append(percentSymbol);
    $('progress-fill').style.width = `${percentage}%`;
    $('progress-track').setAttribute('aria-valuenow', String(Math.round(percentage)));
    $('progress-distance').textContent = run.state === 'idle' ? `0 / ${distanceText(routeDistance() * finite($('loops').value, 1))}` : `${distanceText(distance)} / ${distanceText(total)}`;
    if (run.infinite && run.state !== 'idle') {
      const lapPercent = run.lapDistance > 0 ? (distance % run.lapDistance) / run.lapDistance * 100 : 0;
      $('progress-percent').textContent = '∞';
      $('progress-fill').style.width = `${lapPercent}%`;
      $('progress-track').setAttribute('aria-valuenow', String(Math.round(lapPercent)));
      $('progress-track').setAttribute('aria-valuetext', `无限循环，已完成 ${run.completedLaps || 0} 圈`);
      $('progress-distance').textContent = `${distanceText(distance)} · 已完成 ${run.completedLaps || 0} 圈`;
    } else {
      $('progress-track').removeAttribute('aria-valuetext');
      if (run.state === 'idle' && $('loop-mode').value === 'infinite') $('progress-distance').textContent = '无限循环 · 手动停止';
    }
    $('elapsed-time').textContent = clockText(run.elapsed);
    $('live-speed-status').textContent = run.point ? `当前沿路线速度：${Number(run.point.speed || 0).toFixed(2)} m/s · 变速时预计时长仅供参考` : '当前速度：—';
    $('ios-motion-note').hidden = $('mode').value !== 'ios';
    const sent = Number.isFinite(run.sentUpdates) ? run.sentUpdates : null;
    const age = run.lastSendTime ? Math.max(0, (Date.now() / 1000) - run.lastSendTime) : null;
    $('send-diagnostics').textContent = run.state === 'idle' ? '开始回放后显示坐标发送状态。' : sent === null ? '当前后台尚未支持发送诊断，请停止回放后重新启动 start.cmd。' : `已发送 ${sent} 次坐标${age === null ? ' · 等待首次发送' : ` · 上次发送 ${Math.floor(age)} 秒前 · 耗时 ${run.lastSendMs || 0} 毫秒`}。接口发送成功不等于手机地图已确认更新。`;
    if (run.point && Number.isFinite(run.point.lat) && Number.isFinite(run.point.lon)) {
      $('current-position').textContent = `${run.point.lat.toFixed(7)}, ${run.point.lon.toFixed(7)}`;
      if (map) {
        const display = toMap(run.point);
        const position = [display.lat, display.lon];
        if (!playbackMarker) playbackMarker = L.marker(position, {icon: L.divIcon({className: 'route-map-marker current-marker', iconSize: [23, 23], iconAnchor: [11.5, 11.5]}), zIndexOffset: 1000, interactive: false, title: '当前回放位置'}).addTo(map);
        else playbackMarker.setLatLng(position);
        if (followPlayback) map.setView(position, Math.max(18, map.getZoom()), {animate: false});
      }
    } else {
      $('current-position').textContent = '—';
      if (map && playbackMarker) { map.removeLayer(playbackMarker); playbackMarker = null; }
    }
    if (run.error && run.error !== lastRunError) { lastRunError = run.error; notify(`回放失败：${run.error}`, true); }
    if (run.cleanupError && run.cleanupError !== lastCleanupError) { lastCleanupError = run.cleanupError; notify(`停止后的设备清理未完成：${run.cleanupError}\n请在设备上检查定位是否恢复。`, true); }
    if (previousState !== 'completed' && run.state === 'completed' && !run.cleanupError) notify('路线回放已完成。设备模式下，请在设备上核对定位恢复情况。');
    updateControls();
  }

  function refreshStatus() {
    if (statusPromise) return statusPromise;
    statusPromise = (async () => {
      try {
        const data = await api('/api/status', undefined, 8000);
        serverOnline = true;
        $('server-status').textContent = '本机服务已连接';
        $('connection-dot').classList.add('connected');
        $('app-version').textContent = data.info && data.info.version ? `v${data.info.version}` : '';
        if (data.run) renderStatus(data.run);
      } catch (error) {
        serverOnline = false;
        $('server-status').textContent = '本机服务连接中断';
        $('connection-dot').classList.remove('connected');
        if (isActive()) notify(`${error.message}\n界面无法确认设备端是否仍在回放。`, true);
        updateControls();
      } finally { statusPromise = null; }
    })();
    return statusPromise;
  }

  function populateDevices() {
    if (!deviceData) return;
    const avdOnly = $('mode').value === 'avd';
    const previousAndroid = $('android-device').value;
    const previousIos = $('ios-device').value;
    $('android-device').replaceChildren(new Option('请选择已连接设备', ''));
    $('ios-device').replaceChildren(new Option('请选择已连接设备', ''));
    (deviceData.android || []).filter(device => !avdOnly || String(device.serial).startsWith('emulator-')).forEach(device => {
      const option = new Option(`${device.model || device.serial}${device.model ? ` · ${device.serial}` : ''}${device.state !== 'device' ? ` (${device.state})` : ''}`, device.serial);
      option.disabled = device.state !== 'device';
      $('android-device').append(option);
    });
    (deviceData.ios || []).forEach(device => { $('ios-device').append(new Option(`${device.name || 'iOS 设备'}${device.version ? ` · ${device.version}` : ''} · ${String(device.udid).slice(0, 8)}…`, device.udid)); });
    if (Array.from($('android-device').options).some(option => option.value === previousAndroid && !option.disabled)) $('android-device').value = previousAndroid;
    if (Array.from($('ios-device').options).some(option => option.value === previousIos)) $('ios-device').value = previousIos;
    const androidAvailable = Array.from($('android-device').options).filter(option => option.value && !option.disabled);
    if (!$('android-device').value && androidAvailable.length === 1) $('android-device').value = androidAvailable[0].value;
    if (!$('ios-device').value && $('ios-device').options.length === 2) $('ios-device').selectedIndex = 1;
    const messages = [];
    const mode = $('mode').value;
    if (['android', 'avd'].includes(mode)) {
      if (!deviceData.dependencies?.adb) messages.push('未检测到 adb。请安装 Android Platform Tools 并加入 PATH。');
      else if (!androidAvailable.length) messages.push(avdOnly ? '未发现可用 AVD。请在 Android Studio 中启动模拟器。' : '未发现已授权设备。请打开 USB 调试、确认授权，或填写 MuMu ADB 地址。');
    }
    if (mode === 'ios') {
      if (!deviceData.dependencies?.ios) messages.push('iPhone 扫描依赖未安装到当前 Python。请退出后用 start.cmd 重新启动；Apple 驱动已安装也需要此依赖。');
      else if (!$('ios-device').options[1]) messages.push('未发现 iOS 设备。请使用数据线连接、解锁并信任此电脑。');
    }
    if (['android', 'ios', 'avd'].includes(mode)) (deviceData.errors || []).forEach(error => { messages.push(typeof error === 'string' ? error : error.message || JSON.stringify(error)); });
    $('device-notice').textContent = messages.join('\n');
    $('device-notice').hidden = !messages.length;
    updateControls();
  }

  async function refreshDevices() {
    if (deviceBusy || isActive()) return;
    deviceBusy = true;
    updateControls();
    try {
      deviceData = await api('/api/devices', undefined, 60000);
      populateDevices();
    } catch (error) { notify(error.message, true); }
    finally { deviceBusy = false; updateControls(); }
  }

  function modeChanged() {
    const mode = $('mode').value;
    $('mode-description').textContent = MODE_DESCRIPTIONS[mode];
    $('android-fields').hidden = !['android', 'avd'].includes(mode);
    $('android-helper').hidden = mode !== 'android';
    $('adb-connect').hidden = mode !== 'android';
    $('ios-fields').hidden = mode !== 'ios';
    $('mumu-fields').hidden = mode !== 'mumu';
    $('sensor-field').hidden = mode !== 'avd';
    if (mode !== 'avd') $('sensor').checked = false;
    $('device-notice').hidden = true;
    populateDevices();
    updateControls();
    if (['android', 'avd', 'ios'].includes(mode)) refreshDevices();
  }

  function downloadText(filename, text, mime) {
    const blob = new Blob([text], {type: mime || 'text/plain;charset=utf-8'});
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = filename;
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  $('coordinate-form').addEventListener('submit', (event) => {
    event.preventDefault();
    if (!$('coordinate-form').reportValidity()) return;
    addPoint({lat: Number($('latitude').value), lon: Number($('longitude').value)}, true);
  });
  $('undo-button').addEventListener('click', () => { if (!editingLocked()) { points.pop(); changeCount++; renderRoute(); } });
  $('clear-button').addEventListener('click', () => { if (!editingLocked()) { points = []; changeCount++; renderRoute(); } });
  $('close-loop-button').addEventListener('click', () => {
    if (editingLocked() || points.length < 2) return;
    if (haversine(points[0], points[points.length - 1]) < 0.1) return notify('路线已经闭合。');
    addPoint({...points[0]});
  });
  $('demo-button').addEventListener('click', () => {
    if (editingLocked()) return;
    points = DEFAULT_POINTS.map(point => ({...point}));
    changeCount++;
    renderRoute(true);
    notify('已载入“重庆建筑工程职业学院东站校区操场”，请在开始前核对路线与实际场地。');
  });
  $('speed').addEventListener('input', updateEstimates);
  $('loops').addEventListener('input', updateEstimates);
  $('loop-mode').addEventListener('change', () => { updateEstimates(); updateControls(); });
  $('mode').addEventListener('change', modeChanged);
  $('android-device').addEventListener('change', updateControls);
  document.querySelectorAll('.refresh-button').forEach(button => button.addEventListener('click', refreshDevices));
  // 连续输入：合并成一次写入，避免每敲一个键就把整条路线序列化一遍。
  ['speed', 'loops', 'motion-low', 'motion-high', 'motion-period', 'motion-sway', 'motion-sway-period', 'live-speed', 'manager', 'instance', 'adb-address'].forEach(id => $(id).addEventListener('input', scheduleSave));
  // 离散操作：改完立即写盘，不等防抖。
  ['loop-mode', 'motion-mode', 'export-format', 'sensor'].forEach(id => $(id).addEventListener('change', saveNow));
  window.addEventListener('pagehide', flushSave);
  document.addEventListener('visibilitychange', () => { if (document.hidden) flushSave(); });
  $('setup-button').addEventListener('click', () => action(async () => {
    const serial = $('android-device').value;
    if (!serial) throw new Error('请先选择一台已授权的 Android 设备。');
    notify('正在安装定位助手并打开设备设置…');
    const data = await api('/api/android/setup', {serial}, 120000);
    notify(data.message || '定位助手已安装。请在设备开发者选项中，将本项目助手选为“模拟位置信息应用”，然后开始回放。');
  }));
  $('connect-button').addEventListener('click', () => action(async () => {
    const address = $('adb-address').value.trim();
    if (!address || address.length > 255 || /\s/.test(address)) throw new Error('请输入有效的 ADB 地址，例如 127.0.0.1:16384。');
    const data = await api('/api/connect', {address}, 60000);
    notify(data.message || 'ADB 连接请求已执行，请查看设备列表中的实际连接状态。');
    await refreshDevices();
  }));
  $('start-button').addEventListener('click', () => action(async () => {
    const mode = $('mode').value;
    const route = settings();
    const payload = {mode, route, motion: motionSettings(), sensor: mode === 'avd' && $('sensor').checked};
    if (['android', 'avd'].includes(mode)) {
      payload.serial = $('android-device').value;
      if (!payload.serial) throw new Error('请先刷新并选择一台已授权设备。');
    }
    if (mode === 'ios') {
      payload.udid = $('ios-device').value;
      if (!payload.udid) throw new Error('请先刷新并选择一台 iOS 设备。');
    }
    if (mode === 'mumu') {
      payload.manager = $('manager').value.trim();
      payload.instance = Number($('instance').value);
      if (!payload.manager) throw new Error('请输入本机 MuMuManager.exe 的完整路径。');
      if (!Number.isInteger(payload.instance) || payload.instance < 0 || payload.instance > 9999) throw new Error('MuMu 实例编号应为 0 到 9999 的整数。');
    }
    lastRunError = '';
    lastCleanupError = '';
    notify(mode === 'preview' ? '正在启动路线预览…' : '正在初始化设备回放，请稍候…');
    await api('/api/start', payload, 120000);
    if (statusPromise) await statusPromise;
    await refreshStatus();
    if (['running', 'starting'].includes(run.state)) notify(mode === 'preview' ? '路线预览已启动。橙色标记显示服务返回的当前位置。' : '设备回放已启动，请在设备端核对实际定位效果。');
  }));
  $('pause-button').addEventListener('click', () => action(async () => {
    const command = run.state === 'paused' ? 'resume' : 'pause';
    await api('/api/control', {action: command});
    if (statusPromise) await statusPromise;
    await refreshStatus();
    notify(command === 'pause' ? '回放已暂停。' : '回放已继续。');
  }));
  $('stop-button').addEventListener('click', () => action(async () => {
    await api('/api/control', {action: 'stop'}, 60000);
    if (statusPromise) await statusPromise;
    await refreshStatus();
    if (!run.cleanupError && !run.error) notify('已发送停止指令。设备模式下，请核对设备定位是否恢复。');
  }));
  $('import-button').addEventListener('click', () => { if (!editingLocked()) $('import-file').click(); });
  $('import-file').addEventListener('change', () => action(async () => {
    const file = $('import-file').files[0];
    $('import-file').value = '';
    if (!file) return;
    if (file.size > 10 * 1024 * 1024) throw new Error('导入文件不能超过 10 MB。');
    const extension = file.name.split('.').pop().toLowerCase();
    const format = extension === 'gpx' ? 'gpx' : extension === 'geojson' ? 'geojson' : 'json';
    const data = await api('/api/import', {text: await file.text(), format});
    const imported = validatePoints(data.points);
    if (imported.length < 2) throw new Error('文件中需要至少两个有效路线点。');
    points = imported;
    changeCount++;
    renderRoute(true);
    notify(`已导入 ${points.length} 个路线点。`);
  }));
  $('export-button').addEventListener('click', () => action(async () => {
    const {points: routePoints, speed, loops} = settings();
    const data = await api('/api/export', {points: routePoints, speed, loops, format: $('export-format').value});
    if (typeof data.text !== 'string' || typeof data.filename !== 'string') throw new Error('服务未返回有效的导出文件。');
    downloadText(data.filename, data.text, data.mime);
    notify('路线文件已生成，浏览器将保存下载文件。');
  }));
  // 「保存到本机」/「读取上次方案」维持原样：显式保存和恢复整条轨迹。
  $('save-button').addEventListener('click', () => {
    try {
      const route = settings(false);
      localStorage.setItem(STORAGE_KEY, JSON.stringify({version: 1, savedAt: new Date().toISOString(), route}));
      notify('当前路线与回放参数已保存在此浏览器，可通过“读取上次方案”恢复。');
    } catch (error) { notify(`保存失败：${error.message}`, true); }
  });
  $('load-button').addEventListener('click', () => {
    if (editingLocked()) return;
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) throw new Error('此浏览器尚未保存路线。');
      const saved = JSON.parse(raw);
      if (saved.version !== 1 || !saved.route) throw new Error('保存的方案格式不受支持。');
      const restored = validatePoints(saved.route.points);
      const speed = Number(saved.route.speed);
      const loops = Number(saved.route.loops);
      if (!Number.isFinite(speed) || speed < 0.2 || speed > 20 || !Number.isInteger(loops) || loops < 0 || loops > 10000) throw new Error('保存的回放参数无效。');
      points = restored;
      $('speed').value = speed;
      $('loop-mode').value = loops === 0 ? 'infinite' : 'finite';
      $('loops').value = loops || 1;
      changeCount++;
      renderRoute(true);
      notify('已恢复上次保存的路线与回放参数。');
    } catch (error) { notify(error.message, true); }
  });
  $('reset-settings-button').addEventListener('click', () => {
    if (!window.confirm('恢复默认回放参数？当前路线会保留。')) return;
    Object.entries(DEFAULT_SETTINGS).forEach(([id, value]) => { $(id).value = value; });
    setFollow(false);
    $('sensor').checked = false;
    updateEstimates();
    updateControls();
    saveNow();
    notify('回放参数已恢复默认值。');
  });
  $('help-button').addEventListener('click', () => $('help-dialog').showModal());
  $('close-help-button').addEventListener('click', () => $('help-dialog').close());
  $('help-done-button').addEventListener('click', () => $('help-dialog').close());
  $('help-dialog').addEventListener('click', event => { if (event.target === $('help-dialog')) { const rect = $('help-dialog').getBoundingClientRect(); if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) $('help-dialog').close(); } });

  // 先恢复上次保存的设置与路线，再初始化界面，避免默认值覆盖已保存的参数。
  restoreSettings();
  initializeMap();
  libraryAction(() => refreshLibrary());
  renderRoute(true);
  modeChanged();
  refreshStatus();
  setInterval(() => { if (!document.hidden || isActive()) refreshStatus(); }, 1000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refreshStatus(); });
})();
