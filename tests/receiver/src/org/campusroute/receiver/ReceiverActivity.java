package org.campusroute.receiver;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;
import android.os.Handler;
import android.view.Gravity;
import android.widget.TextView;
import org.json.JSONObject;

/** Test consumer only: no permission or API for producing mock locations. */
public final class ReceiverActivity extends Activity {
    final Handler handler=new Handler();TextView display;
    final Runnable refresh=new Runnable(){public void run(){
        try{
            JSONObject data=new JSONObject(ReceiverService.last);StringBuilder text=new StringBuilder("安卓独立接收验证\n\n仅接收系统坐标，不发送位置\n\n");
            text.append("回调次数：").append(data.optInt("callbacks")).append("\n\n");
            for(String channel:new String[]{"gps","network","fused"}){
                JSONObject p=data.optJSONObject(channel);text.append(channel.toUpperCase()).append("\n");
                if(p==null)text.append("等待系统位置\n\n");
                else text.append(String.format(java.util.Locale.ROOT,"%.7f, %.7f\n速度 %.2f m/s · mock=%s\n\n",p.getDouble("lat"),p.getDouble("lon"),p.getDouble("speed"),p.getBoolean("mock")));
            }
            if(data.has("error"))text.append(data.optString("error"));display.setText(text);
        }catch(Exception e){display.setText(e.toString());}
        handler.postDelayed(this,500);
    }};
    @Override public void onCreate(Bundle state){
        super.onCreate(state);display=new TextView(this);display.setTextSize(18);display.setPadding(28,50,28,28);display.setGravity(Gravity.TOP);setContentView(display);
        startForegroundService(new Intent(this,ReceiverService.class));handler.post(refresh);
    }
    @Override public void onDestroy(){handler.removeCallbacks(refresh);super.onDestroy();}
}
