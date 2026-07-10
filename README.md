# fastscripts

One-command environment bootstrapper: Node.js, Java + apktool, and a ready-to-use
APK align+sign (v1+v2+v3) toolchain built on Google's official `apksig` library.

## Usage

```bash
python3 bootstrap.py
```

Or as a true one-liner on any fresh machine (after this repo is public/cloned):

```bash
curl -fsSL https://raw.githubusercontent.com/<your-username>/fastscripts/main/bootstrap.py | python3 -
```

On Replit, if Java/apktool aren't found, the script prints the exact
`installSystemDependencies` call to ask the agent to run (Nix-managed, so it
can't be installed by a plain shell script there).

## What it sets up

- **Node.js LTS** — via `nvm`, if not already on `PATH`.
- **Java 17 + apktool** — via `apt-get` on Debian/Ubuntu, or via Nix on Replit
  (prints the exact command to run).
- **`apk-toolchain/`** (created next to this script, persistent — safe to commit):
  - `apksig.jar` — Google's official APK signing library (v8.3.2)
  - `SignApk.java` / `classes/SignApk.class` — wrapper that aligns (4-byte,
    including `resources.arsc`) and signs with v1+v2+v3 in a single command
  - `nova_debug.jks` — debug keystore (`alias=androiddebugkey`, `pass=android`)

## APK patch/build pipeline

```bash
apktool d input.apk -o decompiled -f
# ...edit smali...
apktool b decompiled -o rebuilt.apk
java -cp apk-toolchain/classes:apk-toolchain/apksig.jar SignApk \
  rebuilt.apk signed.apk apk-toolchain/nova_debug.jks androiddebugkey android
```

Re-running `bootstrap.py` is safe — it skips anything already installed/downloaded.
