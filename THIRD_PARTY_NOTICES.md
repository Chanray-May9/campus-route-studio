# Third-party software

Campus Route Studio is licensed under GPL-3.0-or-later. Corresponding source is
distributed as `CampusRoute-Source.zip` and at
https://github.com/Chanray-May9/campus-route-studio (the matching release tag).

Windows packages contain the Python runtime (PSF License), PyInstaller runtime
(GPL with the bootloader distribution exception), pymobiledevice3 (GPL-3.0),
and their dependencies. Original license files and distribution metadata are
included in `_internal` where supplied by those distributions.

Android Platform-Tools are from the Android SDK/AOSP distribution. Their
complete third-party notices are retained at `_internal/platform-tools/NOTICE.txt`.
Source: https://android.googlesource.com/platform/packages/modules/adb/ .

Both apps contain Leaflet (BSD-2-Clause), with its license retained in
`web/vendor/LEAFLET-LICENSE.txt` or `assets/vendor/LEAFLET-LICENSE.txt`.
Map imagery and labels are provided by AMap; tile requests require an Internet
connection and the map displays the provider attribution. MuMu is a separate
user-installed product; no MuMu binary is redistributed by this project.
