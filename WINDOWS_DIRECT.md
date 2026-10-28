# Windows 0.6.4：Android 免安装 APK 直连测试版

当前电脑安卓模式不再依赖“校园乐跑定位助手”。安装包不包含手机 APK，界面没有安装入口，后端也移除了 APK 安装接口。手机独立版仍为 0.6.3，是另一种使用方式。

## 怎么用

1. 安装本次 Windows 0.6.4 测试版，或解压本次免安装 ZIP。
2. 手机打开 USB 调试、授权此电脑，并打开系统定位。
3. 在电脑选择“Android（USB 直连，免安装 APK）”，选择设备，点击“检测安卓直连”。
4. 检测通过后，从电脑开始、暂停、继续或结束；手机不用安装本项目的 APK，也不用选择本项目手机应用为模拟位置应用。系统模拟位置标记仍然保留。
5. 基础检测通过仅表示临时进程可启动并访问所需入口；开始时还会验证模拟位置授权与 GPS 通道。开始后仍须核对手机地图和目标软件位置是否持续变化。

Android 8+ 是构建最低版本。厂商、系统版本、企业策略、ADB 权限与系统接口限制可能拒绝本方案；拒绝时显示错误，不自动安装 APK、启用无障碍或要求 Root。ADB 若运行在 root UID，而非普通 shell UID 2000，本版明确拒绝，不擅自改变 ADB 模式。

## 手机上实际运行什么

电脑通过 ADB 将一个 DEX JAR 传入 `/data/local/tmp`，启动临时 `app_process` 进程，并通过标准输入输出发送坐标。没有 APK 安装、应用图标、Activity、Android 应用前台服务或无障碍服务；运行期间手机仍有临时文件和临时进程。

临时进程以普通 ADB shell 身份调用系统 GPS/network 模拟位置接口，携带速度、方向、时间戳、精度与模拟 GPS 质量元数据，保留 Android mock 标记。不修改目标应用、不隐藏 mock 标记、不写入运动传感器。

电脑读取 shell 包原有模拟位置操作模式并传给进程；进程持有互斥锁，记录原模式后临时授权，结束时移除测试提供器并恢复原模式。UID 级别的 AppOps 覆盖不由电脑改写。

正常结束或输入流断开时尝试清理；10 秒无有效更新时，手机进程自身看门狗尝试清理退出。进程被强杀、手机断电或系统接口卡死时，不能保证清理已执行；保存的恢复记录供下次连接尝试恢复。清理失败会保留恢复记录并报错。临时 JAR 尝试删除；固定零字节互斥锁文件可保留，以免删除锁文件引入并发竞态。不会承诺手机完全不落盘。

本方案使用系统接口，部分入口依赖 Android 内部接口，不能仅凭 Java 编译通过宣称支持所有系统。

## 本次验证

- 60 项 Python 测试通过，其中 11 项验证真实桌面子进程/管道与模拟安卓协议端：开始、发送、结束、状态序号、权限拒绝、断连、参数校验和临时文件清理命令。模拟协议端不能验证 Android 权限与系统定位分发。
- HTTP 测试确认直连检测需要认证，旧 `/api/android/setup` 安装入口为 404。
- 临时 DEX JAR 使用 Android API 35、JDK 21、D8/min-api 26 编译通过。JAR 没有 Manifest 或 APK 安装结构，不需要 APK 签名。
- 已在 Android 15 / API 35 官方 AOSP ATD 模拟器以普通 shell UID 2000，运行实际冻结 Windows EXE，通过 29 项运行验收；原始记录另确认融合定位暂停、恢复、熄屏更新。持续更新、暂停继续、熄屏、权限恢复及手机自主超时清理通过。详见 [运行验收报告](DIRECT_RUNTIME_VALIDATION.md)。
- 使用独立普通应用作为定位接收测试夹具；电脑产品不安装、包含或依赖这个测试 APK。尚未验证各厂商实体手机、步道乐跑实际接收与里程记录，不能据此宣称广泛机型全部兼容。
- iOS 连接源码没有修改；本次没有真实 iPhone 回归结果。

## 构建

```powershell
python scripts/build_android_bridge.py --sdk PATH_TO_ANDROID_SDK
python -m unittest discover -s tests -v
python scripts/build_windows.py --sdk PATH_TO_ANDROID_SDK --iscc PATH_TO_ISCC --output dist/direct
```

## 实现依据

核对了 Android 官方源码：原生 `cmd location` 的位置设置入口提供位置、精度和时间参数，没有速度与方向参数，因此本版没有只替换为该命令而丢掉原有定位字段。

- [Android LocationShellCommand](https://android.googlesource.com/platform/frameworks/base/+/refs/heads/main/services/core/java/com/android/server/location/LocationShellCommand.java)
- [Android ContextImpl](https://android.googlesource.com/platform/frameworks/base/+/refs/heads/main/core/java/android/app/ContextImpl.java)
