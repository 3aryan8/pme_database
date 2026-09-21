from __future__ import annotations

import html
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .models import MedicalExamination
from .report_data import PMEReportData, build_report_data, report_data_to_dict


# ============================================================================
# BASIC HELPERS
# ============================================================================

def esc(value: Any) -> str:
    """
    Safely convert a value to HTML.

    Empty / None values are displayed as an em dash.
    """
    if value is None or value == "":
        return "—"

    return html.escape(str(value))


def format_date(value: date | datetime | None) -> str:
    """Format dates consistently for the report."""

    if value is None:
        return "—"

    if isinstance(value, datetime):
        value = value.date()

    return value.strftime("%d-%m-%Y")


def calculate_age(
    dob: date | None,
    reference_date: date | None,
) -> str:
    """
    Calculate age at the time of medical examination.
    """

    if dob is None or reference_date is None:
        return "—"

    age = reference_date.year - dob.year

    if (reference_date.month, reference_date.day) < (
        dob.month,
        dob.day,
    ):
        age -= 1

    return str(age)


def table_row(label: str, value: Any) -> str:
    """Generate a standard two-column table row."""

    return f"""
        <tr>
            <th>{esc(label)}</th>
            <td>{esc(value)}</td>
        </tr>
    """


def section_title(
    title: str,
    page: int | None = None,
) -> str:
    """Generate a report section heading."""

    if page is not None:
        title = f"Page {page} — {title}"

    return f"""
        <div class="section-title">
            {esc(title)}
        </div>
    """


def safe_filename(value: Any) -> str:
    """Create a filesystem-safe filename."""

    value = str(value)

    return "".join(
        char if char.isalnum() or char in "-_"
        else "_"
        for char in value
    )


# ============================================================================
# PAGE 1
# ============================================================================

def render_page_1(report: PMEReportData) -> str:
    """
    Render all Page 1 information.
    """

    candidate = report.candidate
    examination = report.examination

    age = calculate_age(
        candidate.date_of_birth,
        examination.medical_examination_date,
    )

    return f"""
    <section class="page-section">

        {section_title("Candidate / General Details", 1)}

        <table class="data-table">
            <tbody>

                {table_row(
                    "Candidate Name",
                    candidate.candidate_name
                )}

                {table_row(
                    "Father Name",
                    candidate.father_name
                )}

                {table_row(
                    "Date of Birth",
                    format_date(candidate.date_of_birth)
                )}

                {table_row(
                    "Age at Medical Examination",
                    age
                )}

                {table_row(
                    "Mobile Number",
                    candidate.mobile_number
                )}

                {table_row(
                    "Email ID",
                    candidate.email
                )}

                {table_row(
                    "Roll Number",
                    candidate.roll_number
                )}

                {table_row(
                    "Recruitment CEN",
                    candidate.recruitment_cen
                )}

                {table_row(
                    "Class",
                    examination.medical_class
                )}

                {table_row(
                    "Document Verification Date",
                    format_date(examination.dv_date)
                )}

                {table_row(
                    "Medical Examination Date",
                    format_date(
                        examination.medical_examination_date
                    )
                )}

            </tbody>
        </table>


        {section_title("Physical Identification", 1)}

        <table class="data-table">
            <tbody>

                {table_row(
                    "Permanent Physical Identification Marks",
                    examination.identification_marks
                )}

            </tbody>
        </table>

    </section>
    """


# ============================================================================
# PAGE 2
# ============================================================================

