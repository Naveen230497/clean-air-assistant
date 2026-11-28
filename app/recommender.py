"""Deterministic rules engine: AQI + household profile -> actionable plan.

The rules are the source of truth. GenAI (ai.py) only explains this plan in
friendly language, so advice stays grounded and reproducible.
Reduction figures are rough exposure-reduction estimates (see README).
"""
from dataclasses import dataclass, field
from typing import Any

from .aqi import classify

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


def _sensitive_groups(p: Profile) -> str:
    """Format comma-separated sensitive group labels enabled on profile."""
    return ", ".join(
        n for n, f in (
            ("children", p.children),
            ("older adults", p.elderly),
            ("people with lung/heart conditions", p.respiratory),
        ) if f
    )


def _routine(p: Profile, lvl: int) -> list[Action]:
    """Return daily routine actions for the given profile and AQI severity level."""
    out = []
    if lvl <= 1:
        out.append(Action("routine", "Enjoy outdoor time and air out your home",
                          "Air quality is acceptable, so ventilation dilutes indoor pollutants.",
                          "Opening windows 10-15 min flushes cooking fumes and CO2."))
        return out
    if lvl >= 2 and p.sensitive:
        who = _sensitive_groups(p)
        out.append(Action("routine", f"Keep outdoor time short for {who}",
                          "These groups are affected at lower AQI levels.",
                          "Moving play and walks indoors cuts their exposure by roughly 30%.",
                          REDUCTION_WEIGHTS["sensitive"]))
    if p.outdoor_exercise and lvl >= 3:
        out.append(Action("routine", "Move exercise indoors today",
                          "Hard breathing multiplies how much PM2.5 reaches the lungs.",
                          "Indoor workout avoids several times the inhaled dose of a jog outside.",
                          REDUCTION_WEIGHTS["exercise"]))
    if lvl >= 3:
        out.append(Action("routine", "Wear a well-fitted N95/FFP2 mask outdoors",
                          "Cloth and loose surgical masks let fine particles through; a sealed N95 filters about 95%.",
                          "Cuts the PM2.5 you inhale outdoors by up to ~90% with a good seal.",
                          REDUCTION_WEIGHTS["mask"]))
    if lvl >= 2:
        out.append(Action("routine", "Run errands between 12:00 and 16:00",
                          "In winter, cold air traps pollution near the ground; "
                          "it is usually worst early morning and late evening.",
                          "Midday trips often see noticeably lower PM2.5 than 6-10 am.",
                          REDUCTION_WEIGHTS["midday"]))
        out.append(Action("routine", "Combine errands into one trip",
                          "Fewer trips mean less time outside and fewer vehicle emissions.",
                          "One trip instead of three saves ~2/3 of that travel emissions and exposure.",
                          REDUCTION_WEIGHTS["errands"]))
    return out


def _commute(p: Profile, lvl: int) -> list[Action]:
    """Return commute actions tailored to transport mode and AQI level."""
    if lvl < 2:
        return []
    c = p.commute
    if c == "car":
        return [Action("alternative", "Carpool or take metro/bus for at least some days",
                       "Cars are a major urban PM2.5 and NOx source.",
                       "Public transit emits roughly 3-4x less CO2 per passenger-km than a solo car.", 0.0),
                Action("routine", "Keep car windows up and set AC to recirculate",
                       "Traffic queues have the highest roadside pollution.",
                       "Recirculation can lower in-cabin particles by about 30-50%.",
                       REDUCTION_WEIGHTS["car_recirc"])]
    if c == "two_wheeler":
        return [Action("routine", "Wear an N95 and avoid the peak-traffic corridors",
                       "Riders breathe unfiltered roadside air.",
                       "Mask plus quieter side roads can halve your commute dose.",
                       REDUCTION_WEIGHTS["two_wheeler"]),
                Action("alternative", "Switch to metro/bus when AQI is above 200",
                       "Enclosed transit with a mask exposes you to less tailpipe smoke.",
                       "Also removes your own emissions from the street.")]
    if c == "walk_cycle":
        return [Action("routine", "Choose parks or low-traffic lanes and wear an N95 if AQI > 150",
                       "Pollution drops quickly with distance from heavy roads.",
                       "A route 100+ m from a main road can reduce exposure by ~20-30%.",
                       REDUCTION_WEIGHTS["walk_cycle"])]
    if c == "public_transit":
        return [Action("routine", "Mask up at stations and bus stops",
                       "Waiting areas near traffic are exposure hotspots.",
                       "A mask during waits cuts the biggest roadside dose.",
                       REDUCTION_WEIGHTS["transit"])]
    if c == "work_from_home":
        return [Action("alternative", "Keep working from home on high-AQI days",
                       "Zero commute exposure and zero commute emissions.",
                       "Avoids your whole commute dose and its CO2.",
                       REDUCTION_WEIGHTS["wfh"])]
    raise ValueError(f"Unknown commute type: {c}")


