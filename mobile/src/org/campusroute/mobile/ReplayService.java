package org.campusroute.mobile;

import android.Manifest;
import android.app.*;
import android.content.*;
import android.content.pm.PackageManager;
import android.location.*;
import android.os.*;
import java.util.ArrayList;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import org.json.JSONObject;

/** A single worker owns route timing, commands and device I/O, including in background. */
public final class ReplayService extends Service {
    static volatile ReplayService instance;
    static volatile String state="idle",error="",cleanupError="";
    static volatile JSONObject last=new JSONObject();
    Handler handler;
    HandlerThread worker;
    LocationManager locations;
    RouteEngine engine;
    JSONObject runConfig;
    volatile boolean stopping;
    long checkpointAt;
    double recoveredWall;
    int restores;
    final Object checkpointLock=new Object();
    PowerManager.WakeLock wake;
    long previous,sent,started,received,fusedReceived;
    long lastSent;
    double maxSendGap;
    double receivedMovement;
    Location observed;
    final ArrayList<String> providers=new ArrayList<>(),ownedProviders=new ArrayList<>();
    JSONObject providerErrors=new JSONObject();
    final LocationListener observer=new LocationListener(){
        @Override public void onLocationChanged(Location l){if(observed!=null)receivedMovement+=observed.distanceTo(l);observed=new Location(l);received++;}
        @Override public void onProviderEnabled(String p){}
        @Override public void onProviderDisabled(String p){}
        @Override public void onStatusChanged(String p,int status,Bundle extras){}
    };
    final LocationListener fusedObserver=new LocationListener(){
        @Override public void onLocationChanged(Location l){fusedReceived++;}
        @Override public void onProviderEnabled(String p){}
        @Override public void onProviderDisabled(String p){}
        @Override public void onStatusChanged(String p,int status,Bundle extras){}
    };
    public static boolean active(){return instance!=null&&(state.equals("running")||state.equals("paused")||state.equals("starting"));}
    public static boolean recoveryEnabled(Context context){return context.getSharedPreferences("campus_route",MODE_PRIVATE).getBoolean("restart_enabled",true);}
    @Override public void onCreate(){
        super.onCreate();instance=this;state="idle";locations=getSystemService(LocationManager.class);
        worker=new HandlerThread("campus-run");worker.start();handler=new Handler(worker.getLooper());
    }
    @Override public int onStartCommand(Intent intent,int flags,int id){
        if(intent!=null&&"stop".equals(intent.getStringExtra("action"))){stopping=true;clearCheckpoint();handler.post(()->stop("idle",""));return START_NOT_STICKY;}
        ResultReceiver reply=intent==null?null:intent.getParcelableExtra("reply");
        if(active()){respond(reply,false,"已有跑步正在进行，请先结束");return recoveryEnabled(this)?START_STICKY:START_NOT_STICKY;}
        state="starting";error="";cleanupError="";last=new JSONObject();
        stopping=false;
        try{
            String saved=intent==null&&recoveryEnabled(this)?getSharedPreferences("run_session",MODE_PRIVATE).getString("checkpoint",null):null;
            if(intent==null&&saved==null){stop("idle","");return START_NOT_STICKY;}
            notifyRunning(); // Meet the foreground-service deadline before asynchronous I/O.
            JSONObject config=intent==null?null:new JSONObject(intent.getStringExtra("config"));
            handler.post(()->startRun(config,saved,reply));
        }catch(Exception e){handler.post(()->{stop("error",message(e));respond(reply,false,message(e));});}
        return recoveryEnabled(this)?START_STICKY:START_NOT_STICKY;
    }
    void startRun(JSONObject config,String saved,ResultReceiver reply){
        sent=received=fusedReceived=0;receivedMovement=0;observed=null;providerErrors=new JSONObject();
        lastSent=0;maxSendGap=0;checkpointAt=0;recoveredWall=0;restores=0;
        try{
            if(stopping){stop("idle","");respond(reply,false,"启动已取消");return;}
            if(checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION)!=PackageManager.PERMISSION_GRANTED)throw new SecurityException("请先授予精确位置权限");
            if(Build.VERSION.SDK_INT>=28&&!locations.isLocationEnabled())throw new IllegalStateException("请开启手机定位服务");
            if(saved!=null){
                RunCheckpoint restored=RunCheckpoint.restore(new JSONObject(saved),SystemClock.elapsedRealtime());
                runConfig=restored.config;engine=restored.engine;recoveredWall=restored.wallElapsed;sent=restored.sent;restores=restored.restores;
            }else{
                clearCheckpoint();runConfig=new JSONObject(config.toString());
                engine=new RouteEngine(config.getJSONObject("route"),config.optJSONObject("motion"));
            }
            if(getSystemService(AppOpsManager.class).checkOpNoThrow(AppOpsManager.OPSTR_MOCK_LOCATION,android.os.Process.myUid(),getPackageName())!=AppOpsManager.MODE_ALLOWED)throw new SecurityException("请在开发者选项中选择“校园乐跑助手”为模拟位置应用");
            registerProvider(LocationManager.GPS_PROVIDER);registerProvider(LocationManager.NETWORK_PROVIDER);
            if(providers.isEmpty())throw new IllegalStateException("GPS 和网络定位都无法启用："+providerErrors);
            wake=getSystemService(PowerManager.class).newWakeLock(PowerManager.PARTIAL_WAKE_LOCK,"campusroute:Run");wake.setReferenceCounted(false);wake.acquire(15000);
            String provider=providers.contains("gps")?"gps":providers.get(0);
            if(locations.getAllProviders().contains(provider))locations.requestLocationUpdates(provider,500,0,observer,worker.getLooper());
            if(locations.getAllProviders().contains("fused")){
                try{locations.requestLocationUpdates("fused",500,0,fusedObserver,worker.getLooper());}
                catch(Exception e){providerErrors.put("fusedSubscription",message(e));}
            }
            started=previous=SystemClock.elapsedRealtime();sendPoint(started);
            state=engine.paused?"paused":"running";saveCheckpoint(true);respond(reply,true,"");handler.postDelayed(tick,500);
        }catch(Exception e){stop("error",message(e));respond(reply,false,message(e));}
    }
    final Runnable tick=()->{
        try{
            if(stopping)return;
            long now=SystemClock.elapsedRealtime();double dt=(now-previous)/1000.0;previous=now;
            engine.advance(dt,Double.POSITIVE_INFINITY);sendPoint(now);
            if(engine.distance>=engine.total){stop("completed","");return;}
            saveCheckpoint(false);
            if(wake!=null)wake.acquire(15000);handler.postDelayed(this.tick,500);
        }catch(Exception e){stop("error",message(e));}
    };
    void sendPoint(long now) throws Exception {
        JSONObject point=engine.point();long time=System.currentTimeMillis(),nanos=SystemClock.elapsedRealtimeNanos();
        for(String provider:new ArrayList<>(providers)){
            try{
                Location l=new Location(provider);l.setLatitude(point.getDouble("lat"));l.setLongitude(point.getDouble("lon"));l.setAccuracy(5);l.setAltitude(0);
                l.setSpeed((float)point.getDouble("speed"));l.setBearing((float)point.getDouble("bearing"));l.setTime(time);l.setElapsedRealtimeNanos(nanos);
                l.setSpeedAccuracyMetersPerSecond(.25f);l.setBearingAccuracyDegrees(3f);l.setVerticalAccuracyMeters(5f);
                // Some location consumers require this legacy GPS quality field.
                // This is simulated metadata, not a measurement of real satellites.
                if(LocationManager.GPS_PROVIDER.equals(provider)){
                    Bundle quality=new Bundle();quality.putInt("satellites",12);l.setExtras(quality);
                }
                locations.setTestProviderLocation(provider,l);
            }catch(Exception e){providerErrors.put(provider,message(e));providers.remove(provider);try{locations.removeTestProvider(provider);}catch(Exception ignored){}}
        }
        if(providers.isEmpty())throw new IllegalStateException("所有定位通道发送失败："+providerErrors);
        if(lastSent!=0)maxSendGap=Math.max(maxSendGap,(now-lastSent)/1000.0);
        lastSent=now;
        JSONObject snapshot=new JSONObject().put("distance",engine.distance).put("elapsed",engine.elapsed).put("point",point).put("sent",++sent)
            .put("lastSentRealtime",now).put("maxSendGap",maxSendGap)
            .put("providers",new org.json.JSONArray(providers)).put("providerErrors",new JSONObject(providerErrors.toString()))
            .put("laps",(int)(engine.distance/engine.lap)).put("infinite",engine.loops==0).put("total",engine.loops==0?JSONObject.NULL:engine.total)
            .put("wallElapsed",recoveredWall+(now-started)/1000.0).put("received",received).put("receivedMovement",receivedMovement).put("fusedReceived",fusedReceived).put("restores",restores);
        if(observed!=null){
            double age=(SystemClock.elapsedRealtimeNanos()-observed.getElapsedRealtimeNanos())/1000000000.0;
            snapshot.put("observedPoint",new JSONObject().put("lat",observed.getLatitude()).put("lon",observed.getLongitude())).put("observedAge",Math.max(0,age));
        }
        last=snapshot; // Publish a complete snapshot, without sharing mutable worker data.
    }
    void respond(ResultReceiver reply,boolean ok,String reason){
        if(reply==null)return;Bundle data=new Bundle();data.putString("error",reason);
        try{data.putString("status",status().toString());}catch(Exception ignored){}
        reply.send(ok?1:0,data);
    }
    static String message(Exception e){return e.getMessage()==null?e.getClass().getSimpleName():e.getMessage();}
    void registerProvider(String provider){
        LocationProvider original=locations.getProvider(provider);boolean gps="gps".equals(provider);
        boolean network=original==null?!gps:original.requiresNetwork(),satellite=original==null?gps:original.requiresSatellite(),cell=original==null?!gps:original.requiresCell();
        int power=original==null?(gps?Criteria.POWER_HIGH:Criteria.POWER_LOW):original.getPowerRequirement();
        int accuracy=original==null?(gps?Criteria.ACCURACY_FINE:Criteria.ACCURACY_COARSE):original.getAccuracy();
        for(int attempt=0;attempt<2;attempt++){
            try{
                locations.addTestProvider(provider,network,satellite,cell,false,true,true,true,power,accuracy);
                if(!ownedProviders.contains(provider))ownedProviders.add(provider);
                locations.setTestProviderEnabled(provider,true);
                if(Build.VERSION.SDK_INT<29)locations.setTestProviderStatus(provider,LocationProvider.AVAILABLE,null,SystemClock.elapsedRealtime());
                providers.add(provider);return;
            }catch(Exception e){
                try{locations.removeTestProvider(provider);}catch(Exception ignored){}
                if(attempt==1)try{providerErrors.put(provider,message(e));}catch(Exception ignored){}
            }
        }
    }
    void notifyRunning(){
        NotificationManager nm=getSystemService(NotificationManager.class);nm.createNotificationChannel(new NotificationChannel("replay","跑步定位",NotificationManager.IMPORTANCE_LOW));
        PendingIntent open=PendingIntent.getActivity(this,0,new Intent(this,MobileActivity.class),PendingIntent.FLAG_IMMUTABLE);
        PendingIntent stop=PendingIntent.getService(this,1,new Intent(this,ReplayService.class).putExtra("action","stop"),PendingIntent.FLAG_IMMUTABLE|PendingIntent.FLAG_UPDATE_CURRENT);
        Notification n=new Notification.Builder(this,"replay").setSmallIcon(android.R.drawable.ic_menu_mylocation).setContentTitle("校园乐跑助手 · 跑步中")
            .setContentText("可切换到乐跑查看位置；点击结束跑步可停止定位更新").setContentIntent(open).setOngoing(true)
            .addAction(new Notification.Action.Builder(null,"结束跑步",stop).build()).build();
        startForeground(101,n);
    }
    void cleanup(){
        handler.removeCallbacks(tick);
        try{locations.removeUpdates(observer);locations.removeUpdates(fusedObserver);}catch(Exception e){cleanupError=message(e);}
        if(wake!=null&&wake.isHeld())wake.release();
        for(String provider:new ArrayList<>(ownedProviders)){try{locations.removeTestProvider(provider);}catch(IllegalArgumentException absent){}catch(Exception e){cleanupError=message(e);}}
        providers.clear();ownedProviders.clear();
    }
    void clearCheckpoint(){
        synchronized(checkpointLock){
            SharedPreferences prefs=getSharedPreferences("run_session",MODE_PRIVATE);
            if(prefs.contains("checkpoint")&&!prefs.edit().remove("checkpoint").commit())cleanupError="运行恢复点清除失败";
        }
    }
    void saveCheckpoint(boolean force) throws Exception {
        if(stopping||engine==null)return;
        if(!recoveryEnabled(this)){clearCheckpoint();return;}
        long now=SystemClock.elapsedRealtime();if(!force&&now-checkpointAt<2000)return;
        String saved=RunCheckpoint.capture(runConfig,engine,recoveredWall+(now-started)/1000.0,sent,restores,now).toString();
        synchronized(checkpointLock){
            if(stopping)return; // A stop must not be overwritten by an in-flight disk save.
            if(!getSharedPreferences("run_session",MODE_PRIVATE).edit().putString("checkpoint",saved).commit())throw new IllegalStateException("运行恢复点保存失败");
            checkpointAt=now;
        }
    }
    void stop(String next,String reason){stopping=true;state=next;error=reason;clearCheckpoint();cleanup();stopForeground(STOP_FOREGROUND_REMOVE);stopSelf();}
    public static JSONObject status() throws Exception {
        JSONObject result=new JSONObject(last.toString()).put("state",state).put("error",error).put("cleanupError",cleanupError);
        if(result.has("lastSentRealtime"))result.put("sendAge",Math.max(0,(SystemClock.elapsedRealtime()-result.getLong("lastSentRealtime"))/1000.0));
        return result;
    }
    public static void command(String action,JSONObject data) throws Exception {
        ReplayService s=instance;if(s==null||s.engine==null||!active())throw new IllegalStateException("当前没有正在进行的跑步");
        if(action.equals("stop")){s.stopping=true;s.clearCheckpoint();}
        CountDownLatch ready=new CountDownLatch(1);AtomicReference<Exception> failure=new AtomicReference<>();
        s.handler.post(()->{try{
            if(s.stopping&&!action.equals("stop"))throw new IllegalStateException("当前运行正在结束");
            if(action.equals("pause")){s.engine.paused=true;state="paused";}
            else if(action.equals("resume")){s.engine.paused=false;state="running";}
            else if(action.equals("tune")){s.engine.motion=RouteEngine.validateMotion(data,s.engine.motion.optDouble("speed"));}
            else if(action.equals("stop"))s.stop("idle","");
            else throw new IllegalArgumentException("操作无效");
            if(!action.equals("stop"))try{s.saveCheckpoint(true);}catch(Exception e){s.stop("error",message(e));throw e;}
        }catch(Exception e){failure.set(e);}finally{ready.countDown();}});
        if(!ready.await(5,TimeUnit.SECONDS))throw new IllegalStateException("跑步操作超时");if(failure.get()!=null)throw failure.get();
    }
    @Override public void onDestroy(){
        CountDownLatch cleaned=new CountDownLatch(1);
        handler.post(()->{try{if(!stopping)saveCheckpoint(true);}catch(Exception e){error=message(e);}finally{try{cleanup();}finally{cleaned.countDown();}}});
        try{if(!cleaned.await(3,TimeUnit.SECONDS))cleanupError="定位服务清理超时";}catch(InterruptedException e){Thread.currentThread().interrupt();}
        if(!stopping&&(state.equals("running")||state.equals("paused")||state.equals("starting"))){state="interrupted";error="服务已停止，等待系统尝试恢复；如未恢复请重新开始";}
        worker.quitSafely();if(instance==this)instance=null;super.onDestroy();
    }
    @Override public IBinder onBind(Intent i){return null;}
}
