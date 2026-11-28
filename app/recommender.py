"""Deterministic rules engine: AQI + household profile -> actionable plan.

The rules are the source of truth. GenAI (ai.py) only explains this plan in
friendly language, so advice stays grounded and reproducible.
Reduction figures are rough exposure-reduction estimates (see README).
"""
from dataclasses import dataclass, field
from typing import Any

from .aqi import classify
from .i18n import band_label, t

COMMUTES = ("car", "two_wheeler", "public_transit", "walk_cycle", "work_from_home")
COOKING = ("gas", "induction", "biomass")
MAX_REDUCTION_PCT = 85
REDUCTION_WEIGHTS = {
    "sensitive": 0.30, "exercise": 0.15, "mask": 0.25, "midday": 0.08, "errands": 0.05,
    "car_recirc": 0.06, "two_wheeler": 0.12, "walk_cycle": 0.10, "transit": 0.05, "wfh": 0.10,
    "windows": 0.20, "purifier": 0.25, "corsi": 0.20, "mop": 0.04, "gas": 0.05, "biomass": 0.15,
}


@dataclass(frozen=True)
class Profile:
    """Household commute, cooking, and vulnerability attributes."""

    commute: str = "public_transit"
    cooking: str = "gas"
    has_purifier: bool = False
    children: bool = False
    elderly: bool = False
    respiratory: bool = False  # asthma, COPD, heart conditions
    outdoor_exercise: bool = False

    @property
    def sensitive(self) -> bool:
        """Return True when the household includes a sensitive group."""
        return self.children or self.elderly or self.respiratory


@dataclass
class Action:
    """Single exposure-reduction action with category and estimated impact."""

    category: str  # routine | indoor | alternative
    title: str
    why: str
    impact: str
    reduction: float = 0.0  # estimated share of daily PM2.5 exposure avoided


@dataclass
class Plan:
    """Complete deterministic daily clean-air plan."""

    aqi: int
    band: str
    level: int
    actions: list[Action] = field(default_factory=list)
    est_reduction_pct: int = 0
    safety_note: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize the plan to a JSON-friendly dictionary."""
        return {
            "aqi": self.aqi, "band": self.band, "level": self.level,
            "est_reduction_pct": self.est_reduction_pct,
            "safety_note": self.safety_note,
            "actions": [a.__dict__ for a in self.actions],
        }


def _action(category: str, key: str, lang: str, reduction: float = 0.0, **params: Any) -> Action:
    """Build a localized Action from a stable message-ID prefix."""
    return Action(
        category,
        t(f"{key}.title", lang, **params),
        t(f"{key}.why", lang),
        t(f"{key}.impact", lang),
        reduction,
    )


def _sensitive_groups(p: Profile, lang: str = "en") -> str:
    """Format comma-separated localized sensitive-group labels enabled on profile."""
    return ", ".join(
        t(key, lang) for key, flag in (
            ("sensitive.children", p.children),
            ("sensitive.elderly", p.elderly),
            ("sensitive.respiratory", p.respiratory),
        ) if flag
    )


def _routine(p: Profile, lvl: int, lang: str = "en") -> list[Action]:
    """Return localized daily routine actions for the profile and AQI severity level."""
    out = []
    if lvl <= 1:
        return [_action("routine", "act.enjoy", lang)]
    if lvl >= 2 and p.sensitive:
        who = _sensitive_groups(p, lang)
        out.append(_action("routine", "act.sensitive", lang, REDUCTION_WEIGHTS["sensitive"], who=who))
    if p.outdoor_exercise and lvl >= 3:
        out.append(_action("routine", "act.exercise", lang, REDUCTION_WEIGHTS["exercise"]))
    if lvl >= 3:
        out.append(_action("routine", "act.mask", lang, REDUCTION_WEIGHTS["mask"]))
    if lvl >= 2:
        out.append(_action("routine", "act.midday", lang, REDUCTION_WEIGHTS["midday"]))
        out.append(_action("routine", "act.errands", lang, REDUCTION_WEIGHTS["errands"]))
    return out


def _commute(p: Profile, lvl: int, lang: str = "en") -> list[Action]:
    """Return localized commute actions tailored to transport mode and AQI level."""
    if lvl < 2:
        return []
    c = p.commute
    if c == "car":
        return [
            _action("alternative", "act.car_pool", lang),
            _action("routine", "act.car_recirc", lang, REDUCTION_WEIGHTS["car_recirc"]),
        ]
    if c == "two_wheeler":
        return [
            _action("routine", "act.two_wheeler", lang, REDUCTION_WEIGHTS["two_wheeler"]),
            _action("alternative", "act.two_wheeler_metro", lang),
        ]
    if c == "walk_cycle":
        return [_action("routine", "act.walk_cycle", lang, REDUCTION_WEIGHTS["walk_cycle"])]
    if c == "public_transit":
        return [_action("routine", "act.transit", lang, REDUCTION_WEIGHTS["transit"])]
    if c == "work_from_home":
        return [_action("alternative", "act.wfh", lang, REDUCTION_WEIGHTS["wfh"])]
    raise ValueError(f"Unknown commute type: {c}")


def _indoor(p: Profile, lvl: int, lang: str = "en") -> list[Action]:
    """Return localized indoor filtration and cooking actions for the household."""
    out = []
    if lvl >= 2:
        out.append(_action("indoor", "act.windows", lang, REDUCTION_WEIGHTS["windows"]))
        if p.has_purifier:
            out.append(_action("indoor", "act.purifier", lang, REDUCTION_WEIGHTS["purifier"]))
        else:
            out.append(_action("indoor", "act.corsi", lang, REDUCTION_WEIGHTS["corsi"]))
        out.append(_action("indoor", "act.mop", lang, REDUCTION_WEIGHTS["mop"]))
        out.append(_action("indoor", "act.plants", lang))
    if p.cooking == "gas":
        out.append(_action("indoor", "act.gas", lang, REDUCTION_WEIGHTS["gas"]))
    elif p.cooking == "biomass":
        out.append(_action("alternative", "act.biomass", lang, REDUCTION_WEIGHTS["biomass"]))
    return out


def _alternatives(lvl: int, lang: str = "en") -> list[Action]:
    """Return localized community-level pollution-reduction alternatives for AQI >= 51."""
    if lvl < 2:
        return []
    return [
        _action("alternative", "act.burn", lang),
        _action("alternative", "act.idle", lang),
        _action("alternative", "act.diesel", lang),
    ]


def build_plan(aqi: float, p: Profile, lang: str = "en") -> Plan:
    """Build a deterministic localized clean-air action plan for an AQI value and profile."""
    band = classify(aqi)
    actions = (
        _routine(p, band.level, lang)
        + _commute(p, band.level, lang)
        + _indoor(p, band.level, lang)
        + _alternatives(band.level, lang)
    )
    remaining = 1.0
    for a in actions:
        remaining *= 1 - a.reduction
    pct = min(MAX_REDUCTION_PCT, round((1 - remaining) * 100))
    note = t("safety.respiratory", lang) if band.level >= 2 and p.respiratory else ""
    return Plan(round(aqi), band_label(band.level, lang), band.level, actions, pct, note)
