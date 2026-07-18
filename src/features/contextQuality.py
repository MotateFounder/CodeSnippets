from src.ui.heat_bar import HeatBar


class contextQuality:
    IMPORTANCE_WEIGHTS = {
        "low": 0.15,
        "mid": 0.35,
        "high": 0.50,
    }

    def __init__(self, master=None, length=180):
        self.characteristics = {}
        self.heat_bar = HeatBar(master, length=length, value=0.0) if master is not None else None

    def add(self, name, importance):
        name = self._validate_name(name)
        importance = self._validate_importance(importance)
        current = self.characteristics.get(name, {})
        self.characteristics[name] = {
            "importance": importance,
            "value": self._clamp(current.get("value", 0.0)),
        }
        self._update_heat_bar()

    def set(self, name, value):
        name = self._validate_name(name)
        if name not in self.characteristics:
            self.add(name, "mid")
        self.characteristics[name]["value"] = self._clamp(value)
        self._update_heat_bar()

    def set_many(self, values, importances=None):
        importances = importances or {}
        for name, value in (values or {}).items():
            if name not in self.characteristics:
                self.add(name, importances.get(name, "mid"))
            self.set(name, value)

    def set_tooltip(self, text):
        if self.heat_bar is not None and hasattr(self.heat_bar, "set_tooltip"):
            self.heat_bar.set_tooltip(text)

    def get(self, name):
        name = self._validate_name(name)
        if name not in self.characteristics:
            return 0.0
        return self.characteristics[name]["value"]

    def remove(self, name):
        name = self._validate_name(name)
        self.characteristics.pop(name, None)
        self._update_heat_bar()

    def score(self):
        weighted_total = 0.0
        weight_total = 0.0
        for characteristic in self.characteristics.values():
            weight = self.IMPORTANCE_WEIGHTS[characteristic["importance"]]
            weighted_total += weight * characteristic["value"]
            weight_total += weight
        if weight_total == 0.0:
            return 0.0
        return self._clamp(weighted_total / weight_total)

    def reset(self):
        self.characteristics.clear()
        self._update_heat_bar()

    def _update_heat_bar(self):
        if self.heat_bar is not None:
            self.heat_bar.set_value(self.score())

    def _validate_name(self, name):
        if name is None:
            raise ValueError("Context quality characteristic name is required.")
        name = str(name).strip()
        if not name:
            raise ValueError("Context quality characteristic name cannot be empty.")
        return name

    def _validate_importance(self, importance):
        importance = str(importance).strip().lower()
        if importance not in self.IMPORTANCE_WEIGHTS:
            accepted = ", ".join(sorted(self.IMPORTANCE_WEIGHTS))
            raise ValueError("Context quality importance must be one of: {0}.".format(accepted))
        return importance

    def _clamp(self, value):
        try:
            value = float(value)
        except (TypeError, ValueError):
            value = 0.0
        return max(0.0, min(1.0, value))


if __name__ == "__main__":
    quality = contextQuality(length=180)
    quality.add("goal", "mid")
    quality.set("goal", 0.6)
    quality.add("clarity", "low")
    quality.set("clarity", 0.9)
    print("Context score:", quality.score())
