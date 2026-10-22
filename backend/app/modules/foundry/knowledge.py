"""Small approved documentation retrieval; never reads arbitrary paths or env files."""
from pathlib import Path
import re
import unicodedata

DOC_ROOT = Path(__file__).resolve().parents[4] / "docs"
APPROVED = ("analytics.md", "suppliers.md", "compatibility.md", "operations.md", "data-model.md")


def words(text):
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().casefold()
    return set(re.findall(r"[a-z0-9]{3,}", normalized))


def search_documentation(query):
    terms = words(query)
    candidates = []
    for name in APPROVED:
        path = DOC_ROOT / name
        if not path.is_file() or path.is_symlink() or path.stat().st_size > 512_000:
            continue
        contents = path.read_text(encoding="utf-8")
        for offset in range(0, len(contents), 1000):
            chunk = contents[offset:offset + 1400]
            score = len(terms & words(chunk))
            if score:
                candidates.append((score, name, offset, chunk))
    candidates.sort(key=lambda item: (-item[0], item[1], item[2]))
    return {"items": [{"source": f"docs/{name}", "offset": offset, "text": chunk}
                      for _, name, offset, chunk in candidates[:5]],
            "searchType": "approved_local_excerpts", "complete": False}
