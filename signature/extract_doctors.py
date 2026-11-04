"""Extract doctor names and stamp/signature crops from report page 3 or 4."""

from __future__ import annotations

import argparse
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import cv2
import easyocr
import numpy as np


PAGE_FILES = ("page_0002.png", "page_0003.png")
DOCTOR_LINE_PATTERN = re.compile(r"\bdr\b|doctor", re.IGNORECASE)
NON_NAME_WORDS = {
    "ADMO",
    "BRC",
    "DRH",
    "EXAMINER",
    "IRHS",
    "MEDICAL",
    "UROLOGIST",
}


@dataclass
class DoctorMark:
    full_name: str
    confidence: float
    page_number: int
    image_png: bytes


def _canonicalize_name(text: str) -> str | None:
    text = re.sub(r"(?i)\bdoctor\b|\bdr\.?\b", " ", text)
    words = re.findall(r"[A-Za-z]+(?:\.[A-Za-z]+)*\.?", text)
    name_parts: list[str] = []
    for word in words:
        letters = re.sub(r"[^A-Za-z]", "", word)
        if not letters or letters.upper() in NON_NAME_WORDS:
            continue
        if len(letters) <= 2:
            name_parts.append(".".join(letters.upper()) + ".")
        else:
            name_parts.append(letters.title())

    if len(name_parts) < 2:
        return None
    return "Dr. " + " ".join(name_parts)


def _encode_png(image: np.ndarray) -> bytes:
    success, encoded = cv2.imencode(".png", image)
    if not success:
        raise RuntimeError("Could not encode the doctor stamp/signature crop as PNG")
    return encoded.tobytes()


def _read_doctor_mark(
    reader: easyocr.Reader,
    image_path: Path,
    page_number: int,
) -> DoctorMark | None:
    image = cv2.imread(str(image_path))
    if image is None:
        raise RuntimeError(f"Could not read report page: {image_path}")

    height, width = image.shape[:2]
    x_offset = int(width * 0.30)
    y_offset = int(height * 0.72)
    crop = image[y_offset : int(height * 0.96), x_offset : int(width * 0.98)]
    detections = reader.readtext(crop, detail=1, paragraph=False)

    boxes: list[tuple[np.ndarray, str, float]] = []
    for box, text, confidence in detections:
        coordinates = np.asarray(box, dtype=np.float32)
        coordinates[:, 0] += x_offset
        coordinates[:, 1] += y_offset
        boxes.append((coordinates, text, float(confidence)))

    marks: list[DoctorMark] = []
    for doctor_box, doctor_text, doctor_confidence in boxes:
        if not DOCTOR_LINE_PATTERN.search(doctor_text):
            continue

        doctor_left = float(doctor_box[:, 0].min())
        doctor_right = float(doctor_box[:, 0].max())
        doctor_top = float(doctor_box[:, 1].min())
        doctor_bottom = float(doctor_box[:, 1].max())
        doctor_center_y = (doctor_top + doctor_bottom) / 2
        line_tolerance = max(22.0, (doctor_bottom - doctor_top) * 0.55)

        line_items = [(doctor_box, doctor_text, doctor_confidence)]
        for box, text, confidence in boxes:
            if box is doctor_box:
                continue
            left = float(box[:, 0].min())
            right = float(box[:, 0].max())
            top = float(box[:, 1].min())
            bottom = float(box[:, 1].max())
            center_y = (top + bottom) / 2
            if (
                left >= doctor_left - 8
                and left <= doctor_right + width * 0.5
                and abs(center_y - doctor_center_y) <= line_tolerance
            ):
                line_items.append((box, text, confidence))

        line_items.sort(key=lambda item: float(item[0][:, 0].min()))
        name = _canonicalize_name(" ".join(item[1] for item in line_items))
        if name is None:
            continue

        left = max(0, int(min(item[0][:, 0].min() for item in line_items)) - 45)
        right = min(width, int(max(item[0][:, 0].max() for item in line_items)) + 80)
        top = max(0, int(min(item[0][:, 1].min() for item in line_items)) - 125)
        bottom = min(height, int(max(item[0][:, 1].max() for item in line_items)) + 125)
        mark_crop = image[top:bottom, left:right]
        confidence = sum(item[2] for item in line_items) / len(line_items)
        marks.append(
            DoctorMark(
                full_name=name,
                confidence=confidence,
                page_number=page_number,
                image_png=_encode_png(mark_crop),
            )
        )

    if not marks:
        return None
    return max(marks, key=lambda mark: (mark.confidence, len(mark.full_name)))


