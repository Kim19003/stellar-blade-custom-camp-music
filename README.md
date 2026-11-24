# Stellar Blade Custom Camp Music Injector

Add your own custom songs to **Stellar Blade's Camp Turntable** — complete with custom song titles, album cover art, and reactive visualizer spectrums — **while keeping all 34 original in-game tracks intact**.

No Unreal Engine installation or `pip install` dependencies are required.

> [!NOTE]
> **AI-Assisted Development**: AI was heavily used throughout this project (including reverse-engineering analysis, UE4 IoStore/Zen asset synthesis, GUI/CLI code, and documentation). Please review the code before running it if you have security concerns.

---

## Features

- **Preserves All 34 Original Songs**: Appends your custom tracks directly to `TurntableSoundTable.uasset` and `StringTable_UI.uasset` instead of replacing vanilla songs. Every custom song is unlocked immediately at any camp (`ConditionGroup = None`) and displays its title in every game language.
- **Native Windows Desktop GUIs**:
  - `Launch_GUI.bat` (`camp_music_gui.py`) for adding individual custom songs with drag-and-drop support, audio preview, and Steam game auto-detection.
  - `Launch_Radio_GUI.bat` (`radio_music_gui.py`) for building **"Fake Radio"** stations from folders (e.g. `Music/PopRadio/`): randomly shuffles and combines songs into one or more pre-shuffled station variants (`Pop Radio #1`, `Pop Radio #2`, ...) with custom folder/1st-song cover art, configurable silence gaps, and automatic visualizer disabling for long mixes.
- **Full CLI Automation**: Build single-track or multi-track mods from the command line or batch-pack an entire `Music/` folder in seconds.
- **Custom & Embedded Album Cover Art**: Automatically extracts embedded artwork (`APIC`, `METADATA_BLOCK_PICTURE`, `covr`) or accepts custom `.png`/`.jpg`/`.webp` images (packed as `256×256` `UTexture2D` assets), with 9 vanilla cover presets as fallbacks.
- **Safe Audio Metadata Stripping**: Strips embedded pictures and Vorbis comment tags from `.ogg` audio streams before packaging so Unreal Engine's Vorbis decoder loads every track cleanly.
- **Ambient (`_OFF`) Audio & Volume Controls**: Pair each song with an optional muffled/ambient `_OFF` track and tune primary/ambient volumes independently.
- **Reactive Visualizer (`UConstantQNRT`)**: Synthesizes duration-matched `UConstantQNRT` spectrum assets so the camp turntable's visualizer animates with your music.
- **Smart Steam Auto-Detection**: Automatically locates your Stellar Blade installation via Windows Registry / Steam library folders (`libraryfolders.vdf`), extracts the required base tables from `pakchunk0`, and can install directly to `SB\Content\Paks\~mods`.

---

## Requirements

- **OS**: Windows (required for the native Win32 GUI and base-game asset extraction via Stellar Blade's Oodle decompressor).
- **Python**: Python **3.10 or newer** (standard library only for core usage).
- **FFmpeg** *(optional)*: Required only if you add non-`.ogg` audio files (`.mp3`, `.wav`, `.flac`, `.m4a`, etc.), use `--reencode`, or convert cover images without Pillow.
- **Pillow / mutagen** *(optional)*:
  - `Pillow` enables rounded album card framing with soft drop shadows for custom cover art.
  - `mutagen` improves embedded tag/artwork reading across complex audio files (pure-Python fallbacks are built in for `.ogg`, `.flac`, and `.mp3` ID3 tags).

---

## Quick Start

### Option A: Desktop GUI (Recommended)

1. Clone or download this repository.
2. Double-click **`Launch_GUI.bat`** (or run `python camp_music_gui.py`).
3. Drag and drop audio files or a music folder onto the window (or click **Add Song(s)...** / **Load ./Music Folder**).
4. Adjust song titles, optional ambient (`_OFF`) files, cover art, and volume as needed.
5. Verify your Stellar Blade folder (auto-detected on startup) and click **Build Custom Music Mod**.
6. Launch Stellar Blade and play your custom tracks at any Camp Turntable.

### Option B: Command Line (CLI)

Place your audio files inside the `Music/` folder and run:

```powershell
python inject_camp_music.py --batch --install
```

Or package specific files directly:

```powershell
python inject_camp_music.py -i "my_song.ogg" --title "My Custom Song" --install
```

> [!NOTE]
> Because `TurntableSoundTable` and `StringTable_UI` are overridden inside the mod container, bundle all of your custom songs into **one** combined mod (`<ModName>_P.{pak,utoc,ucas}`) rather than putting multiple separate camp music mods in `~mods` at the same time.

---

## Repository Structure

| File / Folder | Purpose |
| :--- | :--- |
| [Launch_GUI.bat](Launch_GUI.bat) | One-click Windows launcher for the per-song desktop GUI |
| [Launch_Radio_GUI.bat](Launch_Radio_GUI.bat) | One-click Windows launcher for the Camp Radio & Shuffle GUI |
| [camp_music_gui.py](camp_music_gui.py) | Native Win32 GUI application for individual tracks |
| [radio_music_gui.py](radio_music_gui.py) | Native Win32 GUI application for shuffled Camp Radio folders |
| [gui_common.py](gui_common.py) | Shared Win32 GUI helpers and Stellar Blade auto-detection |
| [inject_camp_music.py](inject_camp_music.py) | Core UE 4.26.2 Zen/IoStore builder, asset synthesizer, radio mixer, and CLI |
| [Music/](Music/) | Default drop-in folder for `--batch` and the GUI's **Load ./Music Folder** button |
| [HOW_TO_USE.md](HOW_TO_USE.md) | Detailed user guide and full CLI flag reference |
| [CAMP_MUSIC_INJECTION_PLAN.md](CAMP_MUSIC_INJECTION_PLAN.md) | UE 4.26.2 Zen/IoStore binary format & architecture reference |
| [LICENSE](LICENSE) | MIT License |

---

## Documentation

- **[User Guide & CLI Reference](HOW_TO_USE.md)** — Full walkthrough of GUI features, batch naming conventions (`*_off`, `*_muffled`, `*_ambient`), and all command-line flags.
- **[Technical Architecture & Binary Reference](CAMP_MUSIC_INJECTION_PLAN.md)** — Exact UE 4.26.2 `.utoc`/`.ucas`/`.pak`, `USoundWave`, `UConstantQNRT`, and catalog details for all 34 base-game tracks.

---

## Disclaimer

This is an unofficial community modding tool for *Stellar Blade* and is not affiliated with or endorsed by SHIFT UP or Sony Interactive Entertainment. Use only audio and artwork you have the rights to use locally.

## License

Licensed under the [MIT License](LICENSE).
