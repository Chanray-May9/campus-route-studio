package org.campusroute.bridge;

import android.app.AppOpsManager;
import android.content.Context;
import android.location.Criteria;
import android.location.Location;
import android.location.LocationManager;
import android.location.LocationProvider;
import android.os.Bundle;
import android.os.Looper;
import android.os.PowerManager;
import android.os.Process;
import android.os.SystemClock;
import java.io.*;
import java.lang.reflect.Method;
import java.nio.channels.FileLock;
import java.util.ArrayList;
import org.json.JSONObject;

/** Temporary ADB shell process. No APK, Activity, accessibility service or network listener. */
public final class Main {
    static final String PREFIX="CRS1 ",SHELL="com.android.shell";
    static final File LOCK=new File("/data/local/tmp/campus-route-direct.lock");
    static final File STATE=new File("/data/local/tmp/campus-route-direct.state");
    static final String[] PROVIDERS={"gps","network"};
    final ArrayList<String> owned=new ArrayList<>();
    final PrintWriter output=new PrintWriter(new OutputStreamWriter(System.out),true);
    Context context;LocationManager locations;AppOpsManager appOps;Method setMode;
    FileOutputStream lockStream;FileLock lock;PowerManager.WakeLock wake;
    int originalMode,mockOperation;boolean saved,closed;long lastUpdate,sent;
    JSONObject providerErrors=new JSONObject();String wakeError="";

