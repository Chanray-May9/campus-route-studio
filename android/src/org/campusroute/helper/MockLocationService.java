package org.campusroute.helper;

import android.Manifest;
import android.app.AppOpsManager;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.location.Criteria;
import android.location.Location;
import android.location.LocationManager;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.os.PowerManager;
import android.os.Process;
import android.os.ResultReceiver;
import android.os.SystemClock;

/** Official mock providers only. This service does not modify sensor data. */
public final class MockLocationService extends Service {
    private static final String CHANNEL = "route_replay";
    private static final int NOTIFICATION = 101;
    public static final long WATCHDOG_MS = 10_000;
    private static final String[] PROVIDERS = {LocationManager.GPS_PROVIDER, LocationManager.NETWORK_PROVIDER};
    private static MockLocationService instance;
    private final Handler handler = new Handler(Looper.getMainLooper());
    private LocationManager locations;
    private PowerManager.WakeLock wakeLock;
    private long lastUpdate;
    private boolean active;
    private final Runnable watchdog = new Runnable() {
        @Override public void run() {
            if (!active) return;
            if (SystemClock.elapsedRealtime() - lastUpdate >= WATCHDOG_MS) {
                try { stopSession(MockLocationService.this); } catch (Exception ignored) { }
            } else {
                handler.postDelayed(this, 1000);
            }
        }
    };

    public static boolean isRunning() { return instance != null && instance.active; }

    @Override public void onCreate() {
        super.onCreate();
        instance = this;
        locations = getSystemService(LocationManager.class);
    }

    @Override public int onStartCommand(Intent intent, int flags, int startId) {
        ResultReceiver reply = intent == null ? null : intent.getParcelableExtra("reply");
        String error = null;
        try {
            verifySetup();
            showNotification();
            if (!active) {
                for (String provider : PROVIDERS) {
                    locations.addTestProvider(provider, false, false, false, false,
                        true, true, true, Criteria.POWER_LOW, Criteria.ACCURACY_FINE);
                    locations.setTestProviderEnabled(provider, true);
                }
                active = true;
            }
            lastUpdate = SystemClock.elapsedRealtime();
            renewWakeLock();
            handler.removeCallbacks(watchdog);
            handler.postDelayed(watchdog, 1000);
        } catch (Exception exception) {
            error = CommandReceiver.message(exception)
                + "; select this mock-location app, grant location permission, and open the helper before starting.";
            try { cleanup(); } catch (Exception ignored) { }
            stopForeground(STOP_FOREGROUND_REMOVE);
            stopSelf();
        }
        if (reply != null) {
            Bundle data = new Bundle();
            data.putString("result", CommandReceiver.result(error == null, error));
            reply.send(error == null ? 0 : 1, data);
        }
        return START_NOT_STICKY;
    }

