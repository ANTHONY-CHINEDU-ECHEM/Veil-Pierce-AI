"""Hybrid retrieval indexes.

Two indexes are provided. HybridIndex ranks passages of text (the typology
library) by combining a lexical BM25 channel with a dense channel and fusing
the two rankings with reciprocal rank fusion. EntityIndex finds entities by
name across hundreds of thousands of companies, persons and offshore
entities, tolerating typing slips and missing legal forms. Fusion helps on
passages and does not help on names, and both results are reported.

The dense channel is latent semantic analysis fitted on the corpus, which
needs no model download and keeps every run reproducible offline. Any
function that maps a list of texts to a matrix of vectors can be passed in
as the embedder to replace it with a neural sentence encoder.
"""

from __future__ import annotations

import re
from typing import Callable, Sequence

import numpy as np
from scipy.sparse import csr_matrix, hstack
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, CountVectorizer, TfidfVectorizer
from sklearn.preprocessing import normalize

from ..textnorm import norm_text

_WORD = re.compile(r"[^\W\d_]{2,}|\d+")
_SUFFIXES = ("ations", "ation", "ments", "ment", "ings", "ing", "ies", "ers", "er", "ed", "es", "s")
_SYNONYMS = {
    "firm": "company", "firms": "company", "business": "company", "businesses": "company", "entities": "entity",
    "owner": "controller", "owners": "controller", "owned": "controlled", "owns": "controls",
    "sanctioned": "designated", "listed": "designated", "blocked": "designated",
    "office": "address", "premises": "address", "building": "address",
    "struck": "dissolved", "closed": "dissolved", "shut": "dissolved",
    "formed": "incorporated", "created": "incorporated", "started": "incorporated",
    "bvi": "offshore", "seychelles": "offshore", "panama": "offshore",
    "loop": "circular", "ring": "circular",
    "spelled": "spelling", "spelt": "spelling",
    "leaked": "leak", "files": "records",
}


def stem(token: str) -> str:
    """Very light suffix stripping so plural and verb forms meet."""
    for suffix in _SUFFIXES:
        if token.endswith(suffix) and len(token) - len(suffix) >= 4:
            return token[: len(token) - len(suffix)]
    return token


def analyse(text: str) -> list[str]:
    """Tokenise, drop stop words, map a few domain synonyms and stem."""
    tokens = []
    for token in _WORD.findall(text.lower()):
        if token in ENGLISH_STOP_WORDS:
            continue
        tokens.append(stem(_SYNONYMS.get(token, token)))
    return tokens


class HybridIndex:
    """BM25 plus dense retrieval over a small or medium passage collection."""

    def __init__(
        self,
        ids: Sequence[str],
        texts: Sequence[str],
        k1: float = 1.4,
        b: float = 0.75,
        dimensions: int = 96,
        rrf_k: int = 60,
        fit_texts: Sequence[str] | None = None,
        embedder: Callable[[Sequence[str]], np.ndarray] | None = None,
    ) -> None:
        self.ids = list(ids)
        self.texts = list(texts)
        self.rrf_k = rrf_k
        self._counts = CountVectorizer(analyzer=analyse)
        tf = self._counts.fit_transform(self.texts).astype(np.float64).tocsr()
        n_docs = tf.shape[0]
        length = np.asarray(tf.sum(axis=1)).ravel()
        df = np.asarray((tf > 0).sum(axis=0)).ravel()
        idf = np.log(1.0 + (n_docs - df + 0.5) / (df + 0.5))
        rows, cols = tf.nonzero()
        values = tf.data
        denom = values + k1 * (1.0 - b + b * length[rows] / max(1e-9, length.mean()))
        self._bm25 = csr_matrix((idf[cols] * values * (k1 + 1.0) / denom, (rows, cols)), shape=tf.shape)

        self._embedder = embedder
        if embedder is None:
            corpus = list(fit_texts) if fit_texts else self.texts
            self._word = TfidfVectorizer(analyzer=analyse, ngram_range=(1, 1), sublinear_tf=True)
            self._char = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True, min_df=1)
            fitted = hstack([self._word.fit_transform(corpus), 0.5 * self._char.fit_transform(corpus)]).tocsr()
            components = int(max(2, min(dimensions, fitted.shape[0] - 1, fitted.shape[1] - 1)))
            self._svd = TruncatedSVD(n_components=components, random_state=0)
            self._svd.fit(fitted)
        self._dense = self._embed(self.texts)

    def _embed(self, texts: Sequence[str]) -> np.ndarray:
        if self._embedder is not None:
            return normalize(np.asarray(self._embedder(list(texts)), dtype=np.float64))
        sparse = hstack([self._word.transform(texts), 0.5 * self._char.transform(texts)]).tocsr()
        return normalize(self._svd.transform(sparse))

    def scores(self, query: str) -> tuple[np.ndarray, np.ndarray]:
        """Raw BM25 and dense cosine scores of every passage for a query."""
        q = self._counts.transform([query])
        q.data[:] = 1.0
        lexical = np.asarray((self._bm25 @ q.T).todense()).ravel()
        dense = self._dense @ self._embed([query])[0]
        return lexical, dense

    def search(self, query: str, k: int = 5, mode: str = "hybrid") -> list[tuple[str, float]]:
        """Ranked passage identifiers with scores. mode is bm25, dense or hybrid."""
        lexical, dense = self.scores(query)
        if mode == "bm25":
            final = lexical
        elif mode == "dense":
            final = dense
        else:
            final = np.zeros(len(self.ids))
            for channel in (lexical, dense):
                order = np.argsort(-channel, kind="stable")
                ranks = np.empty(len(order))
                ranks[order] = np.arange(1, len(order) + 1)
                final += 1.0 / (self.rrf_k + ranks)
        top = np.argsort(-final, kind="stable")[:k]
        return [(self.ids[i], float(final[i])) for i in top]


