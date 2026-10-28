package org.campusroute.tests;

import org.campusroute.mobile.RouteEngine;
import org.campusroute.mobile.RunCheckpoint;
import org.json.JSONObject;

/** Runnable JVM regression against the production checkpoint and route engine. */
public final class RunCheckpointTest {
    static int checks;
    static void check(boolean condition,String why){checks++;if(!condition)throw new AssertionError(why);}
    static void near(double actual,double expected,String why){check(Math.abs(actual-expected)<.00001,why+": "+actual+" != "+expected);}
    interface Task{void run() throws Exception;}
    static void rejects(Task task,String why) throws Exception {
        boolean rejected=false;try{task.run();}catch(Exception e){rejected=true;}check(rejected,why);
    }
    static JSONObject config() throws Exception {
        return new JSONObject("{\"route\":{\"points\":[{\"lat\":30,\"lon\":120},{\"lat\":30.01,\"lon\":120}],\"speed\":2.8,\"loops\":0}}");
    }
    static JSONObject clone(JSONObject value) throws Exception{return new JSONObject(value.toString());}
    public static void main(String[] args) throws Exception {
        JSONObject config=config();RouteEngine engine=new RouteEngine(config.getJSONObject("route"),null);
        engine.advance(10,Double.POSITIVE_INFINITY);
        JSONObject saved=RunCheckpoint.capture(config,engine,10,21,0,100_000);
        RunCheckpoint restored=RunCheckpoint.restore(saved,130_000);
        near(restored.engine.distance,28,"must not create distance for 30-second interruption");
        near(restored.engine.elapsed,10,"must not advance route clock during interruption");
        near(restored.wallElapsed,40,"wall clock must include interruption");
        check(restored.sent==21&&restored.restores==1,"counters must survive recovery");
        near(restored.engine.point().getDouble("lat"),engine.point().getDouble("lat"),"first restored fix must be saved point");
        restored.engine.advance(.5,Double.POSITIVE_INFINITY);near(restored.engine.distance,29.4,"continue from saved distance");
        engine.paused=true;JSONObject paused=RunCheckpoint.capture(config,engine,20,25,1,100_000);
        RunCheckpoint p=RunCheckpoint.restore(paused,101_000);p.engine.advance(100,Double.POSITIVE_INFINITY);
        near(p.engine.distance,28,"paused recovery must remain paused");check(p.restores==2,"multiple recoveries counted");
        engine.motion=RouteEngine.validateMotion(new JSONObject("{\"speed\":4}"),2.8);
        JSONObject tuned=RunCheckpoint.capture(config,engine,20,25,0,100_000);
        engine.motion.put("speed",9);config.getJSONObject("route").put("speed",8);
        RunCheckpoint tunedRestored=RunCheckpoint.restore(tuned,101_000);
        tunedRestored.engine.paused=false;near(tunedRestored.engine.speed(),4,"live tuning persisted without mutable alias");
        RunCheckpoint.restore(saved,100_000+RunCheckpoint.MAX_AGE_MS);checks++;
        rejects(()->RunCheckpoint.restore(saved,100_001+RunCheckpoint.MAX_AGE_MS),"expired run must not restart");
        rejects(()->RunCheckpoint.restore(saved,99_999),"backward clock must not restart");
        JSONObject corrupt=clone(saved).put("distance",-1);rejects(()->RunCheckpoint.restore(corrupt,101_000),"negative progress rejected");
        JSONObject badTime=clone(saved).put("elapsed",99);rejects(()->RunCheckpoint.restore(badTime,101_000),"route time exceeding wall time rejected");
        JSONObject unknown=clone(saved).put("schema",2);rejects(()->RunCheckpoint.restore(unknown,101_000),"unknown schema rejected");
        JSONObject once=config();once.getJSONObject("route").put("loops",1);
        RouteEngine completed=new RouteEngine(once.getJSONObject("route"),null);completed.advance(10000,Double.POSITIVE_INFINITY);
        JSONObject end=RunCheckpoint.capture(once,completed,10000,30,0,100_000);
        rejects(()->RunCheckpoint.restore(end,101_000),"completed run must not restart");
        System.out.println("PASS: "+checks+" checkpoint assertions; frozen interruption progress, live tuning, paused recovery, age/corruption/completion rejection.");
    }
}
