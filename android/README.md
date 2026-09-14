# Android USB helper

`org.campusroute.helper` supports Android 8 / API 26 and newer. It uses official
GPS and network test providers. Coordinates retain Android's mock marker. It does
not replace accelerometer, gyroscope, or step-counter data.

Build from the repository root with `python scripts/build_android.py`. Install an
Android SDK with platform API 35+ and build-tools 35+, and a JDK 17+. The script
uses only Python's standard library and SDK tools; Gradle is not needed. The
development APK is written to `build/campus-route-helper.apk`. Signing keys are
created locally in ignored `build/` and must never be committed or published.

## Device setup

1. Enable USB debugging and accept this computer's authorization on the phone.
2. Install the APK, open Route Studio Helper, and grant location permission.
3. Enable the phone's Location setting. In Developer options, select Route Studio
   Helper as the mock-location app. The desktop does not change app-ops settings.
4. When starting from the background, Android may require the location permission
   to be set to “Allow all the time” in app settings. Background foreground-service
   restrictions also apply. If rejected, keep the helper visible and start it
   manually, then send desktop coordinates within 10 seconds.

## Shell protocol

The exported `.CommandReceiver` requires `android.permission.DUMP`, which is held
by ADB shell and system actors, but not ordinary third-party apps. The service is
not exported. Commands must use explicit component names and string extras:

```text
adb -s SERIAL shell am broadcast -n org.campusroute.helper/.CommandReceiver --es action start
adb -s SERIAL shell am broadcast -n org.campusroute.helper/.CommandReceiver --es action update --es lat 39.9 --es lon 116.4 --es speed 2.5 --es bearing 90 --es accuracy 3
adb -s SERIAL shell am broadcast -n org.campusroute.helper/.CommandReceiver --es action status
adb -s SERIAL shell am broadcast -n org.campusroute.helper/.CommandReceiver --es action stop
```

`am broadcast` sends an ordered broadcast. The receiver sets result code `0` for
success or `1` for failure, with JSON result data such as
`{"ok":true,"running":true}` or
`{"ok":false,"running":false,"error":"Replay is not running; send start first"}`.
`start` waits up to five seconds for the foreground service to initialize both
providers; success means `update` can be sent immediately. `status` is read-only
and does not reset the watchdog. `stop` is also usable after reopening a helper
whose previous process was killed.

`lat`/`lon` are required; `speed` defaults to 0 m/s, `bearing` to 0 degrees, and
`accuracy` to 3 metres. Inputs must be finite. Ranges: latitude −90…90, longitude
−180…180, speed 0…150 m/s, bearing 0…360 (360 becomes 0), accuracy 0.1…10000 m.
Each update supplies wall-clock and monotonic timestamps and writes the same
sample to both GPS and network test providers.

## Cleanup and limits

`stop`, normal service destruction, and removing the helper from recent tasks
remove both test providers. A watchdog removes them after 10 seconds without a
valid coordinate update. This handles USB disconnection and a desktop crash
while the phone helper is alive; pausing a desktop route for longer than ten
seconds therefore needs a fresh `start` when resuming. A bounded partial wake
lock keeps that watchdog awake while replaying with the screen off.

Android does not guarantee cleanup callbacks after force-stop, process death,
or power loss. In that case reopen this helper and use its Stop button, deselect
it as the mock-location app, or restart the phone. No compatibility or acceptance
by another app is guaranteed. The helper is built and signature-verified by the
build script; physical-device behavior still requires testing on the target OS.

Official references: [LocationManager](https://developer.android.com/reference/android/location/LocationManager),
[developer options](https://developer.android.com/studio/debug/dev-options),
[foreground service types](https://developer.android.com/develop/background-work/services/fgs/service-types),
[background start restrictions](https://developer.android.com/develop/background-work/services/fgs/restrictions-bg-start).
