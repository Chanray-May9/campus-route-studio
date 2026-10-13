"""Build and run replay integration test on a selected test Android device.
Prerequisites: install build/CampusRoute-Mobile.apk; allow location and select it
as mock-location app on the test device. Pass --serial to avoid another device.
"""
import argparse
from pathlib import Path
import subprocess
import tempfile
import zipfile
from build_android import ROOT, discover_sdk, jdk_tool, version, run

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--serial',help='ADB test device serial')
    parser.add_argument('--build-only',action='store_true')
    parser.add_argument('--sdk')
    args=parser.parse_args()
    if not args.build_only and not args.serial:parser.error('--serial is required when running the test')
    sdk=discover_sdk(args.sdk)
    platform=max((sdk/'platforms').glob('android-*'),key=version)/'android.jar'
    tools=max((sdk/'build-tools').iterdir(),key=version)
    java,javac=jdk_tool('java'),jdk_tool('javac')
    suffix='.exe' if java.suffix=='.exe' else ''
    key=ROOT/'build/android-helper-debug.keystore'
    if not key.exists():raise RuntimeError('Build mobile APK first with scripts/build_android.py')
    adb=str(sdk/'platform-tools'/('adb'+suffix))
    with tempfile.TemporaryDirectory(dir=ROOT/'build',prefix='replay-test-') as temp:
        tmp=Path(temp);classes=tmp/'classes';dex=tmp/'dex';classes.mkdir();dex.mkdir()
        run([javac,'-encoding','UTF-8','--release','8','-classpath',platform,'-d',classes,*sorted((ROOT/'tests/android').glob('*.java'))])
        run([java,'-cp',tools/'lib/d8.jar','com.android.tools.r8.D8','--min-api','26','--lib',platform,'--output',dex,*classes.rglob('*.class')])
        unsigned=tmp/'unsigned.apk'
        run([tools/('aapt2'+suffix),'link','-I',platform,'--manifest',ROOT/'tests/android/AndroidManifest.xml','-o',unsigned])
        with zipfile.ZipFile(unsigned,'a') as archive:archive.write(dex/'classes.dex','classes.dex')
        aligned=tmp/'aligned.apk';apk=tmp/'test.apk'
        run([tools/('zipalign'+suffix),'-f','4',unsigned,aligned])
        run([java,'-jar',tools/'lib/apksigner.jar','sign','--ks',key,'--ks-pass','pass:android','--out',apk,aligned])
        if args.build_only:
            import shutil
            shutil.copyfile(apk,ROOT/'build/replay-test.apk')
            print('Built instrumentation test APK (not executed)')
            return
        run([adb,'-s',args.serial,'install','-r',apk])
        try:
            command=[adb,'-s',args.serial,'shell','am','instrument','-w']
            command+=['org.campusroute.tests/org.campusroute.tests.ReplaySmoke']
            result=subprocess.run(command,capture_output=True,text=True,encoding='utf-8',timeout=90)
            print(result.stdout)
            (ROOT/'build/replay-test-result.txt').write_text(result.stdout,encoding='utf-8')
            if result.returncode or 'PASS:' not in result.stdout:raise RuntimeError('Android replay integration test failed: '+result.stderr)
        finally:run([adb,'-s',args.serial,'uninstall','org.campusroute.tests'])
if __name__=='__main__':main()
