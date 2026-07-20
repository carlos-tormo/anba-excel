import ast
import inspect
import unittest

from app.db.repositories.draft import DraftReadOperations, DraftRepository
from app.db.repositories.trades import TradeOperations
from app.db.repositories.waivers import WaiverOperations, WaiverRepository
from app.server import LeagueDB
from app.services.trades import TradeService


class WorkflowRepositoryBoundaryTests(unittest.TestCase):
    def test_league_db_compatibility_facade_does_not_access_connections_or_sql(self) -> None:
        tree = ast.parse(inspect.getsource(LeagueDB))
        persistence_calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr
            in {"connect", "transaction", "execute", "executemany", "executescript"}
        ]
        self.assertEqual([], persistence_calls)

    def test_domain_operation_bundles_do_not_expose_workflow_or_outbox_callbacks(self) -> None:
        source = "\n".join(
            inspect.getsource(operations)
            for operations in (DraftReadOperations, WaiverOperations, TradeOperations)
        )
        for callback in (
            "record_workflow_creation_conn",
            "transition_workflow_conn",
            "workflow_actor_fields",
            "record_workflow_creation:",
            "transition_workflow:",
            "enqueue_outbox_event:",
        ):
            self.assertNotIn(callback, source)

    def test_draft_waiver_and_trade_use_concrete_infrastructure_collaborators(self) -> None:
        self.assertIn("self.workflows", inspect.getsource(DraftRepository))
        self.assertIn("self.workflows", inspect.getsource(WaiverRepository))
        trade_source = inspect.getsource(TradeService)
        self.assertIn("self.workflows", trade_source)
        self.assertIn("self.outbox", trade_source)

    def test_server_compatibility_methods_do_not_own_workflow_or_outbox_sql(self) -> None:
        methods = (
            LeagueDB._record_workflow_creation_conn,
            LeagueDB._transition_workflow_conn,
            LeagueDB.enqueue_outbox_event_conn,
            LeagueDB.enqueue_outbox_event,
            LeagueDB.get_outbox_event,
            LeagueDB.mark_outbox_event_succeeded,
            LeagueDB.mark_outbox_event_failed,
        )
        source = "\n".join(inspect.getsource(method) for method in methods)
        for sql_fragment in (
            "INSERT INTO workflow_transition_log",
            "INSERT OR IGNORE INTO workflow_transition_log",
            "UPDATE {definition.table}",
            "INSERT OR IGNORE INTO outbox_events",
            "SELECT id, event_type, aggregate_type",
            "UPDATE outbox_events",
        ):
            self.assertNotIn(sql_fragment, source)


if __name__ == "__main__":
    unittest.main()
