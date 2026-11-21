#!/usr/bin/env python3
"""
Stellar Blade Custom Camp Music Injector — Native Windows Win32 GUI
===================================================================
Zero-dependency native Windows desktop GUI for `inject_camp_music.py`
built with `ctypes` and the Win32 API (`user32`, `gdi32`, `comdlg32`, `shell32`).

Features:
  - Always Keeps Original Music: Bundles all custom tracks into one mod alongside
    all 34 original Camp Turntable tracks (no replacement slot picking needed).
  - Multi-Song Playlist: Add single or multiple audio files, drag & drop songs or
    folders, reorder tracks, customize titles, and assign optional _OFF audio.
  - Smart Game Auto-Detection: Finds Stellar Blade via Steam registry / libraries.
  - Audio Inspector & Preview: Instant duration/format checks & one-click playback.
  - Universal Titles: Writes titles into StringTable_UI.uasset (works in all languages).
  - Persistent Settings: Remembers your playlist, game folder, volumes, and mod name.
"""

import ctypes
from ctypes import wintypes
import dataclasses
import json
import os
import pathlib
import queue
import re
import sys
import threading
from typing import Dict, List, Optional

import inject_camp_music as icm


# ============================================================================
# Win32 Constants & Structures
# ============================================================================

WS_OVERLAPPED = 0x00000000
WS_CAPTION = 0x00C00000
WS_SYSMENU = 0x00080000
WS_MINIMIZEBOX = 0x00020000
WS_VISIBLE = 0x10000000
WS_CHILD = 0x40000000
WS_TABSTOP = 0x00010000
WS_VSCROLL = 0x00200000
WS_BORDER = 0x00800000
WS_OVERLAPPEDWINDOW_FIXED = WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU | WS_MINIMIZEBOX

WS_EX_CLIENTEDGE = 0x00000200
WS_EX_CONTROLPARENT = 0x00010000
WS_EX_ACCEPTFILES = 0x00000010

BS_PUSHBUTTON = 0x00000000
BS_DEFPUSHBUTTON = 0x00000001
BS_AUTOCHECKBOX = 0x00000003
BS_GROUPBOX = 0x00000007

ES_AUTOHSCROLL = 0x0080
ES_AUTOVSCROLL = 0x0040
ES_MULTILINE = 0x0004
ES_READONLY = 0x0800

CBS_DROPDOWNLIST = 0x0003
CBS_HASSTRINGS = 0x0200

LBS_NOTIFY = 0x0001
LBS_NOINTEGRALHEIGHT = 0x0100

SS_LEFT = 0x00000000

WM_DESTROY = 0x0002
WM_SETFONT = 0x0030
WM_COMMAND = 0x0111
WM_CTLCOLORSTATIC = 0x0138
WM_TIMER = 0x0113
WM_DROPFILES = 0x0233

CB_ADDSTRING = 0x0143
CB_SETCURSEL = 0x014E
CB_GETCURSEL = 0x0147
CB_RESETCONTENT = 0x014B
CBN_SELCHANGE = 1

LB_ADDSTRING = 0x0180
LB_DELETESTRING = 0x0182
LB_RESETCONTENT = 0x0184
LB_SETCURSEL = 0x0186
LB_GETCURSEL = 0x0188
LBN_SELCHANGE = 1
LBN_DBLCLK = 2

BM_GETCHECK = 0x00F0
BM_SETCHECK = 0x00F1
BST_UNCHECKED = 0
BST_CHECKED = 1
BN_CLICKED = 0
EN_CHANGE = 0x0300

EM_SETSEL = 0x00B1
EM_REPLACESEL = 0x00C2
EM_SCROLLCARET = 0x00B7

COLOR_BTNFACE = 15
TRANSPARENT = 1

MB_OK = 0x00000000
MB_YESNO = 0x00000004
MB_ICONERROR = 0x00000010
MB_ICONWARNING = 0x00000030
MB_ICONINFORMATION = 0x00000040

IDYES = 6

OFN_ALLOWMULTISELECT = 0x00000200
OFN_EXPLORER = 0x00080000
OFN_FILEMUSTEXIST = 0x00001000
OFN_PATHMUSTEXIST = 0x00000800
OFN_NOCHANGEDIR = 0x00000008

BIF_RETURNONLYFSDIRS = 0x00000001
BIF_NEWDIALOGSTYLE = 0x00000040

SW_SHOWNORMAL = 1
TIMER_ID_LOG = 101

# Control Identifiers
IDC_LIST_PLAYLIST = 1001
IDC_BTN_ADD_SONGS = 1002
IDC_BTN_LOAD_MUSIC = 1003
IDC_BTN_LOAD_FOLDER = 1004
IDC_BTN_MOVE_UP = 1005
IDC_BTN_MOVE_DOWN = 1006
IDC_BTN_REMOVE_SONG = 1007
IDC_BTN_CLEAR_SONGS = 1008
IDC_BTN_PREVIEW_ON = 1009
IDC_LBL_PLAYLIST_STATUS = 1010
IDC_LBL_AUDIO_META = 1011

IDC_EDIT_TITLE = 1020
IDC_BTN_RESET_TITLE = 1021
IDC_EDIT_AUDIO_OFF = 1022
IDC_BTN_BROWSE_OFF = 1023
IDC_BTN_PREVIEW_OFF = 1024
IDC_BTN_CLEAR_OFF = 1025
IDC_COMBO_COVER = 1026
IDC_BTN_COVER_ALL = 1027
IDC_BTN_BROWSE_COVER = 1028
IDC_BTN_CLEAR_COVER = 1029

IDC_EDIT_VOL_ON = 1030
IDC_EDIT_VOL_OFF = 1031
IDC_BTN_VOL_DEFAULT = 1032
IDC_BTN_VOL_QUIET = 1033
IDC_BTN_VOL_BOOST = 1034
IDC_CHK_REENCODE = 1035
IDC_CHK_EMBEDDED_ART = 1036
IDC_LBL_COVER_STATUS = 1037

IDC_EDIT_GAME_DIR = 1040
IDC_BTN_BROWSE_GAME = 1041
IDC_BTN_AUTO_DETECT_GAME = 1042
IDC_LBL_GAME_STATUS = 1043

IDC_EDIT_MOD_NAME = 1044
IDC_CHK_INSTALL = 1045
IDC_LBL_MODS_STATUS = 1046
IDC_EDIT_OUT_DIR = 1047
IDC_BTN_BROWSE_OUT = 1048

IDC_BTN_BUILD = 1050
IDC_BTN_OPEN_MODS = 1051
IDC_BTN_OPEN_GAME = 1052
IDC_BTN_OPEN_OUT = 1053
IDC_BTN_RESET_ALL = 1054
IDC_LBL_BUILD_STATUS = 1055

IDC_BTN_COPY_LOG = 1060
IDC_BTN_CLEAR_LOG = 1061
IDC_EDIT_LOG = 1062
IDC_LBL_DRAG_HINT = 1070

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.UINT),
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
        ("hIconSm", wintypes.HICON),
    ]


class OPENFILENAMEW(ctypes.Structure):
    _fields_ = [
        ("lStructSize", wintypes.DWORD),
        ("hwndOwner", wintypes.HWND),
        ("hInstance", wintypes.HINSTANCE),
        ("lpstrFilter", wintypes.LPCWSTR),
        ("lpstrCustomFilter", wintypes.LPWSTR),
        ("nMaxCustFilter", wintypes.DWORD),
        ("nFilterIndex", wintypes.DWORD),
        ("lpstrFile", wintypes.LPWSTR),
        ("nMaxFile", wintypes.DWORD),
        ("lpstrFileTitle", wintypes.LPWSTR),
        ("nMaxFileTitle", wintypes.DWORD),
        ("lpstrInitialDir", wintypes.LPCWSTR),
        ("lpstrTitle", wintypes.LPCWSTR),
        ("Flags", wintypes.DWORD),
        ("nFileOffset", wintypes.WORD),
        ("nFileExtension", wintypes.WORD),
        ("lpstrDefExt", wintypes.LPCWSTR),
        ("lCustData", wintypes.LPARAM),
        ("lpfnHook", ctypes.c_void_p),
        ("lpTemplateName", wintypes.LPCWSTR),
        ("pvReserved", ctypes.c_void_p),
        ("dwReserved", wintypes.DWORD),
        ("FlagsEx", wintypes.DWORD),
    ]


class BROWSEINFOW(ctypes.Structure):
    _fields_ = [
        ("hwndOwner", wintypes.HWND),
        ("pidlRoot", ctypes.c_void_p),
        ("pszDisplayName", wintypes.LPWSTR),
        ("lpszTitle", wintypes.LPCWSTR),
        ("ulFlags", wintypes.UINT),
        ("lpfn", ctypes.c_void_p),
        ("lParam", wintypes.LPARAM),
        ("iImage", ctypes.c_int),
    ]


class ACTCTXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.ULONG),
        ("dwFlags", wintypes.DWORD),
        ("lpSource", wintypes.LPCWSTR),
        ("wProcessorArchitecture", wintypes.USHORT),
        ("wLangId", wintypes.USHORT),
        ("lpAssemblyDirectory", wintypes.LPCWSTR),
        ("lpResourceName", wintypes.LPCWSTR),
        ("lpApplicationName", wintypes.LPCWSTR),
        ("hModule", wintypes.HMODULE),
    ]


