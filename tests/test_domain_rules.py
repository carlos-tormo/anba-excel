import unittest

from app.domain_rules import (
    ROSTER_STANDARD_MAX_DEFAULT,
    cap_hold_amount,
    minimum_salary_for_season,
    open_roster_spot_cap_hold,
    parse_amount_like,
    parse_float,
    public_settings_payload,
)


class DomainRulesTests(unittest.TestCase):
    def test_money_parsing_preserves_existing_formats(self) -> None:
        self.assertEqual(1_234_567, parse_amount_like("1.234.567"))
        self.assertEqual(231.66, parse_amount_like("231.66"))
        self.assertEqual(1234.5, parse_float("1 234,5"))

    def test_public_settings_payload_applies_roster_defaults(self) -> None:
        payload = public_settings_payload({"current_year": "2025", "salary_cap_2025": "154647000"})

        self.assertEqual(2025, payload["current_year"])
        self.assertEqual(ROSTER_STANDARD_MAX_DEFAULT, payload["roster_standard_max"])
        self.assertEqual("pre30", payload["trade_move_phase"])

    def test_cap_hold_amount_uses_early_bird_multiplier(self) -> None:
        row = {
            "salary_2025_num": 10_000_000,
            "salary_2026_text": "EB",
            "bird_rights": "Reg",
        }
        settings = {"free_agency_mode": "1", "current_year": "2025"}

        self.assertEqual(13_000_000, cap_hold_amount(row, 2026, settings, 154_647_000))

    def test_two_way_qo_hold_uses_one_year_minimum(self) -> None:
        row = {
            "salary_2025_num": 636_435,
            "salary_2026_text": "QO",
            "bird_rights": "TW",
            "is_two_way": 1,
        }
        settings = {"free_agency_mode": "1", "current_year": "2025"}

        self.assertEqual(
            minimum_salary_for_season(154_647_000, 1, 1),
            cap_hold_amount(row, 2026, settings, 154_647_000),
        )

    def test_open_roster_spot_hold_uses_rookie_minimum_and_excludes_two_ways(self) -> None:
        settings = {"free_agency_mode": "1", "current_year": "2025"}
        players = [
            {"salary_2026_num": 10_000_000, "bird_rights": "Reg"},
            {"salary_2025_num": 636_435, "salary_2026_text": "QO", "bird_rights": "TW", "is_two_way": 1},
            {"salary_2026_num": 2_000_000, "bird_rights": "E10"},
        ]

        result = open_roster_spot_cap_hold(players, 2026, settings, 154_647_000)

        self.assertEqual(1, result["roster_count"])
        self.assertEqual(11, result["open_spots"])
        self.assertEqual(
            11 * minimum_salary_for_season(154_647_000, 0, 1),
            result["amount"],
        )


if __name__ == "__main__":
    unittest.main()
