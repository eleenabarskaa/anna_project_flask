"""Демо-данные, перенесённые один в один из макетов.

Единственное место, где живут «захардкоженные» данные. Когда подключим
реальные БД и интеграции, этот модуль остаётся только для тестов/локальной
разработки, а прод-репозитории будут читать из источников.
"""

from __future__ import annotations

from datetime import date

from app.models import (
    Angle,
    DeskTask,
    Dossier,
    Fact,
    IngestLogEntry,
    Kpi,
    Person,
    Prospect,
    Relation,
    Source,
    SourceStatus,
    Stat,
    TimelineEvent,
    Trigger,
    TriggerCategory,
    TriggerType,
    WatchlistItem,
)

TRIGGERS: list[Trigger] = [
    Trigger(
        id="t1",
        date=date(2026, 9, 5),
        company="Helvetia Precision AG",
        headline="Sale of 74% stake to Tata-backed industrial vehicle group agreed",
        type=TriggerType.MA,
        source="NZZ",
        principal="Brunner family",
        est="CHF 1.4bn",
        confidence="High",
        confidence_pct=88,
        parties="Buyer: TML CV Holdings · Seller: Brunner Holding",
        context=(
            "Signed 4 Sep, closing expected Q1 2027 subject to WEKO clearance. "
            "Cash consideration with a 15% deferred tranche; the family retains the "
            "Winterthur property portfolio outside the perimeter."
        ),
        url="https://www.nzz.ch/wirtschaft/helvetia-precision-tml-cv-holdings-2026",
        ingested_at="05 Sep 06:12",
        reviewer="M. Roth",
        people=[
            Person(id="p1", name="Elisabeth Brunner", role="Chair, 41% holder"),
            Person(id="p2", name="Jonas Brunner", role="CFO, 12% holder"),
        ],
    ),
    Trigger(
        id="t2",
        date=date(2026, 9, 4),
        company="Nordkap Telecom",
        headline="Poste-led consortium tables cash offer; founder block to be tendered",
        type=TriggerType.MA,
        source="Il Sole 24 Ore",
        principal="L. Ferretti",
        est="EUR 610m",
        confidence="Medium",
        confidence_pct=62,
        parties="Buyer: Poste consortium · Seller: —",
        context=(
            "Non-binding offer disclosed in a press release; board has formed an "
            "independent committee. Founder holding of 18.4% is expected to tender "
            "based on prior statements."
        ),
        url="https://www.ilsole24ore.com/art/nordkap-offerta-consorzio-2026",
        ingested_at="04 Sep 19:40",
        reviewer="auto",
        people=[Person(id="p3", name="Lorenzo Ferretti", role="Founder, 18.4% holder")],
    ),
    Trigger(
        id="t3",
        date=date(2026, 9, 3),
        company="Vaduz Chemicals Holding",
        headline="IPO priced at top of range; two co-founders sell secondary lines",
        type=TriggerType.IPO,
        source="FT",
        principal="Keller & Amrein",
        est="CHF 380m",
        confidence="High",
        confidence_pct=91,
        parties="Selling shareholders: Keller, Amrein",
        context=(
            "Listing on SIX 12 Sep. Combined secondary proceeds of roughly CHF 380m "
            "before greenshoe; 180-day lock-up applies to remaining stakes."
        ),
        url="https://www.ft.com/content/vaduz-chemicals-ipo-2026",
        ingested_at="03 Sep 08:05",
        reviewer="A. Kaufmann",
        people=[
            Person(id="p4", name="Marc Keller", role="Co-founder"),
            Person(id="p5", name="Sofia Amrein", role="Co-founder"),
        ],
    ),
    Trigger(
        id="t4",
        date=date(2026, 9, 2),
        company="Alpine Data Centres",
        headline="PE exit: Terra Partners sells to infrastructure fund, management rolls 20%",
        type=TriggerType.PE_EXIT,
        source="Reuters",
        principal="Management team",
        est="EUR 240m",
        confidence="Medium",
        confidence_pct=58,
        parties="Buyer: Meridian Infra IV · Seller: Terra Partners",
        context=(
            "Enterprise value not disclosed; Reuters cites two people familiar. "
            "Management rollover implies a cash-out of roughly EUR 240m across six "
            "individuals."
        ),
        url="https://www.reuters.com/markets/deals/alpine-data-centres-2026",
        ingested_at="02 Sep 15:22",
        reviewer="auto",
        people=[Person(id="p6", name="Daniel Wyss", role="CEO, 6.2% holder")],
    ),
    Trigger(
        id="t5",
        date=date(2026, 8, 31),
        company="Rhône Logistics SA",
        headline="Court-approved succession settles 3-generation shareholding",
        type=TriggerType.SUCCESSION,
        source="Le Temps",
        principal="Dupasquier heirs",
        est="CHF 190m",
        confidence="Low",
        confidence_pct=34,
        parties="Estate: Dupasquier · Beneficiaries: 4",
        context=(
            "Public register entry indicates transfer of 61% of voting shares to four "
            "beneficiaries. Valuation is our own estimate from last filed accounts — "
            "treat as indicative."
        ),
        url="https://www.letemps.ch/economie/rhone-logistics-succession-2026",
        ingested_at="31 Aug 11:03",
        reviewer="M. Roth",
        people=[Person(id="p7", name="Camille Dupasquier", role="Beneficiary, 24%")],
    ),
    Trigger(
        id="t6",
        date=date(2026, 8, 28),
        company="Banca Monte Adriatico",
        headline="Dual exchange offer for two listed peers announced by CEO",
        type=TriggerType.MA,
        source="MF",
        principal="L. Lovaglio",
        est="EUR 1.1bn",
        confidence="Medium",
        confidence_pct=55,
        parties="Buyer: Banca Monte Adriatico · Seller: —",
        context=(
            "Share-for-share structure; limited cash element. Relevant for prospects "
            "holding stakes in either target rather than the bidder itself."
        ),
        url="https://www.milanofinanza.it/news/banca-monte-adriatico-opas-2026",
        ingested_at="28 Aug 07:31",
        reviewer="auto",
        people=[Person(id="p8", name="Pierluigi Tortora", role="Target shareholder, 3.1%")],
    ),
    Trigger(
        id="t7",
        date=date(2026, 8, 26),
        company="Genève Biotech Partners",
        headline="Series D secondary allows early-employee liquidity of USD 95m",
        type=TriggerType.SECONDARY,
        source="Bloomberg",
        principal="Early employees",
        est="USD 95m",
        confidence="High",
        confidence_pct=84,
        parties="Buyer: crossover funds · Seller: employees",
        context=(
            "Company-run secondary at a USD 2.4bn valuation. Roughly 40 individuals "
            "eligible; median expected proceeds in the low single-digit millions."
        ),
        url="https://www.bloomberg.com/news/geneve-biotech-secondary-2026",
        ingested_at="26 Aug 16:48",
        reviewer="A. Kaufmann",
        people=[Person(id="p9", name="Dr. Nadia Perrin", role="Employee #4")],
    ),
    Trigger(
        id="t8",
        date=date(2026, 8, 24),
        company="Zug Commodities Trust",
        headline="Family office restructures into two holding vehicles ahead of exit",
        type=TriggerType.RESTRUCTURING,
        source="Handelszeitung",
        principal="Steiner family",
        est="CHF 520m",
        confidence="Low",
        confidence_pct=38,
        parties="Vehicles: ZCT Alpha, ZCT Beta",
        context=(
            "Commercial register filings show two new vehicles with overlapping boards. "
            "Often a precursor to a divestment; no transaction disclosed yet."
        ),
        url="https://www.handelszeitung.ch/unternehmen/zug-commodities-2026",
        ingested_at="24 Aug 09:14",
        reviewer="auto",
        people=[Person(id="p10", name="Ruth Steiner", role="Principal")],
    ),
]

