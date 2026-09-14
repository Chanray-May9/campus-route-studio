# 校园路线工作台 / Campus Route Studio

免费开源的路线编辑与开发者定位回放工具，采用 GPL-3.0-or-later。安卓独立 App 无需付费、手机号、账号或授权服务器，也没有试用里程限制；定位回放在手机前台服务中完成。Windows 桌面版支持 Android/MuMu 与 USB 连接 iPhone。

## 下载与安装

安卓 APK 位于 GitHub Releases。Android 8 或以上：安装后开启开发者选项，将“校园路线”选为模拟位置应用，授予精确定位权限。规划路线并核对场地要求后开始；启动后可切换其他 App，通知栏可停止。更新已有安装包可保留本地轨迹，建议先导出 JSON 备份。

支持地图点击和拖动、学校附近定位、GPX/GeoJSON/JSON、轨迹保存、固定或变化速度、左右轨迹摆动、指定圈数与无限循环。地图底图和云端轨迹同步需要网络，本地编辑和回放无需账号或云端授权。

普通安卓没有通用加速度传感器注入；iPhone 当前仍需电脑连接。目标软件可能识别模拟定位，本项目不保证其认可跑步记录。学校要求只能在操场跑时，需核对实际场地和路径并遵守规定。

## 构建安卓 App

安装 Python 3.11+、JDK 17+、Android SDK（platforms 和 build-tools 35+），设置 JAVA_HOME 与 ANDROID_SDK_ROOT：

```powershell
python scripts/build_android.py --source-dir mobile --apk-name CampusRoute-Mobile.apk
```

开发签名保存在忽略的 build/ 中，不上传。正式维护者应保留稳定签名并在升级时提高版本号。mobile/assets/config.json 只包含可选的公开轨迹服务器 URL，不含管理员密码；清空 backend 可关闭远程轨迹同步。

## 可选 Cloudflare 后端

cloudflare/ 提供 Workers + D1 轨迹管理服务。GET /api/routes 公开读，/api/admin/routes 写入需要管理员密码；没有账号、收款或额度接口。部署步骤见 [Cloudflare 说明](cloudflare/README.md)。公开源码的 wrangler 配置是模板，需填自己的账户和数据库 ID。管理员密码仅存 Cloudflare Secrets。

## Windows 桌面版

## 启动

安装 Python 3.11+，下载源码并在项目目录运行：

```powershell
python -m route_studio
```

程序会打开浏览器界面。默认模式只预览路线，不向设备发送数据。关闭标签页不会退出程序，请点击“停止并退出”或按 Ctrl+C。

Windows 发行包中的 `start.cmd` 使用 Python 3.12 启动，并在首次启动时检查、安装 iOS 依赖。电脑须安装 Python 3.12；不同 Python 环境不共享依赖。手动启动时，iOS 模式还需安装可选依赖：

```powershell
python -m pip install -r requirements-ios.txt
```

## 设备支持范围

| 模式 | 定位 | 运动传感器 | 设置与停止行为 |
| --- | --- | --- | --- |
| 预览 | 本地地图 | 无 | 不操作设备 |
| Android USB / MuMu ADB | GPS 和 network 测试提供器，含速度和方向 | 不支持真机通用注入 | Android 8+；安装助手，授权定位，选择模拟位置应用；正常停止移除测试提供器 |
| MuMu 直接定位 | 官方 MuMuManager CLI | 本项目不将重力角度称为加速度 | MuMu 4.0.0.3179+；停止后保留最后位置，需在 MuMu 面板手动恢复 |
| Android 官方 Emulator | 控制台 GPS | 可选确定性加速度测试波形 | 仅官方 AVD；停止恢复原加速度，GPS 保留最后位置 |
| iOS USB <17 | Apple 开发者定位服务 | 不支持 | 已信任电脑，开发者服务/DDI 可用；停止尝试清除模拟定位 |
| iOS USB 17.0–17.3.1 | DVT 定位，经外部隧道 | 不支持 | Windows 需要预先运行管理员 tunneld，并安装相应驱动 |
| iOS USB 17.4+ | DVT 定位，经 userspace 隧道 | 不支持 | 已信任电脑，开发者模式/DDI 可用；定位只包含经纬度 |

版本表描述代码采用的接口路径，**不是已完成的实机兼容认证**。新 iOS 版本可能改变开发者接口。iOS 依赖固定为 `pymobiledevice3==10.7.4`，避免异步 API 自动升级失配。

### Android 与 MuMu

