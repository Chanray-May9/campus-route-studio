package org.campusroute.mobile;

import android.Manifest;
import android.app.*;
import android.content.*;
import android.content.pm.PackageManager;
import android.location.*;
import android.os.*;
import org.json.JSONObject;

public final class ReplayService extends Service {
    static ReplayService instance;
    static volatile String state="idle",error="",cleanupError="";
    static volatile JSONObject last=new JSONObject();
    final Handler handler=new Handler(Looper.getMainLooper());
    LocationManager locations;
    AppStore store;
    RouteEngine engine;
    PowerManager.WakeLock wake;
    long previous,sent;
    boolean gpsAdded,networkAdded;
    public static boolean active(){return instance!=null&&(state.equals("running")||state.equals("paused")||state.equals("starting"));}
    @Override public void onCreate(){super.onCreate();instance=this;locations=getSystemService(LocationManager.class);}
    @Override public int onStartCommand(Intent intent,int flags,int id){
        if(intent!=null&&"stop".equals(intent.getStringExtra("action"))){stop("idle","");return START_NOT_STICKY;}
        if(active()&&engine!=null)return START_NOT_STICKY;
        state="starting";error="";cleanupError="";last=new JSONObject();sent=0;
        try {
            notifyRunning();store=new AppStore(this);
            if(checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION)!=PackageManager.PERMISSION_GRANTED)throw new SecurityException("请先授予精确位置权限");
            if(getSystemService(AppOpsManager.class).checkOpNoThrow(AppOpsManager.OPSTR_MOCK_LOCATION,android.os.Process.myUid(),getPackageName())!=AppOpsManager.MODE_ALLOWED)throw new SecurityException("请在开发者选项中选择“校园路线”为模拟位置应用");
            if(Build.VERSION.SDK_INT>=28&&!locations.isLocationEnabled())throw new IllegalStateException("请开启手机定位服务");
            JSONObject config=new JSONObject(intent.getStringExtra("config"));engine=new RouteEngine(config.getJSONObject("route"),config.optJSONObject("motion"));
            locations.addTestProvider("gps",false,false,false,false,true,true,true,Criteria.POWER_LOW,Criteria.ACCURACY_FINE);gpsAdded=true;locations.setTestProviderEnabled("gps",true);
            locations.addTestProvider("network",false,false,false,false,true,true,true,Criteria.POWER_LOW,Criteria.ACCURACY_FINE);networkAdded=true;locations.setTestProviderEnabled("network",true);
            wake=getSystemService(PowerManager.class).newWakeLock(PowerManager.PARTIAL_WAKE_LOCK,"campusroute:StandaloneReplay");wake.setReferenceCounted(false);wake.acquire(15000);
            previous=SystemClock.elapsedRealtime();state="running";handler.post(tick);
        }catch(Exception e){stop("error",message(e));}
        return START_NOT_STICKY;
    }
    final Runnable tick=new Runnable(){@Override public void run(){
        try {
            long now=SystemClock.elapsedRealtime();double dt=(now-previous)/1000.0;previous=now;
            engine.advance(dt,Double.POSITIVE_INFINITY);
            JSONObject point=engine.point();long time=System.currentTimeMillis(),nanos=SystemClock.elapsedRealtimeNanos();
            for(String provider:new String[]{"gps","network"}){Location l=new Location(provider);l.setLatitude(point.getDouble("lat"));l.setLongitude(point.getDouble("lon"));l.setAccuracy(5);l.setSpeed((float)point.getDouble("speed"));l.setBearing((float)point.getDouble("bearing"));l.setTime(time);l.setElapsedRealtimeNanos(nanos);locations.setTestProviderLocation(provider,l);}
            sent++;last=new JSONObject().put("distance",engine.distance).put("elapsed",engine.elapsed).put("point",point).put("sent",sent).put("laps",(int)(engine.distance/engine.lap)).put("infinite",engine.loops==0).put("total",engine.loops==0?JSONObject.NULL:engine.total);
            if(engine.distance>=engine.total){stop("completed","");return;}
            if(wake!=null)wake.acquire(15000);handler.postDelayed(this,1000);
        }catch(Exception e){stop("error",message(e));}
    }};
    static String message(Exception e){return e.getMessage()==null?e.getClass().getSimpleName():e.getMessage();}
    void notifyRunning(){
        NotificationManager nm=getSystemService(NotificationManager.class);nm.createNotificationChannel(new NotificationChannel("replay","轨迹回放",NotificationManager.IMPORTANCE_LOW));
        PendingIntent open=PendingIntent.getActivity(this,0,new Intent(this,MobileActivity.class),PendingIntent.FLAG_IMMUTABLE);
        PendingIntent stop=PendingIntent.getService(this,1,new Intent(this,ReplayService.class).putExtra("action","stop"),PendingIntent.FLAG_IMMUTABLE|PendingIntent.FLAG_UPDATE_CURRENT);
        Notification n=new Notification.Builder(this,"replay").setSmallIcon(android.R.drawable.ic_menu_mylocation).setContentTitle("校园路线 · 定位回放").setContentText("手机独立回放中；请按学校要求规划准确路线").setContentIntent(open).setOngoing(true).addAction(new Notification.Action.Builder(null,"停止",stop).build()).build();
        startForeground(101,n);
    }
    void cleanup(){
        handler.removeCallbacks(tick);if(wake!=null&&wake.isHeld())wake.release();
        for(String provider:new String[]{"gps","network"}){boolean added=provider.equals("gps")?gpsAdded:networkAdded;if(!added)continue;try{locations.removeTestProvider(provider);}catch(Exception e){cleanupError=message(e);}}
        gpsAdded=false;networkAdded=false;
    }
    void stop(String next,String reason){state=next;error=reason;cleanup();stopForeground(STOP_FOREGROUND_REMOVE);stopSelf();}
    public static JSONObject status() throws Exception {return new JSONObject(last.toString()).put("state",state).put("error",error).put("cleanupError",cleanupError);}
    public static void command(String action,JSONObject data) throws Exception {
        ReplayService s=instance;if(s==null||s.engine==null||!active())throw new IllegalStateException("当前没有正在回放的轨迹");
        if(action.equals("pause")){s.engine.paused=true;state="paused";}
        else if(action.equals("resume")){s.engine.paused=false;state="running";}
        else if(action.equals("tune")){s.engine.motion=RouteEngine.validateMotion(data,s.engine.motion.optDouble("speed"));}
        else if(action.equals("stop"))s.stop("idle","");
        else throw new IllegalArgumentException("操作无效");
    }
    @Override public void onDestroy(){cleanup();if(instance==this)instance=null;if(state.equals("running")||state.equals("paused")){state="idle";error="服务已停止";}super.onDestroy();}
    @Override public IBinder onBind(Intent i){return null;}
}