    private void verifySetup() {
        if (checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) != PackageManager.PERMISSION_GRANTED
            && checkSelfPermission(Manifest.permission.ACCESS_COARSE_LOCATION) != PackageManager.PERMISSION_GRANTED) {
            throw new SecurityException("Location permission is required for the foreground service");
        }
        AppOpsManager appOps = getSystemService(AppOpsManager.class);
        if (appOps.checkOpNoThrow(AppOpsManager.OPSTR_MOCK_LOCATION, Process.myUid(), getPackageName())
            != AppOpsManager.MODE_ALLOWED) {
            throw new SecurityException("Select Route Studio Helper as the mock-location app in Developer options");
        }
        if (Build.VERSION.SDK_INT >= 28 && !locations.isLocationEnabled()) {
            throw new IllegalStateException("Enable the device Location setting");
        }
    }

    private void showNotification() {
        NotificationManager manager = getSystemService(NotificationManager.class);
        manager.createNotificationChannel(new NotificationChannel(CHANNEL, "位置回放", NotificationManager.IMPORTANCE_LOW));
        PendingIntent open = PendingIntent.getActivity(this, 0, new Intent(this, MainActivity.class), PendingIntent.FLAG_IMMUTABLE);
        PendingIntent stop = PendingIntent.getBroadcast(this, 1,
            new Intent(this, CommandReceiver.class).putExtra("action", "stop"),
            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        Notification notification = new Notification.Builder(this, CHANNEL)
            .setSmallIcon(android.R.drawable.ic_menu_mylocation)
            .setContentTitle("Route Studio · 模拟位置回放")
            .setContentText("10 秒未收到坐标将自动停止；点击停止可恢复位置提供器。")
            .setContentIntent(open).setOngoing(true)
            .addAction(new Notification.Action.Builder(null, "停止", stop).build())
            .build();
        startForeground(NOTIFICATION, notification);
    }

    private void renewWakeLock() {
        if (wakeLock == null) {
            wakeLock = getSystemService(PowerManager.class).newWakeLock(PowerManager.PARTIAL_WAKE_LOCK,
                "campusroute:ReplayWatchdog");
            wakeLock.setReferenceCounted(false);
        }
        // A bounded lock keeps the watchdog responsive while the screen is off.
        wakeLock.acquire(WATCHDOG_MS + 5000);
    }

    private static double number(Intent intent, String name, Double fallback, double min, double max) {
        String raw = intent.getStringExtra(name);
        if (raw == null && fallback != null) return fallback;
        if (raw == null) throw new IllegalArgumentException("Missing " + name);
        double value;
        try { value = Double.parseDouble(raw); }
        catch (NumberFormatException error) { throw new IllegalArgumentException(name + " must be numeric"); }
        if (!Double.isFinite(value) || value < min || value > max) {
            throw new IllegalArgumentException(name + " is out of range");
        }
        return value;
    }

    public static void update(Intent intent) {
        MockLocationService service = instance;
        if (service == null || !service.active) throw new IllegalStateException("Replay is not running; send start first");
        double latitude = number(intent, "lat", null, -90, 90);
        double longitude = number(intent, "lon", null, -180, 180);
        float speed = (float) number(intent, "speed", 0.0, 0, 150);
        float bearing = (float) (number(intent, "bearing", 0.0, 0, 360) % 360);
        float accuracy = (float) number(intent, "accuracy", 3.0, 0.1, 10000);
        long now = System.currentTimeMillis();
        long elapsedNanos = SystemClock.elapsedRealtimeNanos();
        try {
            for (String provider : PROVIDERS) {
                Location location = new Location(provider);
                location.setLatitude(latitude);
                location.setLongitude(longitude);
                location.setAccuracy(accuracy);
                location.setSpeed(speed);
                location.setBearing(bearing);
                location.setTime(now);
                location.setElapsedRealtimeNanos(elapsedNanos);
                service.locations.setTestProviderLocation(provider, location);
            }
            service.lastUpdate = SystemClock.elapsedRealtime();
            service.renewWakeLock();
        } catch (Exception error) {
            try { stopSession(service); } catch (Exception ignored) { }
            throw error;
        }
    }

    private void cleanup() {
        active = false;
        handler.removeCallbacks(watchdog);
        if (wakeLock != null && wakeLock.isHeld()) wakeLock.release();
        removeProviders(locations);
    }

    private static void removeProviders(LocationManager manager) {
        RuntimeException first = null;
        for (String provider : PROVIDERS) {
            try { manager.removeTestProvider(provider); }
            catch (IllegalArgumentException absent) { /* Provider absent on an older Android release. */ }
            catch (RuntimeException error) { if (first == null) first = error; }
        }
        if (first != null) throw first;
    }

    public static void stopSession(Context context) {
        MockLocationService service = instance;
        try {
            if (service != null) service.cleanup();
            else removeProviders(context.getSystemService(LocationManager.class));
        } finally {
            if (service != null) service.stopForeground(STOP_FOREGROUND_REMOVE);
            context.stopService(new Intent(context, MockLocationService.class));
        }
    }

    @Override public void onTaskRemoved(Intent rootIntent) {
        try { stopSession(this); } catch (Exception ignored) { }
        super.onTaskRemoved(rootIntent);
    }

    @Override public void onDestroy() {
        try { cleanup(); } catch (Exception ignored) { }
        if (instance == this) instance = null;
        super.onDestroy();
    }

    @Override public IBinder onBind(Intent intent) { return null; }
}