class EntityIndex:
    """Name lookup over every entity in the graph.

    Each name is stored as character ngram TFIDF, which makes lookup robust
    to typing slips, and as a bag of whole tokens weighted by rarity. Lookup
    uses the character channel by default.
    """

    def __init__(self, keys: Sequence[str], names: Sequence[str], kinds: Sequence[str], rrf_k: int = 60) -> None:
        self.keys = np.asarray(keys, dtype=object)
        self.names = np.asarray(names, dtype=object)
        self.kinds = np.asarray(kinds, dtype=object)
        self.rrf_k = rrf_k
        self.word_weight = 0.15
        normalised = [norm_text(name) for name in names]
        self._normalised = np.asarray(normalised, dtype=object)
        self._exact = {}
        for position, value in enumerate(normalised):
            self._exact.setdefault(value, position)
        self._char = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), sublinear_tf=True, dtype=np.float32)
        self._char_matrix = self._char.fit_transform(normalised).tocsr()
        self._word = TfidfVectorizer(analyzer=str.split, dtype=np.float32)
        self._word_matrix = self._word.fit_transform(normalised).tocsr()

    def _top(self, scores: np.ndarray, k: int) -> np.ndarray:
        k = min(k, len(scores))
        part = np.argpartition(-scores, k - 1)[:k]
        return part[np.argsort(-scores[part], kind="stable")]

    def channels(self, query: str) -> tuple[np.ndarray, np.ndarray]:
        """Word level and character level scores of every entity for a query."""
        text = norm_text(query)
        word = self._word_matrix @ self._word.transform([text]).toarray().ravel()
        char = self._char_matrix @ self._char.transform([text]).toarray().ravel()
        return np.asarray(word).ravel(), np.asarray(char).ravel()

    def rank(self, word: np.ndarray, char: np.ndarray, k: int = 5, mode: str = "char") -> list[dict]:
        """Turn channel scores into a ranked list.

        mode is char (the default), word, blend or rrf. On names the
        character channel alone is the most accurate, because one typing slip
        removes a whole word from the word channel while leaving most
        character ngrams intact. The blend and the rank fusion of the two
        channels are kept so that the comparison can be reproduced.
        """
        if mode == "word":
            return [self._row(i, float(word[i])) for i in self._top(word, k) if word[i] > 0]
        if mode == "rrf":
            depth = max(50, k * 10)
            fused: dict[int, float] = {}
            for channel in (word, char):
                for position, i in enumerate(self._top(channel, depth), start=1):
                    if channel[i] > 0:
                        fused[int(i)] = fused.get(int(i), 0.0) + 1.0 / (self.rrf_k + position)
            ranked = sorted(fused.items(), key=lambda item: (-item[1], -char[item[0]]))[:k]
            return [self._row(i, float(char[i])) for i, _ in ranked]
        if mode == "blend":
            peak = float(word.max()) if len(word) else 0.0
            blended = char + (self.word_weight * word / peak if peak > 0 else 0.0)
            return [self._row(i, float(char[i])) for i in self._top(blended, k) if blended[i] > 0]
        return [self._row(i, float(char[i])) for i in self._top(char, k) if char[i] > 0]

    def exact(self, query: str) -> list[dict]:
        hit = self._exact.get(norm_text(query))
        return [] if hit is None else [self._row(hit, 1.0)]

    def search(self, query: str, k: int = 5, mode: str = "char", kind: str | None = None) -> list[dict]:
        """Best matching entities. mode is char, exact, word, blend or rrf."""
        if mode == "exact":
            return self.exact(query)
        word, char = self.channels(query)
        if kind is not None:
            mask = self.kinds != kind
            word[mask] = 0.0
            char[mask] = 0.0
        return self.rank(word, char, k, mode)

    def _row(self, position: int, score: float) -> dict:
        return {"key": str(self.keys[position]), "name": str(self.names[position]), "kind": str(self.kinds[position]), "score": round(score, 4)}
