# C:\BIB\app\utils.py

import hashlib
import re
from pathlib import Path
from typing import Dict, Any, Optional
import logging
import unicodedata # NOWY IMPORT: dla normalizacji znaków

# Importujemy konfigurację z naszego pliku config.py
from app import config

logger = logging.getLogger(__name__)

# ----------------------------------------------------------
# Funkcja pomocnicza do usuwania znaków diakrytycznych
# ----------------------------------------------------------
def remove_diacritics(text: str) -> str:
    """
    Usuwa znaki diakrytyczne (np. polskie ogonki, kreski) z tekstu.
    Przykład: "żółć" -> "zolc"
    """
    if not isinstance(text, str): # Upewnij się, że to string
        return str(text)
    
    # Składa znaki Unicode w formę NFD (Normalization Form D)
    # Oddziela znaki podstawowe od diakrytyków
    normalized_text = unicodedata.normalize('NFD', text)
    # Usuwa wszystkie znaki, które są klasyfikowane jako "Mark" (diakrytyki)
    # i koduje/dekoduje do ASCII, ignorując błędy (usuwając nie-ASCII znaki)
    return ''.join(c for c in normalized_text if not unicodedata.combining(c)).encode('ascii', 'ignore').decode('utf-8')


# ----------------------------------------------------------
# Generowanie hasha książki (Hashomat)
# ----------------------------------------------------------
def generate_book_hash(meta: Dict[str, Any]) -> str:
    """
    Generuje unikalny hash SHA-256 (skrócony) na podstawie kluczowych metadanych książki.
    Używa pól: title, authors, year, pub_place.
    Hash jest zawsze taki sam dla identycznych metadanych.
    """
    
    def safe_get_and_normalize(key: str) -> str:
        value = str(meta.get(key, "")).strip() # Nie konwertujemy na lower() tutaj
        if config.NORMALIZE_HASH:
            value = remove_diacritics(value) # Usuwamy diakrytyki, jeśli flaga ustawiona
        return value.lower() # Konwersja na małe litery odbywa się na końcu

    base_string = "|".join([
        safe_get_and_normalize("title"),
        safe_get_and_normalize("authors"),
        safe_get_and_normalize("year"),
        safe_get_and_normalize("pub_place")
    ])

    hash_obj = hashlib.sha256(base_string.encode("utf-8"))
    return hash_obj.hexdigest()[:config.BOOK_HASH_LENGTH]

# ----------------------------------------------------------
# Parsowanie nazwy pliku skanu
# ----------------------------------------------------------
def parse_scanned_page_filename(fname: str) -> Optional[Dict[str, Any]]:
    """
    Parsuje nazwę pliku skanu strony w formacie:
    `{alias}_{typ_strony}{numer}.ext`
    Przykłady: `MojaKsiazka_w0001.jpg`, `MojaKsiazka_s0001.jpg`
    Wykorzystuje regex z config.py.
    """
    
    match = re.match(config.SCAN_FILENAME_REGEX, fname, re.IGNORECASE)
    
    if not match:
        logger.warning(f"Nieprawidłowa nazwa pliku skanu: {fname}")
        return None
    
    groups = match.groupdict()
    
    page_type_full = config.PAGE_TYPE_MAPPING.get(groups["page_type"].lower(), "Nieznany")

    formatted_page_num_str = groups["page_type"].lower() + groups["page_num"].zfill(config.PAGE_NUMBER_PADDING)

    # Opcjonalna konwersja na rzymskie dla wstępu (prosta mapa – rozszerz jeśli potrzeba)
    roman_num = ""
    if groups["page_type"].lower() == "w":
        roman_map = {1: 'i', 2: 'ii', 3: 'iii', 4: 'iv', 5: 'v', 6: 'vi', 7: 'vii', 8: 'viii', 9: 'ix', 10: 'x'}
        roman_num = roman_map.get(int(groups["page_num"]), "") # Zwracaj pusty string, jeśli nie ma w mapie

    return {
        "alias": groups["alias"],
        "page_raw_number_str": formatted_page_num_str,
        "page_type_short": groups["page_type"].lower(),
        "page_type_full": page_type_full,
        "page_number_numeric": int(groups["page_num"]),
        "roman_number": roman_num,
        "original_extension": "." + groups["ext"].lower() # Dodaj kropkę, groups["ext"] zawsze istnieje (named group)
    }

