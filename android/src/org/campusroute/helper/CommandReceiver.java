package org.campusroute.helper;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.ResultReceiver;
import java.util.concurrent.atomic.AtomicBoolean;
import org.json.JSONObject;

/** Explicit shell-only command endpoint; the manifest requires DUMP permission. */
public final class CommandReceiver extends BroadcastReceiver {
    static String result(boolean ok, String error) {
        try {
            JSONObject value = new JSONObject();
            value.put("ok", ok);
            value.put("running", MockLocationService.isRunning());
            if (error != null) value.put("error", error);
            return value.toString();
        } catch (Exception impossible) {
            return "{\"ok\":false,\"error\":\"Result serialization failed\"}";
        }
    }

    static String message(Exception error) {
        String detail = error.getMessage();
        return error.getClass().getSimpleName() + (detail == null ? "" : ": " + detail);
    }

    @Override public void onReceive(Context context, Intent intent) {
        String action = intent.getStringExtra("action");
        if ("start".equals(action)) {
            start(context);
            return;
        }
        try {
            if ("update".equals(action)) {
                MockLocationService.update(intent);
            } else if ("stop".equals(action)) {
                MockLocationService.stopSession(context);
            } else if (!"status".equals(action)) {
                throw new IllegalArgumentException("action must be start, update, stop, or status");
            }
            setResultCode(0);
            setResultData(result(true, null));
        } catch (Exception error) {
            setResultCode(1);
            setResultData(result(false, message(error)));
        }
    }

    private void start(Context context) {
        PendingResult pending = goAsync();
        Handler handler = new Handler(Looper.getMainLooper());
        AtomicBoolean finished = new AtomicBoolean(false);
        Runnable timeout = () -> {
            if (!finished.compareAndSet(false, true)) return;
            try { MockLocationService.stopSession(context); } catch (Exception ignored) { }
            pending.setResultCode(1);
            pending.setResultData(result(false, "Service startup timed out; open the helper and start it manually."));
            pending.finish();
        };
        ResultReceiver reply = new ResultReceiver(handler) {
            @Override protected void onReceiveResult(int code, Bundle data) {
                if (!finished.compareAndSet(false, true)) return;
                handler.removeCallbacks(timeout);
                pending.setResultCode(code);
                pending.setResultData(data.getString("result"));
                pending.finish();
            }
        };
        handler.postDelayed(timeout, 5000);
        try {
            context.startForegroundService(new Intent(context, MockLocationService.class)
                .putExtra("reply", reply));
        } catch (Exception error) {
            handler.removeCallbacks(timeout);
            if (finished.compareAndSet(false, true)) {
                pending.setResultCode(1);
                pending.setResultData(result(false, message(error) + "; open the helper and start it manually."));
                pending.finish();
            }
        }
    }
}
