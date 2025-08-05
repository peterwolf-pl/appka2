# C:\BIB\app\analysis\semantic_ripper.py

import logging
import spacy
from collections import Counter
from typing import Dict, Any, List

# Konfiguracja loggera
logger = logging.getLogger(__name__)

class SemanticRipper:
    """
    Klasa odpowiedzialna za głęboką analizę semantyczną tekstu.
    Używa modeli NLP (spaCy) do ekstrakcji encji, relacji i słów kluczowych.
    """
    _instance = None
    _nlp_model = None

    def __new__(cls, model_name: str = "pl_core_news_lg"):
        if cls._instance is None:
            cls._instance = super(SemanticRipper, cls).__new__(cls)
            try:
                # Ładujemy model spaCy tylko raz - jest to kosztowna operacja
                cls._nlp_model = spacy.load(model_name)
                logger.info(f"SemanticRipper: Model spaCy '{model_name}' załadowany pomyślnie.")
            except OSError:
                logger.error(f"SemanticRipper: Model spaCy '{model_name}' nie znaleziony.")
                logger.error(f"Uruchom 'python -m spacy download {model_name}' aby go pobrać.")
                # W tym wypadku ripper nie będzie działać
                cls._nlp_model = None
        return cls._instance

    def is_ready(self) -> bool:
        """Zwraca True, jeśli model NLP jest załadowany i gotowy do pracy."""
        return self._nlp_model is not None

    def analyze_text(self, full_text: str) -> Dict[str, Any]:
        """
        Główna metoda analityczna. Przetwarza cały tekst, dzieląc go na paragrafy.
        """
        if not self.is_ready() or not full_text:
            return {"error": "Ripper not ready or empty text provided."}

        # Dzielimy tekst na paragrafy (zakładamy, że są oddzielone podwójnym newline)
        paragraphs = [p.strip() for p in full_text.split('\n\n') if p.strip()]
        
        analysis_results = {
            "summary": {},
            "paragraphs": []
        }
        
        all_entities = []

        for i, p_text in enumerate(paragraphs):
            paragraph_analysis = self._analyze_paragraph(p_text)
            paragraph_analysis["paragraph_index"] = i
            analysis_results["paragraphs"].append(paragraph_analysis)
            
            # Agregujemy encje z całego tekstu
            all_entities.extend(paragraph_analysis.get("entities", []))

        # Tworzymy podsumowanie dla całego tekstu
        analysis_results["summary"] = self._create_summary(all_entities)
        
        return analysis_results

    def _analyze_paragraph(self, paragraph_text: str) -> Dict[str, Any]:
        """Analizuje pojedynczy paragraf."""
        doc = self._nlp_model(paragraph_text)
        
        # 1. Ekstrakcja Nazwanych Encji (NER)
        # To jest inteligentniejsza wersja szukania miejsc i dat
        entities = [
            {
                "text": ent.text,
                "label": ent.label_, # np. PER (osoba), LOC (miejsce), ORG (organizacja), DATE
                "start": ent.start_char,
                "end": ent.end_char
            }
            for ent in doc.ents
        ]
        
        # 2. Ekstrakcja słów kluczowych (rzeczowniki i przymiotniki)
        # Lematyzacja sprowadza słowo do jego formy podstawowej (np. 'poszli' -> 'pójść')
        keywords = [
            token.lemma_.lower()
            for token in doc
            if not token.is_stop and not token.is_punct and token.pos_ in ["NOUN", "PROPN", "ADJ"]
        ]
        
        # 3. Ekstrakcja kluczowych czasowników
        verbs = [
            token.lemma_.lower()
            for token in doc
            if not token.is_stop and token.pos_ == "VERB"
        ]

        return {
            "text": paragraph_text,
            "entities": entities,
            "keywords": list(Counter(keywords).keys()), # Unikalne słowa kluczowe
            "verbs": list(Counter(verbs).keys()) # Unikalne czasowniki
        }

    def _create_summary(self, all_entities: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Tworzy zagregowane podsumowanie dla całego tekstu."""
        summary = {
            "top_people": [],
            "top_locations": [],
            "top_organizations": [],
            "dates_mentioned": []
        }
        
        # Zliczamy wystąpienia każdej encji
        people_counter = Counter(e['text'] for e in all_entities if e['label'] == 'persName') # Lub PER w standardowym modelu
        locations_counter = Counter(e['text'] for e in all_entities if e['label'] == 'placeName') # Lub LOC
        orgs_counter = Counter(e['text'] for e in all_entities if e['label'] == 'orgName') # Lub ORG
        dates_counter = Counter(e['text'] for e in all_entities if e['label'] == 'date') # Lub DATE

        summary["top_people"] = people_counter.most_common(5)
        summary["top_locations"] = locations_counter.most_common(5)
        summary["top_organizations"] = orgs_counter.most_common(5)
        summary["dates_mentioned"] = list(dates_counter.keys())

        return summary

# Przykład użycia w osobnym skrypcie analitycznym
if __name__ == "__main__":
    from app.db_manager import DBManager
    
    logging.basicConfig(level=logging.INFO)
    logger.info("--- Testowanie SemanticRipper ---")

    # Inicjalizacja rippera
    ripper = SemanticRipper()
    if not ripper.is_ready():
        logger.error("Nie można uruchomić testu, model NLP nie jest załadowany.")
        exit()

    # Przykładowy tekst z książki historycznej
    sample_text = """
Profesor Jan Nowak pojechał do Berlina w maju 1989 roku. Spotkał się tam z przedstawicielami firmy Siemens AG.
Celem wizyty było omówienie współpracy technologicznej. Jan Nowak wrócił do Warszawy tydzień później, dokładnie 15 maja 1989 roku.
Uniwersytet Jagielloński był partnerem w tym projekcie.
    """
    
    # Analiza tekstu
    analysis = ripper.analyze_text(sample_text)

    # Wyświetlenie wyników w czytelny sposób
    import json
    print("--- Wyniki Analizy Semantycznej ---")
    print(json.dumps(analysis, indent=2, ensure_ascii=False))

    # --- Symulacja pełnego przepływu z bazą danych ---
    print("\n--- Symulacja przepływu z DB ---")
    db = DBManager()
    if db.is_connected():
        # Znajdź jeden dokument, który ma tekst OCR, ale nie ma jeszcze analizy
        doc_to_analyze = db.books_collection.find_one(
            {"scans.ocr_text": {"$exists": True, "$ne": ""}, "scans.analysis_results": {"$exists": False}},
            {"scans.$": 1, "book_hash": 1} # Pobierz tylko pierwszy pasujący skan
        )

        if doc_to_analyze:
            book_hash = doc_to_analyze["book_hash"]
            scan = doc_to_analyze["scans"][0]
            scan_path = scan["page_full_path"]
            
            logger.info(f"Znaleziono skan do analizy: {scan_path} z książki {book_hash}")

            # Wykonaj analizę
            scan_analysis_results = ripper.analyze_text(scan["ocr_text"])
            
            # Zaktualizuj dokument w bazie danych
            db.books_collection.update_one(
                {"book_hash": book_hash, "scans.page_full_path": scan_path},
                {"$set": {"scans.$.analysis_results": scan_analysis_results}}
            )
            logger.info(f"Zaktualizowano dokument w DB o wyniki analizy dla: {scan_path}")
        else:
            logger.info("Nie znaleziono w bazie żadnych nowych skanów do analizy.")
        db.close()
    else:
        logger.warning("Brak połączenia z DB, pomijam test integracji.")