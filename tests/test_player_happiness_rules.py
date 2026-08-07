import unittest

from app.domain.player_happiness import (
    EVENT_MODIFIER,
    EVENT_TEAM_JOIN,
    EVENT_TEAM_OBJECTIVE_JOIN_CONTEXT,
    EVENT_TEAM_OBJECTIVE_RESOLUTION,
    EVENT_TEAM_OBJECTIVE_SET,
    EVENT_TRADE_REQUEST_FOLLOWUP,
    MILESTONE_PRIVATE_TRADE_REQUEST,
    MILESTONE_PUBLIC_TRADE_REQUEST,
    MILESTONE_PRIORITIZE_DESTINATION,
    MILESTONE_PRIORITIZE_OTHER_DESTINATIONS,
    MILESTONE_REFUSE_TO_PLAY_UNTIL_TRADE,
    MILESTONE_SALARY_REDUCTION,
    MILESTONE_SHOW_DISCONTENT,
    calculate_change,
    classify_happiness_milestone,
    drafted_rating_threshold_crossed,
    is_free_agent_context,
    is_rookie_scale_contract_type,
    normalize_event_type,
    normalize_happiness,
    recency_decay_weight,
    recency_recalculated_happiness,
    roster_impact_player_delta,
    roster_rating_impact_delta,
    team_join_happiness,
    team_objective_happiness_delta,
    team_objective_happiness_delta_change,
    team_objective_rating_band,
    team_objective_resolution_delta,
    trade_request_followup_penalties,
    trade_request_still_unresolved,
    trade_request_eligible,
    zero_happiness_transition,
    promise_resolution_delta,
)


