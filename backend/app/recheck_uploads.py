"""Re-run the upload check on every stored proposal PDF. Run: docker compose exec backend python -m app.recheck_uploads

Files that pass are replaced by the checked rewrite (proposal_service._check_pdf). Files that fail are kept and listed.
Safe to re-run.
"""

from app.database import SessionLocal
from app.services.proposal_service import recheck_stored_files


def main():
    with SessionLocal() as db:
        rewritten, failed = recheck_stored_files(db)
    print(f"Rewrote {rewritten} file(s).")
    for version_id, why in failed:
        print(f"Kept as is, version {version_id}: {why}")


if __name__ == "__main__":
    main()
