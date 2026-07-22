import unittest

from app.services.settings import SettingsService


class FakeSettingsRepository:
    def __init__(self) -> None:
        self.values = {
            "current_year": "2025",
            "roster_standard_min": "14",
            "roster_standard_max": "15",
            "roster_standard_offseason_max": "21",
            "roster_two_way_min": "0",
            "roster_two_way_max": "3",
        }
        self.updates = []

    def get_all(self):
        return dict(self.values)

    def update(self, key, value):
        self.updates.append((key, value))
        self.values[key] = value


class FakeSeasonRollover:
    def __init__(self) -> None:
        self.years = []

    def update_current_year(self, year, **kwargs):
        self.years.append((year, kwargs))
        return {"current_year": year}


class SettingsServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = FakeSettingsRepository()
        self.rollover = FakeSeasonRollover()
        self.service = SettingsService(
            self.repository,
            season_rollover=self.rollover,
            contract_seasons=(2025, 2026, 2027),
            max_start_year=2026,
        )

    def test_normalizes_and_applies_settings(self) -> None:
        result = self.service.update({
            "salary_cap_2025": "160000000",
            "current_year": 2026,
            "free_agency_mode": True,
            "free_agent_reps": ["Agent A", "agent a", "Agent B"],
        })
        self.assertEqual(2026, result["audit"]["current_year"])
        self.assertEqual(2026, self.rollover.years[0][0])
        self.assertEqual("160000000", self.repository.values["salary_cap_2025"])
        self.assertEqual("1", self.repository.values["free_agency_mode"])
        self.assertEqual(["Agent A", "Agent B"], result["audit"]["free_agent_reps"])

    def test_rejects_inconsistent_roster_range(self) -> None:
        with self.assertRaisesRegex(ValueError, "invalid_roster_standard_range"):
            self.service.update({"roster_standard_min": 16})

    def test_requires_at_least_one_supported_setting(self) -> None:
        with self.assertRaisesRegex(ValueError, "settings_payload_required"):
            self.service.update({"unknown": "ignored"})


if __name__ == "__main__":
    unittest.main()
