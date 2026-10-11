"""Loaders for the public source layouts and an exporter that mirrors them.

Four public sources feed the real data path:

* the Companies House free company data product (one wide CSV)
* the Companies House persons with significant control snapshot (JSON lines)
* the OpenSanctions simplified targets table (CSV), which consolidates the
  OFSI and OFAC lists among others
* the ICIJ Offshore Leaks database (node and relationship CSV files)

Officer appointments are not published as a free bulk file, so they are read
from a plain CSV in the layout documented in docs/data_dictionary.md. That
file can be filled from the Companies House API or a licensed bulk product.

The exporter writes a synthetic registry in these layouts so the loaders can
be exercised without the multi gigabyte originals. The official files use
the ASCII 45 character as a word separator inside several fixed values, so
the separator is built from its character code here and removed on load.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

from ..textnorm import LEGAL_FORM_MAP, norm_text
from .synth import Registry

SEP = chr(45)
_DIGIT_RUNS = re.compile(r"\d+")

COMPANY_COLUMN_MAP = {
    "CompanyName": "company_name",
    "CompanyNumber": "company_number",
    "RegAddress.AddressLine1": "address_line1",
    "RegAddress.PostTown": "post_town",
    "RegAddress.PostCode": "postcode",
    "RegAddress.Country": "country",
    "CompanyCategory": "category",
    "CompanyStatus": "status",
    "CountryOfOrigin": "country_of_origin",
    "DissolutionDate": "dissolution_date",
    "IncorporationDate": "incorporation_date",
    "Accounts.AccountCategory": "accounts_category",
    "Accounts.NextDueDate": "accounts_next_due",
    "SICCode.SicText_1": "sic_raw",
}
PSC_KINDS = {
    "individual person with significant control": "individual",
    "corporate entity person with significant control": "corporate",
    "legal person person with significant control": "corporate",
    "persons with significant control statement": "statement",
    "super secure person with significant control": "statement",
    "individual beneficial owner": "individual",
    "corporate entity beneficial owner": "corporate",
}


def _spaced(value: object) -> str:
    """Lower case text with every separator turned into a single space."""
    return " ".join(re.sub(r"[^\w]|_", " ", str(value or "")).lower().split())


def band_from_natures(natures: str) -> float:
    """Midpoint of the strongest ownership or voting band named in the text."""
    best = 0.0
    numbers = [int(x) for x in _DIGIT_RUNS.findall(natures or "")]
    for low, high in zip(numbers[::2], numbers[1::2]):
        best = max(best, (low + high) / 200.0)
    if best == 0.0 and natures:
        best = 0.5
    return best


def load_companies_house_csv(path: str | Path, snapshot: pd.Timestamp | None = None, nrows: int | None = None) -> pd.DataFrame:
    """Read the free company data product into the canonical company table."""
    frame = pd.read_csv(path, dtype=str, nrows=nrows, keep_default_na=False)
    frame.columns = [c.strip() for c in frame.columns]
    present = {src: dst for src, dst in COMPANY_COLUMN_MAP.items() if src in frame.columns}
    out = frame[list(present)].rename(columns=present)
    for column in COMPANY_COLUMN_MAP.values():
        if column not in out.columns:
            out[column] = ""
    out["company_number"] = out["company_number"].str.strip().str.zfill(8)
    for column in ("incorporation_date", "dissolution_date", "accounts_next_due"):
        out[column] = pd.to_datetime(out[column], format="%d/%m/%Y", errors="coerce")
    sic = out["sic_raw"].str.strip()
    out["sic_code"] = sic.str.extract(r"^(\d+)", expand=False).fillna("")
    out["sic_text"] = sic.str.replace(r"^\d+\W+", "", regex=True)
    out["accounts_category"] = out["accounts_category"].str.upper().str.strip()
    as_of = snapshot if snapshot is not None else pd.Timestamp.today().normalize()
    out["accounts_overdue"] = out["accounts_next_due"].notna() & (out["accounts_next_due"] < as_of) & (out["status"] == "Active")
    return out.drop(columns=["sic_raw", "accounts_next_due"]).reset_index(drop=True)


def load_psc_snapshot(path: str | Path, limit: int | None = None) -> pd.DataFrame:
    """Read the persons with significant control snapshot (one JSON per line)."""
    rows = []
    with open(path, "r", encoding="utf8") as handle:
        for line_number, line in enumerate(handle):
            if limit is not None and line_number >= limit:
                break
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            data = record.get("data", {})
            kind = PSC_KINDS.get(_spaced(data.get("kind")))
            if kind is None:
                continue
            dob = data.get("date_of_birth") or {}
            ident = data.get("identification") or {}
            natures = "|".join(_spaced(x) for x in data.get("natures_of_control", []))
            name = data.get("name") or _spaced(data.get("statement")).capitalize()
            rows.append(
                {
                    "company_number": str(record.get("company_number", "")).zfill(8),
                    "kind": kind,
                    "name": name,
                    "dob_year": int(dob.get("year") or 0),
                    "dob_month": int(dob.get("month") or 0),
                    "nationality": data.get("nationality", "") or "",
                    "country_of_residence": data.get("country_of_residence", "") or "",
                    "natures_of_control": natures,
                    "ownership_band": band_from_natures(natures) if kind != "statement" else 0.0,
                    "notified_on": data.get("notified_on"),
                    "ceased_on": data.get("ceased_on"),
                    "registration_number": ident.get("registration_number", "") or "",
                    "country_registered": ident.get("country_registered", "") or ident.get("place_registered", "") or "",
                    "legal_form": ident.get("legal_form", "") or "",
                }
            )
    out = pd.DataFrame(rows)
    out["notified_on"] = pd.to_datetime(out["notified_on"], errors="coerce")
    ceased = pd.to_datetime(out.pop("ceased_on"), errors="coerce")
    out = out[ceased.isna()].reset_index(drop=True)
    out["dob_year"] = out["dob_year"].astype(np.int16)
    out["dob_month"] = out["dob_month"].astype(np.int8)
    out["ownership_band"] = out["ownership_band"].astype(np.float32)
    out.insert(0, "psc_id", np.arange(len(out)))
    return out


def load_officers_csv(path: str | Path) -> pd.DataFrame:
    """Read officer appointments from the project CSV layout."""
    out = pd.read_csv(path, dtype=str, keep_default_na=False)
    out["company_number"] = out["company_number"].str.zfill(8)
    for column in ("appointed_on", "resigned_on"):
        out[column] = pd.to_datetime(out[column], format="%Y/%m/%d", errors="coerce")
    out["dob_year"] = pd.to_numeric(out["dob_year"], errors="coerce").fillna(0).astype(np.int16)
    out["dob_month"] = pd.to_numeric(out["dob_month"], errors="coerce").fillna(0).astype(np.int8)
    out["appointment_id"] = np.arange(len(out))
    return out


def load_opensanctions_simple(path: str | Path) -> pd.DataFrame:
    """Read the OpenSanctions simplified targets table."""
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    keep = frame["schema"].isin(["Person", "Company", "Organization", "LegalEntity"])
    frame = frame[keep].reset_index(drop=True)
    years, months = [], []
    for value in frame["birth_date"]:
        parts = _DIGIT_RUNS.findall(value.split(";")[0])
        years.append(int(parts[0]) if parts and len(parts[0]) == 4 else 0)
        months.append(int(parts[1]) if len(parts) > 1 and years[len(years) - 1] else 0)
    schema = frame["schema"].where(frame["schema"] == "Person", "Company")
    return pd.DataFrame(
        {
            "entity_id": frame["id"],
            "schema": schema,
            "name": frame["name"],
            "aliases": frame["aliases"].str.replace(";", "; ", regex=False).str.replace(r"\s+", " ", regex=True),
            "birth_year": years,
            "birth_month": months,
            "regime": frame["sanctions"].str.slice(0, 120),
            "listed_on": pd.to_datetime(frame["first_seen"], errors="coerce"),
        }
    )


def _first_match(directory: Path, *patterns: str) -> Path:
    for pattern in patterns:
        found = sorted(directory.glob(pattern))
        if found:
            return found[0]
    raise FileNotFoundError(f"none of {patterns} found in {directory}")


def load_icij(directory: str | Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Read the Offshore Leaks node and relationship files."""
    root = Path(directory)
    entities = pd.read_csv(_first_match(root, "nodes*entities*.csv"), dtype=str, keep_default_na=False)
    officers = pd.read_csv(_first_match(root, "nodes*officers*.csv"), dtype=str, keep_default_na=False)
    edges = pd.read_csv(_first_match(root, "relationships*.csv"), dtype=str, keep_default_na=False)
    jurisdiction = entities["jurisdiction_description"] if "jurisdiction_description" in entities else entities["jurisdiction"]
    offshore_entities = pd.DataFrame(
        {
            "node_id": entities["node_id"].astype(np.int64),
            "name": entities["name"],
            "jurisdiction": jurisdiction,
            "incorporation_date": pd.to_datetime(entities.get("incorporation_date"), errors="coerce", format="mixed"),
            "status": entities.get("status", ""),
            "source": entities.get("sourceID", ""),
        }
    )
    legal = set(LEGAL_FORM_MAP) | {"HOLDINGS", "TRUST", "FOUNDATION", "FUND", "BANK"}
    is_company = [bool(set(norm_text(name).split()) & legal) for name in officers["name"]]
    offshore_officers = pd.DataFrame(
        {
            "node_id": officers["node_id"].astype(np.int64),
            "name": officers["name"],
            "kind": np.where(is_company, "company", "person"),
            "country": officers.get("countries", ""),
        }
    )
    known = set(offshore_entities["node_id"]) | set(offshore_officers["node_id"])
    edges = edges[edges["rel_type"].isin(["officer_of", "intermediary_of"])]
    offshore_edges = pd.DataFrame(
        {
            "start_id": edges["node_id_start"].astype(np.int64),
            "end_id": edges["node_id_end"].astype(np.int64),
            "link": edges["link"].where(edges["link"] != "", edges["rel_type"]),
        }
    )
    offshore_edges = offshore_edges[offshore_edges["start_id"].isin(known) & offshore_edges["end_id"].isin(known)]
    return offshore_entities, offshore_officers, offshore_edges.reset_index(drop=True)


