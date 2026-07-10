#!/usr/bin/env python3
"""
fastscripts/bootstrap.py
One-command environment bootstrapper:
  - Python (checks/reports; you're already running it)
  - Node.js LTS (via nvm)
  - Java 17 + apktool
  - APK align+sign toolchain:
      * Google apksig.jar + SignApk wrapper + debug keystore (custom, full control)
      * uber-apk-signer.jar (simpler one-step zipalign+v1/v2/v3, no custom code needed)
  - download_apk.py — fetch a real APK by package name via APKPure's CDN subdomain,
    which is NOT behind Cloudflare (unlike apkpure.com / apkmirror.com main sites)

Usage (one line, on any fresh Linux/macOS box or Replit shell):
  curl -fsSL https://raw.githubusercontent.com/<user>/fastscripts/main/bootstrap.py | python3 -

Or after cloning:
  python3 bootstrap.py

Everything is installed under ./apk-toolchain (persistent, safe to commit/copy)
except system packages (Node, Java, apktool) which go through the OS/Nix package
manager so they persist at the system level.
"""
import os
import platform
import shutil
import subprocess
import sys
import urllib.request

TOOLS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "apk-toolchain")
APKSIG_VERSION = "8.3.2"
APKSIG_URL = (
    "https://dl.google.com/dl/android/maven2/com/android/tools/build/apksig/"
    f"{APKSIG_VERSION}/apksig-{APKSIG_VERSION}.jar"
)
NVM_INSTALL_URL = "https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh"
UBER_SIGNER_VERSION = "1.3.0"
UBER_SIGNER_URL = (
    "https://github.com/patrickfav/uber-apk-signer/releases/download/"
    f"v{UBER_SIGNER_VERSION}/uber-apk-signer-{UBER_SIGNER_VERSION}.jar"
)

DOWNLOAD_APK_PY = r'''#!/usr/bin/env python3
"""
download_apk.py — fetch a real APK by package name.

apkpure.com and www.apkmirror.com are both behind a Cloudflare JS challenge on
many networks/datacenter IPs and cannot be scraped with plain curl/requests.
APKPure's direct CDN download subdomain (d.apkpure.com) is NOT behind that
challenge and serves the raw APK bytes directly.

Usage:
  python3 download_apk.py <package.name> [output.apk] [--version-code N]

Examples:
  python3 download_apk.py com.google.android.youtube
  python3 download_apk.py bin.mt.plus mt_manager.apk
  python3 download_apk.py com.google.android.youtube --version-code 1234567890
"""
import sys
import urllib.request

MOBILE_UA = (
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/116.0.0.0 Mobile Safari/537.36"
)


def download(package, out_path, version_code=None):
    version_part = f"?versionCode={version_code}" if version_code else "?version=latest"
    url = f"https://d.apkpure.com/b/APK/{package}{version_part}"
    print(f"Fetching {url} ...")
    req = urllib.request.Request(url, headers={"User-Agent": MOBILE_UA})
    with urllib.request.urlopen(req, timeout=120) as resp, open(out_path, "wb") as f:
        f.write(resp.read())

    with open(out_path, "rb") as f:
        header = f.read(4)
    # A real APK is a ZIP, so it starts with "PK\x03\x04". If we got HTML back
    # (e.g. a wrong versionCode guess or a block page), header won't match.
    if header[:2] != b"PK":
        print(
            f"WARNING: {out_path} does not look like a real APK (got non-ZIP content, "
            "likely an HTML error/block page). Verify with `file` before using it."
        )
        return False
    print(f"OK: saved {out_path} ({__import__('os').path.getsize(out_path)} bytes)")
    return True


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    pkg = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else f"{pkg}.apk"
    vcode = None
    if "--version-code" in sys.argv:
        vcode = sys.argv[sys.argv.index("--version-code") + 1]
    ok = download(pkg, out, vcode)
    sys.exit(0 if ok else 2)
'''

