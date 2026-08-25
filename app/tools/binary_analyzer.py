"""Honest binary structure analysis with the Python standard library only.

Scope, stated plainly: file identification, hashes, header/section structure
for ELF/PE/Mach-O, and string extraction (ASCII + UTF-16LE). This is a
structure overview for triage — NOT disassembly or decompilation. No imports
are guessed, no behaviors are inferred, and unknown fields stay unknown.
"""
from __future__ import annotations

import hashlib
import re
import struct
from pathlib import Path
from typing import Any, Dict, List

from app.utils.logger import app_logger, audit_logger

_ELF_MACHINES = {
    0x03: "x86", 0x3E: "x86-64", 0x28: "ARM", 0xB7: "AArch64", 0xF3: "RISC-V",
    0x08: "MIPS", 0x14: "PowerPC", 0x16: "S390",
}
_PE_MACHINES = {
    0x014C: "i386", 0x8664: "x86-64", 0x01C0: "ARM", 0xAA64: "ARM64",
    0x0200: "IA-64", 0x01F0: "PowerPC",
}
_MACHO_MAGICS = {
    0xFEEDFACE: ("32-bit", "big-endian"), 0xCEFAEDFE: ("32-bit", "little-endian"),
    0xFEEDFACF: ("64-bit", "big-endian"), 0xCFFAEDFE: ("64-bit", "little-endian"),
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _identify(header: bytes) -> Dict[str, Any]:
    kind = {"format": "unknown", "detail": None}
    if header[:4] == b"\x7fELF":
        kind["format"] = "ELF"
    elif header[:2] == b"MZ":
        kind["format"] = "PE/COFF (MZ)"
    elif struct.unpack(">I", header[:4])[0] in _MACHO_MAGICS if len(header) >= 4 else False:
        kind["format"] = "Mach-O"
    elif header[:4] == b"PK\x03\x04":
        kind["format"] = "ZIP container (jar/apk/docx/zip)"
    elif header[:4] == b"%PDF":
        kind["format"] = "PDF"
    elif header[:2] == b"\x1f\x8b":
        kind["format"] = "gzip"
    elif header[:3] == b"\xfd7z":
        kind["format"] = "7-zip"
    elif header[:6] == b"Rar!\x1a\x07":
        kind["format"] = "RAR"
    elif header[:3] == b"\x42\x82" or header[:3] == b"\x00\x00\x01":
        kind["format"] = "possibly a disk image"
    return kind


def _parse_elf(blob: bytes) -> Dict[str, Any]:
    info: Dict[str, Any] = {}
    if len(blob) < 64:
        return {"parse_error": "truncated ELF header"}
    info["elf_class"] = "64-bit" if blob[4] == 2 else "32-bit"
    info["endianness"] = "little" if blob[5] == 1 else "big"
    endian = "<" if blob[5] == 1 else ">"
    (e_type, e_machine, _version, entry, _phoff, shoff, _flags, _ehsize,
     _phentsize, _phnum, shentsize, shnum, shstrndx) = struct.unpack(
        endian + "HHIQQQIHHHHHH", blob[16:64]
    )
    info["elf_type"] = {2: "executable", 3: "shared object", 1: "relocatable", 4: "core"}.get(e_type, f"unknown({e_type})")
    info["machine"] = _ELF_MACHINES.get(e_machine, f"unknown({e_machine:#x})")
    info["entry_point"] = f"{entry:#x}"
    sections: List[str] = []
    if shoff and shnum and shoff + shnum * shentsize <= len(blob):
        for i in range(shnum):
            off = shoff + i * shentsize
            sh_name, _sh_type, _sh_flags, _sh_addr, sh_offset, sh_size = struct.unpack(
                endian + "IIQQQQ", blob[off:off + 40]
            )
            name = ""
            strtab_off = shoff + shstrndx * shentsize
            if 0 < shstrndx < shnum:
                _sn, _st, _sf, _sa, stro, strs = struct.unpack(endian + "IIQQQQ", blob[strtab_off:strtab_off + 40])
                end = blob.find(b"\x00", stro + sh_name, stro + strs)
                if end != -1:
                    name = blob[stro + sh_name:end].decode("latin-1")
            sections.append(f"{name or f'section{i}'}@{sh_offset:#x}+{sh_size:#x}")
    info["sections"] = sections[:64]
    info["section_count"] = shnum
    return info


def _parse_pe(blob: bytes) -> Dict[str, Any]:
    info: Dict[str, Any] = {}
    if len(blob) < 0x40:
        return {"parse_error": "truncated MZ header"}
    pe_off = struct.unpack("<I", blob[0x3C:0x40])[0]
    if pe_off + 24 > len(blob) or blob[pe_off:pe_off + 4] != b"PE\x00\x00":
        return {"parse_error": "MZ without a valid PE signature"}
    machine, num_sections, timestamp, _sym, _symnum, opt_size, _chars = struct.unpack(
        "<HHIIIHH", blob[pe_off + 4:pe_off + 24]
    )
    info["machine"] = _PE_MACHINES.get(machine, f"unknown({machine:#x})")
    info["timestamp_utc"] = timestamp
    info["section_count"] = num_sections
    opt_magic = struct.unpack("<H", blob[pe_off + 24:pe_off + 26])[0] if opt_size >= 2 else 0
    info["optional_header"] = {0x10B: "PE32", 0x20B: "PE32+"}.get(opt_magic, f"unknown({opt_magic:#x})" if opt_size else "none")
    sections = []
    sec_off = pe_off + 24 + opt_size
    for i in range(min(num_sections, 64)):
        off = sec_off + i * 40
        if off + 40 > len(blob):
            break
        name = blob[off:off + 8].rstrip(b"\x00").decode("latin-1", "replace")
        _vsize, _vaddr, rsize, raw = struct.unpack("<IIII", blob[off + 8:off + 24])
        sections.append(f"{name}@{raw:#x}+{rsize:#x}")
    info["sections"] = sections
    return info


def extract_strings(path: str, *, min_length: int = 5, limit: int = 5000) -> Dict[str, Any]:
    """Extract printable ASCII and UTF-16LE strings from any file."""
    target = Path(path)
    if not target.is_file():
        return {"success": False, "error": f"File not found: '{path}'"}
    min_length = max(4, int(min_length))
    blob = target.read_bytes()
    ascii_hits = [m.group(0).decode("latin-1") for m in
                  re.finditer(rb"[\x20-\x7e]{%d,}" % min_length, blob)]
    utf16_hits = []
    for m in re.finditer((rb"(?:[\x20-\x7e]\x00){%d,}" % min_length), blob):
        utf16_hits.append(m.group(0).decode("utf-16-le"))
    return {
        "success": True,
        "file": str(target),
        "ascii_strings": ascii_hits[:limit],
        "ascii_count": len(ascii_hits),
        "utf16le_strings": utf16_hits[:limit],
        "utf16le_count": len(utf16_hits),
        "truncated": len(ascii_hits) > limit or len(utf16_hits) > limit,
        "note": "Extraction only: strings may be coincidental; no behavior is inferred.",
    }


def analyze_binary(path: str) -> Dict[str, Any]:
    """Identify a binary and parse its header/section structure honestly."""
    target = Path(path)
    if not target.is_file():
        return {"success": False, "error": f"File not found: '{path}'"}
    blob = target.read_bytes()
    header = blob[:512]
    result: Dict[str, Any] = {
        "success": True,
        "file": str(target),
        "size_bytes": len(blob),
        "sha256": _sha256(target),
    }
    result.update(_identify(header))
    fmt = result.get("format")
    try:
        if fmt == "ELF":
            result.update(_parse_elf(blob))
        elif fmt == "PE/COFF (MZ)":
            result.update(_parse_pe(blob))
        elif fmt == "Mach-O":
            magic = struct.unpack(">I", header[:4])[0]
            bits, endian = _MACHO_MAGICS[magic]
            result["macho_bits"], result["macho_endianness"] = bits, endian
    except Exception as exc:
        result["parse_error"] = f"structure parsing failed: {exc}"
    result["note"] = "Structure overview only — not disassembly; unknown fields stay unknown."
    audit_logger.info("Binary analyzed: %s (%s)", target.name, fmt)
    return result