def _indoor(p: Profile, lvl: int) -> list[Action]:
    """Return indoor filtration and cooking actions for the household."""
    out = []
    if lvl >= 2:
        out.append(Action("indoor", "Keep windows closed during peak pollution hours and seal gaps",
                          "Outdoor PM2.5 seeps in through cracks and open windows.",
                          "Closed windows can keep indoor PM2.5 about 30-50% below outdoors.",
                          REDUCTION_WEIGHTS["windows"]))
        if p.has_purifier:
            out.append(Action("indoor", "Run your purifier on high in the room you use most, door closed",
                              "Purifiers clean only the air in their room; keep filters fresh.",
                              "A HEPA purifier can cut indoor PM2.5 by 50-80%.",
                              REDUCTION_WEIGHTS["purifier"]))
        else:
            out.append(Action("indoor", "Build a DIY Corsi-Rosenthal box fan filter",
                              "A box fan with four MERV-13 filters is a low-cost purifier.",
                              "Can cut indoor PM2.5 by roughly 50-70% for a fraction of purifier cost.",
                              REDUCTION_WEIGHTS["corsi"]))
        out.append(Action("indoor", "Wet-mop instead of dry sweeping; skip incense, candles and mosquito coils",
                          "Sweeping re-suspends dust and burning adds indoor smoke.",
                          "Removes common indoor particle sources.", REDUCTION_WEIGHTS["mop"]))
        out.append(Action("indoor", "Know that indoor plants will not clean your air",
                          "Studies show plants remove negligible pollutants at room scale.",
                          "Spend effort on filters and sealing instead."))
    if p.cooking == "gas":
        out.append(Action("indoor", "Use the chimney or exhaust fan while cooking",
                          "Gas stoves emit NO2 and fine particles.",
                          "Venting removes most cooking pollutants at the source.", REDUCTION_WEIGHTS["gas"]))
    elif p.cooking == "biomass":
        out.append(Action("alternative", "Move to LPG or induction cooking where possible",
                          "Wood and dung smoke is among the worst household PM2.5 sources.",
                          "Cuts household PM2.5 dramatically and protects the cook's lungs.",
                          REDUCTION_WEIGHTS["biomass"]))
    return out


def _alternatives(lvl: int) -> list[Action]:
    """Return community-level pollution-reduction alternatives for AQI >= 51."""
    if lvl < 2:
        return []
    return [
        Action("alternative", "Never burn waste, leaves or wood for warmth",
               "Open burning is a leading winter smog source.",
               "Use an electric heater or extra layers; report burning to local authorities."),
        Action("alternative", "Switch off engines at red lights and long waits",
               "Idling vehicles emit without moving anyone.",
               "Over 60 s idle burns more fuel than restarting."),
        Action("alternative", "Avoid diesel generators; use inverter/battery backup",
               "Small generators emit high particulate and NOx loads.",
               "Reduces local air pollution on your street."),
    ]


def build_plan(aqi: float, p: Profile) -> Plan:
    """Build a deterministic clean-air action plan for an AQI value and profile."""
    band = classify(aqi)
    actions = _routine(p, band.level) + _commute(p, band.level) + _indoor(p, band.level) + _alternatives(band.level)
    remaining = 1.0
    for a in actions:
        remaining *= 1 - a.reduction
    pct = min(MAX_REDUCTION_PCT, round((1 - remaining) * 100))
    note = ""
    if band.level >= 2 and p.respiratory:
        note = ("Follow your doctor's action plan, keep reliever medication handy and seek medical care "
                "if you have breathlessness, chest pain or worsening symptoms. This is not medical advice.")
    return Plan(round(aqi), band.label, band.level, actions, pct, note)
