import re
from typing import List
import nltk

# Pastikan resource tersedia; kalau belum ada akan diunduh (first run)
# Jalankan sekali saat import (aman untuk dev)
for pkg in ["punkt", "stopwords"]:
    try:
        nltk.data.find(f"tokenizers/{pkg}" if pkg=="punkt" else f"corpora/{pkg}")
    except LookupError:
        nltk.download(pkg)

from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize

STOPWORDS = set(stopwords.words("english")) | {
    # tambahkan stopwords teknis kalau perlu
    "the","a","an","to","of","in","on","and","or","for","with"
}

TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_#\-]+")

def normalize_text(text: str) -> str:
    return text.lower().strip()

def tokenize(text: str) -> List[str]:
    text = normalize_text(text)
    # gunakan regex agar token “bug-123”, “fxview-reviewers” tetap ikut
    tokens = TOKEN_PATTERN.findall(text)
    # filter stopwords dan token sangat pendek
    tokens = [t for t in tokens if t not in STOPWORDS and len(t) > 1]
    return tokens