PROSPECTS: list[Prospect] = [
    Prospect(
        id="p1",
        name="Elisabeth Brunner",
        role="Chair, Helvetia Precision AG · Winterthur",
        trigger="Stake sale agreed 04 Sep",
        est="CHF 520m",
        domicile="CH · Zurich",
        updated="2h ago",
        fit=92,
        reason="Signed 74% stake sale · CHF 520m expected, no existing relationship",
        watched=False,
    ),
    Prospect(
        id="p3",
        name="Lorenzo Ferretti",
        role="Founder, Nordkap Telecom · Milan",
        trigger="Cash offer on 18.4% block",
        est="EUR 112m",
        domicile="IT · Milan",
        updated="1d ago",
        fit=78,
        reason="Tender offer on founder block · cross-border, Milan desk lead",
        watched=True,
    ),
    Prospect(
        id="p4",
        name="Marc Keller",
        role="Co-founder, Vaduz Chemicals Holding",
        trigger="IPO secondary, 12 Sep",
        est="CHF 210m",
        domicile="LI · Vaduz",
        updated="2d ago",
        fit=87,
        reason="IPO secondary prices 12 Sep · covered by Zurich desk since 2023",
        watched=False,
    ),
    Prospect(
        id="p6",
        name="Daniel Wyss",
        role="CEO, Alpine Data Centres · Geneva",
        trigger="PE exit, 20% rollover",
        est="EUR 34m",
        domicile="CH · Geneva",
        updated="3d ago",
        fit=59,
        reason="PE exit with 20% rollover · liquid portion modest",
        watched=True,
    ),
    Prospect(
        id="p7",
        name="Camille Dupasquier",
        role="Beneficiary, Rhône Logistics SA",
        trigger="Succession settled 31 Aug",
        est="CHF 46m",
        domicile="CH · Lausanne",
        updated="5d ago",
        fit=64,
        reason="Succession settled · valuation from filed accounts only",
        watched=False,
    ),
    Prospect(
        id="p9",
        name="Dr. Nadia Perrin",
        role="Employee #4, Genève Biotech Partners",
        trigger="Company-run secondary",
        est="USD 8m",
        domicile="CH · Geneva",
        updated="1w ago",
        fit=41,
        reason="Employee secondary · below mandate threshold, monitor only",
        watched=False,
    ),
]

