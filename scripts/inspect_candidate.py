from __future__ import annotations

import sys

from src.database.database import get_session
from src.database.repository import get_examination_by_roll_number


def print_value(label: str, value):
    print(f"{label:<30}: {value if value is not None else '-'}")


def inspect_candidate(roll_number: str):
    session = get_session()

    try:
        examination = get_examination_by_roll_number(
            session,
            roll_number,
        )

        if examination is None:
            print(
                f"No examination found for roll number: "
                f"{roll_number}"
            )
            return 1

        candidate = examination.candidate

        # -----------------------------------------------------
        # Candidate
        # -----------------------------------------------------
        print("=" * 70)
        print("CANDIDATE")
        print("=" * 70)

        print_value(
            "Roll Number",
            candidate.roll_number,
        )
        print_value(
            "Candidate Name",
            candidate.candidate_name,
        )
        print_value(
            "Father Name",
            candidate.father_name,
        )
        print_value(
            "Date of Birth",
            candidate.date_of_birth,
        )
        print_value(
            "Mobile Number",
            candidate.mobile_number,
        )
        print_value(
            "Email",
            candidate.email,
        )
        print_value(
            "Recruitment CEN",
            candidate.recruitment_cen,
        )

        # -----------------------------------------------------
        # Medical Examination
        # -----------------------------------------------------
        print()
        print("=" * 70)
        print("MEDICAL EXAMINATION")
        print("=" * 70)

        print_value(
            "DV Date",
            examination.dv_date,
        )
        print_value(
            "Medical Examination Date",
            examination.medical_examination_date,
        )
        print_value(
            "Candidate Declaration Date",
            examination.candidate_declaration_date,
        )
        print_value(
            "Medical Class",
            examination.medical_class,
        )
        print_value(
            "Identification Marks",
            examination.identification_marks,
        )

        # -----------------------------------------------------
        # Doctor
        # -----------------------------------------------------
        print()
        print("=" * 70)
        print("DOCTOR")
        print("=" * 70)

        doctor = examination.examining_doctor

        if doctor:
            print_value(
                "Doctor Name",
                doctor.doctor_name,
            )
            print_value(
                "Doctor Role",
                doctor.doctor_role,
            )
        else:
            print("No doctor recorded.")

        # -----------------------------------------------------
        # Page 2 - PME Case
        # -----------------------------------------------------
        print()
        print("=" * 70)
        print("PAGE 2 - PME CASE")
        print("=" * 70)

        pme_case = examination.pme_case

        if pme_case:
            print_value(
                "Urine",
                pme_case.urine,
            )
            print_value(
                "Sugar",
                pme_case.sugar,
            )
            print_value(
                "ALB",
                pme_case.alb,
            )
            print_value(
                "Chest X-Ray",
                pme_case.chest_xray_result,
            )
            print_value(
                "Advice",
                pme_case.advice,
            )
            print_value(
                "Handwritten Remarks",
                pme_case.handwritten_remarks,
            )

            print()
            print("Page 2 Measurements:")

            if pme_case.measurements:
                for measurement in pme_case.measurements:
                    print(
                        f"  {measurement.row_label or '-'} | "
                        f"{measurement.column_1 or '-'} | "
                        f"{measurement.column_2 or '-'} | "
                        f"{measurement.raw_text or '-'}"
                    )
            else:
                print("  No generic measurements recorded.")

        else:
            print("No PME case recorded.")

        # -----------------------------------------------------
        # Page 3 - Vision
        # -----------------------------------------------------
        print()
        print("=" * 70)
        print("PAGE 3 - VISION")
        print("=" * 70)

        vision = examination.vision

        if vision:
            print_value(
                "Right Distance Uncorrected",
                vision.right_distance_uncorrected,
            )
            print_value(
                "Right Distance Corrected",
                vision.right_distance_corrected,
            )
            print_value(
                "Right Near Uncorrected",
                vision.right_near_uncorrected,
            )
            print_value(
                "Right Near Corrected",
                vision.right_near_corrected,
            )

            print_value(
                "Right Glasses S",
                vision.right_glasses_s,
            )
            print_value(
                "Right Glasses C",
                vision.right_glasses_c,
            )
            print_value(
                "Right Glasses A",
                vision.right_glasses_a,
            )

            print_value(
                "Left Distance Uncorrected",
                vision.left_distance_uncorrected,
            )
            print_value(
                "Left Distance Corrected",
                vision.left_distance_corrected,
            )
            print_value(
                "Left Near Uncorrected",
                vision.left_near_uncorrected,
            )
            print_value(
                "Left Near Corrected",
                vision.left_near_corrected,
            )

            print_value(
                "Left Glasses S",
                vision.left_glasses_s,
            )
            print_value(
                "Left Glasses C",
                vision.left_glasses_c,
            )
            print_value(
                "Left Glasses A",
                vision.left_glasses_a,
            )

            print_value(
                "Color Perception",
                vision.color_perception,
            )
            print_value(
                "Binocular Vision",
                vision.binocular_vision,
            )
            print_value(
                "Night Vision",
                vision.night_vision,
            )
            print_value(
                "Field of Vision",
                vision.field_of_vision,
            )

        else:
            print("No vision examination recorded.")

        # -----------------------------------------------------
        # Page 3 - Physical Examination
        # -----------------------------------------------------
        print()
        print("=" * 70)
        print("PAGE 3 - PHYSICAL EXAMINATION")
        print("=" * 70)

        physical = examination.physical

        if physical:
            print_value(
                "Urine",
                physical.urine,
            )
            print_value(
                "Hearing",
                physical.hearing,
            )
            print_value(
                "PR",
                physical.pr,
            )
            print_value(
                "BP",
                physical.bp,
            )
            print_value(
                "CVS",
                physical.cvs,
            )
            print_value(
                "RS",
                physical.rs,
            )
            print_value(
                "PIA",
                physical.pia,
            )
            print_value(
                "Spine",
                physical.spine,
            )
            print_value(
                "Heart",
                physical.heart,
            )
            print_value(
                "Lungs",
                physical.lungs,
            )
            print_value(
                "General Physical Examination",
                physical.general_physical_examination,
            )

        else:
            print(
                "No physical examination recorded."
            )

        # -----------------------------------------------------
        # Fitness
        # -----------------------------------------------------
        print()
        print("=" * 70)
        print("FITNESS CLASSIFICATION")
        print("=" * 70)

        fitness = examination.fitness

        if fitness:
            print_value(
                "Fit In Class",
                fitness.fit_in_class,
            )
            print_value(
                "Unfit In Class",
                fitness.unfit_in_class,
            )
        else:
            print(
                "No fitness classification recorded."
            )

        # -----------------------------------------------------
        # Declarations
        # -----------------------------------------------------
        print()
        print("=" * 70)
        print("DECLARATIONS")
        print("=" * 70)

        if examination.declarations:
            for declaration in examination.declarations:
                print(
                    f"{declaration.part:<10} "
                    f"{declaration.question_no:<10} "
                    f"{declaration.answer or '-'}"
                )
        else:
            print("No declarations recorded.")

        # -----------------------------------------------------
        # Extraction
        # -----------------------------------------------------
        print()
        print("=" * 70)
        print("EXTRACTION")
        print("=" * 70)

        if examination.extraction_runs:
            for extraction in examination.extraction_runs:
                print_value(
                    "Document ID",
                    extraction.document_id,
                )
                print_value(
                    "Model",
                    extraction.model_name,
                )
                print_value(
                    "Extracted At",
                    extraction.extracted_at,
                )
        else:
            print("No extraction run recorded.")

        print()
        print("=" * 70)
        print("INSPECTION COMPLETE")
        print("=" * 70)

        return 0

    finally:
        session.close()


def main():
    if len(sys.argv) != 2:
        print(
            "Usage: python scripts/inspect_candidate.py "
            "<roll_number>"
        )
        return 1

    roll_number = sys.argv[1]

    return inspect_candidate(roll_number)


if __name__ == "__main__":
    raise SystemExit(main())