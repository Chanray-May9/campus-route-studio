package org.campusroute.bridge;

import android.content.Context;
import android.location.Location;
import android.location.LocationListener;
import android.location.LocationManager;
import android.os.Bundle;
import android.os.HandlerThread;
import android.os.SystemClock;
import java.util.concurrent.atomic.AtomicLong;
import org.json.JSONObject;

/** Independent read-only Android receiver, not part of the Windows product JAR. */
public final class LocationObserver {
    static final AtomicLong callbacks=new AtomicLong();
    static synchronized void emit(JSONObject data){System.out.println("OBS1 "+data);System.out.flush();}
    static JSONObject point(Location l) throws Exception {
        if(l==null)return null;
        return new JSONObject().put("provider",l.getProvider()).put("lat",l.getLatitude()).put("lon",l.getLongitude())
            .put("time",l.getTime()).put("elapsedNanos",l.getElapsedRealtimeNanos()).put("speed",l.getSpeed())
            .put("bearing",l.getBearing()).put("mock",l.isFromMockProvider())
            .put("satellites",l.getExtras()==null?0:l.getExtras().getInt("satellites",0));
    }
    public static void main(String[] args) throws Exception {
        Context context=Main.shellContext();LocationManager manager=context.getSystemService(LocationManager.class);
        HandlerThread thread=new HandlerThread("independent-location-observer");thread.start();
        LocationListener listener=new LocationListener(){
            @Override public void onLocationChanged(Location location){try{emit(new JSONObject().put("event","callback").put("count",callbacks.incrementAndGet()).put("point",point(location)));}catch(Exception e){throw new RuntimeException(e);}}
            @Override public void onProviderEnabled(String p){}
            @Override public void onProviderDisabled(String p){}
            @Override public void onStatusChanged(String p,int s,Bundle b){}
        };
        Runtime.getRuntime().addShutdownHook(new Thread(()->{try{manager.removeUpdates(listener);}catch(Exception ignored){}thread.quitSafely();}));
        emit(new JSONObject().put("event","started").put("pid",android.os.Process.myPid()));
        try{
            for(String provider:new String[]{"gps","network","fused"}){
                if(manager.getAllProviders().contains(provider)){
                    try{manager.requestLocationUpdates(provider,500,0,listener,thread.getLooper());}
                    catch(Exception e){emit(new JSONObject().put("event","subscriptionError").put("provider",provider).put("error",Main.message(e)));}
                }
            }
            long end=SystemClock.elapsedRealtime()+Long.parseLong(args[0])*1000;
            while(SystemClock.elapsedRealtime()<end){
                JSONObject sample=new JSONObject().put("event","sample").put("realtime",SystemClock.elapsedRealtime()).put("callbacks",callbacks.get());
                for(String provider:new String[]{"gps","network","fused"}){
                    try{sample.put(provider,point(manager.getLastKnownLocation(provider)));}
                    catch(Exception e){sample.put(provider+"Error",Main.message(e));}
                }
                emit(sample);Thread.sleep(1000);
            }
        }finally{manager.removeUpdates(listener);thread.quitSafely();}
    }
}
