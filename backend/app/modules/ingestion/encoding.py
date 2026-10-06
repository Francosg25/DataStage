def decode_asc(raw: bytes, preferred: str) -> tuple[str, str]:
    candidates = (preferred, "cp1252" if preferred == "utf-8-sig" else "utf-8-sig")
    if raw.startswith(b"\xef\xbb\xbf"):
        candidates = ("utf-8-sig", "cp1252")

    for encoding in candidates:
        try:
            content = raw.decode(encoding, errors="strict")
        except UnicodeDecodeError:
            continue
        if encoding != preferred and any(
            ord(char) < 32 and char not in "\t\r\n" for char in content
        ):
            continue
        return content, encoding

    raise UnicodeError("El ASC no se pudo decodificar con UTF-8 ni Windows-1252.")