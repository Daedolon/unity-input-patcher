import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MAIN_PY = REPO_ROOT / "unity_input_patcher.py"
VENV_DIR = REPO_ROOT / ".venv_build"
DIST_DIR = REPO_ROOT / "dist"
BUILD_DIR = REPO_ROOT / "build"
PATCHES_DIR = REPO_ROOT / "patches"

UNITYPY_VERSION = "1.24.2"


def run(cmd: list[str], *, cwd: Path | None = None) -> None:
    print("[build]", " ".join(cmd))
    subprocess.check_call(cmd, cwd=str(cwd) if cwd else None)


def read_version() -> str:
    s = MAIN_PY.read_text(encoding="utf-8")
    m = re.search(r'^\s*VERSION\s*=\s*"([^"]+)"\s*$', s, re.M)
    if not m:
        raise SystemExit('[build] ERROR: Could not find VERSION = "..." in unity_input_patcher.py')
    return m.group(1)


def rm_tree(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)


def rm_file(path: Path) -> None:
    if path.exists():
        path.unlink()


def zip_dir(src_dir: Path, zip_path: Path) -> None:
    rm_file(zip_path)
    zip_path.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for p in src_dir.rglob("*"):
            if p.is_file():
                z.write(p, p.relative_to(src_dir))


def main(argv: list[str]) -> int:
    keep_build = True
    cleanup_after = False

    # Optional flag:
    #   --clean  => remove build/<name>/ and dist/<name>/ after zipping
    if "--clean" in argv:
        cleanup_after = True
        keep_build = False

    if not MAIN_PY.exists():
        print(f"[build] ERROR: Missing {MAIN_PY}")
        return 1

    ver = read_version()
    exename = f"unity-input-patcher-v{ver}"
    raw_dist_dir = DIST_DIR / exename
    outdir = DIST_DIR / f"unity-input-patcher-win64-v{ver}"
    zip_path = DIST_DIR / f"unity-input-patcher-win64-v{ver}.zip"
    build_subdir = BUILD_DIR / exename

    print(f"[build] Version: {ver}")
    print(f"[build] Output : {outdir}")
    print(f"[build] ZIP    : {zip_path}")
    if cleanup_after:
        print("[build] Cleanup: enabled (--clean)")

    # Ensure dist exists, but don't wipe it globally
    DIST_DIR.mkdir(parents=True, exist_ok=True)

    # Clean only version-specific outputs (safe re-runs)
    rm_tree(raw_dist_dir)
    rm_tree(outdir)
    rm_file(zip_path)

    # Clean/recreate build venv (deterministic builds)
    rm_tree(VENV_DIR)

    # Create clean build venv
    run(["py", "-m", "venv", str(VENV_DIR)])

    py = VENV_DIR / "Scripts" / "python.exe"
    if not py.exists():
        print(f"[build] ERROR: venv python not found at {py}")
        return 1

    # Install build deps (kept separate from runtime requirements.txt)
    run([str(py), "-m", "pip", "install", "--upgrade", "pip"])
    run([str(py), "-m", "pip", "install", f"UnityPy=={UNITYPY_VERSION}", "pyinstaller"])

    # Build (patches remain external: no --add-data)
    run([
        str(py), "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--noupx",
        "--collect-all", "UnityPy",
        "--name", exename,
        str(MAIN_PY),
    ], cwd=REPO_ROOT)

    if not raw_dist_dir.exists():
        print(f"[build] ERROR: Expected build output folder missing: {raw_dist_dir}")
        return 1

    # Create release folder (exe + _internal at root)
    outdir.mkdir(parents=True, exist_ok=True)
    for item in raw_dist_dir.iterdir():
        dest = outdir / item.name
        if item.is_dir():
            shutil.copytree(item, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(item, dest)

    # Copy patches next to exe as normal files (external, not embedded)
    if PATCHES_DIR.exists():
        shutil.copytree(PATCHES_DIR, outdir / "patches", dirs_exist_ok=True)

    (outdir / "VERSION.txt").write_text(ver + "\n", encoding="utf-8")

    # Zip the release folder contents (root = exe/_internal/patches/...)
    zip_dir(outdir, zip_path)

    # Optional cleanup after zipping
    if cleanup_after:
        rm_tree(raw_dist_dir)
        if not keep_build:
            rm_tree(build_subdir)

    print(f"[build] OK: {outdir}")
    print(f"[build] OK: {zip_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))