    static Context shellContext() throws Exception {
        if(Looper.myLooper()==null)Looper.prepareMainLooper();
        Class<?> type=Class.forName("android.app.ActivityThread");
        Object thread=type.getMethod("systemMain").invoke(null);
        Context system=(Context)type.getMethod("getSystemContext").invoke(thread);
        Context shell=system.createPackageContext(SHELL,Context.CONTEXT_IGNORE_SECURITY);
        // New ContextImpl versions inherit the container's attribution in
        // createPackageContext(). Build an app context with the shell LoadedApk.
        if(!SHELL.equals(shell.getOpPackageName())){
            Class<?> impl=Class.forName("android.app.ContextImpl");
            java.lang.reflect.Field info=impl.getDeclaredField("mPackageInfo");info.setAccessible(true);
            Method create=impl.getDeclaredMethod("createAppContext",type,Class.forName("android.app.LoadedApk"));create.setAccessible(true);
            shell=(Context)create.invoke(null,thread,info.get(shell));
        }
        if(!SHELL.equals(shell.getOpPackageName()))throw new SecurityException("Shell attribution unavailable");
        return shell;
    }
    static String message(Throwable error){
        while(error.getCause()!=null)error=error.getCause();
        return error.getClass().getSimpleName()+": "+String.valueOf(error.getMessage());
    }
    void reply(long id,JSONObject value) throws Exception {value.put("id",id);output.println(PREFIX+value);}
    void mode(int value) throws Exception {setMode.invoke(appOps,mockOperation,Process.myUid(),SHELL,value);}
    void persist() throws Exception {
        byte[] bytes=new JSONObject().put("mode",originalMode).toString().getBytes("UTF-8");
        try(FileOutputStream stream=new FileOutputStream(STATE)){stream.write(bytes);stream.getFD().sync();}
        saved=true;
    }
    void removeProviders() throws Exception {
        Exception first=null;
        for(String provider:new ArrayList<>(owned)){
            try{locations.removeTestProvider(provider);}catch(IllegalArgumentException absent){}
            catch(Exception e){if(first==null)first=e;}
        }
        owned.clear();if(first!=null)throw first;
    }
    void setup(int baseline) throws Exception {
        lockStream=new FileOutputStream(LOCK,true);lock=lockStream.getChannel().tryLock();
        if(lock==null)throw new IllegalStateException("Another direct-location session is active");
        originalMode=baseline;
        if(STATE.isFile()){
            byte[] bytes=new byte[(int)Math.min(STATE.length(),4096)];
            try(FileInputStream in=new FileInputStream(STATE)){if(in.read(bytes)!=bytes.length)throw new IOException("Incomplete recovery record");}
            originalMode=new JSONObject(new String(bytes,"UTF-8")).getInt("mode");
            if(originalMode<0||originalMode>4)throw new IOException("Invalid recovery mode");
            saved=true;mode(AppOpsManager.MODE_ALLOWED);
            for(String provider:PROVIDERS)owned.add(provider);
            removeProviders();mode(originalMode);
            if(!STATE.delete())throw new IOException("Cannot remove recovered state record");saved=false;
        }
        persist(); // Record restoration before granting the temporary shell operation.
        mode(AppOpsManager.MODE_ALLOWED);
        if(appOps.checkOpNoThrow(AppOpsManager.OPSTR_MOCK_LOCATION,Process.myUid(),SHELL)!=AppOpsManager.MODE_ALLOWED)
            throw new SecurityException("Device denied shell mock-location operation");
        for(String provider:PROVIDERS){
            try{
                LocationProvider old=locations.getProvider(provider);boolean gps=provider.equals("gps");
                locations.addTestProvider(provider,old==null?!gps:old.requiresNetwork(),old==null?gps:old.requiresSatellite(),
                    old==null?!gps:old.requiresCell(),false,true,true,true,
                    old==null?(gps?Criteria.POWER_HIGH:Criteria.POWER_LOW):old.getPowerRequirement(),
                    old==null?(gps?Criteria.ACCURACY_FINE:Criteria.ACCURACY_COARSE):old.getAccuracy());
                owned.add(provider);locations.setTestProviderEnabled(provider,true);
            }catch(Exception e){providerErrors.put(provider,message(e));}
        }
        // Require GPS; a successful network-only setup is not a successful GPS connection.
        if(!owned.contains("gps")||providerErrors.has("gps"))throw new IllegalStateException("GPS channel unavailable: "+providerErrors);
        lastUpdate=SystemClock.elapsedRealtime();
        renewWake();
        Thread watchdog=new Thread(()->{
            try{
                while(true){Thread.sleep(1000);boolean expired;synchronized(this){
                    if(closed)return;
                    expired=SystemClock.elapsedRealtime()-lastUpdate>=10_000;
                }if(expired){cleanup();release();System.exit(0);}}
            }catch(InterruptedException ignored){}catch(Exception e){System.err.println(message(e));release();System.exit(1);}
        },"campus-direct-watchdog");
        watchdog.setDaemon(true);watchdog.start();
    }
    void renewWake(){
        try{
            if(wake==null){wake=context.getSystemService(PowerManager.class).newWakeLock(PowerManager.PARTIAL_WAKE_LOCK,"campusroute:Direct");wake.setReferenceCounted(false);}
            wake.acquire(15_000);
        }catch(Exception e){wakeError=message(e);}
    }
    static double number(JSONObject object,String key,double fallback,double low,double high) throws Exception {
        double value=object.optDouble(key,fallback);
        if(!Double.isFinite(value)||value<low||value>high)throw new IllegalArgumentException("Invalid "+key);
        return value;
    }
    synchronized JSONObject update(JSONObject point) throws Exception {
        if(closed)throw new IllegalStateException("Connection closed");
        double lat=number(point,"lat",Double.NaN,-90,90),lon=number(point,"lon",Double.NaN,-180,180);
        float speed=(float)number(point,"speed",0,0,150),bearing=(float)number(point,"bearing",0,0,360);
        float accuracy=(float)number(point,"accuracy",5,.1,10000);
        for(String provider:owned){
            Location location=new Location(provider);location.setLatitude(lat);location.setLongitude(lon);
            location.setAltitude(0);location.setAccuracy(accuracy);location.setSpeed(speed);location.setBearing(bearing%360);
            location.setTime(System.currentTimeMillis());location.setElapsedRealtimeNanos(SystemClock.elapsedRealtimeNanos());
            location.setSpeedAccuracyMetersPerSecond(.25f);location.setBearingAccuracyDegrees(3);location.setVerticalAccuracyMeters(5);
            if(provider.equals("gps")){Bundle quality=new Bundle();quality.putInt("satellites",12);location.setExtras(quality);}
            locations.setTestProviderLocation(provider,location);
        }
        lastUpdate=SystemClock.elapsedRealtime();renewWake();
        return new JSONObject().put("ok",true).put("sent",++sent);
    }
    synchronized void cleanup() throws Exception {
        if(closed)return;closed=true;Exception failure=null;
        try{if(wake!=null&&wake.isHeld())wake.release();}catch(Exception e){failure=e;}
        try{removeProviders();}catch(Exception e){failure=e;}
        if(saved){
            try{mode(originalMode);}catch(Exception e){failure=e;}
            if(failure==null&&!STATE.delete())failure=new IOException("Cannot delete restoration record");
        }
        if(failure!=null)throw failure;
    }
    void release(){
        try{if(lock!=null)lock.release();}catch(Exception ignored){}
        try{if(lockStream!=null)lockStream.close();}catch(Exception ignored){}
        String jar=System.getProperty("java.class.path","");
        if(jar.matches("/data/local/tmp/campus-route-[a-f0-9]{32}\\.jar"))new File(jar).delete();
    }
    public static void main(String[] args){
        Main session=new Main();long id=0;
        try{
            if(Process.myUid()!=2000)throw new SecurityException("Requires ordinary ADB shell UID 2000; no APK installation or root escalation is attempted");
            session.context=shellContext();session.locations=session.context.getSystemService(LocationManager.class);
            session.appOps=session.context.getSystemService(AppOpsManager.class);
            session.setMode=AppOpsManager.class.getMethod("setMode",int.class,int.class,String.class,int.class);
            session.mockOperation=(Integer)AppOpsManager.class.getMethod("strOpToOp",String.class).invoke(null,AppOpsManager.OPSTR_MOCK_LOCATION);
            if(args.length==1&&args[0].equals("probe")){
                session.reply(0,new JSONObject().put("ok",true).put("probe",true).put("sdk",android.os.Build.VERSION.SDK_INT)
                    .put("locationEnabled",android.os.Build.VERSION.SDK_INT<28||session.locations.isLocationEnabled()));return;
            }
            if(args.length!=1)throw new IllegalArgumentException("Missing original operation mode");
            if(android.os.Build.VERSION.SDK_INT>=28&&!session.locations.isLocationEnabled())throw new IllegalStateException("Enable the phone Location setting first");
            int baseline=Integer.parseInt(args[0]);if(baseline<0||baseline>4)throw new IllegalArgumentException("Invalid operation mode");
            session.setup(baseline);
            Runtime.getRuntime().addShutdownHook(new Thread(()->{try{session.cleanup();}catch(Exception e){System.err.println(message(e));}}));
            session.reply(0,new JSONObject().put("ok",true).put("ready",true).put("providers",new org.json.JSONArray(session.owned)).put("wakeError",session.wakeError));
            BufferedReader input=new BufferedReader(new InputStreamReader(System.in,"UTF-8"));String line;
            while((line=input.readLine())!=null){
                if(line.length()>8192)throw new IOException("Command too long");
                JSONObject request=new JSONObject(line);id=request.getLong("id");String action=request.getString("action");
                if(action.equals("stop")){session.cleanup();session.reply(id,new JSONObject().put("ok",true).put("closed",true));return;}
                if(!action.equals("update"))throw new IllegalArgumentException("Unknown command");
                session.reply(id,session.update(request.getJSONObject("point")));
            }
            session.cleanup();
        }catch(Throwable error){
            String cleanupError="";try{session.cleanup();}catch(Exception e){cleanupError=message(e);}
            try{session.reply(id,new JSONObject().put("ok",false).put("error",message(error)).put("closed",true).put("cleanupError",cleanupError));}catch(Exception ignored){}
        }finally{session.release();}
    }
}
