package org.campusroute.tests;
import android.app.Instrumentation;
import android.content.Intent;
import android.os.Bundle;
import android.os.Looper;
import android.os.SystemClock;
import android.location.*;
import org.json.*;
/** Reads actual system fixes, not coordinates reported by the route service. */
public final class CoordinateSmoke extends Instrumentation {
    double lat,lon;
    final LocationListener listener=new LocationListener(){
        @Override public void onLocationChanged(Location l){}
        @Override public void onProviderEnabled(String p){}
        @Override public void onProviderDisabled(String p){}
        @Override public void onStatusChanged(String p,int status,Bundle extras){}
    };
    @Override public void onCreate(Bundle args){super.onCreate(args);lat=Double.parseDouble(args.getString("lat"));lon=Double.parseDouble(args.getString("lon"));start();}
    @Override public void onStart(){Bundle result=new Bundle();LocationManager lm=getTargetContext().getSystemService(LocationManager.class);int code=-1;
        try{
            startActivitySync(new Intent().setClassName("org.campusroute.mobile","org.campusroute.mobile.MobileActivity").addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));SystemClock.sleep(600);
            lm.requestLocationUpdates("gps",200,0,listener,Looper.getMainLooper());SystemClock.sleep(1800);
            Location expected=new Location("expected");expected.setLatitude(lat);expected.setLongitude(lon);
            Location quantized=new Location("MuMuFloat32");quantized.setLatitude((double)(float)lat);quantized.setLongitude((double)(float)lon);
            JSONArray samples=new JSONArray();double max=0,sum=0,maxQuantized=0;long stamp=-1;
            for(int i=0;i<24;i++){
                Location l=lm.getLastKnownLocation("gps");
                if(l==null||SystemClock.elapsedRealtimeNanos()-l.getElapsedRealtimeNanos()>2500000000L)throw new AssertionError("missing or stale GPS fix");
                if(l.isFromMockProvider())throw new AssertionError("native location unexpectedly comes from mock provider");
                if(l.getElapsedRealtimeNanos()!=stamp){double error=l.distanceTo(expected),quantizedError=l.distanceTo(quantized);max=Math.max(max,error);maxQuantized=Math.max(maxQuantized,quantizedError);sum+=error;samples.put(new JSONObject().put("lat",l.getLatitude()).put("lon",l.getLongitude()).put("errorMetres",error).put("quantizedErrorMetres",quantizedError));stamp=l.getElapsedRealtimeNanos();}
                SystemClock.sleep(100);
            }
            if(samples.length()<2)throw new AssertionError("not enough fresh independent fixes");
            // MuMu's native backend stores lat/lon as float32. Verify there is no
            // additional conversion offset beyond representable coordinates + noise.
            boolean ok=maxQuantized<.15&&max<.55;
            result.putString("report",new JSONObject().put("ok",ok).put("targetLat",lat).put("targetLon",lon).put("quantizedLat",quantized.getLatitude()).put("quantizedLon",quantized.getLongitude()).put("maxQuantizedErrorMetres",maxQuantized).put("maxErrorMetres",max).put("meanErrorMetres",sum/samples.length()).put("samples",samples).toString());
            if(!ok)code=0;
        }catch(Throwable e){code=0;result.putString("report","FAIL: "+e.toString());}
        finally{lm.removeUpdates(listener);}
        finish(code,result);
    }
}