def render_page_2(report: PMEReportData) -> str:
    """
    Render all Page 2 PME case information.
    """

    pme = report.pme_case

    # ------------------------------------------------------------------------
    # Generic measurements
    # ------------------------------------------------------------------------

    measurements = getattr(pme, "measurements", None)

    if measurements:

        measurement_rows = ""

        for measurement in measurements:

            measurement_rows += f"""
                <tr>

                    <td>
                        {esc(
                            getattr(
                                measurement,
                                "row_label",
                                None
                            )
                        )}
                    </td>

                    <td>
                        {esc(
                            getattr(
                                measurement,
                                "column_1",
                                None
                            )
                        )}
                    </td>

                    <td>
                        {esc(
                            getattr(
                                measurement,
                                "column_2",
                                None
                            )
                        )}
                    </td>

                    <td>
                        {esc(
                            getattr(
                                measurement,
                                "raw_text",
                                None
                            )
                        )}
                    </td>

                </tr>
            """

    else:

        measurement_rows = """
            <tr>
                <td colspan="4" class="empty-row">
                    No additional measurements recorded
                </td>
            </tr>
        """

    # ------------------------------------------------------------------------
    # Optional Page 2 fields
    #
    # getattr() is intentionally used here because older database/report-data
    # versions may not yet contain these fields.
    # ------------------------------------------------------------------------

    chest_xray_result = getattr(
        pme,
        "chest_xray_result",
        None,
    )

    advice = getattr(
        pme,
        "advice",
        None,
    )

    handwritten_remarks = getattr(
        pme,
        "handwritten_remarks",
        None,
    )

    return f"""
    <section class="page-section">

        {section_title("PME CASE", 2)}

        <table class="data-table">
            <tbody>

                {table_row(
                    "Urine",
                    pme.urine
                )}

                {table_row(
                    "Sugar",
                    pme.sugar
                )}

                {table_row(
                    "ALB",
                    pme.alb
                )}

            </tbody>
        </table>


        {section_title(
            "Additional Measurements / Table Data",
            2
        )}

        <table class="data-table measurement-table">

            <thead>
                <tr>
                    <th>Row / Label</th>
                    <th>Column 1</th>
                    <th>Column 2</th>
                    <th>Raw Text</th>
                </tr>
            </thead>

            <tbody>
                {measurement_rows}
            </tbody>

        </table>


        {section_title(
            "MMR / F.S. Chest X-Ray",
            2
        )}

        <table class="data-table">
            <tbody>

                {table_row(
                    "Chest X-Ray Result",
                    chest_xray_result
                )}

            </tbody>
        </table>


        {section_title("Advice", 2)}

        <div class="text-box">
            {esc(advice)}
        </div>


        {section_title(
            "Handwritten Remarks",
            2
        )}

        <div class="text-box">
            {esc(handwritten_remarks)}
        </div>

    </section>
    """


# ============================================================================
# PAGE 3 — VISION
# ============================================================================

def render_eye_table(report: PMEReportData) -> str:
    """
    Render the complete right/left eye table.
    """

    vision = report.vision

    right = vision.right_eye
    left = vision.left_eye

    return f"""
    <table class="data-table vision-table">

        <thead>
            <tr>
                <th>Vision Parameter</th>
                <th>Right Eye</th>
                <th>Left Eye</th>
            </tr>
        </thead>

        <tbody>

            <tr>
                <th>Distance - Uncorrected</th>
                <td>{esc(right.distance_uncorrected)}</td>
                <td>{esc(left.distance_uncorrected)}</td>
            </tr>

            <tr>
                <th>Distance - Corrected</th>
                <td>{esc(right.distance_corrected)}</td>
                <td>{esc(left.distance_corrected)}</td>
            </tr>

            <tr>
                <th>Near - Uncorrected</th>
                <td>{esc(right.near_uncorrected)}</td>
                <td>{esc(left.near_uncorrected)}</td>
            </tr>

            <tr>
                <th>Near - Corrected</th>
                <td>{esc(right.near_corrected)}</td>
                <td>{esc(left.near_corrected)}</td>
            </tr>

            <tr>
                <th>Glasses Power - S</th>
                <td>{esc(right.glasses_s)}</td>
                <td>{esc(left.glasses_s)}</td>
            </tr>

            <tr>
                <th>Glasses Power - C</th>
                <td>{esc(right.glasses_c)}</td>
                <td>{esc(left.glasses_c)}</td>
            </tr>

            <tr>
                <th>Glasses Power - A</th>
                <td>{esc(right.glasses_a)}</td>
                <td>{esc(left.glasses_a)}</td>
            </tr>

        </tbody>
    </table>
    """


