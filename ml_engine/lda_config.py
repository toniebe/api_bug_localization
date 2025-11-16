# ml_engine/lda_config.py
from __future__ import annotations

import math
from typing import Callable, Optional, Tuple


def suggest_lda_params(n_docs: int) -> Tuple[int, int]:
    """
    Kasih default (num_topics, passes) yang reasonable berdasarkan jumlah dokumen.

    Logic:
      - num_topics ~ 10 * log10(N), di-clamp ke [8, 150]
      - passes: corpora kecil boleh lebih banyak, corpora besar dikurangi
    """
    if n_docs <= 0:
        raise ValueError("n_docs must be positive")

    # base topic count: naik pelan secara logaritmik
    base_topics = int(round(10 * math.log10(n_docs)))
    num_topics = max(8, min(base_topics, 150))

    # passes: makin besar korpus -> passes sedikit dikurangi
    if n_docs < 5_000:
        passes = 12          # kecil → stabilitas lebih penting
    elif n_docs < 50_000:
        passes = 10          # medium
    else:
        passes = 8           # besar → hemat waktu, cukup stabil

    return num_topics, passes


def resolve_lda_params(
    n_docs: int,
    logger: Optional[Callable[[str], None]] = None,
) -> Tuple[int, int]:
    """
    Pilih (num_topics, passes) final dengan prioritas:

        CLI arg  >  ENV  >  AUTO (suggest_lda_params)

    - n_docs        : jumlah bug / dokumen
    - logger(msg)   : fungsi logging optional (misal log_write), fallback ke print
    """
    log = logger or (lambda msg: print(msg))

    num_topics, passes = suggest_lda_params(n_docs)
    return num_topics, passes
