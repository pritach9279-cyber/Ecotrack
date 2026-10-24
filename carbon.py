"""Carbon assessment calculations and configurable default factors."""

DEFAULT_FACTORS = {
    "food": {"vegan": 1.0, "vegetarian": 1.5, "eggetarian": 1.8,
             "mostly_vegetarian": 2.0, "flexitarian": 2.4, "non_vegetarian": 3.3},
    "travel": {"petrol_car": 0.14, "diesel_car": 0.17, "cng_car": 0.10,
               "hybrid_car": 0.08, "electric_car": 0.02, "petrol_bike": 0.05,
               "electric_bike": 0.01, "bus": 0.03, "train": 0.02,
               "auto": 0.08, "taxi": 0.14, "flight": 0.18},
    "electricity": {"grid": 0.82},
    "waste": {"organic": 0.10, "paper": 0.70, "plastic": 2.50,
              "glass": 0.85, "metal": 1.80, "other": 0.50},
}


def _number(value):
    try:
        return max(0.0, float(value or 0))
    except (TypeError, ValueError):
        return 0.0


def calculate_assessment(data, factors=None):
    """Return monthly, annual and category CO2e estimates from assessment data."""
    factors = factors or DEFAULT_FACTORS
    food_key = data.get("diet_type", "vegetarian").lower().replace(" ", "_")
    food = _number(factors["food"].get(food_key, 1.5)) * 30

    travel = 0.0
    for key, factor in factors["travel"].items():
        travel += _number(data.get(key)) * factor
    travel += _number(data.get("domestic_flights")) * 500 * factors["travel"]["flight"] / 12
    travel += _number(data.get("international_flights")) * 2500 * factors["travel"]["flight"] / 12

    electricity = _number(data.get("electricity_kwh")) * factors["electricity"]["grid"]
    if not data.get("electricity_kwh"):
        for appliance in data.get("appliances", []):
            electricity += (_number(appliance.get("quantity")) *
                            _number(appliance.get("wattage")) *
                            _number(appliance.get("hours_per_day")) *
                            _number(appliance.get("days_per_month", 30)) / 1000) * factors["electricity"]["grid"]
    electricity = max(0.0, electricity - _number(data.get("solar_generation")) * factors["electricity"]["grid"])

    waste = sum(_number(data.get(key)) * factor for key, factor in factors["waste"].items())
    monthly = {"food": food, "travel": travel, "electricity": electricity, "waste": waste}
    total = round(sum(monthly.values()), 2)
    return {"monthly": monthly, "total_monthly": total,
            "total_yearly": round(total * 12, 2), "tonnes_yearly": round(total * 12 / 1000, 2)}


def footprint_status(yearly_kg):
    if yearly_kg < 2000:
        return "Lower estimated footprint"
    if yearly_kg < 5000:
        return "Moderate estimated footprint"
    return "Higher estimated footprint"