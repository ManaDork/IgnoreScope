from PyQt6.QtGui import QFont


class QFontWrapper(QFont):
    """QFont subclass with dict-driven property management."""

    _SETTER_MAP = {
        "family":            "setFamily",
        "pointSize":         "setPointSize",
        "pointSizeF":        "setPointSizeF",
        "pixelSize":         "setPixelSize",
        "bold":              "setBold",
        "italic":            "setItalic",
        "underline":         "setUnderline",
        "strikeOut":         "setStrikeOut",
        "overline":          "setOverline",
        "weight":            "setWeight",
        "stretch":           "setStretch",
        "kerning":           "setKerning",
        "fixedPitch":        "setFixedPitch",
        "capitalization":    "setCapitalization",
        "letterSpacing":     "setLetterSpacing",
        "wordSpacing":       "setWordSpacing",
        "hintingPreference": "setHintingPreference",
        "styleStrategy":     "setStyleStrategy",
        "styleName":         "setStyleName",
    }

    # letterSpacing omitted: getter requires SpacingType arg, doesn't
    # match simple getter() pattern. Always treated as non-default.
    _GETTER_MAP = {
        "family":            "family",
        "pointSize":         "pointSize",
        "pointSizeF":        "pointSizeF",
        "pixelSize":         "pixelSize",
        "bold":              "bold",
        "italic":            "italic",
        "underline":         "underline",
        "strikeOut":         "strikeOut",
        "overline":          "overline",
        "weight":            "weight",
        "stretch":           "stretch",
        "kerning":           "kerning",
        "fixedPitch":        "fixedPitch",
        "capitalization":    "capitalization",
        "wordSpacing":       "wordSpacing",
        "hintingPreference": "hintingPreference",
        "styleStrategy":     "styleStrategy",
        "styleName":         "styleName",
    }

    def __init__(self, props: dict = None, **kwargs):
        super().__init__()
        self._props = {}

        merged = {**(props or {}), **kwargs}
        if merged:
            self._props = dict(merged)
            self._apply_all()

    # ── Public API ──────────────────────────────────────────────

    def set(self, props: dict):
        """Update existing keys only. Ignores keys not already stored."""
        for key, value in props.items():
            if key not in self._props:
                continue
            if self._is_default(key, value):
                continue
            self._props[key] = value
            self._apply_one(key, value)
        return self

    def add(self, props: dict):
        """Update existing or insert new keys. Skips if value matches default."""
        for key, value in props.items():
            if key not in self._SETTER_MAP:
                raise KeyError(f"Unknown font property: '{key}'")
            if self._is_default(key, value):
                continue
            self._props[key] = value
            self._apply_one(key, value)
        return self

    def remove(self, *keys: str):
        """Remove keys from store, rebuild font from scratch with remaining props."""
        for key in keys:
            self._props.pop(key, None)
        self._rebuild()
        return self

    # ── Accessors ───────────────────────────────────────────────

    @property
    def props(self) -> dict:
        """Return a copy of the current stored properties."""
        return dict(self._props)

    # ── Internals ───────────────────────────────────────────────

    def _apply_one(self, key: str, value):
        """Apply a single property to the QFont."""
        setter_name = self._SETTER_MAP.get(key)
        if setter_name is None:
            raise KeyError(f"Unknown font property: '{key}'")
        setter = getattr(self, setter_name)
        if isinstance(value, tuple):
            setter(*value)
        else:
            setter(value)

    def _apply_all(self):
        """Apply all stored properties."""
        for key, value in self._props.items():
            self._apply_one(key, value)

    def _rebuild(self):
        """Reset to clean QFont defaults, reapply stored props."""
        super().__init__()
        self._apply_all()

    def _is_default(self, key: str, value) -> bool:
        """Check if a value matches the QFont default for that property."""
        getter_name = self._GETTER_MAP.get(key)
        if getter_name is None:
            return False
        default_value = getattr(QFont(), getter_name)()
        return value == default_value