SIGNAPK_JAVA = r"""import com.android.apksig.ApkSigner;
import com.android.apksig.apk.ApkFormatException;

import java.io.File;
import java.io.FileInputStream;
import java.security.KeyStore;
import java.security.PrivateKey;
import java.security.cert.X509Certificate;
import java.util.Collections;
import java.util.List;

/**
 * Usage: SignApk <in.apk> <out.apk> <keystore.jks> <alias> <storepass> [keypass]
 * Aligns (4-byte, incl. resources.arsc) and signs with v1+v2+v3 in one pass.
 */
public class SignApk {
    public static void main(String[] args) throws Exception {
        if (args.length < 5) {
            System.err.println("Usage: SignApk <in.apk> <out.apk> <keystore.jks> <alias> <storepass> [keypass]");
            System.exit(1);
        }
        File inApk = new File(args[0]);
        File outApk = new File(args[1]);
        String keystorePath = args[2];
        String alias = args[3];
        String storePass = args[4];
        String keyPass = args.length > 5 ? args[5] : storePass;

        KeyStore ks = KeyStore.getInstance("JKS");
        try (FileInputStream fis = new FileInputStream(keystorePath)) {
            ks.load(fis, storePass.toCharArray());
        }

        PrivateKey privateKey = (PrivateKey) ks.getKey(alias, keyPass.toCharArray());
        if (privateKey == null) {
            System.err.println("No private key found for alias: " + alias);
            System.exit(1);
        }
        X509Certificate cert = (X509Certificate) ks.getCertificate(alias);
        List<X509Certificate> certChain = Collections.singletonList(cert);

        ApkSigner.SignerConfig signerConfig =
                new ApkSigner.SignerConfig.Builder("CERT", privateKey, certChain).build();

        ApkSigner.Builder builder = new ApkSigner.Builder(Collections.singletonList(signerConfig))
                .setInputApk(inApk)
                .setOutputApk(outApk)
                .setV1SigningEnabled(true)
                .setV2SigningEnabled(true)
                .setV3SigningEnabled(true)
                .setAlignFileSize(true); // 4-byte align, incl. resources.arsc — required for v2/v3

        try {
            builder.build().sign();
        } catch (ApkFormatException e) {
            System.err.println("Warning: could not detect minSdkVersion (" + e.getMessage()
                    + "); retrying with minSdkVersion=1");
            try {
                builder.setMinSdkVersion(1).build().sign();
            } catch (ApkFormatException e2) {
                System.err.println("Bad APK format: " + e2.getMessage());
                System.exit(1);
            }
        }
        System.out.println("Signed (v1+v2+v3, aligned): " + outApk.getAbsolutePath());
    }
}
"""


