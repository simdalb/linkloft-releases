"""Verify an official download on a fresh disposable GitHub-hosted emulator."""
import argparse
import hashlib
import json
import os
import re
import subprocess
import time
from pathlib import Path
from zipfile import ZipFile

SIGNER = "52d04f39b93e676d09ed5e616ba223c7eb504d82fb77b9010af62833afc16560"
PACKAGE = "app.linkloft"
OUT = Path("verification")


def run(*command, binary=False, timeout=120):
    result = subprocess.run(command, capture_output=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError("Command failed: " + " ".join(command[:5]) + "\n" + result.stdout.decode(errors="replace")[-3000:] + "\n" + result.stderr.decode(errors="replace")[-2000:])
    return result.stdout if binary else result.stdout.decode(errors="replace")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", required=True)
    parser.add_argument("--archive", required=True, type=Path)
    args = parser.parse_args()
    assert os.environ.get("RUNNER_ENVIRONMENT") == "github-hosted"
    assert os.environ.get("GITHUB_REPOSITORY") == "simdalb/linkloft-releases"
    OUT.mkdir(exist_ok=True)
    devices = re.findall(r"^(emulator-\d+)\s+device$", run("adb", "devices"), re.MULTILINE)
    assert len(devices) == 1, devices
    serial = devices[0]

    def adb(*command, **kwargs):
        return run("adb", "-s", serial, *command, **kwargs)

    assert adb("shell", "getprop", "ro.kernel.qemu").strip() == "1"
    assert adb("shell", "getprop", "ro.build.version.sdk").strip() == args.api
    # sys.boot_completed can precede a stable package service on a new image.
    time.sleep(30)
    for attempt in range(12):
        try:
            assert "package:android" in adb("shell", "pm", "list", "packages", "android")
            break
        except (RuntimeError, AssertionError):
            if attempt == 11:
                raise
            time.sleep(5)
    baseline = adb("shell", "am", "start", "-W", "-a", "android.settings.SETTINGS")
    (OUT / "system-settings-baseline.txt").write_text(baseline, encoding="utf-8")
    assert "Status: ok" in baseline, "The emulator cannot open its own Settings app"
    baseline_screen = adb("exec-out", "screencap", "-p", binary=True)
    assert baseline_screen.startswith(b"\x89PNG"), "The emulator's screen capture service failed"
    (OUT / "system-settings-baseline.png").write_bytes(baseline_screen)
    adb("shell", "input", "keyevent", "KEYCODE_HOME")
    # Refuse replacement installs or any pre-existing user's library.
    assert not adb("shell", "pm", "list", "packages", PACKAGE).strip()
    extracted = Path("candidate/extracted")
    extracted.mkdir(exist_ok=True)
    with ZipFile(args.archive) as archive:
        names = sorted(name for name in archive.namelist() if name.endswith(".apk"))
        assert len(names) == 8 and all("/" not in name and "\\" not in name for name in names)
        metadata = json.loads(archive.read("meta.sai_v2.json"))
        assert metadata["package"] == PACKAGE and metadata["min_sdk"] == 26
        assert metadata["version_code"] == 20 and metadata["version_name"] == "0.6.0"
        for name in names:
            (extracted / name).write_bytes(archive.read(name))
    tools = Path(os.environ["ANDROID_HOME"]) / "build-tools/36.0.0"
    apk_paths = [extracted / name for name in names]
    for apk in apk_paths:
        certs = run(str(tools / "apksigner"), "verify", "--print-certs", str(apk))
        assert "Signer #1 certificate SHA-256 digest: " + SIGNER in certs
    base = extracted / "base.apk"
    manifest = run(str(tools / "aapt2"), "dump", "xmltree", str(base), "--file", "AndroidManifest.xml")
    assert "com.pairip" not in manifest and "CHECK_LICENSE" not in manifest
    assert "maxSdkVersion" not in manifest
    badging = run(str(tools / "aapt2"), "dump", "badging", str(base))
    assert "versionCode='20'" in badging and "minSdkVersion:'26'" in badging
    for attempt in range(3):
        try:
            install = adb("install-multiple", "--no-streaming", *map(str, apk_paths), timeout=180)
            break
        except RuntimeError as error:
            if attempt == 2 or not any(marker in str(error) for marker in ("Broken pipe", "device offline", "Can't find service")):
                (OUT / "installer-error.txt").write_text(str(error), encoding="utf-8")
                (OUT / "system-crash-log.txt").write_text(adb("logcat", "-d", "-s", "AndroidRuntime:E"), encoding="utf-8")
                raise
            print("The emulator package service is restarting; waiting before retry.", flush=True)
            time.sleep(15)
            assert not adb("shell", "pm", "list", "packages", PACKAGE).strip()
    assert "Success" in install
    adb("shell", "input", "keyevent", "KEYCODE_WAKEUP")
    adb("shell", "wm", "dismiss-keyguard")
    launch = adb("shell", "am", "start", "-W", "-a", "android.intent.action.MAIN", "-c", "android.intent.category.LAUNCHER", "-n", PACKAGE + "/com.simon.universallinklibrary.LauncherLoft")
    (OUT / "app-launch.txt").write_text(launch, encoding="utf-8")
    assert "Status: ok" in launch, launch
    time.sleep(12)
    pid = adb("shell", "pidof", PACKAGE).strip()
    assert pid and pid.isdigit(), "App exited after launching"
    crashes = adb("logcat", "-d", "--pid=" + pid, "-s", "AndroidRuntime:E")
    assert "FATAL EXCEPTION" not in crashes
    activities = adb("shell", "dumpsys", "activity", "activities")
    assert "com.pairip.licensecheck" not in activities
    adb("shell", "uiautomator", "dump", "/sdcard/linkloft-download-qa.xml")
    ui = adb("shell", "cat", "/sdcard/linkloft-download-qa.xml")
    (OUT / "screen.xml").write_text(ui, encoding="utf-8")
    (OUT / "screen.png").write_bytes(adb("exec-out", "screencap", "-p", binary=True))
    assert 'package="app.linkloft"' in ui
    result = {"androidApi": int(args.api), "freshExternalInstall": True, "originalSignedApks": 8, "signerSha256": SIGNER, "archiveSha256": hashlib.sha256(args.archive.read_bytes()).hexdigest(), "package": PACKAGE, "versionCode": 20, "installationResult": install.strip(), "launchSucceeded": True, "appStillRunning": True, "runtimeCrash": False, "playInstallerRedirect": False}
    (OUT / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        OUT.mkdir(exist_ok=True)
        (OUT / "failure.txt").write_text(str(error), encoding="utf-8")
        if os.environ.get("RUNNER_ENVIRONMENT") == "github-hosted" and os.environ.get("GITHUB_REPOSITORY") == "simdalb/linkloft-releases":
            for name, command in (
                ("activity-state.txt", ["adb", "shell", "dumpsys", "activity", "activities"]),
                ("package-state.txt", ["adb", "shell", "dumpsys", "package", PACKAGE]),
                ("crash-log.txt", ["adb", "logcat", "-d", "-s", "AndroidRuntime:E", "ActivityManager:E", "PackageManager:E"]),
                ("full-device-log.txt", ["adb", "logcat", "-d", "-v", "threadtime"]),
                ("failure-screen.png", ["adb", "exec-out", "screencap", "-p"]),
            ):
                result = subprocess.run(command, capture_output=True, timeout=30)
                (OUT / name).write_bytes(result.stdout)
        raise