def render_page_3(report: PMEReportData) -> str:
    """
    Render Page 3 vision, physical examination and fitness data.
    """

    vision = report.vision
    physical = report.physical
    fitness = report.fitness
    doctor = report.doctor

    return f"""
    <section class="page-section">


        {section_title(
            "Fitness Classification",
            3
        )}

        <table class="data-table">
            <tbody>

                {table_row(
                    "Fit in Class",
                    fitness.fit_in_class
                )}

                {table_row(
                    "Unfit in Class",
                    fitness.unfit_in_class
                )}

            </tbody>
        </table>


        {section_title(
            "Acuity of Vision",
            3
        )}

        {render_eye_table(report)}


        {section_title(
            "Vision Parameters",
            3
        )}

        <table class="data-table">

            <tbody>

                {table_row(
                    "Color Perception",
                    vision.color_perception
                )}

                {table_row(
                    "Binocular Vision",
                    vision.binocular_vision
                )}

                {table_row(
                    "Night Vision",
                    vision.night_vision
                )}

                {table_row(
                    "Field of Vision",
                    vision.field_of_vision
                )}

            </tbody>

        </table>


        {section_title(
            "Physical Examination",
            3
        )}

        <table class="data-table">

            <tbody>

                {table_row(
                    "Urine",
                    physical.urine
                )}

                {table_row(
                    "Hearing",
                    physical.hearing
                )}

                {table_row(
                    "General Physical Examination",
                    physical.general_physical_examination
                )}

                {table_row(
                    "PR",
                    physical.pr
                )}

                {table_row(
                    "BP",
                    physical.bp
                )}

                {table_row(
                    "CVS",
                    physical.cvs
                )}

                {table_row(
                    "RS",
                    physical.rs
                )}

                {table_row(
                    "PIA",
                    physical.pia
                )}

                {table_row(
                    "Spine",
                    physical.spine
                )}

                {table_row(
                    "Heart",
                    physical.heart
                )}

                {table_row(
                    "Lungs",
                    physical.lungs
                )}

            </tbody>

        </table>


        {section_title(
            "Medical Examiner",
            3
        )}

        <table class="data-table">

            <tbody>

                {table_row(
                    "Doctor Name",
                    doctor.doctor_name
                )}

                {table_row(
                    "Doctor Role / Designation",
                    doctor.doctor_role
                )}

            </tbody>

        </table>

    </section>
    """


# ============================================================================
# PAGE 4 — DECLARATIONS
# ============================================================================

def render_declaration_table(
    declarations: list[Any],
) -> str:
    """
    Render declaration records.

    Your DeclarationReportData contains:
        part
        question_no
        answer

    It does NOT contain question_text, so we do not attempt to display it.
    """

    if not declarations:

        return """
            <tr>
                <td colspan="2" class="empty-row">
                    No declarations recorded
                </td>
            </tr>
        """

    rows = ""

    for declaration in declarations:

        rows += f"""
            <tr>

                <td>
                    {esc(
                        getattr(
                            declaration,
                            "question_no",
                            None
                        )
                    )}
                </td>

                <td>
                    {esc(
                        getattr(
                            declaration,
                            "answer",
                            None
                        )
                    )}
                </td>

            </tr>
        """

    return rows


