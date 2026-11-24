#!/usr/bin/env python3
"""
Shared Win32 GUI helpers, DLL bindings, and Stellar Blade path detection
used by both `camp_music_gui.py` and `radio_music_gui.py`.
"""

import ctypes
from ctypes import wintypes
import json
import os
import pathlib
import queue
import re
from typing import Dict, List, Optional


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
LB_INSERTSTRING = 0x0181
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


def enable_visual_styles_and_dpi() -> None:
    """Enable DPI awareness and Windows ComCtl v6 visual styles."""
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


def detect_stellar_blade_game_dir(root_dir: pathlib.Path) -> Optional[pathlib.Path]:
    """Locate the Stellar Blade installation folder via Steam registry, libraries, or local dirs."""
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


def validate_game_dir(p: pathlib.Path) -> bool:
    """Return True if `p` looks like a valid Stellar Blade root directory."""
    if not p.is_dir():
        return False
    has_paks = (p / "SB" / "Content" / "Paks").is_dir()
    has_exe = (p / "SB.exe").is_file() or (p / "SB" / "Binaries" / "Win64" / "SB-Win64-Shipping.exe").is_file()
    return has_paks or has_exe


def copy_text_to_clipboard(text: str) -> bool:
    """Copy a Unicode string to the Windows clipboard."""
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


class BaseWin32App:
    """Base Win32 desktop window providing shared fonts, dialogs, logging, and event loop."""

    class_name: str = "StellarBladeWin32App"
    default_mod_name: str = "CampMusic_Custom_295_P"

    def __init__(self, settings_filename: str) -> None:
        enable_visual_styles_and_dpi()

        self.root_dir = pathlib.Path(__file__).resolve().parent
        self.cache_dir = self.root_dir / ".cache"
        self.settings_file = self.cache_dir / settings_filename
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
        self._ready = False
        self._log_ctrl_id = 0

        self._wndproc_ref = WNDPROC(self._wnd_proc)
        self._register_class()

    def _load_settings(self) -> Dict[str, object]:
        if self.settings_file.is_file():
            try:
                return json.loads(self.settings_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def _save_settings(self) -> None:
        pass

    def _register_class(self) -> None:
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
        if self.log_queue.empty() or not self._log_ctrl_id:
            return
        hwnd_log = self.controls.get(self._log_ctrl_id)
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

    def _validate_game_dir(self, p: pathlib.Path) -> bool:
        return validate_game_dir(p)

    def _update_game_status_shared(
        self, edit_game_id: int, lbl_game_id: int, lbl_mods_id: int, edit_mod_id: int
    ) -> None:
        game_dir = pathlib.Path(self._get_text(edit_game_id).strip())
        lbl_game = self.controls[lbl_game_id]
        if self._validate_game_dir(game_dir):
            self._set_text(lbl_game, f"[OK] Stellar Blade folder verified ({game_dir})")
            self.ctrl_colors[lbl_game_id] = self.color_green
        else:
            self._set_text(lbl_game, "[!] Game folder not found. Click 'Auto-Detect' or 'Browse...'")
            self.ctrl_colors[lbl_game_id] = self.color_amber
        user32.InvalidateRect(lbl_game, None, 1)
        self._update_mods_status_shared(edit_game_id, lbl_mods_id, edit_mod_id)

    def _update_mods_status_shared(self, edit_game_id: int, lbl_mods_id: int, edit_mod_id: int) -> None:
        game_dir = pathlib.Path(self._get_text(edit_game_id).strip())
        lbl_mods = self.controls[lbl_mods_id]
        if not self._validate_game_dir(game_dir):
            self._set_text(lbl_mods, "~mods: Waiting for game folder")
            self.ctrl_colors[lbl_mods_id] = self.color_gray
            user32.InvalidateRect(lbl_mods, None, 1)
            return

        mods_dir = game_dir / "SB" / "Content" / "Paks" / "~mods"
        cur_mod = self._get_text(edit_mod_id).strip() or self.default_mod_name
        if not cur_mod.endswith("_P"):
            cur_mod += "_P"

        if mods_dir.is_dir():
            paks = list(mods_dir.glob("*.pak"))
            other_camp = [m for m in paks if "camp" in m.name.lower() and m.stem.lower() != cur_mod.lower()]
            this_mod_exists = (mods_dir / f"{cur_mod}.pak").is_file()
            if other_camp:
                self._set_text(lbl_mods, f"[!] {len(other_camp)} older camp mod(s) in ~mods")
                self.ctrl_colors[lbl_mods_id] = self.color_amber
            elif this_mod_exists:
                self._set_text(lbl_mods, f"[OK] {cur_mod} installed")
                self.ctrl_colors[lbl_mods_id] = self.color_green
            elif paks:
                self._set_text(lbl_mods, f"~mods ready ({len(paks)} other mod(s))")
                self.ctrl_colors[lbl_mods_id] = self.color_green
            else:
                self._set_text(lbl_mods, "~mods ready (empty)")
                self.ctrl_colors[lbl_mods_id] = self.color_green
        else:
            self._set_text(lbl_mods, "~mods will be created on build")
            self.ctrl_colors[lbl_mods_id] = self.color_blue
        user32.InvalidateRect(lbl_mods, None, 1)

    def _on_command(self, ctrl_id: int, notify_code: int) -> None:
        pass

    def _on_drop_files(self, hdrop: wintypes.HANDLE) -> None:
        shell32.DragFinish(hdrop)

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

        if msg == WM_DROPFILES:
            self._on_drop_files(ctypes.cast(wparam, wintypes.HANDLE))
            return 0

        if msg == WM_CTLCOLORSTATIC:
            ctrl_hwnd = lparam
            for cid, color in self.ctrl_colors.items():
                if self.controls.get(cid) == ctrl_hwnd:
                    gdi32.SetTextColor(wparam, color)
                    gdi32.SetBkMode(wparam, TRANSPARENT)
                    return self.brush_btnface
            gdi32.SetBkMode(wparam, TRANSPARENT)
            return self.brush_btnface

        if msg == WM_TIMER and wparam == TIMER_ID_LOG:
            self._flush_logs()
            return 0

        if msg == WM_DESTROY:
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
