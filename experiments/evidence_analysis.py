import json
from pathlib import Path

from research_landscape.llm.local_model import LocalLLM
from research_landscape.processing.methodology_extraction import (
    MethodologyExtraction,
    verify_extraction_evidence,
)
from research_landscape.processing.methodology_aggregation import (
    collect_verified_claims, format_claims, synthesize_methodology_profile,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
path = PROJECT_ROOT / "data" / "methodology_extractions.json"

with path.open("r", encoding="utf-8") as file:
    saved_results = json.load(file)


#claims = collect_verified_claims(results)


llm = LocalLLM()


