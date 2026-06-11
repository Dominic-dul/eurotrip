"""Quick logic test: mock the API layer, verify ranking + message + guards."""
import datetime as dt
import weather_bot as wb

# Build fake forecasts: Krakow driest, Gdansk wettest.
def fake(region, probs, sums):
    dates = [(dt.date(2026, 6, 13) + dt.timedelta(days=i)).isoformat()
             for i in range(len(probs))]
    return wb.RegionForecast(region, dates, probs, sums)

sample = [
    fake(wb.Region("Vilnius", "LT", 0, 0), [40, 50, 30, 20, 60, 45, 35, 50, 40], [2, 3, 1, 0, 5, 2, 1, 3, 2]),
    fake(wb.Region("Krakow", "PL", 0, 0), [10, 5, 0, 15, 10, 5, 20, 10, 5], [0, 0, 0, 1, 0, 0, 1, 0, 0]),
    fake(wb.Region("Gdansk", "PL", 0, 0), [70, 80, 65, 60, 75, 90, 55, 70, 80], [8, 10, 7, 6, 9, 12, 5, 8, 10]),
    fake(wb.Region("Riga", "LV", 0, 0), [30, 25, 40, 35, 20, 30, 25, 30, 35], [2, 1, 3, 2, 1, 2, 1, 2, 3]),
    # A region with a missing value to test None handling
    fake(wb.Region("Kaunas", "LT", 0, 0), [20, None, 25, 30, 15, 20, None, 25, 20], [1, None, 2, 2, 1, 1, None, 2, 1]),
]

ranked = wb.rank(sample)
print("RANK ORDER:", [r.region.name for r in ranked])
assert ranked[0].region.name == "Krakow", "driest should win"
assert ranked[-1].region.name == "Gdansk", "wettest should be last"

# Per-day pivot checks
days = wb.daily_rankings(sample)
print("DAYS COVERED:", len(days))
assert len(days) == 9, "should cover all 9 dates"
# Day 1 (index 0): probs Vilnius40 Krakow10 Gdansk70 Riga30 Kaunas20 -> Krakow driest
assert days[0][1][0].region.name == "Krakow", "Krakow driest on day 1"
# Day 2 (index 1): Kaunas is None that day, so it must be skipped, not crash
day2_names = [p.region.name for p in days[1][1]]
assert "Kaunas" not in day2_names, "Kaunas (None on day 2) should be skipped"
print("Day-1 driest:", days[0][1][0].region.name,
      f"{days[0][1][0].rain_prob:.0f}%  backup:", days[0][1][1].region.name)
print("Day-2 cities ranked (Kaunas skipped):", day2_names)

print("\n----- MESSAGE PREVIEW -----")
print(wb.build_message(ranked, "2026-06-13", "2026-06-21"))

print("\n----- GUARD TESTS -----")
# In range: target 5 days from "today"
print("in range (today=2026-06-08):",
      wb.window_is_in_range("2026-06-13", dt.date(2026, 6, 8)))
# Out of range: target 40 days out
print("out of range (today=2026-05-01):",
      wb.window_is_in_range("2026-06-13", dt.date(2026, 5, 1)))
assert wb.window_is_in_range("2026-06-13", dt.date(2026, 6, 8)) is True
assert wb.window_is_in_range("2026-06-13", dt.date(2026, 5, 1)) is False
print("\nALL ASSERTIONS PASSED")
