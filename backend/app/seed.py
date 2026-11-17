"""Fill a dev database with test data. Run: docker compose exec backend python -m app.seed

Dev only. Every seeded account uses the password in SEED_PASSWORD. The coordinator comes from ADMIN_NAME /
ADMIN_EMAIL / ADMIN_ID_NUMBER / ADMIN_PASSWORD. Safe to re-run: it stops if the data is already there.

Seeds: 5 faculty, 8 students in different states (no group, pending, active with uploads, co-supervised, P2,
frozen, awaiting approval), deadlines for P1-P3, and proposal versions with small PDF files.
"""

import hashlib
import uuid
from datetime import datetime, timedelta, timezone

from app.config import settings
from app.database import SessionLocal
from app.models import MilestoneTemplate, Phase, Proposal, ProposalVersion, Thesis, ThesisStatus
from app.models.user import Role
from app.services import auth_service, progress_service
from app.services.proposal_service import _upload_dir

FACULTY = [
    ("faculty@bracu.ac.bd", "20000001", "Demo Faculty", "DF"),
    ("ahsan.habib@bracu.ac.bd", "20000002", "Ahsan Habib", "AH"),
    ("nusrat.jahan@bracu.ac.bd", "20000003", "Nusrat Jahan", "NJ"),
    ("tanvir.rahman@bracu.ac.bd", "20000004", "Tanvir Rahman", "TR"),
    ("farzana.akter@bracu.ac.bd", "20000005", "Farzana Akter", "FA"),
]

# (email, id, name, approved, state, supervisor initials, co-supervisor initials, versions)
STUDENTS = [
    ("student@g.bracu.ac.bd", "10000001", "Demo Student", True, None, None, None, 0),
    ("rafiul.islam@g.bracu.ac.bd", "10000002", "Rafiul Islam", True, "pending", "AH", None, 0),
    ("sadia.karim@g.bracu.ac.bd", "10000003", "Sadia Karim", True, "active", "DF", None, 2),
    ("imran.hossain@g.bracu.ac.bd", "10000004", "Imran Hossain", True, "active", "NJ", "TR", 3),
    ("mitu.chowdhury@g.bracu.ac.bd", "10000005", "Mitu Chowdhury", True, "active", "AH", "FA", 1),
    ("arif.mahmud@g.bracu.ac.bd", "10000006", "Arif Mahmud", True, "p2", "DF", None, 1),
    ("lamia.sultana@g.bracu.ac.bd", "10000007", "Lamia Sultana", True, "frozen", "TR", None, 1),
    ("zahid.hasan@g.bracu.ac.bd", "10000008", "Zahid Hasan", False, None, None, None, 0),  # waits in registration requests
]

TITLES = [
    "Federated Learning for Bangla Speech Recognition",
    "Low-Cost IoT Flood Early Warning for Sylhet",
    "Detecting Fake News in Bangla Social Media",
    "Energy-Aware Scheduling for Edge Devices",
    "Blockchain Land Registry Prototype",
    "Crop Disease Detection with Lightweight CNNs",
    "Traffic Congestion Prediction in Dhaka",
]


def _pdf(text: str) -> bytes:
    # Smallest valid one-page PDF; good enough for the viewer and the download endpoint.
    stream = f"BT /F1 18 Tf 72 720 Td ({text}) Tj ET".encode()
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offsets = b"%PDF-1.4\n", []
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    return out


def main():
    if not settings.seed_password:
        raise SystemExit("Set SEED_PASSWORD in .env")
    pw = settings.seed_password
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        if auth_service.get_by_id_number(db, STUDENTS[-1][1]):  # by ID: emails changed over time
            raise SystemExit("Seed data already present")

        for phase, days in ((Phase.P1, 14), (Phase.P2, 45), (Phase.P3, 90)):
            if db.get(MilestoneTemplate, phase) is None:
                db.add(MilestoneTemplate(phase=phase, due_at=now + timedelta(days=days), grace_days=3, penalty_per_day=5))
        db.commit()

        fac = {}
        for email, id_number, name, initials in FACULTY:
            fac[initials] = auth_service.get_by_email(db, email) or auth_service.create_user(
                db, email, id_number, name, pw, Role.faculty, initials=initials
            )

        titles = iter(TITLES)
        for email, id_number, name, approved, state, sup, co, n_versions in STUDENTS:
            student = auth_service.get_by_email(db, email) or auth_service.create_user(
                db, email, id_number, name, pw, Role.student, approved=approved
            )
            if state is None:
                db.commit()
                print(f"created {email} (ID {id_number})")
                continue
            thesis = Thesis(
                student_id=student.id,
                supervisor_id=fac[sup].id,
                status=ThesisStatus.pending if state == "pending" else ThesisStatus.active,
                code=None if state == "pending" else progress_service.new_code(db),
                p1_registered=state != "pending",
                # Backdated so seeded uploads (an hour ago and later) count toward this phase.
                phase=Phase.P2 if state == "p2" else Phase.P1,
                phase_started_at=now - timedelta(days=2),
                frozen_at=now - timedelta(days=1) if state == "frozen" else None,
            )
            if co:
                thesis.co_supervisor_id = fac[co].id
                thesis.co_supervisor_accepted = thesis.co_supervisor_approved = True
            db.add(thesis)
            db.flush()
            student.thesis_id = thesis.id

            if n_versions:
                title = next(titles)
                proposal = Proposal(thesis_id=thesis.id)
                db.add(proposal)
                db.flush()
                for v in range(1, n_versions + 1):
                    data = _pdf(f"{title} - draft {v}")
                    stored = f"{uuid.uuid4().hex}.pdf"
                    (_upload_dir() / stored).write_bytes(data)
                    db.add(ProposalVersion(
                        proposal_id=proposal.id, version_no=v, phase=thesis.phase, title=title,
                        abstract=f"Draft {v} of the proposal for {title.lower()}. Problem, method and expected results.",
                        original_filename=f"proposal_v{v}.pdf", stored_filename=stored, size_bytes=len(data),
                        sha256=hashlib.sha256(data).hexdigest(), uploaded_by_id=student.id,
                        created_at=now - timedelta(hours=n_versions - v + 1),
                    ))
                gm = progress_service.group_milestone(db, student, create=True)
                progress_service.sync_deliverable(db, gm, student)
            db.commit()
            print(f"created {email} (ID {id_number}, {state}, {n_versions} versions)")


if __name__ == "__main__":
    main()
