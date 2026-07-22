import unittest

from app.services.notifications import NotificationCompositionService
from app.services.owner_interviews import OwnerInterviewCompositionService


class NotificationCompositionServiceTests(unittest.TestCase):
    def test_notification_payload_bounds_fields_and_mentions(self) -> None:
        payload = NotificationCompositionService.notification_payload(
            "T" * 300,
            "D" * 5000,
            fields=[{"name": "Name", "value": "Value", "inline": True}] * 30,
            role_id="12345",
            image_filename="news.png",
        )

        embed = payload["embeds"][0]
        self.assertEqual(len(embed["title"]), 256)
        self.assertEqual(len(embed["description"]), 4096)
        self.assertEqual(len(embed["fields"]), 25)
        self.assertEqual(embed["image"]["url"], "attachment://news.png")
        self.assertEqual(payload["content"], "<@&12345>")
        self.assertEqual(payload["allowed_mentions"]["roles"], ["12345"])

    def test_notification_payload_neutralizes_user_provided_mentions(self) -> None:
        payload = NotificationCompositionService.notification_payload(
            "@everyone <@123> update",
            "DM <@&456> and @here",
            fields=[{"name": "@everyone", "value": "<@789>"}],
        )

        embed = payload["embeds"][0]
        self.assertNotIn("@everyone", embed["title"])
        self.assertNotIn("@here", embed["description"])
        self.assertNotIn("<@123>", embed["title"])
        self.assertNotIn("<@&456>", embed["description"])
        self.assertNotIn("<@789>", embed["fields"][0]["value"])
        self.assertEqual({"parse": []}, payload["allowed_mentions"])

    def test_press_article_payload_validates_and_truncates_teaser(self) -> None:
        with self.assertRaisesRegex(ValueError, "article_text_required"):
            NotificationCompositionService.press_article_payload("", "https://example.test/news", "news.png")

        payload = NotificationCompositionService.press_article_payload(
            "A" * 1200,
            "https://example.test/news/1",
            "news.png",
        )
        embed = payload["embeds"][0]
        teaser = embed["description"].split("\n\n", 1)[0]
        self.assertEqual(len(teaser), 1000)
        self.assertTrue(teaser.endswith("..."))
        self.assertEqual(embed["image"]["url"], "attachment://news.png")

    def test_player_cut_template_preserves_waiver_wording(self) -> None:
        event = NotificationCompositionService.player_cut(
            {
                "team_code": "bos",
                "team_name": "Boston Celtics",
                "player_name": "Test Player",
                "waiver": True,
                "waiver_expires_at": "2026-07-21T12:00:00Z",
            }
        )

        self.assertEqual(event.title, "BOS corta a Test Player")
        self.assertIn("waivers durante 48h", event.description)
        self.assertEqual(event.fields[-1]["name"], "Waivers hasta")
        self.assertEqual(event.image_prompt["transaction_type"], "Released")

    def test_signing_and_draft_templates_are_transport_neutral(self) -> None:
        signing = NotificationCompositionService.free_agent_signed(
            {"team_code": "ATL", "name": "Test Guard", "position": "SG", "bird_rights": "Reg"},
            salary_summary="2026-27: 10.000.000",
            offer_type="renewal",
        )
        draft = NotificationCompositionService.draft_pick_selection(
            {"team_code": "LAL", "selection_text": "Rookie", "pick_number": 8, "draft_round": "1st"},
            2027,
        )

        self.assertEqual(signing.title, "ATL renueva a Test Guard")
        self.assertEqual(signing.fields[-1]["value"], "2026-27: 10.000.000")
        self.assertEqual(draft.title, "LAL elige a Rookie")
        self.assertIn("1ª ronda del Draft 2027", draft.description)

    def test_trade_template_formats_assets_for_multi_team_result(self) -> None:
        event = NotificationCompositionService.trade_processed(
            {
                "trade_bucket": "post30",
                "teams": [
                    {
                        "code": "BOS",
                        "received": {"players": ["Player A"], "cash_amount": 500000},
                        "sent": {"players": ["Player B"]},
                    },
                    {
                        "code": "NYK",
                        "received": {"picks": ["2028 1st-round"]},
                        "sent": {"players": ["Player A"]},
                    },
                ],
            }
        )

        self.assertEqual(event.title, "BOS / NYK cierran un traspaso")
        self.assertIn("movimientos post-30", event.description)
        self.assertIn("Cash: $500.000", event.fields[0]["value"])
        self.assertIn("1ª ronda", event.fields[1]["value"])

    def test_option_and_bird_rights_templates_preserve_transaction_details(self) -> None:
        player = {"team_code": "MIA", "team_name": "Miami Heat", "name": "Test Wing"}
        option = NotificationCompositionService.contract_option_action(player, 2026, "TO", "accepted")
        rights = NotificationCompositionService.bird_rights_renounced(player, 2026, "FB")

        self.assertEqual(option.title, "MIA acepta la team option de Test Wing")
        self.assertEqual(option.color, 0x7C3AED)
        self.assertEqual(option.image_prompt["transaction_type"], "Team Option Exercised")
        self.assertEqual(rights.title, "MIA renuncia a los derechos Full Bird de Test Wing")
        self.assertEqual(rights.fields[-1]["value"], "Full Bird")


class OwnerInterviewCompositionServiceTests(unittest.TestCase):
    def test_opening_falls_back_when_transport_returns_no_text(self) -> None:
        calls = []

        def no_response(system_prompt, user_prompt, max_output_tokens):
            calls.append((system_prompt, user_prompt, max_output_tokens))
            return None

        service = OwnerInterviewCompositionService(no_response)
        message = service.opening_message({"team_code": "BOS"}, 2025, {"name": "Alex GM"})

        self.assertIn("BOS", message)
        self.assertEqual(calls[0][2], 450)
        self.assertIn("GM evaluado: Alex GM", calls[0][1])

    def test_final_reply_parses_fenced_json_and_normalizes_delta(self) -> None:
        service = OwnerInterviewCompositionService(
            lambda *_args: '```json\n{"message":"Bien.","conclusion":"Seguimos.","trust_delta":8}\n```'
        )

        message, conclusion, trust_delta = service.final_reply({}, 2025, "Inicial", "Respuesta")

        self.assertEqual(message, "Bien.")
        self.assertEqual(conclusion, "Seguimos.")
        self.assertEqual(trust_delta, 1)


if __name__ == "__main__":
    unittest.main()
