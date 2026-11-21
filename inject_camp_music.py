#!/usr/bin/env python3
"""
Stellar Blade Custom Camp Music Injector & IoStore (.pak / .utoc / .ucas) Builder
=================================================================================
Builds Unreal Engine 4.26.2 Zen Loader / IoStore mod containers (<ModName>_P.{pak,utoc,ucas})
to inject your own custom music tracks into Stellar Blade's Camp Turntable WHILE keeping all
34 original in-game tracks intact, with automatic UConstantQNRT visualizer generation and
StringTable_UI.uasset title injection across all game languages.
"""

import argparse
import base64
import ctypes
import dataclasses
import hashlib
import io
import pathlib
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import uuid
import zlib
from typing import Callable, Dict, List, Optional, Tuple, Union


# ============================================================================
# 1. Google CityHash64 & Unreal Engine 4.26 FNV64 / CRC32 Implementations
# ============================================================================

_K0 = 0xC3A5C85C97CB3127
_K1 = 0xB492B66FBE98F273
_K2 = 0x9AE16A3B2F90404F
_M64 = 0xFFFFFFFFFFFFFFFF


def _u64(b: bytes, off: int = 0) -> int:
    return struct.unpack_from("<Q", b, off)[0]


def _u32(b: bytes, off: int = 0) -> int:
    return struct.unpack_from("<I", b, off)[0]


def _rotr(val: int, shift: int) -> int:
    val &= _M64
    return ((val >> shift) | (val << (64 - shift))) & _M64


def _shift_mix(val: int) -> int:
    val &= _M64
    return (val ^ (val >> 47)) & _M64


def _bswap64(val: int) -> int:
    return struct.unpack("<Q", struct.pack(">Q", val & _M64))[0]


def _hash_len_16(u: int, v: int, mul: int = 0x9DDFEA08EB382D69) -> int:
    u &= _M64
    v &= _M64
    mul &= _M64
    a = ((u ^ v) * mul) & _M64
    a ^= a >> 47
    b = ((v ^ a) * mul) & _M64
    b ^= b >> 47
    return (b * mul) & _M64


def _hash_len_0_to_16(s: bytes) -> int:
    l = len(s)
    if l >= 8:
        mul = (_K2 + l * 2) & _M64
        a = (_u64(s, 0) + _K2) & _M64
        b = _u64(s, l - 8)
        c = (_rotr(b, 37) * mul + a) & _M64
        d = ((_rotr(a, 25) + b) * mul) & _M64
        return _hash_len_16(c, d, mul)
    if l >= 4:
        mul = (_K2 + l * 2) & _M64
        a = _u32(s, 0)
        return _hash_len_16((l + (a << 3)) & _M64, _u32(s, l - 4), mul)
    if l > 0:
        a = s[0]
        b = s[l >> 1]
        c = s[l - 1]
        y = a + (b << 8)
        z = l + (c << 2)
        return (_shift_mix((y * _K2) ^ (z * _K0)) * _K2) & _M64
    return _K2


def _hash_len_17_to_32(s: bytes) -> int:
    l = len(s)
    mul = (_K2 + l * 2) & _M64
    a = (_u64(s, 0) * _K1) & _M64
    b = _u64(s, 8)
    c = (_u64(s, l - 8) * mul) & _M64
    d = (_u64(s, l - 16) * _K2) & _M64
    return _hash_len_16(
        (_rotr(a + b, 43) + _rotr(c, 30) + d) & _M64,
        (a + _rotr(b + _K2, 18) + c) & _M64,
        mul,
    )


def _hash_len_33_to_64(s: bytes) -> int:
    l = len(s)
    mul = (_K2 + l * 2) & _M64
    a = (_u64(s, 0) * _K2) & _M64
    b = _u64(s, 8)
    c = _u64(s, l - 24)
    d = _u64(s, l - 32)
    e = (_u64(s, 16) * _K2) & _M64
    f = (_u64(s, 24) * 9) & _M64
    g = _u64(s, l - 8)
    h = (_u64(s, l - 16) * mul) & _M64
    u = (_rotr(a + g, 43) + (_rotr(b, 30) + c) * 9) & _M64
    v = (((a + g) ^ d) + f + 1) & _M64
    w = (_bswap64((u + v) * mul) + h) & _M64
    x = (_rotr(e + f, 42) + c) & _M64
    y = ((_bswap64((v + w) * mul) + g) * mul) & _M64
    z = (e + f + c) & _M64
    a = (_bswap64((x + z) * mul + y) + b) & _M64
    b = (_shift_mix((z + a) * mul + d + h) * mul) & _M64
    return (b + x) & _M64


def _weak_hash_len_32_with_seeds(s: bytes, off: int, a: int, b: int) -> Tuple[int, int]:
    w = _u64(s, off)
    x = _u64(s, off + 8)
    y = _u64(s, off + 16)
    z = _u64(s, off + 24)
    a = (a + w) & _M64
    b = _rotr(b + a + z, 21)
    c = a
    a = (a + x + y) & _M64
    b = (b + _rotr(a, 44)) & _M64
    return ((a + z) & _M64, (b + c) & _M64)


def cityhash64(s: bytes) -> int:
    """Compute Google CityHash64 as used by Unreal Engine 4.26."""
    l = len(s)
    if l <= 16:
        return _hash_len_0_to_16(s)
    if l <= 32:
        return _hash_len_17_to_32(s)
    if l <= 64:
        return _hash_len_33_to_64(s)
    x = _u64(s, l - 40)
    y = (_u64(s, l - 16) + _u64(s, l - 56)) & _M64
    z = _hash_len_16(_u64(s, l - 48) + l, _u64(s, l - 24))
    v = _weak_hash_len_32_with_seeds(s, l - 64, l, z)
    w = _weak_hash_len_32_with_seeds(s, l - 32, y + _K1, x)
    x = (x * _K1 + _u64(s, 0)) & _M64
    l = (l - 1) & ~63
    off = 0
    while True:
        x = (_rotr(x + y + v[0] + _u64(s, off + 8), 37) * _K1) & _M64
        y = (_rotr(y + v[1] + _u64(s, off + 48), 42) * _K1) & _M64
        x ^= w[1]
        y = (y + v[0] + _u64(s, off + 40)) & _M64
        z = (_rotr(z + w[0], 33) * _K1) & _M64
        v = _weak_hash_len_32_with_seeds(s, off, v[1] * _K1, x + w[0])
        w = _weak_hash_len_32_with_seeds(s, off + 32, z + w[1], y + _u64(s, off + 16))
        z, x = x, z
        off += 64
        l -= 64
        if l == 0:
            break
    return _hash_len_16(
        _hash_len_16(v[0], w[0]) + _shift_mix(y) * _K1 + z,
        _hash_len_16(v[1], w[1]) + x,
    )


def calc_package_id(package_path: str) -> int:
    """Compute UE4.26 FPackageId::FromName (CityHash64 of lowercase UTF-16LE path)."""
    return cityhash64(package_path.lower().encode("utf-16le"))


def calc_global_import_index(object_path: str) -> int:
    """Compute UE4.26 FPackageObjectIndex for a PackageImport / GlobalImportIndex."""
    h = cityhash64(object_path.lower().encode("utf-16le"))
    return (2 << 62) | (h & 0x3FFFFFFFFFFFFFFF)


def ue4_fnv64_path_hash(rel_path: str, path_hash_seed: int) -> int:
    """Compute UE4.26 FPakFile::HashPath (FNV64 over lowercase UTF-16LE bytes)."""
    fnv_offset = (0xCBF29CE484222325 + path_hash_seed) & _M64
    fnv_prime = 0x00000100000001B3
    h = fnv_offset
    for b in rel_path.lower().encode("utf-16le"):
        h ^= b
        h = (h * fnv_prime) & _M64
    return h


# ============================================================================
# 2. Catalog of All 34 Camp Turntable Tracks in Stellar Blade
# ============================================================================

@dataclasses.dataclass(frozen=True)
class CampTrackSpec:
    index: int
    ui_key: str
    title: str
    on_pkg: str
    off_pkg: str
    nrt_pkg: str

    @property
    def on_name(self) -> str:
        return self.on_pkg.rsplit("/", 1)[-1]

    @property
    def off_name(self) -> str:
        return self.off_pkg.rsplit("/", 1)[-1]

    @property
    def nrt_name(self) -> str:
        return self.nrt_pkg.rsplit("/", 1)[-1]

    @property
    def on_id(self) -> int:
        return calc_package_id(self.on_pkg)

    @property
    def off_id(self) -> int:
        return calc_package_id(self.off_pkg)

    @property
    def nrt_id(self) -> int:
        return calc_package_id(self.nrt_pkg)


CAMP_TRACKS: List[CampTrackSpec] = [
    CampTrackSpec(1,  "UI_Turntable_Music_001",          "The Song of the Sirens",           "/Game/Sound/World/BGM/VendingMachine/BGM_CAMP_MV1_ON",                   "/Game/Sound/World/BGM/VendingMachine/BGM_CAMP_MV1_OFF",                   "/Game/Sound/World/BGM/VendingMachine/BGM_Camp_MV1_ON_NRT"),
    CampTrackSpec(2,  "UI_Turntable_Music_002",          "The Song of the Wanderer",         "/Game/Sound/World/BGM/VendingMachine/BGM_CAMP_MV3_ON",                   "/Game/Sound/World/BGM/VendingMachine/BGM_CAMP_MV3_OFF",                   "/Game/Sound/World/BGM/VendingMachine/BGM_CAMP_MV3_ON_NRT"),
    CampTrackSpec(3,  "UI_Turntable_Music_003",          "The Song of the Traveler",         "/Game/Sound/World/BGM/VendingMachine/BGM_CAMP_MV4_ON",                   "/Game/Sound/World/BGM/VendingMachine/BGM_CAMP_MV4_OFF",                   "/Game/Sound/World/BGM/VendingMachine/BGM_CAMP_MV4_ON_NRT"),
    CampTrackSpec(4,  "UI_Turntable_Music_004",          "The Song of the Nomad",            "/Game/Sound/World/BGM/VendingMachine/BGM_CAMP_MV2_ON",                   "/Game/Sound/World/BGM/VendingMachine/BGM_CAMP_MV2_OFF",                   "/Game/Sound/World/BGM/VendingMachine/BGM_CAMP_MV2_ON_NRT"),
    CampTrackSpec(5,  "UI_Turntable_Music_005",          "Oasis",                            "/Game/Sound/World/BGM/E05/BGM_E05_EVENT_Oasis_Camp",                     "/Game/Sound/World/BGM/E05/BGM_E05_EVENT_OASIS_MONO",                      "/Game/Sound/World/BGM/VendingMachine/BGM_E05_EVENT_Oasis_Camp_NRT"),
    CampTrackSpec(6,  "UI_Turntable_Music_006",          "Don't Forget Me",                  "/Game/Sound/World/BGM/E05/BGM_E05_EVENT_OASIS_SUMMER_CAMP",              "/Game/Sound/World/BGM/E05/BGM_E05_EVENT_OASIS_SUMMER_MONO",               "/Game/Sound/World/BGM/VendingMachine/BGM_E05_EVENT_OASIS_SUMMER_CAMP_NRT"),
    CampTrackSpec(7,  "UI_Turntable_Music_007",          "Lullaby of Secret",                "/Game/Sound/World/BGM/VendingMachine/BGM_CAMP_YJ1_Lullaby_of_Secret_ON", "/Game/Sound/World/BGM/VendingMachine/BGM_CAMP_YJ1_Lullaby_of_Secret_OFF", "/Game/Sound/World/BGM/VendingMachine/BGM_CAMP_YJ1_Lullaby_of_Secret_ON_NRT"),
    CampTrackSpec(8,  "UI_Turntable_Music_008",          "Just Fine",                        "/Game/Sound/World/BGM/VendingMachine/BGM_CAMP_YJ2_Just_Fine_ON",         "/Game/Sound/World/BGM/VendingMachine/BGM_CAMP_YJ2_Just_Fine_OFF",         "/Game/Sound/World/BGM/VendingMachine/BGM_CAMP_YJ2_Just_Fine_ON_NRT"),
    CampTrackSpec(9,  "UI_Turntable_Music_009",          "Blur",                             "/Game/Sound/World/BGM/VendingMachine/BGM_CAMP_YJ3_Blur_ON",              "/Game/Sound/World/BGM/VendingMachine/BGM_CAMP_YJ3_Blur_OFF",              "/Game/Sound/World/BGM/VendingMachine/BGM_CAMP_YJ3_Blur_ON_NRT"),
    CampTrackSpec(10, "UI_Turntable_Music_Nier_02",      "Voice of no Return",               "/Game/Sound/World/BGM/Nier/BGM_NIER_CAMP_ON",                            "/Game/Sound/World/BGM/Nier/BGM_NIER_CAMP_OFF",                            "/Game/Sound/World/BGM/VendingMachine/BGM_NIER_CAMP_ON_NRT"),
    CampTrackSpec(11, "UI_Turntable_Music_Nier_01",      "Emil's Shop",                      "/Game/Sound/World/BGM/Nier/BGM_NIER_EMIL_ON",                            "/Game/Sound/World/BGM/Nier/BGM_NIER_EMIL_OFF",                            "/Game/Sound/World/BGM/VendingMachine/BGM_NIER_EMIL_ON_NRT"),
    CampTrackSpec(12, "UI_Turntable_Music_Christmas_01", "Take me away",                     "/Game/Sound/World/BGM/VendingMachine/BGM_CAMP_WINTER_02_ON",             "/Game/Sound/World/BGM/VendingMachine/BGM_CAMP_WINTER_02_OFF",             "/Game/Sound/World/BGM/VendingMachine/BGM_CAMP_WINTER_02_ON_NRT"),
    CampTrackSpec(13, "UI_Turntable_Music_Christmas_02", "Dawn (Winter)",                    "/Game/Sound/World/BGM/VendingMachine/BGM_CAMP_WINTER_ON",                "/Game/Sound/World/BGM/VendingMachine/BGM_CAMP_WINTER_OFF",                "/Game/Sound/World/BGM/VendingMachine/BGM_CAMP_WINTER_ON_NRT"),
    CampTrackSpec(14, "UI_Turntable_Music_Nikke_01",     "Good Day Commander",               "/Game/Sound/World/BGM/Nikke/Camp/BGM_CAMP_NIKKE_01_ON",                  "/Game/Sound/World/BGM/Nikke/Camp/BGM_CAMP_NIKKE_01_OFF",                  "/Game/Sound/World/BGM/Nikke/Camp/BGM_CAMP_NIKKE_01_NRT_CAMP"),
    CampTrackSpec(15, "UI_Turntable_Music_Nikke_02",     "Meditation",                       "/Game/Sound/World/BGM/Nikke/Camp/BGM_CAMP_NIKKE_02_ON",                  "/Game/Sound/World/BGM/Nikke/Camp/BGM_CAMP_NIKKE_02_OFF",                  "/Game/Sound/World/BGM/Nikke/Camp/BGM_CAMP_NIKKE_02_NRT_CAMP"),
    CampTrackSpec(16, "UI_Turntable_Music_Nikke_03",     "Lovely Lonely Cat",                "/Game/Sound/World/BGM/Nikke/Camp/BGM_CAMP_NIKKE_03_ON",                  "/Game/Sound/World/BGM/Nikke/Camp/BGM_CAMP_NIKKE_03_OFF",                  "/Game/Sound/World/BGM/Nikke/Camp/BGM_CAMP_NIKKE_03_NRT_CAMP"),
    CampTrackSpec(17, "UI_Turntable_Music_Nikke_04",     "COLORLESS",                        "/Game/Sound/World/BGM/Nikke/Camp/BGM_CAMP_NIKKE_04_ON",                  "/Game/Sound/World/BGM/Nikke/Camp/BGM_CAMP_NIKKE_04_OFF",                  "/Game/Sound/World/BGM/Nikke/Camp/BGM_CAMP_NIKKE_04_NRT_CAMP"),
    CampTrackSpec(18, "UI_Turntable_Music_Nikke_05",     "In Neverland",                     "/Game/Sound/World/BGM/Nikke/Camp/BGM_CAMP_NIKKE_05_ON",                  "/Game/Sound/World/BGM/Nikke/Camp/BGM_CAMP_NIKKE_05_OFF",                  "/Game/Sound/World/BGM/Nikke/Camp/BGM_CAMP_NIKKE_05_NRT_CAMP"),
    CampTrackSpec(19, "UI_Turntable_Music_Nikke_06",     "Midnight Memories",                "/Game/Sound/World/BGM/Nikke/Camp/BGM_CAMP_NIKKE_06_ON",                  "/Game/Sound/World/BGM/Nikke/Camp/BGM_CAMP_NIKKE_06_OFF",                  "/Game/Sound/World/BGM/Nikke/Camp/BGM_CAMP_NIKKE_06_NRT_CAMP"),
    CampTrackSpec(20, "UI_Turntable_Music_Nikke_07",     "Summer Seaside",                   "/Game/Sound/World/BGM/Nikke/Camp/BGM_CAMP_NIKKE_07_ON",                  "/Game/Sound/World/BGM/Nikke/Camp/BGM_CAMP_NIKKE_07_OFF",                  "/Game/Sound/World/BGM/Nikke/Camp/BGM_CAMP_NIKKE_07_NRT_CAMP"),
    CampTrackSpec(21, "UI_Turntable_Music_Nikke_08",     "Camellia",                         "/Game/Sound/World/BGM/Nikke/Camp/BGM_CAMP_NIKKE_08_ON",                  "/Game/Sound/World/BGM/Nikke/Camp/BGM_CAMP_NIKKE_08_OFF",                  "/Game/Sound/World/BGM/Nikke/Camp/BGM_CAMP_NIKKE_08_NRT_CAMP"),
    CampTrackSpec(22, "UI_Turntable_Music_Bundle_01",    "Don't Forget Me (Trio)",           "/Game/Sound/World/BGM/VendingMachine/BGM_CAMP_JZ01_DFM_ON",              "/Game/Sound/World/BGM/VendingMachine/BGM_CAMP_JZ01_DFM_OFF",              "/Game/Sound/World/BGM/VendingMachine/BGM_CAMP_JZ01_DFM_NRT"),
    CampTrackSpec(23, "UI_Turntable_Music_Bundle_02",    "Flooded Commercial Sector (Trio)", "/Game/Sound/World/BGM/VendingMachine/BGM_CAMP_JZ02_FCS_ON",              "/Game/Sound/World/BGM/VendingMachine/BGM_CAMP_JZ02_FCS_OFF",              "/Game/Sound/World/BGM/VendingMachine/BGM_CAMP_JZ02_FCS_NRT"),
    CampTrackSpec(24, "UI_Turntable_Music_Bundle_03",    "Clock Tower (Trio)",               "/Game/Sound/World/BGM/VendingMachine/BGM_CAMP_JZ03_CT_ON",               "/Game/Sound/World/BGM/VendingMachine/BGM_CAMP_JZ03_CT_OFF",               "/Game/Sound/World/BGM/VendingMachine/BGM_CAMP_JZ03_CT_NRT"),
    CampTrackSpec(25, "UI_Turntable_Music_Bundle_04",    "White Night (Trio)",               "/Game/Sound/World/BGM/VendingMachine/BGM_CAMP_JZ04_WN_ON",               "/Game/Sound/World/BGM/VendingMachine/BGM_CAMP_JZ04_WN_OFF",               "/Game/Sound/World/BGM/VendingMachine/BGM_CAMP_JZ04_WN_NRT"),
    CampTrackSpec(26, "UI_Turntable_Music_Bundle_05",    "Wasteland - Reboot (Trio)",        "/Game/Sound/World/BGM/VendingMachine/BGM_CAMP_JZ05_WLR_ON",              "/Game/Sound/World/BGM/VendingMachine/BGM_CAMP_JZ05_WLR_OFF",              "/Game/Sound/World/BGM/VendingMachine/BGM_CAMP_JZ05_WLR_NRT"),
    CampTrackSpec(27, "UI_Turntable_Music_Bundle_06",    "Oasis (Trio)",                     "/Game/Sound/World/BGM/VendingMachine/BGM_CAMP_JZ06_OASIS_ON",            "/Game/Sound/World/BGM/VendingMachine/BGM_CAMP_JZ06_OASIS_OFF",            "/Game/Sound/World/BGM/VendingMachine/BGM_CAMP_JZ06_OASIS_NRT"),
    CampTrackSpec(28, "UI_Turntable_Music_Bundle_07",    "Don't Forget Me (Refresh)",        "/Game/Sound/World/BGM/VendingMachine/BGM_CAMP_JZ07_DFMV_ON",             "/Game/Sound/World/BGM/VendingMachine/BGM_CAMP_JZ07_DFMV_OFF",             "/Game/Sound/World/BGM/VendingMachine/BGM_CAMP_JZ07_DFMV_NRT"),
    CampTrackSpec(29, "UI_Turntable_Music_Bundle_08",    "The Song of the Sirens (Arrange)", "/Game/Sound/World/BGM/VendingMachine/BGM_CAMP_AR2_01_SIRENS_ON",         "/Game/Sound/World/BGM/VendingMachine/BGM_CAMP_AR2_01_SIRENS_OFF",         "/Game/Sound/World/BGM/VendingMachine/BGM_CAMP_AR2_01_SIRENS_NRT"),
    CampTrackSpec(30, "UI_Turntable_Music_Bundle_09",    "Star Descent (Arrange)",           "/Game/Sound/World/BGM/VendingMachine/BGM_CAMP_AR2_02_SD_ON",             "/Game/Sound/World/BGM/VendingMachine/BGM_CAMP_AR2_02_SD_OFF",             "/Game/Sound/World/BGM/VendingMachine/BGM_CAMP_AR2_02_SD_NRT"),
    CampTrackSpec(31, "UI_Turntable_Music_Bundle_10",    "Arisa (Arrange)",                  "/Game/Sound/World/BGM/VendingMachine/BGM_CAMP_AR2_03_ARISA_ON",          "/Game/Sound/World/BGM/VendingMachine/BGM_CAMP_AR2_03_ARISA_OFF",          "/Game/Sound/World/BGM/VendingMachine/BGM_CAMP_AR2_03_ARISA_NRT"),
    CampTrackSpec(32, "UI_Turntable_Music_Bundle_11",    "Democrawler (Arrange)",            "/Game/Sound/World/BGM/VendingMachine/BGM_CAMP_AR2_04_DC_ON",             "/Game/Sound/World/BGM/VendingMachine/BGM_CAMP_AR2_04_DC_OFF",             "/Game/Sound/World/BGM/VendingMachine/BGM_CAMP_AR2_04_DC_NRT"),
    CampTrackSpec(33, "UI_Turntable_Music_Bundle_12",    "Everglow (Arrange)",               "/Game/Sound/World/BGM/VendingMachine/BGM_CAMP_AR2_05_EG_ON",             "/Game/Sound/World/BGM/VendingMachine/BGM_CAMP_AR2_05_EG_OFF",             "/Game/Sound/World/BGM/VendingMachine/BGM_CAMP_AR2_05_EG_NRT"),
    CampTrackSpec(34, "UI_Turntable_Music_Bundle_13",    "Hypertube (Arrange)",              "/Game/Sound/World/BGM/VendingMachine/BGM_CAMP_AR2_06_HT_ON",             "/Game/Sound/World/BGM/VendingMachine/BGM_CAMP_AR2_06_HT_OFF",             "/Game/Sound/World/BGM/VendingMachine/BGM_CAMP_AR2_06_HT_NRT"),
]


