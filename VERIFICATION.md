# Download verification — 0.6.0

The published `Linkloft-0.6.0-Android-8-plus.apks` has SHA-256:

```
7255301b711968e0a7ed85b8c5bdf026fed6d36ad530b473da9e30b23f6f98f8
```

All eight contained APKs retain the original Google Play signature. Their checksums and signer are listed in the release's `PROVENANCE.json`. The archive was downloaded again after publication and matched the tested checksum.

Fresh external installation and launch passed on disposable Android 8 (API 26) and Android 16 (API 36) virtual devices. The app remained running, showed the Linkloft home screen and did not redirect to Google Play for installation.

- [Android 8 result](https://github.com/simdalb/linkloft-releases/actions/runs/39078170675)
- [Android 16 result and Android 17 baseline](https://github.com/simdalb/linkloft-releases/actions/runs/39079171386)

The Android 17 virtual-device check is **inconclusive**. Its activity service failed to open the device's own Settings app, before Linkloft was installed. Disabling Vulkan and using software rendering did not resolve that device failure. This is not a passing Android 17 installation test, nor evidence of a Linkloft-specific failure.

These checks cover installation and initial launch, not every feature or every Android device. Google Play remains the easiest installation route. Direct downloads need a compatible split APK installer.
