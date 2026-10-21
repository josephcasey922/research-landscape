import json
from json_repair import repair_json
from dataclasses import dataclass
from research_landscape.llm.local_model import LocalLLM
import re

@dataclass
class MethodologyClaim:
    description: str
    evidence: str
    verified: bool


@dataclass
class MethodologyExtraction:
    passage: str
    claims: list[MethodologyClaim]
    raw_response: str
    parse_success: bool


def validate_extraction(result: dict) -> bool:
    expected_fields = {"method", "evaluation",
                     "data", "limitations"}
    if set(result.keys()) != expected_fields:
        return False

    for key in expected_fields:
        entry = result[key]

        if entry is None:
            continue

        if not isinstance(entry, dict):
            return False

        if set(entry.keys()) != {"value", "evidence"}:
            return False

        if not isinstance(entry["value"], str):
            return False

        if not isinstance(entry["evidence"], str):
            return False

        if not entry["value"].strip() or not entry["evidence"].strip():
            return False

    #if not all(isinstance(value, (str, type(None))) for value in result.values()):
    #    return False

    return True

def parse_claims(response: str) -> dict | None:
    response = response.strip()

    if response.startswith("```"):
        response = response.split("\n", 1)[-1]
        response = response.rsplit("```", 1)[0].strip()

    try:
        result = json.loads(response)
    except json.JSONDecodeError:
        try:
            result = repair_json(response, return_objects=True)
        except (ValueError, TypeError):
            return None

    if not isinstance(result, dict):
        return None

    if set(result.keys()) != {"claims"}:
        return None

    if not isinstance(result["claims"], list):
        return None

    for claim in result["claims"]:

        if not isinstance(claim, dict):
            return None

        if set(claim.keys()) != {"description", "block_id"}:
            return None

        if not isinstance(claim["description"], str):
            return None

        if not claim["description"].strip():
            return None

        if not isinstance(claim["block_id"], str):
            return None

        if not claim["block_id"].strip():
            return None

    return result

def extract_methodology(
    passage: str,
    llm: LocalLLM,
    paper_title: str
) -> MethodologyExtraction:

    blocks = create_evidence_blocks(passage)
    formatted_blocks = format_evidence_blocks(blocks)

    system_prompt = """
    You extract methodological information from scientific research papers.

    Identify distinct methodological details describing how the authors
    conduct their research.

    These may include experimental designs, mathematical techniques,
    statistical procedures, algorithms, computational methods,
    data collection, assumptions, and evaluation procedures.

    Rules:
    - Extract only methods used or proposed by the authors.
    - Exclude background methods and related work.
    - Exclude research findings that do not describe methodology.
    - Each claim must describe one distinct methodological detail.
    - Write short, plain-English descriptions.
    - Do not use LaTeX, equations, or backslashes.
    - Select the evidence block that best supports each claim.
    - Use only block IDs provided in the passage.
    - Do not reproduce source quotations.
    - Return valid JSON only.

    Required JSON format:

    {
        "claims": [
            {
                "description": "The authors scale attention scores.",
                "block_id": "B1"
            }
        ]
    }

    If no methodology is present, return {"claims": []}.
    """

    messages = [
        {
            "role": "system",
            "content": system_prompt
        },
        {
            "role": "user",
            "content": (
                f"Paper: {paper_title}\n\n"
                f"Evidence blocks:\n{formatted_blocks}"
            )
        }
    ]

    raw_response = llm.generate(
        messages,
        max_new_tokens=400
    )

    parsed = parse_claims(raw_response)

    claims = []

    if parsed is not None:
        for item in parsed["claims"]:

            evidence = blocks.get(item["block_id"])

            claims.append(
                MethodologyClaim(
                    description=item["description"],
                    evidence=evidence or "",
                    verified=evidence is not None
                )
            )

    return MethodologyExtraction(
        passage=passage,
        claims=claims,
        raw_response=raw_response,
        parse_success=parsed is not None
    )

def normalize_evidence_text(text: str) -> str:
    text = re.sub(r"(?<=\w)-\s*\n\s*(?=\w)", "", text)

    text = " ".join(text.split())

    return text

def verify_evidence(passage: str, evidence: str) -> bool:
    normalized_passage = normalize_evidence_text(passage)
    normalized_evidence = normalize_evidence_text(evidence)

    if not normalized_evidence:
        return False

    return normalized_evidence in normalized_passage

def verify_extraction_evidence (
        passage: str,
        fields: dict
    ) -> dict[str, bool | None]:
    results = {}

    for field, entry in fields.items():
        if entry is None:
            results[field] = None
        else:
            results[field] = verify_evidence(
                passage,
                entry["evidence"]
            )
    return results

def extract_paper_methodology(
        chunks: list[str],
        llm: LocalLLM,
        paper_title: str
) -> list[MethodologyExtraction]:

    results = []

    for chunk in chunks:
        extraction = extract_methodology(
            passage=chunk,
            llm=llm,
            paper_title=paper_title
        )

        results.append(extraction)

    return results

def number_passage_lines(passage: str) -> str:
    lines = passage.splitlines()

    return "\n".join(
        f"[L{i}] {line}"
        for i, line in enumerate(lines, start=1)
    )

def get_evidence_lines(
    passage: str,
    start_line: int,
    end_line: int
) -> str | None:

    lines = passage.splitlines()

    if start_line < 1 or end_line > len(lines):
        return None

    if end_line < start_line:
        return None

    return "\n".join(
        lines[start_line - 1:end_line]
    )

def escape_invalid_json_backslashes(text: str) -> str:
    valid_escapes = {'"', "\\", "/", "b", "f", "n", "r", "t", "u"}

    result = []
    i = 0

    while i < len(text):
        if text[i] == "\\" and i + 1 < len(text):
            next_char = text[i + 1]

            if next_char not in valid_escapes:
                result.append("\\\\")
            else:
                result.append("\\")

            i += 1
        else:
            result.append(text[i])

        i += 1

    return "".join(result)

def create_evidence_blocks(
    passage: str,
    lines_per_block: int = 4
) -> dict[str, str]:

    if lines_per_block <= 0:
        raise ValueError("lines_per_block must be positive")

    lines = passage.splitlines()
    blocks = {}

    for start in range(0, len(lines), lines_per_block):
        block_id = f"B{len(blocks) + 1}"

        blocks[block_id] = "\n".join(
            lines[start:start + lines_per_block]
        )

    return blocks

def format_evidence_blocks(blocks: dict[str, str]) -> str:
    return "\n\n".join(
        f"[{block_id}]\n{text}"
        for block_id, text in blocks.items()
    )