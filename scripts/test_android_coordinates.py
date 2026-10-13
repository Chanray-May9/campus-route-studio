"""Verify MuMu CLI conversion against fresh Android GPS fixes at five landmarks.

Prerequisites: build/replay-test.apk (--build-only test_android_replay.py), selected
device and mobile APK installed; no running route. Does not open or record a run
in any third-party app. Coordinates are temporarily set on this test emulator.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import threading
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from route_studio.adapters import MuMuAdapter,adb_path,command
from route_studio.coordinates import wgs_to_mumu


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--serial',required=True)
    parser.add_argument('--manager',required=True)
    parser.add_argument('--instance',type=int,required=True)
    args=parser.parse_args()
    adb=adb_path();adapter=MuMuAdapter(args.manager,args.instance);adapter.open()
    command([adb,'-s',args.serial,'install','-r',ROOT/'build/replay-test.apk'])
    results=[]
    try:
        for name,lat,lon in [('校园起点',29.51264659,106.69253011),('校园南弯',29.51145258,106.69364529),('杭州',30.2741,120.1551),('北京',39.915,116.404),('上海',31.2304,121.4737)]:
            adapter.send({'lat':lat,'lon':lon})
            # Keep refreshing the same point, like a paused run, so fixes stay fresh.
            done=threading.Event();send_errors=[]
            def refresh():
                try:
                    while not done.wait(.5):adapter.send({'lat':lat,'lon':lon})
                except Exception as error:send_errors.append(error)
            sender=threading.Thread(target=refresh);sender.start()
            try:
                result=command([adb,'-s',args.serial,'shell','am','instrument','-w','-e','lat',str(lat),'-e','lon',str(lon),'org.campusroute.tests/org.campusroute.tests.CoordinateSmoke'],timeout=20)
            finally:done.set();sender.join(15)
            if send_errors:raise send_errors[0]
            line=next((s for s in result.splitlines() if s.startswith('INSTRUMENTATION_RESULT: report=')),None)
            if not line:raise RuntimeError(result)
            payload=line.split('=',1)[1]
            if not payload.startswith('{'):raise RuntimeError(payload)
            record=json.loads(payload);record['name']=name;record['commandInput']=wgs_to_mumu(lat,lon);results.append(record)
            print(name,'max error',round(record['maxErrorMetres'],4),'metres',flush=True)
        (ROOT/'build/coordinate-test-result.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),'utf-8')
        if not all(r['ok'] for r in results):raise RuntimeError('Coordinate accuracy test failed; see build/coordinate-test-result.json')
    finally:
        adapter.send({'lat':29.51264659,'lon':106.69253011})
        command([adb,'-s',args.serial,'uninstall','org.campusroute.tests'])


if __name__=='__main__':main()
