#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Optional, Tuple

import UnityPy

VERSION = "0.1.0"
PATCH_DEFAULT = "patch.json"
FLOAT_EPS = 1e-6


# Read JSON from disk.
def load_json(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


# Resolve game root (arg or CWD).
def game_root_from_arg(s: Optional[str]) -> Path:
    return Path(s).resolve() if s else Path.cwd().resolve()


# Resolve patch path (absolute, or relative to this script).
def patch_path_from_arg(s: str) -> Path:
    p = Path(s)
    return p if p.is_absolute() else (Path(__file__).resolve().parent / p).resolve()


# Quote a path for safe copy/paste in Windows cmd.
def q(p: Path) -> str:
    return f"\"{p}\""


# Fail if required files/dirs are missing from the game root.
def verify_root_contains(root: Path, items: list[str]) -> None:
    missing = [x for x in items if not (root / x).exists()]
    if missing:
        raise RuntimeError(f"Root sanity check failed at {q(root)} (missing: {', '.join(missing)})")


# Fetch a required key from a dict with a nice error.
def req(d: dict, k: str) -> Any:
    if k not in d:
        raise RuntimeError(f"Toggle entry missing required key: {k!r}")
    return d[k]


# Print a formatted failure block and return an exit code.
def fail(message: str, *, extra: Optional[str] = None, code: int = 1) -> int:
    print(f"[UnityInputPatcher] ERROR: {message}")
    if extra:
        print(f"[UnityInputPatcher] {extra}")
    print("[UnityInputPatcher] ERROR: Patch failed to apply.")
    return code


# Resolve the target file (relative to game root).
def target_file(root: Path, rel: str) -> Path:
    p = root / rel
    if not p.exists() or not p.is_file():
        raise FileNotFoundError(f"Target file not found: {q(p)}")
    return p


# Find a Unity object by class name.
def find_obj(env: Any, type_name: str) -> Any:
    for o in env.objects:
        if getattr(o.type, "name", None) == type_name:
            return o
    raise RuntimeError(f"{type_name} not found (wrong file / Unity version / not legacy InputManager?)")


# Read a Unity object as a typetree dict (UnityPy-version tolerant).
def read_tree(o: Any) -> dict:
    if hasattr(o, "read_typetree"):
        return o.read_typetree()
    data = o.read()
    if isinstance(data, dict):
        return data
    if hasattr(data, "to_dict"):
        return data.to_dict()
    if hasattr(data, "type_tree"):
        return data.type_tree
    raise RuntimeError("Cannot read typetree (UnityPy API mismatch)")


# Write a typetree dict back into a Unity object (UnityPy-version tolerant).
def write_tree(o: Any, d: dict) -> None:
    if hasattr(o, "save_typetree"):
        o.save_typetree(d)
        return
    data = o.read()
    if hasattr(data, "save_typetree"):
        data.save_typetree(d)
        return
    raise RuntimeError("Cannot write typetree (UnityPy API mismatch)")


# Compare values with float tolerance; strict for everything else.
def equal(a: Any, b: Any) -> bool:
    if isinstance(a, (int, float)) and not isinstance(a, bool) and isinstance(b, (int, float)) and not isinstance(b, bool):
        return math.isfinite(float(a)) and math.isfinite(float(b)) and abs(float(a) - float(b)) <= FLOAT_EPS
    return a == b


# Decide whether to apply or revert based on current value.
def toggle_decision(current: Any, original: Any, patched: Any) -> Tuple[Optional[Any], str]:
    if equal(current, original):
        return patched, "applied"
    if equal(current, patched):
        return original, "reverted"
    return None, "unknown"


# Apply a single legacy InputManager axis field toggle.
def toggle_legacy_axis_field(
    axes: list[dict],
    axis_index: int,
    field: str,
    original: Any,
    patched: Any,
    axis_name: Optional[str],
) -> Tuple[str, str, str]:
    if axis_index < 0 or axis_index >= len(axes):
        raise IndexError(f"Axis index out of range: {axis_index} (axes={len(axes)})")

    ax = axes[axis_index]
    name = ax.get("m_Name", "")

    if axis_name:
        if name != axis_name:
            raise RuntimeError(f"Axis name mismatch at index {axis_index}: expected {axis_name!r}, found {name!r}")

    if field not in ax:
        raise RuntimeError(f"Field {field!r} not present on axis[{axis_index}] (name={name!r})")

    cur = ax[field]
    new, mode = toggle_decision(cur, original, patched)
    if new is None:
        raise RuntimeError(
            f"Unknown state for axis[{axis_index}] {name!r}.{field}: current={cur!r}, expected {original!r} or {patched!r}"
        )

    ax[field] = new
    line = f"axis[{axis_index}] {name!r}.{field}: {cur!r} -> {new!r}"
    check = f"axis_name_ok ({name!r})" if axis_name else "axis_name_skipped"
    return mode, line, check


# Serialize the modified Unity file back to the original path (in-place).
def save_in_place(env: Any, out_path: Path) -> None:
    data = None
    if hasattr(env, "file") and hasattr(env.file, "save"):
        data = env.file.save()
    if data is None and hasattr(env, "fs") and hasattr(env.fs, "save"):
        data = env.fs.save()
    if data is None:
        raise RuntimeError("UnityPy could not serialize (no save() available)")
    out_path.write_bytes(data)


# Run one toggle pass.
def run(game_root: Path, patch_path: Path) -> None:
    patch = load_json(patch_path)
    patch_id = str(patch.get("id") or patch_path.stem)
    patch_name = str(patch.get("name") or patch_id)

    root_contains = patch.get("root_contains", [])
    if isinstance(root_contains, list) and root_contains:
        items = [str(x) for x in root_contains]
        try:
            verify_root_contains(game_root, items)
        except RuntimeError:
            parent = game_root.parent
            if parent != game_root:
                print(f"[UnityInputPatcher] Root check failed at {q(game_root)}; trying parent {q(parent)}")
                verify_root_contains(parent, items)
                game_root = parent
            else:
                raise

    rel = patch.get("file")
    if not isinstance(rel, str) or not rel.strip():
        raise RuntimeError("patch.json missing required string: 'file'")

    file_path = target_file(game_root, rel)

    toggles = patch.get("toggle")
    if not isinstance(toggles, list) or not toggles:
        raise RuntimeError("patch.json missing required non-empty list: 'toggle'")

    print(f"[UnityInputPatcher] Loaded patch: {patch_name} ({patch_id})")
    print(f"[UnityInputPatcher] Root: {q(game_root)}")
    print(f"[UnityInputPatcher] File: {q(file_path)}")
    if root_contains:
        count = len(root_contains)
        label = "item" if count == 1 else "items"
        print(f"[UnityInputPatcher] Root check: OK ({count} required {label})")

    env = UnityPy.load(str(file_path))
    im = find_obj(env, "InputManager")
    d = read_tree(im)

    axes = d.get("m_Axes")
    if not isinstance(axes, list):
        raise RuntimeError("InputManager.m_Axes missing or unexpected format")

    mode_seen: Optional[str] = None
    checks: list[str] = []
    logs: list[str] = []

    for t in toggles:
        if not isinstance(t, dict):
            raise RuntimeError(f"Bad toggle entry (not object): {t!r}")
        if t.get("type") != "legacy_axis_field":
            raise RuntimeError(f"Unsupported toggle type: {t.get('type')!r}")

        # Read required toggle fields.
        try:
            axis_index = int(req(t, "axis"))
        except Exception:
            raise RuntimeError(f"Toggle entry has non-integer 'axis': {t.get('axis')!r}")
        field = str(req(t, "field"))
        original = req(t, "original")
        patched = req(t, "patched")
        axis_name = t.get("axis_name")
        axis_name = str(axis_name) if isinstance(axis_name, str) and axis_name.strip() else None

        mode, line, check = toggle_legacy_axis_field(
            axes=axes,
            axis_index=axis_index,
            field=field,
            original=original,
            patched=patched,
            axis_name=axis_name,
        )

        if mode_seen is None:
            mode_seen = mode
        elif mode_seen != mode:
            raise RuntimeError("Mixed apply/revert across entries (patch values don't match current file consistently)")

        checks.append(check)
        logs.append(line)

    d["m_Axes"] = axes
    write_tree(im, d)
    save_in_place(env, file_path)

    for c in checks:
        print(f"[UnityInputPatcher] Check: {c}")
    for l in logs:
        print(f"[UnityInputPatcher] Patched: {l}")

    if mode_seen == "applied":
        print("[UnityInputPatcher] Patch applied OK.")
    else:
        print("[UnityInputPatcher] Patch reverted OK.")


def main() -> int:
    print(f"[UnityInputPatcher] ===== UNITY INPUT PATCHER v{VERSION} =====")

    ap = argparse.ArgumentParser(prog="UnityInputPatcher", add_help=True)
    ap.add_argument("game_root", nargs="?", default=None)
    ap.add_argument("--patch", default=PATCH_DEFAULT)
    args = ap.parse_args()

    try:
        root = game_root_from_arg(args.game_root)
        patch_path = patch_path_from_arg(args.patch)

        if not patch_path.exists():
            return fail(f"Patch file not found ({q(patch_path)}).", code=2)

        run(root, patch_path)
        return 0

    except PermissionError as e:
        where = q(Path(e.filename)) if getattr(e, "filename", None) else str(e)
        return fail(
            f"Cannot write to file ({where}).",
            extra="Try closing the game or running it as Administrator.",
            code=3,
        )

    except Exception as e:
        return fail(str(e), code=1)


if __name__ == "__main__":
    raise SystemExit(main())