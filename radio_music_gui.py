#!/usr/bin/env python3
"""
Stellar Blade Camp Radio & Shuffle Mod Builder — Native Windows Win32 GUI
=========================================================================
Dedicated Win32 GUI for building pre-shuffled Camp Radio stations from folders
(e.g. Music/PopRadio/). Each station folder is combined into one or more
pre-shuffled single-stream Ogg Vorbis tracks with custom cover art, configurable
silence gaps, and automatic/manual UConstantQNRT visualizer disabling.
"""

import ctypes
from ctypes import wintypes
import dataclasses
import json
import os
import pathlib
import shutil
import sys
import threading
from typing import List, Optional

import inject_camp_music as icm
from gui_common import (
    BaseWin32App,
    BM_SETCHECK,
    BN_CLICKED,
    BS_AUTOCHECKBOX,
    BS_DEFPUSHBUTTON,
    BS_GROUPBOX,
    BS_PUSHBUTTON,
    BST_CHECKED,
    BST_UNCHECKED,
    CB_ADDSTRING,
    CB_GETCURSEL,
    CB_SETCURSEL,
    CBN_SELCHANGE,
    CBS_DROPDOWNLIST,
    CBS_HASSTRINGS,
    EN_CHANGE,
    ES_AUTOHSCROLL,
    ES_AUTOVSCROLL,
    ES_MULTILINE,
    ES_READONLY,
    LB_ADDSTRING,
    LB_DELETESTRING,
    LB_GETCURSEL,
    LB_INSERTSTRING,
    LB_RESETCONTENT,
    LB_SETCURSEL,
    LBN_DBLCLK,
    LBN_SELCHANGE,
    LBS_NOINTEGRALHEIGHT,
    LBS_NOTIFY,
    MB_ICONERROR,
    MB_ICONINFORMATION,
    MB_ICONWARNING,
    MB_OK,
    SS_LEFT,
    WS_BORDER,
    WS_EX_ACCEPTFILES,
    WS_EX_CLIENTEDGE,
    WS_EX_CONTROLPARENT,
    WS_OVERLAPPEDWINDOW_FIXED,
    WS_TABSTOP,
    WS_VSCROLL,
    copy_text_to_clipboard,
    detect_stellar_blade_game_dir,
    shell32,
    user32,
)

# Control Identifiers
IDC_LIST_STATIONS = 2001
IDC_BTN_ADD_RADIO = 2002
IDC_BTN_LOAD_MUSIC_SUBS = 2003
IDC_BTN_MOVE_UP = 2004
IDC_BTN_MOVE_DOWN = 2005
IDC_BTN_REMOVE_STATION = 2006
IDC_BTN_CLEAR_STATIONS = 2007
IDC_BTN_RESCAN = 2008
IDC_LBL_STATION_STATUS = 2009
IDC_LBL_STATION_SONGS = 2010
IDC_COMBO_INCLUDE_SONGS = 2011

IDC_EDIT_TITLE = 2020
IDC_BTN_RESET_TITLE = 2021
IDC_EDIT_VARIANTS = 2022
IDC_EDIT_SILENCE = 2023
IDC_COMBO_VIS = 2024
IDC_COMBO_COVER = 2025
IDC_BTN_BROWSE_COVER = 2026
IDC_BTN_CLEAR_COVER = 2027
IDC_CHK_FIRST_SONG_ART = 2028
IDC_EDIT_VOL_ON = 2029
IDC_EDIT_VOL_OFF = 2030
IDC_BTN_VOL_DEFAULT = 2031
IDC_BTN_VOL_QUIET = 2032
IDC_BTN_VOL_BOOST = 2033
IDC_LBL_COVER_STATUS = 2034

IDC_EDIT_GAME_DIR = 2040
IDC_BTN_BROWSE_GAME = 2041
IDC_BTN_AUTO_DETECT_GAME = 2042
IDC_LBL_GAME_STATUS = 2043
IDC_EDIT_MOD_NAME = 2044
IDC_CHK_INSTALL = 2045
IDC_LBL_MODS_STATUS = 2046
IDC_EDIT_OUT_DIR = 2047
IDC_BTN_BROWSE_OUT = 2048

IDC_BTN_BUILD = 2050
IDC_BTN_OPEN_MODS = 2051
IDC_BTN_OPEN_GAME = 2052
IDC_BTN_OPEN_OUT = 2053
IDC_BTN_RESET_ALL = 2054
IDC_LBL_BUILD_STATUS = 2055

IDC_BTN_COPY_LOG = 2060
IDC_BTN_CLEAR_LOG = 2061
IDC_EDIT_LOG = 2062
IDC_LBL_DRAG_HINT = 2070

VISUALIZER_CHOICES = [
    ("Auto (Off > 20 min)", "auto"),
    ("Always On (Full CQT)", "on"),
    ("Always Off (Saves Space)", "off"),
]


@dataclasses.dataclass
class RadioStationItem:
    station_dir: pathlib.Path
    title: str
    variants: int = 3
    silence_sec: float = 0.5
    visualizer_idx: int = 0
    cover_idx: int = 0
    custom_cover_path: Optional[pathlib.Path] = None
    songs: List[pathlib.Path] = dataclasses.field(default_factory=list)
    folder_cover_path: Optional[pathlib.Path] = None
    first_song_has_art: bool = False
    est_duration_sec: Optional[float] = None
    songs_summary: str = ""
    meta_color: int = 0x555555


def load_saved_custom_playlist_entries(cache_dir: pathlib.Path) -> List[dict]:
    """Read valid entries from the per-song GUI's `.cache/gui_settings.json`."""
    cfg = cache_dir / "gui_settings.json"
    if not cfg.is_file():
        return []
    try:
        data = json.loads(cfg.read_text(encoding="utf-8"))
        pl = data.get("playlist")
        if not isinstance(pl, list):
            return []
        valid: List[dict] = []
        for entry in pl:
            if isinstance(entry, dict) and entry.get("audio_on") and pathlib.Path(str(entry["audio_on"])).is_file():
                valid.append(entry)
        return valid
    except Exception:
        return []


def prepare_extra_custom_tracks(
    mode: str,
    root_dir: pathlib.Path,
    cache_dir: pathlib.Path,
    vol_on: float,
    vol_off: float,
    use_embedded_art: bool = True,
    progress_callback=None,
) -> List[icm.CustomTrackInput]:
    """Prepare individual custom tracks from `./Music` or the saved Custom GUI playlist."""
    if mode == "music":
        music_dir = root_dir / "Music"
        if not music_dir.is_dir() or not icm.scan_music_folder(music_dir):
            return []
        return icm.prepare_custom_tracks_from_folder(
            music_dir=music_dir,
            volume_on=vol_on,
            volume_off=vol_off,
            use_embedded_art=use_embedded_art,
            progress_callback=lambda idx, tot, p, title: progress_callback(
                f"[Song {idx}/{tot}] Encoding/preparing {title!r}..."
            ) if progress_callback else None,
        )

    if mode == "gui_playlist":
        entries = load_saved_custom_playlist_entries(cache_dir)
        tracks: List[icm.CustomTrackInput] = []
        total = len(entries)
        for idx, entry in enumerate(entries, start=1):
            on_p = pathlib.Path(str(entry["audio_on"]))
            title = str(entry.get("title") or "").strip() or icm.infer_song_title(on_p)
            if progress_callback:
                progress_callback(f"[Song {idx}/{total}] Encoding/preparing {title!r}...")
            off_raw = entry.get("audio_off")
            off_p = pathlib.Path(str(off_raw)) if off_raw else None
            if off_p and not off_p.is_file():
                off_p = None
            cov_raw = entry.get("custom_cover_path")
            cov_p = pathlib.Path(str(cov_raw)) if cov_raw else None
            if cov_p and not cov_p.is_file():
                cov_p = None
            cidx = int(entry.get("cover_idx", 0))
            if not (0 <= cidx < len(icm.ALBUM_COVER_PRESETS)):
                cidx = 0
            img_path, cover_bgra, cover_lbl = icm.resolve_track_cover_art(
                audio_path=on_p,
                fallback_image_path=icm.ALBUM_COVER_PRESETS[cidx][1],
                custom_image_file=cov_p,
                use_embedded=use_embedded_art,
            )
            ogg_on = icm.load_or_convert_ogg(on_p)
            ogg_off = icm.load_or_convert_ogg(off_p) if off_p else ogg_on
            tracks.append(
                icm.CustomTrackInput(
                    title=title,
                    ogg_on=ogg_on,
                    ogg_off=ogg_off,
                    volume_on=vol_on,
                    volume_off=vol_off,
                    image_path=img_path,
                    cover_bgra=cover_bgra,
                    cover_label=cover_lbl,
                )
            )
        return tracks

    return []


