"""Fill a dev database with test data. Run: docker compose exec backend python -m app.seed

Dev only. Every seeded account uses the password in SEED_PASSWORD. The coordinator comes from ADMIN_NAME /
ADMIN_EMAIL / ADMIN_ID_NUMBER / ADMIN_PASSWORD. One transaction: it stops if the data is already there.

Seeds: 5 faculty; thesis groups in every state (pending, formed, active with uploads and meetings, co-supervised,
P2, frozen); a ready group with no thesis; a 2-member group inviting the demo student; loose students with
teammate-finder profiles; one sign-up awaiting approval, one deletion request, one restart request, one title change.
"""

import hashlib
import uuid
from datetime import datetime, timedelta, timezone

from app.config import settings
from app.database import SessionLocal
from app.models import (
    Meeting, MeetingTask, MilestoneTemplate, Phase, Proposal, ProposalVersion, Semester, Thesis, ThesisStatus,
    TitleChange, User,
)
from app.models.group import Group, GroupMember, Invitation, StudentProfile
from app.models.user import Role
from app.security import hash_password
from app.services import auth_service, progress_service
from app.services.proposal_service import _upload_dir

FACULTY = [
    ("faculty@bracu.ac.bd", "20000001", "Demo Faculty", "DF"),
    ("ahsan.habib@bracu.ac.bd", "20000002", "Ahsan Habib", "AH"),
    ("nusrat.jahan@bracu.ac.bd", "20000003", "Nusrat Jahan", "NJ"),
    ("tanvir.rahman@bracu.ac.bd", "20000004", "Tanvir Rahman", "TR"),
    ("farzana.akter@bracu.ac.bd", "20000005", "Farzana Akter", "FA"),
]

# (group name, state, supervisor, co-supervisor, versions, title, members). The first member leads and asked.
GROUPS = [
    ("Speech Lab", "pending", "AH", None, 0, None, ["Rafiul Islam", "Nabila Ahmed", "Fahim Rahman"]),
    ("Flood Watch", "formed", "NJ", None, 0, None, ["Tasnim Haque", "Rakib Hasan", "Sumaiya Akter"]),
    ("Fake News", "active", "DF", None, 2, "Detecting Fake News in Bangla Social Media",
     ["Sadia Karim", "Mahir Faisal", "Anika Tabassum"]),
    ("Edge Energy", "active", "NJ", "TR", 3, "Energy-Aware Scheduling for Edge Devices",
     ["Imran Hossain", "Tahmid Chowdhury", "Riya Das", "Shafin Alam"]),
    ("Land Chain", "active", "AH", "FA", 1, "Blockchain Land Registry Prototype",
     ["Mitu Chowdhury", "Sakib Khan", "Nusaiba Islam"]),
    ("Crop Vision", "p2", "DF", None, 1, "Crop Disease Detection with Lightweight CNNs",
     ["Arif Mahmud", "Farhan Kabir", "Jannat Ara"]),
    ("Dhaka Traffic", "frozen", "TR", None, 1, "Traffic Congestion Prediction in Dhaka",
     ["Lamia Sultana", "Omar Faruk", "Priya Saha"]),
    ("Health Bot", None, None, None, 0, None, ["Kamrul Hasan", "Sabrina Yasmin", "Rifat Ahmed"]),  # ready, no thesis
    ("Smart Grid", None, None, None, 0, None, ["Nafis Iqbal", "Tania Sultana"]),  # too small; invites Demo Student
]

