package org.campusroute.mobile;

import org.json.JSONArray;
import org.json.JSONObject;
import java.util.ArrayList;

/** Distance-based synthetic route replay, independent of Activity/WebView lifecycle. */
public final class RouteEngine {
    public static final double R = 6371008.8;
    public final ArrayList<double[]> points = new ArrayList<>();
    public final ArrayList<Double> cumulative = new ArrayList<>();
    public final double lap;
    public final int loops;
    public final double total;
    public double distance, elapsed;
    public JSONObject motion;
    public boolean paused;

    public static double num(JSONObject obj, String key, double fallback, double min, double max) throws Exception {
        Object raw = obj.opt(key);
        if (raw instanceof Boolean) throw new IllegalArgumentException(key + " 必须为数字");
        double v = raw == null ? fallback : Double.parseDouble(raw.toString());
        if (!Double.isFinite(v) || v < min || v > max) throw new IllegalArgumentException(key + " 超出范围");
        return v;
    }
    public static JSONObject validateMotion(JSONObject m, double speed) throws Exception {
        if (m == null) m = new JSONObject();
        JSONObject out = new JSONObject();
        String mode = m.optString("mode", "fixed");
        if (!mode.equals("fixed") && !mode.equals("smooth") && !mode.equals("alternating")) throw new IllegalArgumentException("速度模式无效");
        out.put("mode", mode); out.put("speed", num(m,"speed",speed,.2,20));
        double low = num(m,"low",speed,.2,20);
        out.put("low",low); out.put("high",num(m,"high",speed,low,20));
        out.put("period",num(m,"period",10,2,120)); out.put("sway",num(m,"sway",0,0,3));
        out.put("swayPeriod",num(m,"swayPeriod",4,2,30));
        return out;
    }
    public RouteEngine(JSONObject route, JSONObject profile) throws Exception {
        JSONArray array = route.getJSONArray("points");
        if (array.length()<2 || array.length()>10000) throw new IllegalArgumentException("需要 2–10000 个路线点");
        for (int i=0;i<array.length();i++) {
            JSONObject p=array.getJSONObject(i);
            double[] v={num(p,"lat",Double.NaN,-85,85),num(p,"lon",Double.NaN,-180,180)};
            if (points.isEmpty() || metres(points.get(points.size()-1),v)>.01) points.add(v);
        }
        if(points.size()<2) throw new IllegalArgumentException("至少两个不同的路线点");
        double count=num(route,"loops",1,0,10000);
        if(count != Math.floor(count)) throw new IllegalArgumentException("圈数必须为整数");
        loops=(int)count;
        if(loops!=1 && metres(points.get(0),points.get(points.size()-1))>.01) points.add(points.get(0).clone());
        cumulative.add(0.0);
        for(int i=1;i<points.size();i++) {
            double length=metres(points.get(i-1),points.get(i));
            if(length>1000000) throw new IllegalArgumentException("相邻点超过 1000 公里，请检查坐标");
            cumulative.add(cumulative.get(i-1)+length);
        }
        lap=cumulative.get(cumulative.size()-1);
        if(lap<1) throw new IllegalArgumentException("路线至少 1 米");
        total=loops==0 ? Double.POSITIVE_INFINITY : lap*loops;
        motion=validateMotion(profile,num(route,"speed",2.5,.2,20));
    }
    public static double metres(double[] a,double[] b) {
        double p1=Math.toRadians(a[0]),p2=Math.toRadians(b[0]);
        double x=Math.sin((p2-p1)/2),y=Math.sin(Math.toRadians(b[1]-a[1])/2);
        return 2*R*Math.asin(Math.sqrt(Math.min(1,x*x+Math.cos(p1)*Math.cos(p2)*y*y)));
    }
    public static double bearing(double[] a,double[] b) {
        double p1=Math.toRadians(a[0]),p2=Math.toRadians(b[0]),d=Math.toRadians(b[1]-a[1]);
        return (Math.toDegrees(Math.atan2(Math.sin(d)*Math.cos(p2),Math.cos(p1)*Math.sin(p2)-Math.sin(p1)*Math.cos(p2)*Math.cos(d)))+360)%360;
    }
    public double integral(double t) {
        String mode=motion.optString("mode"); double lo=motion.optDouble("low"),hi=motion.optDouble("high"),period=motion.optDouble("period"),mean=(lo+hi)/2;
        if(mode.equals("fixed")) return motion.optDouble("speed")*t;
        if(mode.equals("smooth")) return mean*t-(hi-lo)*period/(4*Math.PI)*Math.sin(2*Math.PI*t/period);
        double cycles=Math.floor(t/period),rest=t-cycles*period;
        return cycles*mean*period+Math.min(rest,period/2)*lo+Math.max(0,rest-period/2)*hi;
    }
    public double speed() {
        if(paused || distance>=total) return 0;
        String mode=motion.optString("mode");
        double low=motion.optDouble("low"),high=motion.optDouble("high"),period=motion.optDouble("period");
        if(mode.equals("fixed")) return motion.optDouble("speed");
        if(mode.equals("alternating")) return elapsed%period<period/2 ? low:high;
        return (low+high)/2-(high-low)/2*Math.cos(2*Math.PI*elapsed/period);
    }
    public double advance(double dt,double allowance) {
        if(paused) return 0;
        double start=elapsed,end=start+Math.max(0,dt),maximum=Math.min(allowance,total-distance);
        double change=integral(end)-integral(start);
        if(change>maximum) {
            double low=start,high=end;
            for(int i=0;i<40;i++){double mid=(low+high)/2;if(integral(mid)-integral(start)<maximum)low=mid;else high=mid;}
            end=high;change=maximum;
        }
        elapsed=end;distance+=change;return change;
    }
    public JSONObject point() throws Exception {
        double local=distance>=total ? lap : distance%lap;
        int i=0;while(i<cumulative.size()-2 && cumulative.get(i+1)<=local)i++;
        double[] a=points.get(i),b=points.get(i+1);
        double fraction=(local-cumulative.get(i))/(cumulative.get(i+1)-cumulative.get(i));
        double angle=metres(a,b)/R,u=Math.sin((1-fraction)*angle)/Math.sin(angle),v=Math.sin(fraction*angle)/Math.sin(angle);
        double p1=Math.toRadians(a[0]),p2=Math.toRadians(b[0]),l1=Math.toRadians(a[1]),l2=Math.toRadians(b[1]);
        double x=u*Math.cos(p1)*Math.cos(l1)+v*Math.cos(p2)*Math.cos(l2),y=u*Math.cos(p1)*Math.sin(l1)+v*Math.cos(p2)*Math.sin(l2),z=u*Math.sin(p1)+v*Math.sin(p2);
        double lat=Math.toDegrees(Math.atan2(z,Math.hypot(x,y))),lon=Math.toDegrees(Math.atan2(y,x)),heading=bearing(a,b);
        double sway=motion.optDouble("sway")*Math.sin(2*Math.PI*elapsed/motion.optDouble("swayPeriod"))*Math.min(1,Math.min(distance/5,(total-distance)/5));
        lat+=Math.toDegrees(sway*Math.cos(Math.toRadians(heading+90))/R);
        lon+=Math.toDegrees(sway*Math.sin(Math.toRadians(heading+90))/(R*Math.cos(Math.toRadians(lat))));
        return new JSONObject().put("lat",lat).put("lon",(lon+540)%360-180).put("speed",speed()).put("bearing",heading);
    }
}
