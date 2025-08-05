# C:\BIB\app\scanner.py

import logging
import shutil
import time
from pathlib import Path
from typing import Dict, Any, Optional, List # Pamiętaj o imporcie List!

from app import config
from app import utils
from app.db_manager import DBManager # Importujemy klasę DBManager (Singleton)
from app.ocr_engine import OCREngine # Importujemy klasę OCREngine (Singleton)

# Logger dla tego modułu
logger = logging.getLogger(__name__)
change_logger = logging.getLogger("changes")

class Scanner:
    """
    Klasa odpowiedzialna za skanowanie folderu wejściowego (scans/),
    przetwarzanie plików skanów i zarządzanie ich metadanymi.
    Orkiestruje wykorzystanie innych modułów (utils, db_manager, ocr_engine).
    """
    _instance = None # Wzorzec Singleton, aby mieć tylko jedną instancję Skanera

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Scanner, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self.db_manager = DBManager() # Inicjalizacja Singletonu DBManager
        self.ocr_engine = OCREngine() # Inicjalizacja Singletonu OCREngine
        self._initialized = True
        logger.info("Scanner: Zainicjalizowany.")

    def _get_files_to_process(self) -> List[Path]:
        """Pobiera listę plików graficznych z folderu skanów (config.SCAN_DIR)."""
        files = [
            p for p in config.SCAN_DIR.iterdir() 
            if p.is_file() and p.suffix.lower() in config.PAGE_TYPE_MAPPING.values() # Sprawdź tylko wspierane rozszerzenia
            # Lepsze sprawdzenie rozszerzeń: p.suffix.lower() in [".jpg", ".jpeg", ".png", ".tiff", ".tif"]
        ]
        # Sortujemy, aby zachować kolejność (np. numery stron w ramach aliasu)
        return sorted(files) 

    def _handle_book_metadata_input(self, alias: str) -> Optional[Dict[str, Any]]:
        """
        Symulacja interakcji z GUI do pobierania metadanych nowej książki od użytkownika.
        W przyszłości będzie to wywołanie modułu GUI (app/gui/book_form.py).
        """
        logger.info(f"Scanner: Wykryto nowy alias książki '{alias}'. Wymagane metadane.")
        
        # --- Symulacja GUI (konsolowa interakcja) ---
        print("\n" + "="*60)
        print(f"| NOWA KSIĄŻKA WYKRYTA: '{alias}'")
        print("| PROSZĘ WPROWADZIĆ DANE BIBLIOGRAFICZNE")
        print("="*60)
        
        title = input("Tytuł: ").strip()
        authors = input("Autorzy: ").strip()
        year = input("Rok wydania: ").strip()
        pub_place = input("Miejsce wydania: ").strip()
        publisher = input("Wydawca (opcjonalnie): ").strip()
        num_pages_str = input("Liczba stron całkowita (np. 300, opcjonalnie): ").strip()
        notes = input("Dodatkowe notatki (opcjonalnie): ").strip()
        keywords_str = input("Słowa kluczowe (rozdzielone przecinkami, opcjonalnie): ").strip()
        
        # Pola dla ikonografii (checkboxy w GUI)
        maps_present = input("Czy książka zawiera mapy? (t/n, domyślnie 'n'): ").strip().lower() == 't'
        illustrations_present = input("Czy książka zawiera ilustracje? (t/n, domyślnie 'n'): ").strip().lower() == 't'
        tables_present = input("Czy książka zawiera tabele? (t/n, domyślnie 'n'): ").strip().lower() == 't'
        
        print("="*60 + "\n")

        if not title or not authors:
            logger.error("Scanner: Tytuł i autorzy są polami wymaganymi. Anuluję przetwarzanie tej książki.")
            return None

        num_pages = int(num_pages_str) if num_pages_str.isdigit() else None
        keywords = [kw.strip() for kw in keywords_str.split(',') if kw.strip()]

        book_meta = {
            "title": title,
            "authors": authors,
            "year": year,
            "pub_place": pub_place,
            "publisher": publisher,
            "num_pages": num_pages,
            "language": config.DEFAULT_OCR_LANG, # Język domyślny z config, w przyszłości może być w GUI
            "notes": notes,
            "keywords": keywords,
            "maps_present": maps_present,
            "illustrations_present": illustrations_present,
            "tables_present": tables_present,
        }
        
        return book_meta

    def process_scans_batch(self):
        """
        Główna funkcja przetwarzająca pliki w folderze scans/.
        Obsługuje pakiety skanów należących do tej samej książki.
        """
        logger.info("Scanner: Rozpoczynam przetwarzanie folderu skanów.")

        files_to_process = self._get_files_to_process()
        if not files_to_process:
            logger.info("Scanner: Brak nowych plików do przetworzenia w folderze scans/.")
            return

        # Słownik do śledzenia już przetworzonych aliasów w tej sesji
        # klucz: alias, wartość: book_hash (lub None jeśli anulowano)
        session_processed_aliases: Dict[str, Optional[str]] = {} 

        for scan_path in files_to_process:
            logger.info(f"Scanner: Przetwarzam plik: {scan_path.name}")
            parsed_scan_info = utils.parse_scanned_page_filename(scan_path.name)

            if not parsed_scan_info:
                logger.warning(f"Scanner: Plik '{scan_path.name}' ma nieprawidłową nazwę. Pomijam i usuwam.")
                try:
                    scan_path.unlink() # Usuń plik, który nie pasuje do wzorca
                    change_logger.info(f"Scanner: Usunięto nieprawidłowy plik: {scan_path.name}")
                except Exception as e:
                    logger.error(f"Scanner: Błąd podczas usuwania nieprawidłowego pliku '{scan_path.name}': {e}")
                continue

            alias = parsed_scan_info["alias"]
            current_book_hash: Optional[str] = None
            current_book_meta: Optional[Dict[str, Any]] = None

            # Krok 1: Identyfikacja książki i pobranie/uzyskanie metadanych
            if alias in session_processed_aliases:
                # Alias już przetworzony w tej sesji batcha (albo dodany, albo anulowany)
                current_book_hash = session_processed_aliases[alias]
                if current_book_hash is None: # Anulowano dla tego aliasu wcześniej
                    logger.info(f"Scanner: Przetwarzanie dla aliasu '{alias}' zostało wcześniej anulowane. Pomijam plik '{scan_path.name}'.")
                    continue
                # Jeśli book_hash jest znany, pobierz aktualne meta z DB
                current_book_meta = self.db_manager.get_book_by_hash(current_book_hash)
                if not current_book_meta:
                    logger.error(f"Scanner: Książka o hash '{current_book_hash}' nie znaleziona w DB mimo, że była w pamięci sesji. Błąd stanu. Pomijam plik '{scan_path.name}'.")
                    continue
            else: # Alias nieznany w bieżącej sesji, sprawdzamy DB lub prosimy o metadane
                if not self.db_manager.is_connected():
                    logger.warning("Scanner: Brak połączenia z bazą danych. Nie można sprawdzić, czy książka dla aliasu '{alias}' już istnieje. Będę pytał o metadane.")
                    # Jeśli nie ma połączenia, każdy nowy alias to prośba o metadane
                    book_meta_from_input = self._handle_book_metadata_input(alias)
                    if not book_meta_from_input:
                        logger.warning(f"Scanner: Metadane dla aliasu '{alias}' nie zostały wprowadzone. Anuluję przetwarzanie dla tego aliasu.")
                        session_processed_aliases[alias] = None # Zapisz jako anulowany
                        continue
                    current_book_meta = book_meta_from_input
                    current_book_hash = utils.generate_book_hash(book_meta_from_input)
                    current_book_meta["book_hash"] = current_book_hash # Dodaj hash do meta
                    session_processed_aliases[alias] = current_book_hash
                    logger.info(f"Scanner: Generuję nowy hash dla aliasu '{alias}': {current_book_hash} (brak DB).")
                else:
                    # Połączono z DB, więc spróbuj znaleźć książkę po metadanych (po GUI)
                    book_meta_from_input = self._handle_book_metadata_input(alias) # Użytkownik musi zawsze podać metadane
                    if not book_meta_from_input:
                        logger.warning(f"Scanner: Metadane dla aliasu '{alias}' nie zostały wprowadzone. Anuluję przetwarzanie dla tego aliasu.")
                        session_processed_aliases[alias] = None
                        continue
                    
                    existing_book_by_meta = self.db_manager.get_book_by_meta(book_meta_from_input)
                    if existing_book_by_meta:
                        current_book_hash = existing_book_by_meta["book_hash"]
                        current_book_meta = existing_book_by_meta # Pobierz pełne meta z DB
                        logger.info(f"Scanner: Książka o metadanych dla aliasu '{alias}' już istnieje w bazie (hash: {current_book_hash}).")
                    else:
                        current_book_hash = utils.generate_book_hash(book_meta_from_input)
                        current_book_meta = book_meta_from_input
                        current_book_meta["book_hash"] = current_book_hash # Dodaj hash do meta
                        logger.info(f"Scanner: Tworzę nową książkę w DB dla aliasu '{alias}': {current_book_hash}.")
                    
                    session_processed_aliases[alias] = current_book_hash


            # Jeśli current_book_hash jest None, to oznacza, że coś poszło nie tak
            # (np. brak połączenia z DB i użytkownik nie podał danych, lub błąd w logice)
            if not current_book_hash:
                logger.error(f"Scanner: Nie można ustalić book_hash dla pliku '{scan_path.name}'. Pomijam.")
                continue

            # Krok 2: Kopiowanie pliku do processed/
            book_folder = config.PROCESSED_DIR / current_book_hash
            book_folder.mkdir(exist_ok=True, parents=True)

            # Ustandaryzowana nazwa pliku w processed/
            standardized_filename = f"{current_book_hash}_{parsed_scan_info['page_raw_number_str']}{parsed_scan_info['original_extension']}"
            destination_path = book_folder / standardized_filename

            # Kopiowanie pliku (shutil.copy2 nadpisuje, jeśli istnieje - obsługa ponownego skanowania)
            try:
                shutil.copy2(scan_path, destination_path)
                change_logger.info(f"Scanner: Skan skopiowany: {scan_path.name} -> {destination_path.relative_to(config.BASE_DIR)}")
            except Exception as e:
                logger.error(f"Scanner: Błąd kopiowania pliku '{scan_path.name}' do '{destination_path}': {e}. Pomijam OCR i zapis DB.")
                continue # Przejdź do następnego pliku

            # Krok 3: Wykonanie OCR i zapis tekstu do pliku .txt
            ocr_text = ""
            # Wykonujemy OCR tylko dla typów stron, które mają tekst
            if parsed_scan_info["page_type_full"] in ["Wstęp", "Strona Główna"]: 
                if self.ocr_engine.is_available():
                    ocr_text = self.ocr_engine.perform_ocr(destination_path, lang=config.DEFAULT_OCR_LANG)
                    ocr_txt_path = destination_path.with_suffix(".txt")
                    try:
                        with open(ocr_txt_path, "w", encoding="utf-8") as f:
                            f.write(ocr_text)
                        logger.info(f"Scanner: Zapisano tekst OCR do: {ocr_txt_path.relative_to(config.BASE_DIR)}")
                    except Exception as e:
                        logger.error(f"Scanner: Błąd zapisu pliku OCR dla {destination_path.name}: {e}")
                else:
                    logger.warning("Scanner: Silnik OCR niedostępny. Pomijam OCR dla pliku '{scan_path.name}'.")
            else:
                logger.info(f"Scanner: Typ strony '{parsed_scan_info['page_type_full']}' ({scan_path.name}) - pomijam OCR.")

            # Krok 4: Przygotowanie danych skanu i zapis do DB/JSON
            scan_data_for_db = {
                **parsed_scan_info, # Rozpakuj sparsowane info z utils (alias, page_raw_number_str, etc.)
                "ocr_text": ocr_text,
                "page_full_path": destination_path, # Ścieżka do przetworzonego pliku
                # Data processed_at zostanie dodana w db_manager.upsert_book_and_scan
                # created_at (pierwsze dodanie skanu) zostanie dodane w db_manager
            }

            # Zapis do MongoDB i lokalnego JSON (DBManager to wszystko obsłuży)
            if not self.db_manager.upsert_book_and_scan(current_book_meta, scan_data_for_db):
                logger.error(f"Scanner: Błąd zapisu danych do bazy/JSON dla {scan_path.name}. Kontynuuję, ale dane mogą być niespójne.")
            else:
                # Po udanym zapisie do Mongo, pobierz aktualny stan książki z bazy, aby zapisać go lokalnie
                # Jest to ważne, bo MongoDB mogło dodać/zaktualizować pola (np. _id, created_at, scans array)
                current_book_data_from_db = self.db_manager.get_book_by_hash(current_book_hash)
                if current_book_data_from_db:
                    self.db_manager.save_local_metadata_json(
                        current_book_hash, 
                        current_book_data_from_db, 
                        scan_data_for_db # Tutaj scan_data_for_db jest już poprawnie przygotowany
                    )
                else:
                    logger.error(f"Scanner: Nie można pobrać danych książki '{current_book_hash}' z bazy po upsert, aby zapisać lokalny JSON.")

            # Krok 5: Usunięcie oryginalnego pliku z folderu scans/
            try:
                scan_path.unlink()
                change_logger.info(f"Scanner: Oryginał usunięty z scans/: {scan_path.name}")
            except Exception as e:
                logger.error(f"Scanner: Nie można usunąć oryginalnego pliku '{scan_path.name}' ze scans/: {e}")
        
        logger.info("Scanner: Przetwarzanie folderu skanów zakończone.")


