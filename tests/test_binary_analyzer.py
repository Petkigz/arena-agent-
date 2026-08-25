"""Binary structure analysis: identification, headers, sections, strings.

Pure-stdlib triage: ELF/PE/Mach-O headers and sections, container formats,
SHA-256, ASCII + UTF-16LE string extraction. Unknown stays unknown; nothing
about behavior is inferred.
"""
import struct

from app.tools.binary_analyzer import analyze_binary, extract_strings


def make_elf64(tmp_path):
    """Minimal but structurally valid ELF64 little-endian shared object."""
    e_ident = b"\x7fELF" + bytes([2, 1, 1, 0]) + b"\x00" * 8
    shoff, ehsize, phentsize, phnum, shentsize, shnum, shstrndx = 64, 64, 56, 0, 64, 3, 1
    header = e_ident + struct.pack(
        "<HHIQQQIHHHHHH",
        3,              # e_type: ET_DYN
        0x3E,           # e_machine: x86-64
        1,              # version
        0x401000,       # entry
        0,              # phoff
        shoff,          # shoff = 64
        0,              # flags
        ehsize, phentsize, phnum, shentsize, shnum, shstrndx,
    )
    def shdr(name, sh_type, offset, size):
        return struct.pack("<IIQQQQIIQQ", name, sh_type, 0, 0, offset, size, 0, 0, 1, 0)
    sections = (
        shdr(0, 0, 0, 0) +                                  # SHT_NULL
        shdr(1, 3, 0, 0) +                                  # .shstrtab (offset set below)
        shdr(11, 1, 0x1000, 0x40)                           # .text (PROGBITS)
    )
    blob = bytearray(header) + sections                     # sections live at shoff=64
    shstr_off = len(blob)                                   # string table after the section table
    shstrtab = b"\x00.shstrtab\x00.text\x00"
    blob += shstrtab
    # Point .shstrtab's sh_offset/sh_size at its real location (section entry 1).
    blob[64 + 64 + 24:64 + 64 + 40] = struct.pack("<QQ", shstr_off, len(shstrtab))
    path = tmp_path / "libdemo.so"
    path.write_bytes(bytes(blob))
    return path


def make_pe32(tmp_path):
    """Minimal PE32: MZ header, PE signature, optional header, one section."""
    dos = bytearray(b"MZ" + b"\x00" * 0x3A) + struct.pack("<I", 0x80)
    blob = bytearray(dos)
    blob += b"\x00" * (0x80 - len(blob))
    pe = struct.pack("<IHHIIIHH", 0, 0x014C, 1, 0x5F5E10FF, 0, 0, 0xF0, 0x0102)[:4]
    pe = b"PE\x00\x00" + struct.pack("<HHIIIHH", 0x014C, 1, 0x5F5E10FF, 0, 0, 0xF0, 0x22)
    blob += pe
    blob += struct.pack("<H", 0x10B) + b"\x00" * (0xF0 - 2)  # PE32 optional header
    sec = b".text\x00\x00\x00" + struct.pack("<IIIIIIHHI", 0x40, 0x1000, 0x200, 0x80, 0, 0, 0, 0, 0)
    blob += sec
    path = tmp_path / "demo.exe"
    path.write_bytes(bytes(blob))
    return path


def test_elf_structure_is_parsed(tmp_path):
    result = analyze_binary(str(make_elf64(tmp_path)))
    assert result["success"] is True and result["format"] == "ELF"
    assert result["elf_class"] == "64-bit" and result["endianness"] == "little"
    assert result["elf_type"] == "shared object" and result["machine"] == "x86-64"
    assert result["entry_point"] == "0x401000"
    assert result["section_count"] == 3
    assert any(s.startswith(".text@") for s in result["sections"])
    assert any(s.startswith(".shstrtab@") for s in result["sections"])
    assert len(result["sha256"]) == 64


def test_pe_structure_is_parsed(tmp_path):
    result = analyze_binary(str(make_pe32(tmp_path)))
    assert result["success"] is True and result["format"] == "PE/COFF (MZ)"
    assert result["machine"] == "i386"
    assert result["optional_header"] == "PE32"
    assert result["section_count"] == 1
    assert result["sections"] and result["sections"][0].startswith(".text@")


def test_containers_and_unknowns_are_identified_without_inference(tmp_path):
    pdf = tmp_path / "a.pdf"; pdf.write_bytes(b"%PDF-1.7 ...")
    assert analyze_binary(str(pdf))["format"] == "PDF"
    unknown = tmp_path / "blob.bin"; unknown.write_bytes(bytes(range(256)) * 4)
    result = analyze_binary(str(unknown))
    assert result["format"] in ("unknown", "possibly a disk image")
    assert "not disassembly" in result["note"]
    missing = analyze_binary(str(tmp_path / "nope"))
    assert missing["success"] is False and "not found" in missing["error"].lower()


def test_string_extraction_ascii_and_utf16(tmp_path):
    blob = (
        b"\x00" * 16 + b"LOGIN_ENDPOINT=https://api.example.test/v1" + b"\x00\x00" +
        "pässwörd-utf16".encode("utf-16-le") + b"\x00\x00" + b"ab" + b"\x00" * 8
    )
    target = tmp_path / "strings.bin"; target.write_bytes(blob)
    result = extract_strings(str(target), min_length=6)
    assert result["success"] is True
    assert any("LOGIN_ENDPOINT" in s for s in result["ascii_strings"])
    assert any("utf16" in s for s in result["utf16le_strings"])
    assert result["ascii_count"] >= 1 and result["utf16le_count"] >= 1
    assert "no behavior is inferred" in result["note"]
    # Short noise does not leak through.
    assert all(len(s) >= 6 for s in result["ascii_strings"])


def test_truncated_headers_report_parse_errors_honestly(tmp_path):
    bad = tmp_path / "bad.so"; bad.write_bytes(b"\x7fELF\x02\x01")
    result = analyze_binary(str(bad))
    assert result["success"] is True and result["format"] == "ELF"
    assert "parse_error" in result and "truncated" in result["parse_error"]
