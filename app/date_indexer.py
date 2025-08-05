#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
date_indexer.py  –  Agreguje wszystkie daty z metadata.json w data/processed
                  i tworzy jeden zbiorczy indeks (oś czasu).
"""

import json
from pathlib import Path
from datetime import datetime

# Ścieżki
PROCESSED_DIR  = Path("data/processed")
OUTPUTS_DIR    = Path("outputs")
DATE_INDEX     = OUTPUTS_DIR / "date_index.json"

def build_date_index() -> list[dict]:
    """
    Przechodzi przez każdy katalog książki w data/processed/,
    zbiera wszystkie sparsowane daty i zwraca posortowaną listę wpisów.
    """
    index = []

    if not PROCESSED_DIR.exists():
        print(f"❌ Brak folderu: {PROCESSED_DIR}")
        return index

    # Iteruj po wszystkich hash-katalogach (książkach)
    for book_folder in PROCESSED_DIR.iterdir():
        if not book_folder.is_dir():
            continue

        meta_file = book_folder / "metadata.json"
        if not meta_file.exists():
            print(f"⚠ Brak metadata.json w {book_folder.name}, pomijam")
            continue

        # Wczytaj metadane książki
        try:
            data = json.loads(meta_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print(f"⚠ Uszkodzony JSON: {meta_file}, pomijam")
            continue

        # Dane książki
        book_hash   = book_folder.name
        book_title  = data.get("tytul", "")
        book_author = data.get("autor", "")

        # Zbierz daty z każdego skanu
        for scan in data.get("scans", []):
            for dt in scan.get("extracted_dates", []):
                parsed = dt.get("parsed")
                if not parsed:
                    continue
                entry = {
                    "date_parsed": parsed,           # ISO string
                    "date_text": dt.get("text", ""), # surowy zapis
                    "book_hash": book_hash,
                    "book_title": book_title,
                    "book_author": book_author,
                    "scan_path": scan.get("path", ""),
                    "ocr_snippet": scan.get("ocr", "")[:80] + "..."
                }
                index.append(entry)

    # Sortuj indeks po dacie
    index.sort(key=lambda e: e["date_parsed"])
    return index

def save_date_index(index: list[dict]):
    """Zapisuje posortowany indeks do outputs/date_index.json."""
    OUTPUTS_DIR.mkdir(exist_ok=True)
    with open(DATE_INDEX, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)
    print(f"✅ Zapisano date_index.json ({len(index)} wpisów)")

def main():
    print("▶ Buduję zbiorczy indeks dat (date_index.json)...")
    idx = build_date_index()
    if not idx:
        print(ℹ️  Brak danych do indeksowania.")
    else:
        save_date_index(idx)
    print("✔ Gotowe.")

if __name__ == "__main__":
    main()