"""AQI classification (US AQI scale, 0-500)."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Band:
    """EPA US AQI severity band with numeric level (0-5) and label."""

    level: int  # 0 (best) .. 5 (worst)
    label: str


_BANDS = (
    (50, Band(0, "Good")),
    (100, Band(1, "Moderate")),
    (150, Band(2, "Unhealthy for sensitive groups")),
    (200, Band(3, "Unhealthy")),
    (300, Band(4, "Very unhealthy")),
    (500, Band(5, "Hazardous")),
)


def classify(aqi: float) -> Band:
    """Return the band for an AQI value; raises ValueError if out of range."""
    if not 0 <= aqi <= 500:
        raise ValueError("AQI must be between 0 and 500")
    for upper, band in _BANDS:
        if aqi <= upper:
            return band
    raise ValueError("AQI must be between 0 and 500")  # pragma: no cover