def resolve_track(query: str) -> CampTrackSpec:
    q = query.strip()
    if q.isdigit():
        idx = int(q)
        for t in CAMP_TRACKS:
            if t.index == idx:
                return t
    q_low = q.lower()
    for t in CAMP_TRACKS:
        if q_low in (t.ui_key.lower(), t.title.lower(), t.on_name.lower(), t.off_name.lower(), t.on_name[:-3].lower()):
            return t
    matches = [
        t for t in CAMP_TRACKS
        if q_low in t.title.lower() or q_low in t.ui_key.lower() or q_low in t.on_name.lower()
    ]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        names = ", ".join(f"[{m.index}] {m.title}" for m in matches)
        raise ValueError(f"Ambiguous track query {query!r}; matches: {names}")
    raise ValueError(f"Unknown track query {query!r}. Use --list-tracks to see all 34 tracks.")


SUPPORTED_AUDIO_EXTENSIONS = {".ogg", ".wav", ".mp3", ".flac", ".m4a", ".aac", ".wma", ".opus"}
SUPPORTED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tga", ".tif", ".tiff"}

TRACK_CATEGORIES: List[Tuple[str, int, int]] = [
    ("All Tracks (1 - 34)", 1, 34),
    ("Base Camp Tracks (1 - 9)", 1, 9),
    ("NieR:Automata DLC (10 - 11)", 10, 11),
    ("Holiday Specials (12 - 13)", 12, 13),
    ("NIKKE DLC (14 - 21)", 14, 21),
    ("Enya's Gift Bundle (22 - 34)", 22, 34),
]


def natural_sort_key(p: Union[pathlib.Path, str]) -> List[Union[int, str]]:
    """Alphanumeric natural sorting key (e.g. '02' comes before '10')."""
    name = p.name if isinstance(p, pathlib.Path) else str(p)
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r"(\d+)", name)]


def clean_title_from_stem(stem: str) -> str:
    """Format an audio file stem into a clean display title."""
    clean = re.sub(r"^(?:track\s*)?\d+[\s\-_]+", "", stem, flags=re.IGNORECASE)
    clean = re.sub(r"[\-_]+", " ", clean).strip()
    if clean.isupper() or clean.islower():
        clean = clean.title()
    return clean or stem


def _format_song_name(raw_name: str) -> str:
    clean = re.sub(r"\s+", " ", raw_name).strip()
    if clean.isupper() or clean.islower():
        clean = clean.title()
    return clean


def _parse_vorbis_comment_block(payload: bytes) -> Dict[str, str]:
    tags: Dict[str, str] = {}
    if len(payload) < 8:
        return tags
    vlen = struct.unpack_from("<I", payload, 0)[0]
    p = 4 + vlen
    if p + 4 > len(payload):
        return tags
    cnt = struct.unpack_from("<I", payload, p)[0]
    p += 4
    for _ in range(min(cnt, 512)):
        if p + 4 > len(payload):
            break
        elen = struct.unpack_from("<I", payload, p)[0]
        p += 4
        if p + elen > len(payload):
            break
        entry = payload[p : p + elen].decode("utf-8", errors="replace")
        p += elen
        if "=" in entry:
            k, v = entry.split("=", 1)
            k_up = k.strip().upper()
            v_clean = v.strip()
            if k_up and v_clean and k_up not in tags:
                tags[k_up] = v_clean
    return tags


def _read_ogg_tags(head: bytes) -> Dict[str, str]:
    pos = 0
    packets: List[bytes] = []
    cur_pkt = bytearray()
    while pos + 27 <= len(head) and len(packets) < 2:
        if head[pos : pos + 4] != b"OggS":
            nxt = head.find(b"OggS", pos + 1)
            if nxt == -1:
                break
            pos = nxt
            continue
        seg_cnt = head[pos + 26]
        if pos + 27 + seg_cnt > len(head):
            break
        seg_table = head[pos + 27 : pos + 27 + seg_cnt]
        data_pos = pos + 27 + seg_cnt
        total_body = sum(seg_table)
        if data_pos + total_body > len(head):
            break
        for seg_len in seg_table:
            cur_pkt.extend(head[data_pos : data_pos + seg_len])
            data_pos += seg_len
            if seg_len < 255:
                packets.append(bytes(cur_pkt))
                cur_pkt.clear()
                if len(packets) >= 2:
                    break
        pos = data_pos
    if len(packets) < 2:
        return {}
    pkt = packets[1]
    if pkt.startswith(b"\x03vorbis"):
        return _parse_vorbis_comment_block(pkt[7:])
    if pkt.startswith(b"OpusTags"):
        return _parse_vorbis_comment_block(pkt[8:])
    return {}


def _read_flac_tags(head: bytes) -> Dict[str, str]:
    if not head.startswith(b"fLaC"):
        return {}
    p = 4
    while p + 4 <= len(head):
        hdr = head[p]
        is_last = (hdr & 0x80) != 0
        btype = hdr & 0x7F
        blen = int.from_bytes(head[p + 1 : p + 4], "big")
        p += 4
        if p + blen > len(head):
            break
        if btype == 4:
            return _parse_vorbis_comment_block(head[p : p + blen])
        p += blen
        if is_last:
            break
    return {}


def _decode_id3_text(raw: bytes) -> str:
    if not raw:
        return ""
    enc = raw[0]
    body = raw[1:]
    if enc == 0:
        return body.decode("latin1", errors="replace").rstrip("\x00").strip()
    if enc == 1:
        return body.decode("utf-16", errors="replace").rstrip("\x00").strip()
    if enc == 2:
        return body.decode("utf-16be", errors="replace").rstrip("\x00").strip()
    if enc == 3:
        return body.decode("utf-8", errors="replace").rstrip("\x00").strip()
    return raw.decode("utf-8", errors="replace").rstrip("\x00").strip()


def _read_id3_tags(head: bytes, tail: bytes) -> Dict[str, str]:
    tags: Dict[str, str] = {}
    if len(head) >= 10 and head[:3] == b"ID3":
        ver_maj = head[3]
        sz = (
            ((head[6] & 0x7F) << 21)
            | ((head[7] & 0x7F) << 14)
            | ((head[8] & 0x7F) << 7)
            | (head[9] & 0x7F)
        )
        end = min(len(head), 10 + sz)
        p = 10
        if ver_maj == 2:
            while p + 6 <= end:
                fid = head[p : p + 3].decode("latin1", errors="replace")
                fsz = int.from_bytes(head[p + 3 : p + 6], "big")
                p += 6
                if fsz <= 0 or p + fsz > end:
                    break
                if fid == "TT2":
                    tags["TITLE"] = _decode_id3_text(head[p : p + fsz])
                elif fid == "TP1":
                    tags["ARTIST"] = _decode_id3_text(head[p : p + fsz])
                elif fid == "TP2":
                    tags["ALBUMARTIST"] = _decode_id3_text(head[p : p + fsz])
                p += fsz
        elif ver_maj in (3, 4):
            if head[5] & 0x40 and p + 4 <= end:
                ext_sz = struct.unpack_from(">I", head, p)[0]
                p += ext_sz if ver_maj == 4 else (4 + ext_sz)
            while p + 10 <= end:
                fid = head[p : p + 4].decode("latin1", errors="replace")
                if fid == "\x00\x00\x00\x00":
                    break
                if ver_maj == 4:
                    fsz = (
                        ((head[p + 4] & 0x7F) << 21)
                        | ((head[p + 5] & 0x7F) << 14)
                        | ((head[p + 6] & 0x7F) << 7)
                        | (head[p + 7] & 0x7F)
                    )
                else:
                    fsz = struct.unpack_from(">I", head, p + 4)[0]
                p += 10
                if fsz <= 0 or p + fsz > end:
                    break
                if fid == "TIT2":
                    tags["TITLE"] = _decode_id3_text(head[p : p + fsz])
                elif fid == "TPE1":
                    tags["ARTIST"] = _decode_id3_text(head[p : p + fsz])
                elif fid == "TPE2":
                    tags["ALBUMARTIST"] = _decode_id3_text(head[p : p + fsz])
                p += fsz
    if not tags and len(tail) == 128 and tail[:3] == b"TAG":
        t = tail[3:33].split(b"\x00", 1)[0].decode("latin1", errors="replace").strip()
        a = tail[33:63].split(b"\x00", 1)[0].decode("latin1", errors="replace").strip()
        if t:
            tags["TITLE"] = t
        if a:
            tags["ARTIST"] = a
    return tags


def _read_mp4_tags(head: bytes) -> Dict[str, str]:
    tags: Dict[str, str] = {}
    def walk(buf: bytes, start: int, end: int) -> None:
        p = start
        while p + 8 <= end:
            bsz = struct.unpack_from(">I", buf, p)[0]
            btype = buf[p + 4 : p + 8]
            if bsz < 8 or p + bsz > end:
                break
            body_start = p + 8
            if btype in (b"moov", b"udta", b"ilst"):
                walk(buf, body_start, p + bsz)
            elif btype == b"meta":
                walk(buf, body_start + 4, p + bsz)
            elif btype in (b"\xa9nam", b"\xa9ART", b"aART"):
                sub = body_start
                while sub + 8 <= p + bsz:
                    ssz = struct.unpack_from(">I", buf, sub)[0]
                    styp = buf[sub + 4 : sub + 8]
                    if ssz < 16 or sub + ssz > p + bsz:
                        break
                    if styp == b"data":
                        txt = buf[sub + 16 : sub + ssz].decode("utf-8", errors="replace").strip()
                        if txt:
                            if btype == b"\xa9nam":
                                tags["TITLE"] = txt
                            elif btype == b"\xa9ART":
                                tags["ARTIST"] = txt
                            elif btype == b"aART":
                                tags["ALBUMARTIST"] = txt
                        break
                    sub += ssz
            p += bsz
    walk(head, 0, len(head))
    return tags