DOSSIERS: list[Dossier] = [
    Dossier(
        prospect_id="p1",
        name="Elisabeth Brunner",
        role="Chair & 41% shareholder, Helvetia Precision AG · Winterthur, CH",
        tags=["Live trigger", "Industrials", "First-generation wealth", "No existing relationship"],
        stats=[
            Stat(label="Est. proceeds", value="CHF 520m", note="Pre-tax, our estimate"),
            Stat(label="Confidence", value="High", note="3 corroborating sources"),
            Stat(label="Mandate fit", value="92", note="Industrials · CH onshore"),
        ],
        summary=(
            "Brunner chairs a fourth-generation precision components maker in Winterthur "
            "and holds 41% directly plus 6% through a foundation. The agreed sale of a "
            "74% block to TML CV Holdings would be her first liquidity event; she has no "
            "disclosed banking relationship beyond the company’s corporate lender. "
            "Closing is expected in Q1 2027 after WEKO clearance, which leaves a "
            "nine-month window before proceeds land."
        ),
        facts=[
            Fact(
                label="Direct holding",
                value="41.2% of share capital, held personally since the 2011 reorganisation",
                source="SIX filing",
            ),
            Fact(
                label="Indirect holding",
                value="6.0% via Brunner Stiftung, a family foundation registered in Zug",
                source="Commercial register",
            ),
            Fact(
                label="Board seats",
                value="Chair at Helvetia Precision AG; non-executive at two unlisted suppliers",
                source="Annual report 2025",
            ),
            Fact(
                label="Philanthropy",
                value="Named donor to a Winterthur engineering scholarship since 2019",
                source="Foundation report",
            ),
            Fact(
                label="Excluded data",
                value="No political exposure, health or family-structure data collected",
                source="Policy",
            ),
        ],
        timeline=[
            TimelineEvent(
                date="2026-09-04",
                title="Share purchase agreement signed",
                detail="74% block to TML CV Holdings; cash with 15% deferred tranche.",
                tone="amber",
            ),
            TimelineEvent(
                date="2026-06-18",
                title="Advisor mandate reported",
                detail="Press reported a boutique bank running the process.",
                tone="blue",
            ),
            TimelineEvent(
                date="2026-02-02",
                title="Foundation stake increased",
                detail="Brunner Stiftung moved from 4.5% to 6.0%.",
                tone="green",
            ),
            TimelineEvent(
                date="2025-11-30",
                title="Record FY results",
                detail="Revenue CHF 1.1bn, EBITDA margin 18.4%.",
                tone="green",
            ),
        ],
        angles=[
            Angle(
                n="01",
                text="Nine-month window between signing and closing — pre-transaction structuring is still open.",
            ),
            Angle(
                n="02",
                text="Deferred 15% tranche creates a natural conversation about staged liquidity planning.",
            ),
            Angle(
                n="03",
                text="Existing foundation suggests appetite for a structured philanthropy vehicle.",
            ),
        ],
        relations=[
            Relation(name="Jonas Brunner", tie="Son · CFO, 12% holder", strength="Family"),
            Relation(name="Dr. Peter Meier", tie="Co-board member, two suppliers", strength="Strong"),
            Relation(
                name="Winterthur Engineering Fund",
                tie="Named donor since 2019",
                strength="Institutional",
            ),
            Relation(name="TML CV Holdings", tie="Counterparty in current deal", strength="Transactional"),
        ],
    )
]

