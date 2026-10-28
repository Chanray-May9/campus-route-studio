"""Build a temporary app_process DEX JAR; no APK, manifest or signing key."""
import argparse
from pathlib import Path
import tempfile
import zipfile
from build_android import ROOT, discover_sdk, jdk_tool, version, run


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk')
    args=parser.parse_args()
    sdk=discover_sdk(args.sdk)
    platform=max((sdk/'platforms').glob('android-*'),key=version)/'android.jar'
    tools=max((sdk/'build-tools').iterdir(),key=version)
    output=ROOT/'build';output.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output,prefix='direct-bridge-') as temp:
        tmp=Path(temp);classes=tmp/'classes';dex=tmp/'dex';classes.mkdir();dex.mkdir()
        run([jdk_tool('javac'),'-encoding','UTF-8','--release','8','-classpath',platform,'-d',classes,*sorted((ROOT/'bridge/src').rglob('*.java'))])
        run([jdk_tool('java'),'-cp',tools/'lib/d8.jar','com.android.tools.r8.D8','--min-api','26','--lib',platform,'--output',dex,*classes.rglob('*.class')])
        with zipfile.ZipFile(output/'campus-route-direct.jar','w',zipfile.ZIP_DEFLATED) as archive:
            for path in dex.glob('*.dex'):archive.write(path,path.name)
    print('Built build/campus-route-direct.jar (no APK installation)')


if __name__=='__main__':main()
