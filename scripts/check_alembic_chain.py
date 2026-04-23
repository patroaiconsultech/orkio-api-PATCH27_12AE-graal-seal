from __future__ import annotations

import re
import sys
from pathlib import Path

VERSIONS_DIR = Path("alembic/versions")

REV_RE = re.compile(r'^\s*revision\s*=\s*["\']([^"\']+)["\']', re.MULTILINE)
DOWN_RE = re.compile(r'^\s*down_revision\s*=\s*(.+)$', re.MULTILINE)

def parse_revision(text: str) -> str | None:
    m = REV_RE.search(text)
    return m.group(1).strip() if m else None

def parse_down_revision(text: str):
    m = DOWN_RE.search(text)
    if not m:
        return None
    raw = m.group(1).strip()
    if raw == "None":
        return None
    if raw.startswith(("'", '"')):
        return raw.strip("\"'")
    if raw.startswith("("):
        return tuple(re.findall(r'["\']([^"\']+)["\']', raw))
    return raw

def main() -> int:
    if not VERSIONS_DIR.exists():
        print("ERRO: diretório alembic/versions não encontrado.")
        return 2

    revisions: dict[str, str] = {}
    down_refs: list[tuple[str, str]] = []

    for file in sorted(VERSIONS_DIR.glob("*.py")):
        text = file.read_text(encoding="utf-8")
        rev = parse_revision(text)
        down = parse_down_revision(text)

        if not rev:
            print(f"ERRO: revision ausente em {file}")
            return 1

        if rev in revisions:
            print(f"ERRO: revision duplicado '{rev}' em {revisions[rev]} e {file}")
            return 1

        revisions[rev] = str(file)

        if isinstance(down, tuple):
            for item in down:
                down_refs.append((str(file), item))
        elif isinstance(down, str):
            down_refs.append((str(file), down))

    errors = 0
    for file, down in down_refs:
        if down not in revisions:
            print(f"ERRO: down_revision inexistente '{down}' referenciado em {file}")
            errors += 1

    heads = sorted(set(revisions) - {ref for _, ref in down_refs if ref in revisions})

    if errors:
        print(f"Falhas encontradas: {errors}")
        return 1

    print("OK: cadeia Alembic válida.")
    print(f"Total migrations: {len(revisions)}")
    print(f"Heads inferidos: {len(heads)} -> {', '.join(heads)}")
    if len(heads) != 1:
        print("ALERTA: múltiplos heads detectados.")
        return 1

    return 0

if __name__ == "__main__":
    sys.exit(main())