SOURCES: list[Source] = [
    Source(id="s1", name="Neue Zürcher Zeitung", region="CH", last_pull="06:05", status=SourceStatus.LIVE),
    Source(id="s2", name="Handelszeitung", region="CH", last_pull="06:05", status=SourceStatus.LIVE),
    Source(id="s3", name="Le Temps", region="CH-FR", last_pull="06:07", status=SourceStatus.LIVE),
    Source(id="s4", name="Financial Times", region="UK", last_pull="06:11", status=SourceStatus.LIVE),
    Source(id="s5", name="Il Sole 24 Ore", region="IT", last_pull="05:58", status=SourceStatus.LIVE),
    Source(id="s6", name="SIX disclosure feed", region="CH", last_pull="06:00", status=SourceStatus.LIVE),
    Source(
        id="s7",
        name="Commercial register (Zefix)",
        region="CH",
        last_pull="yesterday",
        status=SourceStatus.DELAYED,
    ),
    Source(id="s8", name="Bloomberg terminal export", region="Global", last_pull="—", status=SourceStatus.LICENCE),
]

TRIGGER_CATEGORIES: list[TriggerCategory] = [
    TriggerCategory(
        key=TriggerType.MA,
        label="M&A / liquidity event",
        description="Share or asset sales where an individual receives cash consideration.",
        volume="134 events · 90 days",
        enabled=True,
    ),
    TriggerCategory(
        key=TriggerType.IPO,
        label="IPO & secondary",
        description="Listings and company-run secondaries with selling shareholders.",
        volume="61 events · 90 days",
        enabled=True,
    ),
    TriggerCategory(
        key=TriggerType.PE_EXIT,
        label="PE exit",
        description="Sponsor exits where management holds equity or rolls over.",
        volume="48 events · 90 days",
        enabled=True,
    ),
    TriggerCategory(
        key=TriggerType.SUCCESSION,
        label="Succession & estate",
        description="Register entries transferring control between generations.",
        volume="32 events · 90 days",
        enabled=True,
    ),
    TriggerCategory(
        key=TriggerType.RESTRUCTURING,
        label="Holding restructuring",
        description="New vehicles or reorganisations that often precede a sale.",
        volume="17 events · 90 days",
        enabled=False,
    ),
]

INGEST_LOG: list[IngestLogEntry] = [
    IngestLogEntry(
        time="07:41 CET",
        text="14 articles classified · 9 matched an existing trigger category, 5 discarded as noise",
    ),
    IngestLogEntry(
        time="06:12 CET",
        text="Helvetia Precision AG · new M&A event created from NZZ, reviewed by M. Roth",
    ),
    IngestLogEntry(time="06:00 CET", text="Morning ingest started across 7 live sources · look-back 3 months"),
    IngestLogEntry(
        time="yesterday 22:15",
        text="Zefix pull failed twice, retried at 06:00 · 1 register entry may be missing",
    ),
]

DESK_TASKS: list[DeskTask] = [
    DeskTask(id=1, label="Call Elisabeth Brunner’s advisor before WEKO filing", meta="Due 09:30 · Helvetia trigger"),
    DeskTask(id=2, label="Review Vaduz Chemicals IPO allocation note", meta="Due 11:00 · with Legal"),
    DeskTask(id=3, label="Sign off Nordkap brief for the Milan desk", meta="Due 14:00", done=True),
    DeskTask(id=4, label="Refresh source licences expiring this month", meta="Due Friday"),
]

WATCHLIST: list[WatchlistItem] = [
    WatchlistItem(
        prospect_id="p3",
        name="Lorenzo Ferretti",
        note="Cash offer on his 18.4% block — offer period opens Monday",
        flag="HOT",
        tone="amber",
    ),
    WatchlistItem(
        prospect_id="p6",
        name="Daniel Wyss",
        note="PE exit closed; rollover leaves EUR 34m unallocated",
        flag="NEW",
        tone="blue",
    ),
    WatchlistItem(
        prospect_id="p4",
        name="Marc Keller",
        note="IPO 12 Sep — lock-up expires March 2027",
        flag="CAL",
        tone="muted",
    ),
    WatchlistItem(
        prospect_id="p7",
        name="Camille Dupasquier",
        note="Succession settled; no contact attempt yet",
        flag="IDLE",
        tone="faint",
    ),
]

