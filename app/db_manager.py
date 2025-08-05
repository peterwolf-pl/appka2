# C:\BIB\app\db_manager.py - PEŁNA I OSTATECZNA WERSJA KODU Z NAPRAWIONĄ SERIALIZACJĄ DATETIME I OBJECTID

import logging
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, PyMongoError
from typing import Dict, Any, Optional, List
from datetime import datetime
import json # Do zapisu/odczytu lokalnych metadata.json
from pathlib import Path
from bson import ObjectId # Do obsługi identyfikatorów MongoDB

from app import config
from app import utils # Będziemy używać generate_book_hash z utils

# Logger dla tego modułu
logger = logging.getLogger(__name__)
change_logger = logging.getLogger("changes") # Logger do logowania zmian w bazie

# ----------------------------------------------------------
# Funkcja pomocnicza do rekurencyjnej konwersji dla JSON
# ----------------------------------------------------------
def _json_serializable(obj: Any) -> Any:
    """
    Rekurencyjnie konwertuje obiekty datetime i ObjectId na stringi
    oraz obiekty Path na stringi, aby były serializowalne do JSON.
    """
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, ObjectId):
        return str(obj)
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, dict):
        return {k: _json_serializable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_serializable(elem) for elem in obj]
    return obj

class DBManager:
    """
    Klasa do zarządzania połączeniem i operacjami na bazie danych MongoDB.
    Implementuje wzorzec Singleton, aby zapewnić tylko jedną instancję.
    """
    _instance = None # Prywatna zmienna do przechowywania instancji Singletona

    def __new__(cls):
        """Implementuje wzorzec Singleton."""
        if cls._instance is None:
            cls._instance = super(DBManager, cls).__new__(cls)
            cls._instance._initialized = False # Flaga do jednokrotnej inicjalizacji
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self.client: Optional[MongoClient] = None
        self.db = None
        self.books_collection = None
        self._initialized = True
        self.connect()

    def connect(self):
        """Nawiązuje połączenie z bazą danych MongoDB."""
        if self.client:
            try:
                self.client.admin.command('ping') # Sprawdź, czy istniejące połączenie jest aktywne
                logger.info("MongoDB: Już połączono z bazą.")
                return True
            except (ConnectionFailure, PyMongoError):
                logger.warning("MongoDB: Istniejące połączenie nieaktywne, próbuję ponownie.")
                self.client = None # Resetuj klienta
        
        try:
            self.client = MongoClient(config.MONGO_URI, serverSelectionTimeoutMS=5000)
            self.client.admin.command('ping')  # Test połączenia
            self.db = self.client[config.MONGO_DB_NAME]
            self.books_collection = self.db[config.MONGO_COL_BOOKS]
            logger.info(f"MongoDB: Połączono z bazą '{config.MONGO_DB_NAME}'.")
            return True
        except ConnectionFailure as e:
            logger.error(f"MongoDB: Nie można połączyć z bazą danych. Upewnij się, że serwer MongoDB jest uruchomiony. Błąd: {e}")
            self.client = None
            return False
        except PyMongoError as e:
            logger.error(f"MongoDB: Błąd PyMongo podczas łączenia: {e}")
            self.client = None
            return False
        except Exception as e:
            logger.error(f"MongoDB: Nieoczekiwany błąd podczas łączenia: {e}")
            self.client = None
            return False

    def is_connected(self) -> bool:
        """Sprawdza, czy istnieje aktywne połączenie z MongoDB."""
        try:
            if self.client:
                self.client.admin.command('ping')
                return True
        except (ConnectionFailure, PyMongoError):
            pass # Połączenie nieaktywne lub błąd
        return False

    def close(self):
        """Zamyka połączenie z bazą danych MongoDB."""
        if self.client:
            self.client.close()
            self.client = None
            logger.info("MongoDB: Połączenie zamknięte.")

    # ----------------------------------------------------------
    # Operacje na Metadanych Książki
    # ----------------------------------------------------------

    def get_book_by_hash(self, book_hash: str) -> Optional[Dict[str, Any]]:
        """Pobiera metadane książki z MongoDB po hash'u."""
        if not self.is_connected():
            logger.warning("MongoDB: Brak połączenia, nie można pobrać książki.")
            return None
        try:
            book_data = self.books_collection.find_one({"book_hash": book_hash})
            if book_data:
                logger.debug(f"Pobrano książkę o hash: {book_hash}")
            return book_data
        except PyMongoError as e:
            logger.error(f"MongoDB: Błąd podczas pobierania książki po hash'u '{book_hash}': {e}")
            return None

    def get_book_by_meta(self, meta_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Pobiera metadane książki z MongoDB na podstawie danych bibliograficznych.
        Generuje hash z podanych meta_data i wyszukuje po nim.
        """
        if not self.is_connected():
            logger.warning("MongoDB: Brak połączenia, nie można pobrać książki po metadanych.")
            return None
        book_hash = utils.generate_book_hash(meta_data)
        return self.get_book_by_hash(book_hash)
    
    def book_exists_by_hash(self, book_hash: str) -> bool:
        """Sprawdza, czy książka o danym hash'u istnieje w bazie."""
        if not self.is_connected():
            return False
        try:
            return self.books_collection.count_documents({"book_hash": book_hash}) > 0
        except PyMongoError as e:
            logger.error(f"MongoDB: Błąd podczas sprawdzania istnienia książki po hash'u '{book_hash}': {e}")
            return False

    def upsert_book_and_scan(self, book_meta: Dict[str, Any], scan_info: Dict[str, Any]) -> bool:
        """
        Dodaje lub aktualizuje metadane książki w MongoDB i jej skanów.
        Jeśli książka istnieje (po book_hash), dodaje/aktualizuje tylko skan.
        Jeśli skan już istnieje w liście skanów, aktualizuje go.
        """
        if not self.is_connected():
            logger.warning("MongoDB: Brak połączenia, nie można zapisać danych.")
            return False

        # --- Twoja poprawka: Usunięcie pola 'language' przed wysłaniem do Mongo ---
        # Pracujemy na kopii book_meta, żeby nie modyfikować oryginalnego słownika
        book_meta_copy = book_meta.copy() 
        book_meta_copy.pop("language", None) # Usuń 'language' jeśli istnieje
        # -------------------------------------------------------------------------

        book_hash = utils.generate_book_hash(book_meta) # Hash generujemy z oryginalnych meta, żeby był spójny

        # Przygotowanie danych książki do wstawienia/aktualizacji
        book_data_to_upsert = {
            "book_hash": book_hash,
            "title": book_meta_copy.get("title", ""), # Używamy book_meta_copy
            "authors": book_meta_copy.get("authors", ""),
            "year": book_meta_copy.get("year", ""),
            "pub_place": book_meta_copy.get("pub_place", ""),
            "publisher": book_meta_copy.get("publisher", ""),
            "num_pages": book_meta_copy.get("num_pages", None),
            # "language" usunięte z book_data_to_upsert celowo
            "notes": book_meta_copy.get("notes", ""),
            "keywords": book_meta_copy.get("keywords", []),
            "maps_present": book_meta_copy.get("maps_present", False),
            "illustrations_present": book_meta_copy.get("illustrations_present", False),
            "tables_present": book_meta_copy.get("tables_present", False),
            "last_updated_book_at": datetime.now(),
        }
        
        # Atomowa operacja upsert dla głównego rekordu książki
        # $setOnInsert gwarantuje, że 'created_at' jest ustawiane tylko raz przy pierwszym wstawieniu
        result = self.books_collection.update_one(
            {"book_hash": book_hash},
            {"$set": book_data_to_upsert, "$setOnInsert": {"created_at": datetime.now()}},
            upsert=True # Jeśli nie istnieje, utwórz nowy dokument
        )

        if result.upserted_id:
            change_logger.info(f"MongoDB: Dodano nową książkę (hash: {book_hash}). ID: {result.upserted_id}")
        elif result.modified_count > 0:
            change_logger.info(f"MongoDB: Zaktualizowano metadane książki (hash: {book_hash}).")
        else:
            logger.debug(f"MongoDB: Książka (hash: {book_hash}) istnieje i nie wymaga aktualizacji metadanych.")


        # Aktualizacja/dodanie skanu do listy skanów w książce
        scan_info_to_save = scan_info.copy()
        # Usuwamy 'language' ze scan_info, jeśli tam było, aby uniknąć problemów
        scan_info_to_save.pop("language", None) 
        scan_info_to_save["processed_at"] = datetime.now() # Kiedy ostatnio przetworzono ten skan
        scan_info_to_save["page_full_path"] = str(scan_info_to_save["page_full_path"]) # Path -> string dla Mongo

        # Sprawdź, czy skan o tym page_raw_number_str już istnieje w tablicy 'scans'
        update_scan_result = self.books_collection.update_one(
            {"book_hash": book_hash, "scans.page_raw_number_str": scan_info_to_save["page_raw_number_str"]},
            {"$set": {"scans.$": scan_info_to_save}} # $ operator aktualizuje pierwszy pasujący element
        )

        if update_scan_result.modified_count > 0:
            change_logger.info(f"MongoDB: Zaktualizowano istniejący skan '{scan_info_to_save['page_raw_number_str']}' w książce (hash: {book_hash}).")
        else:
            # Jeśli skan nie istnieje, dodaj go do tablicy 'scans'
            self.books_collection.update_one(
                {"book_hash": book_hash},
                {"$push": {"scans": scan_info_to_save}}
            )
            change_logger.info(f"MongoDB: Dodano nowy skan '{scan_info_to_save['page_raw_number_str']}' do książki (hash: {book_hash}).")
        
        return True

    def save_local_metadata_json(self, book_hash: str, book_data: Dict[str, Any], scan_info: Dict[str, Any]) -> bool:
        """
        Zapisuje/aktualizuje metadane książki w lokalnym pliku JSON w folderze processed.
        Synchronizuje dane z Mongo.
        """
        book_folder = config.PROCESSED_DIR / book_hash
        book_folder.mkdir(exist_ok=True, parents=True) # Upewnij się, że folder istnieje
        json_path = book_folder / "metadata.json"
        
        # Wczytaj istniejące dane, jeśli plik istnieje
        data = {}
        if json_path.exists():
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except json.JSONDecodeError:
                logger.warning(f"Lokalny plik JSON uszkodzony – tworzę nowy: {json_path}")
                data = {}
        
        # Przygotowanie danych do serializacji JSON (rekurencyjnie)
        # Bierzemy book_data (które jest z MongoDB) i scan_info
        # Musimy je przekonwertować na format JSON-friendly
        serializable_book_data = _json_serializable(book_data)
        serializable_scan_info = _json_serializable(scan_info)
        
        # Aktualizuj metadane książki
        data.update(serializable_book_data)
        
        # Zaktualizuj lub dodaj skan do listy
        data.setdefault("scans", [])
        scan_exists = False
        
        for i, existing_scan in enumerate(data["scans"]):
            if existing_scan.get("page_raw_number_str") == serializable_scan_info["page_raw_number_str"]:
                data["scans"][i].update(serializable_scan_info)
                scan_exists = True
                break
        if not scan_exists:
            data["scans"].append(serializable_scan_info)

        # Zapisz JSON
        try:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            logger.info(f"Zapisano lokalne metadane JSON: {json_path}")
            return True
        except Exception as e:
            logger.error(f"Błąd zapisu lokalnego JSON dla {book_hash}: {e}", exc_info=True) # exc_info=True pokaże pełny traceback
            return False

# ----------------------------------------------------------
# Funkcje testowe dla DBManager
# ----------------------------------------------------------
if __name__ == "__main__":
    import sys
    # Upewniamy się, że logowanie jest skonfigurowane dla testów
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)-15s | %(message)s",
        handlers=[
            logging.FileHandler(config.LOGS_DIR / "db_manager_test.log", encoding="utf-8"),
            logging.StreamHandler(sys.stdout)
        ]
    )
    logger = logging.getLogger(__name__)
    change_logger = logging.getLogger("changes")
    logger.info("System logowania dla db_manager_test.py skonfigurowany lokalnie.")

    logger.info("\n--- Testowanie DBManager ---")

    db_manager = DBManager()

    if not db_manager.is_connected():
        logger.error("Brak połączenia z MongoDB. Upewnij się, że serwer jest uruchomiony. Nie można przeprowadzić testów bazy danych.")
        sys.exit(1) # Zakończ, jeśli nie ma połączenia

    # 1. Test dodawania/aktualizowania książki i skanu
    logger.info("\n--- Test 1: Dodawanie/Aktualizowanie książki i skanu ---")
    
    test_book_meta = {
        "title": "Historia Dawna",
        "authors": "Anna Krawczyk",
        "year": "2023",
        "pub_place": "Kraków",
        "publisher": "Wydawnictwo ABC",
        "num_pages": 300,
        "language": "pol", # Testujemy z językiem, ale zostanie usunięty przez pop() w upsert_book_and_scan
        "notes": "Testowa książka do biblioteki.",
        "keywords": ["historia", "starożytność", "test"]
    }
    test_scan_info_s0001 = {
        "alias": "TestKsiazka",
        "page_raw_number_str": "s0001",
        "page_type_short": "s",
        "page_type_full": "Strona Główna",
        "page_number_numeric": 1,
        "roman_number": "",
        "original_extension": ".jpg",
        "ocr_text": "To jest tekst OCR strony 1.",
        "page_full_path": Path("placeholder_path/s0001.jpg"), # Placeholder
        "created_at": datetime.now() # Data dodania skanu do rekordu
    }

    test_book_hash = utils.generate_book_hash(test_book_meta)
    test_scan_info_s0001["page_full_path"] = config.PROCESSED_DIR / test_book_hash / f"{test_book_hash}_{test_scan_info_s0001['page_raw_number_str']}{test_scan_info_s0001['original_extension']}"

    db_manager.upsert_book_and_scan(test_book_meta, test_scan_info_s0001)
    
    retrieved_book = db_manager.get_book_by_hash(test_book_hash)
    if retrieved_book:
        # Prawidłowe wywołanie save_local_metadata_json PO pobraniu danych z Mongo
        # Aby upewnić się, że to, co zapisujemy do JSON, jest zgodne z Mongo
        db_manager.save_local_metadata_json(test_book_hash, retrieved_book, test_scan_info_s0001)

        logger.info(f"Pobrano książkę po hash'u: {retrieved_book['title']}")
        if "scans" in retrieved_book and len(retrieved_book["scans"]) == 1 and \
           retrieved_book["scans"][0]["page_raw_number_str"] == "s0001":
            logger.info("Skan 's0001' został poprawnie dodany do książki.")
            local_json_path = config.PROCESSED_DIR / test_book_hash / 'metadata.json'
            if local_json_path.exists():
                logger.info(f"Lokalny plik JSON zapisany i istnieje: {local_json_path}")
            else:
                logger.error("Błąd: Lokalny plik JSON nie został zapisany.") # Ten błąd nie powinien się już pojawić
        else:
            logger.error("Błąd: Skan nie został dodany do książki lub brakuje pola 'scans'.")
    else:
        logger.error("Błąd: Książka nie została dodana do MongoDB.")

    # 2. Test aktualizacji istniejącego skanu (np. ponowne skanowanie OCR)
    logger.info("\n--- Test 2: Aktualizacja istniejącego skanu ---")
    test_scan_info_s0001_updated = test_scan_info_s0001.copy()
    test_scan_info_s0001_updated["ocr_text"] = "To jest ZAKTUALIZOWANY tekst OCR strony 1."
    test_scan_info_s0001_updated["processed_at"] = datetime.now()

    db_manager.upsert_book_and_scan(test_book_meta, test_scan_info_s0001_updated)
    retrieved_book_updated = db_manager.get_book_by_hash(test_book_hash)
    if retrieved_book_updated:
        db_manager.save_local_metadata_json(test_book_hash, retrieved_book_updated, test_scan_info_s0001_updated) # Wywołanie w Test 2
        
        if "scans" in retrieved_book_updated:
            updated_scan_data = next((s for s in retrieved_book_updated["scans"] if s["page_raw_number_str"] == "s0001"), None)
            if updated_scan_data and updated_scan_data["ocr_text"] == "To jest ZAKTUALIZOWANY tekst OCR strony 1.":
                logger.info("Skan 's0001' został poprawnie zaktualizowany (OCR).")
            else:
                logger.error("Błąd: Skan 's0001' nie został zaktualizowany poprawnie.")
        else:
            logger.error("Błąd: Nie można pobrać zaktualizowanej książki.")
    else:
        logger.error("Błąd: Nie można pobrać zaktualizowanej książki (po upsert w Test 2).")


    # 3. Test dodawania nowego skanu do tej samej książki
    logger.info("\n--- Test 3: Dodawanie nowego skanu do tej samej książki ---")
    test_scan_info_s0002 = {
        "alias": "TestKsiazka",
        "page_raw_number_str": "s0002",
        "page_type_short": "s",
        "page_type_full": "Strona Główna",
        "page_number_numeric": 2,
        "roman_number": "",
        "original_extension": ".jpg",
        "ocr_text": "To jest tekst OCR strony 2.",
        "page_full_path": config.PROCESSED_DIR / test_book_hash / f"{test_book_hash}_s0002.jpg",
        "created_at": datetime.now()
    }
    db_manager.upsert_book_and_scan(test_book_meta, test_scan_info_s0002)
    retrieved_book_with_page2 = db_manager.get_book_by_hash(test_book_hash)
    if retrieved_book_with_page2:
        db_manager.save_local_metadata_json(test_book_hash, retrieved_book_with_page2, test_scan_info_s0002) # Wywołanie w Test 3
        
        if "scans" in retrieved_book_with_page2 and len(retrieved_book_with_page2["scans"]) == 2:
            logger.info("Nowy skan 's0002' został poprawnie dodany.")
        else:
            logger.error("Błąd: Nowy skan 's0002' nie został dodany lub liczba skanów jest niepoprawna.")
    else:
        logger.error("Błąd: Nie można pobrać książki z nowym skanem (po upsert w Test 3).")


    # 4. Test ponownego dodania tej samej książki (powinno zaktualizować metadane książki)
    logger.info("\n--- Test 4: Ponowne dodanie tej samej książki (powinno aktualizować metadane) ---")
    test_book_meta_updated = test_book_meta.copy()
    test_book_meta_updated["notes"] = "Zaktualizowana notatka o książce. Dodana później."
    test_scan_info_s0001_again = test_scan_info_s0001.copy() 
    
    db_manager.upsert_book_and_scan(test_book_meta_updated, test_scan_info_s0001_again)
    retrieved_book_meta_updated = db_manager.get_book_by_hash(test_book_hash)
    if retrieved_book_meta_updated:
        db_manager.save_local_metadata_json(test_book_hash, retrieved_book_meta_updated, test_scan_info_s0001_again) # Wywołanie w Test 4
        
        if retrieved_book_meta_updated["notes"] == "Zaktualizowana notatka o książce. Dodana później.":
            logger.info("Metadane książki zostały poprawnie zaktualizowane.")
        else:
            logger.error("Błąd: Metadane książki nie zostały zaktualizowane poprawnie.")
            logger.error(f"Aktualne notatki: {retrieved_book_meta_updated.get('notes')}")
    else:
        logger.error("Błąd: Nie można pobrać zaktualizowanych metadanych książki (po upsert w Test 4).")


    # Opcjonalnie: Usuń testową książkę z bazy po testach, aby zachować czystość
    logger.info("\n--- Czyszczenie danych testowych (usuwanie książki) ---")
    try:
        delete_result = db_manager.books_collection.delete_one({"book_hash": test_book_hash})
        if delete_result.deleted_count > 0:
            logger.info(f"Usunięto testową książkę z bazy danych: {test_book_hash}")
        else:
            logger.warning(f"Nie znaleziono testowej książki do usunięcia: {test_book_hash}")
        
        # Usuń lokalny folder i pliki
        test_book_folder = config.PROCESSED_DIR / test_book_hash
        if test_book_folder.exists():
            import shutil
            shutil.rmtree(test_book_folder)
            logger.info(f"Usunięto lokalny folder testowy: {test_book_folder}")
    except PyMongoError as e:
        logger.error(f"Błąd podczas usuwania testowej książki z MongoDB: {e}")
    except Exception as e:
        logger.error(f"Nieoczekiwany błąd podczas czyszczenia danych testowych: {e}")


    # Po zakończeniu testów
    db_manager.close()
    logger.info("\n--- Testowanie DBManager zakończone ---")