class RadioMusicWin32GUI(BaseWin32App):
    class_name = "StellarBladeCampRadioGUI"
    default_mod_name = "CampMusic_Radio_295_P"

    def __init__(self) -> None:
        super().__init__("radio_gui_settings.json")
        self._log_ctrl_id = IDC_EDIT_LOG
        self._suppress_editor_sync = False
        self.stations: List[RadioStationItem] = []
        self._create_main_window()

    def _save_settings(self) -> None:
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            serialized = [
                {
                    "station_dir": str(st.station_dir),
                    "title": st.title,
                    "variants": st.variants,
                    "silence_sec": st.silence_sec,
                    "visualizer_idx": st.visualizer_idx,
                    "cover_idx": st.cover_idx,
                    "custom_cover_path": str(st.custom_cover_path) if st.custom_cover_path else None,
                }
                for st in self.stations
            ]
            data = {
                "game_dir": self._get_text(IDC_EDIT_GAME_DIR).strip(),
                "out_dir": self._get_text(IDC_EDIT_OUT_DIR).strip(),
                "mod_name": self._get_text(IDC_EDIT_MOD_NAME).strip() or self.default_mod_name,
                "install_to_game": self._is_checked(IDC_CHK_INSTALL),
                "vol_on": self._get_text(IDC_EDIT_VOL_ON).strip(),
                "vol_off": self._get_text(IDC_EDIT_VOL_OFF).strip(),
                "use_first_song_art": self._is_checked(IDC_CHK_FIRST_SONG_ART),
                "include_custom_mode": self._get_include_mode(),
                "stations": serialized,
            }
            self.settings_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _create_main_window(self) -> None:
        width, height = 880, 916
        screen_w = user32.GetSystemMetrics(0)
        screen_h = user32.GetSystemMetrics(1)
        pos_x = max(0, (screen_w - width) // 2)
        pos_y = max(0, (screen_h - height) // 2)

        self.hwnd = user32.CreateWindowExW(
            WS_EX_CONTROLPARENT | WS_EX_ACCEPTFILES,
            self.class_name,
            "Stellar Blade — Camp Radio & Shuffle Mod Builder",
            WS_OVERLAPPEDWINDOW_FIXED,
            pos_x,
            pos_y,
            width,
            height,
            None,
            None,
            self.hinst,
            None,
        )

        shell32.DragAcceptFiles(self.hwnd, 1)

        # Header
        self._add_ctrl("STATIC", "Stellar Blade — Camp Radio & Shuffle Mod Builder", SS_LEFT, 18, 12, 740, 26, font=self.font_title)
        self._add_ctrl(
            "STATIC",
            "Combine each radio folder (e.g. Music/PopRadio) into pre-shuffled camp radio tracks while keeping all 34 original tracks intact.",
            SS_LEFT,
            18, 38, 840, 18,
        )
        self.lbl_drag_hint = self._add_ctrl(
            "STATIC",
            "Tip: Drag & drop radio folders (e.g. Music/PopRadio), ./Music parent folder, a cover image, or your Stellar Blade folder here!",
            SS_LEFT,
            18, 58, 840, 18,
            IDC_LBL_DRAG_HINT,
            font=self.font_bold,
        )
        self.ctrl_colors[IDC_LBL_DRAG_HINT] = self.color_blue

        # ====================================================================
        # 1. Radio Stations List Group
        # ====================================================================
        self._add_ctrl(
            "BUTTON",
            " 1. Radio Station Folders (Each Folder -> Shuffled Radio Mix Variants) ",
            BS_GROUPBOX,
            14, 80, 840, 276,
            font=self.font_bold,
        )

        self._add_ctrl(
            "LISTBOX",
            "",
            LBS_NOTIFY | LBS_NOINTEGRALHEIGHT | WS_VSCROLL | WS_BORDER | WS_TABSTOP,
            26, 104, 578, 200,
            IDC_LIST_STATIONS,
            WS_EX_CLIENTEDGE,
            font=self.font_mono,
        )

        self._add_ctrl("BUTTON", "Add Radio Folder...", BS_PUSHBUTTON | WS_TABSTOP, 614, 104, 226, 28, IDC_BTN_ADD_RADIO, font=self.font_bold)
        self._add_ctrl("BUTTON", "Load ./Music Subfolders", BS_PUSHBUTTON | WS_TABSTOP, 614, 136, 226, 26, IDC_BTN_LOAD_MUSIC_SUBS)
        self._add_ctrl("BUTTON", "Move Up", BS_PUSHBUTTON | WS_TABSTOP, 614, 168, 110, 26, IDC_BTN_MOVE_UP)
        self._add_ctrl("BUTTON", "Move Down", BS_PUSHBUTTON | WS_TABSTOP, 730, 168, 110, 26, IDC_BTN_MOVE_DOWN)
        self._add_ctrl("BUTTON", "Remove", BS_PUSHBUTTON | WS_TABSTOP, 614, 198, 110, 26, IDC_BTN_REMOVE_STATION)
        self._add_ctrl("BUTTON", "Clear All", BS_PUSHBUTTON | WS_TABSTOP, 730, 198, 110, 26, IDC_BTN_CLEAR_STATIONS)
        self._add_ctrl("BUTTON", "Rescan Selected Folder", BS_PUSHBUTTON | WS_TABSTOP, 614, 230, 226, 28, IDC_BTN_RESCAN)
        self._add_ctrl("STATIC", "Also Include Custom Songs:", SS_LEFT, 614, 262, 226, 16, font=self.font_small)
        combo_inc = self._add_ctrl(
            "COMBOBOX",
            "",
            CBS_DROPDOWNLIST | CBS_HASSTRINGS | WS_VSCROLL | WS_TABSTOP,
            614, 279, 226, 140,
            IDC_COMBO_INCLUDE_SONGS,
        )
        self._populate_include_combo(combo_inc)

        self.lbl_station_status = self._add_ctrl(
            "STATIC",
            "0 radio station(s) queued — all 34 original tracks will remain intact.",
            SS_LEFT,
            26, 310, 814, 18,
            IDC_LBL_STATION_STATUS,
            font=self.font_bold,
        )
        self.lbl_station_songs = self._add_ctrl(
            "STATIC",
            "Add a radio folder (e.g. Music/PopRadio) or drop folders onto this window.",
            SS_LEFT,
            26, 330, 814, 18,
            IDC_LBL_STATION_SONGS,
        )

        # ====================================================================
        # 2. Selected Station & Radio Options Group
        # ====================================================================
        self._add_ctrl(
            "BUTTON",
            " 2. Selected Station Shuffle, Cover & Visualizer Settings ",
            BS_GROUPBOX,
            14, 362, 840, 172,
            font=self.font_bold,
        )

        self._add_ctrl("STATIC", "Station Title:", SS_LEFT, 26, 386, 115, 18)
        self._add_ctrl("EDIT", "", ES_AUTOHSCROLL | WS_TABSTOP, 145, 383, 560, 23, IDC_EDIT_TITLE, WS_EX_CLIENTEDGE)
        self._add_ctrl("BUTTON", "Auto-Detect", BS_PUSHBUTTON | WS_TABSTOP, 712, 382, 128, 25, IDC_BTN_RESET_TITLE)

        self._add_ctrl("STATIC", "Shuffled Variants:", SS_LEFT, 26, 416, 115, 18)
        self._add_ctrl("EDIT", "3", ES_AUTOHSCROLL | WS_TABSTOP, 145, 413, 55, 23, IDC_EDIT_VARIANTS, WS_EX_CLIENTEDGE)

        self._add_ctrl("STATIC", "Silence Gap (sec):", SS_LEFT, 214, 416, 115, 18)
        self._add_ctrl("EDIT", "0.5", ES_AUTOHSCROLL | WS_TABSTOP, 332, 413, 55, 23, IDC_EDIT_SILENCE, WS_EX_CLIENTEDGE)

        self._add_ctrl("STATIC", "Visualizer:", SS_LEFT, 405, 416, 68, 18)
        combo_vis = self._add_ctrl(
            "COMBOBOX",
            "",
            CBS_DROPDOWNLIST | CBS_HASSTRINGS | WS_VSCROLL | WS_TABSTOP,
            478, 413, 210, 180,
            IDC_COMBO_VIS,
        )
        for vis_label, _ in VISUALIZER_CHOICES:
            buf = ctypes.create_unicode_buffer(vis_label)
            user32.SendMessageW(combo_vis, CB_ADDSTRING, 0, ctypes.addressof(buf))
        user32.SendMessageW(combo_vis, CB_SETCURSEL, 0, 0)

        self._add_ctrl("STATIC", "(1..20 mixes)", SS_LEFT, 696, 416, 140, 18, font=self.font_small)

        self._add_ctrl("STATIC", "Station Cover:", SS_LEFT, 26, 446, 115, 18)
        combo_cover = self._add_ctrl(
            "COMBOBOX",
            "",
            CBS_DROPDOWNLIST | CBS_HASSTRINGS | WS_VSCROLL | WS_TABSTOP,
            145, 443, 220, 240,
            IDC_COMBO_COVER,
        )
        for label, _ in icm.ALBUM_COVER_PRESETS:
            buf = ctypes.create_unicode_buffer(label)
            user32.SendMessageW(combo_cover, CB_ADDSTRING, 0, ctypes.addressof(buf))
        user32.SendMessageW(combo_cover, CB_SETCURSEL, 0, 0)
        self._add_ctrl("BUTTON", "Custom Img...", BS_PUSHBUTTON | WS_TABSTOP, 372, 442, 102, 25, IDC_BTN_BROWSE_COVER)
        self._add_ctrl("BUTTON", "Clear Img", BS_PUSHBUTTON | WS_TABSTOP, 480, 442, 82, 25, IDC_BTN_CLEAR_COVER)
        self._add_ctrl(
            "BUTTON",
            "Fallback to 1st Song Art",
            BS_AUTOCHECKBOX | WS_TABSTOP,
            574, 445, 266, 20,
            IDC_CHK_FIRST_SONG_ART,
        )
        if self.settings.get("use_first_song_art", True):
            user32.SendMessageW(self.controls[IDC_CHK_FIRST_SONG_ART], BM_SETCHECK, BST_CHECKED, 0)

        self._add_ctrl("STATIC", "Turntable Vol:", SS_LEFT, 26, 478, 84, 18)
        vol_on_val = str(self.settings.get("vol_on", "1.1"))
        self._add_ctrl("EDIT", vol_on_val, ES_AUTOHSCROLL | WS_TABSTOP, 114, 475, 48, 22, IDC_EDIT_VOL_ON, WS_EX_CLIENTEDGE)

        self._add_ctrl("STATIC", "Ambient Vol:", SS_LEFT, 174, 478, 78, 18)
        vol_off_val = str(self.settings.get("vol_off", "0.6"))
        self._add_ctrl("EDIT", vol_off_val, ES_AUTOHSCROLL | WS_TABSTOP, 256, 475, 48, 22, IDC_EDIT_VOL_OFF, WS_EX_CLIENTEDGE)

        self._add_ctrl("BUTTON", "Default (1.1 / 0.6)", BS_PUSHBUTTON | WS_TABSTOP, 318, 474, 116, 24, IDC_BTN_VOL_DEFAULT)
        self._add_ctrl("BUTTON", "Quiet (0.5 / 0.2)", BS_PUSHBUTTON | WS_TABSTOP, 440, 474, 110, 24, IDC_BTN_VOL_QUIET)
        self._add_ctrl("BUTTON", "Boosted (1.3 / 0.8)", BS_PUSHBUTTON | WS_TABSTOP, 556, 474, 118, 24, IDC_BTN_VOL_BOOST)

        self.lbl_cover_status = self._add_ctrl(
            "STATIC",
            "Cover priority: Custom Img > Image in Radio Folder > 1st Song Embedded Art > Preset Fallback",
            SS_LEFT,
            26, 508, 814, 16,
            IDC_LBL_COVER_STATUS,
            font=self.font_small,
        )

        # ====================================================================
        # 3. Game Folder & Mod Output Group
        # ====================================================================
        self._add_ctrl("BUTTON", " 3. Game Folder & Output Installation ", BS_GROUPBOX, 14, 540, 840, 148, font=self.font_bold)

        self._add_ctrl("STATIC", "Stellar Blade Dir:", SS_LEFT, 26, 564, 115, 18)
        self._add_ctrl(
            "EDIT", str(self.default_game_dir), ES_AUTOHSCROLL | WS_TABSTOP,
            145, 561, 475, 23, IDC_EDIT_GAME_DIR, WS_EX_CLIENTEDGE
        )
        self._add_ctrl("BUTTON", "Browse...", BS_PUSHBUTTON | WS_TABSTOP, 628, 560, 72, 25, IDC_BTN_BROWSE_GAME)
        self._add_ctrl("BUTTON", "Auto-Detect Game", BS_PUSHBUTTON | WS_TABSTOP, 706, 560, 134, 25, IDC_BTN_AUTO_DETECT_GAME)

        self.lbl_game_status = self._add_ctrl("STATIC", "", SS_LEFT, 145, 587, 695, 18, IDC_LBL_GAME_STATUS)

        self._add_ctrl("STATIC", "Mod Name (_P):", SS_LEFT, 26, 611, 115, 18)
        saved_mod = str(self.settings.get("mod_name", self.default_mod_name))
        self._add_ctrl("EDIT", saved_mod, ES_AUTOHSCROLL | WS_TABSTOP, 145, 608, 230, 23, IDC_EDIT_MOD_NAME, WS_EX_CLIENTEDGE)

        self._add_ctrl(
            "BUTTON",
            "Install directly into ~mods",
            BS_AUTOCHECKBOX | WS_TABSTOP,
            385, 610, 175, 20,
            IDC_CHK_INSTALL,
        )
        install_chk = self.settings.get("install_to_game", True)
        user32.SendMessageW(self.controls[IDC_CHK_INSTALL], BM_SETCHECK, BST_CHECKED if install_chk else BST_UNCHECKED, 0)

        self.lbl_mods_status = self._add_ctrl("STATIC", "", SS_LEFT, 566, 611, 274, 18, IDC_LBL_MODS_STATUS)

        self._add_ctrl("STATIC", "Output Folder (dist):", SS_LEFT, 26, 642, 115, 18)
        self._add_ctrl(
            "EDIT", str(self.default_out_dir), ES_AUTOHSCROLL | WS_TABSTOP,
            145, 639, 601, 23, IDC_EDIT_OUT_DIR, WS_EX_CLIENTEDGE
        )
        self._add_ctrl("BUTTON", "Browse...", BS_PUSHBUTTON | WS_TABSTOP, 752, 638, 88, 25, IDC_BTN_BROWSE_OUT)

        # ====================================================================
        # 4. Actions & Build Feedback
        # ====================================================================
        self._add_ctrl("BUTTON", "Build Camp Radio Mod", BS_DEFPUSHBUTTON | WS_TABSTOP, 14, 696, 220, 36, IDC_BTN_BUILD, font=self.font_bold)
        self._add_ctrl("BUTTON", "Open ~mods", BS_PUSHBUTTON | WS_TABSTOP, 240, 696, 105, 36, IDC_BTN_OPEN_MODS)
        self._add_ctrl("BUTTON", "Open Game Folder", BS_PUSHBUTTON | WS_TABSTOP, 351, 696, 125, 36, IDC_BTN_OPEN_GAME)
        self._add_ctrl("BUTTON", "Open Output", BS_PUSHBUTTON | WS_TABSTOP, 482, 696, 100, 36, IDC_BTN_OPEN_OUT)
        self._add_ctrl("BUTTON", "Reset", BS_PUSHBUTTON | WS_TABSTOP, 588, 696, 65, 36, IDC_BTN_RESET_ALL)

        self.lbl_build_status = self._add_ctrl(
            "STATIC", "Ready. Add radio folders and click 'Build Camp Radio Mod'.",
            SS_LEFT, 660, 701, 195, 30, IDC_LBL_BUILD_STATUS, font=self.font_bold
        )

        # ====================================================================
        # 5. Activity Log
        # ====================================================================
        self._add_ctrl("STATIC", "Activity Log:", SS_LEFT, 16, 740, 100, 18, font=self.font_bold)
        self._add_ctrl("BUTTON", "Copy Log", BS_PUSHBUTTON | WS_TABSTOP, 688, 737, 76, 22, IDC_BTN_COPY_LOG)
        self._add_ctrl("BUTTON", "Clear Log", BS_PUSHBUTTON | WS_TABSTOP, 770, 737, 76, 22, IDC_BTN_CLEAR_LOG)

        self._add_ctrl(
            "EDIT",
            "",
            ES_MULTILINE | ES_AUTOVSCROLL | ES_READONLY | WS_VSCROLL,
            14, 762, 840, 108,
            IDC_EDIT_LOG,
            WS_EX_CLIENTEDGE,
            font=self.font_mono,
        )

        # Initialize state
        self._update_game_status()
        self._update_install_state()
        self._restore_or_load_initial_stations()

        self._log("Stellar Blade Camp Radio & Shuffle Mod Builder initialized.")
        if not shutil.which("ffmpeg"):
            self._log("[WARNING] 'ffmpeg' was not found on PATH. Install FFmpeg to build combined radio mixes.")
        if self.default_game_dir.is_dir():
            self._log(f"Stellar Blade game directory: {self.default_game_dir}")
        self._log("All 34 original in-game Camp Turntable songs are always preserved.")

        user32.SetTimer(self.hwnd, 101, 80, None)
        self._ready = True

    # ========================================================================
    # Radio Station Inspection & List Management
    # ========================================================================

    def _inspect_station(self, st: RadioStationItem) -> None:
        if not st.station_dir.is_dir():
            st.songs = []
            st.folder_cover_path = None
            st.first_song_has_art = False
            st.est_duration_sec = None
            st.songs_summary = f"[Missing] Folder not found: {st.station_dir}"
            st.meta_color = self.color_red
            return

        songs, folder_cover = icm.scan_radio_folder(st.station_dir)
        st.songs = songs
        st.folder_cover_path = folder_cover
        st.first_song_has_art = bool(songs and icm.extract_embedded_cover_art(songs[0]))

        if not songs:
            st.est_duration_sec = None
            st.songs_summary = f"[Warning] No supported audio files found in {st.station_dir.name}"
            st.meta_color = self.color_red
            return

        total_ogg_sec = 0.0
        ogg_parsed = 0
        for s in songs:
            if s.suffix.lower() == ".ogg":
                try:
                    _, _, dur = icm.probe_ogg_duration(s)
                    total_ogg_sec += dur
                    ogg_parsed += 1
                except Exception:
                    pass

        gap_total = max(0.0, st.silence_sec) * max(0, len(songs) - 1)
        if ogg_parsed == len(songs):
            est = total_ogg_sec + gap_total
            st.est_duration_sec = est
            mins = int(est // 60)
            secs = int(est % 60)
            vis_mode = VISUALIZER_CHOICES[st.visualizer_idx][1]
            vis_note = "Vis OFF (>20m)" if icm.should_disable_visualizer(est, vis_mode) else "Vis ON"
            preview_names = ", ".join(p.stem for p in songs[:4])
            if len(songs) > 4:
                preview_names += f", +{len(songs) - 4} more"
            st.songs_summary = f"[OK] {len(songs)} songs (~{mins}m {secs:02d}s/mix, {vis_note}): {preview_names}"
            st.meta_color = self.color_green
        else:
            st.est_duration_sec = None
            preview_names = ", ".join(p.stem for p in songs[:4])
            if len(songs) > 4:
                preview_names += f", +{len(songs) - 4} more"
            st.songs_summary = f"[Ready] {len(songs)} audio files (FFmpeg mix): {preview_names}"
            st.meta_color = self.color_blue

    def _describe_station_cover(self, st: Optional[RadioStationItem]) -> str:
        if st is None:
            return "Cover priority: Custom Img > Image in Radio Folder > 1st Song Embedded Art > Preset Fallback"
        if st.custom_cover_path and st.custom_cover_path.is_file():
            return f"Cover Art: Custom image '{st.custom_cover_path.name}' (256x256 UTexture2D)"
        if st.folder_cover_path and st.folder_cover_path.is_file():
            return f"Cover Art: Folder image '{st.folder_cover_path.name}' (256x256 UTexture2D)"
        if st.first_song_has_art and self._is_checked(IDC_CHK_FIRST_SONG_ART):
            return f"Cover Art: 1st song embedded art ({st.songs[0].name})"
        preset_label = icm.ALBUM_COVER_PRESETS[st.cover_idx][0]
        return f"Cover Art: Preset '{preset_label}' (no folder image or 1st song art)"

    def _format_station_label(self, idx_1based: int, st: RadioStationItem) -> str:
        n_songs = len(st.songs)
        vis_short = ("Auto", "On", "Off")[st.visualizer_idx]
        if st.custom_cover_path and st.custom_cover_path.is_file():
            cov = st.custom_cover_path.name
        elif st.folder_cover_path and st.folder_cover_path.is_file():
            cov = st.folder_cover_path.name
        elif st.first_song_has_art and self._is_checked(IDC_CHK_FIRST_SONG_ART):
            cov = "1st Song"
        else:
            cov = "Preset"
        return f"[{idx_1based:02d}] {st.title} | {n_songs} songs | {st.variants}x | Gap {st.silence_sec:.1f}s | Vis:{vis_short} | Img:{cov}"

    def _refresh_stations_box(self, select_idx: Optional[int] = None) -> None:
        lb = self.controls[IDC_LIST_STATIONS]
        if select_idx is None:
            select_idx = int(user32.SendMessageW(lb, LB_GETCURSEL, 0, 0))
        user32.SendMessageW(lb, LB_RESETCONTENT, 0, 0)
        for i, st in enumerate(self.stations, start=1):
            buf = ctypes.create_unicode_buffer(self._format_station_label(i, st))
            user32.SendMessageW(lb, LB_ADDSTRING, 0, ctypes.addressof(buf))

        if self.stations:
            if select_idx < 0 or select_idx >= len(self.stations):
                select_idx = 0
            user32.SendMessageW(lb, LB_SETCURSEL, select_idx, 0)
        else:
            select_idx = -1

        total_tracks = sum(max(1, st.variants) for st in self.stations)
        extra_cnt = self._get_include_count()
        extra_part = f" + {extra_cnt} individual song(s)" if extra_cnt > 0 else ""
        self._set_text(
            self.lbl_station_status,
            f"{len(self.stations)} radio station(s) ({total_tracks} mix(es)){extra_part} — all 34 original tracks preserved.",
        )
        self._load_selected_into_editors(select_idx)

    def _populate_include_combo(self, combo_hwnd: wintypes.HWND) -> None:
        music_dir = self.root_dir / "Music"
        music_cnt = len(icm.scan_music_folder(music_dir)) if music_dir.is_dir() else 0
        gui_cnt = len(load_saved_custom_playlist_entries(self.cache_dir))
        self._include_options = [
            ("none", "None (Radio + 34 Default)", 0),
            ("music", f"./Music Folder ({music_cnt} songs)", music_cnt),
            ("gui_playlist", f"Custom GUI Playlist ({gui_cnt} songs)", gui_cnt),
        ]
        for _, label, _ in self._include_options:
            buf = ctypes.create_unicode_buffer(label)
            user32.SendMessageW(combo_hwnd, CB_ADDSTRING, 0, ctypes.addressof(buf))

        saved_mode = str(self.settings.get("include_custom_mode", "")).strip()
        sel_idx = 0
        if saved_mode in ("none", "music", "gui_playlist"):
            sel_idx = [m for m, _, _ in self._include_options].index(saved_mode)
        elif music_cnt > 0:
            sel_idx = 1
        elif gui_cnt > 0:
            sel_idx = 2
        user32.SendMessageW(combo_hwnd, CB_SETCURSEL, sel_idx, 0)

    def _get_include_mode(self) -> str:
        cidx = int(user32.SendMessageW(self.controls[IDC_COMBO_INCLUDE_SONGS], CB_GETCURSEL, 0, 0))
        if 0 <= cidx < len(getattr(self, "_include_options", [])):
            return self._include_options[cidx][0]
        return "none"

    def _get_include_count(self) -> int:
        cidx = int(user32.SendMessageW(self.controls[IDC_COMBO_INCLUDE_SONGS], CB_GETCURSEL, 0, 0))
        if 0 <= cidx < len(getattr(self, "_include_options", [])):
            return self._include_options[cidx][2]
        return 0

    def _get_selected_station_index(self) -> int:
        idx = int(user32.SendMessageW(self.controls[IDC_LIST_STATIONS], LB_GETCURSEL, 0, 0))
        return idx if 0 <= idx < len(self.stations) else -1

    def _load_selected_into_editors(self, idx: Optional[int] = None) -> None:
        if idx is None:
            idx = self._get_selected_station_index()
        self._suppress_editor_sync = True
        try:
            if 0 <= idx < len(self.stations):
                st = self.stations[idx]
                self._set_text(IDC_EDIT_TITLE, st.title)
                self._set_text(IDC_EDIT_VARIANTS, str(st.variants))
                self._set_text(IDC_EDIT_SILENCE, f"{st.silence_sec:g}")
                user32.SendMessageW(self.controls[IDC_COMBO_VIS], CB_SETCURSEL, st.visualizer_idx, 0)
                user32.SendMessageW(self.controls[IDC_COMBO_COVER], CB_SETCURSEL, st.cover_idx, 0)
                self._set_text(self.lbl_station_songs, st.songs_summary)
                self._set_text(self.lbl_cover_status, self._describe_station_cover(st))
                self.ctrl_colors[IDC_LBL_STATION_SONGS] = st.meta_color
                for cid in (
                    IDC_EDIT_TITLE, IDC_BTN_RESET_TITLE, IDC_EDIT_VARIANTS, IDC_EDIT_SILENCE,
                    IDC_COMBO_VIS, IDC_COMBO_COVER, IDC_BTN_BROWSE_COVER, IDC_BTN_RESCAN,
                ):
                    self._set_enabled(cid, True)
                self._set_enabled(IDC_BTN_CLEAR_COVER, bool(st.custom_cover_path))
            else:
                self._set_text(IDC_EDIT_TITLE, "")
                self._set_text(IDC_EDIT_VARIANTS, "3")
                self._set_text(IDC_EDIT_SILENCE, "0.5")
                user32.SendMessageW(self.controls[IDC_COMBO_VIS], CB_SETCURSEL, 0, 0)
                user32.SendMessageW(self.controls[IDC_COMBO_COVER], CB_SETCURSEL, 0, 0)
                self._set_text(self.lbl_station_songs, "Add a radio folder (e.g. Music/PopRadio) or drop folders onto this window.")
                self._set_text(self.lbl_cover_status, self._describe_station_cover(None))
                self.ctrl_colors[IDC_LBL_STATION_SONGS] = self.color_gray
                for cid in (
                    IDC_EDIT_TITLE, IDC_BTN_RESET_TITLE, IDC_EDIT_VARIANTS, IDC_EDIT_SILENCE,
                    IDC_COMBO_VIS, IDC_COMBO_COVER, IDC_BTN_BROWSE_COVER, IDC_BTN_CLEAR_COVER, IDC_BTN_RESCAN,
                ):
                    self._set_enabled(cid, False)
            user32.InvalidateRect(self.lbl_station_songs, None, 1)
        finally:
            self._suppress_editor_sync = False

    def _add_station_dirs(self, dirs: List[pathlib.Path]) -> int:
        added = 0
        existing = {st.station_dir.resolve() for st in self.stations if st.station_dir.exists()}
        for d in dirs:
            if not d.is_dir():
                continue
            rd = d.resolve()
            if rd in existing:
                continue
            songs = icm.scan_music_folder(rd)
            if not songs:
                continue
            st = RadioStationItem(
                station_dir=d,
                title=icm.clean_title_from_stem(d.name),
                variants=3,
                silence_sec=0.5,
                visualizer_idx=0,
                cover_idx=0,
            )
            self._inspect_station(st)
            self.stations.append(st)
            existing.add(rd)
            added += 1

        if added:
            self._refresh_stations_box(select_idx=len(self.stations) - 1)
        return added

    def _add_folder_or_subfolders(self, folder: pathlib.Path, show_warning: bool = True) -> int:
        if icm.scan_music_folder(folder):
            added = self._add_station_dirs([folder])
            if added:
                self._log(f"Added radio station folder: {folder.name}")
            return added

        subs = icm.discover_radio_station_dirs(folder)
        if subs:
            added = self._add_station_dirs(subs)
            self._log(f"Loaded {added} radio station subfolder(s) from: {folder}")
            return added

        if show_warning:
            user32.MessageBoxW(
                self.hwnd,
                f"No audio files or radio subfolders with audio were found in:\n\n{folder}",
                "No Radio Stations Found",
                MB_OK | MB_ICONINFORMATION,
            )
        return 0

    def _restore_or_load_initial_stations(self) -> None:
        saved = self.settings.get("stations")
        restored = 0
        if isinstance(saved, list):
            for entry in saved:
                if not isinstance(entry, dict):
                    continue
                sdir = pathlib.Path(str(entry.get("station_dir", "")))
                if not sdir.is_dir():
                    continue
                cov_raw = entry.get("custom_cover_path")
                cov_p = pathlib.Path(str(cov_raw)) if cov_raw else None
                if cov_p and not cov_p.is_file():
                    cov_p = None
                cidx = int(entry.get("cover_idx", 0))
                if not (0 <= cidx < len(icm.ALBUM_COVER_PRESETS)):
                    cidx = 0
                vidx = int(entry.get("visualizer_idx", 0))
                if not (0 <= vidx < len(VISUALIZER_CHOICES)):
                    vidx = 0
                variants = max(1, min(20, int(entry.get("variants", 3))))
                silence = max(0.0, float(entry.get("silence_sec", 0.5)))
                title = str(entry.get("title") or "").strip() or icm.clean_title_from_stem(sdir.name)
                st = RadioStationItem(
                    station_dir=sdir,
                    title=title,
                    variants=variants,
                    silence_sec=silence,
                    visualizer_idx=vidx,
                    cover_idx=cidx,
                    custom_cover_path=cov_p,
                )
                self._inspect_station(st)
                self.stations.append(st)
                restored += 1

        if restored == 0:
            music_dir = self.root_dir / "Music"
            subs = icm.discover_radio_station_dirs(music_dir)
            if subs:
                self._add_station_dirs(subs)
                return

        self._refresh_stations_box(select_idx=0 if self.stations else -1)

    def _update_selected_listbox_row(self, idx: int) -> None:
        lb = self.controls[IDC_LIST_STATIONS]
        user32.SendMessageW(lb, LB_DELETESTRING, idx, 0)
        buf = ctypes.create_unicode_buffer(self._format_station_label(idx + 1, self.stations[idx]))
        user32.SendMessageW(lb, LB_INSERTSTRING, idx, ctypes.addressof(buf))
        user32.SendMessageW(lb, LB_SETCURSEL, idx, 0)
        total_tracks = sum(max(1, st.variants) for st in self.stations)
        extra_cnt = self._get_include_count()
        extra_part = f" + {extra_cnt} individual song(s)" if extra_cnt > 0 else ""
        self._set_text(
            self.lbl_station_status,
            f"{len(self.stations)} radio station(s) ({total_tracks} mix(es)){extra_part} — all 34 original tracks preserved.",
        )

    def _sync_editor_changes(self, rescan: bool = False) -> None:
        if self._suppress_editor_sync:
            return
        idx = self._get_selected_station_index()
        if idx < 0:
            return
        st = self.stations[idx]
        st.title = self._get_text(IDC_EDIT_TITLE)
        try:
            v = int(self._get_text(IDC_EDIT_VARIANTS).strip())
            if 1 <= v <= 20:
                st.variants = v
        except ValueError:
            pass
        try:
            s = float(self._get_text(IDC_EDIT_SILENCE).strip())
            if s >= 0.0:
                st.silence_sec = s
        except ValueError:
            pass
        if rescan:
            self._inspect_station(st)
            self._set_text(self.lbl_station_songs, st.songs_summary)
            self.ctrl_colors[IDC_LBL_STATION_SONGS] = st.meta_color
            user32.InvalidateRect(self.lbl_station_songs, None, 1)
        self._update_selected_listbox_row(idx)

    # ========================================================================
    # Game Directory & Output Helpers
    # ========================================================================

    def _update_game_status(self) -> None:
        self._update_game_status_shared(IDC_EDIT_GAME_DIR, IDC_LBL_GAME_STATUS, IDC_LBL_MODS_STATUS, IDC_EDIT_MOD_NAME)

    def _update_mods_status(self) -> None:
        self._update_mods_status_shared(IDC_EDIT_GAME_DIR, IDC_LBL_MODS_STATUS, IDC_EDIT_MOD_NAME)

    def _update_install_state(self) -> None:
        installing = self._is_checked(IDC_CHK_INSTALL)
        self._set_enabled(IDC_EDIT_OUT_DIR, not installing)
        self._set_enabled(IDC_BTN_BROWSE_OUT, not installing)

    def _auto_detect_game_action(self) -> None:
        detected = detect_stellar_blade_game_dir(self.root_dir)
        if detected:
            self._set_text(IDC_EDIT_GAME_DIR, str(detected))
            self._update_game_status()
            self._log(f"Auto-detected Stellar Blade: {detected}")
            user32.MessageBoxW(
                self.hwnd,
                f"Stellar Blade folder detected successfully:\n\n{detected}",
                "Game Detected",
                MB_OK | MB_ICONINFORMATION,
            )
        else:
            user32.MessageBoxW(
                self.hwnd,
                "Could not automatically detect Stellar Blade installation.\nPlease click 'Browse...' and select your game directory.",
                "Game Detection",
                MB_OK | MB_ICONWARNING,
            )

    def _open_mods_folder_action(self) -> None:
        game_dir = pathlib.Path(self._get_text(IDC_EDIT_GAME_DIR).strip())
        if not self._validate_game_dir(game_dir):
            user32.MessageBoxW(self.hwnd, "Please select a valid Stellar Blade game folder first.", "Game Folder Not Found", MB_OK | MB_ICONWARNING)
            return
        mods_dir = game_dir / "SB" / "Content" / "Paks" / "~mods"
        mods_dir.mkdir(parents=True, exist_ok=True)
        os.startfile(str(mods_dir))

    def _open_game_folder_action(self) -> None:
        game_dir = pathlib.Path(self._get_text(IDC_EDIT_GAME_DIR).strip())
        if game_dir.is_dir():
            os.startfile(str(game_dir))
        else:
            user32.MessageBoxW(self.hwnd, "Game directory does not exist.", "Folder Not Found", MB_OK | MB_ICONWARNING)

    def _get_target_output_dir(self) -> pathlib.Path:
        if self._is_checked(IDC_CHK_INSTALL):
            return pathlib.Path(self._get_text(IDC_EDIT_GAME_DIR).strip()) / "SB" / "Content" / "Paks" / "~mods"
        return pathlib.Path(self._get_text(IDC_EDIT_OUT_DIR).strip())

    # ========================================================================
    # Drag & Drop and Commands
    # ========================================================================

    def _on_drop_files(self, hdrop: wintypes.HANDLE) -> None:
        count = shell32.DragQueryFileW(hdrop, 0xFFFFFFFF, None, 0)
        buf = ctypes.create_unicode_buffer(1024)
        dropped_images: List[pathlib.Path] = []

        for i in range(count):
            shell32.DragQueryFileW(hdrop, i, buf, 1024)
            path = pathlib.Path(buf.value)
            if path.is_file() and path.suffix.lower() in icm.SUPPORTED_IMAGE_EXTENSIONS:
                dropped_images.append(path)
            elif path.is_dir():
                if self._validate_game_dir(path):
                    self._set_text(IDC_EDIT_GAME_DIR, str(path))
                    self._update_game_status()
                    self._log(f"[Drag & Drop] Set Stellar Blade game directory: {path}")
                else:
                    self._add_folder_or_subfolders(path, show_warning=False)

        if dropped_images:
            idx = self._get_selected_station_index()
            if idx >= 0:
                self.stations[idx].custom_cover_path = dropped_images[0]
                self._refresh_stations_box(select_idx=idx)
                self._log(f"[Drag & Drop] Set custom cover for '{self.stations[idx].title}': {dropped_images[0].name}")

        shell32.DragFinish(hdrop)

    def _on_command(self, ctrl_id: int, notify_code: int) -> None:
        if ctrl_id == IDC_LIST_STATIONS and notify_code == LBN_SELCHANGE:
            self._load_selected_into_editors()

        elif ctrl_id == IDC_LIST_STATIONS and notify_code == LBN_DBLCLK:
            idx = self._get_selected_station_index()
            if idx >= 0 and self.stations[idx].station_dir.is_dir():
                os.startfile(str(self.stations[idx].station_dir))

        elif ctrl_id == IDC_BTN_ADD_RADIO and notify_code == BN_CLICKED:
            folder = self._ask_folder("Select Radio Station Folder (e.g. Music/PopRadio)")
            if folder:
                self._add_folder_or_subfolders(pathlib.Path(folder), show_warning=True)

        elif ctrl_id == IDC_BTN_LOAD_MUSIC_SUBS and notify_code == BN_CLICKED:
            music_dir = self.root_dir / "Music"
            music_dir.mkdir(parents=True, exist_ok=True)
            subs = icm.discover_radio_station_dirs(music_dir)
            if not subs:
                user32.MessageBoxW(
                    self.hwnd,
                    f"No radio station subfolders found in:\n\n{music_dir}\n\n"
                    "Create subfolders like Music\\PopRadio\\ with songs inside them, or click 'Add Radio Folder...'.",
                    "No Station Subfolders Found",
                    MB_OK | MB_ICONINFORMATION,
                )
            else:
                added = self._add_station_dirs(subs)
                self._log(f"Loaded {added} radio station subfolder(s) from ./Music.")

        elif ctrl_id == IDC_BTN_MOVE_UP and notify_code == BN_CLICKED:
            idx = self._get_selected_station_index()
            if idx > 0:
                self.stations[idx - 1], self.stations[idx] = self.stations[idx], self.stations[idx - 1]
                self._refresh_stations_box(select_idx=idx - 1)

        elif ctrl_id == IDC_BTN_MOVE_DOWN and notify_code == BN_CLICKED:
            idx = self._get_selected_station_index()
            if 0 <= idx < len(self.stations) - 1:
                self.stations[idx + 1], self.stations[idx] = self.stations[idx], self.stations[idx + 1]
                self._refresh_stations_box(select_idx=idx + 1)

        elif ctrl_id == IDC_BTN_REMOVE_STATION and notify_code == BN_CLICKED:
            idx = self._get_selected_station_index()
            if idx >= 0:
                removed = self.stations.pop(idx)
                self._log(f"Removed radio station: {removed.title}")
                self._refresh_stations_box(select_idx=min(idx, len(self.stations) - 1))

        elif ctrl_id == IDC_BTN_CLEAR_STATIONS and notify_code == BN_CLICKED:
            if self.stations:
                self.stations.clear()
                self._refresh_stations_box(select_idx=-1)
                self._log("Cleared all radio stations.")

        elif ctrl_id == IDC_BTN_RESCAN and notify_code == BN_CLICKED:
            idx = self._get_selected_station_index()
            if idx >= 0:
                self._inspect_station(self.stations[idx])
                self._refresh_stations_box(select_idx=idx)
                self._log(f"Rescanned '{self.stations[idx].title}': {len(self.stations[idx].songs)} song(s).")

        elif ctrl_id in (IDC_EDIT_TITLE, IDC_EDIT_VARIANTS) and notify_code == EN_CHANGE:
            self._sync_editor_changes(rescan=False)

        elif ctrl_id == IDC_EDIT_SILENCE and notify_code == EN_CHANGE:
            self._sync_editor_changes(rescan=True)

        elif ctrl_id == IDC_BTN_RESET_TITLE and notify_code == BN_CLICKED:
            idx = self._get_selected_station_index()
            if idx >= 0:
                self._set_text(IDC_EDIT_TITLE, icm.clean_title_from_stem(self.stations[idx].station_dir.name))

        elif ctrl_id == IDC_COMBO_INCLUDE_SONGS and notify_code == CBN_SELCHANGE:
            self._refresh_stations_box()

        elif ctrl_id == IDC_COMBO_VIS and notify_code == CBN_SELCHANGE:
            idx = self._get_selected_station_index()
            if idx >= 0:
                vidx = int(user32.SendMessageW(self.controls[IDC_COMBO_VIS], CB_GETCURSEL, 0, 0))
                if 0 <= vidx < len(VISUALIZER_CHOICES):
                    self.stations[idx].visualizer_idx = vidx
                    self._inspect_station(self.stations[idx])
                    self._refresh_stations_box(select_idx=idx)

        elif ctrl_id == IDC_COMBO_COVER and notify_code == CBN_SELCHANGE:
            idx = self._get_selected_station_index()
            if idx >= 0:
                cidx = int(user32.SendMessageW(self.controls[IDC_COMBO_COVER], CB_GETCURSEL, 0, 0))
                if 0 <= cidx < len(icm.ALBUM_COVER_PRESETS):
                    self.stations[idx].cover_idx = cidx
                    self._set_text(self.lbl_cover_status, self._describe_station_cover(self.stations[idx]))

        elif ctrl_id == IDC_BTN_BROWSE_COVER and notify_code == BN_CLICKED:
            idx = self._get_selected_station_index()
            if idx >= 0:
                files = self._ask_open_files(
                    "Select Custom Radio Station Cover Image",
                    "Image Files (*.png;*.jpg;*.jpeg;*.webp;*.bmp;*.tga)\0*.png;*.jpg;*.jpeg;*.webp;*.bmp;*.tga\0All Files (*.*)\0*.*\0\0",
                    multi=False,
                )
                if files:
                    self.stations[idx].custom_cover_path = files[0]
                    self._refresh_stations_box(select_idx=idx)
                    self._log(f"Set custom cover for '{self.stations[idx].title}': {files[0].name}")

        elif ctrl_id == IDC_BTN_CLEAR_COVER and notify_code == BN_CLICKED:
            idx = self._get_selected_station_index()
            if idx >= 0 and self.stations[idx].custom_cover_path is not None:
                self.stations[idx].custom_cover_path = None
                self._refresh_stations_box(select_idx=idx)

        elif ctrl_id == IDC_CHK_FIRST_SONG_ART and notify_code == BN_CLICKED:
            self._refresh_stations_box()

        elif ctrl_id == IDC_BTN_VOL_DEFAULT and notify_code == BN_CLICKED:
            self._set_text(IDC_EDIT_VOL_ON, "1.1")
            self._set_text(IDC_EDIT_VOL_OFF, "0.6")

        elif ctrl_id == IDC_BTN_VOL_QUIET and notify_code == BN_CLICKED:
            self._set_text(IDC_EDIT_VOL_ON, "0.5")
            self._set_text(IDC_EDIT_VOL_OFF, "0.2")

        elif ctrl_id == IDC_BTN_VOL_BOOST and notify_code == BN_CLICKED:
            self._set_text(IDC_EDIT_VOL_ON, "1.3")
            self._set_text(IDC_EDIT_VOL_OFF, "0.8")

        elif ctrl_id == IDC_BTN_BROWSE_GAME and notify_code == BN_CLICKED:
            folder = self._ask_folder("Select Stellar Blade Game Folder")
            if folder:
                self._set_text(IDC_EDIT_GAME_DIR, folder)
                self._update_game_status()

        elif ctrl_id == IDC_BTN_AUTO_DETECT_GAME and notify_code == BN_CLICKED:
            self._auto_detect_game_action()

        elif ctrl_id == IDC_EDIT_GAME_DIR and notify_code == EN_CHANGE:
            self._update_game_status()

        elif ctrl_id == IDC_EDIT_MOD_NAME and notify_code == EN_CHANGE:
            self._update_mods_status()

        elif ctrl_id == IDC_CHK_INSTALL and notify_code == BN_CLICKED:
            self._update_install_state()

        elif ctrl_id == IDC_BTN_OPEN_MODS and notify_code == BN_CLICKED:
            self._open_mods_folder_action()

        elif ctrl_id == IDC_BTN_OPEN_GAME and notify_code == BN_CLICKED:
            self._open_game_folder_action()

        elif ctrl_id == IDC_BTN_BROWSE_OUT and notify_code == BN_CLICKED:
            folder = self._ask_folder("Select Output Directory")
            if folder:
                self._set_text(IDC_EDIT_OUT_DIR, folder)

        elif ctrl_id == IDC_BTN_OPEN_OUT and notify_code == BN_CLICKED:
            if self._is_checked(IDC_CHK_INSTALL):
                self._open_mods_folder_action()
            else:
                out_dir = self._get_target_output_dir()
                out_dir.mkdir(parents=True, exist_ok=True)
                os.startfile(str(out_dir))

        elif ctrl_id == IDC_BTN_RESET_ALL and notify_code == BN_CLICKED:
            self.stations.clear()
            self._refresh_stations_box(select_idx=-1)
            self._set_text(IDC_EDIT_VOL_ON, "1.1")
            self._set_text(IDC_EDIT_VOL_OFF, "0.6")
            self._set_text(IDC_EDIT_MOD_NAME, self.default_mod_name)
            self._log("Reset radio stations and volume/mod settings to defaults.")

        elif ctrl_id == IDC_BTN_COPY_LOG and notify_code == BN_CLICKED:
            if copy_text_to_clipboard(self._get_text(IDC_EDIT_LOG)):
                self._log("[Log copied to Windows clipboard]")

        elif ctrl_id == IDC_BTN_CLEAR_LOG and notify_code == BN_CLICKED:
            self._set_text(IDC_EDIT_LOG, "")

        elif ctrl_id == IDC_BTN_BUILD and notify_code == BN_CLICKED:
            self._start_build()

    # ========================================================================
    # Build Mod Logic
    # ========================================================================

    def _start_build(self) -> None:
        if self.is_building:
            return

        include_mode = self._get_include_mode()
        extra_cnt = self._get_include_count()

        if not self.stations and extra_cnt == 0:
            user32.MessageBoxW(
                self.hwnd,
                "No radio station folders or individual custom songs are queued.\n\n"
                "Add a radio folder (e.g. Music/PopRadio) or select an individual custom songs source.",
                "Nothing Queued",
                MB_OK | MB_ICONWARNING,
            )
            return

        if self.stations and not shutil.which("ffmpeg"):
            user32.MessageBoxW(
                self.hwnd,
                "FFmpeg ('ffmpeg.exe') was not found on your system PATH.\n\n"
                "Combining and shuffling multiple tracks into a single Camp Radio Ogg stream requires FFmpeg.",
                "FFmpeg Not Found",
                MB_OK | MB_ICONERROR,
            )
            return

        try:
            vol_on = float(self._get_text(IDC_EDIT_VOL_ON).strip())
            vol_off = float(self._get_text(IDC_EDIT_VOL_OFF).strip())
        except ValueError:
            user32.MessageBoxW(
                self.hwnd,
                "Turntable Volume and Ambient Volume must be valid numbers (e.g. 1.1 and 0.6).",
                "Invalid Volume",
                MB_OK | MB_ICONERROR,
            )
            return

        install_to_game = self._is_checked(IDC_CHK_INSTALL)
        game_dir = pathlib.Path(self._get_text(IDC_EDIT_GAME_DIR).strip())
        if install_to_game and not self._validate_game_dir(game_dir):
            user32.MessageBoxW(
                self.hwnd,
                "Stellar Blade game installation folder is invalid or not found.\n\n"
                "Please configure a valid Stellar Blade folder or uncheck 'Install directly into ~mods'.",
                "Invalid Game Folder",
                MB_OK | MB_ICONWARNING,
            )
            return

        mod_name = self._get_text(IDC_EDIT_MOD_NAME).strip() or self.default_mod_name
        out_dir = self._get_target_output_dir()
        use_first_art = self._is_checked(IDC_CHK_FIRST_SONG_ART)

        station_specs = [
            icm.RadioStationInput(
                station_dir=st.station_dir,
                title=st.title.strip() or icm.clean_title_from_stem(st.station_dir.name),
                variants=max(1, min(20, int(st.variants))),
                silence_sec=max(0.0, float(st.silence_sec)),
                volume_on=vol_on,
                volume_off=vol_off,
                image_path=icm.ALBUM_COVER_PRESETS[st.cover_idx][1],
                custom_cover_file=st.custom_cover_path,
                use_first_song_art=use_first_art,
                visualizer_mode=VISUALIZER_CHOICES[st.visualizer_idx][1],
            )
            for st in self.stations
        ]

        total_radio = sum(s.variants for s in station_specs)
        total_tracks = total_radio + extra_cnt
        self.is_building = True
        self._set_enabled(IDC_BTN_BUILD, False)
        self._set_text(IDC_BTN_BUILD, "Building...")
        self._set_text(self.lbl_build_status, f"Building {total_tracks} track(s)...")
        self.ctrl_colors[IDC_LBL_BUILD_STATUS] = self.color_blue
        user32.InvalidateRect(self.lbl_build_status, None, 1)

        self._log("=" * 76)
        self._log(
            f"Building Combined Camp Mod ({extra_cnt} individual song(s) + {len(station_specs)} station(s)/{total_radio} mix(es) + 34 original tracks)..."
        )
        self._log(f"  Mod Name    : {mod_name}")
        self._log(f"  Destination : {out_dir}")
        self._log("-" * 76)

        def worker() -> None:
            try:
                def on_progress(msg: str) -> None:
                    self._log(msg)
                    self._set_text(self.lbl_build_status, msg[:48])

                extra_tracks = prepare_extra_custom_tracks(
                    mode=include_mode,
                    root_dir=self.root_dir,
                    cache_dir=self.cache_dir,
                    vol_on=vol_on,
                    vol_off=vol_off,
                    use_embedded_art=True,
                    progress_callback=on_progress,
                )

                built_radio, variant_logs, pak_p, utoc_p, ucas_p = icm.build_radio_mod(
                    stations=station_specs,
                    output_dir=out_dir,
                    mod_name=mod_name,
                    game_dir=game_dir if self._validate_game_dir(game_dir) else None,
                    template_ucas_path=icm.find_default_template_ucas(self.root_dir),
                    cache_dir=self.cache_dir,
                    extra_tracks=extra_tracks,
                    progress_callback=on_progress,
                )

                total_built = len(extra_tracks) + len(built_radio)
                self._log("=" * 76)
                self._log(f"SUCCESS! Added {total_built} custom track(s) (all 34 original tracks kept intact):")
                for idx, trk in enumerate(extra_tracks, start=1):
                    cov_note = f" | Cover: {trk.cover_label}" if trk.cover_label else ""
                    self._log(f"  [Song  {idx:02d}] {trk.title!r} ({trk.ogg_on.duration:.1f}s{cov_note})")
                for idx, (trk, (v_title, order)) in enumerate(zip(built_radio, variant_logs), start=1):
                    vis_note = "Vis: OFF" if trk.disable_visualizer else "Vis: ON"
                    cov_note = f" | Cover: {trk.cover_label}" if trk.cover_label else ""
                    self._log(f"  [Radio {idx:02d}] {v_title!r} ({trk.ogg_on.duration:.1f}s | {len(order)} songs | {vis_note}{cov_note})")
                    self._log(f"             Order: {' -> '.join(p.stem for p in order)}")
                self._log(f"  PAK  : {pak_p} ({pak_p.stat().st_size:,} bytes)")
                self._log(f"  UTOC : {utoc_p} ({utoc_p.stat().st_size:,} bytes)")
                self._log(f"  UCAS : {ucas_p} ({ucas_p.stat().st_size:,} bytes)")

                self._set_text(self.lbl_build_status, f"SUCCESS! {total_built} track(s) built.")
                self.ctrl_colors[IDC_LBL_BUILD_STATUS] = self.color_green
                user32.MessageBeep(0x00000040)
                self._save_settings()
                self._update_mods_status()

            except Exception as e:
                self._log(f"ERROR: {e}")
                self._set_text(self.lbl_build_status, "BUILD FAILED (see log below)")
                self.ctrl_colors[IDC_LBL_BUILD_STATUS] = self.color_red
                user32.MessageBoxW(self.hwnd, str(e), "Build Failed", MB_OK | MB_ICONERROR)
            finally:
                self.is_building = False
                self._set_enabled(IDC_BTN_BUILD, True)
                self._set_text(IDC_BTN_BUILD, "Build Camp Radio Mod")
                user32.InvalidateRect(self.lbl_build_status, None, 1)

        threading.Thread(target=worker, daemon=True).start()


def launch_gui() -> int:
    app = RadioMusicWin32GUI()
    return app.run()


if __name__ == "__main__":
    sys.exit(launch_gui())
