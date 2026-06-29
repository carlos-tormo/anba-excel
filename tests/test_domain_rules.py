import unittest

from app.domain_rules import (
    ROSTER_STANDARD_MAX_DEFAULT,
    cap_hold_amount,
    minimum_salary_for_season,
    open_roster_spot_cap_hold,
    parse_amount_like,
    parse_float,
    parse_free_agent_rep_discord_ids,
    public_settings_payload,
    apply_salary_floor,
    roster_contract_counts,
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
        self.assertEqual(139_182_300, payload["salary_floor_2025"])

    def test_salary_floor_applies_only_outside_free_agency_mode(self) -> None:
        settings = {"salary_floor_2025": "90000000", "free_agency_mode": "0"}
        self.assertEqual(90_000_000, apply_salary_floor(settings, 2025, 100_000_000, 50_000_000))

        settings["free_agency_mode"] = "1"
        self.assertEqual(50_000_000, apply_salary_floor(settings, 2025, 100_000_000, 50_000_000))

    def test_free_agent_rep_discord_ids_accept_admin_text_format(self) -> None:
        result = parse_free_agent_rep_discord_ids(
            "Agente Uno = <@123456789012345678>\n"
            "Agente Dos: 987654321098765432\n"
            "sin delimitador\n"
            "Agente Malo = abc"
        )

        self.assertEqual(
            {
                "Agente Uno": "123456789012345678",
                "Agente Dos": "987654321098765432",
            },
            result,
        )

    def test_cap_hold_amount_uses_early_bird_multiplier(self) -> None:
        row = {
            "salary_2025_num": 10_000_000,
            "salary_2026_text": "EB",
            "bird_rights": "Reg",
        }
        settings = {"free_agency_mode": "1", "current_year": "2025"}

        self.assertEqual(13_000_000, cap_hold_amount(row, 2026, settings, 154_647_000))

    def test_cap_hold_amount_is_capped_by_low_yos_max_salary(self) -> None:
        row = {
            "salary_2025_num": 20_000_000,
            "salary_2026_text": "QO",
            "bird_rights": "R",
            "experience_years": 6,
        }
        settings = {
            "free_agency_mode": "1",
            "current_year": "2025",
            "average_salary_2025": "10000000",
        }

        self.assertEqual(25_000_000, cap_hold_amount(row, 2026, settings, 100_000_000))

    def test_cap_hold_amount_uses_highest_max_tier_when_yos_missing(self) -> None:
        row = {
            "salary_2025_num": 40_000_000,
            "salary_2026_text": "FB",
            "bird_rights": "Reg",
        }
        settings = {
            "free_agency_mode": "1",
            "current_year": "2025",
            "average_salary_2025": "10000000",
        }

        self.assertEqual(35_000_000, cap_hold_amount(row, 2026, settings, 100_000_000))

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

    def test_standard_cap_holds_count_for_open_roster_minimum_not_roster_limit(self) -> None:
        settings = {
            "free_agency_mode": "1",
            "current_year": "2025",
            "average_salary_2025": "13254485",
        }
        players = [
            {"salary_2026_num": 10_000_000, "bird_rights": "Reg"}
            for _ in range(10)
        ] + [
            {"salary_2025_num": 5_000_000, "salary_2026_text": "FB", "bird_rights": "Reg"}
            for _ in range(8)
        ]

        open_roster_hold = open_roster_spot_cap_hold(players, 2026, settings, 154_647_000)
        roster_counts = roster_contract_counts(players, 2026)

        self.assertEqual(18, open_roster_hold["roster_count"])
        self.assertEqual(0, open_roster_hold["open_spots"])
        self.assertEqual({"standard": 10, "two_way": 0}, roster_counts)

    def test_two_way_contracts_count_only_against_two_way_roster_limit(self) -> None:
        settings = {"free_agency_mode": "1", "current_year": "2025"}
        players = [
            {"salary_2026_num": 10_000_000, "bird_rights": "Reg"},
            {"salary_2026_num": 636_435, "bird_rights": "TW", "is_two_way": 1},
            {"salary_2025_num": 636_435, "salary_2026_text": "QO", "bird_rights": "TW", "is_two_way": 1},
        ]

        open_roster_hold = open_roster_spot_cap_hold(players, 2026, settings, 154_647_000)
        roster_counts = roster_contract_counts(players, 2026)

        self.assertEqual(1, open_roster_hold["roster_count"])
        self.assertEqual(11, open_roster_hold["open_spots"])
        self.assertEqual({"standard": 1, "two_way": 1}, roster_counts)


if __name__ == "__main__":
    unittest.main()