def render_page_4(report: PMEReportData) -> str:
    """
    Render Part I and Part II declarations.
    """

    declarations = report.declarations

    part_one = []
    part_two = []
    other_parts = {}

    for declaration in declarations:

        part = str(
            getattr(
                declaration,
                "part",
                ""
            )
        ).strip().lower()

        if part in {
            "part_i",
            "part 1",
            "part1",
            "i",
            "1",
        }:
            part_one.append(declaration)

        elif part in {
            "part_ii",
            "part 2",
            "part2",
            "ii",
            "2",
        }:
            part_two.append(declaration)

        else:
            other_parts.setdefault(
                part or "other",
                []
            ).append(declaration)

    # ------------------------------------------------------------------------
    # If the stored part names are different, we still show all declarations.
    # This prevents data from silently disappearing from the report.
    # ------------------------------------------------------------------------

    if not part_one and not part_two and declarations:

        midpoint = len(declarations) // 2

        part_one = declarations[:midpoint]
        part_two = declarations[midpoint:]

    declaration_date = getattr(
        report.examination,
        "candidate_declaration_date",
        None,
    )

    doctor = report.doctor

    html_parts = f"""
    <section class="page-section">

        {section_title(
            "Part I — Candidate Declaration",
            4
        )}

        <table class="data-table declaration-table">

            <thead>
                <tr>
                    <th>Question No.</th>
                    <th>Answer</th>
                </tr>
            </thead>

            <tbody>
                {render_declaration_table(part_one)}
            </tbody>

        </table>


        {section_title(
            "Part II — Candidate Declaration",
            4
        )}

        <table class="data-table declaration-table">

            <thead>
                <tr>
                    <th>Question No.</th>
                    <th>Answer</th>
                </tr>
            </thead>

            <tbody>
                {render_declaration_table(part_two)}
            </tbody>

        </table>
    """

    # ------------------------------------------------------------------------
    # Any unexpected declaration parts are retained.
    # ------------------------------------------------------------------------

    for part_name, part_declarations in other_parts.items():

        html_parts += f"""

        {section_title(
            f"Additional Declaration Part — {part_name}",
            4
        )}

        <table class="data-table declaration-table">

            <thead>
                <tr>
                    <th>Question No.</th>
                    <th>Answer</th>
                </tr>
            </thead>

            <tbody>
                {render_declaration_table(
                    part_declarations
                )}
            </tbody>

        </table>
        """

    html_parts += f"""

        {section_title(
            "Declaration / Medical Examiner Details",
            4
        )}

        <table class="data-table">

            <tbody>

                {table_row(
                    "Declaration Date",
                    format_date(declaration_date)
                )}

                {table_row(
                    "Doctor Name",
                    doctor.doctor_name
                )}

                {table_row(
                    "Doctor Role / Designation",
                    doctor.doctor_role
                )}

            </tbody>

        </table>

    </section>
    """

    return html_parts


# ============================================================================
# EXTRACTION METADATA
# ============================================================================

def render_extraction_metadata(
    report: PMEReportData,
) -> str:
    """
    Render extraction metadata.

    This is useful for traceability and future audit/review workflows.
    """

    extraction = report.extraction

    return f"""
    <section class="metadata">

        {section_title(
            "Extraction Metadata"
        )}

        <table class="data-table">

            <tbody>

                {table_row(
                    "Document ID",
                    extraction.document_id
                )}

                {table_row(
                    "Extraction Model",
                    extraction.model_name
                )}

                {table_row(
                    "Extracted At",
                    extraction.extracted_at
                )}

            </tbody>

        </table>

    </section>
    """


# ============================================================================
# COMPLETE HTML
# ============================================================================

