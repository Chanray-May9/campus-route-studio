"""Exercise a frozen Windows build and independent receiver on an explicitly selected Android device.

Changes mock GPS/network coordinates on that test device, including a screen-off
phase. No APK is installed. --observer is a test-only DEX JAR built from
bridge/src and tests/bridge/LocationObserver.java, not the product transport JAR.
"""
import argparse
import ctypes
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import time
import urllib.request
from urllib.parse import urlsplit, parse_qs
import uuid


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('serial','adb','exe','observer','output'):
        parser.add_argument('--'+name,required=True)
    parser.add_argument('--state-dir',required=True,help='Isolated Windows runtime data directory outside protected Documents')
    args=parser.parse_args();out=Path(args.output).resolve();out.mkdir(parents=True,exist_ok=True)
    for name in ('NtSuspendProcess','NtResumeProcess'):
        call=getattr(ctypes.windll.ntdll,name);call.argtypes=[ctypes.c_void_p];call.restype=ctypes.c_long
    report={'serial':args.serial,'checks':[],'version':None,'status':'running'};events=[]
    app=receiver=None;suspended=False;remote=None;receiver_out=receiver_err=None
    def adb(*parts):
        r=subprocess.run([args.adb,'-s',args.serial,*parts],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=20,creationflags=subprocess.CREATE_NO_WINDOW)
        if r.returncode:raise RuntimeError(r.stdout+r.stderr)
        return r.stdout.strip()
    def check(value,name):
        if not value:raise AssertionError(name)
        report['checks'].append(name);print('PASS:',name,flush=True)
    def mode(text):
        match=re.search(r'^\s*MOCK_LOCATION:\s*(allow|ignore|deny|default|foreground)\b',text,re.M)
        if match:return match[1]
        if 'No operations' in text:return 'default'
        raise RuntimeError('Unrecognized AppOps output: '+text)
    def operation():return mode(adb('shell','appops','get','--user','current','com.android.shell','android:mock_location'))
    def no_override():return not re.search(r'^\s+(gps|network) provider \[mock\]:',adb('shell','dumpsys','location'),re.M)
    def sample():
        if not (out/'receiver.jsonl').exists():return {}
        lines=(out/'receiver.jsonl').read_text(encoding='utf-8',errors='replace').splitlines()
        for line in reversed(lines):
            if line.startswith('OBS1 '):
                try:data=json.loads(line[5:])
                except ValueError:continue
                if data.get('event')=='sample':return data
        return {}
    def metres(a,b):
        lat1,lat2=map(math.radians,(a['lat'],b['lat']));dlat=lat2-lat1;dlon=math.radians(b['lon']-a['lon'])
        return 12742017.6*math.asin(min(1,math.sqrt(math.sin(dlat/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2)))
    api=None
    try:
        check(adb('get-state')=='device','explicit test device authorized')
        report['device']={key:adb('shell','getprop',prop) for key,prop in [('release','ro.build.version.release'),('sdk','ro.build.version.sdk'),('fingerprint','ro.build.fingerprint')]}
        report['uid']=adb('shell','id');check('uid=2000(shell)' in report['uid'],'ordinary non-root ADB shell identity')
        before_packages=set(adb('shell','pm','list','packages').splitlines());before_mode=operation();report['originalMockMode']=before_mode
        remote='/data/local/tmp/campus-route-observer-'+uuid.uuid4().hex+'.jar'
        adb('push',args.observer,remote);adb('shell','chmod','444',remote)
        receiver_out=(out/'receiver.jsonl').open('w',encoding='utf-8');receiver_err=(out/'receiver.stderr.txt').open('w',encoding='utf-8')
        receiver=subprocess.Popen([args.adb,'-s',args.serial,'shell','-T','app_process','-Djava.class.path='+remote,'/data/local/tmp','org.campusroute.bridge.LocationObserver','240'],stdout=receiver_out,stderr=receiver_err,creationflags=subprocess.CREATE_NO_WINDOW)
        user=Path(args.state_dir).absolute();user.mkdir(parents=True,exist_ok=True)
        app=subprocess.Popen([args.exe,'--no-browser','--port','0'],env=dict(os.environ,LOCALAPPDATA=str(user)),creationflags=subprocess.CREATE_NO_WINDOW)
        session=user/'CampusRouteStudio/desktop-session.json';deadline=time.monotonic()+20
        while not session.exists():
            if app.poll() is not None:raise RuntimeError('Frozen Windows app exited during startup')
            if time.monotonic()>deadline:raise TimeoutError('Windows startup')
            time.sleep(.2)
        url=json.loads(session.read_text())['url'];parsed=urlsplit(url);origin='http://'+parsed.netloc;cookie='campus_route_session='+parse_qs(parsed.query)['token'][0]
        def api(path,data=None):
            req=urllib.request.Request(origin+path,data=None if data is None else json.dumps(data).encode(),headers={'Cookie':cookie,'Origin':origin,'Content-Type':'application/json'})
            with urllib.request.urlopen(req,timeout=30) as response:return json.load(response)
        def state():return api('/api/status')['run']
        def wait(expected):
            limit=time.monotonic()+20
            while True:
                status=state()
                if status['state']==expected:return status
                if status['state']=='error':raise RuntimeError(json.dumps(status,ensure_ascii=False))
                if time.monotonic()>limit:raise TimeoutError(expected+': '+json.dumps(status))
                time.sleep(.2)
        def phase(name,seconds):
            for _ in range(seconds):
                current=state();received=sample();events.append({'phase':name,'pcTime':time.time(),'run':current,'receiver':received})
                if current['state']=='error':raise RuntimeError(json.dumps(current,ensure_ascii=False))
                time.sleep(1)
            return sample()
        report['version']=api('/api/status')['info']['version'];report['exeSha256']=hashlib.sha256(Path(args.exe).read_bytes()).hexdigest()
        check(api('/api/android/probe',{'serial':args.serial}).get('probe'),'frozen build probes real Android without APK')
        check(operation()==before_mode,'probe does not change mock operation mode')
        config={'mode':'android','serial':args.serial,'route':{'points':[{'lat':30,'lon':120},{'lat':30.01,'lon':120}],'speed':2.8,'loops':1},'motion':{'mode':'fixed','speed':2.8}}
        api('/api/start',config);wait('running');phase('warmup',4)
        first=sample();check(bool(first.get('gps')),'independent Android receiver reads GPS')
        moving=phase('moving',25)
        check(moving.get('callbacks',0)>first.get('callbacks',0)+20,'independent location callbacks continue beyond initial fix')
        check(metres(first['gps'],moving['gps'])>50,'GPS moves over 50 metres during sustained run')
        check(moving['gps']['mock'] and moving['gps']['satellites']==12,'framework preserves mock marker and GPS quality metadata')
        check(moving['gps']['elapsedNanos']>first['gps']['elapsedNanos'],'framework GPS timestamps keep advancing')
        check(abs(moving['gps']['speed']-2.8)<.001,'framework receives speed field')
        check(bool(moving.get('fused')) and metres(moving['gps'],moving['fused'])<5,'native fused provider stays synchronized with moving GPS')
        check(moving['fused']['elapsedNanos']>first['fused']['elapsedNanos'],'native fused timestamps advance beyond the cached initial fix')
        api('/api/control',{'action':'pause'});wait('paused');phase('pause-settle',2);paused=sample();still=phase('paused',10)
        check(metres(paused['gps'],still['gps'])<.2 and abs(still['gps']['speed'])<.001,'pause freezes received coordinates with zero speed')
        check(metres(paused['fused'],still['fused'])<.2 and abs(still['fused']['speed'])<.001,'native fused remains stationary during pause')
        check(still['gps']['elapsedNanos']>paused['gps']['elapsedNanos'],'paused heartbeats update timestamps')
        api('/api/control',{'action':'resume'});wait('running');resumed=phase('resumed',15)
        check(metres(still['gps'],resumed['gps'])>25,'resume advances received GPS again')
        check(metres(still['fused'],resumed['fused'])>25,'resume advances native fused again')
        adb('shell','input','keyevent','KEYCODE_SLEEP');power=adb('shell','dumpsys','power');report['screenOffPower']=next((line.strip() for line in power.splitlines() if 'mWakefulness=' in line),'')
        check('mWakefulness=Asleep' in power,'Android display actually enters asleep state')
        asleep_start=sample();asleep_end=phase('screen-off',20)
        check(metres(asleep_start['gps'],asleep_end['gps'])>40,'GPS continues moving with screen off')
        check(metres(asleep_start['fused'],asleep_end['fused'])>40,'native fused continues moving with screen off')
        adb('shell','input','keyevent','KEYCODE_WAKEUP')
        api('/api/control',{'action':'stop'});stopped=wait('idle')
        check(not stopped.get('cleanupError'),'Windows acknowledges normal cleanup')
        check(no_override(),'normal stop removes both mock provider overrides')
        check(operation()==before_mode,'normal stop restores original mock operation mode')
        check('campus-route-direct.state' not in adb('shell','ls','/data/local/tmp'),'normal stop clears recovery record')
        api('/api/start',config);wait('running');phase('watchdog-warmup',3)
        check(operation()=='allow','second session temporarily enables shell mock operation')
        status=ctypes.windll.ntdll.NtSuspendProcess(int(app._handle))
        check(status==0,'suspend only the isolated test Windows process to stop heartbeats without EOF')
        suspended=True
        time.sleep(14)
        check(no_override(),'phone watchdog independently removes providers after 10 seconds without updates')
        check(operation()==before_mode,'phone watchdog independently restores mock operation mode')
        check('campus-route-direct.state' not in adb('shell','ls','/data/local/tmp'),'watchdog clears recovery record')
        ctypes.windll.ntdll.NtResumeProcess(int(app._handle));suspended=False
        deadline=time.monotonic()+12
        while state()['state']!='error' and time.monotonic()<deadline:time.sleep(.5)
        check(state()['state']=='error','Windows detects that watchdog closed the Android connection')
        check(set(adb('shell','pm','list','packages').splitlines())==before_packages,'no APK/package installed during complete test')
        jars=adb('shell','ls','/data/local/tmp')
        check(not re.search(r'^campus-route-[a-f0-9]{32}\.jar$',jars,re.M),'product temporary DEX JARs removed')
        report['status']='passed'
    except Exception as error:
        report['status']='failed';report['error']=str(error);raise
    finally:
        if suspended and app is not None:ctypes.windll.ntdll.NtResumeProcess(int(app._handle))
        try:
            if api is not None and app is not None and app.poll() is None:api('/api/quit',{})
        except Exception:pass
        if app is not None:
            try:app.wait(timeout=15)
            except subprocess.TimeoutExpired:app.terminate();app.wait(timeout=5)
        if receiver is not None:
            try:
                for line in (out/'receiver.jsonl').read_text(encoding='utf-8',errors='replace').splitlines():
                    if not line.startswith('OBS1 '):continue
                    record=json.loads(line[5:])
                    if record.get('event')=='started':
                        pid=int(record['pid'])
                        if pid>0 and 'org.campusroute.bridge.LocationObserver' in adb('shell','ps','-p',str(pid),'-o','ARGS'):
                            adb('shell','kill','-15',str(pid))
                        break
            except Exception:pass
            try:receiver.wait(timeout=5)
            except subprocess.TimeoutExpired:receiver.terminate();receiver.wait(timeout=5)
        if receiver_out is not None:receiver_out.close()
        if receiver_err is not None:receiver_err.close()
        if remote:
            try:adb('shell','rm','-f',remote)
            except Exception:pass
        try:adb('shell','input','keyevent','KEYCODE_WAKEUP')
        except Exception:pass
        (out/'events.json').write_text(json.dumps(events,ensure_ascii=False,indent=2),encoding='utf-8')
        (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print('REPORT',json.dumps(report,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