user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
comdlg32 = ctypes.WinDLL("comdlg32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)

kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE
kernel32.LoadLibraryW.argtypes = [wintypes.LPCWSTR]
kernel32.LoadLibraryW.restype = wintypes.HMODULE
kernel32.CreateActCtxW.argtypes = [ctypes.POINTER(ACTCTXW)]
kernel32.CreateActCtxW.restype = wintypes.HANDLE
kernel32.ActivateActCtx.argtypes = [wintypes.HANDLE, ctypes.POINTER(ctypes.c_size_t)]
kernel32.ActivateActCtx.restype = wintypes.BOOL

gdi32.CreateFontW.argtypes = [
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
    wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
    wintypes.LPCWSTR,
]
gdi32.CreateFontW.restype = wintypes.HFONT
gdi32.SetTextColor.argtypes = [wintypes.HDC, wintypes.COLORREF]
gdi32.SetTextColor.restype = wintypes.COLORREF
gdi32.SetBkMode.argtypes = [wintypes.HDC, ctypes.c_int]
gdi32.SetBkMode.restype = ctypes.c_int
gdi32.CreateSolidBrush.argtypes = [wintypes.COLORREF]
gdi32.CreateSolidBrush.restype = wintypes.HBRUSH

user32.LoadIconW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR]
user32.LoadIconW.restype = wintypes.HICON
user32.LoadCursorW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR]
user32.LoadCursorW.restype = wintypes.HANDLE
user32.RegisterClassExW.argtypes = [ctypes.POINTER(WNDCLASSEXW)]
user32.RegisterClassExW.restype = wintypes.ATOM
user32.CreateWindowExW.argtypes = [
    wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID,
]
user32.CreateWindowExW.restype = wintypes.HWND
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.DefWindowProcW.restype = LRESULT
user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.SendMessageW.restype = LRESULT
user32.SetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPCWSTR]
user32.SetWindowTextW.restype = wintypes.BOOL
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextLengthW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int
user32.EnableWindow.argtypes = [wintypes.HWND, wintypes.BOOL]
user32.EnableWindow.restype = wintypes.BOOL
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.ShowWindow.restype = wintypes.BOOL
user32.UpdateWindow.argtypes = [wintypes.HWND]
user32.UpdateWindow.restype = wintypes.BOOL
user32.SetTimer.argtypes = [wintypes.HWND, ctypes.c_size_t, wintypes.UINT, ctypes.c_void_p]
user32.SetTimer.restype = ctypes.c_size_t
user32.KillTimer.argtypes = [wintypes.HWND, ctypes.c_size_t]
user32.KillTimer.restype = wintypes.BOOL
user32.PostQuitMessage.argtypes = [ctypes.c_int]
user32.PostQuitMessage.restype = None
user32.MessageBoxW.argtypes = [wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.UINT]
user32.MessageBoxW.restype = ctypes.c_int
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.GetMessageW.restype = wintypes.BOOL
user32.IsDialogMessageW.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.MSG)]
user32.IsDialogMessageW.restype = wintypes.BOOL
user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.TranslateMessage.restype = wintypes.BOOL
user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.DispatchMessageW.restype = LRESULT
user32.GetSysColor.argtypes = [ctypes.c_int]
user32.GetSysColor.restype = wintypes.DWORD
user32.MessageBeep.argtypes = [wintypes.UINT]
user32.MessageBeep.restype = wintypes.BOOL
user32.InvalidateRect.argtypes = [wintypes.HWND, ctypes.c_void_p, wintypes.BOOL]
user32.InvalidateRect.restype = wintypes.BOOL

shell32.DragAcceptFiles.argtypes = [wintypes.HWND, wintypes.BOOL]
shell32.DragAcceptFiles.restype = None
shell32.DragQueryFileW.argtypes = [ctypes.c_void_p, wintypes.UINT, wintypes.LPWSTR, wintypes.UINT]
shell32.DragQueryFileW.restype = wintypes.UINT
shell32.DragFinish.argtypes = [ctypes.c_void_p]
shell32.DragFinish.restype = None

comdlg32.GetOpenFileNameW.argtypes = [ctypes.POINTER(OPENFILENAMEW)]
comdlg32.GetOpenFileNameW.restype = wintypes.BOOL
shell32.SHBrowseForFolderW.argtypes = [ctypes.POINTER(BROWSEINFOW)]
shell32.SHBrowseForFolderW.restype = ctypes.c_void_p
shell32.SHGetPathFromIDListW.argtypes = [ctypes.c_void_p, wintypes.LPWSTR]
shell32.SHGetPathFromIDListW.restype = wintypes.BOOL


def _enable_visual_styles_and_dpi() -> None:
    try:
        user32.SetProcessDPIAware()
    except Exception:
        pass
    try:
        act = ACTCTXW()
        act.cbSize = ctypes.sizeof(ACTCTXW)
        act.dwFlags = 0x08 | 0x80
        act.hModule = kernel32.LoadLibraryW("shell32.dll")
        act.lpResourceName = ctypes.cast(ctypes.c_void_p(124), wintypes.LPCWSTR)
        h_ctx = kernel32.CreateActCtxW(ctypes.byref(act))
        if h_ctx and h_ctx != ctypes.c_void_p(-1).value:
            cookie = ctypes.c_size_t()
            kernel32.ActivateActCtx(h_ctx, ctypes.byref(cookie))
    except Exception:
        pass


@dataclasses.dataclass
class PlaylistItem:
    audio_on: pathlib.Path
    title: str
    audio_off: Optional[pathlib.Path] = None
    cover_idx: int = 0
    custom_cover_path: Optional[pathlib.Path] = None
    has_embedded_cover: bool = False
    duration_str: str = ""
    meta_summary: str = ""
    meta_color: int = 0x555555


# ============================================================================
# Smart Game Folder Auto-Detection & Clipboard
# ============================================================================