def run(cmd, **kw):
    print(f"$ {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    return subprocess.run(cmd, shell=isinstance(cmd, str), check=True, **kw)


def have(binary):
    return shutil.which(binary) is not None


def section(title):
    print(f"\n== {title} ==")


def ensure_python():
    section("Python")
    print(f"Using {sys.executable} ({platform.python_version()}) — already running, nothing to do.")


def ensure_node():
    section("Node.js")
    if have("node") and have("npm"):
        print(f"Found node {subprocess.check_output(['node', '-v']).decode().strip()}, skipping install.")
        return
    if platform.system() != "Linux" and platform.system() != "Darwin":
        print("Unsupported OS for auto-install; install Node.js manually.")
        return
    nvm_dir = os.path.expanduser("~/.nvm")
    if not os.path.isdir(nvm_dir):
        print("Installing nvm...")
        script = urllib.request.urlopen(NVM_INSTALL_URL).read().decode()
        subprocess.run(["bash", "-c", script], check=True)
    print("Installing Node.js LTS via nvm...")
    subprocess.run(
        ["bash", "-c", f'export NVM_DIR="{nvm_dir}"; . "$NVM_DIR/nvm.sh"; nvm install --lts'],
        check=True,
    )
    print("Node LTS installed. Open a new shell (or `source ~/.nvm/nvm.sh`) to pick it up.")


def ensure_java_and_apktool():
    section("Java + apktool")
    if have("java") and have("apktool"):
        print("Both java and apktool already on PATH, skipping.")
        return
    if have("nix-env") or os.environ.get("REPL_ID"):
        print("Detected Replit/Nix environment.")
        print("Ask the agent to run (package-management skill):")
        print('  installSystemDependencies({ packages: ["temurin-bin-17", "apktool"] })')
        return
    if have("apt-get"):
        print("Installing via apt-get (needs sudo)...")
        run("sudo apt-get update && sudo apt-get install -y default-jdk unzip wget")
        if not have("apktool"):
            print("Installing apktool manually...")
            bin_dir = os.path.expanduser("~/.local/bin")
            os.makedirs(bin_dir, exist_ok=True)
            wrapper_url = "https://raw.githubusercontent.com/iBotPeaches/Apktool/master/scripts/linux/apktool"
            jar_url = "https://bitbucket.org/iBotPeaches/apktool/downloads/apktool_2.9.3.jar"
            urllib.request.urlretrieve(wrapper_url, os.path.join(bin_dir, "apktool"))
            urllib.request.urlretrieve(jar_url, os.path.join(bin_dir, "apktool.jar"))
            os.chmod(os.path.join(bin_dir, "apktool"), 0o755)
            print(f"Installed to {bin_dir} — make sure it's on PATH.")
    else:
        print("No known package manager found; install java (17+) and apktool manually.")


def ensure_apk_signing_toolchain():
    section("APK align+sign toolchain (apksig)")
    os.makedirs(TOOLS_DIR, exist_ok=True)

    apksig_jar = os.path.join(TOOLS_DIR, "apksig.jar")
    if not os.path.isfile(apksig_jar) or os.path.getsize(apksig_jar) < 100_000:
        print(f"Downloading apksig.jar v{APKSIG_VERSION}...")
        urllib.request.urlretrieve(APKSIG_URL, apksig_jar)
    else:
        print("apksig.jar already present, skipping download.")

    signapk_java = os.path.join(TOOLS_DIR, "SignApk.java")
    with open(signapk_java, "w") as f:
        f.write(SIGNAPK_JAVA)

    classes_dir = os.path.join(TOOLS_DIR, "classes")
    os.makedirs(classes_dir, exist_ok=True)
    if have("javac"):
        print("Compiling SignApk.java...")
        run(["javac", "-cp", apksig_jar, "-d", classes_dir, signapk_java])
    else:
        print("javac not found — install Java first, then re-run this script.")

    keystore = os.path.join(TOOLS_DIR, "nova_debug.jks")
    if not os.path.isfile(keystore):
        if have("keytool"):
            print("Generating debug keystore...")
            run([
                "keytool", "-genkeypair", "-v",
                "-keystore", keystore, "-storepass", "android",
                "-alias", "androiddebugkey", "-keypass", "android",
                "-keyalg", "RSA", "-keysize", "2048", "-validity", "10000",
                "-dname", "CN=Android Debug,O=Android,C=US",
            ])
        else:
            print("keytool not found — install Java first, then re-run this script.")
    else:
        print("Debug keystore already present, skipping.")

    print("\nReady (custom signer). Pipeline:")
    print("  apktool d input.apk -o decompiled -f")
    print("  # ...edit smali...")
    print("  apktool b decompiled -o rebuilt.apk")
    print(
        f"  java -cp {classes_dir}:{apksig_jar} SignApk \\\n"
        f"    rebuilt.apk signed.apk {keystore} androiddebugkey android"
    )


def ensure_uber_apk_signer():
    section("uber-apk-signer (simpler one-step align+sign alternative)")
    os.makedirs(TOOLS_DIR, exist_ok=True)
    jar_path = os.path.join(TOOLS_DIR, f"uber-apk-signer-{UBER_SIGNER_VERSION}.jar")
    if not os.path.isfile(jar_path) or os.path.getsize(jar_path) < 1_000_000:
        print(f"Downloading uber-apk-signer v{UBER_SIGNER_VERSION}...")
        urllib.request.urlretrieve(UBER_SIGNER_URL, jar_path)
    else:
        print("uber-apk-signer already present, skipping download.")

    keystore = os.path.join(TOOLS_DIR, "nova_debug.jks")
    print("\nReady (uber-apk-signer). Usage — does zipalign + v1/v2/v3 in ONE step:")
    print(
        f"  java -jar {jar_path} -a rebuilt.apk \\\n"
        f"    --ks {keystore} --ksAlias androiddebugkey \\\n"
        f"    --ksKeyPass android --ksPass android --allowResign -o out/"
    )


def ensure_download_apk_script():
    section("download_apk.py (fetch real APKs, bypassing Cloudflare)")
    os.makedirs(TOOLS_DIR, exist_ok=True)
    script_path = os.path.join(TOOLS_DIR, "download_apk.py")
    with open(script_path, "w") as f:
        f.write(DOWNLOAD_APK_PY)
    os.chmod(script_path, 0o755)
    print(f"Wrote {script_path}")
    print("Usage: python3 apk-toolchain/download_apk.py <package.name> [output.apk]")
    print("  (apkpure.com / apkmirror.com main sites are Cloudflare-gated; d.apkpure.com is not)")


def main():
    ensure_python()
    ensure_node()
    ensure_java_and_apktool()
    ensure_apk_signing_toolchain()
    ensure_uber_apk_signer()
    ensure_download_apk_script()
    print("\nAll done.")


if __name__ == "__main__":
    main()