KPIS: list[Kpi] = [
    Kpi(label="New triggers · 24h", value="14", delta="+5", tone="amber", note="9 above CHF 50m"),
    Kpi(label="Watchlist touched", value="3", delta="live", tone="blue", note="of 4 tracked"),
    Kpi(label="Briefs enriched · week", value="21", delta="+8", tone="green", note="avg 40 min to first draft"),
    Kpi(label="Sources healthy", value="7/8", delta="1 delayed", tone="amber", note="Zefix retry at 06:00"),
]

QUEUE_COMPOSITION = [
    {"label": "M&A / liquidity", "value": "46%", "pct": 46, "tone": "amber"},
    {"label": "IPO & secondary", "value": "23%", "pct": 23, "tone": "blue"},
    {"label": "PE exits", "value": "19%", "pct": 19, "tone": "green"},
    {"label": "Succession", "value": "12%", "pct": 12, "tone": "muted"},
]

SEARCH_SUGGESTIONS = [
    "Stake sales above CHF 100m in CH since June",
    "IPO secondaries pricing this month",
    "Founders with no existing relationship",
    "Succession events in Romandie",
]

RECENT_BRIEFS = [
    {"id": "p1", "name": "Elisabeth Brunner", "meta": "Helvetia Precision · enriched", "when": "2h"},
    {"id": "p4", "name": "Marc Keller", "meta": "Vaduz Chemicals · enriched", "when": "1d"},
    {"id": "p3", "name": "Lorenzo Ferretti", "meta": "Nordkap Telecom · draft", "when": "2d"},
    {"id": "p7", "name": "Camille Dupasquier", "meta": "Rhône Logistics · draft", "when": "5d"},
]

FILTER_CHIPS = [
    "Live triggers only",
    "CH onshore",
    "> CHF 50m",
    "No relationship",
    "Last 90 days",
]

TOTAL_TRIGGERS = 292
COVERAGE_DAYS = 92


# --- researched_documents (демо для backend=memory) ----------------------

_BRUNNER_MD = """# PROSPECT ENRICHMENT BRIEF
## Public-Source Research | Switzerland

**Prospect name:** Elisabeth Brunner
**Role / relationship to company or group:** Chair and 41% shareholder, Helvetia Precision AG

---

## 1. Executive Assessment

Brunner chairs a fourth-generation precision components maker in Winterthur and holds
41% directly plus 6% through a foundation. The agreed sale of a 74% block to TML CV
Holdings would be her first liquidity event.

## 2. Group, Ownership & Governance

| Entity | Role | Ownership | Source |
|---|---|---|---|
| Helvetia Precision AG | Operating company | 41.2% direct | SIX filing |
| Brunner Stiftung | Family foundation, Zug | 6.0% | Commercial register |

## 3. Liquidity History

Signed 4 Sep, closing expected Q1 2027 subject to WEKO clearance. Cash consideration
with a 15% deferred tranche.

## 4. RM Preparation

- Nine-month window between signing and closing — pre-transaction structuring is still open.
- Deferred 15% tranche opens a conversation about staged liquidity planning.
"""

RESEARCH_DOCUMENTS = [
    {
        "id": "11111111-1111-4111-8111-111111111111",
        "name": "Elisabeth Brunner",
        "normalized_name": "elisabeth brunner",
        "document_type": "person",
        "status": "completed",
        "source_query": "find information about Elisabeth Brunner",
        "researched_at": "2026-09-05 06:12:00+00",
        "full_markdown": _BRUNNER_MD,
    },
    {
        "id": "22222222-2222-4222-8222-222222222222",
        "name": "Vaduz Chemicals Holding",
        "normalized_name": "vaduz chemicals holding",
        "document_type": "company",
        "status": "completed",
        "source_query": "find information about Vaduz Chemicals Holding",
        "researched_at": "2026-09-03 08:05:00+00",
        "full_markdown": "# PROSPECT ENRICHMENT BRIEF\n\n## 1. Executive Assessment\n\nIPO priced at the top of the range; two co-founders sold secondary lines.\n",
    },
    {
        "id": "33333333-3333-4333-8333-333333333333",
        "name": "Lorenzo Ferretti",
        "normalized_name": "lorenzo ferretti",
        "document_type": "person",
        "status": "running",
        "source_query": "find information about Lorenzo Ferretti",
        "researched_at": None,
        "full_markdown": "",
    },
]