def render_html(
    report: PMEReportData,
) -> str:
    """
    Convert PMEReportData into a complete standalone HTML document.
    """

    candidate_name = (
        report.candidate.candidate_name
        or "Unknown Candidate"
    )

    roll_number = (
        report.candidate.roll_number
        or "Unknown Roll Number"
    )

    medical_date = format_date(
        report.examination.medical_examination_date
    )

    return f"""<!DOCTYPE html>

<html lang="en">

<head>

    <meta charset="UTF-8">

    <meta
        name="viewport"
        content="width=device-width, initial-scale=1.0"
    >

    <title>
        PME Report — {esc(candidate_name)}
    </title>


    <style>

        * {{
            box-sizing: border-box;
        }}


        body {{
            margin: 0;
            padding: 0;

            background: #f2f4f7;

            color: #202124;

            font-family:
                Arial,
                Helvetica,
                sans-serif;

            font-size: 14px;

            line-height: 1.5;
        }}


        .container {{
            max-width: 1100px;

            margin: 30px auto;

            background: #ffffff;

            box-shadow:
                0 2px 12px
                rgba(0, 0, 0, 0.08);
        }}


        /* ================================================================
           HEADER
           ================================================================ */

        .header {{
            padding: 30px 35px;

            border-bottom:
                2px solid #222222;
        }}


        .header h1 {{
            margin:
                0 0 8px 0;

            font-size: 28px;
        }}


        .subtitle {{
            color: #555555;

            font-size: 15px;
        }}


        .candidate-summary {{
            margin-top: 20px;

            display: grid;

            grid-template-columns:
                repeat(3, 1fr);

            gap: 12px;
        }}


        .summary-box {{
            border:
                1px solid #dddddd;

            padding:
                12px 15px;

            background:
                #fafafa;
        }}


        .summary-label {{
            font-size: 11px;

            text-transform:
                uppercase;

            color: #666666;

            margin-bottom: 3px;
        }}


        .summary-value {{
            font-weight: 600;

            font-size: 15px;
        }}


        /* ================================================================
           CONTENT
           ================================================================ */

        .content {{
            padding:
                25px 35px 40px;
        }}


        .page-section {{
            margin-bottom: 45px;
        }}


        .section-title {{
            margin-top: 28px;

            margin-bottom: 12px;

            padding:
                9px 12px;

            background:
                #eeeeee;

            border-left:
                4px solid #333333;

            font-size: 16px;

            font-weight: 700;
        }}


        /* ================================================================
           TABLES
           ================================================================ */

        .data-table {{
            width: 100%;

            border-collapse:
                collapse;

            margin-bottom: 15px;
        }}


        .data-table th,
        .data-table td {{
            border:
                1px solid #d5d5d5;

            padding:
                9px 11px;

            text-align: left;

            vertical-align:
                top;
        }}


        .data-table th {{
            width: 32%;

            background:
                #f7f7f7;

            font-weight: 600;
        }}


        .data-table thead th {{
            background:
                #e9e9e9;

            font-weight: 700;

            width: auto;
        }}


        .measurement-table th,
        .measurement-table td {{
            width: auto;
        }}


        .vision-table th:first-child {{
            width: 35%;
        }}


        .declaration-table th,
        .declaration-table td {{
            width: auto;
        }}


        /* ================================================================
           TEXT BOX
           ================================================================ */

        .text-box {{
            min-height: 45px;

            border:
                1px solid #d5d5d5;

            padding: 12px;

            white-space:
                pre-wrap;

            word-break:
                break-word;

            background:
                #fafafa;
        }}


        .empty-row {{
            text-align:
                center !important;

            color:
                #777777;

            font-style:
                italic;
        }}


        /* ================================================================
           METADATA
           ================================================================ */

        .metadata {{
            margin-top: 40px;

            padding-top: 20px;

            border-top:
                2px solid #dddddd;
        }}


        /* ================================================================
           FOOTER
           ================================================================ */

        .footer {{
            padding:
                18px 35px;

            border-top:
                1px solid #dddddd;

            color:
                #666666;

            font-size:
                12px;

            text-align:
                center;
        }}


        /* ================================================================
           RESPONSIVE
           ================================================================ */

        @media (max-width: 700px) {{

            .container {{
                margin: 0;

                box-shadow: none;
            }}


            .header,
            .content,
            .footer {{
                padding-left: 15px;

                padding-right: 15px;
            }}


            .candidate-summary {{
                grid-template-columns:
                    1fr;
            }}


            .data-table {{
                font-size: 13px;
            }}


            .data-table th {{
                width: 40%;
            }}

        }}


        /* ================================================================
           PRINT
           ================================================================ */

        @media print {{

            body {{
                background:
                    #ffffff;
            }}


            .container {{
                max-width: none;

                margin: 0;

                box-shadow: none;
            }}


            .header {{
                padding:
                    20px 0;
            }}


            .content {{
                padding:
                    10px 0;
            }}


            .page-section {{
                break-inside:
                    avoid;
            }}


            .section-title {{
                break-after:
                    avoid;
            }}


            tr {{
                break-inside:
                    avoid;
            }}


            .footer {{
                padding:
                    15px 0;
            }}


            @page {{
                size: A4;

                margin: 15mm;
            }}

        }}

    </style>

</head>


<body>


<div class="container">


    <!-- ================================================================
         HEADER
         ================================================================ -->

    <header class="header">

        <h1>
            Periodical Medical Examination Report
        </h1>

        <div class="subtitle">
            Digital PME Record
        </div>


        <div class="candidate-summary">


            <div class="summary-box">

                <div class="summary-label">
                    Candidate
                </div>

                <div class="summary-value">
                    {esc(candidate_name)}
                </div>

            </div>


            <div class="summary-box">

                <div class="summary-label">
                    Roll Number
                </div>

                <div class="summary-value">
                    {esc(roll_number)}
                </div>

            </div>


            <div class="summary-box">

                <div class="summary-label">
                    Medical Examination
                </div>

                <div class="summary-value">
                    {esc(medical_date)}
                </div>

            </div>


        </div>

    </header>


    <!-- ================================================================
         REPORT CONTENT
         ================================================================ -->

    <main class="content">

        {render_page_1(report)}

        {render_page_2(report)}

        {render_page_3(report)}

        {render_page_4(report)}

        {render_extraction_metadata(report)}

    </main>


    <!-- ================================================================
         FOOTER
         ================================================================ -->

    <footer class="footer">

        Digital PME Data Record

    </footer>


</div>


</body>

</html>
"""


