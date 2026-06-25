from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date, timedelta
from typing import Optional

from app.database import get_db
from app import models
from app.models import MAIN_STATUS_LABELS

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

# Status pipeline order (excluding rejected)
PIPELINE = ["prospecting", "applied", "hr", "fb", "waiting", "negotiating", "signed"]
PIPELINE_RANK = {s: i for i, s in enumerate(PIPELINE)}


def _effective_status(app: models.Application) -> str:
    """Return the highest pipeline stage this application reached."""
    if app.main_status == "rejected":
        pre = app.pre_rejection_status
        if pre and pre in PIPELINE_RANK:
            return pre
        return "applied"
    return app.main_status


@router.get("/summary")
def analytics_summary(db: Session = Depends(get_db)):
    apps = db.query(models.Application).all()

    if not apps:
        empty_funnel = [
            {"status": s, "label": MAIN_STATUS_LABELS.get(s, s), "count": 0, "pct": 0.0}
            for s in PIPELINE
        ]
        return {
            "kpis": {
                "total": 0, "active": 0, "rejected": 0, "signed": 0,
                "ghosting_count": 0, "ghosting_rate": 0.0,
                "hh_count": 0, "direct_count": 0, "hh_pct": 0.0,
                "conversion_gespräch": 0.0, "conversion_offer": 0.0,
                "avg_days_to_gespräch": None, "avg_days_applied_to_rejected": None,
            },
            "funnel": empty_funnel,
            "by_month": [],
            "by_source": [],
            "hh_vs_direct": {
                "hh": {"total": 0, "gespräch": 0, "offer": 0},
                "direct": {"total": 0, "gespräch": 0, "offer": 0},
            },
            "rejection_by_status": [],
            "company_sync": {"total": 0, "pending": 0, "done": 0, "failed": 0},
        }

    total = len(apps)
    rejected_apps = [a for a in apps if a.main_status == "rejected"]
    active_apps = [a for a in apps if a.main_status != "rejected"]
    rejected = len(rejected_apps)
    active = len(active_apps)
    signed = sum(1 for a in apps if a.main_status == "signed")
    ghosting_count = sum(1 for a in apps if a.ghosting)
    ghosting_rate = round(ghosting_count / total, 4) if total else 0.0
    hh_count = sum(1 for a in apps if a.is_headhunter)
    direct_count = total - hh_count
    hh_pct = round(hh_count / total, 4) if total else 0.0

    # Funnel: for each stage, count apps that reached it or beyond
    funnel_counts = {}
    for app in apps:
        eff = _effective_status(app)
        rank = PIPELINE_RANK.get(eff, 1)  # default to applied rank
        for stage in PIPELINE:
            if PIPELINE_RANK[stage] <= rank:
                funnel_counts[stage] = funnel_counts.get(stage, 0) + 1

    funnel_base = funnel_counts.get("prospecting", total)
    funnel = [
        {
            "status": s,
            "label": MAIN_STATUS_LABELS.get(s, s),
            "count": funnel_counts.get(s, 0),
            "pct": round(funnel_counts.get(s, 0) / funnel_base, 4) if funnel_base else 0.0,
        }
        for s in PIPELINE
    ]

    # Conversions
    applied_or_beyond = funnel_counts.get("applied", 0)
    hr_or_beyond = funnel_counts.get("hr", 0)
    offer_or_beyond = funnel_counts.get("negotiating", 0) + signed

    conversion_gespräch = round(hr_or_beyond / applied_or_beyond, 4) if applied_or_beyond else 0.0
    conversion_offer = round(offer_or_beyond / applied_or_beyond, 4) if applied_or_beyond else 0.0

    # Avg days to first Gespräch
    app_ids = [a.id for a in apps]
    first_gespraeche = dict(
        db.query(models.Event.application_id, func.min(models.Event.datum))
        .filter(
            models.Event.application_id.in_(app_ids),
            models.Event.typ.in_(["gespräch", "anruf"]),
            models.Event.datum.isnot(None),
        )
        .group_by(models.Event.application_id)
        .all()
    )

    days_to_gespräch_list = []
    for app in apps:
        if app.datum_bewerbung and app.id in first_gespraeche:
            fg = first_gespraeche[app.id]
            if fg and isinstance(fg, date):
                delta = (fg - app.datum_bewerbung).days
                if 0 <= delta <= 365:
                    days_to_gespräch_list.append(delta)

    avg_days_to_gespräch: Optional[float] = None
    if days_to_gespräch_list:
        avg_days_to_gespräch = round(sum(days_to_gespräch_list) / len(days_to_gespräch_list), 1)

    # Avg days applied to rejected
    days_to_rejected = []
    for app in rejected_apps:
        if app.datum_bewerbung and app.letztes_update:
            delta = (app.letztes_update - app.datum_bewerbung).days
            if 0 <= delta <= 730:
                days_to_rejected.append(delta)

    avg_days_applied_to_rejected: Optional[float] = None
    if days_to_rejected:
        avg_days_applied_to_rejected = round(sum(days_to_rejected) / len(days_to_rejected), 1)

    # By month (last 12 months)
    today = date.today()
    month_counts: dict[str, int] = {}
    for i in range(11, -1, -1):
        d = today.replace(day=1) - timedelta(days=i * 28)
        key = d.strftime("%Y-%m")
        month_counts[key] = 0

    for app in apps:
        if app.datum_bewerbung:
            key = app.datum_bewerbung.strftime("%Y-%m")
            if key in month_counts:
                month_counts[key] = month_counts.get(key, 0) + 1

    month_labels = {
        "01": "Jan", "02": "Feb", "03": "Mär", "04": "Apr", "05": "Mai", "06": "Jun",
        "07": "Jul", "08": "Aug", "09": "Sep", "10": "Okt", "11": "Nov", "12": "Dez",
    }

    by_month = []
    for key in sorted(month_counts.keys()):
        year, month = key.split("-")
        label = f"{month_labels.get(month, month)} {year}"
        by_month.append({"month": key, "label": label, "count": month_counts[key]})

    # By source
    source_counts: dict[str, int] = {}
    for app in apps:
        src = (app.quelle or "Unbekannt").strip() or "Unbekannt"
        source_counts[src] = source_counts.get(src, 0) + 1
    by_source = [
        {"source": k, "count": v}
        for k, v in sorted(source_counts.items(), key=lambda x: -x[1])
    ]

    # HH vs Direct
    def _reached(app: models.Application, stage: str) -> bool:
        eff = _effective_status(app)
        return PIPELINE_RANK.get(eff, 0) >= PIPELINE_RANK.get(stage, 999)

    hh_apps = [a for a in apps if a.is_headhunter]
    direct_apps = [a for a in apps if not a.is_headhunter]

    hh_vs_direct = {
        "hh": {
            "total": len(hh_apps),
            "gespräch": sum(1 for a in hh_apps if _reached(a, "hr")),
            "offer": sum(1 for a in hh_apps if _reached(a, "negotiating")),
        },
        "direct": {
            "total": len(direct_apps),
            "gespräch": sum(1 for a in direct_apps if _reached(a, "hr")),
            "offer": sum(1 for a in direct_apps if _reached(a, "negotiating")),
        },
    }

    # Rejection by status (where were apps when rejected)
    rej_by_status: dict[str, int] = {}
    for app in rejected_apps:
        pre = app.pre_rejection_status or "applied"
        if pre not in PIPELINE_RANK:
            pre = "applied"
        rej_by_status[pre] = rej_by_status.get(pre, 0) + 1

    rejection_by_status = [
        {
            "status": s,
            "label": MAIN_STATUS_LABELS.get(s, s),
            "count": rej_by_status.get(s, 0),
        }
        for s in PIPELINE
        if rej_by_status.get(s, 0) > 0
    ]

    # Company sync stats
    profiles = db.query(models.CompanyProfile).all()
    sync_pending = sum(1 for p in profiles if p.sync_status == "pending")
    sync_done = sum(1 for p in profiles if p.sync_status == "done")
    sync_failed = sum(1 for p in profiles if p.sync_status == "failed")

    company_sync = {
        "total": len(profiles),
        "pending": sync_pending,
        "done": sync_done,
        "failed": sync_failed,
    }

    return {
        "kpis": {
            "total": total,
            "active": active,
            "rejected": rejected,
            "signed": signed,
            "ghosting_count": ghosting_count,
            "ghosting_rate": ghosting_rate,
            "hh_count": hh_count,
            "direct_count": direct_count,
            "hh_pct": hh_pct,
            "conversion_gespräch": conversion_gespräch,
            "conversion_offer": conversion_offer,
            "avg_days_to_gespräch": avg_days_to_gespräch,
            "avg_days_applied_to_rejected": avg_days_applied_to_rejected,
        },
        "funnel": funnel,
        "by_month": by_month,
        "by_source": by_source,
        "hh_vs_direct": hh_vs_direct,
        "rejection_by_status": rejection_by_status,
        "company_sync": company_sync,
    }
