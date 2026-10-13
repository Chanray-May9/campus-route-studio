package org.campusroute.mobile;

import android.Manifest;
import android.app.Activity;
import android.content.*;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.*;
import android.provider.Settings;
import android.webkit.*;
import android.location.*;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import java.nio.charset.StandardCharsets;
import org.json.*;

public final class MobileActivity extends Activity {
    WebView web;
    AppStore store;
    final Handler main=new Handler(Looper.getMainLooper());
    @Override public void onCreate(Bundle saved){super.onCreate(saved);try{store=new AppStore(this);}catch(Exception e){throw new IllegalStateException(e);}
        WebView.setWebContentsDebuggingEnabled(store.config.optBoolean("debug",false));
        web=new WebView(this);setContentView(web);
        web.setOnApplyWindowInsetsListener((view,insets)->{
            if(Build.VERSION.SDK_INT>=30){android.graphics.Insets bars=insets.getInsets(android.view.WindowInsets.Type.systemBars()|android.view.WindowInsets.Type.displayCutout());view.setPadding(bars.left,bars.top,bars.right,bars.bottom);}
            else view.setPadding(insets.getSystemWindowInsetLeft(),insets.getSystemWindowInsetTop(),insets.getSystemWindowInsetRight(),insets.getSystemWindowInsetBottom());
            return insets;
        });web.getSettings().setJavaScriptEnabled(true);web.getSettings().setDomStorageEnabled(true);web.getSettings().setAllowFileAccess(false);web.getSettings().setAllowContentAccess(false);web.getSettings().setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        web.setWebViewClient(new WebViewClient(){
            @Override public boolean shouldOverrideUrlLoading(WebView v,WebResourceRequest r){return !"appassets.androidplatform.net".equals(r.getUrl().getHost());}
            @Override public WebResourceResponse shouldInterceptRequest(WebView v,WebResourceRequest request){
                Uri u=request.getUrl();if(!"appassets.androidplatform.net".equals(u.getHost()))return null;
                String path=u.getPath();if(path==null||path.contains(".."))return new WebResourceResponse("text/plain","UTF-8",new java.io.ByteArrayInputStream(new byte[0]));
                try{String name=path.equals("/")?"index.html":path.substring(1);String mime=name.endsWith(".js")?"text/javascript":name.endsWith(".css")?"text/css":name.endsWith(".png")?"image/png":"text/html";return new WebResourceResponse(mime,"UTF-8",getAssets().open(name));}catch(Exception e){return new WebResourceResponse("text/plain","UTF-8",404,"Not Found",java.util.Collections.emptyMap(),new java.io.ByteArrayInputStream(new byte[0]));}
            }
        });
        web.setWebChromeClient(new WebChromeClient(){
            @Override public boolean onJsConfirm(WebView view,String url,String message,JsResult result){
                new android.app.AlertDialog.Builder(MobileActivity.this).setMessage(message).setPositiveButton("确定",(dialog,which)->result.confirm()).setNegativeButton("取消",(dialog,which)->result.cancel()).setOnCancelListener(dialog->result.cancel()).show();return true;
            }
        });
        web.addJavascriptInterface(new Bridge(),"Native");web.loadUrl("https://appassets.androidplatform.net/");
    }
    JSONObject setupStatus() throws Exception {
        JSONObject result=new JSONObject();
        try{result.put("developerEnabled",Settings.Global.getInt(getContentResolver(),Settings.Global.DEVELOPMENT_SETTINGS_ENABLED,0)!=0);}catch(Exception ignored){result.put("developerEnabled",JSONObject.NULL);}
        result.put("mockSelected",getSystemService(android.app.AppOpsManager.class).checkOpNoThrow(android.app.AppOpsManager.OPSTR_MOCK_LOCATION,android.os.Process.myUid(),getPackageName())==android.app.AppOpsManager.MODE_ALLOWED);
        result.put("finePermission",checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION)==PackageManager.PERMISSION_GRANTED);
        LocationManager manager=getSystemService(LocationManager.class);
        result.put("locationEnabled",Build.VERSION.SDK_INT>=28?manager.isLocationEnabled():manager.isProviderEnabled("gps")||manager.isProviderEnabled("network"));
        return result;
    }
    String openSettings(String... actions){
        for(String action:actions){try{startActivity(new Intent(action));return action;}catch(ActivityNotFoundException|SecurityException ignored){}}
        throw new IllegalStateException("无法跳转系统设置，请手动打开设置，进入关于手机或搜索开发者选项");
    }
    JSONObject developerSettings() throws Exception {
        JSONObject setup=setupStatus();
        boolean needsEnable=setup.has("developerEnabled")&&!setup.isNull("developerEnabled")&&!setup.getBoolean("developerEnabled");
        String action=needsEnable?openSettings(Settings.ACTION_DEVICE_INFO_SETTINGS,Settings.ACTION_SETTINGS):openSettings(Settings.ACTION_APPLICATION_DEVELOPMENT_SETTINGS,Settings.ACTION_DEVICE_INFO_SETTINGS,Settings.ACTION_SETTINGS);
        boolean direct=Settings.ACTION_APPLICATION_DEVELOPMENT_SETTINGS.equals(action);
        return new JSONObject().put("needsEnable",needsEnable).put("openedDeveloper",direct).put("message",direct?"在开发者选项中找到“选择模拟位置信息应用”，选择“校园乐跑助手”，然后返回。":"进入关于手机（部分手机在软件信息中），连续点击版本号/Build 号约 7 次，直到系统提示已进入开发者模式。再在设置中搜索“开发者选项”，选择模拟位置信息应用为“校园乐跑助手”。具体名称因手机而异。");
    }
    interface Task {JSONObject run() throws Exception;}
    JSONObject onMain(Task task) throws Exception {
        AtomicReference<JSONObject> result=new AtomicReference<>();AtomicReference<Exception> failure=new AtomicReference<>();CountDownLatch latch=new CountDownLatch(1);
        main.post(()->{try{result.set(task.run());}catch(Exception e){failure.set(e);}finally{latch.countDown();}});
        if(!latch.await(8,TimeUnit.SECONDS))throw new IllegalStateException("手机操作超时");if(failure.get()!=null)throw failure.get();return result.get();
    }
    public final class Bridge {
        @JavascriptInterface public String request(String action,String text){
            try {
                JSONObject data=new JSONObject(text==null?"{}":text),result=new JSONObject();ApiClient api=new ApiClient(store);
                switch(action){
                    case "status":result=onMain(()->ReplayService.status().put("setup",setupStatus()));break;
                    case "start":
                        if(!data.optBoolean("acknowledged"))throw new IllegalArgumentException("请先确认学校场地与路线要求");
                        new RouteEngine(data.getJSONObject("route"),data.optJSONObject("motion"));
                        CountDownLatch ready=new CountDownLatch(1);AtomicReference<Bundle> startup=new AtomicReference<>();
                        ResultReceiver receipt=new ResultReceiver(main){@Override protected void onReceiveResult(int code,Bundle value){value.putBoolean("ok",code==1);startup.set(value);ready.countDown();}};
                        onMain(()->{if(ReplayService.active())throw new IllegalStateException("请先停止当前跑步");startForegroundService(new Intent(MobileActivity.this,ReplayService.class).putExtra("config",data.toString()).putExtra("reply",receipt));return new JSONObject();});
                        if(!ready.await(5,TimeUnit.SECONDS)){
                            onMain(()->{startService(new Intent(MobileActivity.this,ReplayService.class).putExtra("action","stop"));return new JSONObject();});
                            throw new IllegalStateException("首个定位坐标发送超时，跑步已取消");
                        }
                        Bundle response=startup.get();if(!response.getBoolean("ok"))throw new IllegalStateException(response.getString("error","跑步定位启动失败"));
                        result=new JSONObject(response.getString("status","{}"));break;
                    case "pause":case "resume":case "stop":case "tune":ReplayService.command(action,data);result=ReplayService.status();break;
                    case "permissions":result=onMain(()->{java.util.ArrayList<String> p=new java.util.ArrayList<>();p.add(Manifest.permission.ACCESS_FINE_LOCATION);p.add(Manifest.permission.ACCESS_COARSE_LOCATION);if(Build.VERSION.SDK_INT>=33)p.add(Manifest.permission.POST_NOTIFICATIONS);requestPermissions(p.toArray(new String[0]),10);return new JSONObject();});break;
                    case "developerSettings":result=onMain(()->developerSettings());break;
                    case "aboutPhone":result=onMain(()->new JSONObject().put("action",openSettings(Settings.ACTION_DEVICE_INFO_SETTINGS,Settings.ACTION_SETTINGS)));break;
                    case "location":result=onMain(()->{
                        if(ReplayService.active())throw new IllegalStateException("正在模拟定位，停止后再获取手机实际位置");
                        if(checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION)!=PackageManager.PERMISSION_GRANTED)throw new SecurityException("请先授予定位权限");
                        Location best=null;LocationManager manager=getSystemService(LocationManager.class);for(String provider:new String[]{"gps","network"}){Location l=manager.getLastKnownLocation(provider);if(l!=null&&(best==null||l.getTime()>best.getTime()))best=l;}
                        if(best==null||System.currentTimeMillis()-best.getTime()>300000)throw new IllegalStateException("暂无近期位置，请先打开手机地图获取定位后重试，或直接输入学校坐标");
                        return new JSONObject().put("lat",best.getLatitude()).put("lon",best.getLongitude()).put("accuracy",best.getAccuracy());});break;
                    case "library":result.put("entries",store.library());break;
                    case "save":result=store.save(data);break;
                    case "delete":store.delete(data.getString("id"));break;
                    case "remoteRoutes":result=api.request("/api/routes");break;
                    default:throw new IllegalArgumentException("未知操作");
                }
                return new JSONObject().put("ok",true).put("data",result).toString();
            }catch(Exception e){try{return new JSONObject().put("ok",false).put("error",ReplayService.message(e)).toString();}catch(Exception ignored){return "{\"ok\":false,\"error\":\"操作失败\"}";}}
        }
    }
    @Override public void onDestroy(){if(web!=null){web.removeJavascriptInterface("Native");web.destroy();}super.onDestroy();}
}
