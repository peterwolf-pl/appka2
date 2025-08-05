import json
import re
from pathlib import Path
from typing import List, Dict, Any
import logging

# Konfiguracja logowania
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(message)s")

# ----------------------------------------------------------
# MODUŁ ROZDZIELACZA DANYCH (A = Miejsce, B = Czas, C = Osoba, R = Rzecz)
# ----------------------------------------------------------
class DateSplitter:
    def __init__(self, metadata_path: Path):
        self.metadata_path = metadata_path
        self.data = self.load_metadata()

    def load_metadata(self) -> Dict[str, Any]:
        """Ładuje dane z metadata.json."""
        if not self.metadata_path.exists():
            logging.error(f"Plik {self.metadata_path} nie istnieje.")
            return {}
        with open(self.metadata_path, encoding="utf-8") as f:
            return json.load(f)

    def extract_dates_and_places(self) -> List[Dict[str, Any]]:
        """Wyciąga daty i miejsca z OCR skanów, buduje oś czasu."""
        timeline = []
        for scan in self.data.get("scans", []):
            ocr_text = scan.get("ocr", "")
            dates = self._extract_dates(ocr_text)
            places = self._extract_places(ocr_text)
            for date in dates:
                timeline.append({
                    "date": date,
                    "places": places,
                    "scan_path": scan["path"],
                    "description": ocr_text[:100] + "..."  # Krótki opis
                })
        # Sortuj po dacie (liniowo)
        timeline.sort(key=lambda x: x["date"])
        return timeline

    def _extract_dates(self, text: str) -> List[str]:
        """Wyciąga daty z tekstu (np. 1945, II w. p.n.e.)."""
        patterns = [
            r'\b(\d{4})\b',  # 1945
            r'\b(II|III|IV|V|VI|VII|VIII|IX|X|XI|XII|XIII|XIV|XV|XVI|XVII|XVIII|XIX|XX)\s+w\.\s+p\.n\.e\.\b',
            r'\b(\d{1,2})\s+(styczeń|luty|marzec|kwiecień|maj|czerwiec|lipiec|sierpień|wrzesień|październik|listopad|grudzień)\s+(\d{4})\b',
            r'\b(1[6-9]\d{2}|20\d{2})\s+-\s+(1[6-9]\d{2}|20\d{2})\b'  # 1945-1947
        ]
        dates = []
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            dates.extend(matches)
        return dates

    def _extract_places(self, text: str) -> List[str]:
        """Wyciąga miejsca (np. Warszawa, Kraków)."""
        places_pattern = r'\b(Warszawa|Kraków|Gdansk|Poznań|Londyn|Berlin|Rzym|Kair)\b'
        return re.findall(places_pattern, text, re.IGNORECASE)

    def generate_timeline_report(self) -> str:
        """Generuje raport osi czasu."""
        timeline = self.extract_dates_and_places()
        report = "Oś czasu:\n"
        for event in timeline:
            report += f"{event['date']} – Miejsca: {event['places']} (z skanu: {event['scan_path']})\n"
        return report

# ----------------------------------------------------------
# MAIN (dla testu modułu)
# ----------------------------------------------------------
if __name__ == "__main__":
    analyzer = DateSplitter(Path("processed/Historia-Powszechna Starożytność Wolski-Józef/metadata.json"))
    report = analyzer.generate_timeline_report()
    print(report)
    logging.info("Analiza dat zakończona.")