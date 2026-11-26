"""The qualitative case table must stay honest: every URL is http(s), unverified rows say so, all sectors covered."""

import csv
from pathlib import Path

CASES = Path(__file__).resolve().parents[1] / "data" / "cases.csv"
REQUIRED = {"table_locator", "sector", "incident_or_scenario", "author_claim", "independent_source_url",
            "incident_evidence_status", "ai_use_evidence_status", "observed_or_hypothetical_impact"}


def rows():
    with CASES.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def test_columns_and_sector_coverage():
    r = rows()
    assert REQUIRED <= set(r[0])
    sectors = {x["sector"] for x in r}
    assert {"Energy", "Finance", "Government and defense", "Telecom and smart cities"} <= sectors
    for sector in ("Energy", "Finance", "Government and defense", "Telecom and smart cities"):
        assert any(x["sector"] == sector and x["independent_source_url"] for x in r), sector


def test_urls_are_http_and_empty_urls_are_not_claimed_verified():
    for x in rows():
        url = x["independent_source_url"]
        assert not url or url.startswith("https://")
        if not url:
            assert "verified_in_this_run" not in x["incident_evidence_status"].split(":")[0] or "not_verified" in x["incident_evidence_status"]


def test_hypothetical_rows_are_marked():
    t7 = [x for x in rows() if x["table_locator"].startswith("Table 7")]
    assert t7 and all("hypothetical" in x["observed_or_hypothetical_impact"] for x in t7)
