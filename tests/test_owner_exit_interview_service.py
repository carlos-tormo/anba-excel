import unittest
from contextlib import contextmanager
from unittest.mock import Mock

from app.services.owner_office import OwnerExitInterviewError, OwnerOfficeService


class FakeOwnerOfficeRepository:
    def __init__(self) -> None:
        self.settings_values = {"current_year": "2025", "free_agency_mode": "1"}
        self.existing = None
        self.started = {"id": 1, "status": "awaiting_gm"}
        self.completed = {"id": 1, "status": "completed", "trust_delta": 1}
        self.reset_result = True

    @contextmanager
    def transaction(self):
        yield object()

    def settings(self, _conn):
        return dict(self.settings_values)

    def get_owner_exit_interview(self, _code, _season_year):
        return self.existing

    def start_owner_exit_interview(self, _code, _season_year, _session, _owner_message):
        return self.started

    def complete_owner_exit_interview(self, *_args):
        return self.completed

    def reset_owner_exit_interview(self, _code, _season_year):
        return self.reset_result


class FakeInterviewComposer:
    def opening_message(self, _office, _season_year, *, session):
        return f"Welcome {session['name']}"

    def final_reply(self, _office, _season_year, _owner_message, _gm_response, *, session):
        return f"Reply to {session['name']}", "Next season", 1


class OwnerExitInterviewServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = FakeOwnerOfficeRepository()
        self.service = OwnerOfficeService(
            self.repository,
            now=lambda: "2025-01-01T00:00:00Z",
            min_year=2025,
            max_year=2035,
            forecast_window=5,
            objective_options=[],
            interview_composer=FakeInterviewComposer(),
        )
        self.office = {"team_code": "ATL", "entries": {}, "owner_profile": {}}
        self.refreshed = {**self.office, "refreshed": True}
        self.session = {"name": "GM", "email": "gm@example.com"}

    def test_start_owns_composition_persistence_and_refresh(self) -> None:
        self.service.get = Mock(side_effect=[self.office, self.refreshed])

        result = self.service.update_exit_interview(
            "ATL", "start", {}, self.session, include_private=False
        )

        self.assertEqual(result["response"]["interview"], self.repository.started)
        self.assertEqual(result["response"]["owner_office"], self.refreshed)

    def test_reply_owns_completion_and_refresh(self) -> None:
        self.repository.existing = {
            "id": 1,
            "status": "awaiting_gm",
            "owner_message": "How did the season go?",
        }
        self.service.get = Mock(side_effect=[self.office, self.refreshed])

        result = self.service.update_exit_interview(
            "ATL",
            "reply",
            {"gm_response": "We have a clear plan for next season."},
            self.session,
            include_private=True,
        )

        self.assertEqual(result["response"]["interview"], self.repository.completed)
        self.assertEqual(result["response"]["owner_office"], self.refreshed)

    def test_reset_returns_audit_command(self) -> None:
        self.service.get = Mock(return_value=self.refreshed)

        result = self.service.update_exit_interview(
            "atl", "reset", {}, self.session, include_private=True
        )

        self.assertEqual(result["audit"]["entity_id"], "ATL:2025")
        self.assertEqual(result["response"]["owner_office"], self.refreshed)

    def test_rejects_wrong_season_and_disabled_free_agency(self) -> None:
        with self.assertRaises(OwnerExitInterviewError) as wrong_season:
            self.service.update_exit_interview(
                "ATL", "start", {"season_year": 2024}, self.session, include_private=False
            )
        self.assertEqual(wrong_season.exception.code, "invalid_exit_interview_season")
        self.assertEqual(wrong_season.exception.details, {"season_year": 2025})

        self.repository.settings_values["free_agency_mode"] = "0"
        with self.assertRaises(OwnerExitInterviewError) as disabled:
            self.service.update_exit_interview(
                "ATL", "start", {}, self.session, include_private=False
            )
        self.assertEqual(disabled.exception.code, "free_agency_mode_required")


if __name__ == "__main__":
    unittest.main()
