package org.campusroute.helper;

import android.Manifest;
import android.app.Activity;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.ResultReceiver;
import android.provider.Settings;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import java.util.ArrayList;

public final class MainActivity extends Activity {
    private TextView status;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        int pad = (int) (24 * getResources().getDisplayMetrics().density);
        LinearLayout column = new LinearLayout(this);
        column.setOrientation(LinearLayout.VERTICAL);
        column.setPadding(pad, pad * 2, pad, pad * 2);
        column.setBackgroundColor(Color.rgb(246, 248, 246));
        TextView title = text("Route Studio Helper", 26);
        title.setTextColor(Color.rgb(21, 80, 61));
        column.addView(title);
        column.addView(text("Android 位置回放连接器", 18));
        column.addView(text("1. 开启手机定位，授予本工具定位权限。\n\n"
            + "2. 开发者选项 → 选择模拟位置信息应用 → Route Studio Helper。\n\n"
            + "3. USB 调试连接电脑，并在手机确认电脑授权。\n\n"
            + "4. 回到电脑选择设备并开始回放。如系统限制后台启动，先在此点击启动，再于 10 秒内开始电脑回放。", 16));
        column.addView(button("授予定位和通知权限", view -> requestAccess()));
        column.addView(button("打开开发者选项", view -> openSettings(Settings.ACTION_APPLICATION_DEVELOPMENT_SETTINGS)));
        column.addView(button("应用权限设置", view -> startActivity(new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
            Uri.parse("package:" + getPackageName())))));
        column.addView(text("后台启动可能需要在应用权限中允许“始终访问位置”。也可保持此页面可见并手动启动。本工具不会自动修改模拟位置应用授权。", 14));
        column.addView(button("启动位置回放服务", view -> startReplay()));
        column.addView(button("停止并移除模拟位置", view -> {
            try { MockLocationService.stopSession(this); status.setText("已停止，并移除测试位置提供器。"); }
            catch (Exception error) { status.setText(CommandReceiver.message(error)); }
        }));
        status = text("等待电脑连接", 15);
        column.addView(status);
        column.addView(text("坐标带有 Android 官方 mock 标记；本工具不修改加速度、陀螺仪或计步数据。\n\n"
            + "服务在 10 秒没有收到有效坐标后自动停止。电脑断开或程序退出时，只要手机服务仍正常运行，看门狗会移除提供器。"
            + "手机进程被强制结束时，系统可能不执行清理；请重新打开本工具点击停止，或在开发者选项取消模拟位置应用。", 14));
        ScrollView scroll = new ScrollView(this);
        scroll.setFillViewport(true);
        scroll.addView(column);
        setContentView(scroll);
    }

    @Override public void onResume() {
        super.onResume();
        if (status != null) status.setText(MockLocationService.isRunning() ? "回放服务运行中" : "服务未运行");
    }

    private TextView text(String value, int size) {
        TextView view = new TextView(this);
        view.setText(value);
        view.setTextSize(size);
        view.setPadding(0, 12, 0, 12);
        return view;
    }

    private Button button(String label, View.OnClickListener listener) {
        Button button = new Button(this);
        button.setText(label);
        button.setAllCaps(false);
        button.setOnClickListener(listener);
        return button;
    }

    private void requestAccess() {
        ArrayList<String> permissions = new ArrayList<>();
        if (checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) != PackageManager.PERMISSION_GRANTED) {
            permissions.add(Manifest.permission.ACCESS_COARSE_LOCATION);
            permissions.add(Manifest.permission.ACCESS_FINE_LOCATION);
        }
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)
            != PackageManager.PERMISSION_GRANTED) permissions.add(Manifest.permission.POST_NOTIFICATIONS);
        if (!permissions.isEmpty()) requestPermissions(permissions.toArray(new String[0]), 1);
        else status.setText("定位权限已授予；后台启动权限可在应用权限设置中检查。");
    }

    private void openSettings(String action) {
        try { startActivity(new Intent(action)); }
        catch (Exception error) { status.setText("请先在系统设置中启用开发者选项。"); }
    }

    private void startReplay() {
        try {
            ResultReceiver reply = new ResultReceiver(new Handler(Looper.getMainLooper())) {
                @Override protected void onReceiveResult(int code, Bundle data) {
                    status.setText(code == 0 ? "服务已启动；请在 10 秒内从电脑发送坐标。" : data.getString("result"));
                }
            };
            startForegroundService(new Intent(this, MockLocationService.class).putExtra("reply", reply));
        } catch (Exception error) { status.setText(CommandReceiver.message(error)); }
    }
}