# ----------------------------------------------------------
# Funkcje testowe dla Scanner (do usunięcia w finalnej wersji lub przeniesienia do dedykowanych testów)
# ----------------------------------------------------------
if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)-15s | %(message)s",
        handlers=[
            logging.FileHandler(config.LOGS_DIR / "scanner.log", encoding="utf-8"),
            logging.StreamHandler(sys.stdout)
        ]
    )
    logger = logging.getLogger(__name__)
    change_logger = logging.getLogger("changes")
    logger.info("System logowania dla scanner.py skonfigurowany lokalnie.")

    logger.info("\n--- Analiza folderu scans/ ---")

    db_manager = DBManager()
    ocr_engine = OCREngine()

    if not db_manager.is_connected():
        logger.error("Brak połączenia z MongoDB. Upewnij się, że serwer jest uruchomiony. Nie można przeprowadzić testów Scanner.")
        sys.exit(1)

    if not ocr_engine.is_available():
        logger.warning("Tesseract jest niedostępny, OCR w testach Scanner zostanie pominięty.")

    scanner = Scanner()

    scan_dir = config.SCAN_DIR
    scan_dir.mkdir(exist_ok=True)

    try:
        files = [f for f in scan_dir.iterdir() if f.is_file()]
        if files:
            logger.info("Znalezione pliki w folderze scans/:")
            for f in files:
                logger.info(f"  - {f.name}")
        else:
            logger.info("Brak plików w folderze scans/ do analizy.")
    except Exception as e:
        logger.error(f"Błąd podczas analizy plików w scans/: {e}")

    logger.info("\n--- Rozpoczynam przetwarzanie skanów przez Scanner ---")
    scanner.process_scans_batch()
    logger.info("\n--- Przetwarzanie skanów przez Scanner zakończone ---")

    db_manager.close()
    logger.info("\n--- Testowanie Modułu Scanner zakończone ---")