安装 [Android SDK Platform-Tools](https://developer.android.com/tools/releases/platform-tools)，把 adb 加入 PATH 或设置 ANDROID_HOME。手机开启 USB 调试并信任电脑，然后刷新设备列表。点击安装助手，按手机提示授予权限并选择“校园路线助手”为模拟位置应用。厂商限制后台启动时，先在助手界面手动启动服务。

MuMu 可使用 ADB 模式，地址与端口以实际实例设置为准，不固定为 7555。新版本也可以选择安装目录里的 `MuMuManager.exe` 和实例编号走直接定位。

助手收到更新时重置 10 秒看门狗，电脑进程崩溃或 USB 断开但助手仍存活时会尝试清理。手机强制杀死助手、系统崩溃或连接丢失可能阻止清理；不能保证所有异常都恢复定位。助手有停止入口。

### iOS

Windows 安装 Apple 驱动/Apple Mobile Device Service，连接后解锁并手动信任电脑。iOS 16+ 开启开发者模式，并按上游指南挂载适配 DDI。程序不自动配对、开启开发者模式或提权。

早期 iOS 17 在管理员终端预先运行：

```powershell
python -m pymobiledevice3 remote tunneld
```

清理失败时界面保留错误。重新连接原手机后，可按版本手动清除定位（把 UDID 替换为实际设备标识）：

```powershell
# iOS 17.4+
python -m pymobiledevice3 developer dvt simulate-location clear --udid UDID --userspace
# iOS 17.0–17.3.1，已有 tunneld
python -m pymobiledevice3 developer dvt simulate-location clear --tunnel UDID
# iOS <17
python -m pymobiledevice3 developer simulate-location clear --udid UDID
```

## 路线与本地数据

循环方式支持“指定圈数”和“无限循环”。指定圈数 1–10000，有限任务预计时长仍限制为 24 小时；无限模式没有圈数上限，自动闭合路线并持续回放直到手动停止。状态栏显示累计距离、已完成圈数及当前圈进度，轨迹库会保存无限循环设置。

“我的轨迹库”支持命名保存多条轨迹（最多 100 条）、载入、更新所选及删除。路线点、基础速度、多圈设置和变速/摆动参数一起保存。数据位于 Windows `%LOCALAPPDATA%\CampusRouteStudio\routes.sqlite3`，不依赖浏览器缓存或端口，重启程序后仍可读取。删除条目不清空当前编辑路线。GPX/GeoJSON 导出仍可用于文件备份；轨迹数据库可在退出程序后复制备份。

回放参数支持固定、平滑变速和突然快慢交替；设置最低/最高速度及完整周期（每半周期切换一次快慢）。左右摆幅 0–3 米、周期 2–30 秒，0 表示关闭。回放中修改“实时基础速度”和运动参数，再点“应用到当前回放”即可连续调节。暂停保持位置，变速时预计时长仅为参考。摆动是合成路线偏移，不是实际传感器数据；速度字段是沿路线速度，不含摆动产生的横向分量。

使用 WGS84 坐标。其他坐标系文件需先转换。路线按距离和单调时钟插值；重复次数大于 1 时自动连接终点至起点，避免跨圈跳点。GPX 多段轨迹需先拆分。导入不采纳历史时间戳，回放速度由界面设置。

路线可保存在浏览器本地存储。在线底图来自 OpenStreetMap，瓦片请求会向底图服务器暴露所查看区域；没有联网也能通过坐标编辑、导入和回放。后端只监听 127.0.0.1，使用启动会话 cookie 并限制请求来源。

## 开发与验证

```powershell
python -B -m unittest discover -s tests -v
# Android SDK API 35+、build-tools 35+ 和 JDK 17+
python scripts/build_android.py
```

构建脚本生成本地开发签名 APK 和私钥。私钥位于忽略的 build/，不应上传。Windows 文件夹保护阻止构建时，可使用 `--build-dir` 指定临时构建目录，不需要关闭系统防护。

测试覆盖路线距离插值、跨经度边界、多圈闭合、文件格式及错误处理，回放状态/心跳/清理，以及 iOS 模拟接口的连接与恢复。尚未进行真实手机或步道乐跑有效记录测试。

## 接口依据与许可

- [MuMu 官方命令文档](https://mumu.163.com/help/20240726/35047_1170006.html)
- [Android LocationManager](https://developer.android.com/reference/android/location/LocationManager)
- [Android Emulator 控制台](https://developer.android.com/studio/run/emulator-console)
- [pymobiledevice3 iOS 隧道指南](https://doronz88.github.io/pymobiledevice3/guides/ios17-tunnels/)
- [pymobiledevice3 定位与 DDI 指南](https://doronz88.github.io/pymobiledevice3/guides/cli-recipes/)
- [Apple 软件模拟定位标记](https://developer.apple.com/documentation/corelocation/cllocationsourceinformation/issimulatedbysoftware)

本项目采用 GPL-3.0-or-later。Leaflet 使用 BSD-2-Clause，许可随 vendor 文件提供。pymobiledevice3 为 GPL-3.0-or-later。
