# C:\BIB\app\ocr_engine.py

import logging
from pathlib import Path
from typing import Optional, List
from PIL import Image # Do manipulacji obrazami
import pytesseract    # Do wywoływania Tesseract OCR

from app import config

# Logger dla tego modułu
logger = logging.getLogger(__name__)

class OCREngine:
    """
    Klasa zarządzająca operacjami OCR za pomocą Tesseract.
    Obsługuje inicjalizację, sprawdzanie dostępności i wykonywanie OCR.
    """
    _instance = None # Singleton pattern

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(OCREngine, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._tesseract_available = False
        self._initialized = True
        self._check_tesseract_availability()

    def _check_tesseract_availability(self):
        """Sprawdza dostępność pliku wykonywalnego Tesseract i PyTesseract."""
        if not Path(config.TESS_CMD).exists():
            logger.error(f"Tesseract: Plik wykonywalny nie znaleziony pod ścieżką: {config.TESS_CMD}")
            self._tesseract_available = False
            return
        
        try:
            pytesseract.pytesseract.tesseract_cmd = config.TESS_CMD
            # Testujemy, czy pytesseract jest w stanie wywołać tesseract
            version = pytesseract.get_tesseract_version()
            logger.info(f"Tesseract: Zainicjalizowany (wersja: {version}) z: {config.TESS_CMD}")
            self._tesseract_available = True
        except pytesseract.TesseractNotFoundError:
            logger.error(f"Tesseract: Błąd 'TesseractNotFoundError'. Upewnij się, że '{config.TESS_CMD}' jest poprawne i Tesseract jest zainstalowany.")
            self._tesseract_available = False
        except Exception as e:
            logger.error(f"Tesseract: Nieoczekiwany błąd inicjalizacji: {e}")
            self._tesseract_available = False

    def is_available(self) -> bool:
        """Zwraca True, jeśli Tesseract OCR jest dostępny i gotowy do użycia."""
        return self._tesseract_available

    def perform_ocr(self, image_path: Path, lang: str = config.DEFAULT_OCR_LANG) -> str:
        """
        Wykonuje OCR na podanym obrazie.
        Obraz jest konwertowany do czarno-białego, jeśli config.OCR_CONVERT_TO_BW jest True.
        """
        if not self.is_available():
            logger.warning("OCR: Tesseract niedostępny, pomijam rozpoznawanie tekstu.")
            return ""
        
        if not image_path.exists():
            logger.error(f"OCR: Plik obrazu nie istnieje: {image_path}")
            return ""

        if lang not in config.SUPPORTED_OCR_LANGS:
            logger.warning(f"OCR: Język '{lang}' nie jest wspierany lub nieznany w konfiguracji. Używam domyślnego '{config.DEFAULT_OCR_LANG}'.")
            lang = config.DEFAULT_OCR_LANG

        try:
            with Image.open(image_path) as img:
                if config.OCR_CONVERT_TO_BW:
                    # Konwersja do skali szarości, a następnie do 1-bitowej czerni-bieli
                    # Adaptacyjna binaryzacja może poprawić wyniki dla zdjęć
                    img = img.convert("L").point(lambda x: 0 if x < 128 else 255, '1')
                    # Możesz eksperymentować z Image.ADAPTIVE_THRESHOLD lub innymi algorytmami binaryzacji
                    # img = img.convert("L").filter(ImageFilter.SHARPEN) # Opcjonalnie wyostrzanie
                
                # Używamy psm (page segmentation mode) 3 dla domyślnego rozpoznawania
                # Inne tryby (np. 6 dla pojedynczego bloku tekstu) mogą być lepsze w specyficznych przypadkach
                # '--oem 1' to LSTM (nowy silnik), '--oem 0' to legacy, '--oem 3' to kombinacja (domyślnie)
                ocr_text = pytesseract.image_to_string(img, lang=lang, config='--psm 3')
                
                logger.info(f"OCR: Przetworzono obraz {image_path.name} (język: {lang}).")
                return ocr_text.strip()
        except Image.UnidentifiedImageError:
            logger.error(f"OCR: Niepoprawny format obrazu dla {image_path.name}.")
            return ""
        except pytesseract.TesseractError as e:
            logger.error(f"OCR: Błąd Tesseracta podczas przetwarzania {image_path.name}: {e}")
            return ""
        except Exception as e:
            logger.error(f"OCR: Nieoczekiwany błąd podczas OCR dla {image_path.name}: {e}")
            return ""

# ----------------------------------------------------------
# Funkcje testowe dla OCREngine
# ----------------------------------------------------------
if __name__ == "__main__":
    import sys
    # Upewniamy się, że logowanie jest skonfigurowane dla testów
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)-15s | %(message)s",
        handlers=[
            logging.FileHandler(config.LOGS_DIR / "ocr_engine_test.log", encoding="utf-8"),
            logging.StreamHandler(sys.stdout)
        ]
    )
    logger = logging.getLogger(__name__)
    logger.info("System logowania dla ocr_engine_test.py skonfigurowany lokalnie.")

    logger.info("\n--- Testowanie OCREngine ---")

    # Inicjalizacja silnika OCR
    ocr_engine = OCREngine()

    if not ocr_engine.is_available():
        logger.warning("Tesseract jest niedostępny, testy OCR zostaną pominięte.")
        sys.exit(0) # Zakończ testy, jeśli Tesseract nie działa

    # Przygotowanie testowego obrazu
    # Utwórz fikcyjny obraz testowy (np. biały obraz z napisem "Test OCR")
    test_image_dir = config.BASE_DIR / "test_data"
    test_image_dir.mkdir(exist_ok=True)
    test_image_path = test_image_dir / "test_ocr_image.png"

    try:
        from PIL import ImageDraw, ImageFont
        # Tworzenie prostego obrazka z tekstem
        img_width, img_height = 400, 200
        test_img = Image.new("RGB", (img_width, img_height), color="white")
        d = ImageDraw.Draw(test_img)
        
        try:
            # Spróbuj użyć czcionki systemowej, np. Arial
            font = ImageFont.truetype("arial.ttf", 40)
        except IOError:
            # Fallback na domyślną czcionkę Pillow
            font = ImageFont.load_default()
            logger.warning("Nie znaleziono arial.ttf, używam domyślnej czcionki.")
        
        d.text((50, 70), "Test OCR po Polsku", fill=(0, 0, 0), font=font)
        d.text((50, 120), "Hello World in English", fill=(0, 0, 0), font=font)
        test_img.save(test_image_path)
        logger.info(f"Utworzono obraz testowy: {test_image_path}")

        # Testowanie OCR dla języka polskiego
        logger.info("\n--- Testowanie OCR (polski) ---")
        ocr_result_pol = ocr_engine.perform_ocr(test_image_path, lang="pol")
        logger.info(f"Wynik OCR (polski):\n---\n{ocr_result_pol}\n---")
        if "Test OCR po Polsku" in ocr_result_pol and "Hello World in English" in ocr_result_pol:
            logger.info("Test OCR (polski) POWODZENIE.")
        else:
            logger.error("Test OCR (polski) NIEPOWODZENIE - oczekiwany tekst nie został znaleziony.")

        # Testowanie OCR dla języka angielskiego
        logger.info("\n--- Testowanie OCR (angielski) ---")
        ocr_result_eng = ocr_engine.perform_ocr(test_image_path, lang="eng")
        logger.info(f"Wynik OCR (angielski):\n---\n{ocr_result_eng}\n---")
        if "Test OCR po Polsku" in ocr_result_eng and "Hello World in English" in ocr_result_eng:
            logger.info("Test OCR (angielski) POWODZENIE.")
        else:
            logger.error("Test OCR (angielski) NIEPOWODZENIE - oczekiwany tekst nie został znaleziony.")

    except ImportError:
        logger.error("Brak modułów Pillow.ImageDraw/ImageFont. Nie można utworzyć obrazu testowego. Zainstaluj: pip install Pillow")
    except Exception as e:
        logger.error(f"Wystąpił błąd podczas tworzenia/testowania obrazu: {e}")
    finally:
        # Cleanup - usuń obraz testowy
        if test_image_path.exists():
            test_image_path.unlink()
            logger.info(f"Usunięto obraz testowy: {test_image_path}")
        if test_image_dir.exists():
            try:
                test_image_dir.rmdir() # Spróbuj usunąć folder, jeśli pusty
                logger.info(f"Usunięto katalog testowy: {test_image_dir}")
            except OSError:
                logger.warning(f"Nie można usunąć katalogu testowego {test_image_dir}, prawdopodobnie nie jest pusty.")

    logger.info("\n--- Testowanie OCREngine zakończone ---")