from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ============================================================
# Common / Utility Models
# ============================================================

class Provenance(BaseModel):
    """
    Metadata describing where an extracted value came from.
    """

    model_config = ConfigDict(extra="ignore")

    page_index: int | None = None
    model: str | None = None
    extracted_at: datetime | None = None
    raw_value: Any = None


# ============================================================
# Page 1
# ============================================================

class GeneralDetails(BaseModel):
    """
    Candidate identity and examination dates from Page 1.
    """

    model_config = ConfigDict(extra="ignore")

    candidate_name: str | None = None
    father_name: str | None = None
    date_of_birth: date | None = None

    # Page 4 candidate particulars may be extracted into
    # the general-details section by the OCR pipeline.
    mobile_number: str | None = None
    email: str | None = None

    dv_date: date | None = None
    medical_examination_date: date | None = None

    @field_validator(
        "date_of_birth",
        "dv_date",
        "medical_examination_date",
        mode="before",
    )
    @classmethod
    def parse_date(cls, value: Any) -> date | None:
        """
        Accept common date formats produced by OCR.
        """

        if value in (None, ""):
            return None

        if isinstance(value, date):
            return value

        value = str(value).strip()

        for fmt in (
            "%d-%m-%Y",
            "%d/%m/%Y",
            "%Y-%m-%d",
        ):
            try:
                return datetime.strptime(
                    value,
                    fmt,
                ).date()
            except ValueError:
                continue

        raise ValueError(
            f"Unsupported date: {value!r}"
        )


class NarrativeDetails(BaseModel):
    """
    Narrative/basic details extracted from Page 1.
    """

    model_config = ConfigDict(
        extra="ignore",
        populate_by_name=True,
    )

    roll_number: str | None = None

    recruitment_cen: str | None = None

    class_name: str | None = Field(
        default=None,
        alias="class",
    )


class PhysicalTraits(BaseModel):
    """
    Physical identification information from Page 1.
    """

    model_config = ConfigDict(extra="ignore")

    permanent_physical_identification_marks: (
        str | None
    ) = None


class Page1(BaseModel):
    """
    Structured representation of Page 1.
    """

    model_config = ConfigDict(extra="ignore")

    general_details: GeneralDetails = Field(
        default_factory=GeneralDetails
    )

    narrative_details: NarrativeDetails = Field(
        default_factory=NarrativeDetails
    )

    physical_traits: PhysicalTraits = Field(
        default_factory=PhysicalTraits
    )


# ============================================================
# Page 2
# ============================================================

class PmeCase(BaseModel):
    model_config = ConfigDict(extra="ignore")

    urine: str | None = None
    sugar: str | None = None
    alb: str | None = None


class PmeCaseMeasurement(BaseModel):
    model_config = ConfigDict(extra="ignore")

    row_label: str | None = None
    column_1: str | None = None
    column_2: str | None = None
    raw_text: str | None = None


class Page2(BaseModel):
    model_config = ConfigDict(extra="ignore")

    pme_case: PmeCase = Field(
        default_factory=PmeCase
    )

    measurements: list[PmeCaseMeasurement] = Field(
        default_factory=list
    )

    chest_xray_result: str | None = None

    advice: str | None = None

    handwritten_remarks: str | None = None


# ============================================================
# Page 3
# ============================================================

class Eye(BaseModel):
    """
    Vision measurements for one eye.
    """

    model_config = ConfigDict(extra="ignore")

    distance_uncorrected: str | None = None
    distance_corrected: str | None = None

    near_uncorrected: str | None = None
    near_corrected: str | None = None

    glasses_power_s: str | None = None
    glasses_power_c: str | None = None
    glasses_power_a: str | None = None


