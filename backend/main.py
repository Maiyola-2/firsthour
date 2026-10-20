"""FirstHour backend: triage engine (Phase 2).

Run from the backend folder:
    uvicorn main:app --reload

Then open http://127.0.0.1:8000/docs to try the API in your browser.
"""

import json
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query

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
