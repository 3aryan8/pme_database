# Phase: dashboard | Input: normalized database and report-image paths | Output: Streamlit candidate search and review UI | Command: ``uv run streamlit run frontend/app.py``.
from __future__ import annotations

from io import BytesIO
import os
import sys
from datetime import date, datetime
from pathlib import Path
import logging

import pandas as pd
import streamlit as st
from sqlalchemy import select

REPO_DIR = Path(__file__).resolve().parents[1]
if str(REPO_DIR) not in sys.path:
    sys.path.insert(0, str(REPO_DIR))

from src.database.config import get_extraction_dir
from src.database.database import get_session, init_db
from src.database.importer import sync_extractions
from src.database.models import Candidate
from src.database.repository import (
    get_candidate_directory,
    get_dashboard_stats,
    get_latest_examination_for_candidate,
    search_candidates,
)
from src.database.report_images import find_report_images


LOGGER = logging.getLogger(__name__)


st.set_page_config(
    page_title="Candidate Database Dashboard",
    page_icon="✚",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@600;700;800&display=swap');
    :root { --ink: #17332f; --muted: #667b76; --line: #dcebe6; --mint: #eaf7f2; --teal: #0f8b78; --deep: #0d3b35; --coral: #e87561; }
    .stApp { background: #f3f8f6; color: var(--ink); }
    /* Use the complete browser viewport instead of Streamlit's centered canvas. */
    [data-testid="stHeader"] { background: transparent; height: 0; }
    [data-testid="stHeader"] [data-testid="stDecoration"] { display: none; }
    [data-testid="stHeader"] [data-testid="stToolbar"] { display: none; }
    #MainMenu, footer { display: none; }
    [data-testid="stAppViewContainer"] { min-height: 100vh; }
    [data-testid="stAppViewContainer"] > .main { width: 100%; }
    .block-container { width: 100%; max-width: none; padding: .85rem 2.4rem 2rem; }
    h1, h2, h3, h4 { font-family: 'Manrope', sans-serif; color: var(--ink); letter-spacing: -0.04em; }
    p, label, input, button, div { font-family: 'DM Sans', sans-serif; }
    .hero { position: relative; overflow: hidden; padding: 1.25rem 1.7rem 1.15rem; margin-bottom: 1.15rem; border-radius: 20px; background: linear-gradient(115deg, #0d3b35 0%, #155b4e 58%, #277e6c 100%); color: #f3fffb; box-shadow: 0 12px 28px rgba(13,59,53,.14); }
    .hero:after { content: "✚"; position: absolute; right: 6%; top: -36px; color: rgba(255,255,255,.1); font-size: 9rem; font-family: sans-serif; }
    .eyebrow { color: #9ee6d4; font-weight: 700; letter-spacing: .13em; text-transform: uppercase; font-size: .72rem; position: relative; z-index: 1; }
    .hero h1 { color: #fff; font-size: clamp(1.8rem, 3.2vw, 2.7rem); margin: .25rem 0 .3rem; position: relative; z-index: 1; }
    .hero p { color: #d5f2e9; font-size: .92rem; max-width: 690px; margin: 0; position: relative; z-index: 1; }
    .hero-meta { display: inline-flex; align-items: center; gap: .45rem; margin-top: .5rem; padding: .32rem .62rem; border: 1px solid rgba(255,255,255,.2); border-radius: 999px; color: #e2faf3; font-size: .75rem; position: relative; z-index: 1; }
    .hero-dot { width: 7px; height: 7px; border-radius: 50%; background: #7ce0b4; box-shadow: 0 0 0 4px rgba(124,224,180,.15); }
    .metric-card, .panel, .detail-card { background: rgba(255,255,255,.96); border: 1px solid var(--line); border-radius: 18px; box-shadow: 0 9px 30px rgba(13,59,53,.055); }
    .metric-card { padding: .65rem .9rem; min-height: 76px; margin-bottom: .35rem; border-top: 3px solid var(--teal); }
    .metric-label { color: var(--muted); font-size: .75rem; font-weight: 700; text-transform: uppercase; letter-spacing: .08em; }
    .metric-value { color: var(--deep); font-family: 'Manrope'; font-size: 1.65rem; font-weight: 800; margin-top: .15rem; }
    .panel { padding: .8rem 1.1rem; margin: 1.15rem 0; }
    .search-panel { border-top: 4px solid var(--teal); }
    .section-kicker { color: var(--teal); font-size: .72rem; text-transform: uppercase; letter-spacing: .1em; font-weight: 800; }
    .section-title { font-family: 'Manrope'; color: var(--deep); font-size: 1.2rem; font-weight: 800; margin: .12rem 0 .55rem; }
    .detail-card { padding: .6rem .8rem; min-height: 64px; box-sizing: border-box; border: 1px solid #b8e2d5; border-top: 3px solid var(--teal); background: linear-gradient(180deg, #f0fbf7 0%, #ffffff 34%); }
    .detail-card h4 { margin: 0 0 .35rem; font-size: .9rem; color: #087563; }
    .kv { display: flex; justify-content: space-between; gap: 1rem; border-bottom: 1px solid #edf4f1; padding: .52rem 0; }
    .kv:last-child { border-bottom: 0; }
    .kv span:first-child { color: var(--muted); font-size: .84rem; }
    .kv span:last-child { text-align: right; font-weight: 600; font-size: .88rem; color: var(--ink); }
    .kv-important { margin: .3rem -.35rem; padding: .72rem .65rem; border: 1px solid #8ed2bf; border-left: 4px solid #0f8b78; border-radius: 9px; background: #e7f8f1; }
    .kv-important span:first-child { color: #087563; font-weight: 800; }
    .kv-important span:last-child { color: #075f51; font-size: 1rem; font-weight: 800; }
    .result-banner { background: #e9f8f2; border: 1px solid #bde6d8; color: #126b5a; padding: 1rem 1.1rem; border-radius: 12px; margin: .9rem 0 1rem; }
    .subtle-note { color: var(--muted); font-size: .82rem; margin: -.2rem 0 .55rem; }
    .required-note { display: flex; align-items: center; gap: .55rem; background: #fff7e6; border: 1px solid #f0c36b; color: #7b4b00; border-radius: 10px; padding: .5rem .7rem; margin: .15rem 0 .65rem; font-weight: 700; font-size: .8rem; }
    .required-note strong { color: #c85b00; }
    .record-heading { display: flex; align-items: baseline; justify-content: space-between; gap: 1rem; margin-top: 1.4rem; }
    .record-heading h3 { margin: 0; }
    .record-count { color: var(--muted); font-size: .85rem; }
    .empty-state { background: #fff; border: 1px dashed #b6d7cd; border-radius: 14px; padding: 1.5rem; color: var(--muted); text-align: center; }
    [data-testid="stSidebar"] { background: var(--deep); }
    [data-testid="stSidebar"] * { color: #e9faf5 !important; }
    [data-testid="stSidebar"][aria-expanded="false"] {
        width: 18rem !important;
        min-width: 18rem !important;
        flex: 0 0 18rem !important;
        transform: translateX(0) !important;
        visibility: visible !important;
    }
    [data-testid="stSidebarCollapseButton"],
    [data-testid="stExpandSidebarButton"] { display: none !important; }
    [data-testid="stSidebar"] .stRadio label { color: #c9e2db !important; }
    [data-testid="stTextInput"] label, [data-testid="stTextInput"] label p { color: var(--ink) !important; font-weight: 700; }
    [data-testid="stTextInput"] input { border-radius: 9px; border: 2px solid #159b86; background: #fbfffd; color: var(--ink) !important; caret-color: var(--teal); box-shadow: 0 0 0 2px rgba(21,155,134,.10); }
    [data-testid="stTextInput"] input::placeholder { color: #71827d !important; opacity: 1; }
    [data-testid="stTextInput"] input:focus { border-color: #087563; box-shadow: 0 0 0 3px rgba(15,139,120,.24); }
    [data-testid="stFormSubmitButton"] button, [data-testid="stBaseButton-primary"] { background: var(--teal); border: 0; border-radius: 10px; font-weight: 700; }
    [data-testid="stFormSubmitButton"] button:hover, [data-testid="stBaseButton-primary"]:hover { background: #0b7465; }
    [data-testid="stDownloadButton"] button { background: var(--teal) !important; color: #ffffff !important; border: 1px solid #087563 !important; border-radius: 10px; font-weight: 700; }
    [data-testid="stDownloadButton"] button p { color: #ffffff !important; }
    [data-testid="stDownloadButton"] button:hover { background: #0b7465 !important; border-color: #075f51 !important; }
    [data-testid="stDownloadButton"] button:focus-visible { outline: 3px solid #7ce0b4; outline-offset: 2px; }
    [data-testid="stDataFrame"] { border: 1px solid var(--line); border-radius: 12px; overflow: hidden; background: #fff; }
    [data-testid="stMetric"] { background: #fff; border: 1px solid var(--line); border-radius: 14px; padding: .8rem 1rem; }
    [data-testid="stFileUploader"] { border-radius: 12px; }
    [data-testid="stCaptionContainer"] code { display: inline-block; max-width: 100%; padding: .16rem .38rem; border: 1px solid #8ed2bf; border-radius: 5px; background: #e7f8f1; color: #075f51 !important; font-weight: 700; overflow-wrap: anywhere; word-break: break-all; }
        @media (max-width: 760px) {
            .block-container { padding: .7rem; }
            .hero { padding: 1rem; }
            .hero:after { font-size: 7rem; }
            .record-heading { display: block; }
            [data-testid="stHorizontalBlock"] { flex-direction: column !important; gap: .65rem !important; }
            [data-testid="stHorizontalBlock"] > [data-testid="column"] { width: 100% !important; flex: 1 1 100% !important; min-width: 100% !important; }
            .metric-card { min-height: 68px; }
            .metric-value { font-size: 1.45rem; }
            .panel { padding: .75rem; }
            .detail-card { min-height: 0; padding: 1rem; }
            .kv { align-items: flex-start; }
            .kv span:last-child { max-width: 58%; overflow-wrap: anywhere; }
        }

    /* Make expanders and their headers use a white background for clarity */
    .st-expander, .stExpander, .st-expanderHeader, .stExpanderHeader, .streamlit-expander, .streamlit-expanderHeader {
      background: #ffffff !important;
      color: var(--ink) !important;
      border: 1px solid var(--line) !important;
      box-shadow: none !important;
      border-radius: 10px !important;
    }
    .st-expander > div[role="button"], .st-expanderHeader, .stExpanderHeader > button {
      background: #ffffff !important;
      color: var(--ink) !important;
    }
        [data-testid="stExpander"] { background: #ffffff !important; border: 1px solid var(--line) !important; border-radius: 10px !important; }
        [data-testid="stExpander"] summary, [data-testid="stExpander"] summary:hover { background: #ffffff !important; color: var(--ink) !important; }
        [data-testid="stExpander"] summary p, [data-testid="stExpander"] summary span,
        [data-testid="stExpander"] summary svg { color: var(--ink) !important; fill: var(--ink) !important; }

    </style>
    """,
    unsafe_allow_html=True,
)


def display(value: object) -> str:
    if value is None or value == "":
        return "Not available"
    if isinstance(value, (date, datetime)):
        return value.strftime("%d %b %Y")
    return str(value)


def kv(label: str, value: object, important: bool = False) -> None:
    class_name = "kv kv-important" if important else "kv"
    st.markdown(
        f'<div class="{class_name}"><span>{label}</span><span>{display(value)}</span></div>',
        unsafe_allow_html=True,
    )


def show_candidate(candidate: Candidate) -> None:
    with get_session() as session:
        examination = get_latest_examination_for_candidate(session, candidate.id)
        if examination is None:
            st.warning("This candidate has no medical examination record.")
            return

        st.markdown(
            f'<div class="result-banner"><strong>{display(candidate.candidate_name)}</strong> '
            f'found in the database · Roll number {display(candidate.roll_number)}</div>',
            unsafe_allow_html=True,
        )
        extraction_runs = sorted(
            examination.extraction_runs,
            key=lambda extraction: extraction.id,
            reverse=True,
        )
        document_id = (
            extraction_runs[0].document_id
            if extraction_runs
            else None
        )
        st.markdown(
            '<div class="detail-card"><h4>Original candidate images</h4>',
            unsafe_allow_html=True,
        )
        if document_id is None:
            LOGGER.warning(
                "Candidate id=%s has no extraction run/document_id",
                candidate.id,
            )
            st.warning(
                "Candidate found, but original image is not available."
            )
        else:
            try:
                report_pages = find_report_images(document_id)
            except FileNotFoundError:
                report_pages = []
            image_paths = [path for _, path in report_pages]
            if image_paths:
                image_columns = st.columns(
                    min(len(image_paths), 4)
                )
                for index, image_path in enumerate(image_paths):
                    with image_columns[index % len(image_columns)]:
                        st.image(
                            str(image_path),
                            caption=image_path.name,
                            use_container_width=True,
                        )
                st.caption(
                    f"Hash/Source ID: `{document_id}` · "
                    f"{len(image_paths)} original image(s)"
                )
            else:
                LOGGER.warning(
                    "Candidate id=%s document_id=%s has no source images",
                    candidate.id,
                    document_id,
                )
                st.warning(
                    "Candidate found, but original image is not available."
                )
        st.markdown("</div>", unsafe_allow_html=True)
        left, right = st.columns(2)
        with left:
            st.markdown('<div class="detail-card"><h4>Candidate identity</h4>', unsafe_allow_html=True)
            kv("Candidate name", candidate.candidate_name)
            kv("Father's name", candidate.father_name)
            kv("Date of birth", candidate.date_of_birth)
            kv("Roll number", candidate.roll_number)
            kv("Recruitment CEN", candidate.recruitment_cen)
            kv("Mobile", candidate.mobile_number)
            kv("Email", candidate.email)
            st.markdown("</div>", unsafe_allow_html=True)
        with right:
            st.markdown('<div class="detail-card"><h4>Medical examination</h4>', unsafe_allow_html=True)
            kv("DV date", examination.dv_date)
            kv("Medical examination date", examination.medical_examination_date)
            kv("Medical class", examination.medical_class, important=True)
            kv("Identification marks", examination.identification_marks)
            kv("Declaration date", examination.candidate_declaration_date)
            kv("Doctor", examination.examining_doctor.doctor_name if examination.examining_doctor else None)
            st.markdown("</div>", unsafe_allow_html=True)

        pme, vision = st.columns(2)
        with pme:
            st.markdown('<div class="detail-card"><h4>PME case</h4>', unsafe_allow_html=True)
            case = examination.pme_case
            kv("Urine", case.urine if case else None)
            kv("Sugar", case.sugar if case else None)
            kv("Albumin", case.alb if case else None)
            kv("Remarks", case.handwritten_remarks if case else None)
            if case and case.vision_rows:
                st.caption("Measurements")
                st.dataframe(
                    [{"Row": row.row_label, "Right": row.right_value, "Left": row.left_value}
                     for row in case.vision_rows],
                    use_container_width=True,
                    hide_index=True,
                )
            st.markdown("</div>", unsafe_allow_html=True)
        with vision:
            st.markdown('<div class="detail-card"><h4>Vision and fitness</h4>', unsafe_allow_html=True)
            eyesight = examination.vision
            fitness = examination.fitness
            kv("Fit in class", fitness.fit_in_class if fitness else None, important=True)
            kv("Unfit in class", fitness.unfit_in_class if fitness else None, important=True)
            kv("Right eye distance", eyesight.right_distance_uncorrected if eyesight else None)
            kv("Left eye distance", eyesight.left_distance_uncorrected if eyesight else None)
            kv("Color perception", eyesight.color_perception if eyesight else None)
            kv("Night vision", eyesight.night_vision if eyesight else None)
            st.markdown("</div>", unsafe_allow_html=True)

        physical, declarations = st.columns(2)
        with physical:
            st.markdown('<div class="detail-card"><h4>Physical examination</h4>', unsafe_allow_html=True)
            record = examination.physical
            for label, attr in (("Urine", "urine"), ("Hearing", "hearing"), ("Pulse", "pr"),
                                ("Blood pressure", "bp"), ("Heart", "heart"), ("Lungs", "lungs")):
                kv(label, getattr(record, attr, None) if record else None)
            st.markdown("</div>", unsafe_allow_html=True)
        with declarations:
            st.markdown('<div class="detail-card"><h4>Declarations</h4>', unsafe_allow_html=True)
            if examination.declarations:
                st.dataframe(
                    [{"Part": item.part, "Question": item.question_no, "Answer": item.answer}
                     for item in examination.declarations],
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.caption("No declarations stored.")
            st.markdown("</div>", unsafe_allow_html=True)

        if extraction_runs:
            with st.expander(
                f"Complete extracted data ({len(extraction_runs)} run(s))",
                expanded=False,
            ):
                for extraction in extraction_runs:
                    extracted_label = extraction.document_id
                    if extraction.model_name:
                        extracted_label += f" · {extraction.model_name}"
                    with st.expander(extracted_label, expanded=False):
                        st.json(extraction.raw_json)


@st.fragment(run_every="60s")
def main() -> None:
    init_db()
    extraction_dir = get_extraction_dir()
    current_document_ids = {
        path.parent.name
        for path in extraction_dir.rglob("record.json")
    }
    with get_session() as session:
        sync_extractions(session)
    with get_session() as session:
        stats = get_dashboard_stats(session, current_document_ids)

    if "sync_message" not in st.session_state:
        st.session_state.sync_message = None

    st.markdown(
        '<div class="hero"><div class="eyebrow">PME records · clinical data workspace</div>'
        '<h1>Candidate Database</h1>'
        '<p>Search and review verified medical-examination records from across India using a precise candidate identity match.</p>'
        '<div class="hero-meta"><span class="hero-dot"></span>Pan-India record workspace&nbsp; · &nbsp;Live database connection</div></div>',
        unsafe_allow_html=True,
    )

    metric_columns = st.columns(2)
    metric_data = (
        ("Total candidates", stats["candidates"]),
        ("Unique medical examinations", stats["examinations"]),
    )
    for column, (label, value) in zip(metric_columns, metric_data):
        with column:
            st.markdown(
                f'<div class="metric-card"><div class="metric-label">{label}</div>'
                f'<div class="metric-value">{value:,}</div></div>',
                unsafe_allow_html=True,
            )
    st.caption(
        "Counts use the current extraction files; duplicate reports for the "
        "same candidate and examination date count once."
    )

    with st.sidebar:
        st.markdown("## ✚ PME Dashboard")
        st.caption("Connected directly to the existing database")
        page = st.radio("Navigate", ["Search candidate", "Candidate directory"])
        if st.button("Sync extraction files", use_container_width=True):
            with st.spinner("Fetching and syncing extraction files..."):
                try:
                    with get_session() as session:
                        imported, failed = sync_extractions(session)
                except Exception as error:
                    LOGGER.exception("Manual extraction sync failed")
                    st.session_state.sync_message = (
                        "error",
                        f"Sync failed: {error}",
                    )
                else:
                    status = "success" if failed == 0 else "warning"
                    st.session_state.sync_message = (
                        status,
                        f"Processed {imported} extraction records; "
                        f"{failed} failed.",
                    )
            st.rerun()
        if st.session_state.sync_message:
            message_type, message = st.session_state.sync_message
            if message_type == "success":
                st.success(message)
            elif message_type == "warning":
                st.warning(message)
            else:
                st.warning(message)
        st.divider()
        st.caption(f"Database URL: {os.getenv('DATABASE_URL', 'SQLite · data/pme.db')}")

    if page == "Search candidate":
        st.markdown(
            '<div class="panel search-panel"><div class="section-kicker">Identity lookup</div>'
            '<div class="section-title">Find a candidate</div>'
            '<div class="subtle-note">Enter all three identity fields for an exact match. Uppercase and lowercase letters are both accepted.</div>'
            '<div class="required-note"><strong>Required:</strong> Fill in Candidate name, Father\'s name, and Date of birth before searching.</div>',
            unsafe_allow_html=True,
        )
        with st.form("candidate-search", clear_on_submit=False):
            first, second, third, action = st.columns([1.2, 1.2, .72, .75])
            with first:
                name = st.text_input("Candidate name *", placeholder="e.g. PRAKASH CHANDRA MURMU")
            with second:
                father_name = st.text_input("Father's name *", placeholder="e.g. LOBIN MURMU")
            with third:
                dob_text = st.text_input(
                    "Date of birth *",
                    placeholder="DD-MM-YYYY",
                    help="Enter the date exactly as DD-MM-YYYY, for example 21-02-1996.",
                )
            with action:
                st.markdown("<div style='height: 1.72rem'></div>", unsafe_allow_html=True)
                submitted = st.form_submit_button("Search", type="primary", use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

        if "search_candidate_ids" not in st.session_state:
            st.session_state.search_candidate_ids = []
        if "search_error" not in st.session_state:
            st.session_state.search_error = None

        if submitted:
            st.session_state.search_candidate_ids = []
            st.session_state.search_error = None
            if not name.strip() or not father_name.strip() or not dob_text.strip():
                st.session_state.search_error = "Enter candidate name, father's name, and date of birth."
            else:
                try:
                    dob = datetime.strptime(
                        dob_text.strip(),
                        "%d-%m-%Y",
                    ).date()
                except ValueError:
                    st.session_state.search_error = "Enter DOB in DD-MM-YYYY format, for example 21-02-1996."
                else:
                    with get_session() as session:
                        matches = search_candidates(session, name, father_name, dob)
                    st.session_state.search_candidate_ids = [
                        candidate.id for candidate in matches
                    ]

        if st.session_state.search_error:
            st.error(st.session_state.search_error)
        elif st.session_state.search_candidate_ids:
            with get_session() as session:
                candidates = list(session.scalars(
                    select(Candidate).where(
                        Candidate.id.in_(st.session_state.search_candidate_ids)
                    )
                ).all())
            candidates.sort(
                key=lambda candidate: st.session_state.search_candidate_ids.index(candidate.id)
            )
            st.markdown(
                f'<div class="record-heading"><h3>Candidate result</h3>'
                f'<span class="record-count">{len(candidates)} matching record(s)</span></div>',
                unsafe_allow_html=True,
            )
            for candidate in candidates:
                show_candidate(candidate)
        elif submitted:
            st.markdown(
                '<div class="empty-state"><strong>No candidate found</strong><br>'
                'Check the spelling of the name, father’s name, and DOB, then try again.</div>',
                unsafe_allow_html=True,
            )
    else:
        st.markdown(
            '<div class="panel"><div class="section-kicker">Records</div>'
            '<div class="section-title">Candidate directory</div>'
            '<div class="subtle-note">Browse the latest stored records or filter by name, father\'s name, roll number, or recruitment CEN.</div>',
            unsafe_allow_html=True,
        )
        with get_session() as session:
            candidates = get_candidate_directory(session)
        if candidates:
            directory_filter = st.text_input(
                "Filter directory",
                placeholder="Type a name, father's name, roll number, or CEN",
                label_visibility="collapsed",
            ).strip().casefold()
            if directory_filter:
                candidates = [
                    candidate for candidate in candidates
                    if directory_filter in " ".join(
                        (
                            candidate.candidate_name or "",
                            candidate.father_name or "",
                            candidate.roll_number or "",
                            candidate.recruitment_cen or "",
                        )
                    ).casefold()
                ]
            st.caption(f"Showing {len(candidates)} of {stats['candidates']:,} candidates")
            st.dataframe(
                [{
                    "Candidate name": candidate.candidate_name or "Not available",
                    "Father's name": candidate.father_name or "Not available",
                    "Date of birth": candidate.date_of_birth,
                    "Roll number": candidate.roll_number or "Not available",
                    "Recruitment CEN": candidate.recruitment_cen or "Not available",
                } for candidate in candidates],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Candidate name": st.column_config.TextColumn("Candidate name", width="large"),
                    "Father's name": st.column_config.TextColumn("Father's name", width="large"),
                    "Date of birth": st.column_config.DateColumn("Date of birth", format="DD MMM YYYY"),
                    "Roll number": st.column_config.TextColumn("Roll number", width="medium"),
                    "Recruitment CEN": st.column_config.TextColumn("Recruitment CEN", width="small"),
                },
            )
            with get_session() as session:
                export_rows = []
                for candidate in candidates:
                    examination = get_latest_examination_for_candidate(session, candidate.id)
                    fitness = examination.fitness if examination else None
                    doctor = examination.examining_doctor if examination else None
                    export_rows.append({
                        "Candidate name": candidate.candidate_name,
                        "Father's name": candidate.father_name,
                        "Date of birth": candidate.date_of_birth,
                        "Roll number": candidate.roll_number,
                        "Recruitment CEN": candidate.recruitment_cen,
                        "Medical examination date": examination.medical_examination_date if examination else None,
                        "DV date": examination.dv_date if examination else None,
                        "Medical class": examination.medical_class if examination else None,
                        "Candidate declaration date": examination.candidate_declaration_date if examination else None,
                        "Doctor": doctor.doctor_name if doctor else None,
                        "Fit in class": fitness.fit_in_class if fitness else None,
                        "Unfit in class": fitness.unfit_in_class if fitness else None,
                    })
            export_frame = pd.DataFrame(export_rows)
            csv_data = export_frame.to_csv(index=False).encode("utf-8")
            excel_buffer = BytesIO()
            export_frame.to_excel(excel_buffer, index=False, engine="openpyxl")
            download_columns = st.columns(2)
            with download_columns[0]:
                st.download_button(
                    "Download CSV",
                    data=csv_data,
                    file_name="filtered_candidates.csv",
                    mime="text/csv",
                    use_container_width=True,
                )
            with download_columns[1]:
                st.download_button(
                    "Download Excel",
                    data=excel_buffer.getvalue(),
                    file_name="filtered_candidates.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )
            if not candidates:
                st.info("No candidates match this filter.")
        else:
            st.markdown('<div class="empty-state">No candidates are stored yet.</div>', unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)


if __name__ == "__main__":
    main()
