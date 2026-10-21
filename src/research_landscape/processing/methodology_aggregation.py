from research_landscape.llm.local_model import LocalLLM
from research_landscape.processing.methodology_extraction import MethodologyExtraction

def collect_verified_claims(
        results: list[MethodologyExtraction],
) -> dict[str, list[dict]]:

    claims = {
        "method": [],
        "evaluation": [],
        "data": [],
        "limitations": [],
    }

    for chunk_index, result in enumerate(results):
        if result.fields is None:
            continue

        if result.evidence_verification is None:
            continue

        for field, entry in result.fields.items():
            if entry is None:
                continue

            if result.evidence_verification[field] is not True:
                continue

            claims[field].append({
                "value": entry["value"],
                "evidence": entry["evidence"],
                "chunk_index": chunk_index,
            })
    return claims

def format_claims(claims: dict[str, list[dict]]) -> str:
    sections = []

    for category, entries in claims.items():
        sections.append(f"{category.upper()}:")

        for entry in entries:
            sections.append(
                f"- [Chunk {entry['chunk_index']}]"
                f"{entry['value']}\n"
                f"  Evidence: {entry['evidence']}"
            )

        sections.append("")

    return "\n".join(sections)

def synthesize_methodology_profile(
    claims: dict[str, list[dict]],
    llm: LocalLLM,
    paper_title: str
) -> dict[str, str]:

    profile = {}

    for category, entries in claims.items():

        if not entries:
            profile[category] = "Insufficient verified evidence."
            continue

        evidence_text = "\n".join(
            f"[Chunk {entry['chunk_index']}] "
            f"Claim: {entry['value']}\n"
            f"Evidence: {entry['evidence']}"
            for entry in entries
        )

        messages = [
            {
                "role": "system",
                "content": (
                    "You summarize research methodology claims. "
                    "Use only the supplied evidence. "
                    "Do not introduce external facts. "
                    "Distinguish the authors' own methods from "
                    "background or related work. "
                    "Include chunk references for your statements. "
                    "If evidence is insufficient, say so. "
                    "Be concise."
                )
            },
            {
                "role": "user",
                "content": (
                    f"Paper: {paper_title}\n"
                    f"Category: {category}\n\n"
                    f"{evidence_text}\n\n"
                    f"Summarize the evidence for this category."
                )
            }
        ]

        profile[category] = llm.generate(
            messages,
            max_new_tokens=250
        )

    return profile

# def classify_method_claims(
#     claims: list[dict],
#         llm: LocalLLM
# ) -> dict[str, list[dict]]:
#     categories = {
#         "core_method": [],
#         "architecture": [],
#         "training": [],
#         "other": []
#     }
#
#     for claim in claims:
#         messages = [
#             {
#                 "role": "system",
#                 "content": (
#                     "Classify the following research methodology claim "
#                     "into exactly one category:\n"
#                     "core_method, architecture, training, other.\n\n"
#                     "core_method: The paper's central proposed method.\n"
#                     "architecture: Components of the proposed model.\n"
#                     "training: Optimization and training procedures.\n"
#                     "other: Related work or anything that does not fit.\n\n"
#                     "Return only the category name."
#                 )
#             },
#             {
#                 "role": "user",
#                 "content": (
#                     f"Claim: {claim['value']}\n"
#                     f"Evidence: {claim['evidence']}"
#                 )
#             }
#         ]
#
#         category = llm.generate(
#             messages,
#             max_new_tokens=20
#         ).strip().lower()
#
#         if category not in categories:
#             category = "other"
#
#         categories[category].append(claim)
#
#     return categories