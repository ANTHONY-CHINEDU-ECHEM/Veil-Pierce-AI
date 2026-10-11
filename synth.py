"""Synthetic corporate registry with planted concealment typologies.

Real registries carry no labels saying which companies are shells, so a
detector cannot be scored against them. This generator produces a registry in
the same shape as the public sources (company register, officer appointments,
persons with significant control, a leaked offshore database and a sanctions
list) and plants six concealment typologies inside realistic background
noise. Because the generator knows exactly what it planted, every stage of
the system can be measured against ground truth.

Each planted typology comes with a benign lookalike that shares its surface
signature, so that a detector cannot succeed on one simple threshold.

All names are fictional combinations of common words and name tokens.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ..config import SynthConfig
from ..logging_utils import get_logger
from . import pools

log = get_logger(__name__)

TABLE_NAMES = (
    "companies",
    "officers",
    "pscs",
    "offshore_entities",
    "offshore_officers",
    "offshore_edges",
    "sanctions",
)
TYPOLOGIES = ("nominee", "address_factory", "circular", "sanctions", "opaque", "phoenix_burst")


def day(year: int, month: int, dom: int) -> np.datetime64:
    """Build a numpy day from integers."""
    return np.datetime64(dt.date(year, month, dom), "D")


PSC_REGIME_START = day(2016, 4, 6)
NAT = np.datetime64("NaT", "D")


@dataclass
class Registry:
    """Container for the canonical tables and, for synthetic data, the truth."""

    companies: pd.DataFrame
    officers: pd.DataFrame
    pscs: pd.DataFrame
    offshore_entities: pd.DataFrame
    offshore_officers: pd.DataFrame
    offshore_edges: pd.DataFrame
    sanctions: pd.DataFrame
    truth: dict[str, pd.DataFrame] = field(default_factory=dict)
    meta: dict = field(default_factory=dict)

    def summary(self) -> dict[str, int]:
        return {name: int(len(getattr(self, name))) for name in TABLE_NAMES}

    def total_records(self) -> int:
        return int(sum(self.summary().values()))


def _typo(rng: np.random.Generator, text: str) -> str:
    """Apply one keyboard slip: drop, swap or double a character."""
    if len(text) < 4:
        return text
    pos = int(rng.integers(1, len(text) - 1))
    op = int(rng.integers(0, 3))
    if op == 0:
        return text[:pos] + text[pos + 1:]
    if op == 1:
        return text[:pos] + text[pos + 1] + text[pos] + text[pos + 2:]
    return text[:pos] + text[pos] + text[pos:]


_TRANSLIT_SWAPS = [
    ("EI", "EY"), ("EY", "EI"), ("OU", "U"), ("U", "OU"), ("PH", "F"), ("F", "PH"), ("KS", "X"), ("X", "KS"),
    ("V", "W"), ("W", "V"), ("MM", "M"), ("SS", "S"), ("LL", "L"), ("I", "Y"), ("Y", "I"), ("O", "U"),
    ("E", "A"), ("K", "C"), ("EE", "I"), ("N", "NN"), ("S", "SS"), ("M", "MM"),
]


def translit_variant(rng: np.random.Generator, token: str) -> str:
    """Return a plausible alternative romanisation of a name token."""
    upper = token.upper()
    order = rng.permutation(len(_TRANSLIT_SWAPS))
    for index in order:
        src, dst = _TRANSLIT_SWAPS[int(index)]
        pos = upper.find(src, 1)
        if pos > 0:
            changed = upper[:pos] + dst + upper[pos + len(src):]
            return changed.title()
    return _typo(rng, upper).title()


def corp_name_variant(rng: np.random.Generator, name: str) -> str:
    """Rewrite a company name the way a different filer might type it."""
    if " " not in name:
        return name
    core, form = name.rsplit(" ", 1)
    roll = rng.random()
    if roll < 0.45:
        return name
    if roll < 0.7:
        swapped = {"LTD": "LIMITED", "LIMITED": "LTD"}.get(form, form)
        return f"{core} {swapped}"
    if roll < 0.85:
        return f"{core} {form}".title()
    if roll < 0.93:
        return core.title() + " Ltd."
    if roll < 0.97:
        return core
    return f"{_typo(rng, core)} {form}"


class RegistryGenerator:
    """Builds a Registry from a SynthConfig. Deterministic for a given seed."""

    def __init__(self, cfg: SynthConfig) -> None:
        self.cfg = cfg
        self.rng = np.random.default_rng(cfg.seed)
        self.n = int(cfg.n_companies)
        self.scale = self.n / 200_000
        self.size_scale = min(1.0, max(0.1, 5 * self.scale))
        y, m, d = (int(part) for part in cfg.snapshot_date.split("/"))
        self.snapshot = day(y, m, d)
        self._person_chunks: dict[str, list[np.ndarray]] = {k: [] for k in ("f1", "f2", "sur", "y", "m", "nat", "res", "occ")}
        self._n_persons = 0
        self._person_overrides: list[tuple[int, str, str, str, int, int]] = []
        self._officer_rows: list[dict[str, np.ndarray]] = []
        self._psc_rows: list[dict[str, np.ndarray]] = []
        self._oe_rows: list[dict[str, np.ndarray]] = []
        self._oo_rows: list[dict[str, np.ndarray]] = []
        self._oedge_rows: list[dict[str, np.ndarray]] = []
        self._next_oe = 81_000_000
        self._next_oo = 91_000_000
        self._sanctions: list[dict] = []
        self._sanction_truth: list[dict] = []
        self._sanction_reach: list[dict] = []
        self._leak_company_links: list[dict] = []
        self._address_truth: list[dict] = []
        self._person_truth: list[dict] = []
        self._used_offshore_names: set[int] = set()
        self._virtual_office: set[int] = set()

    # ================================================================== helpers
    def k(self, per_200k: float, minimum: int = 1) -> int:
        return max(minimum, int(round(per_200k * self.scale)))

    def size(self, value: float, minimum: int = 4) -> int:
        return max(minimum, int(round(value * self.size_scale)))

    def take(self, count: int) -> np.ndarray:
        """Reserve company slots for a planted block."""
        count = int(count)
        if self._cursor + count > len(self._reserve):
            raise ValueError("planted typologies exceed the number of companies; raise synth.n_companies")
        out = self._reserve[self._cursor: self._cursor + count]
        self._cursor += count
        self.special[out] = True
        return out

    def new_persons(self, count: int, overseas: float = 0.04, force_middle: bool = False) -> np.ndarray:
        rng = self.rng
        group = rng.choice(len(pools.FORENAMES), size=count, p=pools.NAME_GROUP_WEIGHTS)
        f1 = np.empty(count, dtype=object)
        f2 = np.empty(count, dtype=object)
        sur = np.empty(count, dtype=object)
        has_middle = np.ones(count, dtype=bool) if force_middle else rng.random(count) < 0.9
        for g in range(len(pools.FORENAMES)):
            mask = group == g
            size = int(mask.sum())
            if not size:
                continue
            fore = np.array(pools.FORENAMES[g], dtype=object)
            surn = np.array(pools.SURNAMES[g], dtype=object)
            # Middle names come from forenames and family names alike, as they do in
            # real registers, which keeps chance collisions of full names rare.
            middle_pool = np.concatenate([fore, surn])
            first = rng.integers(0, len(fore), size)
            f1[mask] = fore[first]
            f2[mask] = middle_pool[(first + 1 + rng.integers(0, len(middle_pool) - 1, size)) % len(middle_pool)]
            sur[mask] = surn[rng.integers(0, len(surn), size)]
        f2[~has_middle] = ""
        abroad = rng.random(count) < overseas
        res = np.array(pools.UK_RESIDENCE, dtype=object)[rng.choice(5, size=count, p=[0.62, 0.2, 0.09, 0.06, 0.03])]
        res[abroad] = np.array(pools.OVERSEAS_RESIDENCE, dtype=object)[rng.integers(0, len(pools.OVERSEAS_RESIDENCE), int(abroad.sum()))]
        chunk = {
            "f1": f1,
            "f2": f2,
            "sur": sur,
            "y": rng.integers(1942, 2004, count).astype(np.int16),
            "m": rng.integers(1, 13, count).astype(np.int8),
            "nat": np.array(pools.NATIONALITIES, dtype=object)[rng.choice(len(pools.NATIONALITIES), size=count, p=pools.NATIONALITY_WEIGHTS)],
            "res": res,
            "occ": np.array(pools.OCCUPATIONS, dtype=object)[rng.integers(0, len(pools.OCCUPATIONS), count)],
        }
        for key, values in chunk.items():
            self._person_chunks[key].append(values)
        ids = np.arange(self._n_persons, self._n_persons + count)
        self._n_persons += count
        return ids

    def person_attr(self, pid: int) -> dict:
        """Look up one person generated earlier (used by the planted blocks)."""
        offset = 0
        for index, chunk in enumerate(self._person_chunks["f1"]):
            if pid < offset + len(chunk):
                local = pid - offset
                return {key: self._person_chunks[key][index][local] for key in self._person_chunks}
            offset += len(chunk)
        raise KeyError(pid)

    def set_person(self, pid: int, **values) -> None:
        offset = 0
        for index, chunk in enumerate(self._person_chunks["f1"]):
            if pid < offset + len(chunk):
                for key, value in values.items():
                    self._person_chunks[key][index][pid - offset] = value
                return
            offset += len(chunk)
        raise KeyError(pid)

    def random_dates(self, lo: np.datetime64, hi: np.datetime64, count: int) -> np.ndarray:
        span = max(1, int((hi - lo).astype(int)))
        return lo + self.rng.integers(0, span, count).astype("timedelta64[D]")

    def add_officers(self, cidx, pid, role: str = "director", noise: float | None = None, resigned=None) -> None:
        cidx = np.atleast_1d(np.asarray(cidx))
        pid = np.broadcast_to(np.asarray(pid), cidx.shape).copy()
        count = len(cidx)
        if not count:
            return
        rate = self.cfg.background_name_noise if noise is None else noise
        delay = np.where(self.rng.random(count) < 0.8, 0, self.rng.integers(1, 900, count)).astype("timedelta64[D]")
        appointed = np.minimum(self.c_inc[cidx] + delay, self.snapshot)
        res = np.full(count, NAT) if resigned is None else resigned
        self._officer_rows.append(
            {
                "cidx": cidx.astype(np.int64),
                "pid": pid.astype(np.int64),
                "role": np.full(count, role, dtype=object),
                "appointed": appointed,
                "resigned": res,
                "noise": np.full(count, rate, dtype=np.float32),
            }
        )

    def add_second_directors(self, cidx, share: float = 0.3) -> None:
        """Give a share of companies an extra director, as background companies have."""
        cidx = np.atleast_1d(np.asarray(cidx))
        chosen = cidx[self.rng.random(len(cidx)) < share]
        if len(chosen):
            self.add_officers(chosen, self.new_persons(len(chosen)))

    def _psc_dates(self, cidx: np.ndarray) -> np.ndarray:
        return np.maximum(self.c_inc[cidx], PSC_REGIME_START)

    def add_psc_individual(self, cidx, pid, nature: str = "own_75_100") -> None:
        cidx = np.atleast_1d(np.asarray(cidx)).astype(np.int64)
        count = len(cidx)
        if not count:
            return
        pid = np.broadcast_to(np.asarray(pid), cidx.shape).astype(np.int64)
        text, band = pools.NATURES_OF_CONTROL[nature]
        self._psc_rows.append(
            {
                "cidx": cidx,
                "kind": np.full(count, "individual", dtype=object),
                "pid": pid,
                "name": np.full(count, "", dtype=object),
                "natures": np.full(count, text, dtype=object),
                "band": np.full(count, band, dtype=np.float32),
                "notified": self._psc_dates(cidx),
                "reg": np.full(count, "", dtype=object),
                "country": np.full(count, "", dtype=object),
                "form": np.full(count, "", dtype=object),
                "target": np.full(count, "", dtype=object),
            }
        )

    def add_psc_corporate(self, cidx, names, reg, country, form, targets, nature: str = "own_75_100") -> None:
        cidx = np.atleast_1d(np.asarray(cidx)).astype(np.int64)
        count = len(cidx)
        if not count:
            return
        text, band = pools.NATURES_OF_CONTROL[nature]

        def col(values):
            return np.broadcast_to(np.asarray(values, dtype=object), cidx.shape).copy()

        self._psc_rows.append(
            {
                "cidx": cidx,
                "kind": np.full(count, "corporate", dtype=object),
                "pid": np.full(count, -1, dtype=np.int64),
                "name": col(names),
                "natures": np.full(count, text, dtype=object),
                "band": np.full(count, band, dtype=np.float32),
                "notified": self._psc_dates(cidx),
                "reg": col(reg),
                "country": col(country),
                "form": col(form),
                "target": col(targets),
            }
        )

    def add_psc_statement(self, cidx) -> None:
        cidx = np.atleast_1d(np.asarray(cidx)).astype(np.int64)
        count = len(cidx)
        if not count:
            return
        self._psc_rows.append(
            {
                "cidx": cidx,
                "kind": np.full(count, "statement", dtype=object),
                "pid": np.full(count, -1, dtype=np.int64),
                "name": np.full(count, "No individual or entity with significant control", dtype=object),
                "natures": np.full(count, "", dtype=object),
                "band": np.full(count, 0.0, dtype=np.float32),
                "notified": self._psc_dates(cidx),
                "reg": np.full(count, "", dtype=object),
                "country": np.full(count, "", dtype=object),
                "form": np.full(count, "", dtype=object),
                "target": np.full(count, "", dtype=object),
            }
        )

    def add_uk_corporate_psc(self, child: np.ndarray, parent: np.ndarray, nature: str = "own_75_100") -> None:
        """Record that UK company parent controls UK company child."""
        child = np.atleast_1d(child)
        parent = np.broadcast_to(np.asarray(parent), child.shape)
        rng = self.rng
        names = np.array([corp_name_variant(rng, self.c_name[p]) for p in parent], dtype=object)
        numbers = self.c_number[parent].astype(object)
        roll = rng.random(len(child))
        reg = np.where(roll < 0.62, numbers, "")
        stripped = np.array([num.lstrip("0") for num in numbers], dtype=object)
        reg = np.where((roll >= 0.62) & (roll < 0.72), stripped, reg)
        country = np.array(["England", "United Kingdom", "England and Wales", "UK"], dtype=object)[rng.integers(0, 4, len(child))]
        targets = np.array(["C:" + num for num in numbers], dtype=object)
        self.add_psc_corporate(child, names, reg, country, "Private Limited Company", targets, nature)

    def new_offshore_entities(self, count: int, jurisdictions=None) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        rng = self.rng
        a, b = len(pools.NAME_WORDS_A), len(pools.NAME_WORDS_B)
        names = []
        while len(names) < count:
            code = int(rng.integers(0, a * a * b))
            if code in self._used_offshore_names:
                continue
            self._used_offshore_names.add(code)
            i, rest = divmod(code, a * b)
            j, kk = divmod(rest, b)
            if i == j:
                continue
            form = pools.OFFSHORE_FORMS[int(rng.integers(0, len(pools.OFFSHORE_FORMS)))]
            names.append(f"{pools.NAME_WORDS_A[i]} {pools.NAME_WORDS_A[j]} {pools.NAME_WORDS_B[kk]} {form}")
        names = np.array(names, dtype=object)
        if jurisdictions is None:
            weights = np.array([0.3, 0.1, 0.05, 0.05, 0.14, 0.06, 0.04, 0.03, 0.07, 0.06, 0.03, 0.03, 0.02, 0.02])
            jurisdictions = np.array(pools.SECRECY_JURISDICTIONS, dtype=object)[rng.choice(len(weights), size=count, p=weights / weights.sum())]
        ids = np.arange(self._next_oe, self._next_oe + count)
        self._next_oe += count
        self._oe_rows.append(
            {
                "node_id": ids,
                "name": names,
                "jurisdiction": np.asarray(jurisdictions, dtype=object),
                "inc": self.random_dates(day(1998, 1, 1), day(2024, 12, 31), count),
                "status": np.array(["Active", "Defaulted", "Struck off", "Dissolved"], dtype=object)[rng.choice(4, size=count, p=[0.55, 0.2, 0.15, 0.1])],
                "source": np.array(pools.LEAK_SOURCES, dtype=object)[rng.integers(0, len(pools.LEAK_SOURCES), count)],
            }
        )
        return ids, names, np.asarray(jurisdictions, dtype=object)

    def new_offshore_officers(self, names, kind: str, countries) -> np.ndarray:
        names = np.atleast_1d(np.asarray(names, dtype=object))
        count = len(names)
        ids = np.arange(self._next_oo, self._next_oo + count)
        self._next_oo += count
        self._oo_rows.append(
            {
                "node_id": ids,
                "name": names,
                "kind": np.full(count, kind, dtype=object),
                "country": np.broadcast_to(np.asarray(countries, dtype=object), names.shape).copy(),
            }
        )
        return ids

    def add_offshore_edges(self, start, end, link) -> None:
        start = np.atleast_1d(np.asarray(start)).astype(np.int64)
        end = np.broadcast_to(np.asarray(end), start.shape).astype(np.int64)
        self._oedge_rows.append(
            {"start": start, "end": end, "link": np.broadcast_to(np.asarray(link, dtype=object), start.shape).copy()}
        )

    def fresh_address(self) -> tuple[str, str, str]:
        rng = self.rng
        town, area = pools.TOWNS[int(rng.integers(0, len(pools.TOWNS)))]
        street = pools.STREET_NAMES[int(rng.integers(0, len(pools.STREET_NAMES)))]
        stype = pools.STREET_TYPES[int(rng.integers(0, len(pools.STREET_TYPES)))]
        number = int(rng.integers(1, 400))
        letters = "ABDEFGHJLNPQRSTUWXYZ"
        postcode = f"{area} {int(rng.integers(1, 10))}{letters[int(rng.integers(0, 20))]}{letters[int(rng.integers(0, 20))]}"
        return f"{number} {street} {stype}", town, postcode

    def set_address(self, cidx: np.ndarray, base: tuple[str, str, str], with_units: bool = True) -> None:
        """Place companies at one building, written in several different ways."""
        line, town, postcode = base
        rng = self.rng
        short = line.replace(" STREET", " ST").replace(" ROAD", " RD").replace(" AVENUE", " AVE")
        out = np.empty(len(cidx), dtype=object)
        style = rng.integers(0, 6, len(cidx)) if with_units else np.zeros(len(cidx), dtype=int)
        unit = rng.integers(1, 40, len(cidx))
        ordinal = np.array(["1st", "2nd", "3rd", "4th", "5th"], dtype=object)[rng.integers(0, 5, len(cidx))]
        for pos in range(len(cidx)):
            s = style[pos]
            if s == 0:
                out[pos] = line.title()
            elif s == 1:
                out[pos] = f"Suite {unit[pos]}, {line.title()}"
            elif s == 2:
                out[pos] = f"Office {unit[pos]} {short.title()}"
            elif s == 3:
                out[pos] = f"{line.title()}, Floor {1 + unit[pos] % 6}"
            elif s == 4:
                out[pos] = f"Unit {unit[pos]}, {short.title()}."
            else:
                out[pos] = f"{ordinal[pos]} Floor, {line.title()}"
        self.c_line[cidx] = out
        self.c_town[cidx] = town
        compact = rng.random(len(cidx)) < 0.15
        self.c_postcode[cidx] = np.where(compact, postcode.replace(" ", ""), postcode)

    # =============================================================== background
    def _background_companies(self) -> None:
        rng, n = self.rng, self.n
        self.c_number = np.char.zfill((rng.choice(15_000_000, size=n, replace=False) + 1_000_000).astype(str), 8)
        a, b, s = len(pools.NAME_WORDS_A), len(pools.NAME_WORDS_B), len(pools.NAME_SECTORS)
        base = a * b * s
        with_qualifier = n > 0.6 * base
        space = base * 5 if with_qualifier else base
        codes = rng.choice(space, size=n, replace=False)
        qual = codes // base
        rest = codes % base
        ia, rest = rest // (b * s), rest % (b * s)
        ib, isec = rest // s, rest % s
        words_a = np.array(pools.NAME_WORDS_A, dtype=object)
        words_b = np.array(pools.NAME_WORDS_B, dtype=object)
        sectors = np.array(pools.NAME_SECTORS, dtype=object)
        qualifiers = np.array(["", " (UK)", " EUROPE", " NORTH", " SOUTH"], dtype=object)
        form_roll = rng.random(n)
        form = np.where(form_roll < 0.55, "LTD", np.where(form_roll < 0.98, "LIMITED", "LLP")).astype(object)
        self.c_stem = words_a[ia] + " " + words_b[ib]
        self.c_name = self.c_stem + " " + sectors[isec] + qualifiers[qual] + " " + form
        self.c_category = np.where(form == "LLP", "Limited Liability Partnership", "Private Limited Company").astype(object)

        years = np.arange(1995, 2027)
        weights = np.exp(0.11 * (years - 1995))
        year = rng.choice(years, size=n, p=weights / weights.sum())
        inc = np.array([day(int(y), 1, 1) for y in years])[year - 1995] + rng.integers(0, 365, n).astype("timedelta64[D]")
        self.c_inc = np.minimum(inc, self.snapshot - np.timedelta64(20, "D"))
        life = np.clip(rng.lognormal(np.log(1500), 0.7, n), 330, None).astype(int).astype("timedelta64[D]")
        diss = self.c_inc + life
        dissolved = (rng.random(n) < 0.42) & (diss < self.snapshot)
        self.c_diss = np.where(dissolved, diss, NAT)
        status = np.where(dissolved, "Dissolved", "Active").astype(object)
        liquid = (~dissolved) & (rng.random(n) < 0.03)
        status[liquid] = "Liquidation"
        self.c_status = status
        self.c_accounts = np.full(n, "", dtype=object)
        self.c_overdue = np.zeros(n, dtype=bool)
        self._refresh_accounts(np.arange(n))
        self.c_sic = rng.integers(0, len(pools.SIC_CODES), n)

        n_addr = max(10, int(0.8 * n))
        town_idx = rng.integers(0, len(pools.TOWNS), n_addr)
        towns = np.array([t for t, _ in pools.TOWNS], dtype=object)[town_idx]
        areas = np.array([p for _, p in pools.TOWNS], dtype=object)[town_idx]
        streets = np.array(pools.STREET_NAMES, dtype=object)[rng.integers(0, len(pools.STREET_NAMES), n_addr)]
        stypes = np.array(pools.STREET_TYPES, dtype=object)[rng.integers(0, len(pools.STREET_TYPES), n_addr)]
        letters = np.array(list("ABDEFGHJLNPQRSTUWXYZ"), dtype=object)
        lines = rng.integers(1, 400, n_addr).astype(str).astype(object) + " " + np.char.title(streets.astype(str)).astype(object) + " " + np.char.title(stypes.astype(str)).astype(object)
        postcodes = areas + " " + rng.integers(1, 10, n_addr).astype(str).astype(object) + letters[rng.integers(0, 20, n_addr)] + letters[rng.integers(0, 20, n_addr)]
        own = rng.random(n) < 0.72
        shared_pool = max(5, int(0.03 * n_addr))
        zipf = 1.0 / np.arange(1, shared_pool + 1) ** 0.75
        shared = rng.choice(shared_pool, size=n, p=zipf / zipf.sum())
        addr = np.where(own, shared_pool + rng.integers(0, n_addr - shared_pool, n), shared)
        self.c_line = lines[addr]
        self.c_town = towns[addr]
        self.c_postcode = postcodes[addr]

    def _refresh_accounts(self, idx: np.ndarray, healthy_only: bool = False) -> None:
        """Assign an accounts category consistent with the age of each company."""
        rng = self.rng
        end = np.where(np.isnat(self.c_diss[idx]), self.snapshot, self.c_diss[idx])
        age = (end - self.c_inc[idx]).astype(int)
        cats = np.array(["MICRO ENTITY", "TOTAL EXEMPTION FULL", "DORMANT", "SMALL", "UNAUDITED ABRIDGED", "FULL", "GROUP"], dtype=object)
        probs = [0.46, 0.27, 0.12, 0.07, 0.04, 0.025, 0.015]
        if healthy_only:
            cats = np.array(["TOTAL EXEMPTION FULL", "SMALL", "FULL", "GROUP", "MICRO ENTITY"], dtype=object)
            probs = [0.35, 0.3, 0.15, 0.1, 0.1]
        chosen = cats[rng.choice(len(cats), size=len(idx), p=probs)]
        self.c_accounts[idx] = np.where(age < 640, "NO ACCOUNTS FILED", chosen)
        self.c_overdue[idx] = (self.c_status[idx] == "Active") & (age >= 640) & (rng.random(len(idx)) < 0.03)

    def _shell_profile(self, idx: np.ndarray, short_p: float = 0.7, inc=None) -> None:
        """Give companies the look of disposable shells."""
        rng = self.rng
        count = len(idx)
        if inc is None:
            inc = self.random_dates(day(2019, 1, 1), self.snapshot - np.timedelta64(60, "D"), count)
        self.c_inc[idx] = inc
        diss = inc + rng.integers(300, 720, count).astype("timedelta64[D]")
        short = (rng.random(count) < short_p) & (diss < self.snapshot)
        self.c_diss[idx] = np.where(short, diss, NAT)
        self.c_status[idx] = np.where(short, "Dissolved", "Active")
        end = np.where(short, diss, self.snapshot)
        age = (end - inc).astype(int)
        roll = rng.random(count)
        late = np.where(roll < 0.5, "DORMANT", np.where(roll < 0.75, "MICRO ENTITY", "NO ACCOUNTS FILED")).astype(object)
        self.c_accounts[idx] = np.where(short | (age < 640), "NO ACCOUNTS FILED", late)
        self.c_overdue[idx] = (~short) & (age >= 640) & (self.c_accounts[idx] == "NO ACCOUNTS FILED")
        shell_sic = [i for i, (code, _) in enumerate(pools.SIC_CODES) if code in pools.SHELL_SIC_CODES]
        self.c_sic[idx] = np.array(shell_sic)[rng.integers(0, len(shell_sic), count)]

    # ================================================================== planted
    def _attach_opaque(self, idx: np.ndarray, label: bool = True) -> None:
        """Give companies an offshore corporate controller with no declared person."""
        rng = self.rng
        count = len(idx)
        if not count:
            return
        n_entities = max(1, int(np.ceil(count / 2)))
        owner = rng.integers(0, n_entities, count)
        in_leak = rng.random(n_entities) < 0.55
        ids, names, jurs = self.new_offshore_entities(int(in_leak.sum()))
        stub_count = int((~in_leak).sum())
        a, b = len(pools.NAME_WORDS_A), len(pools.NAME_WORDS_B)
        stub_names = np.array(
            [
                f"{pools.NAME_WORDS_A[int(rng.integers(0, a))]} {pools.NAME_WORDS_B[int(rng.integers(0, b))]} "
                f"{pools.NAME_SECTORS[int(rng.integers(0, len(pools.NAME_SECTORS)))]} OVERSEAS {pools.OFFSHORE_FORMS[int(rng.integers(0, 5))]}"
                for _ in range(stub_count)
            ],
            dtype=object,
        )
        stub_jurs = np.array(pools.SECRECY_JURISDICTIONS, dtype=object)[rng.integers(0, 10, stub_count)]
        ent_name = np.empty(n_entities, dtype=object)
        ent_jur = np.empty(n_entities, dtype=object)
        ent_target = np.empty(n_entities, dtype=object)
        ent_name[in_leak], ent_jur[in_leak] = names, jurs
        ent_target[in_leak] = np.array([f"O:{i}" for i in ids], dtype=object)
        ent_name[~in_leak], ent_jur[~in_leak] = stub_names, stub_jurs
        ent_target[~in_leak] = np.array([f"F:{nm}|{jr}" for nm, jr in zip(stub_names, stub_jurs)], dtype=object)

        # Hidden controllers that only the leak data reveals.
        for ent_id in ids[rng.random(len(ids)) < 0.5]:
            n_off = int(rng.integers(1, 3))
            pids = self.new_persons(n_off, overseas=0.8)
            person_names = [self._natural_name(self.person_attr(int(p))) for p in pids]
            countries = [self.person_attr(int(p))["res"] for p in pids]
            oo = self.new_offshore_officers(person_names, "person", countries)
            self.add_offshore_edges(oo, ent_id, np.array(pools.LEAK_LINKS, dtype=object)[rng.integers(0, 3, n_off)])
        parents = ids[rng.random(len(ids)) < 0.25]
        if len(parents):
            parent_ids, _, _ = self.new_offshore_entities(len(parents))
            self.add_offshore_edges(parent_ids, parents, "shareholder of")

        variants = np.array(
            [
                pools.JURISDICTION_VARIANTS.get(j, [j])[int(rng.integers(0, len(pools.JURISDICTION_VARIANTS.get(j, [j]))))]
                for j in ent_jur[owner]
            ],
            dtype=object,
        )
        psc_names = np.array([nm if rng.random() < 0.6 else nm.title() for nm in ent_name[owner]], dtype=object)
        reg = rng.integers(100_000, 9_999_999, count).astype(str).astype(object)
        form = np.array(["International Business Company", "Limited Company", "Company Limited by Shares"], dtype=object)[rng.integers(0, 3, count)]
        self.add_psc_corporate(idx, psc_names, reg, variants, form, ent_target[owner])
        if label:
            self.y["opaque"][idx] = True

    @staticmethod
    def _natural_name(attr: dict) -> str:
        middle = f" {attr['f2']}" if attr["f2"] else ""
        return f"{attr['f1']}{middle} {attr['sur']}"

    def _shell_pscs(self, idx: np.ndarray, directors: np.ndarray, mix=(0.45, 0.25, 0.3)) -> None:
        roll = self.rng.random(len(idx))
        ind = roll < mix[0]
        stmt = (roll >= mix[0]) & (roll < mix[0] + mix[1])
        opaque = ~(ind | stmt)
        self.add_psc_individual(idx[ind], directors[ind])
        self.add_psc_statement(idx[stmt])
        self._attach_opaque(idx[opaque])

    def _plant_factories_and_nominees(self) -> None:
        cfg, rng = self.cfg, self.rng
        n_factories = self.k(cfg.n_factories, 3)
        factory_free: list[list[int]] = []
        for f in range(n_factories):
            m = self.size(rng.integers(cfg.factory_min_companies, cfg.factory_max_companies + 1), 30)
            idx = self.take(m)
            base = self.fresh_address()
            self.set_address(idx, base)
            n_bursts = max(2, m // 60)
            centres = self.random_dates(day(2019, 6, 1), self.snapshot - np.timedelta64(200, "D"), n_bursts)
            inc = centres[rng.integers(0, n_bursts, m)] + rng.integers(0, 12, m).astype("timedelta64[D]")
            self._shell_profile(idx, short_p=float(rng.uniform(0.5, 0.85)), inc=inc)
            self.y["address_factory"][idx] = True
            self.group[idx] = f"FACTORY{f:03d}"
            self._address_truth.append({"address_line1": base[0], "post_town": base[1], "postcode": base[2], "kind": "factory", "n_companies": m})
            factory_free.append(list(idx))

        n_nominees = self.k(cfg.n_nominees, 3)
        nominee_ids = self.new_persons(n_nominees, overseas=0.6)
        for j, pid in enumerate(nominee_ids):
            quota = self.size(rng.integers(cfg.nominee_min_companies, cfg.nominee_max_companies + 1), 14)
            affiliated = rng.random() < 0.6
            idx_parts = []
            if affiliated:
                order = rng.permutation(n_factories)
                for f in order:
                    free = factory_free[int(f)]
                    grab = min(quota - sum(len(p) for p in idx_parts), len(free) // 2)
                    if grab > 0:
                        idx_parts.append(np.array([free.pop() for _ in range(grab)]))
                    if sum(len(p) for p in idx_parts) >= quota:
                        break
            missing = quota - sum(len(p) for p in idx_parts)
            if missing > 0:
                own = self.take(missing)
                self._shell_profile(own, short_p=0.6)
                n_addr = int(np.ceil(missing / 32))
                bases = [self.fresh_address() for _ in range(n_addr)]
                which = rng.integers(0, n_addr, missing)
                for a_index, base in enumerate(bases):
                    self.set_address(own[which == a_index], base)
                idx_parts.append(own)
            idx = np.concatenate(idx_parts)
            self.add_officers(idx, pid, noise=cfg.nominee_name_noise)
            self.add_second_directors(idx, 0.12)
            self._shell_pscs(idx, np.full(len(idx), pid), mix=(0.3, 0.3, 0.4))
            self.y["nominee"][idx] = True
            self.group[idx] = np.where(self.group[idx] == "", f"NOMINEE{j:03d}", self.group[idx])
            self._person_truth.append({"true_person_id": int(pid), "kind": "nominee", "n_companies": int(len(idx))})

        for free in factory_free:
            idx = np.array(free, dtype=np.int64)
            if not len(idx):
                continue
            n_fronts = max(1, len(idx) // 3)
            fronts = self.new_persons(n_fronts, overseas=0.75)
            directors = fronts[rng.integers(0, n_fronts, len(idx))]
            self.add_officers(idx, directors)
            self.add_second_directors(idx, 0.15)
            self._shell_pscs(idx, directors)

    def _plant_rings(self) -> None:
        cfg, rng = self.cfg, self.rng
        n_rings = self.k(cfg.n_rings, 6)
        for r in range(n_rings):
            length = int(rng.choice([2, 3, 4, 5, 6], p=[0.25, 0.32, 0.22, 0.13, 0.08]))
            idx = self.take(length)
            director = self.new_persons(1, overseas=0.3)[0]
            self.add_officers(idx, director)
            self.add_second_directors(idx)
            offshore_at = int(rng.integers(0, length)) if rng.random() < cfg.ring_offshore_share else -1
            for pos in range(length):
                child, parent = idx[pos], idx[(pos + 1) % length]
                if pos == offshore_at:
                    ent_ids, ent_names, ent_jurs = self.new_offshore_entities(1)
                    self.add_psc_corporate(
                        [child], ent_names[0], str(int(rng.integers(100_000, 999_999))), ent_jurs[0],
                        "International Business Company", f"O:{ent_ids[0]}",
                    )
                    oo = self.new_offshore_officers([corp_name_variant(rng, self.c_name[parent])], "company", "United Kingdom")
                    self.add_offshore_edges(oo, ent_ids[0], "shareholder of")
                    self._leak_company_links.append({"node_id": int(oo[0]), "company_number": self.c_number[parent]})
                else:
                    self.add_uk_corporate_psc(np.array([child]), np.array([parent]))
            self.y["circular"][idx] = True
            if offshore_at >= 0:
                self.y["opaque"][idx] = True
            self.group[idx] = f"RING{r:04d}"
            self.ring_length[idx] = length

    def _chain_down(self, top: int, depth: int) -> list[int]:
        """Create a chain of UK subsidiaries below company top."""
        chain = []
        parent = top
        for _ in range(depth):
            child = int(self.take(1)[0])
            self.add_officers([child], self.new_persons(1)[0])
            self.add_second_directors([child])
            self.add_uk_corporate_psc(np.array([child]), np.array([parent]))
            chain.append(child)
            parent = child
        return chain

    def _sanction_entry(self, schema: str, primary: str, aliases: list[str], year: int, month: int, linked: bool, kind: str, key: str) -> str:
        rng = self.rng
        entity_id = f"SAN{len(self._sanctions):06d}"
        roll = rng.random()
        listed = self.random_dates(day(2014, 1, 1), self.snapshot - np.timedelta64(30, "D"), 1)[0]
        self._sanctions.append(
            {
                "entity_id": entity_id,
                "schema": schema,
                "name": primary,
                "aliases": "; ".join(aliases),
                "birth_year": int(year) if schema == "Person" and roll < 0.95 else 0,
                "birth_month": int(month) if schema == "Person" and roll < 0.8 else 0,
                "regime": pools.SANCTIONS_REGIMES[int(rng.integers(0, len(pools.SANCTIONS_REGIMES)))],
                "listed_on": listed,
            }
        )
        self._sanction_truth.append({"entity_id": entity_id, "linked": linked, "link_kind": kind, "registry_key": key})
        return entity_id

    def _person_listing(self, attr: dict) -> tuple[str, list[str]]:
        """Primary list name and aliases for a person whose registry spelling is attr."""
        rng = self.rng
        f1, f2, sur = attr["f1"], attr["f2"], attr["sur"]
        middle = f" {f2}" if f2 else ""
        registry = f"{f1}{middle} {sur}"
        alt_sur = translit_variant(rng, sur)
        alt_f1 = translit_variant(rng, f1)
        candidates = [f"{f1}{middle} {alt_sur}", f"{alt_f1}{middle} {sur}", f"{alt_sur.upper()} {f1}{middle}", f"{alt_f1}{middle} {alt_sur}"]
        roll = rng.random()
        if roll < 0.3:
            return registry, candidates[:2]
        if roll < 0.75:
            return candidates[0], [registry, candidates[1]]
        return candidates[3], [candidates[0]] if rng.random() < 0.5 else [candidates[2]]

    def _record_reach(self, entity_id: str, companies: list[int], first_hop: int) -> None:
        for offset, cidx in enumerate(companies):
            hops = first_hop + offset
            self.y["sanctions"][cidx] = True
            self.hops[cidx] = hops if self.hops[cidx] == 0 else min(self.hops[cidx], hops)
            self._sanction_reach.append({"entity_id": entity_id, "company_number": self.c_number[cidx], "hops": hops})
        self.group[np.array(companies)] = f"SANCTION{entity_id[3:]}"

    def _plant_sanctions(self) -> None:
        cfg, rng = self.cfg, self.rng
        n_linked = self.k(cfg.n_sanctions_linked, 8)
        for _ in range(n_linked):
            roll = rng.random()
            depth = int(rng.choice([0, 1, 2], p=[0.5, 0.3, 0.2]))
            if roll < 0.35:
                pid = int(self.new_persons(1, overseas=0.7, force_middle=True)[0])
                attr = self.person_attr(pid)
                primary, aliases = self._person_listing(attr)
                entity_id = self._sanction_entry("Person", primary, aliases, attr["y"], attr["m"], True, "registry_person", f"P:{pid}")
                top = int(self.take(1)[0])
                as_director = rng.random() < 0.5
                if as_director:
                    self.add_officers([top], pid)
                else:
                    self.add_officers([top], self.new_persons(1)[0])
                if (not as_director) or rng.random() < 0.6:
                    self.add_psc_individual([top], pid)
                else:
                    self.add_psc_statement([top])
                self._record_reach(entity_id, [top] + self._chain_down(top, depth), 1)
            elif roll < 0.8:
                pid = int(self.new_persons(1, overseas=0.9, force_middle=True)[0])
                attr = self.person_attr(pid)
                primary, aliases = self._person_listing(attr)
                ent_ids, ent_names, ent_jurs = self.new_offshore_entities(1)
                oo = self.new_offshore_officers([self._natural_name(attr)], "person", attr["res"])
                self.add_offshore_edges(oo, ent_ids[0], pools.LEAK_LINKS[int(rng.integers(0, 3))])
                entity_id = self._sanction_entry("Person", primary, aliases, attr["y"], attr["m"], True, "leak_officer", f"LO:{int(oo[0])}")
                top = int(self.take(1)[0])
                self.add_officers([top], self.new_persons(1, overseas=0.5)[0])
                self.add_psc_corporate([top], ent_names[0], str(int(rng.integers(100_000, 999_999))), ent_jurs[0], "International Business Company", f"O:{ent_ids[0]}")
                chain = [top] + self._chain_down(top, depth)
                self.y["opaque"][np.array(chain)] = True
                self._record_reach(entity_id, chain, 2)
            else:
                ent_ids, ent_names, ent_jurs = self.new_offshore_entities(1)
                core = ent_names[0].rsplit(" ", 1)[0]
                aliases = [core.title(), f"{core} CO"] if rng.random() < 0.7 else []
                entity_id = self._sanction_entry("Company", ent_names[0], aliases, 0, 0, True, "offshore_entity", f"O:{ent_ids[0]}")
                top = int(self.take(1)[0])
                self.add_officers([top], self.new_persons(1, overseas=0.5)[0])
                self.add_psc_corporate([top], corp_name_variant(rng, ent_names[0]), "", ent_jurs[0], "Limited Company", f"O:{ent_ids[0]}")
                chain = [top] + self._chain_down(top, depth)
                self.y["opaque"][np.array(chain)] = True
                self._record_reach(entity_id, chain, 1)

    def _plant_opaque(self) -> None:
        idx = self.take(self.k(self.cfg.n_opaque_chains, 10))
        n_dir = max(1, len(idx) // 2)
        directors = self.new_persons(n_dir, overseas=0.55)[self.rng.integers(0, n_dir, len(idx))]
        self.add_officers(idx, directors)
        self.add_second_directors(idx)
        self._attach_opaque(idx)
        self.group[idx] = "OPAQUE"

    def _plant_benign_foreign_parents(self) -> None:
        rng = self.rng
        total = self.k(self.cfg.n_benign_foreign_parents, 6)
        idx = self.take(total)
        n_parents = max(1, int(total / 2.5))
        parent_of = rng.integers(0, n_parents, total)
        a, b = len(pools.NAME_WORDS_A), len(pools.NAME_WORDS_B)
        names, countries = [], []
        for _ in range(n_parents):
            country, form = pools.LOW_OPACITY_PARENTS[int(rng.integers(0, len(pools.LOW_OPACITY_PARENTS)))]
            names.append(f"{pools.NAME_WORDS_A[int(rng.integers(0, a))]} {pools.NAME_WORDS_B[int(rng.integers(0, b))]} WORLDWIDE {form}")
            countries.append(country)
        names, countries = np.array(names, dtype=object), np.array(countries, dtype=object)
        self.c_status[idx] = "Active"
        self.c_diss[idx] = NAT
        self._refresh_accounts(idx, healthy_only=True)
        for _ in range(2):
            self.add_officers(idx, self.new_persons(total, overseas=0.05))
        targets = np.array([f"F:{nm}|{ct}" for nm, ct in zip(names[parent_of], countries[parent_of])], dtype=object)
        self.add_psc_corporate(idx, names[parent_of], rng.integers(10_000, 999_999, total).astype(str).astype(object), countries[parent_of], "Listed Corporation", targets)
        self.negative[idx] = "foreign_parent"

    def _batch_names(self, count: int) -> np.ndarray:
        rng = self.rng
        stem = f"{pools.NAME_WORDS_A[int(rng.integers(0, len(pools.NAME_WORDS_A)))]} {pools.NAME_WORDS_B[int(rng.integers(0, len(pools.NAME_WORDS_B)))]}"
        sectors = rng.permutation(len(pools.NAME_SECTORS))[:count]
        return np.array([f"{stem} {pools.NAME_SECTORS[int(s)]} {int(rng.integers(100, 999))} LTD" for s in sectors], dtype=object)

    def _plant_bursts_and_phoenix(self) -> None:
        cfg, rng = self.cfg, self.rng
        for b in range(self.k(cfg.n_burst_batches, 4)):
            size = int(rng.integers(6, 21))
            idx = self.take(size)
            inc = self.random_dates(day(2019, 1, 1), self.snapshot - np.timedelta64(700, "D"), 1)[0]
            self._shell_profile(idx, short_p=0.95, inc=np.full(size, inc) + rng.integers(0, 3, size).astype("timedelta64[D]"))
            self.set_address(idx, self.fresh_address())
            self.c_name[idx] = self._batch_names(size)
            director = self.new_persons(1, overseas=0.4)[0]
            self.add_officers(idx, director)
            self.add_psc_individual(idx, director)
            self.y["phoenix_burst"][idx] = True
            self.group[idx] = f"BURST{b:04d}"

        for b in range(self.k(cfg.n_benign_spv_batches, 3)):
            size = int(rng.integers(6, 21))
            idx = self.take(size)
            inc = self.random_dates(day(2012, 1, 1), day(2022, 12, 31), 1)[0]
            self.c_inc[idx] = np.full(size, inc) + rng.integers(0, 3, size).astype("timedelta64[D]")
            self.c_status[idx] = "Active"
            self.c_diss[idx] = NAT
            self._refresh_accounts(idx, healthy_only=True)
            self.set_address(idx, self.fresh_address(), with_units=False)
            self.c_name[idx] = self._batch_names(size)
            directors = self.new_persons(2, overseas=0.0)
            self.add_officers(idx, directors[0])
            self.add_officers(idx, directors[1])
            self.add_psc_individual(idx, directors[0])
            self.negative[idx] = "spv_batch"

        suffixes = [" (UK)", " TRADING", " 2", " GROUP", " SERVICES"]
        for p in range(self.k(cfg.n_phoenix_chains, 4)):
            length = int(rng.choice([2, 3, 4], p=[0.5, 0.35, 0.15]))
            idx = self.take(length)
            director = self.new_persons(1, overseas=0.1)[0]
            base = self.fresh_address()
            self.set_address(idx, base, with_units=False)
            core = self.c_name[idx[0]].rsplit(" ", 1)[0]
            start = self.random_dates(day(2017, 1, 1), self.snapshot - np.timedelta64(int(650 * length + 200), "D"), 1)[0]
            for pos, cidx in enumerate(idx):
                self.c_inc[cidx] = start
                life = np.timedelta64(int(rng.integers(330, 640)), "D")
                last = pos == length - 1
                if last and rng.random() < 0.5:
                    self.c_status[cidx], self.c_diss[cidx] = "Active", NAT
                else:
                    self.c_status[cidx], self.c_diss[cidx] = "Dissolved", start + life
                self.c_accounts[cidx] = "NO ACCOUNTS FILED" if rng.random() < 0.8 else "MICRO ENTITY"
                self.c_overdue[cidx] = False
                if pos == 0:
                    self.c_name[cidx] = f"{core} LTD"
                else:
                    form = "LIMITED" if rng.random() < 0.5 else "LTD"
                    self.c_name[cidx] = f"{core}{suffixes[(pos - 1 + p) % len(suffixes)]} {form}"
                start = start + life + np.timedelta64(int(rng.integers(5, 60)), "D")
            self.add_officers(idx, director)
            self.add_second_directors(idx)
            self.add_psc_individual(idx, director)
            self.y["phoenix_burst"][idx] = True
            self.group[idx] = f"PHOENIX{p:04d}"

    # ========================================================== background links
    def _background_people(self) -> None:
        cfg, rng = self.cfg, self.rng
        bg = np.flatnonzero(~self.special)
        n_bg = len(bg)
        pool = self.new_persons(max(50, int(0.85 * n_bg)))
        weights = rng.lognormal(0.0, 0.75, len(pool))
        weights /= weights.sum()
        first = pool[rng.choice(len(pool), size=n_bg, p=weights)]
        self.add_officers(bg, first)
        second_mask = rng.random(n_bg) < 0.3
        second = pool[rng.choice(len(pool), size=n_bg, p=weights)]
        second_mask &= second != first
        self.add_officers(bg[second_mask], second[second_mask])
        third_mask = rng.random(n_bg) < 0.07
        third = pool[rng.choice(len(pool), size=n_bg, p=weights)]
        third_mask &= (third != first) & (third != second)
        self.add_officers(bg[third_mask], third[third_mask])
        sec_mask = rng.random(n_bg) < 0.18
        self.add_officers(bg[sec_mask], pool[rng.choice(len(pool), size=int(sec_mask.sum()), p=weights)], role="secretary")

        has_psc = np.isnat(self.c_diss[bg]) | (self.c_diss[bg] >= PSC_REGIME_START)
        roll = rng.random(n_bg)
        is_holding = rng.random(n_bg) < 0.02
        holdings = bg[is_holding & has_psc]
        sub_mask = (roll >= 0.9) & (roll < 0.95) & ~is_holding & has_psc
        if len(holdings) >= 2:
            subs = bg[sub_mask]
            self.add_uk_corporate_psc(subs, holdings[rng.integers(0, len(holdings), len(subs))])
            self.negative[subs] = "group_tree"
            nested = np.flatnonzero(rng.random(len(holdings)) < 0.3)
            nested = nested[nested > 0]
            if len(nested):
                parents = holdings[(rng.random(len(nested)) * nested).astype(int)]
                self.add_uk_corporate_psc(holdings[nested], parents)
                self.negative[holdings[nested]] = "group_tree"
                nested_set = np.zeros(self.n, dtype=bool)
                nested_set[holdings[nested]] = True
            else:
                nested_set = np.zeros(self.n, dtype=bool)
        else:
            sub_mask[:] = False
            nested_set = np.zeros(self.n, dtype=bool)
        own_psc = has_psc & ~sub_mask & ~nested_set[bg]
        single = own_psc & (roll < 0.86)
        double = own_psc & (roll >= 0.86) & (roll < 0.9)
        stmt = own_psc & ~single & ~double
        self.add_psc_individual(bg[single], first[single])
        partner = np.where(second_mask, second, pool[rng.choice(len(pool), size=n_bg, p=weights)])
        double &= partner != first
        self.add_psc_individual(bg[double], first[double], "own_25_50")
        self.add_psc_individual(bg[double], partner[double], "own_25_50")
        self.add_psc_statement(bg[stmt & (rng.random(n_bg) < 0.8)])

        # Professional directors: many appointments, but in healthy companies.
        healthy = bg[(self.c_status[bg] == "Active") & (self.c_accounts[bg] != "NO ACCOUNTS FILED") & (self.c_accounts[bg] != "DORMANT")]
        for pid in self.new_persons(self.k(cfg.n_professional_directors, 4), overseas=0.0):
            count = min(len(healthy), self.size(rng.integers(15, 121), 12))
            chosen = rng.choice(healthy, size=count, replace=False)
            self.add_officers(chosen, pid, noise=0.05)
            self.negative[chosen] = np.where(self.negative[chosen] == "", "professional_director", self.negative[chosen])
            self._person_truth.append({"true_person_id": int(pid), "kind": "professional", "n_companies": int(count)})

        # Legitimate formation agents and accountants: crowded but healthy addresses.
        free = bg[self.negative[bg] == ""]
        cursor = 0
        order = rng.permutation(len(free))
        for _ in range(self.k(cfg.n_benign_agents, 3)):
            count = self.size(rng.integers(cfg.factory_min_companies, cfg.factory_max_companies + 1), 30)
            chosen = free[order[cursor: cursor + count]]
            cursor += count
            if not len(chosen):
                break
            base = self.fresh_address()
            self.set_address(chosen, base)
            self.negative[chosen] = "benign_agent"
            kind = "benign_agent"
            if rng.random() < 0.4:
                # A virtual office with an international client base: many
                # overseas directors, but the companies are real and file accounts.
                kind = "virtual_office"
                abroad = chosen[rng.random(len(chosen)) < 0.55]
                self.add_officers(abroad, self.new_persons(len(abroad), overseas=1.0))
                self._virtual_office.update(int(c) for c in abroad)
            self._address_truth.append({"address_line1": base[0], "post_town": base[1], "postcode": base[2], "kind": kind, "n_companies": int(len(chosen))})

        self._bg_first_directors = first
        self._bg_companies = bg

    def _plant_namesakes(self) -> None:
        """Give innocent directors the same name as a listed person."""
        rng = self.rng
        persons = [row for row in self._sanctions if row["schema"] == "Person" and row["birth_year"]]
        if not persons:
            return
        appointments = np.bincount(self._bg_first_directors, minlength=self._n_persons)
        single = np.flatnonzero(appointments[self._bg_first_directors] == 1)
        count = min(self.k(self.cfg.n_namesakes, 6), len(single))
        chosen = rng.choice(single, size=count, replace=False)
        for position in chosen:
            entry = persons[int(rng.integers(0, len(persons)))]
            tokens = entry["name"].split()
            if len(tokens) < 2:
                continue
            if tokens[0].isupper():
                tokens = [t.title() for t in tokens[1:] + tokens[:1]]
            pid = int(self._bg_first_directors[position])
            roll = rng.random()
            if roll < 0.92:
                shift = int(rng.integers(4, 16)) * (1 if rng.random() < 0.5 else -1)
                year, month = int(np.clip(entry["birth_year"] + shift, 1940, 2004)), int(rng.integers(1, 13))
                if abs(year - entry["birth_year"]) < 3:
                    year = entry["birth_year"] - 6
            elif roll < 0.98:
                year = entry["birth_year"]
                month = (entry["birth_month"] % 12) + 1 if entry["birth_month"] else int(rng.integers(1, 13))
            else:
                year, month = entry["birth_year"], entry["birth_month"] or int(rng.integers(1, 13))
            middle = " ".join(tokens[1:-1])
            self.set_person(pid, f1=tokens[0], f2=middle, sur=tokens[-1], y=year, m=month)
            cidx = self._bg_companies[position]
            if self.negative[cidx] == "":
                self.negative[cidx] = "namesake"

    def _background_offshore(self) -> None:
        rng = self.rng
        count = max(20, int(self.cfg.offshore_entity_ratio * self.n))
        ids, _, _ = self.new_offshore_entities(count)
        n_people = int(count * 1.1)
        pids = self.new_persons(n_people, overseas=0.7)
        chunk = {key: self._person_chunks[key][-1] for key in ("f1", "f2", "sur", "res")}
        middle = np.where(chunk["f2"] == "", "", " " + chunk["f2"])
        names = chunk["f1"] + middle + " " + chunk["sur"]
        officers = self.new_offshore_officers(names, "person", chunk["res"])
        self.add_offshore_edges(officers, ids[rng.integers(0, count, n_people)], np.array(pools.LEAK_LINKS, dtype=object)[rng.integers(0, len(pools.LEAK_LINKS), n_people)])
        n_corp = int(count * 0.2)
        corp_ids, corp_names, corp_jurs = self.new_offshore_entities(n_corp)
        self.add_offshore_edges(corp_ids, ids[rng.integers(0, count, n_corp)], "shareholder of")
        del pids

    def _filler_sanctions(self) -> None:
        rng = self.rng
        target = self.k(self.cfg.n_sanctions_entries, 30)
        missing = max(0, target - len(self._sanctions))
        n_person = int(missing * 0.7)
        pids = self.new_persons(n_person, overseas=1.0, force_middle=True)
        for pid in pids:
            attr = self.person_attr(int(pid))
            primary, aliases = self._person_listing(attr)
            self._sanction_entry("Person", primary, aliases, attr["y"], attr["m"], False, "none", "")
        a, b = len(pools.NAME_WORDS_A), len(pools.NAME_WORDS_B)
        for _ in range(missing - n_person):
            name = f"{pools.NAME_WORDS_B[int(rng.integers(0, b))]} {pools.NAME_WORDS_A[int(rng.integers(0, a))]} {pools.NAME_WORDS_A[int(rng.integers(0, a))]} STATE CORPORATION"
            self._sanction_entry("Company", name, [name.title()[:-12].strip()] if rng.random() < 0.4 else [], 0, 0, False, "none", "")

    def _plant_injections(self) -> None:
        rng = self.rng
        suspicious = np.flatnonzero(np.any([self.y[t] for t in TYPOLOGIES], axis=0))
        count = min(self.k(self.cfg.n_injection_names, 4), len(suspicious))
        chosen = rng.choice(suspicious, size=count, replace=False)
        for position, cidx in enumerate(chosen):
            template = pools.INJECTION_TEMPLATES[position % len(pools.INJECTION_TEMPLATES)]
            self.c_name[cidx] = f"{template} {int(rng.integers(10, 99))} LTD"
        self.injected[chosen] = True

    # ================================================================= assembly
    def _render_person_names(self, pid: np.ndarray, noise: np.ndarray, persons: dict[str, np.ndarray]) -> np.ndarray:
        rng = self.rng
        sur = np.char.upper(persons["sur"][pid].astype(str)).astype(object)
        f1 = persons["f1"][pid]
        f2 = persons["f2"][pid]
        has_middle = f2 != ""
        variant = np.zeros(len(pid), dtype=np.int8)
        noisy = rng.random(len(pid)) < noise
        variant[noisy] = rng.choice([1, 2, 3, 4], size=int(noisy.sum()), p=[0.4, 0.3, 0.18, 0.12])
        typo_rows = np.flatnonzero(variant == 3)
        if len(typo_rows):
            sur[typo_rows] = np.array([_typo(rng, s) for s in sur[typo_rows]], dtype=object)
        fore_rows = np.flatnonzero(variant == 4)
        if len(fore_rows):
            f1 = f1.copy()
            f1[fore_rows] = np.array([_typo(rng, s.upper()).title() for s in f1[fore_rows]], dtype=object)
        full_middle = np.where(has_middle & np.isin(variant, [0, 3, 4]), " " + f2, "")
        initial = np.array([m[:1] for m in f2], dtype=object)
        full_middle = np.where(has_middle & (variant == 2), " " + initial, full_middle)
        return sur + ", " + f1 + full_middle

    def generate(self) -> Registry:
        n = self.n
        self.special = np.zeros(n, dtype=bool)
        self.y = {t: np.zeros(n, dtype=bool) for t in TYPOLOGIES}
        self.group = np.full(n, "", dtype=object)
        self.negative = np.full(n, "", dtype=object)
        self.hops = np.zeros(n, dtype=np.int8)
        self.ring_length = np.zeros(n, dtype=np.int8)
        self.injected = np.zeros(n, dtype=bool)
        self._background_companies()
        self._reserve = self.rng.permutation(n)
        self._cursor = 0

        self._plant_factories_and_nominees()
        self._plant_rings()
        self._plant_sanctions()
        self._plant_opaque()
        self._plant_benign_foreign_parents()
        self._plant_bursts_and_phoenix()
        self._background_people()
        self._background_offshore()
        self._filler_sanctions()
        self._plant_namesakes()
        self._plant_injections()
        return self._assemble()

    def _assemble(self) -> Registry:
        rng = self.rng
        persons = {key: np.concatenate(chunks) for key, chunks in self._person_chunks.items()}
        sic_code = np.array([c for c, _ in pools.SIC_CODES], dtype=object)[self.c_sic]
        sic_text = np.array([t for _, t in pools.SIC_CODES], dtype=object)[self.c_sic]
        companies = pd.DataFrame(
            {
                "company_number": self.c_number.astype(object),
                "company_name": self.c_name,
                "status": self.c_status,
                "category": self.c_category,
                "country_of_origin": "United Kingdom",
                "incorporation_date": pd.to_datetime(self.c_inc),
                "dissolution_date": pd.to_datetime(self.c_diss),
                "address_line1": self.c_line,
                "post_town": self.c_town,
                "postcode": self.c_postcode,
                "country": "United Kingdom",
                "sic_code": sic_code,
                "sic_text": sic_text,
                "accounts_category": self.c_accounts,
                "accounts_overdue": self.c_overdue,
            }
        )

        off = {key: np.concatenate([row[key] for row in self._officer_rows]) for key in self._officer_rows[0]}
        officers = pd.DataFrame(
            {
                "company_number": self.c_number[off["cidx"]].astype(object),
                "officer_name": self._render_person_names(off["pid"], off["noise"], persons),
                "officer_kind": "person",
                "role": off["role"],
                "dob_year": persons["y"][off["pid"]].astype(np.int16),
                "dob_month": persons["m"][off["pid"]].astype(np.int8),
                "nationality": persons["nat"][off["pid"]],
                "country_of_residence": persons["res"][off["pid"]],
                "occupation": persons["occ"][off["pid"]],
                "appointed_on": pd.to_datetime(off["appointed"]),
                "resigned_on": pd.to_datetime(off["resigned"]),
                "true_person_id": off["pid"],
            }
        )
        # A deliberate share of nominee filings carries a wrong birth month.
        slip = np.flatnonzero((off["noise"] > 0.5) & (rng.random(len(officers)) < 0.03))
        officers.loc[slip, "dob_month"] = (officers.loc[slip, "dob_month"] % 12 + 1).astype(np.int8)
        officers = officers.drop_duplicates(["company_number", "true_person_id", "role"]).reset_index(drop=True)
        officers.insert(0, "appointment_id", np.arange(len(officers)))

        psc = {key: np.concatenate([row[key] for row in self._psc_rows]) for key in self._psc_rows[0]}
        ind = psc["kind"] == "individual"
        pid = np.where(ind, psc["pid"], 0)
        person_title = np.array(["Mr", "Mrs", "Ms", "Dr", "Miss"], dtype=object)[rng.choice(5, size=len(persons["f1"]), p=[0.5, 0.2, 0.2, 0.05, 0.05])]
        titles = person_title[pid]
        middle = np.where((persons["f2"][pid] != "") & (rng.random(len(pid)) < 0.7), " " + persons["f2"][pid], "")
        natural = titles + " " + persons["f1"][pid] + middle + " " + persons["sur"][pid]
        pscs = pd.DataFrame(
            {
                "company_number": self.c_number[psc["cidx"]].astype(object),
                "kind": psc["kind"],
                "name": np.where(ind, natural, psc["name"]),
                "dob_year": np.where(ind, persons["y"][pid], 0).astype(np.int16),
                "dob_month": np.where(ind, persons["m"][pid], 0).astype(np.int8),
                "nationality": np.where(ind, persons["nat"][pid], ""),
                "country_of_residence": np.where(ind, persons["res"][pid], ""),
                "natures_of_control": psc["natures"],
                "ownership_band": psc["band"],
                "notified_on": pd.to_datetime(psc["notified"]),
                "registration_number": psc["reg"],
                "country_registered": psc["country"],
                "legal_form": psc["form"],
                "true_person_id": psc["pid"],
                "true_target": psc["target"],
            }
        )
        pscs.insert(0, "psc_id", np.arange(len(pscs)))

        oe = {key: np.concatenate([row[key] for row in self._oe_rows]) for key in self._oe_rows[0]}
        offshore_entities = pd.DataFrame(
            {
                "node_id": oe["node_id"],
                "name": oe["name"],
                "jurisdiction": oe["jurisdiction"],
                "incorporation_date": pd.to_datetime(oe["inc"]),
                "status": oe["status"],
                "source": oe["source"],
            }
        )
        oo = {key: np.concatenate([row[key] for row in self._oo_rows]) for key in self._oo_rows[0]}
        offshore_officers = pd.DataFrame(oo)
        oedge = {key: np.concatenate([row[key] for row in self._oedge_rows]) for key in self._oedge_rows[0]}
        offshore_edges = pd.DataFrame({"start_id": oedge["start"], "end_id": oedge["end"], "link": oedge["link"]})
        sanctions = pd.DataFrame(self._sanctions)
        sanctions["listed_on"] = pd.to_datetime(sanctions["listed_on"])

        labels = pd.DataFrame({"company_number": self.c_number.astype(object)})
        for name in TYPOLOGIES:
            labels[name] = self.y[name]
        labels["suspicious"] = labels[list(TYPOLOGIES)].any(axis=1)
        labels["sanction_hops"] = self.hops
        labels["ring_length"] = self.ring_length
        labels["group"] = self.group
        labels["hard_negative"] = np.where(labels["suspicious"], "", self.negative)
        labels["injected_name"] = self.injected

        truth = {
            "company_labels": labels,
            "officers": officers[["appointment_id", "true_person_id"]].copy(),
            "pscs": pscs[["psc_id", "true_person_id", "true_target"]].copy(),
            "sanctions": pd.DataFrame(self._sanction_truth),
            "sanction_reach": pd.DataFrame(self._sanction_reach),
            "leak_company_links": pd.DataFrame(self._leak_company_links, columns=["node_id", "company_number"]),
            "addresses": pd.DataFrame(self._address_truth),
            "persons": pd.DataFrame(self._person_truth),
        }
        officers = officers.drop(columns=["true_person_id"])
        pscs = pscs.drop(columns=["true_person_id", "true_target"])
        meta = {
            "synthetic": True,
            "seed": int(self.cfg.seed),
            "snapshot_date": self.cfg.snapshot_date,
            "n_companies": int(self.n),
            "n_true_persons": int(self._n_persons),
        }
        registry = Registry(companies, officers, pscs, offshore_entities, offshore_officers, offshore_edges, sanctions, truth, meta)
        log.info("synthetic registry built: %s", registry.summary())
        return registry


def generate_registry(cfg: SynthConfig) -> Registry:
    """Convenience wrapper used by the pipeline and the tests."""
    return RegistryGenerator(cfg).generate()
