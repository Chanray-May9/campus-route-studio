package org.campusroute.mobile;

import android.content.Context;
import android.content.SharedPreferences;
import java.nio.charset.StandardCharsets;
import org.json.JSONArray;
import org.json.JSONObject;

public final class AppStore {
    final Context context;
    final SharedPreferences prefs;
    public final JSONObject config;
    public AppStore(Context c) throws Exception {
        context=c.getApplicationContext();prefs=context.getSharedPreferences("campus_route",Context.MODE_PRIVATE);
        java.io.InputStream input=context.getAssets().open("config.json");
        java.io.ByteArrayOutputStream output=new java.io.ByteArrayOutputStream();byte[] buffer=new byte[4096];int n;
        while((n=input.read(buffer))!=-1)output.write(buffer,0,n);input.close();
        config=new JSONObject(new String(output.toByteArray(),StandardCharsets.UTF_8));
    }
    public JSONArray library() throws Exception {return new JSONArray(prefs.getString("library","[]"));}
    public JSONObject save(JSONObject data) throws Exception {
        String name=data.optString("name").trim();if(name.isEmpty()||name.length()>80)throw new IllegalArgumentException("轨迹名称需要 1–80 个字符");
        new RouteEngine(data.getJSONObject("route"),data.optJSONObject("motion"));
        JSONArray list=library();String id=data.optString("id");boolean updated=false;
        if(id.isEmpty())id=java.util.UUID.randomUUID().toString();
        JSONObject entry=new JSONObject(data.toString()).put("id",id).put("updated",System.currentTimeMillis());
        for(int i=0;i<list.length();i++)if(id.equals(list.getJSONObject(i).optString("id"))){list.put(i,entry);updated=true;break;}
        if(!updated){if(list.length()>=100)throw new IllegalArgumentException("最多保存 100 条轨迹");list.put(entry);}
        if(!prefs.edit().putString("library",list.toString()).commit())throw new IllegalStateException("保存失败");
        return entry;
    }
    public void delete(String id) throws Exception {
        JSONArray previous=library(),next=new JSONArray();
        for(int i=0;i<previous.length();i++)if(!id.equals(previous.getJSONObject(i).optString("id")))next.put(previous.get(i));
        if(!prefs.edit().putString("library",next.toString()).commit())throw new IllegalStateException("删除失败");
    }
}
