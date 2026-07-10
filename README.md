# fastscripts

One-command environment bootstrapper: Node.js, Java + apktool, and a ready-to-use
APK align+sign (v1+v2+v3) toolchain — plus a working method for downloading real
APKs when apkpure.com / apkmirror.com are Cloudflare-gated.

## Usage

```bash
python3 bootstrap.py
```

Or as a true one-liner on any fresh machine:

```bash
git clone https://github.com/e-creator1309/fastscripts.git && cd fastscripts && python3 bootstrap.py
```

On Replit, if Java/apktool aren't found, the script prints the exact
`installSystemDependencies` call to ask the agent to run (Nix-managed, so it
can't be installed by a plain shell script there).

## What it sets up (all under `apk-toolchain/`, persistent — safe to commit)

- **Node.js LTS** — via `nvm`, if not already on `PATH`.
- **Java 17 + apktool** — via `apt-get` on Debian/Ubuntu, or via Nix on Replit
  (prints the exact command to run).
- **`apksig.jar`** — Google's official APK signing library (v8.3.2).
- **`SignApk.java` / `classes/SignApk.class`** — custom wrapper that aligns
  (4-byte, including `resources.arsc`) and signs with v1+v2+v3 in one command.
- **`uber-apk-signer-1.3.0.jar`** — simpler drop-in alternative: does zipalign
  + v1/v2/v3 signing in one step, no custom Java code needed. Use this when you
  just want "align and sign," and reach for `SignApk` when you need more control
  (e.g. custom minSdk fallback logic).
- **`nova_debug.jks`** — debug keystore (`alias=androiddebugkey`, `pass=android`).
- **`download_apk.py`** — fetch a real APK by package name (see below).

Re-running `bootstrap.py` is safe — it skips anything already installed/downloaded.

## Downloading a real APK (Cloudflare-safe method)

`apkpure.com` and `www.apkmirror.com` both put an interactive Cloudflare JS
challenge in front of plain `curl`/`requests` on many networks (confirmed on
Replit's sandbox IPs) — scraping those pages directly does not work reliably.

**Working alternative:** APKPure's direct CDN download subdomain, `d.apkpure.com`,
is NOT behind that challenge and serves the raw APK bytes directly:

```bash
python3 apk-toolchain/download_apk.py <package.name> [output.apk]

# e.g.
python3 apk-toolchain/download_apk.py com.google.android.youtube
python3 apk-toolchain/download_apk.py bin.mt.plus mt_manager.apk
python3 apk-toolchain/download_apk.py com.google.android.youtube pinned.apk --version-code 1234567890
```

Equivalent raw curl (mobile UA matters — some UAs get blocked):

```bash
curl -sL --max-time 120 \
  -A "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Mobile Safari/537.36" \
  -o app.apk \
  "https://d.apkpure.com/b/APK/<package.name>?version=latest"

file app.apk   # must say "Android package (APK), with AndroidManifest.xml", not HTML
```

`version=latest` gets whatever APKPure currently serves. For a pinned/specific
version, use `?versionCode=<N>` instead — wrong guesses there return HTML
silently, so always verify with `file` (or the script's built-in ZIP-header check).

If you need to confirm the actual target platform/SDK after downloading (version
strings can be misleading — e.g. Samsung's `15.0.03.35` looks like an OS version
but isn't), use `aapt2 dump badging app.apk | grep -E "platformBuildVersionName|targetSdkVersion|compileSdkVersion"`
(requires the full Android SDK build-tools — not bundled here).

## APK patch/build pipeline

```bash
apktool d input.apk -o decompiled -f
# ...edit smali...
apktool b decompiled -o rebuilt.apk

# Option A: custom SignApk (fine-grained control)
java -cp apk-toolchain/classes:apk-toolchain/apksig.jar SignApk \
  rebuilt.apk signed.apk apk-toolchain/nova_debug.jks androiddebugkey android

# Option B: uber-apk-signer (simplest — one step, no custom code)
java -jar apk-toolchain/uber-apk-signer-1.3.0.jar -a rebuilt.apk \
  --ks apk-toolchain/nova_debug.jks --ksAlias androiddebugkey \
  --ksKeyPass android --ksPass android --allowResign -o out/
```

⚠️ Order matters: align must happen before signing (v2/v3 signatures cover the
whole file byte-for-byte). Both signing options above align and sign in one
call, so this is handled automatically — just don't manually zipalign an
already-signed APK or you'll break the signature.
