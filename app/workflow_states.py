from dataclasses import dataclass
from typing import FrozenSet, Mapping


class WorkflowTransitionError(ValueError):
    """Raised when a workflow command attempts an invalid state transition."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class WorkflowDefinition:
    table: str
    key_column: str
    state_column: str
    transitions: Mapping[str, FrozenSet[str]]
    mutable_columns: FrozenSet[str]


WORKFLOW_DEFINITIONS = {
    "gm_option_request": WorkflowDefinition(
        table="gm_option_requests",
        key_column="id",
        state_column="status",
        transitions={"pending": frozenset({"approved", "rejected"})},
        mutable_columns=frozenset(
            {"admin_email", "admin_name", "admin_decision_note", "updated_at", "decided_at"}
        ),
    ),
    "gm_draft_pick_request": WorkflowDefinition(
        table="gm_draft_pick_requests",
        key_column="id",
        state_column="status",
        transitions={"pending": frozenset({"approved", "rejected"})},
        mutable_columns=frozenset(
            {"admin_email", "admin_name", "admin_decision_note", "updated_at", "decided_at"}
        ),
    ),
    "gm_free_agent_offer_request": WorkflowDefinition(
        table="gm_free_agent_offer_requests",
        key_column="id",
        state_column="status",
        transitions={"pending": frozenset({"approved", "rejected", "cancelled"})},
        mutable_columns=frozenset(
            {"admin_email", "admin_name", "admin_decision_note", "updated_at", "decided_at"}
        ),
    ),
    "waiver_claim": WorkflowDefinition(
        table="waiver_claims",
        key_column="id",
        state_column="status",
        transitions={"pending": frozenset({"approved", "rejected"})},
        mutable_columns=frozenset(
            {"admin_email", "admin_name", "admin_decision_note", "updated_at", "decided_at"}
        ),
    ),
    "waiver_player": WorkflowDefinition(
        table="waiver_players",
        key_column="id",
        state_column="status",
        transitions={
            "active": frozenset({"pending_claims", "claimed", "expired"}),
            "pending_claims": frozenset({"claimed", "expired"}),
        },
        mutable_columns=frozenset(
            {"claimed_team_code", "player_id", "free_agent_id", "dead_contract_id", "updated_at"}
        ),
    ),
    "trade_command": WorkflowDefinition(
        table="workflow_runs",
        key_column="id",
        state_column="state",
        transitions={
            "draft": frozenset({"validating", "rejected"}),
            "validating": frozenset({"processing", "rejected", "failed"}),
            "processing": frozenset({"completed", "rejected", "failed"}),
        },
        mutable_columns=frozenset({"reason", "metadata_json", "updated_at", "completed_at"}),
    ),
}


def workflow_definition(workflow_type: str) -> WorkflowDefinition:
    definition = WORKFLOW_DEFINITIONS.get(str(workflow_type or "").strip())
    if definition is None:
        raise WorkflowTransitionError(
            "unknown_workflow",
            f"Unknown workflow type: {workflow_type}",
        )
    return definition
