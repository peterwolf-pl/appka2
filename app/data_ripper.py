import json
import re
from pathlib import Path
from typing import List, Dict, Any
import logging
from dateparser import parse  # Dla parsowania dat
from tabulate import tabulate  # Dla formatowania tabel
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure

# Konfiguracja logowania
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(message)s")

# Custom exceptions
class OCRFileNotFound(Exception):
    """Wyjątek gdy plik z OCR nie istnieje."""
    pass

class DateParseException(Exception):
    """Wyjątek gdy nie udaje się sparsować daty."""
    pass

# ----------------------------------------------------------
# MODUŁ ANALIZY SEMIOTYCZNEJ
# ----------------------------------------------------------
class SemioticsAnalyzer:
    def __init__(self, symbols_db: List[str] = ["krzyż", "półksiężyc", "gwiazda Dawida", "orzeł"]):
        self.symbols = [s.lower() for s in symbols_db]  # Lista symboli do wyszukiwania
    
    def analyze(self, text: str) -> Dict[str, int]:
        """Analizuje tekst pod kątem symboli semiotycznych i zwraca licznik wystąpień."""
        text_lower = text.lower()
        results = {symbol: text_lower.count(symbol) for symbol in self.symbols}
        return {k: v for k, v in results.items() if v > 0}  # Zwracaj tylko symbole, które wystąpiły

# ----------------------------------------------------------
# MODUŁ EKSPORTERA DO MONGODB
# ----------------------------------------------------------
class MongoDBExporter:
    def __init__(self, uri: str = "mongodb://localhost:27017/", db_name: str = "history_db"):
        try:
            self.client = MongoClient(uri)
            self.client.admin.command('ping')  # Test połączenia
            self.db = self.client[db_name]
            logging.info("Połączenie z MongoDB udane.")
        except ConnectionFailure:
            logging.error("Nie udało się połączyć z MongoDB. Sprawdź URI.")
            raise
    
    def save_timeline(self, timeline: List[Dict[str, Any]]):
        """Zapisuje oś czasu do kolekcji 'timeline' w MongoDB."""
        try:
            collection = self.db.timeline
            result = collection.insert_many(timeline)
            logging.info(f"Zapisano {len(result.inserted_ids)} dokumentów do MongoDB.")
            return result.inserted_ids
        except Exception as e:
            logging.error(f"Błąd podczas zapisu do MongoDB: {e}")
            raise

