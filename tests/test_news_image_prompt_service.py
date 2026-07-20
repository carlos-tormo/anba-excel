import unittest

from app.services.news_image_prompts import NewsImagePromptService, TEAM_IMAGE_COLORS


class NewsImagePromptServiceTests(unittest.TestCase):
    def test_palette_contains_all_teams_and_has_stable_fallback(self):
        service = NewsImagePromptService()
        self.assertEqual(30, len(TEAM_IMAGE_COLORS))
        self.assertEqual("#E03A3E, #C1D32F", service.colors_for("atl"))
        self.assertEqual("#0F766E, #111827", service.colors_for("unknown"))

    def test_generic_prompt_normalizes_teams_players_and_context(self):
        prompt = NewsImagePromptService().build(
            "ATL signs Player",
            "The player joins in free agency.",
            teams=["atl", ""],
            players=["Player", ""],
            context="One-year agreement.",
        )
        self.assertIn("Main headline text exactly: ATL signs Player", prompt)
        self.assertIn("Relevant team(s): ATL.", prompt)
        self.assertIn("Relevant player name(s): Player.", prompt)
        self.assertIn("Additional context: One-year agreement.", prompt)

    def test_reference_prompt_contains_identity_team_palette_and_transaction(self):
        prompt = NewsImagePromptService().build(
            "ATL renews Player",
            "A new contract is agreed.",
            teams=["ATL"],
            players=["Player"],
            team_name="Atlanta Hawks",
            team_code="ATL",
            player_name="Player",
            secondary_headline="Player stays in Atlanta",
            additional_details="Three seasons",
            transaction_type="Re-signing",
            use_player_reference=True,
        )
        self.assertIn("Atlanta Hawks uniform", prompt)
        self.assertIn("#E03A3E, #C1D32F", prompt)
        self.assertIn("Player stays in Atlanta", prompt)
        self.assertIn("Three seasons", prompt)
        self.assertIn("Transaction Type:\nRe-signing", prompt)

if __name__ == "__main__":
    unittest.main()