def detect_stellar_blade_game_dir(root_dir: pathlib.Path) -> Optional[pathlib.Path]:
    candidates: List[pathlib.Path] = [
        pathlib.Path(r"C:\Program Files (x86)\Steam\steamapps\common\StellarBlade"),
        pathlib.Path(r"C:\Program Files (x86)\Steam\steamapps\common\Stellar Blade"),
        pathlib.Path(r"C:\Program Files\Steam\steamapps\common\StellarBlade"),
        pathlib.Path(r"C:\Program Files\Steam\steamapps\common\Stellar Blade"),
    ]

    steam_roots: List[pathlib.Path] = []
    try:
        import winreg
        for root_key, subkey in [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam"),
            (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
        ]:
            for val_name in ("InstallPath", "SteamPath"):
                try:
                    with winreg.OpenKey(root_key, subkey) as k:
                        val, _ = winreg.QueryValueEx(k, val_name)
                        if val:
                            p = pathlib.Path(val)
                            if p not in steam_roots:
                                steam_roots.append(p)
                except Exception:
                    pass
    except Exception:
        pass

    for s_dir in steam_roots:
        candidates.append(s_dir / "steamapps" / "common" / "StellarBlade")
        candidates.append(s_dir / "steamapps" / "common" / "Stellar Blade")
        vdf = s_dir / "steamapps" / "libraryfolders.vdf"
        if vdf.is_file():
            try:
                txt = vdf.read_text(encoding="utf-8", errors="ignore")
                for match in re.finditer(r'"path"\s+"([^"]+)"', txt):
                    lib_p = pathlib.Path(match.group(1).replace("\\\\", "\\"))
                    candidates.append(lib_p / "steamapps" / "common" / "StellarBlade")
                    candidates.append(lib_p / "steamapps" / "common" / "Stellar Blade")
            except Exception:
                pass

    for drive in "CDEFGHIJKLMNOPQRSTUVWXYZ":
        candidates.append(pathlib.Path(f"{drive}:/SteamLibrary/steamapps/common/StellarBlade"))
        candidates.append(pathlib.Path(f"{drive}:/SteamLibrary/steamapps/common/Stellar Blade"))
        candidates.append(pathlib.Path(f"{drive}:/Games/StellarBlade"))
        candidates.append(pathlib.Path(f"{drive}:/Games/Stellar Blade"))

    candidates.extend([
        root_dir / "Context" / "StellarBlade",
        root_dir / "StellarBlade",
        root_dir.parent / "StellarBlade",
        root_dir.parent / "Stellar Blade",
    ])

    for c in candidates:
        try:
            if c.is_dir() and ((c / "SB" / "Content" / "Paks").is_dir() or (c / "SB.exe").is_file()):
                return c.resolve()
        except Exception:
            pass

    return None


def copy_text_to_clipboard(text: str) -> bool:
    try:
        if not user32.OpenClipboard(None):
            return False
        user32.EmptyClipboard()
        raw = text.encode("utf-16le") + b"\x00\x00"
        h_mem = kernel32.GlobalAlloc(0x0002, len(raw))
        if not h_mem:
            user32.CloseClipboard()
            return False
        ptr = kernel32.GlobalLock(h_mem)
        ctypes.memmove(ptr, raw, len(raw))
        kernel32.GlobalUnlock(h_mem)
        user32.SetClipboardData(13, h_mem)
        user32.CloseClipboard()
        return True
    except Exception:
        return False


# ============================================================================
# Native Win32 GUI Application
# ============================================================================

class CampMusicWin32GUI:
    def __init__(self) -> None:
        _enable_visual_styles_and_dpi()

        self.root_dir = pathlib.Path(__file__).resolve().parent
        self.cache_dir = self.root_dir / ".cache"
        self.settings_file = self.cache_dir / "gui_settings.json"
        self.settings: Dict[str, object] = self._load_settings()

        steam_default = pathlib.Path(r"C:\Program Files (x86)\Steam\steamapps\common\StellarBlade")
        detected_game = detect_stellar_blade_game_dir(self.root_dir)
        saved_game = self.settings.get("game_dir")

        if saved_game:
            saved_p = pathlib.Path(str(saved_game))
            if "context" in str(saved_p).lower() and detected_game and "context" not in str(detected_game).lower():
                self.default_game_dir = detected_game
            elif saved_p.is_dir():
                self.default_game_dir = saved_p
            elif detected_game:
                self.default_game_dir = detected_game
            else:
                self.default_game_dir = steam_default
        elif detected_game:
            self.default_game_dir = detected_game
        else:
            self.default_game_dir = steam_default

        saved_out = self.settings.get("out_dir")
        self.default_out_dir = pathlib.Path(str(saved_out)) if saved_out else (self.root_dir / "dist")

        self.hinst = kernel32.GetModuleHandleW(None)
        self.hwnd: Optional[wintypes.HWND] = None
        self.controls: Dict[int, wintypes.HWND] = {}
        self.log_queue: "queue.Queue[str]" = queue.Queue()
        self.is_building = False
        self._suppress_editor_sync = False

        self.color_green = 0x008020
        self.color_amber = 0x0055B8
        self.color_red = 0x0000C8
        self.color_blue = 0x8A3A00
        self.color_gray = 0x555555
        self.ctrl_colors: Dict[int, int] = {}

        self.font_title = gdi32.CreateFontW(-20, 0, 0, 0, 700, 0, 0, 0, 1, 0, 0, 5, 0, "Segoe UI")
        self.font_bold = gdi32.CreateFontW(-13, 0, 0, 0, 600, 0, 0, 0, 1, 0, 0, 5, 0, "Segoe UI")
        self.font_ui = gdi32.CreateFontW(-13, 0, 0, 0, 400, 0, 0, 0, 1, 0, 0, 5, 0, "Segoe UI")
        self.font_small = gdi32.CreateFontW(-11, 0, 0, 0, 400, 0, 0, 0, 1, 0, 0, 5, 0, "Segoe UI")
        self.font_mono = gdi32.CreateFontW(-12, 0, 0, 0, 400, 0, 0, 0, 1, 0, 0, 5, 0, "Consolas")

        self.brush_btnface = gdi32.CreateSolidBrush(user32.GetSysColor(COLOR_BTNFACE))

        self.playlist: List[PlaylistItem] = []
        self._ready = False

        self._wndproc_ref = WNDPROC(self._wnd_proc)
        self._register_class()
        self._create_main_window()

    def _load_settings(self) -> Dict[str, object]:
        if self.settings_file.is_file():
            try:
                return json.loads(self.settings_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def _save_settings(self) -> None:
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            serialized_playlist = [
                {
                    "audio_on": str(item.audio_on),
                    "title": item.title,
                    "audio_off": str(item.audio_off) if item.audio_off else None,
                    "cover_idx": item.cover_idx,
                    "custom_cover_path": str(item.custom_cover_path) if item.custom_cover_path else None,
                }
                for item in self.playlist
            ]
            data = {
                "game_dir": self._get_text(IDC_EDIT_GAME_DIR).strip(),
                "out_dir": self._get_text(IDC_EDIT_OUT_DIR).strip(),
                "mod_name": self._get_text(IDC_EDIT_MOD_NAME).strip() or "CampMusic_Custom_295_P",
                "install_to_game": self._is_checked(IDC_CHK_INSTALL),
                "vol_on": self._get_text(IDC_EDIT_VOL_ON).strip(),
                "vol_off": self._get_text(IDC_EDIT_VOL_OFF).strip(),
                "reencode": self._is_checked(IDC_CHK_REENCODE),
                "use_embedded_art": self._is_checked(IDC_CHK_EMBEDDED_ART),
                "playlist": serialized_playlist,
            }
            self.settings_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _register_class(self) -> None:
        self.class_name = "StellarBladeCampMusicGUI"
        wc = WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wc.style = 0
        wc.lpfnWndProc = self._wndproc_ref
        wc.cbClsExtra = 0
        wc.cbWndExtra = 0
        wc.hInstance = self.hinst
        wc.hIcon = user32.LoadIconW(None, ctypes.cast(32512, wintypes.LPCWSTR))
        wc.hCursor = user32.LoadCursorW(None, ctypes.cast(32512, wintypes.LPCWSTR))
        wc.hbrBackground = wintypes.HBRUSH(COLOR_BTNFACE + 1)
        wc.lpszMenuName = None
        wc.lpszClassName = self.class_name
        wc.hIconSm = wc.hIcon
        user32.RegisterClassExW(ctypes.byref(wc))

    def _add_ctrl(
        self,
        cls: str,
        text: str,
        style: int,
        x: int,
        y: int,
        w: int,
        h: int,
        ctrl_id: int = 0,
        ex_style: int = 0,
        font: Optional[int] = None,
    ) -> wintypes.HWND:
        hwnd = user32.CreateWindowExW(
            ex_style,
            cls,
            text,
            WS_CHILD | WS_VISIBLE | style,
            x,
            y,
            w,
            h,
            self.hwnd,
            wintypes.HMENU(ctrl_id),
            self.hinst,
            None,
        )
        user32.SendMessageW(hwnd, WM_SETFONT, font or self.font_ui, 1)
        if ctrl_id:
            self.controls[ctrl_id] = hwnd
        return hwnd

    def _create_main_window(self) -> None:
        width, height = 880, 910
        screen_w = user32.GetSystemMetrics(0)
        screen_h = user32.GetSystemMetrics(1)
        pos_x = max(0, (screen_w - width) // 2)
        pos_y = max(0, (screen_h - height) // 2)

        self.hwnd = user32.CreateWindowExW(
            WS_EX_CONTROLPARENT | WS_EX_ACCEPTFILES,
            self.class_name,
            "Stellar Blade — Custom Camp Music Injector",
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
        self._add_ctrl("STATIC", "Stellar Blade — Custom Camp Music Injector", SS_LEFT, 18, 12, 700, 26, font=self.font_title)
        self._add_ctrl(
            "STATIC",
            "Add your own custom songs to the Camp Turntable while keeping all 34 original in-game tracks intact.",
            SS_LEFT,
            18, 38, 830, 18,
        )
        self.lbl_drag_hint = self._add_ctrl(
            "STATIC",
            "Tip: Drag & drop audio files (.ogg, .mp3, .wav, .flac), a music folder, or your Stellar Blade folder anywhere onto this window!",
            SS_LEFT,
            18, 58, 835, 18,
            IDC_LBL_DRAG_HINT,
            font=self.font_bold,
        )
        self.ctrl_colors[IDC_LBL_DRAG_HINT] = self.color_blue

        # ====================================================================
        # 1. Custom Camp Tracks Playlist Group
        # ====================================================================
        self._add_ctrl(
            "BUTTON",
            " 1. Custom Songs to Add (Original 34 Tracks Always Preserved) ",
            BS_GROUPBOX,
            14, 80, 840, 276,
            font=self.font_bold,
        )

        self._add_ctrl(
            "LISTBOX",
            "",
            LBS_NOTIFY | LBS_NOINTEGRALHEIGHT | WS_VSCROLL | WS_BORDER | WS_TABSTOP,
            26, 104, 578, 200,
            IDC_LIST_PLAYLIST,
            WS_EX_CLIENTEDGE,
            font=self.font_mono,
        )

        # Playlist buttons (right column)
        self._add_ctrl("BUTTON", "Add Song(s)...", BS_PUSHBUTTON | WS_TABSTOP, 614, 104, 226, 28, IDC_BTN_ADD_SONGS, font=self.font_bold)
        self._add_ctrl("BUTTON", "Load ./Music Folder", BS_PUSHBUTTON | WS_TABSTOP, 614, 136, 226, 26, IDC_BTN_LOAD_MUSIC)
        self._add_ctrl("BUTTON", "Load Custom Folder...", BS_PUSHBUTTON | WS_TABSTOP, 614, 166, 226, 26, IDC_BTN_LOAD_FOLDER)
        self._add_ctrl("BUTTON", "Move Up", BS_PUSHBUTTON | WS_TABSTOP, 614, 196, 110, 26, IDC_BTN_MOVE_UP)
        self._add_ctrl("BUTTON", "Move Down", BS_PUSHBUTTON | WS_TABSTOP, 730, 196, 110, 26, IDC_BTN_MOVE_DOWN)
        self._add_ctrl("BUTTON", "Remove", BS_PUSHBUTTON | WS_TABSTOP, 614, 226, 110, 26, IDC_BTN_REMOVE_SONG)
        self._add_ctrl("BUTTON", "Clear All", BS_PUSHBUTTON | WS_TABSTOP, 730, 226, 110, 26, IDC_BTN_CLEAR_SONGS)
        self._add_ctrl("BUTTON", "Preview Selected Audio", BS_PUSHBUTTON | WS_TABSTOP, 614, 256, 226, 28, IDC_BTN_PREVIEW_ON)

        self.lbl_playlist_status = self._add_ctrl(
            "STATIC",
            "0 custom song(s) queued — all 34 original tracks will remain intact.",
            SS_LEFT,
            26, 310, 814, 18,
            IDC_LBL_PLAYLIST_STATUS,
            font=self.font_bold,
        )
        self.lbl_audio_meta = self._add_ctrl(
            "STATIC",
            "Add audio files or drop them onto this window to inspect format & duration.",
            SS_LEFT,
            26, 330, 814, 18,
            IDC_LBL_AUDIO_META,
        )

        # ====================================================================
        # 2. Selected Song Details & Playback Settings Group
        # ====================================================================
        self._add_ctrl(
            "BUTTON",
            " 2. Selected Song Details & Playback Settings ",
            BS_GROUPBOX,
            14, 362, 840, 166,
            font=self.font_bold,
        )

        self._add_ctrl("STATIC", "In-Game Title:", SS_LEFT, 26, 386, 115, 18)
        self._add_ctrl("EDIT", "", ES_AUTOHSCROLL | WS_TABSTOP, 145, 383, 560, 23, IDC_EDIT_TITLE, WS_EX_CLIENTEDGE)
        self._add_ctrl("BUTTON", "Auto-Detect", BS_PUSHBUTTON | WS_TABSTOP, 712, 382, 128, 25, IDC_BTN_RESET_TITLE)

        self._add_ctrl("STATIC", "Ambient (_OFF):", SS_LEFT, 26, 415, 115, 18)
        self._add_ctrl("EDIT", "", ES_AUTOHSCROLL | WS_TABSTOP, 145, 412, 415, 23, IDC_EDIT_AUDIO_OFF, WS_EX_CLIENTEDGE)
        self._add_ctrl("BUTTON", "Browse...", BS_PUSHBUTTON | WS_TABSTOP, 566, 411, 72, 25, IDC_BTN_BROWSE_OFF)
        self._add_ctrl("BUTTON", "Preview", BS_PUSHBUTTON | WS_TABSTOP, 644, 411, 68, 25, IDC_BTN_PREVIEW_OFF)
        self._add_ctrl("BUTTON", "Clear", BS_PUSHBUTTON | WS_TABSTOP, 718, 411, 60, 25, IDC_BTN_CLEAR_OFF)
        self._add_ctrl("STATIC", "(Optional)", SS_LEFT, 784, 415, 58, 18, font=self.font_small)

        self._add_ctrl("STATIC", "Album Cover:", SS_LEFT, 26, 444, 115, 18)
        combo_cover = self._add_ctrl(
            "COMBOBOX",
            "",
            CBS_DROPDOWNLIST | CBS_HASSTRINGS | WS_VSCROLL | WS_TABSTOP,
            145, 441, 200, 240,
            IDC_COMBO_COVER,
        )
        for label, _ in icm.ALBUM_COVER_PRESETS:
            buf = ctypes.create_unicode_buffer(label)
            user32.SendMessageW(combo_cover, CB_ADDSTRING, 0, ctypes.addressof(buf))
        user32.SendMessageW(combo_cover, CB_SETCURSEL, 0, 0)
        self._add_ctrl("BUTTON", "Custom Img...", BS_PUSHBUTTON | WS_TABSTOP, 351, 440, 96, 25, IDC_BTN_BROWSE_COVER)
        self._add_ctrl("BUTTON", "Clear Img", BS_PUSHBUTTON | WS_TABSTOP, 451, 440, 74, 25, IDC_BTN_CLEAR_COVER)
        self._add_ctrl("BUTTON", "Apply Cover to All", BS_PUSHBUTTON | WS_TABSTOP, 531, 440, 134, 25, IDC_BTN_COVER_ALL)
        self._add_ctrl(
            "BUTTON",
            "Use Embedded Art",
            BS_AUTOCHECKBOX | WS_TABSTOP,
            673, 443, 167, 20,
            IDC_CHK_EMBEDDED_ART,
        )
        if self.settings.get("use_embedded_art", True):
            user32.SendMessageW(self.controls[IDC_CHK_EMBEDDED_ART], BM_SETCHECK, BST_CHECKED, 0)

        self._add_ctrl("STATIC", "Turntable Vol:", SS_LEFT, 26, 476, 84, 18)
        vol_on_val = str(self.settings.get("vol_on", "1.1"))
        self._add_ctrl("EDIT", vol_on_val, ES_AUTOHSCROLL | WS_TABSTOP, 114, 473, 44, 22, IDC_EDIT_VOL_ON, WS_EX_CLIENTEDGE)

        self._add_ctrl("STATIC", "Ambient Vol:", SS_LEFT, 166, 476, 78, 18)
        vol_off_val = str(self.settings.get("vol_off", "0.6"))
        self._add_ctrl("EDIT", vol_off_val, ES_AUTOHSCROLL | WS_TABSTOP, 246, 473, 44, 22, IDC_EDIT_VOL_OFF, WS_EX_CLIENTEDGE)

        self._add_ctrl("BUTTON", "Default (1.1 / 0.6)", BS_PUSHBUTTON | WS_TABSTOP, 298, 472, 108, 24, IDC_BTN_VOL_DEFAULT)
        self._add_ctrl("BUTTON", "Quiet (0.5 / 0.2)", BS_PUSHBUTTON | WS_TABSTOP, 410, 472, 104, 24, IDC_BTN_VOL_QUIET)
        self._add_ctrl("BUTTON", "Boosted (1.3 / 0.8)", BS_PUSHBUTTON | WS_TABSTOP, 518, 472, 108, 24, IDC_BTN_VOL_BOOST)

        self._add_ctrl(
            "BUTTON",
            "Force FFmpeg 48kHz Stereo",
            BS_AUTOCHECKBOX | WS_TABSTOP,
            634, 474, 206, 20,
            IDC_CHK_REENCODE,
        )
        if self.settings.get("reencode", False):
            user32.SendMessageW(self.controls[IDC_CHK_REENCODE], BM_SETCHECK, BST_CHECKED, 0)

        self.lbl_cover_status = self._add_ctrl(
            "STATIC",
            "Cover: Preset fallback | Custom song titles display in every game language.",
            SS_LEFT,
            26, 504, 814, 16,
            IDC_LBL_COVER_STATUS,
            font=self.font_small,
        )

        # ====================================================================
        # 3. Game Folder & Mod Output Group
        # ====================================================================
        self._add_ctrl("BUTTON", " 3. Game Folder & Output Installation ", BS_GROUPBOX, 14, 534, 840, 148, font=self.font_bold)

        self._add_ctrl("STATIC", "Stellar Blade Dir:", SS_LEFT, 26, 558, 115, 18)
        self._add_ctrl(
            "EDIT", str(self.default_game_dir), ES_AUTOHSCROLL | WS_TABSTOP,
            145, 555, 475, 23, IDC_EDIT_GAME_DIR, WS_EX_CLIENTEDGE
        )
        self._add_ctrl("BUTTON", "Browse...", BS_PUSHBUTTON | WS_TABSTOP, 628, 554, 72, 25, IDC_BTN_BROWSE_GAME)
        self._add_ctrl("BUTTON", "Auto-Detect Game", BS_PUSHBUTTON | WS_TABSTOP, 706, 554, 134, 25, IDC_BTN_AUTO_DETECT_GAME)

        self.lbl_game_status = self._add_ctrl("STATIC", "", SS_LEFT, 145, 581, 695, 18, IDC_LBL_GAME_STATUS)

        self._add_ctrl("STATIC", "Mod Name (_P):", SS_LEFT, 26, 605, 115, 18)
        saved_mod = str(self.settings.get("mod_name", "CampMusic_Custom_295_P"))
        self._add_ctrl("EDIT", saved_mod, ES_AUTOHSCROLL | WS_TABSTOP, 145, 602, 230, 23, IDC_EDIT_MOD_NAME, WS_EX_CLIENTEDGE)

        self._add_ctrl(
            "BUTTON",
            "Install directly into ~mods",
            BS_AUTOCHECKBOX | WS_TABSTOP,
            385, 604, 175, 20,
            IDC_CHK_INSTALL,
        )
        install_chk = self.settings.get("install_to_game", True)
        user32.SendMessageW(self.controls[IDC_CHK_INSTALL], BM_SETCHECK, BST_CHECKED if install_chk else BST_UNCHECKED, 0)

        self.lbl_mods_status = self._add_ctrl("STATIC", "", SS_LEFT, 566, 605, 274, 18, IDC_LBL_MODS_STATUS)

        self._add_ctrl("STATIC", "Output Folder (dist):", SS_LEFT, 26, 636, 115, 18)
        self._add_ctrl(
            "EDIT", str(self.default_out_dir), ES_AUTOHSCROLL | WS_TABSTOP,
            145, 633, 601, 23, IDC_EDIT_OUT_DIR, WS_EX_CLIENTEDGE
        )
        self._add_ctrl("BUTTON", "Browse...", BS_PUSHBUTTON | WS_TABSTOP, 752, 632, 88, 25, IDC_BTN_BROWSE_OUT)

        # ====================================================================
        # 4. Actions & Build Feedback
        # ====================================================================
        self._add_ctrl("BUTTON", "Build Custom Music Mod", BS_DEFPUSHBUTTON | WS_TABSTOP, 14, 690, 220, 36, IDC_BTN_BUILD, font=self.font_bold)
        self._add_ctrl("BUTTON", "Open ~mods", BS_PUSHBUTTON | WS_TABSTOP, 240, 690, 105, 36, IDC_BTN_OPEN_MODS)
        self._add_ctrl("BUTTON", "Open Game Folder", BS_PUSHBUTTON | WS_TABSTOP, 351, 690, 125, 36, IDC_BTN_OPEN_GAME)
        self._add_ctrl("BUTTON", "Open Output", BS_PUSHBUTTON | WS_TABSTOP, 482, 690, 100, 36, IDC_BTN_OPEN_OUT)
        self._add_ctrl("BUTTON", "Reset", BS_PUSHBUTTON | WS_TABSTOP, 588, 690, 65, 36, IDC_BTN_RESET_ALL)

        self.lbl_build_status = self._add_ctrl(
            "STATIC", "Ready. Add songs and click 'Build Custom Music Mod'.",
            SS_LEFT, 660, 695, 195, 30, IDC_LBL_BUILD_STATUS, font=self.font_bold
        )

        # ====================================================================
        # 5. Activity Log
        # ====================================================================
        self._add_ctrl("STATIC", "Activity Log:", SS_LEFT, 16, 734, 100, 18, font=self.font_bold)
        self._add_ctrl("BUTTON", "Copy Log", BS_PUSHBUTTON | WS_TABSTOP, 688, 731, 76, 22, IDC_BTN_COPY_LOG)
        self._add_ctrl("BUTTON", "Clear Log", BS_PUSHBUTTON | WS_TABSTOP, 770, 731, 76, 22, IDC_BTN_CLEAR_LOG)

        self._add_ctrl(
            "EDIT",
            "",
            ES_MULTILINE | ES_AUTOVSCROLL | ES_READONLY | WS_VSCROLL,
            14, 756, 840, 108,
            IDC_EDIT_LOG,
            WS_EX_CLIENTEDGE,
            font=self.font_mono,
        )

        # Initialize state
        self._update_game_status()
        self._update_install_state()
        self._restore_or_load_initial_playlist()

        self._log("Stellar Blade Custom Camp Music Injector initialized (Keep-Original-Music mode).")
        if self.default_game_dir.is_dir():
            self._log(f"Stellar Blade game directory: {self.default_game_dir}")
        self._log("All 34 original in-game Camp Turntable songs are always preserved.")

        user32.SetTimer(self.hwnd, TIMER_ID_LOG, 80, None)
        self._ready = True

    # ========================================================================
    # Playlist Management Helpers
    # ========================================================================

    def _inspect_audio_meta(self, item: PlaylistItem) -> None:
        p = item.audio_on
        if not p.is_file():
            item.duration_str = "missing"
            item.has_embedded_cover = False
            item.meta_summary = f"[Missing] File not found: {p}"
            item.meta_color = self.color_red
            return

        item.has_embedded_cover = bool(icm.extract_embedded_cover_art(p))
        size_mb = p.stat().st_size / (1024 * 1024)
        ext = p.suffix.lower()
        if ext == ".ogg":
            try:
                raw = p.read_bytes()
                info = icm.parse_ogg_vorbis(raw)
                mins = int(info.duration // 60)
                secs = int(info.duration % 60)
                item.duration_str = f"{mins}:{secs:02d}"
                strip_reason = icm._ogg_has_image_or_extra_streams(raw)
                if strip_reason:
                    item.meta_summary = (
                        f"[Notice] Vorbis {info.sample_rate} Hz, {info.channels}ch ({strip_reason}) "
                        f"— Will auto-strip metadata for audio & extract cover"
                    )
                    item.meta_color = self.color_amber
                elif info.sample_rate == 48000 and info.channels == 2:
                    item.meta_summary = (
                        f"[OK] Native Vorbis: 48 kHz Stereo, {mins}m {secs:02d}s ({size_mb:.2f} MB) — Ready!"
                    )
                    item.meta_color = self.color_green
                else:
                    item.meta_summary = (
                        f"[Notice] Vorbis {info.sample_rate} Hz, {info.channels}ch, {mins}m {secs:02d}s ({size_mb:.2f} MB) "
                        f"— Will convert to 48 kHz Stereo via FFmpeg"
                    )
                    item.meta_color = self.color_amber
                return
            except Exception as e:
                item.duration_str = "?"
                item.meta_summary = f"[Notice] Ogg check: {e} (will auto-convert via FFmpeg)"
                item.meta_color = self.color_amber
                return

        item.duration_str = ext.upper().lstrip(".")
        art_note = " (embedded cover detected)" if item.has_embedded_cover else ""
        item.meta_summary = (
            f"[Notice] {ext.upper()}{art_note} ({size_mb:.2f} MB) — Will auto-convert to clean 48 kHz Stereo Vorbis"
        )
        item.meta_color = self.color_blue

    def _format_cover_status(self, item: Optional[PlaylistItem]) -> str:
        if item is None:
            return "Cover Art: Select a track to customize cover image or preset fallback."
        if item.custom_cover_path and item.custom_cover_path.is_file():
            return f"Cover Art: Custom image '{item.custom_cover_path.name}' (256x256 BGRA UTexture2D)"
        if item.has_embedded_cover and self._is_checked(IDC_CHK_EMBEDDED_ART):
            return "Cover Art: Auto-extracted from audio file metadata (256x256 BGRA UTexture2D)"
        preset_label = icm.ALBUM_COVER_PRESETS[item.cover_idx][0]
        if item.has_embedded_cover:
            return f"Cover Art: Preset '{preset_label}' (embedded art ignored)"
        return f"Cover Art: Preset '{preset_label}' (no embedded art found in file)"

    def _format_playlist_label(self, idx_1based: int, item: PlaylistItem) -> str:
        dur = f" ({item.duration_str})" if item.duration_str else ""
        off_tag = " [+OFF]" if item.audio_off else ""
        if item.custom_cover_path and item.custom_cover_path.is_file():
            art_tag = f" [Img: {item.custom_cover_path.name}]"
        elif item.has_embedded_cover and self._is_checked(IDC_CHK_EMBEDDED_ART):
            art_tag = " [Embedded Art]"
        else:
            art_tag = ""
        return f"[{idx_1based:02d}] {item.title}{dur}{off_tag}{art_tag}  —  {item.audio_on.name}"

    def _refresh_playlist_box(self, select_idx: Optional[int] = None) -> None:
        lb = self.controls[IDC_LIST_PLAYLIST]
        if select_idx is None:
            select_idx = int(user32.SendMessageW(lb, LB_GETCURSEL, 0, 0))
        user32.SendMessageW(lb, LB_RESETCONTENT, 0, 0)
        for i, item in enumerate(self.playlist, start=1):
            buf = ctypes.create_unicode_buffer(self._format_playlist_label(i, item))
            user32.SendMessageW(lb, LB_ADDSTRING, 0, ctypes.addressof(buf))

        if self.playlist:
            if select_idx < 0 or select_idx >= len(self.playlist):
                select_idx = 0
            user32.SendMessageW(lb, LB_SETCURSEL, select_idx, 0)
        else:
            select_idx = -1

        self._set_text(
            self.lbl_playlist_status,
            f"{len(self.playlist)} custom song(s) queued — all 34 original songs will remain intact.",
        )
        self._load_selected_into_editors(select_idx)

    def _get_selected_playlist_index(self) -> int:
        idx = int(user32.SendMessageW(self.controls[IDC_LIST_PLAYLIST], LB_GETCURSEL, 0, 0))
        if 0 <= idx < len(self.playlist):
            return idx
        return -1

    def _load_selected_into_editors(self, idx: Optional[int] = None) -> None:
        if idx is None:
            idx = self._get_selected_playlist_index()
        self._suppress_editor_sync = True
        try:
            if 0 <= idx < len(self.playlist):
                item = self.playlist[idx]
                self._set_text(IDC_EDIT_TITLE, item.title)
                self._set_text(IDC_EDIT_AUDIO_OFF, str(item.audio_off) if item.audio_off else "")
                user32.SendMessageW(self.controls[IDC_COMBO_COVER], CB_SETCURSEL, item.cover_idx, 0)
                self._set_text(self.lbl_audio_meta, item.meta_summary)
                self._set_text(self.lbl_cover_status, self._format_cover_status(item))
                self.ctrl_colors[IDC_LBL_AUDIO_META] = item.meta_color
                for cid in (
                    IDC_EDIT_TITLE, IDC_BTN_RESET_TITLE,
                    IDC_EDIT_AUDIO_OFF, IDC_BTN_BROWSE_OFF, IDC_BTN_PREVIEW_OFF, IDC_BTN_CLEAR_OFF,
                    IDC_COMBO_COVER, IDC_BTN_BROWSE_COVER, IDC_BTN_COVER_ALL,
                ):
                    self._set_enabled(cid, True)
                self._set_enabled(IDC_BTN_CLEAR_COVER, bool(item.custom_cover_path))
            else:
                self._set_text(IDC_EDIT_TITLE, "")
                self._set_text(IDC_EDIT_AUDIO_OFF, "")
                user32.SendMessageW(self.controls[IDC_COMBO_COVER], CB_SETCURSEL, 0, 0)
                self._set_text(self.lbl_audio_meta, "Add audio files or drop them onto this window to inspect format & duration.")
                self._set_text(self.lbl_cover_status, self._format_cover_status(None))
                self.ctrl_colors[IDC_LBL_AUDIO_META] = self.color_gray
                for cid in (
                    IDC_EDIT_TITLE, IDC_BTN_RESET_TITLE,
                    IDC_EDIT_AUDIO_OFF, IDC_BTN_BROWSE_OFF, IDC_BTN_PREVIEW_OFF, IDC_BTN_CLEAR_OFF,
                    IDC_COMBO_COVER, IDC_BTN_BROWSE_COVER, IDC_BTN_CLEAR_COVER, IDC_BTN_COVER_ALL,
                ):
                    self._set_enabled(cid, False)
            user32.InvalidateRect(self.lbl_audio_meta, None, 1)
        finally:
            self._suppress_editor_sync = False

    def _add_audio_paths(self, paths: List[pathlib.Path]) -> int:
        added = 0
        existing = {item.audio_on.resolve() for item in self.playlist if item.audio_on.exists()}
        for p in paths:
            if not p.is_file() or p.suffix.lower() not in icm.SUPPORTED_AUDIO_EXTENSIONS:
                continue
            rp = p.resolve()
            if rp in existing:
                continue
            off_cand = icm.find_off_audio_candidate(p)
            item = PlaylistItem(
                audio_on=p,
                title=icm.infer_song_title(p),
                audio_off=off_cand,
                cover_idx=0,
            )
            self._inspect_audio_meta(item)
            self.playlist.append(item)
            existing.add(rp)
            added += 1

        if added:
            self._refresh_playlist_box(select_idx=len(self.playlist) - 1)
        return added

    def _load_folder_songs(self, folder: pathlib.Path, replace: bool = False) -> None:
        files = icm.scan_music_folder(folder)
        if not files:
            user32.MessageBoxW(
                self.hwnd,
                f"No supported audio files (.ogg, .wav, .mp3, .flac, .m4a) were found in:\n\n{folder}",
                "No Audio Files Found",
                MB_OK | MB_ICONINFORMATION,
            )
            return
        if replace:
            self.playlist.clear()
        added = self._add_audio_paths(files)
        self._log(f"Loaded {added} song(s) from folder: {folder}")

    def _restore_or_load_initial_playlist(self) -> None:
        saved_pl = self.settings.get("playlist")
        restored = 0
        if isinstance(saved_pl, list):
            for entry in saved_pl:
                if not isinstance(entry, dict):
                    continue
                on_p = pathlib.Path(str(entry.get("audio_on", "")))
                if not on_p.is_file():
                    continue
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
                saved_title = str(entry.get("title") or "").strip()
                inferred_title = icm.infer_song_title(on_p)
                if not saved_title or saved_title == icm.clean_title_from_stem(on_p.stem):
                    final_title = inferred_title
                else:
                    final_title = saved_title
                item = PlaylistItem(
                    audio_on=on_p,
                    title=final_title,
                    audio_off=off_p,
                    cover_idx=cidx,
                    custom_cover_path=cov_p,
                )
                self._inspect_audio_meta(item)
                self.playlist.append(item)
                restored += 1

        if restored == 0:
            music_dir = self.root_dir / "Music"
            if music_dir.is_dir():
                files = icm.scan_music_folder(music_dir)
                self._add_audio_paths(files)
                return

        self._refresh_playlist_box(select_idx=0 if self.playlist else -1)

    def _sync_title_from_editor(self) -> None:
        if self._suppress_editor_sync:
            return
        idx = self._get_selected_playlist_index()
        if idx < 0:
            return
        new_title = self._get_text(IDC_EDIT_TITLE)
        if self.playlist[idx].title != new_title:
            self.playlist[idx].title = new_title
            # Refresh just the listbox text keeping selection
            lb = self.controls[IDC_LIST_PLAYLIST]
            user32.SendMessageW(lb, LB_DELETESTRING, idx, 0)
            buf = ctypes.create_unicode_buffer(self._format_playlist_label(idx + 1, self.playlist[idx]))
            user32.SendMessageW(lb, 0x0181, idx, ctypes.addressof(buf))  # LB_INSERTSTRING
            user32.SendMessageW(lb, LB_SETCURSEL, idx, 0)

    def _preview_audio(self, path: Optional[pathlib.Path]) -> None:
        if not path:
            user32.MessageBoxW(self.hwnd, "Please select an audio file first.", "No Audio File", MB_OK | MB_ICONINFORMATION)
            return
        if not path.is_file():
            user32.MessageBoxW(self.hwnd, f"File does not exist:\n{path}", "File Not Found", MB_OK | MB_ICONWARNING)
            return
        try:
            self._log(f"Playing audio preview in system media player: {path.name}")
            os.startfile(str(path))
        except Exception as e:
            user32.MessageBoxW(self.hwnd, f"Could not launch preview:\n{e}", "Preview Error", MB_OK | MB_ICONERROR)

    # ========================================================================
    # Game Directory, ~mods Validation & Status Helpers
    # ========================================================================

    def _validate_game_dir(self, p: pathlib.Path) -> bool:
        if not p.is_dir():
            return False
        has_paks = (p / "SB" / "Content" / "Paks").is_dir()
        has_exe = (p / "SB.exe").is_file() or (p / "SB" / "Binaries" / "Win64" / "SB-Win64-Shipping.exe").is_file()
        return has_paks or has_exe

    def _update_game_status(self) -> None:
        game_dir = pathlib.Path(self._get_text(IDC_EDIT_GAME_DIR).strip())
        if self._validate_game_dir(game_dir):
            self._set_text(self.lbl_game_status, f"[OK] Stellar Blade folder verified ({game_dir})")
            self.ctrl_colors[IDC_LBL_GAME_STATUS] = self.color_green
        else:
            self._set_text(self.lbl_game_status, "[!] Game folder not found. Click 'Auto-Detect' or 'Browse...'")
            self.ctrl_colors[IDC_LBL_GAME_STATUS] = self.color_amber
        user32.InvalidateRect(self.lbl_game_status, None, 1)
        self._update_mods_status()

    def _update_mods_status(self) -> None:
        game_dir = pathlib.Path(self._get_text(IDC_EDIT_GAME_DIR).strip())
        if not self._validate_game_dir(game_dir):
            self._set_text(self.lbl_mods_status, "~mods: Waiting for game folder")
            self.ctrl_colors[IDC_LBL_MODS_STATUS] = self.color_gray
            user32.InvalidateRect(self.lbl_mods_status, None, 1)
            return

        mods_dir = game_dir / "SB" / "Content" / "Paks" / "~mods"
        cur_mod = (self._get_text(IDC_EDIT_MOD_NAME).strip() or "CampMusic_Custom_295_P")
        if not cur_mod.endswith("_P"):
            cur_mod += "_P"

        if mods_dir.is_dir():
            paks = list(mods_dir.glob("*.pak"))
            other_camp = [m for m in paks if "camp" in m.name.lower() and m.stem.lower() != cur_mod.lower()]
            this_mod_exists = (mods_dir / f"{cur_mod}.pak").is_file()
            if other_camp:
                self._set_text(self.lbl_mods_status, f"[!] {len(other_camp)} older camp mod(s) in ~mods")
                self.ctrl_colors[IDC_LBL_MODS_STATUS] = self.color_amber
            elif this_mod_exists:
                self._set_text(self.lbl_mods_status, f"[OK] {cur_mod} installed")
                self.ctrl_colors[IDC_LBL_MODS_STATUS] = self.color_green
            elif paks:
                self._set_text(self.lbl_mods_status, f"~mods ready ({len(paks)} other mod(s))")
                self.ctrl_colors[IDC_LBL_MODS_STATUS] = self.color_green
            else:
                self._set_text(self.lbl_mods_status, "~mods ready (empty)")
                self.ctrl_colors[IDC_LBL_MODS_STATUS] = self.color_green
        else:
            self._set_text(self.lbl_mods_status, "~mods will be created on build")
            self.ctrl_colors[IDC_LBL_MODS_STATUS] = self.color_blue
        user32.InvalidateRect(self.lbl_mods_status, None, 1)

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
            user32.MessageBoxW(
                self.hwnd,
                "Please select a valid Stellar Blade game folder first.",
                "Game Folder Not Found",
                MB_OK | MB_ICONWARNING,
            )
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
    # Win32 Dialogs & Text Helpers
    # ========================================================================

    def _get_text(self, hwnd_or_id: int) -> str:
        hwnd = self.controls.get(hwnd_or_id, hwnd_or_id)
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return ""
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value

    def _set_text(self, hwnd_or_id: int, text: str) -> None:
        hwnd = self.controls.get(hwnd_or_id, hwnd_or_id)
        user32.SetWindowTextW(hwnd, text)

    def _is_checked(self, ctrl_id: int) -> bool:
        return user32.SendMessageW(self.controls[ctrl_id], BM_GETCHECK, 0, 0) == BST_CHECKED

    def _set_enabled(self, ctrl_id: int, enabled: bool) -> None:
        user32.EnableWindow(self.controls[ctrl_id], 1 if enabled else 0)

    def _log(self, msg: str) -> None:
        self.log_queue.put(msg)

    def _flush_logs(self) -> None:
        if self.log_queue.empty():
            return
        hwnd_log = self.controls.get(IDC_EDIT_LOG)
        if not hwnd_log:
            return
        lines = []
        while not self.log_queue.empty():
            lines.append(self.log_queue.get_nowait())
        chunk = "\r\n".join(lines) + "\r\n"
        txt_len = user32.GetWindowTextLengthW(hwnd_log)
        user32.SendMessageW(hwnd_log, EM_SETSEL, txt_len, txt_len)
        buf = ctypes.create_unicode_buffer(chunk)
        user32.SendMessageW(hwnd_log, EM_REPLACESEL, 0, ctypes.addressof(buf))
        user32.SendMessageW(hwnd_log, EM_SCROLLCARET, 0, 0)

    def _ask_open_files(self, title: str, filter_str: str, multi: bool = True) -> List[pathlib.Path]:
        max_chars = 16384
        buf = ctypes.create_unicode_buffer(max_chars)
        ofn = OPENFILENAMEW()
        ofn.lStructSize = ctypes.sizeof(OPENFILENAMEW)
        ofn.hwndOwner = self.hwnd
        ofn.lpstrFilter = filter_str
        ofn.lpstrFile = ctypes.cast(buf, wintypes.LPWSTR)
        ofn.nMaxFile = max_chars
        ofn.lpstrTitle = title
        flags = OFN_FILEMUSTEXIST | OFN_PATHMUSTEXIST | OFN_NOCHANGEDIR
        if multi:
            flags |= OFN_ALLOWMULTISELECT | OFN_EXPLORER
        ofn.Flags = flags
        if not comdlg32.GetOpenFileNameW(ctypes.byref(ofn)):
            return []

        raw = ctypes.wstring_at(ctypes.addressof(buf), max_chars)
        parts: List[str] = []
        for token in raw.split("\x00"):
            if not token:
                break
            parts.append(token)
        if not parts:
            return []
        if len(parts) == 1:
            return [pathlib.Path(parts[0])]
        folder = pathlib.Path(parts[0])
        return [folder / name for name in parts[1:]]

    def _ask_folder(self, title: str) -> Optional[str]:
        disp_buf = ctypes.create_unicode_buffer(260)
        bi = BROWSEINFOW()
        bi.hwndOwner = self.hwnd
        bi.pszDisplayName = ctypes.cast(disp_buf, wintypes.LPWSTR)
        bi.lpszTitle = title
        bi.ulFlags = BIF_RETURNONLYFSDIRS | BIF_NEWDIALOGSTYLE
        pidl = shell32.SHBrowseForFolderW(ctypes.byref(bi))
        if not pidl:
            return None
        path_buf = ctypes.create_unicode_buffer(260)
        ok = shell32.SHGetPathFromIDListW(pidl, path_buf)
        ctypes.windll.ole32.CoTaskMemFree(ctypes.c_void_p(pidl))
        return path_buf.value if ok else None

    # ========================================================================
    # Drag & Drop Handler
    # ========================================================================

    def _on_drop_files(self, hdrop: wintypes.HANDLE) -> None:
        count = shell32.DragQueryFileW(hdrop, 0xFFFFFFFF, None, 0)
        buf = ctypes.create_unicode_buffer(1024)
        dropped_audio: List[pathlib.Path] = []
        dropped_images: List[pathlib.Path] = []

        for i in range(count):
            shell32.DragQueryFileW(hdrop, i, buf, 1024)
            path = pathlib.Path(buf.value)
            if path.is_file() and path.suffix.lower() in icm.SUPPORTED_AUDIO_EXTENSIONS:
                dropped_audio.append(path)
            elif path.is_file() and path.suffix.lower() in icm.SUPPORTED_IMAGE_EXTENSIONS:
                dropped_images.append(path)
            elif path.is_dir():
                if self._validate_game_dir(path):
                    self._set_text(IDC_EDIT_GAME_DIR, str(path))
                    self._update_game_status()
                    self._log(f"[Drag & Drop] Set Stellar Blade game directory: {path}")
                else:
                    self._load_folder_songs(path, replace=False)

        if dropped_audio:
            dropped_audio.sort(key=icm.natural_sort_key)
            added = self._add_audio_paths(dropped_audio)
            self._log(f"[Drag & Drop] Added {added} audio file(s) to playlist.")
        elif dropped_images:
            idx = self._get_selected_playlist_index()
            if idx >= 0:
                self.playlist[idx].custom_cover_path = dropped_images[0]
                self._refresh_playlist_box(select_idx=idx)
                self._log(f"[Drag & Drop] Set custom cover for '{self.playlist[idx].title}': {dropped_images[0].name}")

        shell32.DragFinish(hdrop)

    # ========================================================================
    # Event Commands
    # ========================================================================

    def _on_command(self, ctrl_id: int, notify_code: int) -> None:
        if ctrl_id == IDC_LIST_PLAYLIST and notify_code == LBN_SELCHANGE:
            self._load_selected_into_editors()

        elif ctrl_id == IDC_LIST_PLAYLIST and notify_code == LBN_DBLCLK:
            idx = self._get_selected_playlist_index()
            if idx >= 0:
                self._preview_audio(self.playlist[idx].audio_on)

        elif ctrl_id == IDC_BTN_ADD_SONGS and notify_code == BN_CLICKED:
            files = self._ask_open_files(
                "Select Audio File(s) to Add to Camp Turntable",
                "Audio Files (*.ogg;*.wav;*.mp3;*.flac;*.m4a;*.aac;*.opus)\0*.ogg;*.wav;*.mp3;*.flac;*.m4a;*.aac;*.opus\0Ogg Vorbis (*.ogg)\0*.ogg\0All Files (*.*)\0*.*\0\0",
                multi=True,
            )
            if files:
                files.sort(key=icm.natural_sort_key)
                added = self._add_audio_paths(files)
                self._log(f"Added {added} song(s) to playlist.")

        elif ctrl_id == IDC_BTN_LOAD_MUSIC and notify_code == BN_CLICKED:
            music_dir = self.root_dir / "Music"
            music_dir.mkdir(parents=True, exist_ok=True)
            self._load_folder_songs(music_dir, replace=False)

        elif ctrl_id == IDC_BTN_LOAD_FOLDER and notify_code == BN_CLICKED:
            folder = self._ask_folder("Select Folder Containing Audio Files")
            if folder:
                self._load_folder_songs(pathlib.Path(folder), replace=False)

        elif ctrl_id == IDC_BTN_MOVE_UP and notify_code == BN_CLICKED:
            idx = self._get_selected_playlist_index()
            if idx > 0:
                self.playlist[idx - 1], self.playlist[idx] = self.playlist[idx], self.playlist[idx - 1]
                self._refresh_playlist_box(select_idx=idx - 1)

        elif ctrl_id == IDC_BTN_MOVE_DOWN and notify_code == BN_CLICKED:
            idx = self._get_selected_playlist_index()
            if 0 <= idx < len(self.playlist) - 1:
                self.playlist[idx + 1], self.playlist[idx] = self.playlist[idx], self.playlist[idx + 1]
                self._refresh_playlist_box(select_idx=idx + 1)

        elif ctrl_id == IDC_BTN_REMOVE_SONG and notify_code == BN_CLICKED:
            idx = self._get_selected_playlist_index()
            if idx >= 0:
                removed = self.playlist.pop(idx)
                self._log(f"Removed song: {removed.title}")
                new_sel = min(idx, len(self.playlist) - 1)
                self._refresh_playlist_box(select_idx=new_sel)

        elif ctrl_id == IDC_BTN_CLEAR_SONGS and notify_code == BN_CLICKED:
            if self.playlist:
                self.playlist.clear()
                self._refresh_playlist_box(select_idx=-1)
                self._log("Cleared custom song playlist.")

        elif ctrl_id == IDC_BTN_PREVIEW_ON and notify_code == BN_CLICKED:
            idx = self._get_selected_playlist_index()
            self._preview_audio(self.playlist[idx].audio_on if idx >= 0 else None)

        elif ctrl_id == IDC_EDIT_TITLE and notify_code == EN_CHANGE:
            self._sync_title_from_editor()

        elif ctrl_id == IDC_BTN_RESET_TITLE and notify_code == BN_CLICKED:
            idx = self._get_selected_playlist_index()
            if idx >= 0:
                self._set_text(IDC_EDIT_TITLE, icm.infer_song_title(self.playlist[idx].audio_on))

        elif ctrl_id == IDC_BTN_BROWSE_OFF and notify_code == BN_CLICKED:
            idx = self._get_selected_playlist_index()
            if idx >= 0:
                files = self._ask_open_files(
                    "Select Optional Ambient Audio File (_OFF)",
                    "Audio Files (*.ogg;*.wav;*.mp3;*.flac;*.m4a;*.aac;*.opus)\0*.ogg;*.wav;*.mp3;*.flac;*.m4a;*.aac;*.opus\0Ogg Vorbis (*.ogg)\0*.ogg\0All Files (*.*)\0*.*\0\0",
                    multi=False,
                )
                if files:
                    self.playlist[idx].audio_off = files[0]
                    self._refresh_playlist_box(select_idx=idx)

        elif ctrl_id == IDC_BTN_PREVIEW_OFF and notify_code == BN_CLICKED:
            idx = self._get_selected_playlist_index()
            self._preview_audio(self.playlist[idx].audio_off if idx >= 0 else None)

        elif ctrl_id == IDC_BTN_CLEAR_OFF and notify_code == BN_CLICKED:
            idx = self._get_selected_playlist_index()
            if idx >= 0:
                self.playlist[idx].audio_off = None
                self._refresh_playlist_box(select_idx=idx)

        elif ctrl_id == IDC_COMBO_COVER and notify_code == CBN_SELCHANGE:
            idx = self._get_selected_playlist_index()
            if idx >= 0:
                cidx = int(user32.SendMessageW(self.controls[IDC_COMBO_COVER], CB_GETCURSEL, 0, 0))
                if 0 <= cidx < len(icm.ALBUM_COVER_PRESETS):
                    self.playlist[idx].cover_idx = cidx
                    self._set_text(self.lbl_cover_status, self._format_cover_status(self.playlist[idx]))

        elif ctrl_id == IDC_BTN_BROWSE_COVER and notify_code == BN_CLICKED:
            idx = self._get_selected_playlist_index()
            if idx >= 0:
                files = self._ask_open_files(
                    "Select Custom Album Cover Image",
                    "Image Files (*.png;*.jpg;*.jpeg;*.webp;*.bmp;*.tga)\0*.png;*.jpg;*.jpeg;*.webp;*.bmp;*.tga\0All Files (*.*)\0*.*\0\0",
                    multi=False,
                )
                if files:
                    self.playlist[idx].custom_cover_path = files[0]
                    self._refresh_playlist_box(select_idx=idx)
                    self._log(f"Set custom cover for '{self.playlist[idx].title}': {files[0].name}")

        elif ctrl_id == IDC_BTN_CLEAR_COVER and notify_code == BN_CLICKED:
            idx = self._get_selected_playlist_index()
            if idx >= 0 and self.playlist[idx].custom_cover_path is not None:
                self.playlist[idx].custom_cover_path = None
                self._refresh_playlist_box(select_idx=idx)

        elif ctrl_id == IDC_CHK_EMBEDDED_ART and notify_code == BN_CLICKED:
            self._refresh_playlist_box()

        elif ctrl_id == IDC_BTN_COVER_ALL and notify_code == BN_CLICKED:
            idx = self._get_selected_playlist_index()
            cidx = int(user32.SendMessageW(self.controls[IDC_COMBO_COVER], CB_GETCURSEL, 0, 0))
            if 0 <= cidx < len(icm.ALBUM_COVER_PRESETS):
                sel_custom = self.playlist[idx].custom_cover_path if idx >= 0 else None
                for item in self.playlist:
                    item.cover_idx = cidx
                    if sel_custom is not None:
                        item.custom_cover_path = sel_custom
                self._refresh_playlist_box(select_idx=idx)
                label = sel_custom.name if sel_custom is not None else icm.ALBUM_COVER_PRESETS[cidx][0]
                self._log(f"Applied album cover '{label}' to all {len(self.playlist)} queued song(s).")

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
            self._reset_all_defaults()

        elif ctrl_id == IDC_BTN_COPY_LOG and notify_code == BN_CLICKED:
            log_txt = self._get_text(IDC_EDIT_LOG)
            if copy_text_to_clipboard(log_txt):
                self._log("[Log copied to Windows clipboard]")

        elif ctrl_id == IDC_BTN_CLEAR_LOG and notify_code == BN_CLICKED:
            self._set_text(IDC_EDIT_LOG, "")

        elif ctrl_id == IDC_BTN_BUILD and notify_code == BN_CLICKED:
            self._start_build()

    def _reset_all_defaults(self) -> None:
        self.playlist.clear()
        self._refresh_playlist_box(select_idx=-1)
        self._set_text(IDC_EDIT_VOL_ON, "1.1")
        self._set_text(IDC_EDIT_VOL_OFF, "0.6")
        self._set_text(IDC_EDIT_MOD_NAME, "CampMusic_Custom_295_P")
        self._log("Reset playlist and volume/mod settings to defaults.")

    # ========================================================================
    # Build Mod Logic
    # ========================================================================

    def _start_build(self) -> None:
        if self.is_building:
            return

        if not self.playlist:
            user32.MessageBoxW(
                self.hwnd,
                "Your custom song playlist is empty.\n\nClick 'Add Song(s)...' or 'Load ./Music Folder' (or drag & drop audio files onto this window).",
                "No Songs Queued",
                MB_OK | MB_ICONWARNING,
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

        mod_name = self._get_text(IDC_EDIT_MOD_NAME).strip() or "CampMusic_Custom_295_P"
        out_dir = self._get_target_output_dir()
        reencode = self._is_checked(IDC_CHK_REENCODE)
        use_embedded_art = self._is_checked(IDC_CHK_EMBEDDED_ART)
        items_snapshot = list(self.playlist)

        self.is_building = True
        self._set_enabled(IDC_BTN_BUILD, False)
        self._set_text(IDC_BTN_BUILD, "Building...")
        self._set_text(self.lbl_build_status, f"Building {len(items_snapshot)} track(s)...")
        self.ctrl_colors[IDC_LBL_BUILD_STATUS] = self.color_blue
        user32.InvalidateRect(self.lbl_build_status, None, 1)

        self._log("=" * 76)
        self._log(f"Building combined Custom Camp Music Mod ({len(items_snapshot)} custom track(s), keeping all 34 original tracks)...")
        self._log(f"  Mod Name    : {mod_name}")
        self._log(f"  Destination : {out_dir}")
        self._log("-" * 76)

        def worker() -> None:
            try:
                custom_tracks: List[icm.CustomTrackInput] = []
                total = len(items_snapshot)
                for idx, item in enumerate(items_snapshot, start=1):
                    title = item.title.strip() or icm.infer_song_title(item.audio_on)
                    self._log(f"[{idx:02d}/{total:02d}] Processing +{title!r} ({item.audio_on.name})...")
                    self._set_text(self.lbl_build_status, f"Encoding [{idx}/{total}] {title}...")

                    img_path, cover_bgra, cover_lbl = icm.resolve_track_cover_art(
                        audio_path=item.audio_on,
                        fallback_image_path=icm.ALBUM_COVER_PRESETS[item.cover_idx][1],
                        custom_image_file=item.custom_cover_path,
                        use_embedded=use_embedded_art,
                    )

                    ogg_on = icm.load_or_convert_ogg(item.audio_on, force_reencode=reencode)
                    if item.audio_off and item.audio_off.is_file():
                        ogg_off = icm.load_or_convert_ogg(item.audio_off, force_reencode=reencode)
                    else:
                        ogg_off = ogg_on

                    custom_tracks.append(
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

                self._log("Synthesizing Zen assets, patching TurntableSoundTable & StringTable_UI, packing IoStore...")
                self._set_text(self.lbl_build_status, "Packing IoStore container...")

                pak_p, utoc_p, ucas_p = icm.build_custom_music_mod(
                    tracks=custom_tracks,
                    output_dir=out_dir,
                    mod_name=mod_name,
                    game_dir=game_dir if self._validate_game_dir(game_dir) else None,
                    template_ucas_path=icm.find_default_template_ucas(self.root_dir),
                    cache_dir=self.cache_dir,
                )

                self._log("=" * 76)
                self._log(f"SUCCESS! Added {len(custom_tracks)} custom track(s) (all 34 original tracks kept intact):")
                for idx, trk in enumerate(custom_tracks, start=1):
                    cov_note = f" | Cover: {trk.cover_label}" if trk.cover_label else ""
                    self._log(f"  [Custom {idx:02d}] {trk.title!r} ({trk.ogg_on.duration:.2f}s{cov_note})")
                self._log(f"  PAK  : {pak_p} ({pak_p.stat().st_size:,} bytes)")
                self._log(f"  UTOC : {utoc_p} ({utoc_p.stat().st_size:,} bytes)")
                self._log(f"  UCAS : {ucas_p} ({ucas_p.stat().st_size:,} bytes)")

                self._set_text(self.lbl_build_status, f"SUCCESS! {len(custom_tracks)} custom track(s) built.")
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
                self._set_text(IDC_BTN_BUILD, "Build Custom Music Mod")
                user32.InvalidateRect(self.lbl_build_status, None, 1)

        threading.Thread(target=worker, daemon=True).start()

    # ========================================================================
    # Window Procedure & Message Loop
    # ========================================================================

    def _wnd_proc(self, hwnd: wintypes.HWND, msg: int, wparam: int, lparam: int) -> int:
        if not getattr(self, "_ready", False):
            if msg == WM_CTLCOLORSTATIC:
                return self.brush_btnface
            if msg == WM_DESTROY:
                user32.KillTimer(hwnd, TIMER_ID_LOG)
                user32.PostQuitMessage(0)
                return 0
            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

        if msg == WM_COMMAND:
            ctrl_id = wparam & 0xFFFF
            notify_code = (wparam >> 16) & 0xFFFF
            self._on_command(ctrl_id, notify_code)
            return 0

        elif msg == WM_DROPFILES:
            self._on_drop_files(ctypes.cast(wparam, wintypes.HANDLE))
            return 0

        elif msg == WM_CTLCOLORSTATIC:
            ctrl_hwnd = lparam
            for cid, color in self.ctrl_colors.items():
                if self.controls.get(cid) == ctrl_hwnd:
                    gdi32.SetTextColor(wparam, color)
                    gdi32.SetBkMode(wparam, TRANSPARENT)
                    return self.brush_btnface
            gdi32.SetBkMode(wparam, TRANSPARENT)
            return self.brush_btnface

        elif msg == WM_TIMER and wparam == TIMER_ID_LOG:
            self._flush_logs()
            return 0

        elif msg == WM_DESTROY:
            user32.KillTimer(hwnd, TIMER_ID_LOG)
            self._save_settings()
            user32.PostQuitMessage(0)
            return 0

        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def run(self) -> int:
        user32.ShowWindow(self.hwnd, SW_SHOWNORMAL)
        user32.UpdateWindow(self.hwnd)
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if not user32.IsDialogMessageW(self.hwnd, ctypes.byref(msg)):
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        return 0


def launch_gui() -> int:
    app = CampMusicWin32GUI()
    return app.run()


if __name__ == "__main__":
    sys.exit(launch_gui())
