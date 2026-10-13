"""Read-only MuMu discovery and documented CLI reply handling."""
from __future__ import annotations
import json
import os
from pathlib import Path
import shutil
from .adapters import command, DeviceError

def manager_candidates():
    candidates=[]
    found=shutil.which('MuMuManager.exe')
    if found:candidates.append(Path(found))
    if os.name=='nt':
        import winreg
        for hive in (winreg.HKEY_CURRENT_USER,winreg.HKEY_LOCAL_MACHINE):
            for view in (winreg.KEY_WOW64_32KEY,winreg.KEY_WOW64_64KEY):
                try:
                    with winreg.OpenKey(hive,r'Software\Microsoft\Windows\CurrentVersion\Uninstall',0,winreg.KEY_READ|view) as parent:
                        for index in range(winreg.QueryInfoKey(parent)[0]):
                            try:
                                with winreg.OpenKey(parent,winreg.EnumKey(parent,index)) as entry:
                                    name=winreg.QueryValueEx(entry,'DisplayName')[0]
                                    if 'mumu' not in str(name).lower():continue
                                    install=Path(winreg.QueryValueEx(entry,'InstallLocation')[0])
                                    candidates.extend(install/sub for sub in ('nx_main/MuMuManager.exe','shell/MuMuManager.exe','MuMuManager.exe'))
                            except OSError:continue
                except OSError:continue
    for variable in ('ProgramFiles','ProgramFiles(x86)'):
        if os.environ.get(variable):
            base=Path(os.environ[variable])
            candidates.extend(base/sub for sub in ('Netease/MuMu/nx_main/MuMuManager.exe','Netease/MuMuPlayer/nx_main/MuMuManager.exe','Netease/MuMuPlayer-12.0/shell/MuMuManager.exe'))
    return list(dict.fromkeys(p.resolve() for p in candidates if p.is_file()))

def check_reply(output):
    try:data=json.loads(output)
    except (ValueError,TypeError):
        if any(word in output.lower() for word in ('error','failed','失败','错误')):raise DeviceError(output[-800:])
        return None
    if isinstance(data,dict):
        for key in ('errcode','error_code'):
            if key in data and data[key] not in (0,'0',None):raise DeviceError(str(data.get('errmsg') or data.get('error') or output)[-800:])
    return data

def discover_mumu():
    result={'managers':[],'errors':[]}
    for manager in manager_candidates():
        try:
            data=check_reply(command([manager,'info','-v','all']))
            if not isinstance(data,dict):raise DeviceError('MuMu 未返回实例列表')
            instances=[]
            for key,info in data.items():
                if not isinstance(info,dict) or not str(key).isdigit():continue
                index=int(key)
                if index>999:continue
                instances.append({'index':index,'name':str(info.get('name') or ('MuMu '+key)), 'running':info.get('is_android_started') is True})
            result['managers'].append({'path':str(manager),'instances':sorted(instances,key=lambda i:i['index'])})
        except (RuntimeError,ValueError) as e:result['errors'].append(str(e))
    return result