# Loose students for the teammate finder: (name, interests, skills).
LOOSE = [
    ("Demo Student", "machine learning,nlp", "python,pytorch"),
    ("Ayesha Siddiqua", "computer vision,healthcare", "python,opencv"),
    ("Mehedi Hasan", "networks,iot", "c,arduino"),
    ("Ishrat Jahan", "web,hci", "react,figma"),
    ("Tanjim Rahman", "security,blockchain", "go,solidity"),
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
    pw_hash = hash_password(settings.seed_password)  # hashed once: every account shares it
    now = datetime.now(timezone.utc)
    ids = iter(range(10000001, 10000100))
    written: list = []  # PDFs to remove if the commit fails

    with SessionLocal() as db:
        if auth_service.get_by_id_number(db, FACULTY[0][1]):
            raise SystemExit("Seed data already present")

        def user(name, role=Role.student, email=None, id_number=None, **kw):
            email = email or f"{name.lower().replace(' ', '.')}@g.bracu.ac.bd"
            u = User(email=email, id_number=id_number or str(next(ids)), full_name=name, password_hash=pw_hash,
                     role=role, **kw)
            db.add(u)
            return u

        if progress_service.current_semester_id(db) is None:
            db.add(Semester(started_at=now - timedelta(days=2)))  # P1 registration still open
        for phase, days in ((Phase.P1, 14), (Phase.P2, 45), (Phase.P3, 90)):
            if db.get(MilestoneTemplate, phase) is None:
                db.add(MilestoneTemplate(phase=phase, due_at=now + timedelta(days=days), grace_days=3, penalty_per_day=5))

        fac = {ini: user(name, Role.faculty, email, idn, initials=ini) for email, idn, name, ini in FACULTY}

        loose = {}
        for name, interests, skills in LOOSE:
            email = "student@g.bracu.ac.bd" if name == "Demo Student" else None
            loose[name] = user(name, email=email)
            db.flush()
            db.add(StudentProfile(user_id=loose[name].id, interests=interests, skills=skills,
                                  bio=f"Hi, I'm {name.split()[0]}. Looking for a thesis group."))
        loose["Tanjim Rahman"].deletion_requested_at = now - timedelta(hours=3)
        loose["Tanjim Rahman"].deletion_reason = "I am transferring to another university next semester."
        loose["Tanjim Rahman"].deletion_requested_by_id = loose["Tanjim Rahman"].id
        user("Zahid Hasan", approved=False)  # waits in registration requests

        for gname, state, sup, co, n_versions, title, names in GROUPS:
            members = [user(n) for n in names]
            group = Group(name=gname, leader=members[0], members=[GroupMember(user=m) for m in members])
            db.add(group)
            db.flush()
            if gname == "Smart Grid":
                db.add(Invitation(group=group, invitee=loose["Demo Student"], invited_by=members[0]))
            if state is None:
                continue

            thesis = Thesis(
                group=group, student=members[0], supervisor=fac[sup],
                status={"pending": ThesisStatus.pending, "formed": ThesisStatus.formed}.get(state, ThesisStatus.active),
                code=None if state in ("pending", "formed") else progress_service.new_code(db),
                p1_registered=state not in ("pending", "formed", "p2"),
                phase=Phase.P2 if state == "p2" else Phase.P1,
                # Backdated so seeded uploads (an hour ago and later) count toward this phase.
                phase_started_at=now - timedelta(days=2),
                frozen_at=now - timedelta(days=1) if state == "frozen" else None,
                title=title, abstract=title and f"Problem, method and expected results for {title.lower()}.",
            )
            if co:
                thesis.co_supervisor_id = fac[co].id
                thesis.co_supervisor_accepted = thesis.co_supervisor_approved = True
            db.add(thesis)
            for m in members:
                m.thesis = thesis
            db.flush()
            if state == "frozen":
                members[1].restart_requested_at = now - timedelta(hours=5)

            if n_versions:
                proposal = Proposal(thesis_id=thesis.id)
                db.add(proposal)
                db.flush()
                for v in range(1, n_versions + 1):
                    data = _pdf(f"{title} - draft {v}")
                    path = _upload_dir() / f"{uuid.uuid4().hex}.pdf"
                    path.write_bytes(data)
                    written.append(path)
                    db.add(ProposalVersion(
                        proposal_id=proposal.id, version_no=v, phase=thesis.phase, title=title, abstract=thesis.abstract,
                        original_filename=f"proposal_v{v}.pdf", stored_filename=path.name, size_bytes=len(data),
                        sha256=hashlib.sha256(data).hexdigest(), uploaded_by_id=members[(v - 1) % len(members)].id,
                        created_at=now - timedelta(hours=n_versions - v + 1),
                    ))
                gm = progress_service.group_milestone(db, members[0], create=True)
                progress_service.sync_deliverable(db, gm, members[0])

            if state in ("active", "p2"):
                minute = now.replace(second=0, microsecond=0)
                for days_ago, notes, tasks in (
                    (9, "Kick-off: agreed scope, datasets and weekly schedule.",
                     [("Collect related papers", True), ("Set up the shared repository", True)]),
                    (2, "Reviewed the first draft; method section needs more detail.",
                     [("Rewrite the method section", False), ("Add a baseline experiment", False)]),
                ):
                    db.add(Meeting(
                        thesis_id=thesis.id, held_at=minute - timedelta(days=days_ago), notes=notes,
                        co_supervisor_attended=bool(co), recorded_by_id=fac[sup].id,
                        tasks=[MeetingTask(description=d, done=done, due_at=None if done else now + timedelta(days=5))
                               for d, done in tasks],
                    ))
            if gname == "Fake News":
                db.add(TitleChange(thesis_id=thesis.id, title="Detecting Fake News in Bangla and English Social Media",
                                   abstract="Extends the study to English posts and cross-lingual transfer."))

        try:
            db.commit()
        except Exception:
            for p in written:
                p.unlink(missing_ok=True)
            raise
    print(f"Seeded {len(FACULTY)} faculty, {len(GROUPS)} groups, {len(LOOSE) + 1} loose students. "
          f"Log in with ID 10000001 (student) or 20000001 (faculty) and SEED_PASSWORD.")


if __name__ == "__main__":
    main()
