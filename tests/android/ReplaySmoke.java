package org.campusroute.tests;
import android.app.Instrumentation;
import android.content.Intent;
import android.os.Bundle;
import android.os.SystemClock;
import org.json.JSONObject;
import android.location.Location;
import android.location.LocationManager;
/** Run on a designated test device with mock-location permission enabled. */
public final class ReplaySmoke extends Instrumentation {
    Class<?> service;
    JSONObject status() throws Exception {
        final JSONObject[] result=new JSONObject[1];final Exception[] error=new Exception[1];
        runOnMainSync(()->{try{result[0]=(JSONObject)service.getMethod("status").invoke(null);}catch(Exception e){error[0]=e;}});
        if(error[0]!=null)throw error[0];return result[0];
    }
    void command(String action) throws Exception {
        final Exception[] error=new Exception[1];runOnMainSync(()->{try{service.getMethod("command",String.class,JSONObject.class).invoke(null,action,new JSONObject());}catch(Exception e){error[0]=e;}});if(error[0]!=null)throw error[0];
    }
    void check(boolean value,String message){if(!value)throw new AssertionError(message);}
    @Override public void onCreate(Bundle args){super.onCreate(args);start();}
    @Override public void onStart(){Bundle result=new Bundle();int code=-1;
        try{
            service=getTargetContext().getClassLoader().loadClass("org.campusroute.mobile.ReplayService");
            startActivitySync(new Intent().setClassName("org.campusroute.mobile","org.campusroute.mobile.MobileActivity").addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));SystemClock.sleep(1000);
            Intent i=new Intent().setClassName("org.campusroute.mobile","org.campusroute.mobile.ReplayService");
            i.putExtra("config","{\"locationMode\":\""+"phone"+"\",\"route\":{\"points\":[{\"lat\":30,\"lon\":120},{\"lat\":30.01,\"lon\":120}],\"speed\":2.8,\"loops\":2}}");
            runOnMainSync(()->getTargetContext().startForegroundService(i));SystemClock.sleep(4500);
            JSONObject a=status();check(a.getString("state").equals("running"),a.toString());check(a.getDouble("distance")>8,a.toString());check(a.getLong("received")>2,a.toString());check(a.getDouble("receivedMovement")>5,a.toString());check(!a.getJSONArray("providers").toString().contains("fused"),"must preserve native fused provider");check(a.getLong("fusedReceived")>0,"no native fused callback");
            LocationManager lm=getTargetContext().getSystemService(LocationManager.class);
            Location gps=lm.getLastKnownLocation("gps");
            check(gps!=null&&gps.getExtras()!=null&&gps.getExtras().getInt("satellites",0)>0,"GPS quality metadata missing after system delivery");
            check(gps.isFromMockProvider(),"mock location must retain its system marker");
            Location first=lm.getLastKnownLocation("fused");check(first!=null,"no fused position");
            getTargetContext().startActivity(new Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_HOME).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));SystemClock.sleep(2500);
            Location next=lm.getLastKnownLocation("fused");check(next!=null&&first.distanceTo(next)>4,"system fused position stuck in background");check(next.getElapsedRealtimeNanos()>first.getElapsedRealtimeNanos(),"stale system time");
            for(String provider:new String[]{"gps","network"}){Location l=lm.getLastKnownLocation(provider);check(l!=null&&l.distanceTo(next)<6,provider+" is not synchronized");}
            command("pause");SystemClock.sleep(1000);JSONObject b=status();Location pausedPosition=lm.getLastKnownLocation("fused");SystemClock.sleep(1500);JSONObject c=status();check(pausedPosition.distanceTo(lm.getLastKnownLocation("fused"))<0.2,"system position moved while paused");check(Math.abs(b.getDouble("distance")-c.getDouble("distance"))<0.001,"pause advanced");check(c.getDouble("wallElapsed")>b.getDouble("wallElapsed"),"paused wall time not counted");
            command("resume");SystemClock.sleep(2000);JSONObject d=status();check(d.getDouble("distance")>c.getDouble("distance")+3,"resume failed");getUiAutomation().executeShellCommand("input keyevent KEYCODE_SLEEP").close();SystemClock.sleep(6000);JSONObject screenOff=status();check(screenOff.getDouble("distance")>d.getDouble("distance")+10,"screen-off replay stalled");getUiAutomation().executeShellCommand("input keyevent KEYCODE_WAKEUP").close();
            command("stop");SystemClock.sleep(500);check(status().getString("state").equals("idle"),"stop failed");check(status().getString("cleanupError").isEmpty(),"provider cleanup failed");
            runOnMainSync(()->getTargetContext().startActivity(new Intent().setClassName("org.campusroute.mobile","org.campusroute.mobile.MobileActivity").addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)));SystemClock.sleep(1000);
            Intent shortRun=new Intent().setClassName("org.campusroute.mobile","org.campusroute.mobile.ReplayService");shortRun.putExtra("config","{\"locationMode\":\""+"phone"+"\",\"route\":{\"points\":[{\"lat\":30,\"lon\":120},{\"lat\":30.00005,\"lon\":120}],\"speed\":2.8,\"loops\":1}}");
            runOnMainSync(()->getTargetContext().startForegroundService(shortRun));SystemClock.sleep(3500);JSONObject completed=status();check(completed.getString("state").equals("completed"),completed.toString());check(completed.getString("cleanupError").isEmpty(),"completion cleanup failed");check(Math.abs(completed.getJSONObject("point").getDouble("lat")-30.00005)<0.0000001,"endpoint missing");
            result.putString("report","PASS: independent GPS/network/fused system positions and background movement; movement, framework fused callbacks, pause (system position frozen), paused wall time, resume, screen-off movement, stop/cleanup, restart and natural completion. Moving status: "+a.toString());
        }catch(Throwable e){code=0;result.putString("report","FAIL: "+e.toString());try{command("stop");}catch(Exception ignored){}}
        finish(code,result);
    }
}
