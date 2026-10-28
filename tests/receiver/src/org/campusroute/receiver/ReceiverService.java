package org.campusroute.receiver;

import android.app.*;
import android.content.Intent;
import android.location.*;
import android.os.*;
import android.util.Log;
import java.util.ArrayList;
import org.json.JSONObject;

/** Independent normal-app foreground consumer, never injects or changes mock settings. */
public final class ReceiverService extends Service {
    public static volatile String last="{}";
    LocationManager manager;final ArrayList<LocationListener> listeners=new ArrayList<>();
    JSONObject data=new JSONObject();long callbacks;
    @Override public int onStartCommand(Intent intent,int flags,int id){
        NotificationManager notifications=getSystemService(NotificationManager.class);
        notifications.createNotificationChannel(new NotificationChannel("receiver","接收验证",NotificationManager.IMPORTANCE_LOW));
        startForeground(1,new Notification.Builder(this,"receiver").setSmallIcon(android.R.drawable.ic_menu_mylocation).setContentTitle("仅接收定位的独立测试进程").setContentText("不注入位置；测试结束后卸载").build());
        manager=getSystemService(LocationManager.class);
        if(!listeners.isEmpty())return START_NOT_STICKY;
        for(String channel:new String[]{"gps","network","fused"}){
            try{
                if(!manager.getAllProviders().contains(channel))continue;
                LocationListener listener=new LocationListener(){
                    @Override public void onLocationChanged(Location l){try{
                        JSONObject p=new JSONObject().put("lat",l.getLatitude()).put("lon",l.getLongitude()).put("speed",l.getSpeed()).put("mock",l.isFromMockProvider()).put("elapsedNanos",l.getElapsedRealtimeNanos());
                        data.put(channel,p).put("callbacks",++callbacks);last=data.toString();Log.i("CRS_RECEIVER",last);
                    }catch(Exception e){throw new RuntimeException(e);}}
                    @Override public void onProviderEnabled(String p){}
                    @Override public void onProviderDisabled(String p){}
                    @Override public void onStatusChanged(String p,int s,Bundle b){}
                };
                manager.requestLocationUpdates(channel,500,0,listener,Looper.getMainLooper());listeners.add(listener);
            }catch(Exception e){try{data.put("error",e.toString());last=data.toString();}catch(Exception ignored){}}
        }
        return START_NOT_STICKY;
    }
    @Override public void onDestroy(){if(manager!=null)for(LocationListener listener:listeners)manager.removeUpdates(listener);super.onDestroy();}
    @Override public IBinder onBind(Intent intent){return null;}
}
