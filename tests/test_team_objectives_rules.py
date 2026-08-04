import unittest

from app.domain.team_objectives import (
    CHAMPION,
    COMPARISON_EXCEEDED,
    COMPARISON_MET,
    COMPARISON_MISSED,
    COMPARISON_UNKNOWN,
    CONFERENCE_FINALS,
    FINALS,
    FIRST_ROUND,
    PLAY_IN,
    PLAY_IN_RACE,
    SECOND_ROUND,
    YOUTH_DEVELOPMENT,
    compare_objectives,
    normalize_objective_code,
    normalize_objective_list,
    objective_difficulty,
    objective_exceeded,
    objective_label,
    objective_met,
    objective_missed,
    objective_options,
    objective_payload,
    require_objective_code,
    require_objective_result_code,
)


class TeamObjectiveDomainTests(unittest.TestCase):
    def test_normalizes_canonical_codes_and_spanish_labels(self) -> None:
        self.assertEqual(CHAMPION, normalize_objective_code("Campeón"))
        self.assertEqual(FINALS, normalize_objective_code("finals"))
        self.assertEqual(FINALS, normalize_objective_code("Alcanzar las finales"))
        self.assertEqual(CONFERENCE_FINALS, normalize_objective_code("Alcanzar las finales de conferencia"))
        self.assertEqual(SECOND_ROUND, normalize_objective_code("Alcanzar la segunda ronda"))
        self.assertEqual(FIRST_ROUND, normalize_objective_code("Alcanzar la primera ronda"))
        self.assertEqual(PLAY_IN, normalize_objective_code("Jugar el play-in"))
        self.assertEqual(PLAY_IN_RACE, normalize_objective_code("Luchar por el play-in (quedarse cerca)"))
        self.assertEqual(YOUTH_DEVELOPMENT, normalize_objective_code("Desarrollar jóvenes"))

    def test_normalizes_common_aliases_without_accents_or_punctuation(self) -> None:
        self.assertEqual(CHAMPION, normalize_objective_code("ganar el anillo"))
        self.assertEqual(CONFERENCE_FINALS, normalize_objective_code("conference finals"))
        self.assertEqual(SECOND_ROUND, normalize_objective_code("semifinales de conferencia"))
        self.assertEqual(FIRST_ROUND, normalize_objective_code("clasificar a playoffs"))
        self.assertEqual(PLAY_IN, normalize_objective_code("play in"))
        self.assertEqual(PLAY_IN_RACE, normalize_objective_code("quedarse cerca del play-in"))
        self.assertEqual(YOUTH_DEVELOPMENT, normalize_objective_code("reconstrucción"))
        self.assertIsNone(normalize_objective_code(""))
        self.assertIsNone(normalize_objective_code("ganar 42 partidos"))

    def test_payload_and_options_are_ordered_by_difficulty(self) -> None:
        self.assertEqual("Campeón", objective_label(CHAMPION))
        self.assertEqual("Alcanzar las finales", objective_label(FINALS))
        self.assertGreater(objective_difficulty(CHAMPION), objective_difficulty(FINALS))
        self.assertGreater(objective_difficulty(FINALS), objective_difficulty(CONFERENCE_FINALS))
        self.assertGreater(objective_difficulty(PLAY_IN), objective_difficulty(YOUTH_DEVELOPMENT))
        self.assertEqual(
            {
                "code": PLAY_IN,
                "label": "Jugar el play-in",
                "difficulty": objective_difficulty(PLAY_IN),
            },
            objective_payload("Jugar el play-in"),
        )

        hardest = objective_options()
        easiest = objective_options(hardest_first=False)
        self.assertEqual(FINALS, hardest[0]["code"])
        self.assertNotIn(CHAMPION, {row["code"] for row in hardest})
        self.assertEqual(YOUTH_DEVELOPMENT, hardest[-1]["code"])
        self.assertEqual(YOUTH_DEVELOPMENT, easiest[0]["code"])

    def test_result_comparison_reports_met_exceeded_missed_or_unknown(self) -> None:
        self.assertEqual(COMPARISON_MET, compare_objectives("Jugar el play-in", PLAY_IN))
        self.assertEqual(COMPARISON_EXCEEDED, compare_objectives("Alcanzar las finales", CHAMPION))
        self.assertEqual(COMPARISON_EXCEEDED, compare_objectives("Jugar el play-in", SECOND_ROUND))
        self.assertEqual(COMPARISON_MISSED, compare_objectives("Alcanzar la segunda ronda", PLAY_IN))
        self.assertEqual(COMPARISON_UNKNOWN, compare_objectives("objetivo raro", PLAY_IN))

        self.assertTrue(objective_met(PLAY_IN, SECOND_ROUND))
        self.assertTrue(objective_exceeded(PLAY_IN, SECOND_ROUND))
        self.assertTrue(objective_missed(SECOND_ROUND, PLAY_IN))
        self.assertFalse(objective_met(SECOND_ROUND, PLAY_IN))

    def test_require_objective_code_and_list_normalization(self) -> None:
        self.assertEqual(FINALS, require_objective_code("finales"))
        self.assertEqual(CHAMPION, require_objective_result_code("campeón"))
        with self.assertRaisesRegex(ValueError, "invalid_team_objective"):
            require_objective_code("campeón")
        with self.assertRaisesRegex(ValueError, "invalid_team_objective"):
            require_objective_code("top 6")

        self.assertEqual(
            [PLAY_IN, FINALS, YOUTH_DEVELOPMENT],
            normalize_objective_list(["play in", "finales", "play-in", "rebuild", ""]),
        )


if __name__ == "__main__":
    unittest.main()
