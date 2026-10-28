package org.campusroute.mobile;

import org.json.JSONObject;

/** A recent checkpoint resumes from saved progress, never inventing missed fixes. */
public final class RunCheckpoint {
    public static final long MAX_AGE_MS=120_000;
    public final JSONObject config;
    public final RouteEngine engine;
    public final double wallElapsed;
    public final long sent;
    public final int restores;

    private RunCheckpoint(JSONObject config,RouteEngine engine,double wallElapsed,long sent,int restores){
        this.config=config;this.engine=engine;this.wallElapsed=wallElapsed;this.sent=sent;this.restores=restores;
    }
    public static JSONObject capture(JSONObject config,RouteEngine engine,double wallElapsed,long sent,int restores,long now) throws Exception {
        JSONObject current=new JSONObject(config.toString()).put("motion",new JSONObject(engine.motion.toString()));
        return new JSONObject().put("schema",1).put("config",current).put("distance",engine.distance)
            .put("elapsed",engine.elapsed).put("paused",engine.paused).put("wallElapsed",wallElapsed)
            .put("sent",sent).put("restores",restores).put("savedRealtime",now);
    }
    public static RunCheckpoint restore(JSONObject saved,long now) throws Exception {
        long savedAt=saved.getLong("savedRealtime");
        if(saved.getInt("schema")!=1||savedAt<0||now<savedAt||now-savedAt>MAX_AGE_MS)
            throw new IllegalStateException("运行恢复点已过期，请重新开始");
        JSONObject config=new JSONObject(saved.getJSONObject("config").toString());
        RouteEngine engine=new RouteEngine(config.getJSONObject("route"),config.optJSONObject("motion"));
        double distance=saved.getDouble("distance"),elapsed=saved.getDouble("elapsed"),wall=saved.getDouble("wallElapsed");
        long sent=saved.getLong("sent");int restores=saved.getInt("restores");
        if(!Double.isFinite(distance)||distance<0||distance>=engine.total||!Double.isFinite(elapsed)||elapsed<0
            ||!Double.isFinite(wall)||wall<0||wall<elapsed-.001||sent<0||restores<0||restores==Integer.MAX_VALUE)
            throw new IllegalStateException("运行恢复点无效或已完成，请重新开始");
        engine.distance=distance;engine.elapsed=elapsed;engine.paused=saved.getBoolean("paused");
        // Wall time includes the interruption, while route progress stays frozen.
        return new RunCheckpoint(config,engine,wall+(now-savedAt)/1000.0,sent,restores+1);
    }
}
