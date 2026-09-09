"""Доменные модели.

Обычные dataclass-объекты, не привязанные к конкретному хранилищу.
Когда появится реальная БД, поверх этих же структур встанет ORM-слой
(см. app/repositories/base.py — интерфейсы репозиториев остаются теми же).
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from typing import Any


def _serialize(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, list):
        return [_serialize(v) for v in value]
    if isinstance(value, dict):
        return {k: _serialize(v) for k, v in value.items()}
    return value


class Serializable:
    """Общий to_dict для всех доменных моделей."""

    def to_dict(self) -> dict[str, Any]:
        return {k: _serialize(v) for k, v in asdict(self).items()}


# --- справочники ---------------------------------------------------------

class TriggerType:
    MA = "M&A / Liquidity"
    IPO = "IPO / Secondary"
    SECONDARY = "Secondary"
    PE_EXIT = "PE Exit"
    SUCCESSION = "Succession"
    RESTRUCTURING = "Restructuring"

    ALL = [MA, IPO, SECONDARY, PE_EXIT, SUCCESSION, RESTRUCTURING]


class Confidence:
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class SourceStatus:
    LIVE = "Live"
    DELAYED = "Delayed"
    LICENCE = "Licence"


# --- модели --------------------------------------------------------------

@dataclass
class Person(Serializable):
    """Физлицо, попавшее в периметр триггера."""

    id: str
    name: str
    role: str


@dataclass
class Trigger(Serializable):
    id: str
    date: date
    company: str
    headline: str
    type: str
    source: str
    principal: str
    est: str
    confidence: str
    confidence_pct: int
    parties: str
    context: str
    url: str
    ingested_at: str
    reviewer: str
    people: list[Person] = field(default_factory=list)

    @property
    def heat(self) -> str:
        """Цвет индикатора: производная от уровня уверенности."""
        return {
            Confidence.HIGH: "amber",
            Confidence.MEDIUM: "blue",
            Confidence.LOW: "green",
        }.get(self.confidence, "blue")


@dataclass
class Prospect(Serializable):
    id: str
    name: str
    role: str
    trigger: str
    est: str
    domicile: str
    updated: str
    fit: int = 0
    reason: str = ""
    watched: bool = False


@dataclass
class Fact(Serializable):
    label: str
    value: str
    source: str


@dataclass
class TimelineEvent(Serializable):
    date: str
    title: str
    detail: str
    tone: str = "blue"  # blue | amber | green


@dataclass
class Angle(Serializable):
    n: str
    text: str


@dataclass
class Relation(Serializable):
    name: str
    tie: str
    strength: str


@dataclass
class Stat(Serializable):
    label: str
    value: str
    note: str


@dataclass
class Dossier(Serializable):
    prospect_id: str
    name: str
    role: str
    tags: list[str] = field(default_factory=list)
    stats: list[Stat] = field(default_factory=list)
    summary: str = ""
    facts: list[Fact] = field(default_factory=list)
    timeline: list[TimelineEvent] = field(default_factory=list)
    angles: list[Angle] = field(default_factory=list)
    relations: list[Relation] = field(default_factory=list)
    enriched: bool = True


@dataclass
class Source(Serializable):
    id: str
    name: str
    region: str
    last_pull: str
    status: str


@dataclass
class TriggerCategory(Serializable):
    key: str
    label: str
    description: str
    volume: str
    enabled: bool = True


@dataclass
class IngestLogEntry(Serializable):
    time: str
    text: str


@dataclass
class DeskTask(Serializable):
    id: int
    label: str
    meta: str
    done: bool = False


@dataclass
class WatchlistItem(Serializable):
    prospect_id: str
    name: str
    note: str
    flag: str
    tone: str  # amber | blue | muted | faint


@dataclass
class Kpi(Serializable):
    label: str
    value: str
    delta: str
    tone: str
    note: str