# ----------------------------------------------------------
# GŁÓWNA KLASA ROZDZIELACZA DANYCH
# ----------------------------------------------------------
class DateSplitter:
    def __init__(self, metadata_path: Path):
        self.metadata_path = metadata_path
        self.data = self.load_metadata()
        self.semiotics_analyzer = SemioticsAnalyzer()  # Inicjalizacja analizera semiotycznego

    def load_metadata(self) -> Dict[str, Any]:
        """Ładuje dane z metadata.json z lepszą obsługą błędów."""
        if not self.metadata_path.exists():
            raise OCRFileNotFound(f"Plik {self.metadata_path} nie istnieje.")
        try:
            with open(self.metadata_path, encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            raise ValueError(f"Błąd dekodowania JSON w {self.metadata_path}.")
        except Exception as e:
            raise RuntimeError(f"Błąd podczas ładowania metadanych: {e}")

    def extract_dates_and_places(self) -> List[Dict[str, Any]]:
        """Wyciąga daty, miejsca i analizę semiotyczną z OCR skanów, buduje oś czasu."""
        timeline = []
        scans = self.data.get("scans", [])
        if not scans:
            logging.warning("Brak skanów w danych. Zwracam pustą listę.")
            return timeline

        for scan in scans:
            ocr_text = scan.get("ocr", "").lower()  # Konwersja na małe litery
            if not ocr_text:
                logging.warning(f"Brak tekstu OCR w skanie: {scan.get('path', 'Nieznany')}")
                continue

            dates_str = self._extract_dates(ocr_text)
            places = self._extract_places(ocr_text)
            semiotics = self.semiotics_analyzer.analyze(scan.get("ocr", ""))  # Analiza semiotyczna

            for date_str in dates_str:
                try:
                    parsed_date = parse(date_str, languages=['pl'])
                    if not parsed_date:
                        raise DateParseException(f"Nie udało się sparsować daty: {date_str}")
                    timeline.append({
                        "date": parsed_date,  # Obiekt datetime
                        "date_str": date_str,  # Oryginalny string
                        "places": places,  # Lista miejsc
                        "semiotics": semiotics,  # Słownik z symbolami
                        "scan_path": scan.get("path", "Nieznany"),
                        "description": scan.get("ocr", "")[:100] + "..."
                    })
                except DateParseException as e:
                    logging.warning(f"Problem z datą w skanie {scan.get('path', 'Nieznany')}: {e}")
                    continue  # Pomiń tę datę

        # Sortuj po dacie
        timeline.sort(key=lambda x: x["date"])
        return timeline

    def _extract_dates(self, text: str) -> List[str]:
        """Wyciąga potencjalne ciągi dat z tekstu."""
        patterns = [
            r'\b(\d{4})\b',  # np. 1945
            r'\b(II|III|IV|V|VI|VII|VIII|IX|X|XI|XII|XIII|XIV|XV|XVI|XVII|XVIII|XIX|XX)\s*w\.\s*p\.n\.e\.\b',
            r'\b(\d{1,2})\s+(styczeń|luty|marzec|kwiecień|maj|czerwiec|lipiec|sierpień|wrzesień|październik|listopad|grudzień)\s+(\d{4})\b',
            r'\b(1[6-9]\d{2}|20\d{2})\s*-\s*(1[6-9]\d{2}|20\d{2})\b',  # np. 1945-1947
            r'\b\d{1,2}\.\d{1,2}\.\d{4}\b'  # Dodaj format DD.MM.YYYY
        ]
        dates = []
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                if isinstance(match, tuple):
                    date_str = " ".join(match)  # Scal tuple
                else:
                    date_str = match
                dates.append(date_str)
        return dates

    def _extract_places(self, text: str) -> List[str]:
        """Wyciąga miejsca. Lista jest rozszerzona."""
        places_pattern = r'\b(Warszawa|Kraków|Gdansk|Poznań|Londyn|Berlin|Rzym|Kair|Paris|New York|Moskwa|Lwów|Wiedeń)\b'
        return re.findall(places_pattern, text, re.IGNORECASE)

    def generate_timeline_report(self) -> str:
        """Generuje raport osi czasu z tabelarycznym formatowaniem."""
        timeline = self.extract_dates_and_places()
        if not timeline:
            return "Brak wydarzeń do wyświetlenia."

        table_data = []
        for event in timeline:
            date_str = event["date"].strftime("%Y-%m-%d") if event["date"] else event["date_str"]
            places_str = ", ".join(event["places"]) if event["places"] else "Brak miejsc"
            semiotics_str = ", ".join([f"{k}: {v}" for k, v in event["semiotics"].items()]) if event["semiotics"] else "Brak symboli"
            table_data.append([date_str, places_str, semiotics_str, event["scan_path"], event["description"]])

        headers = ["Data", "Miejsca", "Symbole semiotyczne", "Ścieżka skanu", "Opis"]
        report_table = tabulate(table_data, headers=headers, tablefmt="grid")
        return f"Oś czasu wydarzeń:\n{report_table}"

    def export_to_mongo(self, uri: str, db_name: str):
        """Eksportuje oś czasu do MongoDB."""
        exporter = MongoDBExporter(uri, db_name)
        timeline = self.extract_dates_and_places()
        return exporter.save_timeline(timeline)

# MAIN (dla testu modułu)
if __name__ == "__main__":
    try:
        analyzer = DateSplitter(Path("processed/Historia-Powszechna Starożytność Wolski-Józef/metadata.json"))
        
        # Generuj raport
        report = analyzer.generate_timeline_report()
        print(report)
        
        # Eksport do MongoDB (opcjonalny, z domyślnym URI)
        analyzer.export_to_mongo("mongodb://localhost:27017/", "history_analysis")
        
        logging.info("Analiza dat zakończona.")
    except OCRFileNotFound as e:
        logging.error(e)
    except DateParseException as e:
        logging.error(e)
    except Exception as e:
        logging.error(f"Niespodziewany błąd: {e}")