class PlayerHappinessRulesTests(unittest.TestCase):
    def test_normalize_happiness_clamps_to_allowed_bounds(self) -> None:
        self.assertEqual(10, normalize_happiness(12))
        self.assertEqual(-10, normalize_happiness(-12))
        self.assertEqual(7.5, normalize_happiness("7.5"))

    def test_calculate_change_clamps_new_value_and_reports_threshold(self) -> None:
        change = calculate_change(-6, proposed_delta=-5)

        self.assertEqual(-6, change.previous_value)
        self.assertEqual(-5, change.proposed_delta)
        self.assertEqual(-5, change.applied_delta)
        self.assertEqual(-10, change.new_value)
        self.assertTrue(change.eligible_for_trade_request)

    def test_team_join_happiness_starts_at_seven_then_applies_modifiers(self) -> None:
        self.assertEqual(7, team_join_happiness())
        self.assertEqual(8.5, team_join_happiness([1, "0.5"]))
        self.assertEqual(10, team_join_happiness([9]))

    def test_free_agent_context_is_frozen_for_automatic_modifiers(self) -> None:
        self.assertTrue(is_free_agent_context("free_agent"))
        self.assertTrue(is_free_agent_context("Agente libre"))
        self.assertFalse(is_free_agent_context("roster", active_contract=True))

    def test_event_types_are_explicit(self) -> None:
        self.assertEqual(EVENT_TEAM_JOIN, normalize_event_type("team-join"))
        self.assertEqual(EVENT_MODIFIER, normalize_event_type("modifier"))
        self.assertEqual(EVENT_TEAM_OBJECTIVE_SET, normalize_event_type("team-objective-set"))
        self.assertEqual(EVENT_TEAM_OBJECTIVE_JOIN_CONTEXT, normalize_event_type("team objective join context"))
        self.assertEqual(EVENT_TEAM_OBJECTIVE_RESOLUTION, normalize_event_type("team objective resolution"))
        self.assertEqual(EVENT_TRADE_REQUEST_FOLLOWUP, normalize_event_type("trade request followup"))
        with self.assertRaisesRegex(ValueError, "invalid_happiness_event_type"):
            normalize_event_type("unknown")

    def test_trade_request_threshold_is_deterministic(self) -> None:
        self.assertFalse(trade_request_eligible(-6.99))
        self.assertTrue(trade_request_eligible(-7))
        self.assertTrue(trade_request_still_unresolved(1.5, is_last_contract_year=False))
        self.assertFalse(trade_request_still_unresolved(2, is_last_contract_year=False))
        self.assertTrue(trade_request_still_unresolved(2.5, is_last_contract_year=True))
        self.assertFalse(trade_request_still_unresolved(3, is_last_contract_year=True))

    def test_trade_request_followup_penalties_are_month_based_and_idempotent_by_stage(self) -> None:
        self.assertEqual(
            [],
            trade_request_followup_penalties(
                "2026-01-15",
                "2026-04-14",
                current_happiness=1.5,
            ),
        )
        self.assertEqual(
            ["three_months"],
            [
                item["stage"]
                for item in trade_request_followup_penalties(
                    "2026-01-15",
                    "2026-04-15",
                    current_happiness=1.5,
                )
            ],
        )
        self.assertEqual(
            ["three_months", "nine_months"],
            [
                item["stage"]
                for item in trade_request_followup_penalties(
                    "2026-01-15",
                    "2026-10-15",
                    current_happiness=1.5,
                )
            ],
        )
        self.assertEqual(
            ["nine_months"],
            [
                item["stage"]
                for item in trade_request_followup_penalties(
                    "2026-01-15",
                    "2026-10-15",
                    current_happiness=1.5,
                    applied_stages=["three_months"],
                )
            ],
        )
        self.assertEqual(
            [],
            trade_request_followup_penalties(
                "2026-01-15",
                "2026-10-15",
                current_happiness=2,
            ),
        )

    def test_roster_rating_impact_deltas_match_requested_bands(self) -> None:
        self.assertEqual(0, roster_rating_impact_delta(84, "add"))
        self.assertEqual(1, roster_rating_impact_delta(85, "add"))
        self.assertEqual(1, roster_rating_impact_delta(89, "add"))
        self.assertEqual(2, roster_rating_impact_delta(90, "add"))
        self.assertEqual(-1, roster_rating_impact_delta(85, "remove"))
        self.assertEqual(-2, roster_rating_impact_delta(99, "remove"))

    def test_roster_impact_player_delta_handles_first_season_and_young_negative_exemption(self) -> None:
        self.assertEqual(1, roster_impact_player_delta(2, first_season_with_team=True))
        self.assertEqual(-1, roster_impact_player_delta(-2, first_season_with_team=True, date_of_birth="1995-01-01", on_date="2026-07-31"))
        self.assertEqual(0, roster_impact_player_delta(-2, first_season_with_team=True, date_of_birth="2002-01-01", on_date="2026-07-31"))
        self.assertEqual(-2, roster_impact_player_delta(-2, first_season_with_team=False, date_of_birth="2002-01-01", on_date="2026-07-31"))

    def test_team_objective_happiness_table_matches_rating_age_bands(self) -> None:
        self.assertEqual("60_74", team_objective_rating_band(60))
        self.assertEqual("75_79", team_objective_rating_band(79))
        self.assertEqual("95_99", team_objective_rating_band(99))
        self.assertIsNone(team_objective_rating_band(100))

        self.assertEqual(-1, team_objective_happiness_delta("Desarrollar", 80, age=24))
        self.assertEqual(-2, team_objective_happiness_delta("Desarrollar", 85, age=26))
        self.assertEqual(-0.5, team_objective_happiness_delta("Entrar play-in", 80, age=30))
        self.assertEqual(-0.5, team_objective_happiness_delta("Mínimo 2ª ronda", 95, age=24))
        self.assertEqual(0.5, team_objective_happiness_delta("Final de conferencia", 90, age=24))
        self.assertEqual(0, team_objective_happiness_delta("Final de conferencia", 95, age=24))
        self.assertEqual(0.5, team_objective_happiness_delta("Finalista", 95, age=30))
        self.assertEqual(0, team_objective_happiness_delta("Finalista", 85, age=30))
        self.assertEqual(0, team_objective_happiness_delta("Finalista", 95))

    def test_team_objective_delta_change_is_relative_not_cumulative(self) -> None:
        self.assertEqual(
            2.5,
            team_objective_happiness_delta_change(
                "Desarrollar jóvenes",
                "Finalista",
                95,
                date_of_birth="1990-01-01",
                on_date="2026-07-31",
            ),
        )

    def test_team_objective_resolution_delta_matches_season_end_table(self) -> None:
        self.assertEqual(3, team_objective_resolution_delta("Finales", "Campeón"))
        self.assertEqual(2, team_objective_resolution_delta("Finales", "Finales"))
        self.assertEqual(2, team_objective_resolution_delta("Primera ronda", "Final de conferencia"))
        self.assertEqual(1.5, team_objective_resolution_delta("Primera ronda", "Segunda ronda"))
        self.assertEqual(1, team_objective_resolution_delta("Segunda ronda", "Segunda ronda"))
        self.assertEqual(-1, team_objective_resolution_delta("Finales", "Final de conferencia"))
        self.assertEqual(2, team_objective_resolution_delta("Desarrollar jóvenes", "Finales"))
        self.assertEqual(-2, team_objective_resolution_delta("Finales", "Desarrollar jóvenes"))
        self.assertEqual(0, team_objective_resolution_delta("objetivo raro", "Finales"))

    def test_drafted_rating_threshold_rules_are_crossing_based(self) -> None:
        self.assertTrue(drafted_rating_threshold_crossed(84, 85))
        self.assertTrue(drafted_rating_threshold_crossed("84", "90"))
        self.assertFalse(drafted_rating_threshold_crossed(85, 86))
        self.assertFalse(drafted_rating_threshold_crossed("#N/A", 85))
        self.assertTrue(is_rookie_scale_contract_type("R"))
        self.assertTrue(is_rookie_scale_contract_type("R(2)"))
        self.assertFalse(is_rookie_scale_contract_type("Reg"))

    def test_zero_happiness_transition_tracks_original_cohort_boundary(self) -> None:
        self.assertEqual("initial_zero", zero_happiness_transition(1, 0, has_prior_zero_cohort=False))
        self.assertEqual("return_to_zero", zero_happiness_transition(1, 0, has_prior_zero_cohort=True))
        self.assertEqual("recovered_above_zero", zero_happiness_transition(0, 1, has_prior_zero_cohort=True))
        self.assertIsNone(zero_happiness_transition(-1, -2, has_prior_zero_cohort=True))

    def test_promise_resolution_delta_is_reversible_by_status_transition(self) -> None:
        self.assertEqual(1, promise_resolution_delta("pending", "fulfilled"))
        self.assertEqual(-1, promise_resolution_delta("pending", "broken"))
        self.assertEqual(-2, promise_resolution_delta("fulfilled", "broken"))
        self.assertEqual(2, promise_resolution_delta("broken", "fulfilled"))
        self.assertEqual(0, promise_resolution_delta("fulfilled", "fulfilled"))

    def test_recency_decay_weights_match_documented_table(self) -> None:
        expected = {
            0: 1.0,
            1: 0.95,
            2: 0.85,
            3: 0.70,
            4: 0.60,
            5: 0.50,
            6: 0.40,
            7: 0.30,
            8: 0.25,
            9: 0.20,
            10: 0.0,
        }
        for age, weight in expected.items():
            with self.subTest(age=age):
                self.assertEqual(weight, recency_decay_weight(2026, 2026 - age))

    def test_recency_recalculation_keeps_anchor_and_decays_modifiers(self) -> None:
        result = recency_recalculated_happiness(
            [
                {
                    "id": 1,
                    "event_type": "baseline_import",
                    "season_year": 2024,
                    "previous_value": 0,
                    "applied_delta": 7,
                    "new_value": 7,
                },
                {
                    "id": 2,
                    "event_type": "modifier",
                    "season_year": 2026,
                    "previous_value": 7,
                    "applied_delta": 2,
                    "new_value": 9,
                },
                {
                    "id": 3,
                    "event_type": "gm_change",
                    "season_year": 2025,
                    "previous_value": 9,
                    "applied_delta": -1,
                    "new_value": 8,
                },
            ],
            2026,
        )

        self.assertEqual(7, result["base_value"])
        self.assertAlmostEqual(1.05, result["modifier_total"])
        self.assertAlmostEqual(8.05, result["new_value"])
        self.assertEqual(2, len(result["weighted_events"]))

    def test_multiyear_contract_milestones_match_league_rules(self) -> None:
        cases = [
            (10, MILESTONE_SALARY_REDUCTION, "private", False),
            (9.5, MILESTONE_PRIORITIZE_DESTINATION, "private", False),
            (8.5, None, None, None),
            (7.5, None, None, None),
            (6.5, None, None, None),
            (4.5, None, None, None),
            (3.5, None, None, None),
            (2.5, MILESTONE_SHOW_DISCONTENT, "private", False),
            (1.5, MILESTONE_PRIVATE_TRADE_REQUEST, "private", False),
            (0.5, MILESTONE_PUBLIC_TRADE_REQUEST, "public", True),
            (-0.5, MILESTONE_REFUSE_TO_PLAY_UNTIL_TRADE, "private", False),
        ]
        for value, code, visibility, discord_news in cases:
            with self.subTest(value=value):
                milestone = classify_happiness_milestone(value, is_last_contract_year=False)
                if code is None:
                    self.assertIsNone(milestone)
                else:
                    self.assertIsNotNone(milestone)
                    self.assertEqual(code, milestone.code)
                    self.assertEqual(visibility, milestone.visibility)
                    self.assertEqual(discord_news, milestone.discord_news_eligible)

    def test_last_contract_year_milestones_match_league_rules(self) -> None:
        cases = [
            (10, MILESTONE_SALARY_REDUCTION, "private", False),
            (9.5, MILESTONE_PRIORITIZE_DESTINATION, "private", False),
            (8.5, None, None, None),
            (7.5, None, None, None),
            (6.5, None, None, None),
            (4.5, None, None, None),
            (3.5, MILESTONE_PRIORITIZE_OTHER_DESTINATIONS, "private", False),
            (2.5, MILESTONE_PRIVATE_TRADE_REQUEST, "private", False),
            (1.5, MILESTONE_PUBLIC_TRADE_REQUEST, "public", True),
            (0.5, None, None, None),
            (-0.5, MILESTONE_REFUSE_TO_PLAY_UNTIL_TRADE, "private", False),
        ]
        for value, code, visibility, discord_news in cases:
            with self.subTest(value=value):
                milestone = classify_happiness_milestone(value, is_last_contract_year=True)
                if code is None:
                    self.assertIsNone(milestone)
                else:
                    self.assertIsNotNone(milestone)
                    self.assertEqual(code, milestone.code)
                    self.assertEqual(visibility, milestone.visibility)
                    self.assertEqual(discord_news, milestone.discord_news_eligible)