def extract_audio_metadata(audio_path: pathlib.Path) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract (title, artist) from embedded audio metadata tags (Vorbis, FLAC, ID3, MP4)
    or ffprobe if available.
    """
    title: Optional[str] = None
    artist: Optional[str] = None

    # 1. Try mutagen first (handles large picture metadata headers without truncation)
    try:
        import mutagen  # type: ignore
        mf = mutagen.File(str(audio_path), easy=True)
        if mf is not None and getattr(mf, "tags", None):
            t_vals = mf.tags.get("title")
            a_vals = mf.tags.get("artist") or mf.tags.get("albumartist")
            if t_vals:
                title = str(t_vals[0]).strip() or None
            if a_vals:
                artist = str(a_vals[0]).strip() or None
            if title is not None and artist is not None:
                return title, artist
    except Exception:
        pass

    # 2. Pure-Python fallback (reads up to 16 MB so large METADATA_BLOCK_PICTURE blocks don't truncate tags)
    tags: Dict[str, str] = {}
    try:
        with audio_path.open("rb") as f:
            head = f.read(16 * 1024 * 1024)
            f.seek(0, 2)
            fsize = f.tell()
            tail = b""
            if fsize >= 128:
                f.seek(fsize - 128)
                tail = f.read(128)
        if head.startswith(b"OggS"):
            tags = _read_ogg_tags(head)
        elif head.startswith(b"fLaC"):
            tags = _read_flac_tags(head)
        elif head.startswith(b"ID3") or tail.startswith(b"TAG"):
            tags = _read_id3_tags(head, tail)
        elif len(head) >= 8 and head[4:8] == b"ftyp":
            tags = _read_mp4_tags(head)
    except Exception:
        pass

    title = title or tags.get("TITLE") or None
    artist = artist or tags.get("ARTIST") or tags.get("ALBUMARTIST") or None

    if (title is None or artist is None) and shutil.which("ffprobe"):
        try:
            import json
            res = subprocess.run(
                [
                    "ffprobe", "-v", "quiet",
                    "-print_format", "json",
                    "-show_entries", "format_tags=title,artist,album_artist",
                    str(audio_path),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if res.returncode == 0 and res.stdout:
                ftags = json.loads(res.stdout).get("format", {}).get("tags", {})
                norm = {str(k).upper(): str(v).strip() for k, v in ftags.items() if str(v).strip()}
                title = title or norm.get("TITLE")
                artist = artist or norm.get("ARTIST") or norm.get("ALBUM_ARTIST")
        except Exception:
            pass

    return title, artist


def infer_song_title(audio_path: pathlib.Path) -> str:
    """
    Build the in-game display title as 'Song Name (Artist)' when artist metadata
    (or 'Artist - Song Name' filename format) is present, otherwise 'Song Name'.
    """
    tag_title, tag_artist = extract_audio_metadata(audio_path)

    if tag_title:
        song_name = _format_song_name(tag_title)
        artist = tag_artist.strip() if tag_artist else ""
    else:
        stem_no_num = re.sub(r"^(?:track\s*)?\d+[\s.\-_]+", "", audio_path.stem, flags=re.IGNORECASE).strip()
        m = re.match(r"^(.+?)\s+-\s+(.+)$", stem_no_num)
        if m and not tag_artist:
            artist = m.group(1).strip()
            song_name = _format_song_name(re.sub(r"[_]+", " ", m.group(2)))
        else:
            song_name = clean_title_from_stem(audio_path.stem)
            artist = tag_artist.strip() if tag_artist else ""

    if not song_name:
        song_name = clean_title_from_stem(audio_path.stem)

    if artist and f"({artist.lower()})" not in song_name.lower():
        return f"{song_name} ({artist})"
    return song_name


ALBUM_COVER_PRESETS: List[Tuple[str, str]] = [
    ("Classic Vinyl (Default)", "Texture2D'/Game/Art/UI/Texture/Turntable/Album_0104.Album_0104'"),
    ("Just Fine (Blue)",        "Texture2D'/Game/Art/UI/Texture/Turntable/Album_09.Album_09'"),
    ("Lullaby of Secret",       "Texture2D'/Game/Art/UI/Texture/Turntable/Album_08.Album_08'"),
    ("Blur",                    "Texture2D'/Game/Art/UI/Texture/Turntable/Album_07.Album_07'"),
    ("Oasis",                   "Texture2D'/Game/Art/UI/Texture/Turntable/Album_05.Album_05'"),
    ("Don't Forget Me",         "Texture2D'/Game/Art/UI/Texture/Turntable/Album_06.Album_06'"),
    ("Take Me Away (Winter)",   "Texture2D'/Game/Art/UI/Texture/Turntable/Album_9.Album_9'"),
    ("Dawn (Winter)",           "Texture2D'/Game/Art/UI/Texture/Turntable/Album_10.Album_10'"),
    ("Enya's Gift",             "Texture2D'/Game/Art/UI/Texture/Turntable/UI_Turntable_Music_010.UI_Turntable_Music_010'"),
]

DEFAULT_ALBUM_COVER = ALBUM_COVER_PRESETS[0][1]
TURNTABLE_SOUND_TABLE_PKG = "/Game/Local/Data/TurntableSoundTable"
STRING_TABLE_UI_PKG = "/Game/Local/Localize/StringTable_UI"


@dataclasses.dataclass
class CustomTrackInput:
    """Single custom song to add to the Camp Turntable alongside the 34 original tracks."""
    title: str
    ogg_on: "OggVorbisInfo"
    ogg_off: "OggVorbisInfo"
    volume_on: float = 1.100000023841858
    volume_off: float = 0.6000000238418579
    image_path: str = DEFAULT_ALBUM_COVER
    cover_bgra: Optional[bytes] = None
    cover_label: str = ""


def _parse_flac_picture_block(block: bytes) -> Optional[Tuple[int, bytes]]:
    """Parse a FLAC METADATA_BLOCK_PICTURE binary payload -> (pic_type, image_bytes)."""
    if len(block) < 32:
        return None
    pos = 0
    pic_type, mime_len = struct.unpack_from(">II", block, pos)
    pos += 8 + mime_len
    if pos + 4 > len(block):
        return None
    desc_len = struct.unpack_from(">I", block, pos)[0]
    pos += 4 + desc_len + 16  # skip description + width/height/depth/colors
    if pos + 4 > len(block):
        return None
    data_len = struct.unpack_from(">I", block, pos)[0]
    pos += 4
    if data_len <= 0 or pos + data_len > len(block):
        return None
    return pic_type, block[pos : pos + data_len]


def _pick_best_picture(candidates: List[Tuple[int, bytes]]) -> Optional[bytes]:
    if not candidates:
        return None
    for pic_type, img_bytes in candidates:
        if pic_type == 3 and img_bytes:
            return img_bytes
    for _, img_bytes in candidates:
        if img_bytes:
            return img_bytes
    return None


def extract_embedded_cover_art(audio_path: pathlib.Path) -> Optional[bytes]:
    """
    Extract embedded cover art image bytes (ID3 APIC, FLAC PICTURE, Vorbis/Opus
    METADATA_BLOCK_PICTURE, or MP4 covr) from an audio file before transcoding.
    """
    if not audio_path.is_file():
        return None

    # 1. Primary path: mutagen handles large/complex tags cleanly across all formats
    try:
        import mutagen  # type: ignore
        mf = mutagen.File(str(audio_path))
        if mf is not None:
            candidates: List[Tuple[int, bytes]] = []
            pics = getattr(mf, "pictures", None)
            if pics:
                for pic in pics:
                    data = getattr(pic, "data", None)
                    if data:
                        candidates.append((int(getattr(pic, "type", 0)), bytes(data)))
            tags = getattr(mf, "tags", None)
            if tags:
                for key in list(tags.keys()):
                    val = tags[key]
                    k_str = str(key)
                    if k_str.startswith("APIC"):
                        data = getattr(val, "data", None)
                        if data:
                            candidates.append((int(getattr(val, "type", 0)), bytes(data)))
                    elif k_str.upper() == "METADATA_BLOCK_PICTURE":
                        items = val if isinstance(val, (list, tuple)) else [val]
                        for b64_item in items:
                            try:
                                parsed = _parse_flac_picture_block(base64.b64decode(str(b64_item)))
                                if parsed:
                                    candidates.append(parsed)
                            except Exception:
                                pass
                    elif k_str == "covr":
                        items = val if isinstance(val, (list, tuple)) else [val]
                        for cov in items:
                            raw_cov = bytes(cov)
                            if raw_cov:
                                candidates.append((3, raw_cov))
            best = _pick_best_picture(candidates)
            if best:
                return best
    except Exception:
        pass

    # 2. Lightweight pure-Python fallback (up to 16 MB header read)
    try:
        with audio_path.open("rb") as f:
            head = f.read(16 * 1024 * 1024)
        if head.startswith(b"OggS"):
            tags = _read_ogg_tags(head)
            b64 = tags.get("METADATA_BLOCK_PICTURE")
            if b64:
                parsed = _parse_flac_picture_block(base64.b64decode(b64))
                if parsed:
                    return parsed[1]
        elif head.startswith(b"fLaC"):
            p = 4
            candidates = []
            while p + 4 <= len(head):
                hdr = head[p]
                is_last = (hdr & 0x80) != 0
                btype = hdr & 0x7F
                blen = int.from_bytes(head[p + 1 : p + 4], "big")
                p += 4
                if p + blen > len(head):
                    break
                if btype == 6:
                    parsed = _parse_flac_picture_block(head[p : p + blen])
                    if parsed:
                        candidates.append(parsed)
                p += blen
                if is_last:
                    break
            return _pick_best_picture(candidates)
        elif head.startswith(b"ID3") and len(head) >= 10 and head[3] in (3, 4):
            ver_maj = head[3]
            sz = (
                ((head[6] & 0x7F) << 21)
                | ((head[7] & 0x7F) << 14)
                | ((head[8] & 0x7F) << 7)
                | (head[9] & 0x7F)
            )
            end = min(len(head), 10 + sz)
            p = 10
            candidates = []
            while p + 10 <= end:
                fid = head[p : p + 4]
                if fid == b"\x00\x00\x00\x00":
                    break
                if ver_maj == 4:
                    fsz = (
                        ((head[p + 4] & 0x7F) << 21)
                        | ((head[p + 5] & 0x7F) << 14)
                        | ((head[p + 6] & 0x7F) << 7)
                        | (head[p + 7] & 0x7F)
                    )
                else:
                    fsz = struct.unpack_from(">I", head, p + 4)[0]
                p += 10
                if fsz <= 0 or p + fsz > end:
                    break
                if fid == b"APIC":
                    frame = head[p : p + fsz]
                    enc = frame[0]
                    q = frame.find(b"\x00", 1)
                    if q != -1 and q + 2 < len(frame):
                        pic_type = frame[q + 1]
                        d_pos = q + 2
                        if enc in (1, 2):
                            z = frame.find(b"\x00\x00", d_pos)
                            img_start = (z + 2) if z != -1 else -1
                        else:
                            z = frame.find(b"\x00", d_pos)
                            img_start = (z + 1) if z != -1 else -1
                        if img_start != -1 and img_start < len(frame):
                            candidates.append((pic_type, frame[img_start:]))
                p += fsz
            return _pick_best_picture(candidates)
    except Exception:
        pass

    return None


def prepare_cover_art_bgra(
    image_source: Union[pathlib.Path, bytes],
    apply_card_frame: bool = True,
) -> bytes:
    """
    Convert an image file path or raw encoded image bytes into a 256x256
    PF_B8G8R8A8 (raw 32-bit BGRA, 262,144 bytes) payload matching Stellar Blade's
    Camp Turntable album cover dimensions and optional rounded shadow frame.
    """
    raw_bytes = image_source.read_bytes() if isinstance(image_source, pathlib.Path) else image_source

    try:
        from PIL import Image, ImageDraw, ImageFilter, ImageOps  # type: ignore

        with Image.open(io.BytesIO(raw_bytes)) as opened:
            im = ImageOps.exif_transpose(opened).convert("RGBA")

        has_transparency = False
        try:
            min_alpha, _ = im.getchannel("A").getextrema()
            has_transparency = min_alpha < 245
        except Exception:
            pass

        if not apply_card_frame or has_transparency:
            fitted = ImageOps.contain(im, (256, 256), method=Image.Resampling.LANCZOS)
            canvas = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
            canvas.paste(fitted, ((256 - fitted.width) // 2, (256 - fitted.height) // 2), fitted)
            return canvas.tobytes("raw", "BGRA")

        # Match vanilla Album_*.uasset card styling: rounded artwork + soft drop shadow
        card_size = 224
        margin = (256 - card_size) // 2  # 16 px margin around card
        radius = 10

        art = ImageOps.fit(im, (card_size, card_size), method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))

        card_mask = Image.new("L", (card_size, card_size), 0)
        ImageDraw.Draw(card_mask).rounded_rectangle(
            (0, 0, card_size - 1, card_size - 1),
            radius=radius,
            fill=255,
        )

        shadow_canvas = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
        shadow_alpha = Image.new("L", (256, 256), 0)
        ImageDraw.Draw(shadow_alpha).rounded_rectangle(
            (margin, margin + 2, margin + card_size - 1, margin + 2 + card_size - 1),
            radius=radius,
            fill=145,
        )
        shadow_alpha = shadow_alpha.filter(ImageFilter.GaussianBlur(radius=6.5))
        shadow_canvas.putalpha(shadow_alpha)

        art_rgba = art.copy()
        art_rgba.putalpha(card_mask)
        shadow_canvas.paste(art_rgba, (margin, margin), art_rgba)
        return shadow_canvas.tobytes("raw", "BGRA")
    except ImportError:
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise RuntimeError("Pillow (or ffmpeg) is required to convert custom album cover images.")
        cmd = [
            ffmpeg, "-y", "-f", "image2pipe", "-i", "-",
            "-vf", "scale=256:256:force_original_aspect_ratio=increase,crop=256:256",
            "-f", "rawvideo", "-pix_fmt", "bgra", "-",
        ]
        res = subprocess.run(cmd, input=raw_bytes, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        if len(res.stdout) != 256 * 256 * 4:
            raise RuntimeError("Failed to convert cover art image to 256x256 BGRA.")
        return res.stdout


def resolve_track_cover_art(
    audio_path: pathlib.Path,
    fallback_image_path: str = DEFAULT_ALBUM_COVER,
    custom_image_file: Optional[pathlib.Path] = None,
    use_embedded: bool = True,
) -> Tuple[str, Optional[bytes], str]:
    """
    Determine a track's ImagePath fallback and optional custom 256x256 BGRA texture payload.
    Priority: explicit custom image file > embedded cover art > vanilla preset fallback.
    """
    if custom_image_file is not None and custom_image_file.is_file():
        return (
            fallback_image_path,
            prepare_cover_art_bgra(custom_image_file),
            f"image '{custom_image_file.name}'",
        )
    if use_embedded:
        embedded = extract_embedded_cover_art(audio_path)
        if embedded:
            return (
                fallback_image_path,
                prepare_cover_art_bgra(embedded),
                "embedded art",
            )
    return fallback_image_path, None, "preset"


def resolve_album_cover(query: Optional[str]) -> str:
    if not query or not query.strip():
        return DEFAULT_ALBUM_COVER
    q = query.strip()
    if q.startswith("Texture2D'"):
        return q
    q_low = q.lower()
    for label, path in ALBUM_COVER_PRESETS:
        if q_low in label.lower() or q_low in path.lower():
            return path
    if q.isdigit():
        idx = int(q) - 1
        if 0 <= idx < len(ALBUM_COVER_PRESETS):
            return ALBUM_COVER_PRESETS[idx][1]
    return DEFAULT_ALBUM_COVER


def encode_ue_fstring(s: str) -> bytes:
    """Encode a Python str as a UE4 FString (ASCII/UTF-8 or UTF-16LE)."""
    if not s:
        return struct.pack("<i", 0)
    if s.isascii():
        raw = s.encode("ascii") + b"\x00"
        return struct.pack("<i", len(raw)) + raw
    raw16 = s.encode("utf-16le") + b"\x00\x00"
    return struct.pack("<i", -(len(raw16) // 2)) + raw16


def _parse_zen_namemap(data: bytes, nm_off: int, nm_sz: int) -> List[str]:
    names: List[str] = []
    p = nm_off
    end = nm_off + nm_sz
    while p < end:
        is_wide = (data[p] & 0x80) != 0
        slen = ((data[p] & 0x7F) << 8) | data[p + 1]
        p += 2
        if is_wide:
            names.append(data[p : p + slen * 2].decode("utf-16le", errors="replace"))
            p += slen * 2
        else:
            names.append(data[p : p + slen].decode("latin1", errors="replace"))
            p += slen
    return names


def _serialize_zen_namemap_mixed(names: List[str]) -> Tuple[bytes, bytes]:
    name_buf = bytearray()
    hash_buf = bytearray(struct.pack("<Q", 0x00000000C1640000))
    for n in names:
        if n.isascii():
            raw = n.encode("latin1")
            name_buf.append((len(raw) >> 8) & 0x7F)
            name_buf.append(len(raw) & 0xFF)
            name_buf.extend(raw)
            hash_buf.extend(struct.pack("<Q", cityhash64(n.lower().encode("latin1"))))
        else:
            raw16 = n.encode("utf-16le")
            nchars = len(raw16) // 2
            name_buf.append(0x80 | ((nchars >> 8) & 0x7F))
            name_buf.append(nchars & 0xFF)
            name_buf.extend(raw16)
            hash_buf.extend(struct.pack("<Q", cityhash64(n.lower().encode("utf-16le"))))
    return bytes(name_buf), bytes(hash_buf)


def patch_turntable_sound_table(
    base_uasset: bytes,
    custom_rows: List[Tuple[int, str, str, str, str, str]],
) -> bytes:
    """
    Append custom rows to /Game/Local/Data/TurntableSoundTable.uasset while preserving
    all 34 original rows intact.

    Each tuple in `custom_rows` is:
      (id_val, music_path, noise_music_path, title_string_key, image_path, qnrt_asset_path)
    """
    if not custom_rows:
        return base_uasset

    (
        name_idx, name_num, src_idx, src_num,
        pkg_flags, cooked_hdr_sz,
        nm_names_off, nm_names_sz, nm_hashes_off, nm_hashes_sz,
        imp_off, exp_off, exp_bundles_off, graph_off, graph_sz, pad,
    ) = struct.unpack_from("<4I2I10i", base_uasset, 0)

    names = _parse_zen_namemap(base_uasset, nm_names_off, nm_names_sz)
    custom_row_fname_idx = len(names)
    names.append("Turtable_Music_Custom")

    nn_bytes, nh_bytes = _serialize_zen_namemap_mixed(names)
    new_nh_off = (nm_names_off + len(nn_bytes) + 7) & ~7
    pad_len = new_nh_off - (nm_names_off + len(nn_bytes))

    old_body_off = graph_off + graph_sz
    imp_bytes = base_uasset[imp_off:exp_off]
    exp_entry = bytearray(base_uasset[exp_off:exp_bundles_off])
    bundles_and_graph = base_uasset[exp_bundles_off:old_body_off]

    new_imp_off = new_nh_off + len(nh_bytes)
    new_exp_off = new_imp_off + len(imp_bytes)
    new_bnd_off = new_exp_off + len(exp_entry)
    new_grp_off = new_bnd_off + (graph_off - exp_bundles_off)
    new_body_off = new_grp_off + graph_sz
    hdr_delta = new_body_off - old_body_off

    # Export 0 starts with 26-byte UDataTable/USBDataTable header, then uint32 NumRows
    body_prefix = bytearray(base_uasset[old_body_off:])
    num_rows_rel = 0x1A  # 0x5CE - 0x5B4 = 26
    old_num_rows = struct.unpack_from("<I", body_prefix, num_rows_rel)[0]
    struct.pack_into("<I", body_prefix, num_rows_rel, old_num_rows + len(custom_rows))

    # Append each new row using exact same unversioned property header (80 13 06 01):
    # non-zero props: [0] Id, [3] MusicPath, [4] NoiseMusicPath, [5] TitleStringKey, [6] ImagePath, [7] QNRTAssetPath
    # zero props    : [1] ConditionGroup, [2] NotifyAchievement, [8] FileSuffix
    appended = bytearray()
    for idx_1based, (row_id, m_path, nm_path, title_key, img_path, nrt_path) in enumerate(custom_rows, start=1):
        appended.extend(struct.pack("<II", custom_row_fname_idx, idx_1based + 1))
        appended.extend(b"\x80\x13\x06\x01")
        appended.extend(struct.pack("<I", row_id))
        appended.extend(encode_ue_fstring(m_path))
        appended.extend(encode_ue_fstring(nm_path))
        appended.extend(encode_ue_fstring(title_key))
        appended.extend(encode_ue_fstring(img_path))
        appended.extend(encode_ue_fstring(nrt_path))

    new_body = bytes(body_prefix) + bytes(appended)

    old_serial_off, _ = struct.unpack_from("<QQ", exp_entry, 0)
    struct.pack_into("<QQ", exp_entry, 0, old_serial_off + hdr_delta, len(new_body))

    new_summary = struct.pack(
        "<4I2I10i",
        name_idx, name_num, src_idx, src_num,
        pkg_flags, cooked_hdr_sz + hdr_delta,
        nm_names_off, len(nn_bytes), new_nh_off, len(nh_bytes),
        new_imp_off, new_exp_off, new_bnd_off, new_grp_off, graph_sz, pad,
    )

    return (
        new_summary
        + nn_bytes
        + (b"\x00" * pad_len)
        + nh_bytes
        + imp_bytes
        + bytes(exp_entry)
        + bundles_and_graph
        + new_body
    )


def patch_string_table_ui(
    base_uasset: bytes,
    new_entries: List[Tuple[str, str]],
) -> bytes:
    """
    Append (key, source_string) entries to /Game/Local/Localize/StringTable_UI.uasset
    while keeping all existing entries and metadata intact.
    """
    if not new_entries:
        return base_uasset

    (
        name_idx, name_num, src_idx, src_num,
        pkg_flags, cooked_hdr_sz,
        nm_names_off, nm_names_sz, nm_hashes_off, nm_hashes_sz,
        imp_off, exp_off, exp_bundles_off, graph_off, graph_sz, pad,
    ) = struct.unpack_from("<4I2I10i", base_uasset, 0)

    body_off = graph_off + graph_sz
    body = base_uasset[body_off:]

    def _skip_fstr(buf: bytes, p: int) -> int:
        l = struct.unpack_from("<i", buf, p)[0]
        p += 4
        if l == 0:
            return p
        return p + (-l * 2 if l < 0 else l)

    # UObject unversioned header (2B) + uint32 (4B) + FString TableNamespace
    pos = 6
    pos = _skip_fstr(body, pos)
    cnt_off = pos
    old_cnt = struct.unpack_from("<I", body, cnt_off)[0]
    pos += 4
    for _ in range(old_cnt):
        pos = _skip_fstr(body, pos)
        pos = _skip_fstr(body, pos)

    inserted = bytearray()
    for k, v in new_entries:
        inserted.extend(encode_ue_fstring(k))
        inserted.extend(encode_ue_fstring(v))

    new_body = bytearray(body[:pos])
    struct.pack_into("<I", new_body, cnt_off, old_cnt + len(new_entries))
    new_body.extend(inserted)
    new_body.extend(body[pos:])

    hdr = bytearray(base_uasset[:body_off])
    struct.pack_into("<Q", hdr, exp_off + 8, len(new_body))
    return bytes(hdr) + bytes(new_body)


def resolve_category(query: str) -> Tuple[str, List[CampTrackSpec]]:
    """Resolve a category name or shortcut to (category_name, track_list)."""
    q = query.strip().lower()
    if q in ("all", "1-34", "all tracks", "all tracks (1 - 34)"):
        return "All Tracks (1 - 34)", [t for t in CAMP_TRACKS if 1 <= t.index <= 34]
    elif q in ("base", "base camp", "base-camp", "camp", "1-9", "base camp tracks (1 - 9)"):
        return "Base Camp Tracks (1 - 9)", [t for t in CAMP_TRACKS if 1 <= t.index <= 9]
    elif q in ("nier", "nier dlc", "nier:automata", "10-11", "nier:automata dlc (10 - 11)"):
        return "NieR:Automata DLC (10 - 11)", [t for t in CAMP_TRACKS if 10 <= t.index <= 11]
    elif q in ("holiday", "holidays", "christmas", "winter", "12-13", "holiday specials (12 - 13)"):
        return "Holiday Specials (12 - 13)", [t for t in CAMP_TRACKS if 12 <= t.index <= 13]
    elif q in ("nikke", "nikke dlc", "14-21", "nikke dlc (14 - 21)"):
        return "NIKKE DLC (14 - 21)", [t for t in CAMP_TRACKS if 14 <= t.index <= 21]
    elif q in ("enya", "enya's gift", "gift", "bundle", "22-34", "enya's gift bundle (22 - 34)"):
        return "Enya's Gift Bundle (22 - 34)", [t for t in CAMP_TRACKS if 22 <= t.index <= 34]
    else:
        for name, min_i, max_i in TRACK_CATEGORIES:
            if q in name.lower():
                return name, [t for t in CAMP_TRACKS if min_i <= t.index <= max_i]
        valid_cats = "all, base-camp, nier, holiday, nikke, enya"
        raise ValueError(f"Unknown category {query!r}. Supported categories: {valid_cats}")


# ============================================================================
# 3. Ogg Vorbis Parser & FFmpeg Audio Converter
# ============================================================================

@dataclasses.dataclass
class OggVorbisInfo:
    ogg_bytes: bytes
    channels: int
    sample_rate: int
    total_samples: int

    @property
    def duration(self) -> float:
        return self.total_samples / float(self.sample_rate)


def parse_ogg_vorbis(ogg_bytes: bytes) -> OggVorbisInfo:
    if len(ogg_bytes) < 64 or ogg_bytes[:4] != b"OggS":
        raise ValueError("Input audio is not a valid Ogg container (missing 'OggS' magic).")

    seg_count = ogg_bytes[26]
    id_hdr_off = 27 + seg_count
    if ogg_bytes[id_hdr_off : id_hdr_off + 7] != b"\x01vorbis":
        raise ValueError("Ogg stream does not start with a Vorbis identification header.")

    _, channels, sample_rate = struct.unpack_from("<IBI", ogg_bytes, id_hdr_off + 7)
    if sample_rate <= 0 or channels <= 0:
        raise ValueError(f"Invalid Vorbis parameters: channels={channels}, sample_rate={sample_rate}")

    # Scan OggS pages from the back to read the final valid granule_position
    total_samples = 0
    pos = len(ogg_bytes) - 27
    while pos >= 0:
        idx = ogg_bytes.rfind(b"OggS", 0, pos + 4)
        if idx == -1:
            break
        ver = ogg_bytes[idx + 4]
        granule = struct.unpack_from("<q", ogg_bytes, idx + 6)[0]
        if ver == 0 and granule > 0:
            total_samples = granule
            break
        pos = idx - 1

    if total_samples <= 0:
        raise ValueError("Could not determine total sample count from OggS granule positions.")

    return OggVorbisInfo(
        ogg_bytes=ogg_bytes,
        channels=channels,
        sample_rate=sample_rate,
        total_samples=total_samples,
    )


def _ogg_has_image_or_extra_streams(raw: bytes) -> Optional[str]:
    """
    Detect if an Ogg file contains embedded picture metadata (METADATA_BLOCK_PICTURE),
    oversized Vorbis comment headers, non-Vorbis streams, or multiple logical bitstreams
    that UE4's USoundWave / libvorbis loader may choke on.
    Returns a short reason string if cleanup/re-encode is needed, else None.
    """
    if len(raw) < 64 or raw[:4] != b"OggS":
        return "not an Ogg stream"

    pos = 0
    bos_count = 0
    packets: List[bytes] = []
    cur_pkt = bytearray()
    # Scan initial pages up to 8 MB looking for BOS count and first 3 packets
    scan_limit = min(len(raw), 8 * 1024 * 1024)
    while pos + 27 <= scan_limit and len(packets) < 3:
        if raw[pos : pos + 4] != b"OggS":
            nxt = raw.find(b"OggS", pos + 1, scan_limit)
            if nxt == -1:
                break
            pos = nxt
            continue
        hdr_type = raw[pos + 5]
        if hdr_type & 0x02:
            bos_count += 1
            if bos_count > 1:
                return "multiple logical Ogg bitstreams"
        seg_cnt = raw[pos + 26]
        if pos + 27 + seg_cnt > len(raw):
            break
        seg_table = raw[pos + 27 : pos + 27 + seg_cnt]
        data_pos = pos + 27 + seg_cnt
        total_body = sum(seg_table)
        if data_pos + total_body > len(raw):
            break
        for seg_len in seg_table:
            cur_pkt.extend(raw[data_pos : data_pos + seg_len])
            data_pos += seg_len
            if seg_len < 255:
                packets.append(bytes(cur_pkt))
                cur_pkt.clear()
                if len(packets) >= 3:
                    break
        pos = data_pos

    if bos_count > 1:
        return "multiple logical Ogg bitstreams"
    if not packets or not packets[0].startswith(b"\x01vorbis"):
        return "non-Vorbis Ogg stream"
    if len(packets) >= 2:
        comment_pkt = packets[1]
        if b"METADATA_BLOCK_PICTURE" in comment_pkt.upper():
            return "embedded cover art (METADATA_BLOCK_PICTURE)"
        if len(comment_pkt) > 4096:
            return f"oversized Vorbis comment header ({len(comment_pkt)} bytes)"
    if len(packets) < 3 or not packets[2].startswith(b"\x05vorbis"):
        return "incomplete/oversized Vorbis header sequence"
    return None


def _build_ogg_crc_table() -> Tuple[int, ...]:
    table: List[int] = []
    for i in range(256):
        r = i << 24
        for _ in range(8):
            r = ((r << 1) ^ 0x04C11DB7) & 0xFFFFFFFF if (r & 0x80000000) else ((r << 1) & 0xFFFFFFFF)
        table.append(r)
    return tuple(table)


_OGG_CRC_TABLE = _build_ogg_crc_table()


def _ogg_crc32(data: bytes) -> int:
    crc = 0
    tbl = _OGG_CRC_TABLE
    for b in data:
        crc = ((crc << 8) ^ tbl[((crc >> 24) ^ b) & 0xFF]) & 0xFFFFFFFF
    return crc


def _build_ogg_page(serial: int, seq_no: int, hdr_type: int, granule: int, seg_table: bytes, body: bytes) -> bytes:
    hdr = bytearray(struct.pack("<4sBBqIIIB", b"OggS", 0, hdr_type, granule, serial, seq_no, 0, len(seg_table)))
    page = hdr + seg_table + body
    crc = _ogg_crc32(page)
    struct.pack_into("<I", page, 22, crc)
    return bytes(page)


def _strip_ogg_vorbis_metadata(raw: bytes) -> Optional[bytes]:
    """
    Losslessly strip the Vorbis comment header (including METADATA_BLOCK_PICTURE)
    from a single-stream Ogg Vorbis file without needing ffmpeg. Returns cleaned
    Ogg bytes or None if the stream cannot be stripped cleanly as Vorbis.
    """
    if len(raw) < 64 or raw[:4] != b"OggS":
        return None

    pos = 0
    packets: List[bytes] = []
    cur_pkt = bytearray()
    leftover_on_last_hdr_page = b""
    audio_start_pos = 0
    serial = struct.unpack_from("<I", raw, 14)[0]
    page0_end = 0

    while pos + 27 <= len(raw) and len(packets) < 3:
        if raw[pos : pos + 4] != b"OggS":
            return None
        hdr_type = raw[pos + 5]
        if len(packets) > 0 and (hdr_type & 0x02):
            return None
        seg_cnt = raw[pos + 26]
        if pos + 27 + seg_cnt > len(raw):
            return None
        seg_table = raw[pos + 27 : pos + 27 + seg_cnt]
        data_pos = pos + 27 + seg_cnt
        total_body = sum(seg_table)
        if data_pos + total_body > len(raw):
            return None

        seg_idx = 0
        while seg_idx < len(seg_table):
            seg_len = seg_table[seg_idx]
            cur_pkt.extend(raw[data_pos : data_pos + seg_len])
            data_pos += seg_len
            seg_idx += 1
            if seg_len < 255:
                packets.append(bytes(cur_pkt))
                cur_pkt.clear()
                if len(packets) == 1 and page0_end == 0:
                    page0_end = pos + 27 + seg_cnt + total_body
                if len(packets) >= 3:
                    # Preserve any extra segments in the same page just in case
                    rem_body = sum(seg_table[seg_idx:])
                    if rem_body > 0:
                        leftover_on_last_hdr_page = raw[data_pos : data_pos + rem_body]
                        data_pos += rem_body
                    break
        pos = data_pos
        if len(packets) >= 3:
            audio_start_pos = pos
            break

    if len(packets) < 3 or not packets[0].startswith(b"\x01vorbis") or not packets[2].startswith(b"\x05vorbis"):
        return None
    if leftover_on_last_hdr_page:
        # Rare muxing edge case: audio packed on header setup page -> defer to ffmpeg
        return None

    clean_comment = b"\x03vorbis" + struct.pack("<I", 8) + b"CleanOgg" + struct.pack("<II", 0, 1)
    # Build segments for [clean_comment, setup_pkt] packed across Ogg page(s)
    segments: List[int] = []
    for pkt in (clean_comment, packets[2]):
        n = len(pkt)
        while n >= 255:
            segments.append(255)
            n -= 255
        segments.append(n)
    payload_bytes = clean_comment + packets[2]

    out = bytearray()
    # Emit page 0 verbatim with \x01vorbis identification header (or rebuild cleanly)
    out.extend(
        _build_ogg_page(
            serial=serial,
            seq_no=0,
            hdr_type=0x02,
            granule=0,
            seg_table=bytes([len(packets[0])]) if len(packets[0]) < 255 else bytes([255] * (len(packets[0]) // 255) + [len(packets[0]) % 255]),
            body=packets[0],
        )
    )

    seq_no = 1
    seg_cursor = 0
    byte_cursor = 0
    while seg_cursor < len(segments):
        chunk_segs = segments[seg_cursor : seg_cursor + 255]
        chunk_len = sum(chunk_segs)
        chunk_body = payload_bytes[byte_cursor : byte_cursor + chunk_len]
        continued = 0x01 if (seg_cursor > 0 and segments[seg_cursor - 1] == 255) else 0x00
        is_last_hdr_page = (seg_cursor + len(chunk_segs)) >= len(segments)
        granule = 0 if is_last_hdr_page else -1
        out.extend(_build_ogg_page(serial, seq_no, continued, granule, bytes(chunk_segs), chunk_body))
        seq_no += 1
        seg_cursor += len(chunk_segs)
        byte_cursor += chunk_len

    # Copy all remaining audio pages and renumber page_seq + recompute Ogg CRC-32
    pos = audio_start_pos
    while pos + 27 <= len(raw):
        if raw[pos : pos + 4] != b"OggS":
            return None
        seg_cnt = raw[pos + 26]
        if pos + 27 + seg_cnt > len(raw):
            return None
        total_body = sum(raw[pos + 27 : pos + 27 + seg_cnt])
        page_end = pos + 27 + seg_cnt + total_body
        if page_end > len(raw):
            return None
        page = bytearray(raw[pos:page_end])
        struct.pack_into("<I", page, 18, seq_no)
        struct.pack_into("<I", page, 22, 0)
        struct.pack_into("<I", page, 22, _ogg_crc32(page))
        out.extend(page)
        seq_no += 1
        pos = page_end

    return bytes(out)


def load_or_convert_ogg(input_path: pathlib.Path, force_reencode: bool = False) -> OggVorbisInfo:
    if not input_path.is_file():
        raise FileNotFoundError(f"Audio file not found: {input_path}")

    raw = input_path.read_bytes()
    strip_reason: Optional[str] = None
    if raw[:4] == b"OggS" and not force_reencode:
        strip_reason = _ogg_has_image_or_extra_streams(raw)
        if strip_reason is None:
            return parse_ogg_vorbis(raw)
        stripped = _strip_ogg_vorbis_metadata(raw)
        if stripped is not None and _ogg_has_image_or_extra_streams(stripped) is None:
            return parse_ogg_vorbis(stripped)

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        if strip_reason:
            raise RuntimeError(
                f"Input Ogg file {input_path.name!r} contains {strip_reason}, which Stellar Blade's audio engine does not support, "
                "and 'ffmpeg' was not found on PATH to strip it."
            )
        raise RuntimeError(
            f"Input file {input_path.name!r} is not an Ogg Vorbis (.ogg) file and 'ffmpeg' was not found on PATH.\n"
            "Install ffmpeg or convert the audio manually to 48000 Hz stereo Ogg Vorbis."
        )

    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
        tmp_path = pathlib.Path(tmp.name)

    try:
        cmd = [
            ffmpeg, "-y", "-i", str(input_path),
            "-map", "0:a:0", "-vn", "-sn", "-dn", "-map_metadata", "-1",
            "-c:a", "libvorbis", "-ar", "48000", "-ac", "2", "-q:a", "4",
            str(tmp_path),
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return parse_ogg_vorbis(tmp_path.read_bytes())
    finally:
        tmp_path.unlink(missing_ok=True)


# ============================================================================
# 4. Zen Package Builders (USoundWave & UConstantQNRT)
# ============================================================================

SOUNDWAVE_BASE_NAMES: List[str] = [
    "/Game/Sound/SoundAsset/Attenuations/Common/Default",
    "/Game/Sound/SoundAsset/Concurrency/Concurrency_VendingMusic",
    "/Game/Sound/SoundAsset/SoundClass/BGM_VendingMachine",
    "__PKG_PATH__",
    "/Script/CoreUObject",
    "/Script/Engine",
    "AttenuationSettings",
    "__OBJ_NAME__",
    "BGM_VendingMachine",
    "bLooping",
    "BoolProperty",
    "ByteProperty",
    "Class",
    "CompressionQuality",
    "Concurrency_VendingMusic",
    "ConcurrencySet",
    "Default",
    "Default__SoundWave",
    "Duration",
    "EnumProperty",
    "ESoundGroup",
    "EVirtualizationMode",
    "EVirtualizationMode::PlayWhenSilent",
    "FloatProperty",
    "IntProperty",
    "None",
    "NumChannels",
    "ObjectProperty",
    "OGG10000-1-1-1-1-1",
    "Package",
    "SampleRate",
    "SetProperty",
    "SoundAttenuation",
    "SoundClass",
    "SoundClassObject",
    "SoundConcurrency",
    "SoundGroup",
    "SOUNDGROUP_Music",
    "SoundWave",
    "StreamingPriority",
    "TotalSamples",
    "VirtualizationMode",
    "Volume",
]

SOUNDWAVE_IMPORT_MAP: List[int] = [
    0x44F26264628E498D,  # /Script/Engine.SoundWave
    0xFFFFFFFFFFFFFFFF,
    0xFFFFFFFFFFFFFFFF,
    0xFFFFFFFFFFFFFFFF,
    0x51ACCED3DC7C0922,
    0xAA06E5AECC16FC39,  # /Game/Sound/SoundAsset/Attenuations/Common/Default.Default
    0x899C6FABC4A4EA55,  # /Game/Sound/SoundAsset/SoundClass/BGM_VendingMachine.BGM_VendingMachine
    0x9D634AC182E5C344,  # /Game/Sound/SoundAsset/Concurrency/Concurrency_VendingMusic.Concurrency_VendingMusic
    0x4E0856E27FF445AE,  # /Script/Engine.Default__SoundWave
]

SOUNDWAVE_EXPORT_BUNDLES = bytes.fromhex(
    "000000000200000000000000000000000000000001000000"
)

SOUNDWAVE_GRAPH_DATA = bytes.fromhex(
    "03000000"
    "d6abab5acd3b18b1010000000000000000000000"
    "d00359b39f2f02ea010000000000000000000000"
    "aba73c0d1af47fee010000000000000000000000"
)

QNRT_BASE_NAMES: List[str] = [
    "__ON_PKG_PATH__",
    "__NRT_PKG_PATH__",
    "/Game/Sound/World/BGM/VendingMachine/Turntable_ConstantQNRT_Setting",
    "/Script/AudioSynesthesia",
    "/Script/CoreUObject",
    "/Script/Engine",
    "__ON_OBJ_NAME__",
    "__NRT_OBJ_NAME__",
    "Class",
    "ConstantQNRT",
    "ConstantQNRTSettings",
    "Default__ConstantQNRT",
    "DefaultConstantQNRTSettings",
    "DurationInSeconds",
    "FloatProperty",
    "None",
    "ObjectProperty",
    "Package",
    "Settings",
    "Sound",
    "SoundWave",
    "Turntable_ConstantQNRT_Setting",
]


def _serialize_namemap(names: List[str]) -> Tuple[bytes, bytes]:
    name_buf = bytearray()
    hash_buf = bytearray(struct.pack("<Q", 0x00000000C1640000))
    for n in names:
        raw = n.encode("latin1")
        name_buf.append(0x00)
        name_buf.append(len(raw))
        name_buf.extend(raw)
        hash_buf.extend(struct.pack("<Q", cityhash64(n.lower().encode("latin1"))))
    return bytes(name_buf), bytes(hash_buf)


def build_soundwave_zen_asset(
    pkg_path: str,
    obj_name: str,
    ogg_info: OggVorbisInfo,
    volume: float,
    guid_bytes: bytes,
) -> bytes:
    """Build a complete UE 4.26 Zen USoundWave package (.uasset in .ucas)."""
    names = list(SOUNDWAVE_BASE_NAMES)
    names[3] = pkg_path
    names[7] = obj_name

    nn_bytes, nh_bytes = _serialize_namemap(names)
    nn_off = 0x40
    nn_sz = len(nn_bytes)
    nh_off = (nn_off + nn_sz + 7) & ~7
    pad_len = nh_off - (nn_off + nn_sz)
    nh_sz = len(nh_bytes)

    imp_off = nh_off + nh_sz
    imp_bytes = struct.pack(f"<{len(SOUNDWAVE_IMPORT_MAP)}Q", *SOUNDWAVE_IMPORT_MAP)
    exp_off = imp_off + len(imp_bytes)
    bnd_off = exp_off + 72
    grp_off = bnd_off + len(SOUNDWAVE_EXPORT_BUNDLES)
    grp_sz = len(SOUNDWAVE_GRAPH_DATA)
    body_off = grp_off + grp_sz

    # Build tagged properties + bulk data payload
    props = bytearray()

    def add_int_prop(name_idx: int, val: int) -> None:
        props.extend(struct.pack("<6IBi", name_idx, 0, 24, 0, 4, 0, 0, val))

    def add_float_prop(name_idx: int, val: float) -> None:
        props.extend(struct.pack("<6IBf", name_idx, 0, 23, 0, 4, 0, 0, val))

    def add_obj_prop(name_idx: int, pkg_idx: int) -> None:
        props.extend(struct.pack("<6IBi", name_idx, 0, 27, 0, 4, 0, 0, pkg_idx))

    add_int_prop(13, 30)  # CompressionQuality = 30
    add_int_prop(39, 6)   # StreamingPriority = 6
    # SoundGroup (ByteProperty: ESoundGroup = SOUNDGROUP_Music)
    props.extend(struct.pack("<8IB2I", 36, 0, 11, 0, 8, 0, 20, 0, 0, 37, 0))
    # bLooping (BoolProperty = True)
    props.extend(struct.pack("<6I2B", 9, 0, 10, 0, 0, 0, 1, 0))
    add_float_prop(42, volume)              # Volume
    add_int_prop(26, ogg_info.channels)     # NumChannels
    add_int_prop(30, ogg_info.sample_rate)  # SampleRate
    add_obj_prop(34, -7)                    # SoundClassObject
    # VirtualizationMode (EnumProperty: EVirtualizationMode = EVirtualizationMode::PlayWhenSilent)
    props.extend(struct.pack("<8IB2I", 41, 0, 19, 0, 8, 0, 21, 0, 0, 22, 0))
    # ConcurrencySet (SetProperty of ObjectProperty: [-8])
    props.extend(struct.pack("<8IB2Ii", 15, 0, 31, 0, 12, 0, 27, 0, 0, 0, 1, -8))
    add_float_prop(18, ogg_info.duration)              # Duration
    add_float_prop(40, float(ogg_info.total_samples))  # TotalSamples
    add_obj_prop(6, -6)                                # AttenuationSettings
    # None terminator
    props.extend(struct.pack("<2I", 25, 0))

    # USoundWave bulk format container header
    cooked_hdr_sz = body_off - pad_len + 0xEA
    ogg_len = len(ogg_info.ogg_bytes)
    bulk_hdr = struct.pack(
        "<3I2I3Iq",
        0,                       # bSerializeGuid = 0
        1,                       # bCooked = 1
        1,                       # NumFormats = 1
        28, 0,                   # FormatName = FName("OGG10000-1-1-1-1-1")
        0x48,                    # BulkDataFlags = BULKDATA_ForceInlinePayload | BULKDATA_SingleUse
        ogg_len,                 # ElementCount
        ogg_len,                 # BulkDataSizeOnDisk
        cooked_hdr_sz + 0x1CE,   # BulkDataOffsetInFile
    )

    export_payload = bytes(props) + bulk_hdr + ogg_info.ogg_bytes + guid_bytes
    cooked_serial_sz = len(export_payload)
    global_imp = calc_global_import_index(f"{pkg_path}/{obj_name}")

    export_entry = struct.pack(
        "<QQIIQQQQQII",
        cooked_hdr_sz,
        cooked_serial_sz,
        7, 0,  # ObjectName = names[7]
        0xFFFFFFFFFFFFFFFF,
        0x44F26264628E498D,  # Class = /Script/Engine.SoundWave
        0xFFFFFFFFFFFFFFFF,
        0x4E0856E27FF445AE,  # Template = /Script/Engine.Default__SoundWave
        global_imp,
        0x0B,  # RF_Public | RF_Standalone | RF_Transactional
        0x00,
    )

    summary = struct.pack(
        "<6I10i",
        3, 0,  # Name = names[3]
        3, 0,  # SourceName = names[3]
        0x80000000,
        cooked_hdr_sz,
        nn_off, nn_sz, nh_off, nh_sz,
        imp_off, exp_off, bnd_off, grp_off, grp_sz, 0,
    )

    return (
        summary
        + nn_bytes
        + (b"\x00" * pad_len)
        + nh_bytes
        + imp_bytes
        + export_entry
        + SOUNDWAVE_EXPORT_BUNDLES
        + SOUNDWAVE_GRAPH_DATA
        + export_payload
    )


def find_default_template_ucas(root_dir: Optional[pathlib.Path] = None) -> Optional[pathlib.Path]:
    """Auto-detect precomputed CQT visualizer template file from known locations."""
    if root_dir is None:
        root_dir = pathlib.Path(__file__).resolve().parent

    candidates = [
        root_dir / ".cache" / "cqt_template.bin",
        root_dir / ".cache" / "cqt_template.ucas",
    ]
    for c in candidates:
        if c.is_file() and c.stat().st_size > 1000000:
            return c
    return None


def extract_template_nrt_channels(template_ucas_path: Optional[pathlib.Path] = None) -> Tuple[List[bytes], List[bytes], bytes]:
    """
    Extract 48-band (192-byte) CQT spectrum payloads for Channel 0 and Channel 1
    and the 28-byte channel intervals trailer from a template .ucas or .bin file.
    Falls back to generating dynamic, animated 48-band CQT frames if no template is found.
    """
    if template_ucas_path is None:
        template_ucas_path = find_default_template_ucas()

    if template_ucas_path and template_ucas_path.is_file():
        try:
            if template_ucas_path.suffix.lower() == ".bin":
                nrt = template_ucas_path.read_bytes()
            else:
                with template_ucas_path.open("rb") as f:
                    f.seek(0x006D1800)
                    nrt = f.read(0xB3E6BB)

            if len(nrt) >= 0x4A3 + 16:
                pos = 0x4A3 + 16  # skip bSerializeGuid, Duration, bIsSorted, NumChannels
                ch_frames: List[List[bytes]] = []
                for _ in range(2):
                    _, nf = struct.unpack_from("<II", nrt, pos)
                    pos += 8
                    frames = []
                    for _ in range(nf):
                        # Each frame is 204 bytes: int32 ch (4B), float ts (4B), int32 num_bands=48 (4B), float bands[48] (192B)
                        frames.append(nrt[pos + 12 : pos + 204])
                        pos += 204
                    ch_frames.append(frames)
                intervals_trailer = nrt[pos : pos + 28]  # NumIntervals(4B) + 2 * (ch(4B), min(4B), max(4B))
                if len(ch_frames[0]) > 0 and len(ch_frames[1]) > 0:
                    return ch_frames[0], ch_frames[1], intervals_trailer
        except Exception:
            pass

    # Dynamic fallback: generate 1,200 dynamic reactive CQT frames (12 seconds looping)
    import math
    ch0_frames: List[bytes] = []
    ch1_frames: List[bytes] = []
    intervals_trailer = struct.pack("<Iiffiff", 2, 0, -90.0, 13.247509, 1, -90.0, 13.4160385)
    num_dynamic_frames = 1200

    for i in range(num_dynamic_frames):
        t = i * 0.01
        beat = (math.sin(t * math.pi * 2.0) ** 4)
        mid_wave = math.sin(t * math.pi * 4.0 + 0.5)
        high_wave = math.cos(t * math.pi * 8.0)

        bands0 = []
        bands1 = []
        for b in range(48):
            freq_weight = (1.0 - (b / 48.0))
            if b < 12:
                v0 = -25.0 + beat * 35.0 * freq_weight + (b % 3) * 1.5
                v1 = -25.0 + beat * 34.0 * freq_weight + ((b + 1) % 3) * 1.5
            elif b < 32:
                v0 = -30.0 + mid_wave * 20.0 * freq_weight + (b % 4) * 1.0
                v1 = -30.0 + mid_wave * 19.0 * freq_weight + ((b + 2) % 4) * 1.0
            else:
                v0 = -35.0 + high_wave * 15.0 * freq_weight
                v1 = -35.0 + high_wave * 14.5 * freq_weight
            bands0.append(min(13.2, max(-60.0, v0)))
            bands1.append(min(13.4, max(-60.0, v1)))

        ch0_frames.append(struct.pack("<48f", *bands0))
        ch1_frames.append(struct.pack("<48f", *bands1))

    return ch0_frames, ch1_frames, intervals_trailer


def build_qnrt_zen_asset(
    on_pkg: str,
    on_name: str,
    nrt_pkg: str,
    nrt_name: str,
    ogg_info: OggVorbisInfo,
    ch0_templates: List[bytes],
    ch1_templates: List[bytes],
    intervals_trailer: bytes,
) -> bytes:
    """Build a duration-matched UE 4.26 Zen UConstantQNRT package (_ON_NRT.uasset in .ucas)."""
    names = list(QNRT_BASE_NAMES)
    names[0] = on_pkg
    names[1] = nrt_pkg
    names[6] = on_name
    names[7] = nrt_name

    nn_bytes, nh_bytes = _serialize_namemap(names)
    nn_off = 0x40
    nn_sz = len(nn_bytes)
    nh_off = (nn_off + nn_sz + 7) & ~7
    pad_len = nh_off - (nn_off + nn_sz)
    nh_sz = len(nh_bytes)

    imp_off = nh_off + nh_sz
    on_global_imp = calc_global_import_index(f"{on_pkg}/{on_name}")
    import_map = [
        0x46B0226F8F726A72,  # /Script/AudioSynesthesia.ConstantQNRT
        0x7F4EC9DC0404EC55,  # /Script/AudioSynesthesia.ConstantQNRTSettings
        0x5825AE05714D211F,  # /Script/AudioSynesthesia.Default__ConstantQNRT
        0xA11588B828AAB06E,  # /Game/Sound/World/BGM/VendingMachine/Turntable_ConstantQNRT_Setting.Turntable_ConstantQNRT_Setting
        0x5F8D6C4E578E9227,  # /Script/AudioSynesthesia.Default__ConstantQNRTSettings
        0xFFFFFFFFFFFFFFFF,
        0xFFFFFFFFFFFFFFFF,
        0x5A5310D638AF4C55,  # /Script/Engine.SoundWave
        on_global_imp,       # <on_pkg>.<on_name>
    ]
    imp_bytes = struct.pack(f"<{len(import_map)}Q", *import_map)

    exp_off = imp_off + len(imp_bytes)
    bnd_off = exp_off + 144  # 2 exports * 72 bytes
    export_bundles = bytes.fromhex(
        "00000000040000000000000000000000000000000100000001000000000000000100000001000000"
    )
    grp_off = bnd_off + len(export_bundles)
    on_pkg_id = calc_package_id(on_pkg)
    setting_pkg_id = 0x6CF3A48BEB6B3FCE  # /Game/Sound/World/BGM/VendingMachine/Turntable_ConstantQNRT_Setting
    graph_data = struct.pack(
        "<IQIIIQIII",
        2,
        on_pkg_id, 1, 0, 0,
        setting_pkg_id, 1, 0, 0,
    )
    grp_sz = len(graph_data)
    body_off = grp_off + grp_sz

    # Tagged properties for Export 0 (UConstantQNRT)
    props = bytearray()
    # Settings = PackageIndex(-4)
    props.extend(struct.pack("<6IBi", 18, 0, 16, 0, 4, 0, 0, -4))
    # Sound = PackageIndex(-9)
    props.extend(struct.pack("<6IBi", 19, 0, 16, 0, 4, 0, 0, -9))
    # DurationInSeconds = float(duration)
    props.extend(struct.pack("<6IBf", 13, 0, 14, 0, 4, 0, 0, ogg_info.duration))
    # None terminator
    props.extend(struct.pack("<2I", 15, 0))

    # Compute exact number of 0.01s CQT frames matching UE4.26 FConstantQAnalyzer
    hop_samples = max(1, round(ogg_info.sample_rate * 0.01))
    fft_half = round(ogg_info.sample_rate * (2048.0 / 48000.0))
    tail_guard = round(ogg_info.sample_rate * (3072.0 / 48000.0))
    num_frames = max(1, (ogg_info.total_samples - tail_guard) // hop_samples)

    cqt_buf = bytearray()
    cqt_buf.extend(struct.pack("<IfII", 0, ogg_info.duration, 1, 2))

    sr_f = float(ogg_info.sample_rate)
    for ch_idx, tmpl_list in ((0, ch0_templates), (1, ch1_templates)):
        cqt_buf.extend(struct.pack("<II", ch_idx, num_frames))
        t_len = len(tmpl_list)
        for i in range(num_frames):
            ts = (fft_half + i * hop_samples) / sr_f
            cqt_buf.extend(struct.pack("<IfI", ch_idx, ts, 48))
            cqt_buf.extend(tmpl_list[i % t_len])

    cqt_buf.extend(intervals_trailer)
    export0_payload = bytes(props) + bytes(cqt_buf)
    export1_payload = struct.pack("<3I", 15, 0, 0)  # FName("None") + bSerializeGuid=0

    cooked_hdr_sz = body_off - pad_len + 0x137
    exp0_serial_sz = len(export0_payload)
    exp1_serial_off = cooked_hdr_sz + exp0_serial_sz
    exp1_serial_sz = len(export1_payload)

    exp0_global_imp = calc_global_import_index(f"{nrt_pkg}/{nrt_name}")
    exp1_global_imp = calc_global_import_index(f"{nrt_pkg}/{nrt_name}/DefaultConstantQNRTSettings")

    export0_entry = struct.pack(
        "<QQIIQQQQQII",
        cooked_hdr_sz,
        exp0_serial_sz,
        7, 0,  # ObjectName = names[7]
        0xFFFFFFFFFFFFFFFF,
        0x46B0226F8F726A72,
        0xFFFFFFFFFFFFFFFF,
        0x5825AE05714D211F,
        exp0_global_imp,
        0x0B,
        0x00,
    )
    export1_entry = struct.pack(
        "<QQIIQQQQQII",
        exp1_serial_off,
        exp1_serial_sz,
        12, 0,  # ObjectName = DefaultConstantQNRTSettings
        0x0000000000000000,  # Outer = Export[0]
        0x7F4EC9DC0404EC55,
        0xFFFFFFFFFFFFFFFF,
        0x5F8D6C4E578E9227,
        exp1_global_imp,
        0x40009,
        0x00,
    )

    summary = struct.pack(
        "<6I10i",
        1, 0,  # Name = names[1]
        1, 0,  # SourceName = names[1]
        0x80000000,
        cooked_hdr_sz,
        nn_off, nn_sz, nh_off, nh_sz,
        imp_off, exp_off, bnd_off, grp_off, grp_sz, 0,
    )

    return (
        summary
        + nn_bytes
        + (b"\x00" * pad_len)
        + nh_bytes
        + imp_bytes
        + export0_entry
        + export1_entry
        + export_bundles
        + graph_data
        + export0_payload
        + export1_payload
    )


TEXTURE2D_FIXED_NAMES: List[str] = [
    "/Script/CoreUObject",
    "/Script/Engine",
    "ByteProperty",
    "Class",
    "CompressionSettings",
    "Default__Texture2D",
    "Guid",
    "ImportedSize",
    "IntPoint",
    "LightingGuid",
    "LODGroup",
    "None",
    "Package",
    "PF_B8G8R8A8",
    "StructProperty",
    "TC_EditorIcon",
    "Texture2D",
    "TextureCompressionSettings",
    "TextureGroup",
    "TEXTUREGROUP_Project47",
]

TEXTURE2D_IMPORT_MAP: Tuple[int, int, int] = (
    0x5B93BCA796D1FA6F,  # /Script/Engine.Texture2D
    0x51ACCED3DC7C0922,  # /Script/CoreUObject.Class
    0x6BFAD34AC8B1F6D0,  # /Script/Engine.Default__Texture2D
)

TEXTURE2D_EXPORT_BUNDLES = bytes.fromhex(
    "000000000200000000000000000000000000000001000000"
)


def build_texture2d_zen_asset(
    pkg_path: str,
    obj_name: str,
    bgra_pixels: bytes,
    guid_bytes: bytes,
) -> bytes:
    """
    Build a UE 4.26 Zen UTexture2D package (.uasset in .ucas) storing a 256x256
    uncompressed PF_B8G8R8A8 inline mipmap (matching Album_*.uasset).
    """
    expected_len = 256 * 256 * 4
    if len(bgra_pixels) != expected_len:
        raise ValueError(f"Texture pixel buffer must be {expected_len} bytes (256x256 BGRA), got {len(bgra_pixels)}")
    if len(guid_bytes) != 16:
        raise ValueError(f"LightingGuid must be 16 bytes, got {len(guid_bytes)}")

    names = sorted([pkg_path, obj_name, *TEXTURE2D_FIXED_NAMES], key=str.lower)
    idx_pkg = names.index(pkg_path)
    idx_obj = names.index(obj_name)
    idx_pf = names.index("PF_B8G8R8A8")
    idx_none = names.index("None")

    nn_bytes, nh_bytes = _serialize_namemap(names)
    nn_off = 0x40
    nn_sz = len(nn_bytes)
    nh_off = (nn_off + nn_sz + 7) & ~7
    pad_len = nh_off - (nn_off + nn_sz)
    nh_sz = len(nh_bytes)

    imp_off = nh_off + nh_sz
    imp_bytes = struct.pack("<3Q", *TEXTURE2D_IMPORT_MAP)
    exp_off = imp_off + len(imp_bytes)
    bnd_off = exp_off + 72
    grp_off = bnd_off + len(TEXTURE2D_EXPORT_BUNDLES)
    grp_sz = 4
    graph_data = b"\x00\x00\x00\x00"
    body_off = grp_off + grp_sz

    cooked_hdr_sz = body_off - pad_len + 0xB3
    cooked_serial_sz = 0x40090
    skip_off = cooked_hdr_sz + cooked_serial_sz - 8
    bulk_offset_in_file = cooked_hdr_sz + 0x78

    pre_pix = (
        bytes.fromhex("0504010202030001000000010000")
        + guid_bytes
        + bytes.fromhex("0750000000000100010001000000")
        + struct.pack("<IIQ", idx_pf, 0, skip_off)
        + struct.pack("<IIII", 256, 256, 1, 12)
        + b"PF_B8G8R8A8\x00"
        + struct.pack("<IIIIIIq", 0, 1, 1, 0x48, expected_len, expected_len, bulk_offset_in_file)
    )
    post_pix = struct.pack("<IIIIII", 256, 256, 1, 0, idx_none, 0)
    export_payload = pre_pix + bgra_pixels + post_pix

    global_imp = calc_global_import_index(f"{pkg_path}/{obj_name}")
    export_entry = struct.pack(
        "<QQIIQQQQQII",
        cooked_hdr_sz,
        cooked_serial_sz,
        idx_obj, 0,
        0xFFFFFFFFFFFFFFFF,
        TEXTURE2D_IMPORT_MAP[0],
        0xFFFFFFFFFFFFFFFF,
        TEXTURE2D_IMPORT_MAP[2],
        global_imp,
        0x0B,
        0x00,
    )

    summary = struct.pack(
        "<6I10i",
        idx_pkg, 0,
        idx_pkg, 0,
        0x80002000,
        cooked_hdr_sz,
        nn_off, nn_sz, nh_off, nh_sz,
        imp_off, exp_off, bnd_off, grp_off, grp_sz, 0,
    )

    return (
        summary
        + nn_bytes
        + (b"\x00" * pad_len)
        + nh_bytes
        + imp_bytes
        + export_entry
        + TEXTURE2D_EXPORT_BUNDLES
        + graph_data
        + export_payload
    )


# ============================================================================
# 5. IoStore (.ucas / .utoc) Container Assembler
# ============================================================================

def build_container_header_chunk_multi(
    container_id: int,
    packages: List[Tuple[int, int, int, int, int, Tuple[int, ...]]],
) -> bytes:
    """
    Build Chunk 0 (FIoContainerHeader) for any number of packages.

    Each item in `packages` is:
      (pkg_id, pkg_size, export_count, export_bundle_count, load_order, imported_pkg_ids)
    """
    pkg_count = len(packages)
    total_imps = sum(len(p[5]) for p in packages)
    store_entries_sz = pkg_count * 32 + total_imps * 8

    hdr = bytearray()
    hdr.extend(struct.pack("<QI", container_id, pkg_count))
    hdr.extend(struct.pack("<I", 0))  # NamesSize = 0
    hdr.extend(struct.pack("<IQ", 8, 0x00000000C1640000))  # NamesHashes
    hdr.extend(struct.pack("<I", pkg_count))
    for pkg_id, *_ in packages:
        hdr.extend(struct.pack("<Q", pkg_id))
    hdr.extend(struct.pack("<I", store_entries_sz))

    imp_buf = bytearray()
    imp_table_base = pkg_count * 32
    for i, (_, pkg_size, exp_cnt, eb_cnt, load_ord, imp_ids) in enumerate(packages):
        if imp_ids:
            imp_rel = (imp_table_base + len(imp_buf)) - (i * 32 + 24)
            imp_cnt = len(imp_ids)
            for iid in imp_ids:
                imp_buf.extend(struct.pack("<Q", iid))
        else:
            imp_rel = 0
            imp_cnt = 0
        hdr.extend(struct.pack("<QIIIIII", pkg_size, exp_cnt, eb_cnt, load_ord, 0, imp_cnt, imp_rel))

    hdr.extend(imp_buf)
    hdr.extend(struct.pack("<I", 0))  # RedirectsCount = 0

    aligned_sz = max(0x10000, ((len(hdr) + 0xFFFF) // 0x10000) * 0x10000)
    return bytes(hdr).ljust(aligned_sz, b"\x00")


def _write_fstring(s: str) -> bytes:
    raw = s.encode("utf-8") + b"\x00"
    return struct.pack("<i", len(raw)) + raw


def build_utoc_directory_index_multi(entries: List[Tuple[str, int]]) -> bytes:
    """
    Build FIoDirectoryIndexResource under MountPoint '../../../SB/Content/' for an
    arbitrary set of (pkg_path, toc_entry_index) pairs.
    """
    mount_point = "../../../SB/Content/"
    string_table: List[str] = []
    string_idx: Dict[str, int] = {}

    def intern(s: str) -> int:
        if s not in string_idx:
            string_idx[s] = len(string_table)
            string_table.append(s)
        return string_idx[s]

    # Directory nodes: key is tuple of folder names (root = ())
    dir_nodes: Dict[Tuple[str, ...], Dict[str, object]] = {
        (): {"idx": 0, "name_idx": 0xFFFFFFFF, "children": [], "files": []}
    }
    dir_order: List[Tuple[str, ...]] = [()]

    def ensure_dir(parts: Tuple[str, ...]) -> None:
        if parts in dir_nodes:
            return
        parent = parts[:-1]
        ensure_dir(parent)
        idx = len(dir_order)
        dir_nodes[parts] = {
            "idx": idx,
            "name_idx": intern(parts[-1]),
            "children": [],
            "files": [],
        }
        dir_order.append(parts)
        dir_nodes[parent]["children"].append(idx)  # type: ignore[union-attr]

    file_records: List[Tuple[int, int, int]] = []  # (name_idx, next_file, toc_idx)
    for pkg_path, toc_idx in entries:
        rel = pkg_path.removeprefix("/Game/").strip("/")
        parts = rel.split("/")
        folder_parts = tuple(parts[:-1])
        ensure_dir(folder_parts)
        f_name_idx = intern(parts[-1] + ".uasset")
        f_idx = len(file_records)
        file_records.append((f_name_idx, 0xFFFFFFFF, toc_idx))
        dir_nodes[folder_parts]["files"].append(f_idx)  # type: ignore[union-attr]

    # Pass 1: initialize directory entries with NameIdx, FirstChild, NextSibling=NONE, FirstFile
    dir_entries: List[List[int]] = [[0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF] for _ in dir_order]
    for parts in dir_order:
        node = dir_nodes[parts]
        d_idx: int = node["idx"]  # type: ignore[assignment]
        children: List[int] = node["children"]  # type: ignore[assignment]
        files: List[int] = node["files"]  # type: ignore[assignment]
        dir_entries[d_idx][0] = node["name_idx"]  # type: ignore[assignment]
        dir_entries[d_idx][1] = children[0] if children else 0xFFFFFFFF
        dir_entries[d_idx][3] = files[0] if files else 0xFFFFFFFF

    # Pass 2: link NextSibling and NextFile chains without clobbering
    for parts in dir_order:
        node = dir_nodes[parts]
        children = node["children"]  # type: ignore[assignment]
        files = node["files"]  # type: ignore[assignment]
        for j in range(len(children) - 1):
            dir_entries[children[j]][2] = children[j + 1]
        for j in range(len(files) - 1):
            f_cur = files[j]
            fn_i, _, udata = file_records[f_cur]
            file_records[f_cur] = (fn_i, files[j + 1], udata)

    buf = bytearray()
    buf.extend(_write_fstring(mount_point))
    buf.extend(struct.pack("<I", len(dir_entries)))
    for nm, fc, ns, ff in dir_entries:
        buf.extend(struct.pack("<4I", nm, fc, ns, ff))
    buf.extend(struct.pack("<I", len(file_records)))
    for fn_i, nf, udata in file_records:
        buf.extend(struct.pack("<3I", fn_i, nf, udata))
    buf.extend(struct.pack("<I", len(string_table)))
    for s in string_table:
        buf.extend(_write_fstring(s))
    return bytes(buf)


def build_ucas_and_utoc_multi(
    container_id: int,
    package_chunks: List[Tuple[str, int, int, int, int, Tuple[int, ...], bytes]],
) -> Tuple[bytes, bytes]:
    """
    Assemble a complete .ucas and .utoc container for an arbitrary list of packages.

    Each item in `package_chunks` is:
      (pkg_path, pkg_id, export_count, export_bundle_count, load_order, imported_pkg_ids, uasset_bytes)
    """
    hdr_specs = [
        (pkg_id, len(uasset_bytes), exp_cnt, eb_cnt, load_ord, imp_ids)
        for (_, pkg_id, exp_cnt, eb_cnt, load_ord, imp_ids, uasset_bytes) in package_chunks
    ]
    chunk0_hdr = build_container_header_chunk_multi(container_id, hdr_specs)

    chunks: List[Tuple[int, int, bytes]] = [(container_id, 10, chunk0_hdr)]
    dir_entries: List[Tuple[str, int]] = []
    for toc_idx, (pkg_path, pkg_id, _, _, _, _, uasset_bytes) in enumerate(package_chunks, start=1):
        chunks.append((pkg_id, 2, uasset_bytes))
        dir_entries.append((pkg_path, toc_idx))

    block_size = 0x10000
    ucas_buf = bytearray()
    chunk_ids_buf = bytearray()
    offset_lengths_buf = bytearray()
    blocks_buf = bytearray()
    metas_buf = bytearray()

    logical_block_idx = 0
    total_blocks = 0

    for cid, ctype, cdata in chunks:
        chunk_ids_buf.extend(struct.pack("<QHBB", cid, 0, 0, ctype))
        logical_off = logical_block_idx * block_size
        clen = len(cdata)
        offset_lengths_buf.extend(logical_off.to_bytes(5, "big") + clen.to_bytes(5, "big"))

        pos = 0
        while pos < clen:
            b_data = cdata[pos : pos + block_size]
            b_len = len(b_data)
            b_ucas_off = len(ucas_buf)
            blocks_buf.extend(
                b_ucas_off.to_bytes(5, "little")
                + b_len.to_bytes(3, "little")
                + b_len.to_bytes(3, "little")
                + b"\x00"
            )
            ucas_buf.extend(b_data)
            pos += b_len
            logical_block_idx += 1
            total_blocks += 1

        rem = len(ucas_buf) % 0x10
        if rem != 0:
            ucas_buf.extend(b"\x00" * (0x10 - rem))

        sha1_digest = hashlib.sha1(cdata).digest()
        metas_buf.extend(sha1_digest + (b"\x00" * 13))

    dir_index_bytes = build_utoc_directory_index_multi(dir_entries)

    utoc_hdr = bytearray(144)
    utoc_hdr[0:16] = b"-==--==--==--==-"
    struct.pack_into("<BBH", utoc_hdr, 16, 2, 0, 0)
    struct.pack_into("<4I", utoc_hdr, 20, 144, len(chunks), total_blocks, 12)
    struct.pack_into("<4I", utoc_hdr, 36, 0, 32, block_size, len(dir_index_bytes))
    struct.pack_into("<IQ4I", utoc_hdr, 52, 0, container_id, 0, 0, 0, 0)
    struct.pack_into("<BBHIQ", utoc_hdr, 80, 0x08, 0, 0, 0, 0)

    utoc_bytes = (
        bytes(utoc_hdr)
        + bytes(chunk_ids_buf)
        + bytes(offset_lengths_buf)
        + bytes(blocks_buf)
        + dir_index_bytes
        + bytes(metas_buf)
    )
    return bytes(ucas_buf), utoc_bytes


# ============================================================================
# 6. Game.locres In-Game Song Title Patcher & UE4.26 v11 .pak Builder
# ============================================================================

_OODLE_DECOMPRESS_CACHE: Optional[Tuple[Callable, ctypes.Array]] = None


def _get_oodle_decompress(exe_path: pathlib.Path) -> Tuple[Callable, ctypes.Array]:
    """Map oo2::OodleLZ_Decompress from SB-Win64-Shipping.exe into memory once per process."""
    global _OODLE_DECOMPRESS_CACHE
    if _OODLE_DECOMPRESS_CACHE is not None:
        return _OODLE_DECOMPRESS_CACHE

    if sys.platform != "win32":
        raise RuntimeError("Extracting base game assets from Stellar Blade requires Windows (win32).")

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.VirtualAlloc.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32, ctypes.c_uint32]
    kernel32.VirtualAlloc.restype = ctypes.c_void_p
    kernel32.GetProcAddress.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    kernel32.GetProcAddress.restype = ctypes.c_void_p
    kernel32.LoadLibraryA.argtypes = [ctypes.c_char_p]
    kernel32.LoadLibraryA.restype = ctypes.c_void_p

    alloc_ptr = kernel32.VirtualAlloc(0x140000000, 0x07500000, 0x3000, 0x40)
    if not alloc_ptr:
        raise RuntimeError("Failed to allocate virtual memory for Oodle decompression.")
    with exe_path.open("rb") as ef:
        for vma, foff, sz in [
            (0x140001000, 0x0000400, 0x055B2000),
            (0x1455B3000, 0x055B2400, 0x0161D000),
            (0x146BD0000, 0x06BCF400, 0x002C3800),
        ]:
            ef.seek(foff)
            ctypes.memmove(vma, ef.read(sz), sz)

    ucrt = kernel32.LoadLibraryA(b"ucrtbase.dll")
    for iat_addr, fn_name in {
        0x1455B46A0: b"memcpy",
        0x1455B4650: b"memset",
        0x1455B4658: b"memcmp",
        0x1455B4660: b"memmove",
    }.items():
        ctypes.c_uint64.from_address(iat_addr).value = kernel32.GetProcAddress(ucrt, fn_name)
    ctypes.c_uint32.from_address(0x146EA7588).value = 1

    oodle_decompress = ctypes.CFUNCTYPE(
        ctypes.c_int64,
        ctypes.c_void_p, ctypes.c_int64, ctypes.c_void_p, ctypes.c_int64,
        ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_void_p,
        ctypes.c_int64, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
        ctypes.c_int64, ctypes.c_int32,
    )(0x144E6E630)
    scratch_mem = ctypes.create_string_buffer(4 * 1024 * 1024)
    _OODLE_DECOMPRESS_CACHE = (oodle_decompress, scratch_mem)
    return _OODLE_DECOMPRESS_CACHE


def extract_base_uasset_from_iostore(
    game_dir: Optional[pathlib.Path],
    pkg_path: str,
    cache_name: str,
    cache_dir: Optional[pathlib.Path] = None,
) -> bytes:
    """
    Extract and Oodle-decompress a base game Zen .uasset (e.g. TurntableSoundTable or StringTable_UI)
    from pakchunk0-WindowsNoEditor.{utoc,ucas}, caching it under `cache_dir / cache_name`.
    """
    if cache_dir:
        cached = cache_dir / cache_name
        if cached.is_file():
            return cached.read_bytes()

    root_dir = pathlib.Path(__file__).resolve().parent
    candidate_dirs: List[pathlib.Path] = []
    if game_dir is not None:
        candidate_dirs.append(game_dir)
    candidate_dirs.extend([
        root_dir / "Context" / "StellarBlade",
        root_dir / "StellarBlade",
    ])

    resolved_dir: Optional[pathlib.Path] = None
    for d in candidate_dirs:
        if (
            (d / "SB" / "Content" / "Paks" / "pakchunk0-WindowsNoEditor.utoc").is_file()
            and (d / "SB" / "Content" / "Paks" / "pakchunk0-WindowsNoEditor.ucas").is_file()
            and (d / "SB" / "Binaries" / "Win64" / "SB-Win64-Shipping.exe").is_file()
        ):
            resolved_dir = d
            break

    if resolved_dir is None:
        raise FileNotFoundError(
            "Cannot locate base game pakchunk0-WindowsNoEditor.{utoc,ucas} and SB-Win64-Shipping.exe "
            f"to extract {pkg_path}. Please set a valid Stellar Blade directory."
        )

    utoc_path = resolved_dir / "SB" / "Content" / "Paks" / "pakchunk0-WindowsNoEditor.utoc"
    ucas_path = resolved_dir / "SB" / "Content" / "Paks" / "pakchunk0-WindowsNoEditor.ucas"
    exe_path = resolved_dir / "SB" / "Binaries" / "Win64" / "SB-Win64-Shipping.exe"

    utoc = utoc_path.read_bytes()
    hdr_size, entry_count, comp_block_count, _ = struct.unpack_from("<4I", utoc, 20)
    _, _, comp_block_size, _ = struct.unpack_from("<4I", utoc, 36)
    chunk_ids_off = hdr_size
    off_len_off = hdr_size + 12 * entry_count
    blocks_off = hdr_size + 22 * entry_count

    target_id = calc_package_id(pkg_path)
    toc_idx: Optional[int] = None
    for i in range(entry_count):
        cid, _, _, ctype = struct.unpack_from("<QHBB", utoc, chunk_ids_off + i * 12)
        if cid == target_id and ctype == 2:
            toc_idx = i
            break

    if toc_idx is None:
        raise ValueError(f"Package {pkg_path!r} (0x{target_id:016x}) not found in {utoc_path.name}")

    raw_ol = utoc[off_len_off + toc_idx * 10 : off_len_off + (toc_idx + 1) * 10]
    logical_off = int.from_bytes(raw_ol[:5], "big")
    length = int.from_bytes(raw_ol[5:], "big")
    first_blk = logical_off // comp_block_size
    last_blk = (logical_off + length - 1) // comp_block_size
    off_in_first = logical_off % comp_block_size

    oodle_decompress, scratch_mem = _get_oodle_decompress(exe_path)
    out = bytearray()
    with ucas_path.open("rb") as uf:
        for bidx in range(first_blk, last_blk + 1):
            b_rec = utoc[blocks_off + bidx * 12 : blocks_off + (bidx + 1) * 12]
            phys_off = int.from_bytes(b_rec[:5], "little")
            comp_sz = int.from_bytes(b_rec[5:8], "little")
            uncomp_sz = int.from_bytes(b_rec[8:11], "little")
            method = b_rec[11]
            uf.seek(phys_off)
            comp_data = uf.read(comp_sz)
            if method == 0:
                out.extend(comp_data)
            else:
                rbuf = ctypes.create_string_buffer(uncomp_sz)
                r = oodle_decompress(
                    comp_data, comp_sz, rbuf, uncomp_sz, 1, 0, 0, None, 0, None, None, scratch_mem, len(scratch_mem), 3
                )
                if r != uncomp_sz:
                    raise RuntimeError(f"Oodle decompression failed for {pkg_path}: {r} != {uncomp_sz}")
                out.extend(rbuf.raw)

    raw_asset = bytes(out[off_in_first : off_in_first + length])
    if cache_dir:
        cache_dir.mkdir(parents=True, exist_ok=True)
        (cache_dir / cache_name).write_bytes(raw_asset)
    return raw_asset


def extract_base_locres_from_game_pak(
    game_dir: pathlib.Path,
    lang: str = "en",
    cache_dir: Optional[pathlib.Path] = None,
) -> bytes:
    """
    Extract and Oodle-decompress SB/Content/Localization/Game/<lang>/Game.locres
    from StellarBlade/SB/Content/Paks/pakchunk0-WindowsNoEditor.pak using the
    statically linked oo2::OodleLZ_Decompress inside SB-Win64-Shipping.exe.
    """
    if cache_dir:
        cached = cache_dir / f"Game_{lang}.locres"
        if cached.is_file():
            return cached.read_bytes()

    pak_path = game_dir / "SB" / "Content" / "Paks" / "pakchunk0-WindowsNoEditor.pak"
    exe_path = game_dir / "SB" / "Binaries" / "Win64" / "SB-Win64-Shipping.exe"
    if not pak_path.is_file() or not exe_path.is_file():
        raise FileNotFoundError(
            f"Cannot locate base game pak/exe at {pak_path} and {exe_path}"
        )

    target_rel_path = f"SB/Content/Localization/Game/{lang}/Game.locres"

    # Find encoded entry offset in pakchunk0.pak FullDirectoryIndex
    with pak_path.open("rb") as pf:
        pf.seek(-512, 2)
        tail = pf.read(512)
        m_pos = tail.find(b"\xE1\x12\x6F\x5A")
        _, idx_off, idx_sz = struct.unpack_from("<IQQ", tail, m_pos + 4)
        pf.seek(idx_off)
        idx_data = pf.read(idx_sz)

        pos = 0
        mlen = struct.unpack_from("<i", idx_data, pos)[0]
        pos += 4 + mlen
        _, _, has_ph = struct.unpack_from("<IQI", idx_data, pos)
        pos += 16 + (36 if has_ph else 0)
        has_fd = struct.unpack_from("<I", idx_data, pos)[0]
        pos += 4
        fd_off, fd_sz = struct.unpack_from("<QQ", idx_data, pos)
        pos += 36
        enc_sz = struct.unpack_from("<I", idx_data, pos)[0]
        pos += 4
        enc_entries = idx_data[pos : pos + enc_sz]

        pf.seek(fd_off)
        fd_data = pf.read(fd_sz)

    # Search FullDirectoryIndex for target_rel_path
    def _read_pak_fstr(buf: bytes, p: int) -> Tuple[str, int]:
        l = struct.unpack_from("<i", buf, p)[0]
        p += 4
        if l == 0:
            return "", p
        if l < 0:
            l = -l
            s = buf[p : p + (l - 1) * 2].decode("utf-16le", errors="replace")
            p += l * 2
        else:
            s = buf[p : p + l - 1].decode("utf-8", errors="replace")
            p += l
        return s, p

    fpos = 0
    d_cnt = struct.unpack_from("<I", fd_data, fpos)[0]
    fpos += 4
    target_enc_off = None
    target_dir = f"SB/Content/Localization/Game/{lang}/"
    for _ in range(d_cnt):
        d_name, fpos = _read_pak_fstr(fd_data, fpos)
        f_cnt = struct.unpack_from("<I", fd_data, fpos)[0]
        fpos += 4
        for _ in range(f_cnt):
            f_name, fpos = _read_pak_fstr(fd_data, fpos)
            e_off = struct.unpack_from("<i", fd_data, fpos)[0]
            fpos += 4
            if d_name.lower() == target_dir.lower() and f_name.lower() == "game.locres":
                target_enc_off = e_off
                break
        if target_enc_off is not None:
            break

    if target_enc_off is None:
        raise ValueError(f"Could not find {target_rel_path} in pakchunk0-WindowsNoEditor.pak")

    file_off = struct.unpack_from("<I", enc_entries, target_enc_off + 8)[0]

    oodle_decompress, scratch_mem = _get_oodle_decompress(exe_path)

    with pak_path.open("rb") as pf:
        pf.seek(file_off)
        hdr = pf.read(256)
        _, _, usize, method = struct.unpack_from("<QQQI", hdr, 0)
        blk_cnt = struct.unpack_from("<I", hdr, 48)[0]
        blocks = [struct.unpack_from("<QQ", hdr, 52 + i * 16) for i in range(blk_cnt)]
        blk_sz = struct.unpack_from("<I", hdr, 52 + blk_cnt * 16 + 1)[0]
        if blk_sz == 0:
            blk_sz = usize
        out = bytearray()
        rem = usize
        for b_start, b_end in blocks:
            actual_start = file_off + b_start if b_start < file_off else b_start
            pf.seek(actual_start)
            b_comp = pf.read(b_end - b_start)
            this_u = min(rem, blk_sz)
            if method == 1:
                out.extend(zlib.decompress(b_comp))
            elif method == 2:
                rbuf = ctypes.create_string_buffer(this_u)
                r = oodle_decompress(
                    b_comp, len(b_comp), rbuf, this_u, 1, 0, 0, None, 0, None, None, scratch_mem, len(scratch_mem), 3
                )
                if r != this_u:
                    raise RuntimeError(f"Oodle decompression failed for Game.locres: {r} != {this_u}")
                out.extend(rbuf.raw)
            rem -= this_u

    raw_locres = bytes(out)
    if cache_dir:
        cache_dir.mkdir(parents=True, exist_ok=True)
        (cache_dir / f"Game_{lang}.locres").write_bytes(raw_locres)
    return raw_locres


def patch_locres_title(locres_bytes: bytes, ui_key: str, new_title: str) -> bytes:
    """
    Losslessly update the localized string for `ui_key` (e.g. 'UI_Turntable_Music_008')
    inside a UE4 FTextLocalizationResource v4 (.locres) binary.
    """
    ver = locres_bytes[16]
    str_arr_off = struct.unpack_from("<q", locres_bytes, 17)[0]

    def read_fstr(buf: bytes, p: int) -> Tuple[str, int]:
        l = struct.unpack_from("<i", buf, p)[0]
        p += 4
        if l == 0:
            return "", p
        if l < 0:
            l = -l
            s = buf[p : p + (l - 1) * 2].decode("utf-16le", errors="replace")
            p += l * 2
        else:
            s = buf[p : p + l - 1].decode("utf-8", errors="replace")
            p += l
        return s, p

    def encode_fstr(s: str) -> bytes:
        try:
            raw = s.encode("ascii") + b"\x00"
            return struct.pack("<i", len(raw)) + raw
        except UnicodeEncodeError:
            raw16 = s.encode("utf-16le") + b"\x00\x00"
            return struct.pack("<i", -(len(raw16) // 2)) + raw16

    # Parse string table at str_arr_off
    pos = str_arr_off
    str_cnt = struct.unpack_from("<I", locres_bytes, pos)[0]
    pos += 4
    loc_strings: List[Tuple[bytes, int]] = []
    for _ in range(str_cnt):
        s_start = pos
        l = struct.unpack_from("<i", locres_bytes, pos)[0]
        pos += 4 + (-l * 2 if l < 0 else l)
        raw_fstr = locres_bytes[s_start:pos]
        ref_cnt = struct.unpack_from("<I", locres_bytes, pos)[0] if ver >= 2 else 1
        if ver >= 2:
            pos += 4
        loc_strings.append((raw_fstr, ref_cnt))

    # Find ui_key in key tree
    pos = 29
    ns_cnt = struct.unpack_from("<I", locres_bytes, pos)[0]
    pos += 4
    target_str_idx = None
    target_idx_pos = None

    for _ in range(ns_cnt):
        pos += 4
        _, pos = read_fstr(locres_bytes, pos)
        key_cnt = struct.unpack_from("<I", locres_bytes, pos)[0]
        pos += 4
        for _ in range(key_cnt):
            pos += 4
            k_name, pos = read_fstr(locres_bytes, pos)
            _, str_idx, _ = struct.unpack_from("<III", locres_bytes, pos)
            if k_name == ui_key:
                target_str_idx = str_idx
                target_idx_pos = pos + 4
            pos += 12

    if target_str_idx is None or target_idx_pos is None:
        raise ValueError(f"Key {ui_key!r} not found in Game.locres")

    key_tree_buf = bytearray(locres_bytes[:str_arr_off])
    new_fstr = encode_fstr(new_title)
    old_fstr, ref_cnt = loc_strings[target_str_idx]

    if ref_cnt <= 1:
        loc_strings[target_str_idx] = (new_fstr, 1)
    else:
        loc_strings[target_str_idx] = (old_fstr, ref_cnt - 1)
        new_idx = len(loc_strings)
        loc_strings.append((new_fstr, 1))
        struct.pack_into("<I", key_tree_buf, target_idx_pos, new_idx)

    # Rebuild string table
    new_str_arr = bytearray(struct.pack("<I", len(loc_strings)))
    for raw_s, r_cnt in loc_strings:
        new_str_arr.extend(raw_s)
        if ver >= 2:
            new_str_arr.extend(struct.pack("<I", r_cnt))

    return bytes(key_tree_buf) + bytes(new_str_arr)


def build_v11_pak(
    files: Optional[Dict[str, bytes]] = None,
    path_hash_seed: int = 0xE5DF0F41,
) -> bytes:
    """
    Build a UE 4.26 Version 11 .pak file.
    When `files` is empty or None, builds a 339-byte dummy .pak container
    to trigger IoStore container mounting for the companion .utoc/.ucas.
    When `files` contains entries (e.g. {'SB/Content/Localization/Game/en/Game.locres': ...}),
    packs them with valid inline FPakEntry headers, PathHashIndex, and FullDirectoryIndex.
    """
    if not files:
        mount_point = "/"
        ph_bytes = struct.pack("<II", 0, 0)
        fd_bytes = struct.pack("<I", 0)
        ph_sha1 = hashlib.sha1(ph_bytes).digest()
        fd_sha1 = hashlib.sha1(fd_bytes).digest()

        primary_idx = bytearray()
        primary_idx.extend(_write_fstring(mount_point))
        primary_idx.extend(struct.pack("<IQ", 0, path_hash_seed))
        primary_idx.extend(struct.pack("<IQQ", 1, 0x6A, len(ph_bytes)) + ph_sha1)
        primary_idx.extend(struct.pack("<IQQ", 1, 0x72, len(fd_bytes)) + fd_sha1)
        primary_idx.extend(struct.pack("<II", 0, 0))
        idx_sha1 = hashlib.sha1(primary_idx).digest()

        footer = bytearray(221)
        struct.pack_into("<IIQQ", footer, 17, 0x5A6F12E1, 11, 0, len(primary_idx))
        footer[41:61] = idx_sha1
        return bytes(primary_idx) + ph_bytes + fd_bytes + bytes(footer)

    mount_point = "../../../"
    data_buf = bytearray()
    enc_entries_buf = bytearray()
    ph_entries: List[Tuple[int, int]] = []
    dir_tree: Dict[str, List[Tuple[str, int]]] = {}

    for rel_path, content in sorted(files.items()):
        rel_norm = rel_path.replace("\\", "/").lstrip("/")
        file_offset = len(data_buf)
        c_len = len(content)
        c_sha1 = hashlib.sha1(content).digest()

        # Inline FPakEntry (53 bytes for uncompressed)
        inline_hdr = struct.pack("<QQQI", 0, c_len, c_len, 0) + c_sha1 + struct.pack("<BI", 0, 0)
        data_buf.extend(inline_hdr)
        data_buf.extend(content)

        # Encoded entry (12 bytes: flags=0xE0000000, uint32 offset, uint32 size)
        enc_off = len(enc_entries_buf)
        enc_entries_buf.extend(struct.pack("<III", 0xE0000000, file_offset, c_len))

        ph_entries.append((ue4_fnv64_path_hash(rel_norm, path_hash_seed), enc_off))

        # Populate directory tree (including parent directories)
        parts = rel_norm.split("/")
        for d_depth in range(1, len(parts)):
            d_key = "/".join(parts[:d_depth]) + "/"
            dir_tree.setdefault(d_key, [])
        dir_tree.setdefault("/", [])
        parent_dir = "/".join(parts[:-1]) + "/" if len(parts) > 1 else "/"
        dir_tree[parent_dir].append((parts[-1], enc_off))

    # Serialize PathHashIndex
    ph_buf = bytearray(struct.pack("<I", len(ph_entries)))
    for h_val, e_off in ph_entries:
        ph_buf.extend(struct.pack("<Qi", h_val, e_off))
    ph_bytes = bytes(ph_buf)
    ph_sha1 = hashlib.sha1(ph_bytes).digest()

    # Serialize FullDirectoryIndex
    fd_buf = bytearray(struct.pack("<I", len(dir_tree)))
    for d_name in sorted(dir_tree.keys()):
        f_list = dir_tree[d_name]
        fd_buf.extend(_write_fstring(d_name))
        fd_buf.extend(struct.pack("<I", len(f_list)))
        for f_name, e_off in sorted(f_list):
            fd_buf.extend(_write_fstring(f_name))
            fd_buf.extend(struct.pack("<i", e_off))
    fd_bytes = bytes(fd_buf)
    fd_sha1 = hashlib.sha1(fd_bytes).digest()

    idx_offset = len(data_buf)
    # Calculate PrimaryIndex size to determine ph_offset and fd_offset
    mount_bytes = _write_fstring(mount_point)
    primary_idx_sz = len(mount_bytes) + 4 + 8 + 4 + 36 + 4 + 36 + 4 + len(enc_entries_buf) + 4
    ph_offset = idx_offset + primary_idx_sz
    fd_offset = ph_offset + len(ph_bytes)

    primary_idx = bytearray()
    primary_idx.extend(mount_bytes)
    primary_idx.extend(struct.pack("<IQ", len(files), path_hash_seed))
    primary_idx.extend(struct.pack("<IQQ", 1, ph_offset, len(ph_bytes)) + ph_sha1)
    primary_idx.extend(struct.pack("<IQQ", 1, fd_offset, len(fd_bytes)) + fd_sha1)
    primary_idx.extend(struct.pack("<I", len(enc_entries_buf)))
    primary_idx.extend(enc_entries_buf)
    primary_idx.extend(struct.pack("<I", 0))
    idx_sha1 = hashlib.sha1(primary_idx).digest()

    footer = bytearray(221)
    struct.pack_into("<IIQQ", footer, 17, 0x5A6F12E1, 11, idx_offset, len(primary_idx))
    footer[41:61] = idx_sha1

    return bytes(data_buf) + bytes(primary_idx) + ph_bytes + fd_bytes + bytes(footer)


# ============================================================================
# 7. High-Level Mod Builder & CLI Entrypoint
# ============================================================================

def build_custom_music_mod(
    tracks: List[CustomTrackInput],
    output_dir: pathlib.Path,
    mod_name: str = "CampMusic_Custom_295_P",
    game_dir: Optional[pathlib.Path] = None,
    template_ucas_path: Optional[pathlib.Path] = None,
    cache_dir: Optional[pathlib.Path] = None,
    container_id: Optional[int] = None,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> Tuple[pathlib.Path, pathlib.Path, pathlib.Path]:
    """
    Build a single combined <mod_name>.{pak,utoc,ucas} container that ADDS all custom
    tracks in `tracks` to Stellar Blade's Camp Turntable WHILE keeping all 34 original
    in-game songs intact.
    """
    if not tracks:
        raise ValueError("At least one custom track is required.")

    if not mod_name.endswith("_P"):
        mod_name = f"{mod_name}_P"

    if container_id is None:
        container_id = 0x774ACE2200000000 | (cityhash64(mod_name.lower().encode("utf-8")) & 0xFFFFFFFF)

    if cache_dir is None:
        cache_dir = pathlib.Path(__file__).resolve().parent / ".cache"

    base_tst = extract_base_uasset_from_iostore(
        game_dir=game_dir,
        pkg_path=TURNTABLE_SOUND_TABLE_PKG,
        cache_name="TurntableSoundTable.uasset",
        cache_dir=cache_dir,
    )
    base_st = extract_base_uasset_from_iostore(
        game_dir=game_dir,
        pkg_path=STRING_TABLE_UI_PKG,
        cache_name="StringTable_UI.uasset",
        cache_dir=cache_dir,
    )

    ch0_tmpl, ch1_tmpl, intervals_trailer = extract_template_nrt_channels(template_ucas_path)

    imp_soundwave = (0xEE7FF41A0D3CA7AB, 0xB1183BCD5AABABD6, 0xEA022F9FB35903D0)
    setting_pkg_id = 0x6CF3A48BEB6B3FCE  # /Game/Sound/World/BGM/VendingMachine/Turntable_ConstantQNRT_Setting

    custom_rows: List[Tuple[int, str, str, str, str, str]] = []
    string_entries: List[Tuple[str, str]] = []
    audio_pkg_chunks: List[Tuple[str, int, int, int, int, Tuple[int, ...], bytes]] = []

    next_load_order = 60
    total = len(tracks)
    for k, trk in enumerate(tracks, start=1):
        if progress_callback:
            progress_callback(k, total, trk.title)

        base_name = f"BGM_CAMP_CUSTOM_{k:03d}"
        off_name = f"{base_name}_OFF"
        on_name = f"{base_name}_ON"
        nrt_name = f"{base_name}_ON_NRT"

        off_pkg = f"/Game/Sound/World/BGM/VendingMachine/{off_name}"
        on_pkg = f"/Game/Sound/World/BGM/VendingMachine/{on_name}"
        nrt_pkg = f"/Game/Sound/World/BGM/VendingMachine/{nrt_name}"

        off_id = calc_package_id(off_pkg)
        on_id = calc_package_id(on_pkg)
        nrt_id = calc_package_id(nrt_pkg)

        guid_off = uuid.uuid5(uuid.NAMESPACE_DNS, f"sb-camp-custom-{k}-off-{trk.title}").bytes
        guid_on = uuid.uuid5(uuid.NAMESPACE_DNS, f"sb-camp-custom-{k}-on-{trk.title}").bytes

        uasset_off = build_soundwave_zen_asset(
            pkg_path=off_pkg,
            obj_name=off_name,
            ogg_info=trk.ogg_off,
            volume=trk.volume_off,
            guid_bytes=guid_off,
        )
        uasset_on = build_soundwave_zen_asset(
            pkg_path=on_pkg,
            obj_name=on_name,
            ogg_info=trk.ogg_on,
            volume=trk.volume_on,
            guid_bytes=guid_on,
        )
        uasset_nrt = build_qnrt_zen_asset(
            on_pkg=on_pkg,
            on_name=on_name,
            nrt_pkg=nrt_pkg,
            nrt_name=nrt_name,
            ogg_info=trk.ogg_on,
            ch0_templates=ch0_tmpl,
            ch1_templates=ch1_tmpl,
            intervals_trailer=intervals_trailer,
        )

        audio_pkg_chunks.append((off_pkg, off_id, 1, 1, next_load_order, imp_soundwave, uasset_off))
        audio_pkg_chunks.append((on_pkg, on_id, 1, 1, next_load_order + 1, imp_soundwave, uasset_on))
        audio_pkg_chunks.append((nrt_pkg, nrt_id, 2, 1, next_load_order + 2, (on_id, setting_pkg_id), uasset_nrt))
        next_load_order += 3

        resolved_image_path = trk.image_path or DEFAULT_ALBUM_COVER
        if trk.cover_bgra is not None:
            tex_name = f"UI_Turntable_CustomCover_{k:03d}"
            tex_pkg = f"/Game/Art/UI/Texture/Turntable/{tex_name}"
            tex_id = calc_package_id(tex_pkg)
            guid_tex = uuid.uuid5(uuid.NAMESPACE_DNS, f"sb-camp-custom-{k}-cover-{trk.title}").bytes
            uasset_tex = build_texture2d_zen_asset(
                pkg_path=tex_pkg,
                obj_name=tex_name,
                bgra_pixels=trk.cover_bgra,
                guid_bytes=guid_tex,
            )
            audio_pkg_chunks.append((tex_pkg, tex_id, 1, 1, next_load_order, (), uasset_tex))
            next_load_order += 1
            resolved_image_path = f"Texture2D'{tex_pkg}.{tex_name}'"

        ui_key = f"UI_Turntable_Music_Custom_{k:03d}"
        row_id = 9000 + k
        custom_rows.append((
            row_id,
            f"SoundWave'{on_pkg}.{on_name}'",
            f"SoundWave'{off_pkg}.{off_name}'",
            ui_key,
            resolved_image_path,
            f"ConstantQNRT'{nrt_pkg}.{nrt_name}'",
        ))
        string_entries.append((ui_key, trk.title))

    patched_tst = patch_turntable_sound_table(base_tst, custom_rows)
    patched_st = patch_string_table_ui(base_st, string_entries)

    package_chunks: List[Tuple[str, int, int, int, int, Tuple[int, ...], bytes]] = [
        (TURNTABLE_SOUND_TABLE_PKG, calc_package_id(TURNTABLE_SOUND_TABLE_PKG), 1, 1, 10, (), patched_tst),
        (STRING_TABLE_UI_PKG, calc_package_id(STRING_TABLE_UI_PKG), 1, 1, 11, (), patched_st),
    ]
    package_chunks.extend(audio_pkg_chunks)

    ucas_bytes, utoc_bytes = build_ucas_and_utoc_multi(
        container_id=container_id,
        package_chunks=package_chunks,
    )
    pak_bytes = build_v11_pak(files=None)

    output_dir.mkdir(parents=True, exist_ok=True)
    pak_out = output_dir / f"{mod_name}.pak"
    utoc_out = output_dir / f"{mod_name}.utoc"
    ucas_out = output_dir / f"{mod_name}.ucas"

    pak_out.write_bytes(pak_bytes)
    utoc_out.write_bytes(utoc_bytes)
    ucas_out.write_bytes(ucas_bytes)

    return pak_out, utoc_out, ucas_out


def find_off_audio_candidate(song_path: pathlib.Path) -> Optional[pathlib.Path]:
    """Locate a companion ambient/muffled _off audio file if present alongside `song_path`."""
    for suffix_tag in ("_off", "_muffled", "_ambient", "_OFF"):
        cand = song_path.with_name(f"{song_path.stem}{suffix_tag}{song_path.suffix}")
        if cand.is_file():
            return cand
    return None


def scan_music_folder(music_dir: pathlib.Path) -> List[pathlib.Path]:
    """Return naturally sorted primary audio files in `music_dir`."""
    if not music_dir.is_dir():
        raise FileNotFoundError(f"Music directory not found: {music_dir}")

    audio_files = [
        p for p in music_dir.iterdir()
        if p.is_file()
        and p.suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS
        and not p.name.startswith(".")
        and not p.stem.lower().endswith(("_off", "_muffled", "_ambient"))
    ]
    audio_files.sort(key=natural_sort_key)
    return audio_files


def build_custom_music_from_folder(
    music_dir: pathlib.Path,
    output_dir: Optional[pathlib.Path] = None,
    mod_name: str = "CampMusic_Custom_295_P",
    game_dir: Optional[pathlib.Path] = None,
    install: bool = False,
    volume_on: float = 1.100000023841858,
    volume_off: float = 0.6000000238418579,
    image_path: str = DEFAULT_ALBUM_COVER,
    custom_image_file: Optional[pathlib.Path] = None,
    use_embedded_art: bool = True,
    reencode: bool = False,
    template_ucas_path: Optional[pathlib.Path] = None,
    cache_dir: Optional[pathlib.Path] = None,
    progress_callback: Optional[Callable[[int, int, pathlib.Path, str], None]] = None,
) -> Tuple[List[CustomTrackInput], pathlib.Path, pathlib.Path, pathlib.Path]:
    """
    Bundle all audio files in `music_dir` into a single combined mod that keeps all
    34 original Camp Turntable tracks intact.
    """
    audio_files = scan_music_folder(music_dir)
    if not audio_files:
        raise ValueError(
            f"No supported audio files ({', '.join(sorted(SUPPORTED_AUDIO_EXTENSIONS))}) found in {music_dir}"
        )

    if install:
        if game_dir is None:
            raise ValueError("game_dir is required when install is True.")
        final_out_dir = game_dir / "SB" / "Content" / "Paks" / "~mods"
    else:
        final_out_dir = output_dir or (music_dir.parent / "dist")

    custom_tracks: List[CustomTrackInput] = []
    total = len(audio_files)
    for idx, song_path in enumerate(audio_files, start=1):
        title = infer_song_title(song_path)
        if progress_callback:
            progress_callback(idx, total, song_path, title)
        img_fallback, cover_bgra, cover_lbl = resolve_track_cover_art(
            audio_path=song_path,
            fallback_image_path=image_path,
            custom_image_file=custom_image_file,
            use_embedded=use_embedded_art,
        )
        ogg_on = load_or_convert_ogg(song_path, force_reencode=reencode)
        off_cand = find_off_audio_candidate(song_path)
        ogg_off = load_or_convert_ogg(off_cand, force_reencode=reencode) if off_cand else ogg_on
        custom_tracks.append(
            CustomTrackInput(
                title=title,
                ogg_on=ogg_on,
                ogg_off=ogg_off,
                volume_on=volume_on,
                volume_off=volume_off,
                image_path=img_fallback,
                cover_bgra=cover_bgra,
                cover_label=cover_lbl,
            )
        )

    pak_p, utoc_p, ucas_p = build_custom_music_mod(
        tracks=custom_tracks,
        output_dir=final_out_dir,
        mod_name=mod_name,
        game_dir=game_dir,
        template_ucas_path=template_ucas_path,
        cache_dir=cache_dir,
    )
    return custom_tracks, pak_p, utoc_p, ucas_p


def print_tracks_table() -> None:
    print(f"{'#':>2} | {'UI Key':<31} | {'In-Game English Title':<33} | {'ON Asset Name':<35} | {'ON Chunk ID'}")
    print("-" * 130)
    for t in CAMP_TRACKS:
        print(f"{t.index:2d} | {t.ui_key:<31} | {t.title:<33} | {t.on_name:<35} | 0x{t.on_id:016x}")


def get_default_game_dir(root_dir: pathlib.Path) -> pathlib.Path:
    steam_default = pathlib.Path(r"C:\Program Files (x86)\Steam\steamapps\common\StellarBlade")
    candidates = [
        steam_default,
        pathlib.Path(r"C:\Program Files (x86)\Steam\steamapps\common\Stellar Blade"),
        pathlib.Path(r"C:\Program Files\Steam\steamapps\common\StellarBlade"),
        root_dir / "StellarBlade",
        root_dir / "Context" / "StellarBlade",
    ]
    for c in candidates:
        if c.is_dir() and ((c / "SB" / "Content" / "Paks").is_dir() or (c / "SB.exe").is_file()):
            return c.resolve()
    return steam_default


def main(argv: Optional[List[str]] = None) -> int:
    root_dir = pathlib.Path(__file__).resolve().parent
    default_game = get_default_game_dir(root_dir)

    parser = argparse.ArgumentParser(
        description=(
            "Add custom camp music (.ogg/.wav/.mp3/.flac) to Stellar Blade's Camp Turntable "
            "while keeping all 34 original tracks intact."
        )
    )
    parser.add_argument("--gui", action="store_true", help="Launch the native Windows graphical user interface.")
    parser.add_argument("--list-tracks", action="store_true", help="List the 34 base-game Camp Turntable tracks and exit.")
    parser.add_argument("-i", "--input", action="append", type=pathlib.Path, help="Input audio file (.ogg, .wav, .mp3, .flac, etc.). Repeat -i to bundle multiple songs.")
    parser.add_argument("--input-off", action="append", type=pathlib.Path, help="Optional separate ambient (_OFF) audio file paired with each -i input.")
    parser.add_argument("--title", action="append", type=str, help="Optional custom song title paired with each -i input (defaults to cleaned filename).")
    parser.add_argument("--cover", action="append", type=pathlib.Path, help="Optional custom cover art image (.png/.jpg/.webp) paired with each -i input.")
    parser.add_argument("--album-art", type=str, default=None, help="Fallback album cover preset name/number, Texture2D asset path, or image file path.")
    parser.add_argument("--no-embedded-art", action="store_true", help="Do not auto-extract embedded album art from audio files (use preset fallback unless --cover is set).")
    parser.add_argument("-n", "--mod-name", default="CampMusic_Custom_295_P", help="Output mod base name (default: CampMusic_Custom_295_P).")
    parser.add_argument("-o", "--output-dir", type=pathlib.Path, default=root_dir / "dist", help="Output directory for .pak/.utoc/.ucas files.")
    parser.add_argument("--install", action="store_true", help="Install directly into StellarBlade/SB/Content/Paks/~mods.")
    parser.add_argument("--volume-on", type=float, default=1.100000023841858, help="Playback volume for _ON asset (default: 1.1).")
    parser.add_argument("--volume-off", type=float, default=0.6000000238418579, help="Playback volume for _OFF asset (default: 0.6).")
    parser.add_argument("--reencode", action="store_true", help="Force re-encoding input .ogg via ffmpeg to 48000 Hz stereo.")
    parser.add_argument("--template-ucas", type=pathlib.Path, default=find_default_template_ucas(root_dir), help="Optional path to a template .ucas or .bin file for CQT spectrum patterns.")
    parser.add_argument("--game-dir", type=pathlib.Path, default=default_game, help="Path to StellarBlade root directory.")
    parser.add_argument("--batch", nargs="?", const=root_dir / "Music", type=pathlib.Path, help="Add all songs from a folder (defaults to ./Music) into one combined mod.")

    args = parser.parse_args(argv)

    if args.gui:
        if sys.platform != "win32":
            parser.error("The native Windows GUI requires Windows (win32).")
        import camp_music_gui
        return camp_music_gui.launch_gui()

    if args.list_tracks:
        print_tracks_table()
        return 0

    out_dir = (args.game_dir / "SB" / "Content" / "Paks" / "~mods") if args.install else args.output_dir
    global_cover_file: Optional[pathlib.Path] = None
    if args.album_art and pathlib.Path(args.album_art).is_file():
        global_cover_file = pathlib.Path(args.album_art)
        image_path = DEFAULT_ALBUM_COVER
    else:
        image_path = resolve_album_cover(args.album_art)
    use_embedded_art = not args.no_embedded_art
    tmpl_path = args.template_ucas if (args.template_ucas and args.template_ucas.is_file()) else None
    cache_dir = root_dir / ".cache"

    if args.batch is not None:
        music_folder = args.batch.resolve()
        if not music_folder.is_dir():
            parser.error(f"Music directory not found: {music_folder}")
        print(f"Adding all custom tracks from '{music_folder}' (keeping all 34 original tracks)...")

        def cli_progress(cur: int, total: int, song: pathlib.Path, title: str) -> None:
            print(f"  [{cur:02d}/{total:02d}] +{title!r} ({song.name})...")

        built_tracks, pak_p, utoc_p, ucas_p = build_custom_music_from_folder(
            music_dir=music_folder,
            output_dir=out_dir,
            mod_name=args.mod_name,
            game_dir=args.game_dir,
            install=args.install,
            volume_on=args.volume_on,
            volume_off=args.volume_off,
            image_path=image_path,
            custom_image_file=global_cover_file,
            use_embedded_art=use_embedded_art,
            reencode=args.reencode,
            template_ucas_path=tmpl_path,
            cache_dir=cache_dir,
            progress_callback=cli_progress,
        )
        print(f"\nSUCCESS! Added {len(built_tracks)} custom track(s) while keeping all 34 original tracks:")
        for idx, trk in enumerate(built_tracks, start=1):
            cov_note = f" | Cover: {trk.cover_label}" if trk.cover_label else ""
            print(f"  [Custom {idx:02d}] {trk.title!r} ({trk.ogg_on.duration:.2f}s{cov_note})")
        print("  Output Files:")
        print(f"    PAK : {pak_p} ({pak_p.stat().st_size:,} bytes)")
        print(f"    UTOC: {utoc_p} ({utoc_p.stat().st_size:,} bytes)")
        print(f"    UCAS: {ucas_p} ({ucas_p.stat().st_size:,} bytes)")
        return 0

    if not args.input:
        parser.error("the following arguments are required: -i/--input or --batch (or use --gui / --list-tracks)")

    inputs: List[pathlib.Path] = args.input
    titles: List[str] = args.title or []
    off_inputs: List[pathlib.Path] = args.input_off or []
    cover_inputs: List[pathlib.Path] = args.cover or []

    custom_tracks: List[CustomTrackInput] = []
    for idx, song_path in enumerate(inputs):
        song_title = titles[idx] if idx < len(titles) and titles[idx].strip() else infer_song_title(song_path)
        cov_file = cover_inputs[idx] if idx < len(cover_inputs) else global_cover_file
        if cov_file is not None and str(cov_file).strip().lower() in ("", "none", "auto"):
            cov_file = None
        img_fallback, cover_bgra, cover_lbl = resolve_track_cover_art(
            audio_path=song_path,
            fallback_image_path=image_path,
            custom_image_file=cov_file,
            use_embedded=use_embedded_art,
        )
        ogg_on = load_or_convert_ogg(song_path, force_reencode=args.reencode)
        if idx < len(off_inputs):
            ogg_off = load_or_convert_ogg(off_inputs[idx], force_reencode=args.reencode)
        else:
            off_cand = find_off_audio_candidate(song_path)
            ogg_off = load_or_convert_ogg(off_cand, force_reencode=args.reencode) if off_cand else ogg_on
        custom_tracks.append(
            CustomTrackInput(
                title=song_title,
                ogg_on=ogg_on,
                ogg_off=ogg_off,
                volume_on=args.volume_on,
                volume_off=args.volume_off,
                image_path=img_fallback,
                cover_bgra=cover_bgra,
                cover_label=cover_lbl,
            )
        )

    pak_p, utoc_p, ucas_p = build_custom_music_mod(
        tracks=custom_tracks,
        output_dir=out_dir,
        mod_name=args.mod_name,
        game_dir=args.game_dir,
        template_ucas_path=tmpl_path,
        cache_dir=cache_dir,
    )

    print(f"Successfully built Stellar Blade Custom Camp Music Mod (all 34 original tracks preserved):")
    for idx, trk in enumerate(custom_tracks, start=1):
        hop_samples = max(1, round(trk.ogg_on.sample_rate * 0.01))
        tail_guard = round(trk.ogg_on.sample_rate * (3072.0 / 48000.0))
        nrt_frames = max(1, (trk.ogg_on.total_samples - tail_guard) // hop_samples)
        cov_note = f" | Cover: {trk.cover_label}" if trk.cover_label else ""
        print(
            f"  [Custom {idx:02d}] {trk.title!r} | {trk.ogg_on.sample_rate} Hz, {trk.ogg_on.channels}ch, "
            f"{trk.ogg_on.duration:.3f}s | {nrt_frames:,} QNRT frames{cov_note}"
        )
    print(f"  Output Files:")
    print(f"    PAK : {pak_p} ({pak_p.stat().st_size:,} bytes)")
    print(f"    UTOC: {utoc_p} ({utoc_p.stat().st_size:,} bytes)")
    print(f"    UCAS: {ucas_p} ({ucas_p.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
