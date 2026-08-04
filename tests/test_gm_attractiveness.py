import unittest

from app.domain.gm_attractiveness import (
    GM_CHANGE_ENTER,
    GM_CHANGE_LEAVE,
    RANKING_BAND_BOTTOM_5,
    RANKING_BAND_TOP_5,
    gm_change_happiness_delta,
    standardized_ranking,
)


class GMAttractivenessDomainTests(unittest.TestCase):
    def test_standardized_ranking_normalizes_voter_scales(self) -> None:
        ranking = standardized_ranking(
            [
                {"voter_user_id": 1, "target_id": 10, "target_name": "Top GM", "score": 90},
                {"voter_user_id": 1, "target_id": 20, "target_name": "Bottom GM", "score": 70},
                {"voter_user_id": 2, "target_id": 10, "target_name": "Top GM", "score": 100},
                {"voter_user_id": 2, "target_id": 20, "target_name": "Bottom GM", "score": 1},
            ]
        )

        self.assertEqual([10, 20], [entry.target_id for entry in ranking])
        self.assertGreater(ranking[0].standardized_score, 0)
        self.assertLess(ranking[1].standardized_score, 0)

    def test_standardized_ranking_marks_top_and_bottom_five(self) -> None:
        ranking = standardized_ranking(
            [
                {"voter_user_id": 1, "target_id": target_id, "target_name": f"GM {target_id}", "score": target_id}
                for target_id in range(1, 13)
            ]
        )

        bands = {entry.target_id: entry.band for entry in ranking}
        self.assertEqual(RANKING_BAND_TOP_5, bands[12])
        self.assertEqual(RANKING_BAND_TOP_5, bands[8])
        self.assertEqual(RANKING_BAND_BOTTOM_5, bands[5])
        self.assertEqual(RANKING_BAND_BOTTOM_5, bands[1])

    def test_gm_change_happiness_deltas(self) -> None:
        self.assertEqual(1.0, gm_change_happiness_delta(direction=GM_CHANGE_ENTER, band=RANKING_BAND_TOP_5))
        self.assertEqual(-1.0, gm_change_happiness_delta(direction=GM_CHANGE_ENTER, band=RANKING_BAND_BOTTOM_5))
        self.assertEqual(-0.5, gm_change_happiness_delta(direction=GM_CHANGE_LEAVE, band=RANKING_BAND_TOP_5))
        self.assertEqual(0.5, gm_change_happiness_delta(direction=GM_CHANGE_LEAVE, band=RANKING_BAND_BOTTOM_5))


if __name__ == "__main__":
    unittest.main()
