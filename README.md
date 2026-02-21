# Unity Input Patcher
Python utility for modifying Unity’s legacy `InputManager` settings inside `globalgamemanagers`.

Enables toggling options such as **Invert Y Axis** or adjusting key bindings when those settings are not configurable in-game.

Prebuilt Windows binaries are available under [**Releases**](https://github.com/Daedolon/unity-input-patcher/releases).

## Compatibility
Supports Unity **Legacy Input System** only.

Not compatible with the Unity **New Input System**.

## Usage example

### Windows (Recommended)

1. Close the game before patching.

2. Download the latest Win64 build from [**Releases**](https://github.com/Daedolon/unity-input-patcher/releases) and extract the zip.

3. After extracting, ensure the `.exe` and `_internal` folder are together in the same directory.

4. Run:

_Example: Patch E.E.R.I.E with the included **Invert Y Axis** patch_

```
unity-input-patcher.exe "C:\Program Files (x86)\Steam\steamapps\common\EERIE" --patch "patches\eerie\invert-y.json"
```

If a `patch.json` exists in the game directory (quick override mode), the tool can be run directly from that directory:

```
unity-input-patcher.exe
```

Run again to revert the patch.

Steam **"Verify integrity of game files"** restores the original files if needed.

### Python

**Installation**

```
git clone https://github.com/Daedolon/unity-input-patcher.git
cd unity-input-patcher
py -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

**Run from source**

```
python unity_input_patcher.py "C:\Program Files (x86)\Steam\steamapps\common\EERIE" --patch "patches\eerie\invert-y.json"
```

If a `patch.json` exists in the working directory:

```
python unity_input_patcher.py
```

## Custom patch creation

Inspect a game's `*_Data\globalgamemanagers` file using [SeriousCache/UABE](https://github.com/SeriousCache/UABE) (or the newer [nesrak1/UABEA](https://github.com/nesrak1/UABEA)):

1. Open `globalgamemanagers`
2. Locate the `InputManager` asset
3. View Data
4. Identify the target axis and field
   _(e.g. `[3] -> InputAxis data -> "Mouse Y" -> bool invert`)_
6. Create a JSON patch matching this schema:
```
{
  "id": "game-invert-y",
  "name": "Game - Invert Y Axis",
  "root_contains": ["Game_Data"],
  "file": "Game_Data/globalgamemanagers",
  "toggle": [
    {
      "type": "legacy_axis_field",
      "axis": 3,
      "axis_name": "Mouse Y",
      "field": "invert",
      "original": false,
      "patched": true
    }
  ]
}
```