# ============================================================================
# JSON EXPORT
# ============================================================================

def save_json(
    report: PMEReportData,
    output_path: Path,
) -> None:
    """
    Save the report as machine-readable JSON.

    This JSON is useful later for:
        - APIs
        - analytics
        - RAG
        - Text-to-SQL
        - downstream processing
        - auditing
    """

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    payload = report_data_to_dict(report)

    with output_path.open(
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            payload,
            file,
            indent=2,
            ensure_ascii=False,
            default=str,
        )


# ============================================================================
# MAIN REPORT GENERATOR
# ============================================================================

def generate_report(
    examination: MedicalExamination,
    output_dir: str | Path = "data/reports",
) -> tuple[Path, Path]:
    """
    Generate both HTML and JSON reports for one examination.

    Returns:
        (html_path, json_path)
    """

    output_dir = Path(output_dir)

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    # ------------------------------------------------------------------------
    # Convert database models into report-ready data.
    # ------------------------------------------------------------------------

    report = build_report_data(
        examination
    )

    # ------------------------------------------------------------------------
    # Determine filename.
    # ------------------------------------------------------------------------

    roll_number = (
        report.candidate.roll_number
        or f"examination_{report.examination.id}"
    )

    filename = safe_filename(
        roll_number
    )

    html_path = (
        output_dir
        / f"{filename}.html"
    )

    json_path = (
        output_dir
        / f"{filename}.json"
    )

    # ------------------------------------------------------------------------
    # Generate HTML.
    # ------------------------------------------------------------------------

    html_content = render_html(
        report
    )

    with html_path.open(
        "w",
        encoding="utf-8",
    ) as file:

        file.write(
            html_content
        )

    # ------------------------------------------------------------------------
    # Generate JSON.
    # ------------------------------------------------------------------------

    save_json(
        report,
        json_path,
    )

    return (
        html_path,
        json_path,
    )