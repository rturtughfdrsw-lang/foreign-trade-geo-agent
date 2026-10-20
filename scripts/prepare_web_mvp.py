"""Explicit offline preparation for the local Web MVP; never contacts providers.

The pre-generated TEST-only article and its original journal stay frozen in
candidate/. A separate journal starts at missing evidence for browser operations.
"""
import argparse
import json
from pathlib import Path

from scripts.demo_seo_e_only import prepare as prepare_candidate
from foreign_trade_geo_agent.storage.evidence_intake import SQLiteEvidenceIntakeStore
from foreign_trade_geo_agent.storage.sqlite import SQLiteHistoryReader
from foreign_trade_geo_agent.workflows.evidence_intake import EvidenceIntakeWorkflow
from foreign_trade_geo_agent.workflows.planning_evidence import PlanningEvidenceWorkflow


def prepare(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    metadata = prepare_candidate(directory / "candidate")
    original_store = SQLiteEvidenceIntakeStore(directory / "candidate/intake.sqlite3")
    original = original_store.get_revision(metadata["project_id"], metadata["task_id"], 1)
    store = SQLiteEvidenceIntakeStore.create(directory / "interactive-intake.sqlite3")
    planning = PlanningEvidenceWorkflow(SQLiteHistoryReader(directory / "candidate/history.sqlite3"),
                                        EvidenceIntakeWorkflow(store))
    planning.register(original.task.project_id, original.task.task_id,
                      customer_id=original.task.customer_id, requirements=original.task.requirements)
    session = {"profile": "SYNTHETIC_LOCAL_MVP_V1", "project_id": metadata["project_id"],
               "task_id": metadata["task_id"], "candidate_run_id": metadata["run_id"],
               "candidate_artifact_id": metadata["artifact_id"]}
    (directory / "session.json").write_text(json.dumps(session, indent=2), encoding="utf-8")
    return session


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path(".data/seo-mvp"))
    args = parser.parse_args()
    prepare(args.output_dir)
    print("Offline NovaCNC package saved. Article is pre-generated SYNTHETIC TEST ONLY.")
    print("Open http://127.0.0.1:8000/mvp after starting the existing Web server.")