# `overwrite_scan` (funkcja do nadpisywania skanów) będzie zaimplementowana w `scanner.py`
# lub `db_manager.py`, bo wymaga logiki OCR i bazy danych.


# ----------------------------------------------------------
# Funkcje testowe (ten blok uruchamia się tylko po bezpośrednim wywołaniu pliku)
# ----------------------------------------------------------
if __name__ == "__main__":
    import sys # Import sys dla StreamHandler
    # Lokalna konfiguracja logowania dla testów w utils.py
    # UWAGA: To jest tylko do celów testowych, główna konfiguracja logowania będzie w main.py
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)-15s | %(message)s",
        handlers=[
            logging.FileHandler(config.LOGS_DIR / "utils_test.log", encoding="utf-8"),
            logging.StreamHandler(sys.stdout)
        ]
    )
    # Ponowne pobranie loggera dla tego modułu, aby zastosować nową konfigurację
    logger = logging.getLogger(__name__) 
    logger.info("System logowania dla utils_test.py skonfigurowany lokalnie.")


    logger.info(f"Testowanie modułu utils.py (ścieżka bazowa: {config.BASE_DIR})")

    # Testowanie generate_book_hash
    logger.info("\n--- Testowanie generowania hasha książki ---")
    book_meta1 = {
        "title": "Historia Starozytna",
        "authors": "Jan Kowalski",
        "year": "2020",
        "pub_place": "Warszawa"
    }
    book_meta2 = {
        "title": "Historia Starozytna",
        "authors": "Jan Kowalski",
        "year": "2020",
        "pub_place": "Warszawa"
    }
    book_meta3 = {
        "title": "Historia Wspólczesna",
        "authors": "Jan Kowalski",
        "year": "2020",
        "pub_place": "Warszawa"
    }
    book_meta_missing_data = {
        "title": "Książka bez roku",
        "authors": "Autor Anonimowy"
    }

    hash1 = generate_book_hash(book_meta1)
    hash2 = generate_book_hash(book_meta2)
    hash3 = generate_book_hash(book_meta3)
    hash_missing = generate_book_hash(book_meta_missing_data)

    logger.info(f"Hash 1: {hash1}")
    logger.info(f"Hash 2: {hash2} (powinien być taki sam jak Hash 1: {hash1 == hash2})")
    logger.info(f"Hash 3: {hash3} (powinien być inny niż Hash 1: {hash1 != hash3})")
    logger.info(f"Hash z brakującymi danymi: {hash_missing}")

    # Testowanie parse_scanned_page_filename
    logger.info("\n--- Testowanie parsowania nazw plików skanów ---")
    
    test_filenames = [
        "MojaKsiazka_s0001.jpg",
        "MojaKsiazka_w0010.png",
        "Album_i0005.tiff", # Ilustracja
        "Mapa_s0001.jpeg",
        "Ksiazka-Madrosci_s1234.tif",
        "Błąd_w_nazwie.jpg", # Ten powinien teraz logować ostrzeżenie o nieprawidłowej nazwie
        "Okładka_c0001.jpg"
    ]

    for fname in test_filenames:
        parsed_info = parse_scanned_page_filename(fname)
        if parsed_info:
            logger.info(f"\nPlik: {fname}")
            for key, value in parsed_info.items():
                logger.info(f"  {key}: {value}")
        else:
            logger.warning(f"\nPlik: {fname} -> NIEPRAWIDŁOWA NAZWA (zwrócono None)")