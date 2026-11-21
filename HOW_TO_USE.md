# How to Use `inject_camp_music.py`

[inject_camp_music.py](inject_camp_music.py) is a standalone Python CLI & GUI tool that builds Unreal Engine 4.26.2 IoStore mod files (`.pak`, `.utoc`, `.ucas`) to **add your own custom songs to Stellar Blade's Camp Turntable while keeping all 34 original in-game tracks intact**.

---

## 1. Requirements

- **Windows** (required for the native Win32 desktop GUI and automatic extraction of base-game assets via Stellar Blade's embedded Oodle decompressor).
- **Python 3.10+** (uses only the Python standard library for core functionality — **no `pip install` dependencies required**).
- **FFmpeg** *(optional)*: Needed if you pass `.mp3`, `.wav`, `.flac`, `.m4a`, etc. instead of an `.ogg` (Ogg Vorbis) file, if you use `--reencode`, or as a fallback for cover image conversion when Pillow is not installed.
- **Pillow / mutagen** *(optional)*: `Pillow` adds rounded album-card framing with soft drop shadows for custom cover art; `mutagen` improves embedded tag and cover art extraction across complex audio metadata formats (pure-Python fallbacks are built in).
- **Stellar Blade Game Folder**: Auto-detected from Steam (`C:\Program Files (x86)\Steam\steamapps\common\StellarBlade` by default, configurable via `--game-dir`). Used to extract the base `TurntableSoundTable.uasset` and `StringTable_UI.uasset` (cached in `.cache/`) and to install directly to `~mods`.

---

## 2. How It Works (Keeping Original Music)

- Instead of replacing existing Camp Turntable songs, the tool appends new custom entries to `/Game/Local/Data/TurntableSoundTable` (with `ConditionGroup = None`, so every added song is unlocked immediately at any camp) and appends their titles to `/Game/Local/Localize/StringTable_UI` (so titles display properly in every supported game language).
- All custom songs you add are bundled into **one** combined mod container (`<ModName>_P.{pak,utoc,ucas}`).
- All 34 original base-game, DLC, and event songs stay untouched and playable.

> [!NOTE]
> Because `TurntableSoundTable` and `StringTable_UI` are overridden inside the mod container, bundle all of your custom songs into **one** mod package (using the GUI playlist, `--batch`, or multiple `-i` flags) rather than placing multiple separate camp music `.pak`/`.utoc`/`.ucas` mods in `~mods` at the same time.

---

## 3. Graphical User Interface (GUI)

Launch the native Windows desktop GUI by **double-clicking `Launch_GUI.bat`**, or via command line:

```powershell
# Double-click Launch_GUI.bat, or run:
.\Launch_GUI.bat
```
or:
```powershell
python camp_music_gui.py
```
or:
```powershell
python inject_camp_music.py --gui
```

### GUI Features
- **Custom Song Playlist**: Add one or many songs via **Add Song(s)...**, **Load ./Music Folder**, **Load Custom Folder...**, or by **dragging & dropping** audio files, a music folder, a cover image (for the selected track), or your Stellar Blade folder directly onto the window.
- **Reorder & Customize Each Track**: Move tracks up/down, customize each song's **In-Game Title**, optionally attach a muffled **Ambient (`_OFF`)** audio file, and set per-song **Custom Album Cover Art** (auto-extracted from embedded audio artwork or any `.png`/`.jpg`/`.webp` image file, with preset fallback).
- **Audio & Image Metadata Safety**: Embedded album art (`APIC`, `METADATA_BLOCK_PICTURE`, `covr`) is extracted into separate `UTexture2D` (`256×256` `PF_B8G8R8A8`) textures while all picture/tag metadata is stripped cleanly from the Ogg Vorbis audio streams sent to the game.
- **Audio Inspector & Instant Preview**: Shows exact duration (`M:SS`), channels, sample rate, file size, and Vorbis compatibility. Double-click a track or click **Preview Selected Audio** to listen before building.
- **Smart Game Auto-Detection & `~mods` Warning**: Detects your Stellar Blade installation automatically and warns if older `CampMusic_*` mods are already sitting in `~mods`.
- **Persistent Settings**: Saves your playlist, game directory, volume levels, and mod name to `.cache/gui_settings.json`.

---

## 4. CLI Quick Start Examples

### Add All Songs from `./Music` Into One Combined Mod
Place your audio files in the `Music/` folder (or pass `--batch <folder>`). Files are naturally sorted (`01`, `02`, ..., `10`), titles are formatted as `Song Name (Artist)` from embedded audio tags (or filename), and any matching `*_off.*` / `*_muffled.*` / `*_ambient.*` files are paired automatically:
```powershell
python inject_camp_music.py --batch --install
```

### Add a Single Custom Song
```powershell
python inject_camp_music.py -i my_song.ogg --title "My Custom Song" --install
```
This creates one combined mod (`CampMusic_Custom_295_P.{pak,utoc,ucas}`) containing your custom track alongside all 34 original tracks.

### Add Multiple Specific Songs via CLI
Repeat `-i` (and optionally `--title` / `--input-off` in matching order):
```powershell
python inject_camp_music.py -i song1.mp3 --title "First Song" -i song2.ogg --title "Second Song" --install
```

### Supply a Separate Muffled / Ambient Audio File for `_OFF`
Each camp track has an `_ON` stream (primary playback, default volume `1.1`) and an `_OFF` stream (ambient/muffled state, default volume `0.6`). By default, your input file is used for both:
```powershell
python inject_camp_music.py -i my_song_on.ogg --input-off my_song_muffled.ogg --title "My Song" --install
```

---

## 5. Command-Line Arguments Reference

| Argument | Default | Description |
| :--- | :--- | :--- |
| `--gui` | `False` | Launch the native Windows graphical user interface (`camp_music_gui.py`). |
| `--batch [folder]` | `None` (defaults to `./Music` if flag is passed without argument) | Bundle all audio files from a folder into one combined mod while keeping all 34 original tracks. |
| `-i`, `--input <path>` | *(Required unless `--batch`, `--gui`, or `--list-tracks`)* | Input audio file (`.ogg` used directly; `.wav`, `.mp3`, `.flac`, `.m4a` auto-converted to `48000 Hz` stereo Ogg Vorbis via `ffmpeg`). Repeat `-i` to bundle multiple tracks. |
| `--input-off <path>` | Same as `--input` | Optional separate audio file for the `<Track>_OFF` (`NoiseMusicPath`) asset (repeatable to pair with each `-i`). |
| `--title <text>` | Cleaned filename | Custom song title to display in the Camp Turntable UI (repeatable to pair with each `-i`). Written into `StringTable_UI.uasset`. |
| `--cover <path>` | Auto-extracted / fallback | Custom cover image (`.png`/`.jpg`/`.webp`) paired with each `-i` (packed as `256×256` `UTexture2D`). |
| `--album-art <preset\|path>` | `Classic Vinyl (Default)` | Fallback album cover preset (`1..9`), `Texture2D'...'` path, or image file path when no `--cover`/embedded art is used. |
| `--no-embedded-art` | `False` | Skip automatic embedded cover art extraction from audio files (always use `--cover` or preset fallback). |
| `-n`, `--mod-name <name>` | `CampMusic_Custom_295_P` | Base filename for the output `.pak`, `.utoc`, and `.ucas` files (`_P` suffix is appended automatically if omitted). |
| `-o`, `--output-dir <dir>` | `./dist` | Output folder for generated `.pak`, `.utoc`, and `.ucas` files (ignored if `--install` is passed). |
| `--install` | `False` | Write output files directly to `<game-dir>/SB/Content/Paks/~mods/`. |
| `--volume-on <float>` | `1.1` | Playback volume multiplier for primary `_ON` `USoundWave` assets. |
| `--volume-off <float>` | `0.6` | Playback volume multiplier for secondary `_OFF` `USoundWave` assets. |
| `--reencode` | `False` | Force re-encoding via `ffmpeg` (`48000 Hz`, `2` channels, Vorbis `-q:a 4`) even if input is already `.ogg`. |
| `--game-dir <dir>` | Auto-detected | Path to the `StellarBlade` game installation folder. |
| `--template-ucas <path>` | Auto-detected (`.cache/cqt_template.bin`) | Optional path to a `.ucas` or `.bin` template file for CQT visualizer spectrum patterns (uses dynamic reactive CQT synthesizer if unavailable). |
| `--list-tracks` | `False` | Print a reference table of the 34 original base-game Camp Turntable tracks and exit. |
