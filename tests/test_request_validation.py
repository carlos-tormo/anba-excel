import unittest
from unittest import mock

from app import server
from app.routes import validation as route_validation
from app.server import (
    ASSET_UPDATE_FIELDS,
    PLAYER_UPDATE_ALLOWED_FIELDS,
    RequestValidationError,
    validate_admin_decision_payload,
    validate_coadmin_vote_submit_payload,
    validate_free_agent_offer_payload,
    validate_gm_depth_chart_payload,
    validate_gm_minimum_targets_payload,
    validate_gm_option_request_payload,
    validate_gm_spending_limit_payload,
    validate_integer_range,
    validate_json_structure,
    validate_payload_fields,
    validate_text_field,
    validate_unique_integer_ids,
    validate_waiver_claim_payload,
)


class RequestValidationTests(unittest.TestCase):
    def test_json_structure_accepts_normal_nested_payload(self) -> None:
        validate_json_structure(
            {
                "team": "ATL",
                "players": [{"id": 1}, {"id": 2}],
                "metadata": {"season": 2026},
            }
        )

    def test_json_structure_rejects_excessive_depth(self) -> None:
        payload = {}
        current = payload
        for _ in range(server.JSON_MAX_DEPTH):
            child = {}
            current["child"] = child
            current = child

        with self.assertRaisesRegex(RequestValidationError, "payload_too_deep"):
            validate_json_structure(payload)

    def test_json_structure_rejects_oversized_container_and_key(self) -> None:
        with mock.patch.object(route_validation, "JSON_MAX_CONTAINER_ITEMS", 2):
            with self.assertRaisesRegex(RequestValidationError, "list_too_large"):
                validate_json_structure({"items": [1, 2, 3]})

        with self.assertRaisesRegex(RequestValidationError, "invalid_json_key"):
            validate_json_structure({"x" * (server.JSON_MAX_KEY_LENGTH + 1): True})

    def test_payload_fields_reject_unknown_and_missing_fields(self) -> None:
        with self.assertRaisesRegex(RequestValidationError, "unknown_fields") as unknown:
            validate_payload_fields({"name": "Player", "is_admin": True}, {"name"})
        self.assertEqual(["is_admin"], unknown.exception.details["fields"])

        with self.assertRaisesRegex(RequestValidationError, "missing_fields") as missing:
            validate_payload_fields({}, {"name"}, required_fields={"name"})
        self.assertEqual(["name"], missing.exception.details["fields"])

    def test_unique_ids_reject_duplicates_invalid_values_and_long_lists(self) -> None:
        self.assertEqual([1, 2], validate_unique_integer_ids(["1", 2], field="player_ids"))

        with self.assertRaisesRegex(RequestValidationError, "duplicate_ids"):
            validate_unique_integer_ids([1, "1"], field="player_ids")
        with self.assertRaisesRegex(RequestValidationError, "invalid_id"):
            validate_unique_integer_ids([0], field="player_ids")
        with self.assertRaisesRegex(RequestValidationError, "list_too_large"):
            validate_unique_integer_ids([1, 2], field="player_ids", max_items=1)

    def test_text_and_integer_range_validation(self) -> None:
        validate_text_field({"name": "Player"}, "name", max_length=20, required=True)
        validate_integer_range({"year": "2026"}, "year", minimum=2000, maximum=2200)

        with self.assertRaisesRegex(RequestValidationError, "field_too_long"):
            validate_text_field({"name": "Player"}, "name", max_length=3)
        with self.assertRaisesRegex(RequestValidationError, "invalid_field"):
            validate_text_field({"name": True}, "name", max_length=20)
        with self.assertRaisesRegex(RequestValidationError, "invalid_integer_range"):
            validate_integer_range({"year": 1900}, "year", minimum=2000, maximum=2200)

    def test_generic_update_schemas_do_not_allow_identity_or_privilege_assignment(self) -> None:
        for forbidden in {"id", "profile_id", "team", "team_id", "is_admin", "role"}:
            self.assertNotIn(forbidden, PLAYER_UPDATE_ALLOWED_FIELDS)
            self.assertNotIn(forbidden, ASSET_UPDATE_FIELDS)

    def test_gm_spending_limit_schema_rejects_overposting_and_out_of_range_values(self) -> None:
        validate_gm_spending_limit_payload({"team_code": "ATL", "amount_millions": 42.5})

        with self.assertRaisesRegex(RequestValidationError, "unknown_fields"):
            validate_gm_spending_limit_payload(
                {"team_code": "ATL", "amount_millions": 42.5, "is_admin": True}
            )
        with self.assertRaisesRegex(RequestValidationError, "invalid_number_range"):
            validate_gm_spending_limit_payload({"team_code": "ATL", "amount_millions": 101})

    def test_minimum_targets_schema_validates_nested_rows_and_uniqueness(self) -> None:
        validate_gm_minimum_targets_payload(
            {
                "team_code": "ATL",
                "targets": [
                    {"rank": 1, "free_agent_id": 10, "role": "Titular"},
                    {"rank": 2, "free_agent_id": 11, "role": "Sexto hombre"},
                ],
            }
        )
        validate_gm_minimum_targets_payload({"team_code": "ATL"}, omit=True)

        with self.assertRaisesRegex(RequestValidationError, "duplicate_ids"):
            validate_gm_minimum_targets_payload(
                {
                    "targets": [
                        {"rank": 1, "free_agent_id": 10, "role": "Titular"},
                        {"rank": 2, "free_agent_id": 10, "role": "Sexto hombre"},
                    ]
                }
            )
        with self.assertRaisesRegex(RequestValidationError, "unknown_fields"):
            validate_gm_minimum_targets_payload(
                {
                    "targets": [
                        {"rank": 1, "free_agent_id": 10, "role": "Titular", "approved": True}
                    ]
                }
            )

    def test_depth_chart_schema_rejects_duplicate_players_and_slots(self) -> None:
        validate_gm_depth_chart_payload(
            {
                "team_code": "ATL",
                "entries": [
                    {"position": "PG", "depth_order": 1, "player_id": 10},
                    {"position": "SG", "depth_order": 1, "player_id": 11},
                ],
            }
        )

        with self.assertRaisesRegex(RequestValidationError, "duplicate_ids"):
            validate_gm_depth_chart_payload(
                {
                    "entries": [
                        {"position": "PG", "depth_order": 1, "player_id": 10},
                        {"position": "SG", "depth_order": 1, "player_id": 10},
                    ]
                }
            )
        with self.assertRaisesRegex(RequestValidationError, "duplicate_value"):
            validate_gm_depth_chart_payload(
                {
                    "entries": [
                        {"position": "PG", "depth_order": 1, "player_id": 10},
                        {"position": "PG", "depth_order": 1, "player_id": 11},
                    ]
                }
            )

    def test_free_agent_offer_schema_preserves_legacy_money_format(self) -> None:
        validate_free_agent_offer_payload(
            {
                "team_code": "ATL",
                "contract_type": "Reg",
                "years": 2,
                "annual_raise_percent": 5,
                "role": "Titular",
                "salary_by_season": {"2026": "57.750.000", "2027": "60.637.500"},
                "option_by_season": {"2027": "PO"},
                "notes": "Oferta válida",
            }
        )

        with self.assertRaisesRegex(RequestValidationError, "unknown_fields"):
            validate_free_agent_offer_payload(
                {
                    "contract_type": "Reg",
                    "years": 1,
                    "salary_by_season": {"2026": "1000000"},
                    "option_by_season": {},
                    "profile_id": 99,
                }
            )
        with self.assertRaisesRegex(RequestValidationError, "invalid_integer_range"):
            validate_free_agent_offer_payload(
                {
                    "contract_type": "Reg",
                    "years": "",
                    "salary_by_season": {"2026": "1000000"},
                    "option_by_season": {},
                }
            )
        with self.assertRaisesRegex(RequestValidationError, "invalid_enum"):
            validate_free_agent_offer_payload(
                {
                    "contract_type": "Reg",
                    "years": 1,
                    "salary_by_season": {"2026": "1000000"},
                    "option_by_season": {"2027": "QO"},
                }
            )

    def test_gm_option_and_waiver_claim_schemas_reject_privileged_fields(self) -> None:
        validate_gm_option_request_payload(
            {
                "player_id": 10,
                "option_field": "option_2026",
                "option_value": "QO",
                "action": "accepted",
            }
        )
        validate_waiver_claim_payload({"team_code": "ATL", "contingent_cut_player_id": 12})

        with self.assertRaisesRegex(RequestValidationError, "unknown_fields"):
            validate_gm_option_request_payload(
                {
                    "player_id": 10,
                    "option_field": "option_2026",
                    "option_value": "QO",
                    "action": "accepted",
                    "approved_by": 1,
                }
            )
        with self.assertRaisesRegex(RequestValidationError, "invalid_id"):
            validate_waiver_claim_payload({"contingent_cut_player_id": 0})

    def test_vote_and_admin_decision_schemas_validate_ranges_and_booleans(self) -> None:
        validate_coadmin_vote_submit_payload({"scores": {"ATL": 100, "BOS": 1}})
        validate_admin_decision_payload(
            {
                "decision": "approved",
                "note": "Correcto",
                "notify_discord": True,
                "generate_discord_image": False,
            }
        )

        with self.assertRaisesRegex(RequestValidationError, "invalid_integer_range"):
            validate_coadmin_vote_submit_payload({"scores": {"ATL": 101}})
        with self.assertRaisesRegex(RequestValidationError, "invalid_boolean"):
            validate_admin_decision_payload({"decision": "approved", "notify_discord": "true"})
        with self.assertRaisesRegex(RequestValidationError, "unknown_fields"):
            validate_admin_decision_payload({"decision": "approved", "approved_by": 1})


if __name__ == "__main__":
    unittest.main()
