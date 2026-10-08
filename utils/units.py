"""Exact unit boundaries; presentation rounding never changes engine inputs."""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class UnitSystem:
    name: str = "metric"

    def __post_init__(self):
        if self.name not in {"metric", "imperial"}:
            raise ValueError("invalid_unit_system")

    def display(self, value: float, quantity: str) -> str:
        # Source units are those used by the rules engines, never inferred from text.
        definitions = {
            "yards": (0.9144, "m", "yd"),
            "yards_per_second": (0.9144, "m/s", "yd/s"),
            "pounds": (0.45359237, "kg", "lb"),
            "miles": (1.609344, "km", "mi"),
            "miles_per_second": (1.609344, "km/s", "mi/s"),
        }
        if not math.isfinite(value):
            raise ValueError("invalid_quantity")
        factor, metric, imperial = definitions[quantity]
        result = value * factor if self.name == "metric" else value
        return f"{result:.6g} {metric if self.name == 'metric' else imperial}"

    def to_rules(self, value: float, quantity: str) -> float:
        factors = {"yards": 0.9144, "yards_per_second": 0.9144,
                   "pounds": 0.45359237, "miles": 1.609344, "miles_per_second": 1.609344}
        if not math.isfinite(value):
            raise ValueError("invalid_quantity")
        return value / factors[quantity] if self.name == "metric" else value
