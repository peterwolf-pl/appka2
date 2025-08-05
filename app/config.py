# C:\BIB\app\config.py

import os
from pathlib import Path

# ----------------------------------------------------------
# Podstawowa konfiguracja ścieżek
# ----------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parents[1]

SCAN_DIR = BASE_DIR / "scans"
PROCESSED_DIR = BASE_DIR / "processed"
OUTPUTS_DIR = BASE_DIR / "outputs"
LOGS_DIR = BASE_DIR / "logs"

# ----------------------------------------------------------
# Konfiguracja Tesseract OCR
# ----------------------------------------------------------
TESS_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
DEFAULT_OCR_LANG = "pol"
SUPPORTED_OCR_LANGS = ["pol", "eng"]
OCR_CONVERT_TO_BW = True

# ----------------------------------------------------------
# Konfiguracja MongoDB
# ----------------------------------------------------------
MONGO_URI = "mongodb://localhost:27017/"
MONGO_DB_NAME = "moja_biblioteka_db"
MONGO_COL_BOOKS = "books"
MONGO_COL_SCANS = "scans"

# ----------------------------------------------------------
# Inne ustawienia
# ----------------------------------------------------------
BOOK_HASH_LENGTH = 12

# Poprawiony regex z named groups, obsługą unicode w alias i wszystkimi typami stron
SCAN_FILENAME_REGEX = r'^(?P<alias>.+?)_(?P<page_type>[wsimtcgoeb])(?P<page_num>\d+)\.(?P<ext>jpg|jpeg|png|tiff?)$'  # .+? dla unicode, [wsimtcgoeb] dla typów, named ext

PAGE_NUMBER_PADDING = 4

PAGE_TYPE_MAPPING = {
    "w": "Wstęp",
    "s": "Strona Główna",
    "m": "Mapa",
    "i": "Ilustracja",
    "t": "Tabela",
    "c": "Okładka",
    "g": "Grzbiet",
    "o": "Obwoluta",
    "e": "Wyklejka",
    "b": "Pusta Strona",
}

# Flaga dla normalize w hash (dla wielojęzyczności – dyskutujmy)
NORMALIZE_HASH = True  # True: Usuwa diakrytyki w hash ( "żółty" -> "zolty")

# Utwórz foldery
for directory in [SCAN_DIR, PROCESSED_DIR, OUTPUTS_DIR, LOGS_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

print("Config załadowany – root:", BASE_DIR)  # Test