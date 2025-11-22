from __future__ import annotations

import os
import re
from typing import List, Dict, Any, Tuple

import numpy as np
from sklearn.neighbors import NearestNeighbors
from gensim import corpora, models

import nltk
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize

HERE = os.path.dirname(os.path.abspath(__file__))

# Pastikan ini sudah di-run sekali di environment kamu:
# nltk.download("punkt")
# nltk.download("stopwords")

STOPWORDS = set(stopwords.words("english"))


class LdaArtifacts:
    """
    Artefak LDA untuk SATU database:
    - dictionary
    - lda_model
    - topic_mat (optional, untuk similarity)
    - bug_ids  (optional, untuk similarity)
    - nn       (NearestNeighbors)
    """

    def __init__(self, lda_dir: str):
        dict_path = os.path.join(lda_dir, "lda_dictionary.dict")
        model_path = os.path.join(lda_dir, "lda_model.gensim")
        topic_mat_path = os.path.join(lda_dir, "topic_mat.npy")
        bug_ids_path = os.path.join(lda_dir, "bug_ids.txt")

        if not os.path.exists(dict_path) or not os.path.exists(model_path):
            raise RuntimeError(
                f"LDA artifacts not found in {lda_dir}.\n"
                f"Expected files:\n"
                f"  - {dict_path}\n"
                f"  - {model_path}\n"
                f"Run 02_lda_topics.py with --outdir pointing to this directory."
            )

        self.dictionary: corpora.Dictionary = corpora.Dictionary.load(dict_path)
        self.lda_model: models.LdaModel = models.LdaModel.load(model_path)
        self.num_topics: int = self.lda_model.num_topics

        self.topic_mat: np.ndarray | None = None
        self.bug_ids: List[str] = []
        self.nn: NearestNeighbors | None = None

        if os.path.exists(topic_mat_path) and os.path.exists(bug_ids_path):
            self.topic_mat = np.load(topic_mat_path)
            with open(bug_ids_path, "r", encoding="utf-8") as f:
                self.bug_ids = [line.strip() for line in f]

            if len(self.bug_ids) == self.topic_mat.shape[0]:
                self.nn = NearestNeighbors(metric="cosine", algorithm="brute")
                self.nn.fit(self.topic_mat)


class NlpTopicService:
    """
    Multi-database LTM / LDA service.

    Lokasi artefak mengikuti ml_runner_service:
        ML_ENGINE_DIR / "out_lda" / db_name

    Contoh:
        ML_ENGINE_DIR=/.../ml_engine
        db_name="EasyFixLabsAlphaProject"

        -> /.../ml_engine/out_lda/EasyFixLabsAlphaProject/lda_model.gensim
    """

    def __init__(self):
        # sesuaikan default ini dengan struktur project-mu
        self.ml_engine_dir = os.getenv(
            "ML_ENGINE_DIR",
            os.path.join(HERE, "..", "..", "..", "ml_engine"),
        )
        # cache artefak per db_name
        self._models: Dict[str, LdaArtifacts] = {}

    # ---------- helper: load artefak per database ----------
    def _get_artifacts(self, db_name: str) -> LdaArtifacts:
        if db_name in self._models:
            return self._models[db_name]

        lda_dir = os.path.join(self.ml_engine_dir, "out_lda", db_name)
        artifacts = LdaArtifacts(lda_dir)
        self._models[db_name] = artifacts
        return artifacts

    # ---------- NLTK preprocessing ----------
    def preprocess_tokens(self, text: str) -> List[str]:
        text = text.lower()
        text = re.sub(r"http\S+", " ", text)
        text = re.sub(r"[^a-z0-9]+", " ", text)
        tokens = word_tokenize(text)
        tokens = [t for t in tokens if t not in STOPWORDS and len(t) > 2]
        return tokens

    # ---------- Topic inference (LTM) ----------
    def infer_topics(self, db_name: str, text: str) -> Dict[str, Any]:
        """
        Inference topic untuk 1 teks di database tertentu.
        Return:
          {
            "main_topic_id": int | None,
            "main_topic_prob": float | None,
            "topic_distribution": List[Tuple[int, float]]
          }
        """
        artifacts = self._get_artifacts(db_name)

        tokens = self.preprocess_tokens(text)
        if not tokens:
            return {
                "main_topic_id": None,
                "main_topic_prob": None,
                "topic_distribution": [],
            }

        bow = artifacts.dictionary.doc2bow(tokens)
        if not bow:
            return {
                "main_topic_id": None,
                "main_topic_prob": None,
                "topic_distribution": [],
            }

        topic_dist: List[Tuple[int, float]] = artifacts.lda_model.get_document_topics(
            bow, minimum_probability=0.0
        )
        if not topic_dist:
            return {
                "main_topic_id": None,
                "main_topic_prob": None,
                "topic_distribution": [],
            }

        main_topic_id, main_topic_prob = max(topic_dist, key=lambda x: x[1])

        return {
            "main_topic_id": main_topic_id,
            "main_topic_prob": float(main_topic_prob),
            "topic_distribution": topic_dist,
        }

    # ---------- Similar / duplicate ----------
    def find_similar_bugs(
        self,
        db_name: str,
        topic_distribution: List[Tuple[int, float]],
        sim_threshold: float,
        dup_threshold: float,
        top_k: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Cari bug-bug lama yang similar / duplicate berdasarkan distribusi topic.
        """
        artifacts = self._get_artifacts(db_name)

        if artifacts.nn is None or artifacts.topic_mat is None:
            return []

        n_topics = artifacts.num_topics
        vec = np.zeros((1, n_topics), dtype=np.float32)
        for tid, prob in topic_distribution:
            tid = int(tid)
            if 0 <= tid < n_topics:
                vec[0, tid] = float(prob)

        n_neighbors = min(top_k, artifacts.topic_mat.shape[0])
        distances, indices = artifacts.nn.kneighbors(vec, n_neighbors=n_neighbors)

        results: List[Dict[str, Any]] = []
        for dist, idx in zip(distances[0], indices[0]):
            score = 1.0 - float(dist)
            if score < sim_threshold:
                continue

            other_bug_id = artifacts.bug_ids[idx]
            relation = "duplicate" if score >= dup_threshold else "similar"
            results.append(
                {
                    "target_bug_id": str(other_bug_id),
                    "score": score,
                    "relation": relation,
                    "source": "lda_online",
                }
            )

        return results


# ---------- singleton ----------
_nlp_topic_service: NlpTopicService | None = None


def get_nlp_topic_service() -> NlpTopicService:
    global _nlp_topic_service
    if _nlp_topic_service is None:
        _nlp_topic_service = NlpTopicService()
    return _nlp_topic_service
