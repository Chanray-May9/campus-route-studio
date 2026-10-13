package org.campusroute.tests;

import android.app.Instrumentation;
import android.content.Intent;
import android.os.Bundle;
import android.os.SystemClock;
import org.json.JSONObject;

/** Runs the installed release APK's ordinary phone service while a separate probe reads the receiver UI. */
public final class ReceivingProbe extends Instrumentation {
    Class<?> service;
    @Override public void onCreate(Bundle args){super.onCreate(args);start();}
    @Override public void onStart(){
        Bundle result=new Bundle();int code=-1;
        try{
            service=getTargetContext().getClassLoader().loadClass("org.campusroute.mobile.ReplayService");
            startActivitySync(new Intent().setClassName("org.campusroute.mobile","org.campusroute.mobile.MobileActivity").addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
            java.io.ByteArrayOutputStream bytes=new java.io.ByteArrayOutputStream();
            try(java.io.InputStream in=getTargetContext().getAssets().open("default-route.json")){
                byte[] buffer=new byte[4096];int n;while((n=in.read(buffer))!=-1)bytes.write(buffer,0,n);
            }
            JSONObject route=new JSONObject(bytes.toString("UTF-8")).getJSONObject("route");
            route.put("speed",2.8).put("loops",1);
            JSONObject config=new JSONObject().put("route",route).put("motion",new JSONObject().put("mode","fixed").put("speed",2.8));
            Intent start=new Intent().setClassName("org.campusroute.mobile","org.campusroute.mobile.ReplayService").putExtra("config",config.toString());
            runOnMainSync(()->getTargetContext().startForegroundService(start));
            SystemClock.sleep(1000);
            JSONObject initial=(JSONObject)service.getMethod("status").invoke(null);
            if(!"running".equals(initial.optString("state")))throw new AssertionError(initial.toString());
            Bundle ready=new Bundle();ready.putString("ready","true");sendStatus(1,ready);
            SystemClock.sleep(40000);
            JSONObject status=(JSONObject)service.getMethod("status").invoke(null);
            if(status.optDouble("distance")<100||status.optLong("received")<20)throw new AssertionError(status.toString());
            result.putString("report",status.toString());
        }catch(Throwable e){code=0;result.putString("report","FAIL: "+e.toString());}
        finally{
            if(service!=null)try{service.getMethod("command",String.class,JSONObject.class).invoke(null,"stop",new JSONObject());}catch(Exception ignored){}
        }
        finish(code,result);
    }
}
