"""Explicit, scoped import of private supplier lists and optional annual evidence.

Run migrations first. Source JSON is produced by scripts/prepare_supplier_baseline.py;
it is intentionally never bundled in the application or imported into other scopes.
"""
import argparse
import hashlib
import json
from pathlib import Path

from app.core.config import Settings
from app.modules.identity.auth import Principal
from app.modules.processing.service import commit_or_conflict
from app.modules.suppliers import service
from app.persistence import make_engine, session_factory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", required=True, type=Path)
    parser.add_argument("--scope", required=True)
    parser.add_argument("--actor", default="supplier-initialization")
    parser.add_argument("--baseline-only", action="store_true", help="Import evidence after initializing the original lists")
    parser.add_argument("--initial-report", action="store_true", help="Freeze original statuses in an idempotent initial report")
    parser.add_argument("--output", type=Path, help="Export both lists from the initial report")
    args = parser.parse_args()
    settings = Settings()
    if args.scope != settings.scope_id:
        parser.error("--scope debe coincidir con DATASTAGE_SCOPE_ID")
    payload = json.loads(args.seed.read_text(encoding="utf-8"))
    if payload.get("scopeId") != args.scope:
        parser.error("El archivo pertenece a otro ámbito")
    if args.baseline_only and args.initial_report:
        parser.error("Importa evidencia y genera el reporte inicial en pasos separados")
    if args.output and not args.initial_report:
        parser.error("--output requiere --initial-report")
    principal = Principal(args.actor, args.actor, frozenset({"Admin", "Operator", "Reader"}), args.scope)
    engine = make_engine(settings.database_url)
    factory = session_factory(engine)
    try:
        with factory() as session:
            if args.baseline_only:
                result = service.ingest_baseline(session, principal, payload["baseline"])
                report = None
            else:
                result = service.initialize_seed(session, principal, payload)
                report = None
                if args.initial_report:
                    source = {kind: payload.get(kind, []) for kind in ("national", "foreign")}
                    digest = hashlib.sha256(json.dumps(source, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
                    report = service.create_report(session, principal, f"supplier-initial:{digest}", "Listas iniciales de proveedores")
            commit_or_conflict(session)
            if report and args.output:
                args.output.mkdir(parents=True, exist_ok=True)
                for kind in ("national", "foreign"):
                    content = service.report_xlsx(session, args.scope, report["id"], kind)
                    path = args.output / f"proveedores_{kind}_{report['id']}.xlsx"
                    path.write_bytes(content)
            print(json.dumps({"summary": result, "report": report}, ensure_ascii=True))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
