package org.campusroute.tests;

import android.app.Instrumentation;
import android.app.UiAutomation;
import android.accessibilityservice.AccessibilityServiceInfo;
import android.os.Bundle;
import android.view.accessibility.AccessibilityNodeInfo;
import org.json.JSONObject;

/** Read only selected free-run metrics without waiting for an animated map to idle. */
public final class WindowProbe extends Instrumentation {
    @Override public void onCreate(Bundle args){super.onCreate(args);start();}
    void read(AccessibilityNodeInfo node,JSONObject fields) throws Exception {
        if(node==null)return;
        String id=node.getViewIdResourceName();
        if(id!=null&&id.startsWith("com.lptiyu.tanke:id/")){
            String name=id.substring(id.lastIndexOf('/')+1);
            if(name.equals("tv_distance_value")||name.equals("tv_gps_strength")||name.equals("chronometer")||name.equals("tv_start_pause_continue_run"))
                fields.put(name,node.getText()==null?"":node.getText().toString());
        }
        for(int i=0;i<node.getChildCount();i++){
            AccessibilityNodeInfo child=node.getChild(i);
            try{read(child,fields);}finally{if(child!=null)child.recycle();}
        }
    }
    @Override public void onStart(){
        Bundle result=new Bundle();int code=-1;
        try{
            UiAutomation automation=getUiAutomation(UiAutomation.FLAG_DONT_SUPPRESS_ACCESSIBILITY_SERVICES);
            AccessibilityServiceInfo info=automation.getServiceInfo();
            info.flags|=AccessibilityServiceInfo.FLAG_REPORT_VIEW_IDS;
            automation.setServiceInfo(info);
            android.os.SystemClock.sleep(200);
            AccessibilityNodeInfo root=automation.getRootInActiveWindow();
            JSONObject fields=new JSONObject();
            try{read(root,fields);}finally{if(root!=null)root.recycle();}
            result.putString("report",fields.toString());
        }catch(Exception e){code=0;result.putString("report","ERROR: "+e.toString());}
        finish(code,result);
    }
}