def _select_doctor_mark(
    marks: Sequence[DoctorMark],
) -> tuple[DoctorMark | None, str]:
    if not marks:
        return None, "review_required"

    names = {re.sub(r"[^a-z]", "", mark.full_name.lower()) for mark in marks}
    if len(names) == 1:
        return max(marks, key=lambda mark: mark.confidence), "ocr"

    ordered = sorted(marks, key=lambda mark: mark.confidence, reverse=True)
    best, second = ordered[:2]
    best_name = re.sub(r"[^a-z]", "", best.full_name.lower())
    second_name = re.sub(r"[^a-z]", "", second.full_name.lower())
    if best_name in second_name or second_name in best_name:
        return max(marks, key=lambda mark: len(mark.full_name)), "ocr"
    if best.confidence - second.confidence >= 0.15:
        return best, "ocr"
    return None, "conflicting_pages"


def _initialize_database(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        PRAGMA foreign_keys = ON;
        CREATE TABLE IF NOT EXISTS doctors (
            doctor_id INTEGER PRIMARY KEY,
            full_name TEXT NOT NULL UNIQUE,
            stamp_signature_png BLOB NOT NULL,
            representative_candidate_id TEXT NOT NULL,
            representative_page INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS candidate_doctors (
            candidate_id TEXT PRIMARY KEY,
            doctor_id INTEGER REFERENCES doctors(doctor_id),
            source_page INTEGER,
            confidence REAL,
            status TEXT NOT NULL
        );
        """
    )


def extract_doctors(data_root: Path, database_path: Path) -> dict[str, int]:
    clean_root = data_root / "high_res_clean"
    image_root = clean_root if clean_root.is_dir() else data_root / "high_res"
    if not image_root.is_dir():
        raise FileNotFoundError(
            f"Expected report pages under {data_root / 'high_res_clean'} "
            f"or {data_root / 'high_res'}"
        )

    candidates = sorted(path for path in image_root.iterdir() if path.is_dir())
    reader = easyocr.Reader(["en"], gpu=False, verbose=False)
    database_path.parent.mkdir(parents=True, exist_ok=True)

    counts = {
        "candidates": len(candidates),
        "recognized": 0,
        "needs_review": 0,
        "missing_pages": 0,
        "unique_doctors": 0,
    }
    with sqlite3.connect(database_path) as connection:
        _initialize_database(connection)
        connection.execute("DELETE FROM candidate_doctors")
        connection.execute("DELETE FROM doctors")

        for candidate in candidates:
            pages = [
                (page_number, candidate / filename)
                for page_number, filename in enumerate(PAGE_FILES, start=3)
                if (candidate / filename).is_file()
            ]
            if not pages:
                connection.execute(
                    """
                    INSERT INTO candidate_doctors
                        (candidate_id, doctor_id, source_page, confidence, status)
                    VALUES (?, NULL, NULL, NULL, 'missing_pages')
                    """,
                    (candidate.name,),
                )
                counts["missing_pages"] += 1
                continue

            marks = [
                mark
                for page_number, image_path in pages
                if (
                    mark := _read_doctor_mark(reader, image_path, page_number)
                )
                is not None
            ]
            mark, status = _select_doctor_mark(marks)
            if mark is None:
                connection.execute(
                    """
                    INSERT INTO candidate_doctors
                        (candidate_id, doctor_id, source_page, confidence, status)
                    VALUES (?, NULL, NULL, NULL, ?)
                    """,
                    (candidate.name, status),
                )
                counts["needs_review"] += 1
                continue

            connection.execute(
                """
                INSERT OR IGNORE INTO doctors
                    (full_name, stamp_signature_png,
                     representative_candidate_id, representative_page)
                VALUES (?, ?, ?, ?)
                """,
                (
                    mark.full_name,
                    mark.image_png,
                    candidate.name,
                    mark.page_number,
                ),
            )
            doctor_id = connection.execute(
                "SELECT doctor_id FROM doctors WHERE full_name = ?",
                (mark.full_name,),
            ).fetchone()[0]
            connection.execute(
                """
                INSERT INTO candidate_doctors
                    (candidate_id, doctor_id, source_page, confidence, status)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    candidate.name,
                    doctor_id,
                    mark.page_number,
                    mark.confidence,
                    status,
                ),
            )
            counts["recognized"] += 1

        counts["unique_doctors"] = connection.execute(
            "SELECT COUNT(*) FROM doctors"
        ).fetchone()[0]
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Read doctor names and store unique stamp/signature images in SQLite."
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path(__file__).parent / "interim",
        help="Directory containing high_res_clean/ or high_res/ candidate folders",
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=Path(__file__).parent / "doctor_registry.sqlite3",
        help="Path to the SQLite database to create or refresh",
    )
    args = parser.parse_args()
    counts = extract_doctors(args.data_root, args.database)
    print(f"Database: {args.database.resolve()}")
    for key, value in counts.items():
        print(f"{key.replace('_', ' ').title()}: {value}")


if __name__ == "__main__":
    main()
