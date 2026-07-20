import inspect
import unittest

from app.db.repositories.trades import TradeRepository
from app.domain.trade_rules import (
    apron_restriction_issues,
    expanded_tpe_limit,
    first_apron_limited,
    hard_cap_issues,
    minimum_stacking_issue,
    roster_count_issues,
    salary_match_profile,
    second_apron_limited,
    trade_balance_snapshot,
    trade_move_availability,
    trade_roster_limits,
    trade_rule_checklist,
    trade_season,
    trade_thresholds,
)


def player(salary: float = 0.0, *, minimum: bool = False):
    return {"type": "player", "salary": salary, "isMinimumContract": minimum}


class TradeDomainRuleTests(unittest.TestCase):
    def test_expanded_tpe_uses_each_salary_band(self) -> None:
        self.assertEqual(expanded_tpe_limit(5_000_000, 154_647_000), 10_250_000)
        self.assertEqual(expanded_tpe_limit(10_000_000, 154_647_000), 18_527_011)
        self.assertEqual(expanded_tpe_limit(30_000_000, 154_647_000), 37_500_000)

    def test_apron_limits_use_before_or_post_apron_account(self) -> None:
        thresholds = {"firstApron": 195_000_000, "secondApron": 207_000_000}
        flow = {"beforeApronAccount": 190_000_000, "postApronAccount": 208_000_000}

        self.assertTrue(first_apron_limited(flow, thresholds))
        self.assertTrue(second_apron_limited(flow, thresholds))

    def test_season_threshold_roster_and_move_rules_are_domain_owned(self) -> None:
        settings = {
            "current_year": "2026",
            "salary_cap_2026": "160000000",
            "first_apron_2026": "200000000",
            "second_apron_2026": "210000000",
            "roster_standard_min": "14",
            "roster_standard_max": "15",
            "roster_standard_offseason_max": "18",
            "roster_two_way_max": "3",
        }
        season = trade_season(
            {}, settings, contract_min_year=2025, contract_max_year=2031, contract_max_start_year=2026
        )
        thresholds = trade_thresholds(settings, season)
        limits = trade_roster_limits(settings)
        moves = trade_move_availability(
            {"remaining_pre30": 2, "remaining_post30": 3}, "post30"
        )
        balances = trade_balance_snapshot(thresholds, 150_000_000, 190_000_000)

        self.assertEqual(season, 2026)
        self.assertEqual(thresholds["salaryCap"], 160_000_000)
        self.assertEqual(limits["standardOffseasonMax"], 18)
        self.assertEqual(moves["remaining"], 5)
        self.assertEqual(next(row for row in balances if row["key"] == "first_apron")["value"], 10_000_000)

    def test_second_apron_blocks_receiving_more_matching_salary(self) -> None:
        flow = {
            "beforeCap": 210_000_000,
            "postCap": 212_000_000,
            "beforeApronAccount": 210_000_000,
            "postApronAccount": 212_000_000,
            "outgoingSalary": 10_000_000,
            "incomingSalary": 12_000_000,
            "outgoingAssets": [player(10_000_000)],
            "incomingAssets": [player(12_000_000)],
        }
        profile = salary_match_profile(
            flow,
            {"salaryCap": 154_647_000, "firstApron": 195_945_000, "secondApron": 207_824_000},
        )

        self.assertFalse(profile["legal"])
        self.assertEqual(profile["tpe"], "second_apron_block")

    def test_expanded_tpe_is_legal_and_generates_first_apron_hard_cap(self) -> None:
        flow = {
            "beforeCap": 180_000_000,
            "postCap": 185_000_000,
            "beforeApronAccount": 180_000_000,
            "postApronAccount": 185_000_000,
            "outgoingSalary": 10_000_000,
            "incomingSalary": 18_000_000,
            "outgoingAssets": [player(10_000_000)],
            "incomingAssets": [player(18_000_000)],
        }
        profile = salary_match_profile(
            flow,
            {"salaryCap": 154_647_000, "firstApron": 195_945_000, "secondApron": 207_824_000},
        )

        self.assertTrue(profile["legal"])
        self.assertEqual(profile["tpe"], "expanded")
        self.assertEqual(profile["hardCapTrigger"], "first")

    def test_apron_aggregation_and_manual_review_issues_are_domain_owned(self) -> None:
        flow = {
            "beforeApronAccount": 208_000_000,
            "postApronAccount": 209_000_000,
            "incomingSalary": 12_000_000,
            "outgoingAssets": [player(), player()],
        }
        issues = apron_restriction_issues(
            "ATL", flow, {"firstApron": 195_945_000, "secondApron": 207_824_000}
        )

        self.assertTrue(any(issue["rule"] == "second_apron_aggregation" for issue in issues))
        self.assertEqual(sum(issue["rule"] == "manual_review" for issue in issues), 2)

    def test_domain_builds_hard_cap_stacking_roster_and_checklist_messages(self) -> None:
        flow = {
            "postApronAccount": 200_000_000,
            "postRosterStandard": 19,
            "postRosterTwoWay": 4,
            "outgoingAssets": [player(minimum=True), player(minimum=True), player()],
            "incomingAssets": [player()],
        }
        issues = hard_cap_issues(
            "ATL", "first", flow, {"firstApron": 195_945_000, "secondApron": 207_824_000}
        )
        stacking = minimum_stacking_issue("ATL", flow)
        roster = roster_count_issues(
            "ATL",
            flow,
            {"standardMin": 14, "standardMax": 15, "standardOffseasonMax": 18, "twoWayMin": 0, "twoWayMax": 3},
        )
        all_issues = [*issues, stacking, *roster]
        checklist = trade_rule_checklist(all_issues, 4, ["Salary passes"])

        self.assertEqual(next(row for row in checklist if row["key"] == "hard_cap")["status"], "fail")
        self.assertEqual(next(row for row in checklist if row["key"] == "minimum_stacking")["status"], "warning")
        self.assertEqual(next(row for row in checklist if row["key"] == "roster_count")["status"], "fail")

    def test_repository_no_longer_implements_pure_legality_helpers(self) -> None:
        source = inspect.getsource(TradeRepository)
        for method in (
            "_trade_machine_expanded_tpe_limit",
            "_trade_machine_first_apron_limited",
            "_trade_machine_second_apron_limited",
            "_trade_machine_salary_match_profile",
            "_trade_machine_rule_checklist",
        ):
            self.assertNotIn(f"def {method}", source)


if __name__ == "__main__":
    unittest.main()
