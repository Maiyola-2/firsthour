"""FirstHour backend: triage engine (Phase 2), evidence pack PDF (Phase 3),
contact-warning generator (Phase 5).

Run from the backend folder:
    uvicorn main:app --reload

Then open http://127.0.0.1:8000/docs to try the API in your browser.
"""

import json
from pathlib import Path
from typing import Any, List, Literal, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from evidence import build_evidence_pdf
from warn import build_warning

DATA_FILE = Path(__file__).parent / "triage_data.json"
Lang = Literal["en", "sw"]


def load_data() -> dict:
    with open(DATA_FILE, encoding="utf-8") as f:
        return json.load(f)


def validate_data(data: dict) -> None:
    """Fail fast on startup if the decision trees contain mistakes."""
    for case_id, case in data["cases"].items():
        nodes = case["nodes"]
        if case["start"] not in nodes:
            raise ValueError(f"{case_id}: start node '{case['start']}' does not exist")
        for node_id, node in nodes.items():
            if node["type"] == "question":
                for option in node["options"]:
                    if option["next"] not in nodes:
                        raise ValueError(
                            f"{case_id}.{node_id}: option points to missing node '{option['next']}'"
                        )
            elif node["type"] == "plan":
                for key in ("title", "steps", "report_to", "evidence"):
                    if key not in node:
                        raise ValueError(f"{case_id}.{node_id}: plan is missing '{key}'")
            else:
                raise ValueError(f"{case_id}.{node_id}: unknown node type '{node['type']}'")


def localize(value: Any, lang: str) -> Any:
    """Pick the chosen language wherever a {'en': ..., 'sw': ...} pair appears."""
    if isinstance(value, dict):
        if set(value.keys()) == {"en", "sw"}:
            return value[lang]
        return {k: localize(v, lang) for k, v in value.items()}
    if isinstance(value, list):
        return [localize(item, lang) for item in value]
    return value


DATA = load_data()
validate_data(DATA)

app = FastAPI(
    title="FirstHour API",
    description="Incident-response guidance for people who have just been scammed or hacked.",
    version=DATA["meta"]["version"],
)


def get_case(case_id: str) -> dict:
    case = DATA["cases"].get(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"Unknown case '{case_id}'")
    return case


def build_node_response(case_id: str, node_id: str, lang: str) -> dict:
    case = get_case(case_id)
    node = case["nodes"].get(node_id)
    if node is None:
        raise HTTPException(status_code=404, detail=f"Unknown node '{node_id}' in case '{case_id}'")
    response = {"case": case_id, "node_id": node_id, **localize(node, lang)}
    if node["type"] == "plan":
        response["disclaimer"] = localize(DATA["disclaimer"], lang)
    return response


@app.get("/")
def health() -> dict:
    return {
        "app": "FirstHour",
        "status": "ok",
        "version": DATA["meta"]["version"],
        "data_status": DATA["meta"]["status"],
    }


@app.get("/cases")
def list_cases(lang: Lang = Query("en", description="Language: en or sw")) -> list:
    return [
        {
            "id": case_id,
            "title": localize(case["title"], lang),
            "description": localize(case["description"], lang),
        }
        for case_id, case in DATA["cases"].items()
    ]


@app.get("/cases/{case_id}/start")
def start_case(case_id: str, lang: Lang = Query("en", description="Language: en or sw")) -> dict:
    case = get_case(case_id)
    return build_node_response(case_id, case["start"], lang)


@app.get("/cases/{case_id}/nodes/{node_id}")
def get_node(case_id: str, node_id: str, lang: Lang = Query("en", description="Language: en or sw")) -> dict:
    return build_node_response(case_id, node_id, lang)


# ---------------------------------------------------------------------------
# Phase 3: evidence pack
# ---------------------------------------------------------------------------


class EvidenceRequest(BaseModel):
    """Everything is optional except the language, so a victim in a hurry
    can fill in only what they know."""

    lang: Lang = "en"
    case_id: Optional[str] = Field(None, description="e.g. sent_money")
    plan_id: Optional[str] = Field(
        None, description="Action plan to include, e.g. plan_mobile_money"
    )
    victim_name: Optional[str] = Field(None, max_length=120)
    victim_phone: Optional[str] = Field(None, max_length=30)
    incident_date: Optional[str] = Field(None, max_length=40, description="e.g. 20 Oct 2026")
    incident_time: Optional[str] = Field(None, max_length=20, description="e.g. 14:30")
    amount_kes: Optional[float] = Field(None, ge=0, le=1_000_000_000)
    payment_method: Optional[str] = Field(None, max_length=80)
    transaction_id: Optional[str] = Field(None, max_length=60)
    bank_or_provider: Optional[str] = Field(None, max_length=120)
    scammer_phone: Optional[str] = Field(None, max_length=30)
    scammer_name: Optional[str] = Field(None, max_length=120)
    account_affected: Optional[str] = Field(None, max_length=120)
    description: Optional[str] = Field(None, max_length=3000)
    actions_taken: List[str] = Field(default_factory=list, max_length=15)
    bank_reference: Optional[str] = Field(None, max_length=60)
    ob_number: Optional[str] = Field(None, max_length=60)


@app.post("/evidence/pdf")
def create_evidence_pdf(request: EvidenceRequest) -> Response:
    """Generate a PDF evidence report. Nothing is stored on the server."""
    case_title = ""
    plan = None

    if request.case_id:
        case = get_case(request.case_id)
        case_title = localize(case["title"], request.lang)
        if request.plan_id:
            node = case["nodes"].get(request.plan_id)
            if node is None or node["type"] != "plan":
                raise HTTPException(
                    status_code=404,
                    detail=f"Unknown plan '{request.plan_id}' in case '{request.case_id}'",
                )
            plan = localize(node, request.lang)
    elif request.plan_id:
        raise HTTPException(status_code=422, detail="plan_id needs a case_id")

    pdf_bytes = build_evidence_pdf(
        report=request.model_dump(),
        lang=request.lang,
        case_title=case_title,
        plan=plan,
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="firsthour-evidence-report.pdf"'},
    )


# ---------------------------------------------------------------------------
# Phase 5: contact-warning generator
# ---------------------------------------------------------------------------


@app.get("/templates/warn-contacts")
def warn_contacts(
    lang: Lang = Query("en", description="Language: en or sw"),
    platform: Literal["whatsapp", "social", "email"] = Query("whatsapp"),
    name: Optional[str] = Query(None, max_length=60, description="Optional name to sign the message"),
) -> dict:
    """A ready-to-send message to warn contacts after an account was hijacked."""
    return {"message": build_warning(lang, platform, name)}