class Page3(BaseModel):
    """
    Structured representation of Page 3.
    """

    model_config = ConfigDict(extra="ignore")

    # --------------------------------------------------------
    # Fitness
    # --------------------------------------------------------

    fit_in_class: str | None = None
    unfit_in_class: str | None = None

    # --------------------------------------------------------
    # Acuity of Vision
    #
    # Expected structure:
    #
    # {
    #     "right_eye": {...},
    #     "left_eye": {...}
    # }
    # --------------------------------------------------------

    accuracy_of_vision: dict[str, Eye] = Field(
        default_factory=dict
    )

    # --------------------------------------------------------
    # Raw handwritten text
    # --------------------------------------------------------

    handwritten_text_below_vision_table: (
        str | None
    ) = None

    # --------------------------------------------------------
    # Vision-related fields
    # --------------------------------------------------------

    color_perception: str | None = None
    binocular_vision: str | None = None
    night_vision: str | None = None
    field_of_vision: str | None = None

    # --------------------------------------------------------
    # Physical examination
    # --------------------------------------------------------

    urine: str | None = None
    hearing: str | None = None

    pr: str | None = None
    bp: str | None = None

    cvs: str | None = None
    rs: str | None = None
    pia: str | None = None
    spine: str | None = None

    heart: str | None = None
    lungs: str | None = None

    general_physical_examination: (
        str | None
    ) = None

    # --------------------------------------------------------
    # Doctor
    # --------------------------------------------------------

    doctor_name: str | None = None


# ============================================================
# Page 4
# ============================================================

class Declaration(BaseModel):
    """
    One Yes/No declaration question.

    Examples:

        1a -> No
        1b -> No
        2  -> No
    """

    model_config = ConfigDict(extra="ignore")

    question_no: str

    answer: str | None = None


class Page4(BaseModel):
    """
    Structured representation of Page 4.

    Page 4 contains:

        PART-I
            1a
            1b
            2
            3
            4

        PART-II
            1
            2
            3
            4
            5
            6

        Declaration date
        Medical examiner
    """

    model_config = ConfigDict(extra="ignore")

    # --------------------------------------------------------
    # Candidate declarations
    # --------------------------------------------------------

    part_one: list[Declaration] = Field(
        default_factory=list
    )

    part_two: list[Declaration] = Field(
        default_factory=list
    )

    # --------------------------------------------------------
    # Declaration section
    # --------------------------------------------------------

    declaration_date: date | None = None

    doctor_name: str | None = None

    @field_validator(
        "declaration_date",
        mode="before",
    )
    @classmethod
    def parse_declaration_date(
        cls,
        value: Any,
    ) -> date | None:
        """
        Parse the handwritten declaration date.
        """

        if value in (None, ""):
            return None

        if isinstance(value, date):
            return value

        value = str(value).strip()

        for fmt in (
            "%d-%m-%Y",
            "%d/%m/%Y",
            "%Y-%m-%d",
        ):
            try:
                return datetime.strptime(
                    value,
                    fmt,
                ).date()
            except ValueError:
                continue

        raise ValueError(
            f"Unsupported declaration date: {value!r}"
        )


# ============================================================
# Complete PME Extraction
# ============================================================

class PMEExtraction(BaseModel):
    """
    Root model representing one complete 4-page PME document.

    This is the boundary between the Qwen extraction output
    and the database importer.
    """

    model_config = ConfigDict(extra="ignore")

    # --------------------------------------------------------
    # Document metadata
    # --------------------------------------------------------

    document_id: str

    model: str | None = None

    # --------------------------------------------------------
    # Raw extracted fields
    # --------------------------------------------------------

    fields: dict[str, Any]

    # --------------------------------------------------------
    # Extraction metadata
    # --------------------------------------------------------

    provenance: dict[str, Provenance] = Field(
        default_factory=dict
    )

    conflicts: list[Any] = Field(
        default_factory=list
    )

    pages_covered: list[int] = Field(
        default_factory=list
    )

    # ========================================================
    # Page accessors
    # ========================================================

    @property
    def page1(self) -> Page1:
        return Page1.model_validate(
            self.fields.get(
                "page_1_basic_info",
                {},
            )
        )

    @property
    def page2(self) -> Page2:
        return Page2.model_validate(
            self.fields.get(
                "page_2_medical_metrics",
                {},
            )
        )

    @property
    def page3(self) -> Page3:
        return Page3.model_validate(
            self.fields.get(
                "page_3_fitness_classification",
                {},
            )
        )

    @property
    def page4(self) -> Page4:
        return Page4.model_validate(
            self.fields.get(
                "page_4_declarations",
                {},
            )
        )

    # ========================================================
    # File loader
    # ========================================================

    @classmethod
    def from_file(
        cls,
        path: str | Path,
    ) -> "PMEExtraction":
        """
        Load one extraction JSON file and validate it.
        """

        path = Path(path)

        with path.open(
            "r",
            encoding="utf-8",
        ) as file:
            payload = json.load(file)

        return cls.model_validate(payload)