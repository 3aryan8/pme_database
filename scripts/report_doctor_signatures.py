"""Print doctor identification and saved signature/stamp assets for all candidates."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlalchemy import select

from signature.doctor_pipeline import SIGNATURE_ROOT
from src.database.database import get_session, init_db
from src.database.models import Candidate, Doctor, DoctorIdentification


def collect_report() -> list[dict[str, object]]:
    with get_session() as session:
        rows = session.execute(
            select(Candidate, Doctor, DoctorIdentification)
            .outerjoin(Doctor, Candidate.doctor_id == Doctor.id)
            .outerjoin(
                DoctorIdentification,
                (DoctorIdentification.candidate_id == Candidate.id)
                & (DoctorIdentification.doctor_id == Doctor.id),
            )
            .order_by(Candidate.roll_number, DoctorIdentification.id.desc())
        ).all()

    report: dict[int, dict[str, object]] = {}
    for candidate, doctor, identification in rows:
        item = report.setdefault(
            candidate.id,
            {
                "candidate_id": candidate.id,
                "roll_number": candidate.roll_number,
                "candidate_name": candidate.candidate_name,
                "doctor": None,
                "identification": None,
            },
        )
        if doctor is None:
            continue

        doctor_dir = SIGNATURE_ROOT / f"doctor_{doctor.id:04d}"
        item["doctor"] = {
            "id": doctor.id,
            "name": doctor.full_name_english or doctor.doctor_name,
            "english_name": doctor.full_name_english,
            "hindi_name": doctor.full_name_hindi,
            "designation": doctor.designation,
            "canonical_signature": doctor.signature_image_path,
            "canonical_stamp": doctor.stamp_image_path,
            "signature_embedding": str(doctor_dir / "signature_embedding.json"),
            "canonical_signature_exists": bool(
                doctor.signature_image_path
                and Path(doctor.signature_image_path).is_file()
            ),
            "canonical_stamp_exists": bool(
                doctor.stamp_image_path and Path(doctor.stamp_image_path).is_file()
            ),
        }
        if identification is not None and item["identification"] is None:
            item["identification"] = {
                "method": identification.identification_method,
                "confidence": identification.confidence,
                "source_page": identification.source_page,
                "signature": identification.signature_image_path,
                "stamp": identification.stamp_image_path,
                "review_status": identification.review_status,
            }
    return list(report.values())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    parser.add_argument("--output", type=Path, help="Write JSON report to this file")
    args = parser.parse_args()

    init_db()
    report = collect_report()
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(payload + "\n", encoding="utf-8")
        print(f"Wrote {len(report)} candidate records to {args.output}")
    elif args.json:
        print(payload)
    else:
        for item in report:
            doctor = item["doctor"] or {}
            identification = item["identification"] or {}
            print(
                f"{item['roll_number']} | {item['candidate_name'] or '-'} | "
                f"{doctor.get('name', 'UNMAPPED')} | "
                f"{identification.get('method', 'not processed')} | "
                f"score={identification.get('confidence', '-') } | "
                f"signature={doctor.get('canonical_signature_exists', False)} | "
                f"stamp={doctor.get('canonical_stamp_exists', False)}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())