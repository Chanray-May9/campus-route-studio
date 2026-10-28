const {chromium}=require('playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
(async()=>{
  const browser=await chromium.launch({headless:true});
  const page=await browser.newPage({viewport:{width:1280,height:900}});
  const root=path.resolve(__dirname,'../route_studio/web'),errors=[],posts=[];let denied=false;
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('https://*.is.autonavi.com/**',r=>r.abort());
  await page.route('http://127.0.0.1:18765/**',async route=>{
    const req=route.request(),pathname=new URL(req.url()).pathname;
    if(pathname.startsWith('/api/')){
      let status=200,data;
      if(req.method()==='POST')posts.push({path:pathname,data:JSON.parse(req.postData())});
      if(pathname==='/api/status')data={run:{state:'idle',elapsed:0,distance:0,sentUpdates:0},info:{version:'0.6.4'}};
      else if(pathname==='/api/library')data={entries:[]};
      else if(pathname==='/api/devices')data={android:[{serial:'selected-phone',state:'device',model:'Test phone'}],ios:[],dependencies:{adb:true,ios:true},errors:[]};
      else if(pathname==='/api/android/probe'){
        status=denied?400:200;data=denied?{error:'系统拒绝安卓直连测试进程'}:{probe:true,message:'安卓直连基础检测通过，手机不安装 APK。'};
      }else{status=404;data={error:'unexpected endpoint'};}
      return route.fulfill({status,contentType:'application/json',body:JSON.stringify(data)});
    }
    const file=path.join(root,pathname==='/'?'index.html':pathname.slice(1));
    if(!fs.existsSync(file))return route.fulfill({status:404,body:''});
    return route.fulfill({path:file,contentType:file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':file.endsWith('.png')?'image/png':'text/html'});
  });
  await page.goto('http://127.0.0.1:18765/');
  await page.selectOption('#mode','android');
  await page.waitForFunction(()=>document.querySelector('#android-device').value==='selected-phone');
  assert.equal(await page.textContent('#setup-button'),'检测安卓直连');
  assert.doesNotMatch(await page.textContent('#android-fields'),/安装定位助手|选择模拟位置信息应用/);
  await page.click('#setup-button');await page.waitForFunction(()=>document.querySelector('#notice').textContent.includes('基础检测通过'));
  assert.deepEqual(posts,[{path:'/api/android/probe',data:{serial:'selected-phone'}}]);
  denied=true;await page.click('#setup-button');await page.waitForFunction(()=>document.querySelector('#notice').textContent.includes('系统拒绝'));
  assert.equal(await page.isDisabled('#setup-button'),false);
  assert.equal(posts.length,2);assert.equal(posts.some(p=>/setup|install/.test(p.path)),false);
  if(process.env.UI_SCREENSHOT)await page.screenshot({path:process.env.UI_SCREENSHOT,fullPage:true});
  assert.deepEqual(errors,[]);await browser.close();
  console.log('PASS: desktop direct Android mode, no APK-install UI/API, selected-device probe, refusal feedback. API is mocked; no phone acceptance.');
})().catch(e=>{console.error(e);process.exit(1)});
