package org.campusroute.mobile;

import java.net.URL;
import java.net.HttpURLConnection;
import java.nio.charset.StandardCharsets;
import org.json.JSONObject;

public final class ApiClient {
    final AppStore store;
    public ApiClient(AppStore s){store=s;}
    public JSONObject request(String path) throws Exception {
        String base=store.config.optString("backend");
        if(base.isEmpty())throw new IllegalStateException("尚未配置轨迹服务器，本地编辑和回放仍可免费使用");
        URL url=new URL(base+path);if(!url.getProtocol().equals("https"))throw new SecurityException("后端必须使用 HTTPS");
        HttpURLConnection connection=(HttpURLConnection)url.openConnection();connection.setConnectTimeout(10000);connection.setReadTimeout(15000);connection.setInstanceFollowRedirects(false);
        try {
            connection.setRequestProperty("Content-Type","application/json");
            int status=connection.getResponseCode();java.io.InputStream input=status<400?connection.getInputStream():connection.getErrorStream();
            if(input==null)throw new IllegalStateException("服务器未返回内容");
            java.io.ByteArrayOutputStream out=new java.io.ByteArrayOutputStream();byte[] buf=new byte[4096];int n;while((n=input.read(buf))!=-1){out.write(buf,0,n);if(out.size()>2000000)throw new IllegalStateException("响应过大");}input.close();
            JSONObject result=new JSONObject(new String(out.toByteArray(),StandardCharsets.UTF_8));
            if(status>=400)throw new IllegalStateException(result.optString("detail",result.optString("error","服务器请求失败")));
            return result;
        }finally{connection.disconnect();}
    }
}
