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
        web=new WebView(this);setContentView(web);web.getSettings().setJavaScriptEnabled(true);web.getSettings().setDomStorageEnabled(true);web.getSettings().setAllowFileAccess(false);web.getSettings().setAllowContentAccess(false);web.getSettings().setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
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
                    case "status":result=ReplayService.status();break;
                    case "start":
                        if(!data.optBoolean("acknowledged"))throw new IllegalArgumentException("请先确认学校场地与路线要求");
                        new RouteEngine(data.getJSONObject("route"),data.optJSONObject("motion"));
                        result=onMain(()->{if(ReplayService.active())throw new IllegalStateException("请先停止当前回放");startForegroundService(new Intent(MobileActivity.this,ReplayService.class).putExtra("config",data.toString()));return new JSONObject().put("starting",true);});break;
                    case "pause":case "resume":case "stop":case "tune":result=onMain(()->{ReplayService.command(action,data);return ReplayService.status();});break;
                    case "permissions":result=onMain(()->{java.util.ArrayList<String> p=new java.util.ArrayList<>();p.add(Manifest.permission.ACCESS_FINE_LOCATION);p.add(Manifest.permission.ACCESS_COARSE_LOCATION);if(Build.VERSION.SDK_INT>=33)p.add(Manifest.permission.POST_NOTIFICATIONS);requestPermissions(p.toArray(new String[0]),10);return new JSONObject();});break;
                    case "developerSettings":result=onMain(()->{startActivity(new Intent(Settings.ACTION_APPLICATION_DEVELOPMENT_SETTINGS));return new JSONObject();});break;
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
