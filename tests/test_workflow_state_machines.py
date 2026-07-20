import os
import sqlite3
import tempfile
import unittest

from tests.db_helpers import connect_test_db

from app.server import LeagueDB
from app.workflow_states import WorkflowTransitionError, workflow_definition
from app.xlsx_import import create_schema, now_iso


def insert_team(conn: sqlite3.Connection, code: str, name: str) -> None:
    timestamp = now_iso()
    conn.execute(
        """
        INSERT INTO teams (
            code, name, gm, cash_note, apron_hard_cap,
            salary_cap, luxury_cap, first_apron, second_apron,
            created_at, updated_at
        ) VALUES (?, ?, NULL, NULL, NULL, 154647000, 187896105, 195945000, 207824000, ?, ?)
        """,
        (code, name, timestamp, timestamp),
    )


class WorkflowStateMachineTests(unittest.TestCase):
    def setUp(self) -> None:
        fd, path = tempfile.mkstemp(prefix="anba-workflows-", suffix=".db")
        os.close(fd)
        self.db_path = path
        with connect_test_db(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            create_schema(conn)
            insert_team(conn, "ATL", "Atlanta Hawks")
            conn.commit()
        self.db = LeagueDB(self.db_path)
        self.db.ensure_auth_schema()
        free_agent_id = self.db.create_free_agent(
            {
                "name": "Workflow Test Player",
                "position": "SG",
                "rating": "75",
                "free_agent_type": "No restringido",
            }
        )
        self.assertIsNotNone(free_agent_id)
        self.free_agent_id = int(free_agent_id)

    def tearDown(self) -> None:
        try:
            os.unlink(self.db_path)
        except FileNotFoundError:
            pass

    def create_offer_request(self) -> dict:
        request = self.db.create_gm_free_agent_offer_request(
            self.free_agent_id,
            "ATL",
            {"contract_type": "Min", "years": 1},
            {"email": "gm@example.com", "name": "ATL GM", "role": "gm"},
        )
        self.assertIsNotNone(request)
        return request

    def workflow_log(self, request_id: int) -> list[sqlite3.Row]:
        with connect_test_db(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            return conn.execute(
                """
                SELECT *
                FROM workflow_transition_log
                WHERE workflow_type = 'gm_free_agent_offer_request'
                  AND resource_id = ?
                ORDER BY id
                """,
                (str(request_id),),
            ).fetchall()

    def test_unknown_workflows_are_denied_by_default(self) -> None:
        with self.assertRaises(WorkflowTransitionError) as context:
            workflow_definition("unregistered_workflow")

        self.assertEqual("unknown_workflow", context.exception.code)

    def test_offer_cancellation_is_persisted_and_audited(self) -> None:
        request = self.create_offer_request()
        request_id = int(request["id"])

        cancelled = self.db.cancel_gm_free_agent_offer_request(
            request_id,
            "ATL",
            {"email": "gm@example.com", "name": "ATL GM", "role": "gm"},
        )

        self.assertIsNotNone(cancelled)
        stored = self.db.get_gm_free_agent_offer_request(request_id)
        self.assertIsNotNone(stored)
        self.assertEqual("cancelled", stored["status"])
        transitions = self.workflow_log(request_id)
        self.assertEqual(2, len(transitions))
        self.assertEqual(("__none__", "pending"), (transitions[0]["previous_state"], transitions[0]["new_state"]))
        self.assertEqual(("pending", "cancelled"), (transitions[1]["previous_state"], transitions[1]["new_state"]))
        self.assertEqual("gm@example.com", transitions[1]["actor_email"])
        self.assertEqual("offer_cancelled_by_team", transitions[1]["reason"])
        self.assertTrue(str(transitions[1]["command_id"] or ""))

    def test_terminal_offer_cannot_be_decided_twice(self) -> None:
        request = self.create_offer_request()
        request_id = int(request["id"])
        admin = {"email": "admin@example.com", "name": "Admin", "role": "admin"}

        approved = self.db.mark_gm_free_agent_offer_request_decided(request_id, "approved", admin)
        rejected = self.db.mark_gm_free_agent_offer_request_decided(request_id, "rejected", admin)

        self.assertIsNotNone(approved)
        self.assertIsNone(rejected)
        transitions = self.workflow_log(request_id)
        self.assertEqual(["pending", "approved"], [row["new_state"] for row in transitions])

    def test_same_command_retry_is_idempotent(self) -> None:
        request = self.create_offer_request()
        request_id = int(request["id"])
        command_id = "workflow-test-offer-approval"
        timestamp = now_iso()
        admin = {"email": "admin@example.com", "name": "Admin", "role": "admin"}

        with self.db.transaction("IMMEDIATE") as conn:
            first = self.db._transition_workflow_conn(
                conn,
                "gm_free_agent_offer_request",
                request_id,
                "approved",
                actor=admin,
                reason="test_approval",
                command_id=command_id,
                updates={"updated_at": timestamp, "decided_at": timestamp},
                timestamp=timestamp,
            )
        with self.db.transaction("IMMEDIATE") as conn:
            second = self.db._transition_workflow_conn(
                conn,
                "gm_free_agent_offer_request",
                request_id,
                "approved",
                actor=admin,
                reason="test_approval_retry",
                command_id=command_id,
                updates={"updated_at": timestamp, "decided_at": timestamp},
                timestamp=timestamp,
            )

        self.assertFalse(first["idempotent"])
        self.assertTrue(second["idempotent"])
        with connect_test_db(self.db_path) as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM workflow_transition_log WHERE command_id = ?",
                (command_id,),
            ).fetchone()[0]
        self.assertEqual(1, count)

    def test_reused_command_cannot_target_a_different_state(self) -> None:
        request = self.create_offer_request()
        request_id = int(request["id"])
        timestamp = now_iso()
        with self.db.transaction("IMMEDIATE") as conn:
            self.db._transition_workflow_conn(
                conn,
                "gm_free_agent_offer_request",
                request_id,
                "approved",
                command_id="shared-command",
                updates={"updated_at": timestamp, "decided_at": timestamp},
            )

        with self.assertRaises(WorkflowTransitionError) as context:
            with self.db.transaction("IMMEDIATE") as conn:
                self.db._transition_workflow_conn(
                    conn,
                    "gm_free_agent_offer_request",
                    request_id,
                    "rejected",
                    command_id="shared-command",
                    updates={"updated_at": timestamp, "decided_at": timestamp},
                )

        self.assertEqual("command_reused", context.exception.code)

    def test_trade_workflow_has_no_transition_out_of_terminal_states(self) -> None:
        definition = workflow_definition("trade_command")

        self.assertEqual(frozenset({"validating", "rejected"}), definition.transitions["draft"])
        self.assertEqual(frozenset({"processing", "rejected", "failed"}), definition.transitions["validating"])
        self.assertNotIn("completed", definition.transitions)
        self.assertNotIn("rejected", definition.transitions)
        self.assertNotIn("failed", definition.transitions)


if __name__ == "__main__":
    unittest.main()
