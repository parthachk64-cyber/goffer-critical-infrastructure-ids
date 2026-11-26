"""Builds data/cases.csv, the qualitative case table. Source URLs are only ones actually opened or
returned by a search in this work; everything else is marked not verified. Run: python data/build_cases.py
"""

from __future__ import annotations

import csv
from pathlib import Path

HEADER = [
    "table_locator", "sector", "incident_or_scenario", "author_claim", "independent_source_url",
    "incident_evidence_status", "ai_use_evidence_status", "observed_or_hypothetical_impact",
    "cross_sector_theme", "notes",
]  # fmt: skip
V = "verified_in_this_run"
U = "not_verified_in_this_run"
GENERIC = "generic_scenario_no_incident_cited"
NONE_ASSERTED = "none_asserted_in_sources_read"
NOT_SUPPORTED = "not_supported_by_sources_read"

ROWS = [
    ("Table 1, p.1673; text p.1672", "Energy", "Colonial Pipeline ransomware (2021)",
     "Phishing, ransomware, zero-day, data exfiltration; US$4.4 million ransom (cited to Khaustova et al. 2023)",
     "https://www.cisa.gov/ncas/alerts/aa21-131a",
     V + ": CISA/FBI advisory on DarkSide ransomware used against a critical-infrastructure company; IT network affected, no indication of lateral movement to OT",
     NONE_ASSERTED, "observed: fuel-supply disruption per the authors; ransom amount not checked here",
     "ransomware on critical infrastructure",
     "Phishing, zero-day and ransom-amount claims were not checked against an independent source in this run."),
    ("Table 1, p.1673; text p.1672", "Energy", "Ukraine power-grid attacks (2015 and 2016)",
     "SCADA exploitation, state-sponsored, phishing; grid disruption (cited to Younis & Kifayat 2013)",
     "https://cisa.gov/news-events/ics-alerts/ir-alert-h-16-056-01",
     V + " for Dec 2015 (unscheduled outages; BlackEnergy reported; later attributed to Russian state actors). The 2016 event is not covered by this source",
     NONE_ASSERTED, "observed: outages affecting customers (2015)", "state-sponsored attack on energy",
     "The cited source (Younis & Kifayat 2013, a cloud-computing survey) predates the 2015-2016 events."),
    ("Table 1, p.1673", "Energy", "Triton/HatMan malware (2017)",
     "SCADA exploitation, state-sponsored, zero-day, disruption, AI-enhanced malware, insider threats",
     "https://www.cisa.gov/sites/default/files/documents/MAR-17-352-01%20HatMan%E2%80%94Safety%20System%20Targeted%20Malware_S508C.pdf",
     V + ": CISA malware analysis report on malware targeting Triconex safety systems; a joint advisory (https://www.ic3.gov/CSA/2022/220325.pdf) attributes the 2017 attack to a Russian institute",
     NOT_SUPPORTED + ": no AI use asserted", "observed: safety-system controllers at a Middle East petrochemical facility were targeted",
     "state-sponsored attack on energy", "Table 1 marks AI-enhanced malware and insider threats for Triton; neither is supported by what was read."),
    ("Table 1, p.1673", "Energy", "BlackEnergy malware campaign (2014)",
     "Phishing, state-sponsored, zero-day, grid disruption",
     "https://us-cert.cisa.gov/ics/alerts/ICS-ALERT-14-281-01B",
     U + ": an ICS-CERT alert on an ongoing malware campaign against ICS exists; its contents were not read",
     NONE_ASSERTED, "author claim only", "state-sponsored attack on energy", "Per-cell ticks in Table 1 were not checked."),
    ("Table 2, p.1674; text p.1673", "Finance", "UAE bank deepfake-voice fraud (2020, US$35 million)",
     "Deepfake voice/video impersonation, synthetic identity fraud, real-time AI fraud (cited to Hemphill & Longstreet 2016)",
     "https://www.darkreading.com/cyberattacks-data-breaches/deepfake-audio-scores-35-million-in-corporate-heist",
     U + ": reported from a US court filing as relayed by Forbes and secondary outlets (also https://incidentdatabase.ai/reports/1496); bank not named; no primary document read",
     "alleged_in_court_document_as_reported_by_secondary_sources",
     "observed (as reported): US$35 million; about US$400,000 traced to US accounts", "AI-enabled impersonation fraud",
     "The cited source (Hemphill & Longstreet 2016) concerns US retail data breaches, not this case."),
    ("Table 2, p.1674", "Finance", "Stock-market manipulation with AI-generated news",
     "Algorithmic market manipulation, real-time AI fraud", "", GENERIC, "not_applicable", "hypothetical",
     "AI-enabled market manipulation", "No incident named in the paper."),
    ("Table 2, p.1674", "Finance", "AI-powered phishing attacks and AI-driven botnet attacks",
     "Automated phishing, credential stuffing, account takeover", "", GENERIC, "not_applicable", "hypothetical",
     "AI-enabled phishing and credential abuse", "No incident named in the paper."),
    ("Table 3, p.1675; text p.1674", "Government and defense", "SolarWinds Orion supply-chain compromise (2020)",
     "AI-powered malware, supply chain attack, nation-state espionage, AI-driven exfiltration",
     "https://us-cert.cisa.gov/ncas/alerts/aa20-352a",
     V + ": CISA alert on APT compromise via the SolarWinds Orion supply chain; attributed to the Russian SVR in an April 2021 update",
     NOT_SUPPORTED + ": no AI use asserted", "observed: US agencies, critical infrastructure and private organisations compromised",
     "software supply-chain compromise", "The 18,000-organisation figure in Table 5 was not checked here."),
    ("Table 3, p.1675; text p.1674", "Government and defense", "Stuxnet (2010)",
     "AI-powered malware; 'sophisticated AI-powered cyber warfare' (cited to Anwar et al. 2017)", "",
     U + ": no independent source retrieved", NOT_SUPPORTED + ": no source read supports an AI claim", "author claim only",
     "state-sponsored attack on industrial control", "Treat the AI characterisation as unsupported."),
    ("Table 3, p.1675", "Government and defense", "Chinese cyber espionage (2021) and Russian disinformation campaigns",
     "Autonomous cyber threats, deepfake-based disinformation", "", GENERIC, "not_applicable", "author claim only",
     "espionage and disinformation", "No specific incident or source given."),
    ("Table 4, pp.1675-1676; text p.1675", "Telecom and smart cities", "Mirai botnet DDoS (2016)",
     "Botnet-based DDoS, adversarial AI in IoT, data exfiltration (cited to Cardoni et al. 2022)",
     "https://usenix.org/conference/usenixsecurity17/technical-sessions/presentation/antonakakis",
     V + ": peer-reviewed measurement study of Mirai (about 600k infections at peak)", NONE_ASSERTED,
     "observed: large-scale DDoS from compromised IoT devices", "IoT botnet attack",
     "The cited source (Cardoni et al. 2022) concerns seismic resilience of telecom networks, not Mirai."),
    ("Table 4, pp.1675-1676", "Telecom and smart cities", "Water-treatment SCADA intrusion (labelled 'Smart City Water Hack 2021')",
     "Critical infrastructure manipulation, AI-powered malware injection, adversarial AI exploits",
     "https://us-cert.cisa.gov/ncas/alerts/aa21-042a",
     V + ": CISA/FBI/EPA/MS-ISAC advisory on a Feb 2021 unauthorised SCADA access at a US water plant (Oldsmar); treatment unaffected; FBI could not confirm a targeted intrusion",
     NOT_SUPPORTED + ": the advisory cites weak passwords and remote-access software, not AI",
     "observed: attempted chemical-dosing change; no process impact per the advisory", "critical-infrastructure intrusion",
     "The paper does not name the facility; matching it to Oldsmar is this repository's inference."),
    ("Table 4, pp.1675-1676", "Telecom and smart cities", "AI-driven telecom fraud; IoT DDoS on 5G networks",
     "Deepfake-based telecom fraud; IoT DDoS on 5G", "", GENERIC, "not_applicable", "hypothetical",
     "IoT and telecom abuse", "No incident named."),
    ("Table 5, p.1677", "Nation-state cyber attacks", "NotPetya (2017), Microsoft Exchange (2021), HermeticWiper (2022), APT41",
     "US$10 billion damage; 60,000+ companies; financial-institution disruption; AI-enhanced intrusions for APT41", "",
     U + ": figures and the AI characterisation were not checked", NOT_SUPPORTED + " for the APT41 AI claim", "author claim only",
     "nation-state destructive and espionage campaigns", "The cited source for NotPetya and APT41 (Wentz et al. 2011) predates both."),
    ("Table 5, p.1677", "Nation-state cyber attacks", "SolarWinds hack (2020)", "18,000 compromised organizations",
     "https://us-cert.cisa.gov/ncas/alerts/aa20-352a",
     V + " for the incident; the 18,000 figure was not found in the material read", "not_applicable", "observed",
     "software supply-chain compromise", "See the Table 3 SolarWinds row."),
    ("Table 6, p.1677", "AI-driven cybercrime", "UK energy firm voice-clone fraud (2019, US$243,000)",
     "AI voice cloning; US$243,000 stolen",
     "https://www.sophos.com/en-us/blog/scammers-deepfake-ceos-voice-to-talk-underling-into-243000-transfer",
     U + ": reported by the Wall Street Journal and relayed by secondary outlets (EUR 220,000, about US$243,000); original article not retrieved",
     "reported_by_secondary_sources_that_investigators_believed_an_AI_voice_was_used",
     "observed (as reported): EUR 220,000 transferred; insurer reimbursed", "AI-enabled impersonation fraud",
     "The 'first such case' framing is disputed in secondary reporting."),
    ("Table 6, p.1677", "AI-driven cybercrime", "Office 365 phishing campaign (2022, 30,000+ accounts)",
     "ML-generated emails; 30,000+ accounts compromised", "", U + ": no matching source found in this run", "unverified",
     "author claim only", "AI-enabled phishing", "The figure and the ML-generated-email attribution are unverified."),
    ("Table 6, p.1677", "AI-driven cybercrime", "Fake Elon Musk cryptocurrency ad (2023)",
     "GAN-based video synthesis; millions lost", "", U + ": no source retrieved in this run", "unverified",
     "author claim only", "deepfake-enabled fraud", "No amount or source given."),
    ("Table 7, pp.1678-1679", "Cyberterrorism",
     "Financial market disruption; critical-infrastructure attacks; government network intrusions; transportation disruption; disinformation",
     "AI-driven fraud, ransomware, malware, traffic manipulation, deepfakes; blackouts, crashes, accidents", "",
     "hypothetical_scenario_table_no_incidents_cited", "not_applicable", "hypothetical: 'potential impact' column",
     "cyberterrorism scenarios", "Table 7 is scenario planning; no row here is evidence that an incident occurred."),
]  # fmt: skip


def main() -> None:
    out = Path(__file__).resolve().parent / "cases.csv"
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(HEADER)
        w.writerows(ROWS)
    print(f"wrote {len(ROWS)} rows to {out}")


if __name__ == "__main__":
    main()