def export_official_layout(registry: Registry, directory: str | Path) -> Path:
    """Write a registry in the layouts of the public sources."""
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    c = registry.companies
    due = c["incorporation_date"] + pd.to_timedelta(np.where(c["accounts_overdue"], 640, 40_000), unit="D")
    pd.DataFrame(
        {
            "CompanyName": c["company_name"],
            " CompanyNumber": c["company_number"],
            "RegAddress.AddressLine1": c["address_line1"],
            "RegAddress.PostTown": c["post_town"],
            "RegAddress.Country": c["country"],
            "RegAddress.PostCode": c["postcode"],
            "CompanyCategory": c["category"],
            "CompanyStatus": c["status"],
            "CountryOfOrigin": c["country_of_origin"],
            "DissolutionDate": c["dissolution_date"].dt.strftime("%d/%m/%Y").fillna(""),
            "IncorporationDate": c["incorporation_date"].dt.strftime("%d/%m/%Y"),
            "Accounts.NextDueDate": due.dt.strftime("%d/%m/%Y"),
            "Accounts.AccountCategory": c["accounts_category"],
            "SICCode.SicText_1": c["sic_code"] + f" {SEP} " + c["sic_text"],
        }
    ).to_csv(root / "BasicCompanyData.csv", index=False, quoting=csv.QUOTE_ALL)

    kind_text = {
        "individual": "individual person with significant control",
        "corporate": "corporate entity person with significant control",
        "statement": "persons with significant control statement",
    }
    with open(root / "psc_snapshot.jsonl", "w", encoding="utf8") as handle:
        for row in registry.pscs.itertuples(index=False):
            data: dict = {"kind": kind_text[row.kind].replace(" ", SEP), "notified_on": row.notified_on.strftime(f"%Y{SEP}%m{SEP}%d")}
            if row.kind == "statement":
                data["statement"] = "no individual or entity with signficant control".replace(" ", SEP)
            else:
                data["name"] = row.name
                data["natures_of_control"] = [row.natures_of_control.replace(" ", SEP)]
            if row.kind == "individual":
                data["date_of_birth"] = {"month": int(row.dob_month), "year": int(row.dob_year)}
                data["nationality"] = row.nationality
                data["country_of_residence"] = row.country_of_residence
            if row.kind == "corporate":
                data["identification"] = {
                    "country_registered": row.country_registered,
                    "legal_form": row.legal_form,
                    "registration_number": row.registration_number,
                }
            handle.write(json.dumps({"company_number": row.company_number, "data": data}) + "\n")

    officers = registry.officers.drop(columns=["appointment_id"]).copy()
    for column in ("appointed_on", "resigned_on"):
        officers[column] = officers[column].dt.strftime("%Y/%m/%d").fillna("")
    officers.to_csv(root / "officers.csv", index=False)

    s = registry.sanctions
    birth = np.where(
        s["birth_year"] > 0,
        s["birth_year"].astype(str) + np.where(s["birth_month"] > 0, SEP + s["birth_month"].astype(str).str.zfill(2), ""),
        "",
    )
    pd.DataFrame(
        {
            "id": s["entity_id"],
            "schema": s["schema"],
            "name": s["name"],
            "aliases": s["aliases"].str.replace("; ", ";", regex=False),
            "birth_date": birth,
            "countries": "",
            "addresses": "",
            "identifiers": "",
            "sanctions": s["regime"],
            "phones": "",
            "emails": "",
            "dataset": "synthetic list",
            "first_seen": s["listed_on"].dt.strftime(f"%Y{SEP}%m{SEP}%d"),
            "last_seen": "",
            "last_change": "",
        }
    ).to_csv(root / "targets.simple.csv", index=False)

    e = registry.offshore_entities
    pd.DataFrame(
        {
            "node_id": e["node_id"],
            "name": e["name"],
            "jurisdiction": "",
            "jurisdiction_description": e["jurisdiction"],
            "incorporation_date": e["incorporation_date"].dt.strftime("%d %b %Y").str.upper(),
            "status": e["status"],
            "sourceID": e["source"],
        }
    ).to_csv(root / "nodes_entities.csv", index=False)
    o = registry.offshore_officers
    pd.DataFrame({"node_id": o["node_id"], "name": o["name"], "countries": o["country"], "sourceID": ""}).to_csv(root / "nodes_officers.csv", index=False)
    g = registry.offshore_edges
    pd.DataFrame({"node_id_start": g["start_id"], "node_id_end": g["end_id"], "rel_type": "officer_of", "link": g["link"]}).to_csv(root / "relationships.csv", index=False)
    return root


def load_official_directory(directory: str | Path, snapshot: str | None = None) -> Registry:
    """Build a Registry from a folder that holds the public source files."""
    root = Path(directory)
    as_of = pd.to_datetime(snapshot, format="%Y/%m/%d") if snapshot else None
    companies = load_companies_house_csv(_first_match(root, "BasicCompanyData*.csv"), snapshot=as_of)
    pscs = load_psc_snapshot(_first_match(root, "psc*snapshot*", "persons*with*significant*control*snapshot*"))
    officers = load_officers_csv(_first_match(root, "officers*.csv"))
    sanctions = load_opensanctions_simple(_first_match(root, "targets*.csv"))
    offshore_entities, offshore_officers, offshore_edges = load_icij(root)
    known = set(companies["company_number"])
    pscs = pscs[pscs["company_number"].isin(known)].reset_index(drop=True)
    officers = officers[officers["company_number"].isin(known)].reset_index(drop=True)
    meta = {"synthetic": False, "source_directory": str(root), "snapshot_date": snapshot or ""}
    return Registry(companies, officers, pscs, offshore_entities, offshore_officers, offshore_edges, sanctions, {}, meta)
