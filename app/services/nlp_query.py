# app/services/nlp_query.py
import re
import nltk
from typing import List, Dict
from nltk.corpus import stopwords
from nltk.stem import PorterStemmer
from nltk.tokenize import word_tokenize

# --- Inisialisasi NLTK resource (sekali di awal aplikasi) ---
# Di production sebaiknya kamu download di build step, bukan di runtime.
try:
    stopwords.words("english")
except LookupError:
    nltk.download("stopwords")

try:
    word_tokenize("test")
except LookupError:
    nltk.download("punkt")
    nltk.download("punkt_tab")

_stop_words = set(stopwords.words("english"))
_stemmer = PorterStemmer()


def preprocess_query(text: str) -> Dict[str, object]:
    """
    Lakukan preprocessing ala NLTK:
    - lowercase
    - tokenize
    - buang non-alphanumeric
    - buang stopwords
    - stemming

    Return:
    {
        "original": ...,
        "tokens": [...],
        "stems": [...],
        "processed_str": "..."   # untuk dikirim ke search engine / index
    }
    """
    # 1. Lowercase
    text = text.lower()

    # 2. Tokenize
    tokens = word_tokenize(text)

    # 3. Bersihkan token (hanya alnum)
    tokens = [re.sub(r"[^a-z0-9]+", "", t) for t in tokens]
    tokens = [t for t in tokens if t]  # buang kosong

    # 4. Buang stopwords
    tokens = [t for t in tokens if t not in _stop_words]

    # 5. Stemming
    stems = [_stemmer.stem(t) for t in tokens]

    # 6. Gabung jadi 1 string (ini "the content after processing")
    processed_str = " ".join(stems)

    return {
        "original": text,
        "tokens": tokens,
        "stems": stems,
        "processed_str": processed_str,
    }
