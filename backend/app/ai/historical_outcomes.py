"""
Historical comparable-stage outcomes for compute_success_probability()
(see ai/tasks.py::_build_history_block()). "Comparable" was deliberately
defined as "reached at least the same pipeline stage" rather than by
company/industry or job-title similarity -- the most statistically grounded
signal already present in the data model, via Application.pre_rejection_status
(the main_status a now-rejected application was in right before rejection).
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app import models
from app.ai.tasks import _STATUS_LABELS

_PIPELINE_ORDER = ["prospecting", "applied", "hr", "fb", "waiting", "negotiating", "signed"]


def compute_stage_outcomes(db: Session, user_id: int, current_app: "models.Application") -> dict | None:
    """Among the user's OTHER terminal applications (rejected/signed), how many
    reached at least the same pipeline stage `current_app` currently sits at?
    Signed applications count as having reached every stage. Rejected
    applications use pre_rejection_status (the stage right before rejection);
    rows predating that field (None) are excluded rather than guessed.

    Returns None if fewer than 2 comparable applications exist -- too little
    data for a meaningful rate."""
    cur_idx = _PIPELINE_ORDER.index(current_app.main_status) if current_app.main_status in _PIPELINE_ORDER else 0

    others = (
        db.query(models.Application)
        .filter(
            models.Application.user_id == user_id,
            models.Application.id != current_app.id,
            models.Application.main_status.in_(["rejected", "signed"]),
        )
        .all()
    )

    comparable_signed = 0
    comparable_rejected = 0
    for a in others:
        if a.main_status == "signed":
            comparable_signed += 1
            continue
        stage = a.pre_rejection_status
        if stage not in _PIPELINE_ORDER:
            continue
        if _PIPELINE_ORDER.index(stage) >= cur_idx:
            comparable_rejected += 1

    total = comparable_signed + comparable_rejected
    if total < 2:
        return None

    return {
        "total": total,
        "signed": comparable_signed,
        "rejected": comparable_rejected,
        "stage_label": _STATUS_LABELS.get(current_app.main_status, current_app.main_status),
    }
