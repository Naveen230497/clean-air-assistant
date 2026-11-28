"""Per-language message catalogs for backend clean-air recommendations and fallbacks."""
from . import bn, en, hi, mr, ta, te

LANG_PACKS: dict[str, dict[str, str]] = {
    "en": en.MESSAGES,
    "hi": hi.MESSAGES,
    "te": te.MESSAGES,
    "ta": ta.MESSAGES,
    "bn": bn.MESSAGES,
    "mr": mr.MESSAGES,
}
