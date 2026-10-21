"""Evidence-linked, conservative two-paper component comparison (v0.1).

No schema/database changes; LocalLLM and the existing PDF extractor are reused.
This is exploratory research coverage, not a quality assessment.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from research_landscape.llm.local_model import LocalLLM
from research_landscape.processing.text_chunking import chunk_text

VERSION = "coverage-v0.1-5"
COMPONENTS = ("methods", "experiments", "theory")
MAX_PASSAGES = {"methods": 11, "experiments": 6, "theory": 2}
MAX_COMPARISONS = 15

# PDF text extractors often put numbered section headings on separate lines.
HEADING = re.compile(
    r"^\s*(?P<number>\d+(?:\.\d+){0,3})\.?\s+(?P<title>[A-Za-z][A-Za-z0-9 ,:()&/\-]{1,85})\s*$"
)
PLAIN_HEADINGS = {"abstract", "references", "bibliography", "acknowledgments", "acknowledgements"}
SKIP_SECTIONS = ("abstract", "introduction", "related work", "background", "conclusion", "acknowledg", "appendix", "future work", "limitation")
EXPERIMENT_SECTIONS = ("experiment", "evaluation", "result", "ablation", "benchmark", "performance", "empirical", "glue", "squad", "dataset", "question answering", "inference task", "translation", "parsing")
THEORY_SECTIONS = ("theory", "theorem", "proof", "convergence", "complexity bound", "generalization bound")
GENERIC_LABELS = {"none", "methods", "method", "experiments", "experiment", "theory", "training", "fine-tuning", "evaluation", "results", "model", "bert", "attention", "model architecture", "implementation details", "training details", "discussion", "summary"}


@dataclass
class Approach:
    component: str
    label: str
    evidence: str
    section: str
    origin: str = "model"


@dataclass
class Contribution:
    component: str
    approach: str
    relevance: str
    explanation: str
    evidence: str
    section: str
    origin: str = "model"


@dataclass
class CoverageComparison:
    target: list[Approach] = field(default_factory=list)
    source: list[Approach] = field(default_factory=list)
    contributions: list[Contribution] = field(default_factory=list)
    undecided: list[str] = field(default_factory=list)
    already_covered: list[str] = field(default_factory=list)
    target_warnings: list[str] = field(default_factory=list)
    source_warnings: list[str] = field(default_factory=list)


def _clean(text: str) -> str:
    """Normalize PDF whitespace and occasional line-break hyphenation."""
    text = text.replace("\u00ad", "")
    text = re.sub(r"(?<=\w)-\s*\n\s*(?=\w)", "-", text)
    return re.sub(r"\s+", " ", text).strip()


def _sections(text: str) -> list[tuple[str, str, str | None]]:
    """Return (heading, body, component), inheriting numbered parent context.

    A heading like 4.2 SWAG belongs to 4 Experiments, even though "SWAG"
    doesn't itself say "experiment". This prevents benchmark tables being
    incorrectly extracted as *methods*.
    """
    lines = text.splitlines()
    found: list[tuple[str, str, str | None]] = []
    title, body = "Front matter", []
    current_type: str | None = None
    current_excluded = True
    parent_types: dict[str, str] = {}
    blocked_prefixes: set[str] = set()
    idx = 0

    while idx < len(lines):
        stripped = lines[idx].strip()
        numbered = HEADING.fullmatch(stripped)
        heading = numbered.group("title").strip() if numbered else None
        number = numbered.group("number") if numbered else None
        if stripped.casefold() in PLAIN_HEADINGS:
            heading = stripped
        if heading is None and re.fullmatch(r"\d+(?:\.\d+){0,3}\.?", stripped):
            if idx + 1 < len(lines):
                next_line = lines[idx + 1].strip()
                if (re.fullmatch(r"[A-Za-z][A-Za-z0-9 ,:()&/\-]{1,85}", next_line)
                        and not next_line.endswith((".", ","))):
                    number, heading = stripped.rstrip("."), next_line
                    idx += 1
        if heading and re.match(r"^(?:table|figure|fig\.)\s*\d+", heading, re.I):
            heading = None

        if heading is not None:
            if body and not current_excluded and current_type:
                found.append((title, "\n".join(body).strip(), current_type))
            if heading.casefold() in {"references", "bibliography"}:
                return found

            # The closest numbered ancestor controls component context unless
            # this heading explicitly describes experiments or theory.
            ancestor_type = None
            if number and "." in number:
                prefix = number.rsplit(".", 1)[0]
                ancestor_type = parent_types.get(prefix)
            explicit = _explicit_section_type(heading)
            inferred = explicit or ancestor_type or "methods"
            if number:
                parent_types[number] = inferred
                blocked_prefixes = {
                    prefix for prefix in blocked_prefixes
                    if number == prefix or number.startswith(prefix + ".")
                }
                if any(term in heading.casefold() for term in SKIP_SECTIONS):
                    blocked_prefixes.add(number)
                current_excluded = any(
                    number == prefix or number.startswith(prefix + ".")
                    for prefix in blocked_prefixes
                )
            else:
                current_excluded = any(term in heading.casefold() for term in SKIP_SECTIONS)
            title, body, current_type = heading, [], inferred
        else:
            body.append(lines[idx])
        idx += 1

    if body and not current_excluded and current_type:
        found.append((title, "\n".join(body).strip(), current_type))
    return found


def _explicit_section_type(title: str) -> str | None:
    name = title.casefold()
    if any(word in name for word in EXPERIMENT_SECTIONS):
        return "experiments"
    if any(word in name for word in THEORY_SECTIONS):
        return "theory"
    return None


def _without_bibliography(text: str) -> str:
    """Conservatively discard the references tail, even without numbered headings."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.strip().casefold() in {"references", "bibliography"} and i > len(lines) // 3:
            return "\n".join(lines[:i])
    return text


def _fallback_passages(text: str) -> dict[str, list[tuple[str, str]]]:
    """Never silently treat unrecognized headings as an empty paper."""
    without_refs = _without_bibliography(text)
    # Avoid author/affiliation blocks when headings cannot be parsed.
    chunks = [c for c in chunk_text(without_refs, max_chars=1250) if len(c.strip()) >= 90]
    return {
        "methods": [("Unclassified section", c) for c in chunks[:MAX_PASSAGES["methods"]]],
        "experiments": [("Unclassified section", c) for c in chunks[5:5 + MAX_PASSAGES["experiments"]]],
        "theory": [],
    }



def _passages(text: str) -> dict[str, list[tuple[str, str]]]:
    groups: dict[str, list[list[tuple[str, str]]]] = {c: [] for c in COMPONENTS}
    sections = _sections(text)
    for title, body, component in sections:
        if component is None:
            continue
        chunks = [c for c in chunk_text(body, max_chars=1250) if len(c.strip()) >= 90]
        if chunks:
            groups[component].append([(title, c) for c in chunks])

    selected: dict[str, list[tuple[str, str]]] = {c: [] for c in COMPONENTS}
    for component in COMPONENTS:
        section_groups = groups[component]
        depth = 0
        while len(selected[component]) < MAX_PASSAGES[component]:
            added = False
            for section_chunks in section_groups:
                if depth < len(section_chunks):
                    selected[component].append(section_chunks[depth])
                    added = True
                    if len(selected[component]) >= MAX_PASSAGES[component]:
                        break
            if not added:
                break
            depth += 1

    if not any(selected.values()):
        print(f"  WARNING: Could not identify research sections ({len(sections)} text blocks). Using text fallback.")
        selected = _fallback_passages(text)
    print("  Section sample:", [(title, category) for title, _, category in sections[:12]])
    print("  Selected passages:", {k: len(v) for k, v in selected.items()})
    return selected


def _labels(raw: str) -> list[str]:
    raw = raw.strip()
    if raw.startswith("["):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [s for s in parsed if isinstance(s, str)]
        except (ValueError, TypeError):
            pass
    result = []
    for line in raw.splitlines():
        line = re.sub(r"^\s*(?:[-*•]\s*|\d+[.)]\s*)", "", line).strip()
        line = line.strip(" `\"'.,;")
        if line:
            result.append(line)
    return result


def _approach_from_label(component: str, proposed: str, section: str, passage: str) -> Approach | None:
    label = _clean(proposed)
    if not 4 <= len(label) <= 90 or label.casefold() in GENERIC_LABELS:
        return None
    if len(label.split()) > 12:
        return None
    # Reject chopped-off prose presented as an approach label.
    if re.match(r"^(?:we|our|the authors|this paper|in this|it is|table \d+|figure \d+)\b", label, re.I):
        return None
    if re.search(r"[.!?]$", label):
        return None
    # The claimed approach must be an *actual string in the PDF text*.
    context = _clean(passage)
    match = re.search(re.escape(label), context, flags=re.IGNORECASE)
    if not match:
        return None
    matched_text = match.group()
    start = max(0, match.start() - 95)
    end = min(len(context), match.end() + 125)
    return Approach(component, matched_text, context[start:end], section)


def _evidence_fallback(component: str, section: str, passage: str) -> list[Approach]:
    """Extract at most one *verbatim* author-action sentence when Qwen's format fails.

    These are labelled provisional: matching text is not proof of author attribution.
    """
    if component == "theory":
        cue = re.compile(r"\b(?:we (?:prove|derive|establish|show)|theorem|lemma|proof|upper bound|lower bound)\b", re.I)
    elif component == "experiments":
        cue = re.compile(r"\b(?:we (?:evaluate|test|compare|conduct|perform|report|train)|our experiments|experiments on|benchmark|ablation)\b", re.I)
    else:
        cue = re.compile(r"\b(?:we (?:propose|introduce|use|employ|design|train|pre-train|apply|develop)|our (?:model|method|approach|architecture)|we call our)\b", re.I)
    normalized = _clean(passage)
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z])", normalized)
    for sentence in sentences:
        if cue.search(sentence) and 35 <= len(sentence) <= 700:
            short = sentence[:120].strip()
            if len(short) > 85:
                short = short[:85].rsplit(" ", 1)[0].rstrip(" ,:;")
            if len(short.split()) < 3:
                continue
            # A short exact prefix of evidence is a candidate description, not
            # a claim that Qwen verified the paper's intent.
            return [Approach(component, short, sentence[:300], section, origin="heuristic_sentence")]
    return []


def _task_heading_candidates(component: str, section: str, passage: str) -> list[Approach]:
    """Recover explicit task/goal labels even when small LLM omits them.

    Example of the generic pattern: 'Task #1: Masked LM (MLM)'.
    Only exact text from the passage can be emitted. These are candidate
    headings, NOT semantic verification that the authors used the objective.
    """
    if component != "methods":
        return []
    found: list[Approach] = []
    pattern = re.compile(
        r"(?im)(?:^|\n)\s*(?:task\s*#?\d+|training objective\s*#?\d*)\s*:\s*"
        r"(?P<label>[A-Za-z][^\n.!?;:]{3,65})"
    )
    for match in pattern.finditer(passage):
        label = match.group("label").strip()
        # Often a heading ends with '(ABBR)' and the paragraph follows it.
        paren = re.match(r"^(.{3,55}?\([A-Za-z0-9-]{2,12}\))", label)
        if paren:
            label = paren.group(1)
        elif len(label.split()) > 7:
            label = " ".join(label.split()[:7])
        label = label.strip(" -—,.")
        if len(label) < 5:
            continue
        context = _clean(passage)
        found.append(Approach(
            component, label,
            context[max(0, context.casefold().find(label.casefold()) - 65):][:300],
            section, origin="task_heading",
        ))
    return found


def _table_noise(approach: Approach) -> bool:
    """Remove result-table headings/baseline names masquerading as methods."""
    label = approach.label.lower()
    if re.search(r"\b(?:test results|dev results|leaderboard|scores?)\b", label):
        return True
    if approach.component == "methods" and re.search(
        r"\b(?:benchmark|test results|dev set|acc(?:uracy)?|f1|glue|mnli|qnli|mrpc|sst-2)\b", label
    ):
        return True
    # A context made mostly of numeric scores, not explanatory prose.
    evidence = approach.evidence
    if evidence and len(re.findall(r"\d", evidence)) > len(evidence) * 0.20:
        return True
    return False


def _semantic_tokens(label: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", label.casefold())
    # Generic modifiers shouldn't turn an existing encoder into a novel method.
    generic = {"transformer", "model", "architecture", "method", "approach", "based", "mechanism", "layer", "layers", "network"}
    return {w.rstrip("s") if len(w) > 4 else w for w in words if w not in generic}


def _already_represented(candidate: Approach, target: list[Approach]) -> bool:
    key = _semantic_tokens(candidate.label)
    if not key:
        return False
    for item in target:
        if item.component != candidate.component:
            continue
        other = _semantic_tokens(item.label)
        # Subset equality is restricted to reasonably specific terminology.
        if key == other or (len(key) >= 2 and key.issubset(other)) or (
            len(key) == 1 and key == other
        ):
            return True
    return False


def _extract_one(llm: LocalLLM, component: str, section: str, passage: str) -> tuple[list[Approach], bool]:
    instruction = (
        "Identify at most three specific research approaches ACTUALLY USED by the authors "
        "in the supplied passage. Ignore previous studies, citations, and future work. "
        "Copy each name as an EXACT contiguous phrase from the supplied text, "
        "with 2 to 8 words where possible. Return one phrase per line, "
        "no explanations and no JSON. Return NONE if nothing qualifies. "
        "For methods, identify architecture, algorithms, training objectives or procedures. "
        "For experiments, identify datasets, benchmarks, comparisons or evaluation procedures "
        "actually carried out. For theory, include only actual theorems, bounds, "
        "proofs or formal analyses, not mathematically described architectures."
    )
    message = f"Component: {component}\nSection: {section}\nPassage:\n{section}\n{passage}"
    output = llm.generate([
        {"role": "system", "content": instruction},
        {"role": "user", "content": message},
    ], max_new_tokens=115)
    approaches = []
    for phrase in _labels(output)[:4]:
        item = _approach_from_label(component, phrase, section, passage)
        if item is not None:
            approaches.append(item)
    if approaches:
        return approaches, False
    return _evidence_fallback(component, section, passage), True


def _key(phrase: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", phrase.lower())


def extract_paper_components(llm: LocalLLM, text: str, name: str = "paper", cache_dir: Path | str = "data/component_cache") -> tuple[list[Approach], list[str]]:
    cache_dir = Path(cache_dir)
    fingerprint = hashlib.sha256((VERSION + text).encode("utf-8")).hexdigest()[:20]
    cache_path = cache_dir / f"{fingerprint}.json"
    if cache_path.exists():
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        print(f"Using cached components for {name} ({len(data['approaches'])} approaches)")
        return [Approach(**x) for x in data["approaches"]], data.get("warnings", [])

    selected = _passages(text)
    count = sum(len(group) for group in selected.values())
    print(f"Extracting {name}: {count} selected passages")
    approaches: list[Approach] = []
    warnings: list[str] = []
    seen: set[tuple[str, str]] = set()
    model_count, fallback_count = 0, 0
    for component in COMPONENTS:
        for index, (section, passage) in enumerate(selected[component], start=1):
            print(f"  {component}: {index}/{len(selected[component])} — {section}")
            try:
                extracted, fallback_used = _extract_one(llm, component, section, passage)
            except Exception as exc:
                warnings.append(f"{component}/{section}: {type(exc).__name__}: {exc}")
                extracted = _evidence_fallback(component, section, passage)
                fallback_used = True
            if fallback_used:
                fallback_count += bool(extracted)
            else:
                model_count += len(extracted)
            extracted.extend(_task_heading_candidates(component, section, passage))
            for approach in extracted:
                if _table_noise(approach):
                    continue
                signature = (approach.component, _key(approach.label))
                if signature not in seen:
                    seen.add(signature)
                    approaches.append(approach)
    # Scan full methods sections for explicit numbered task/objective headings.
    # Important: an objective can fall beyond the selected passage budget.
    for section, body, component in _sections(text):
        if component != "methods":
            continue
        for approach in _task_heading_candidates(component, section, body):
            signature = (approach.component, _key(approach.label))
            if signature not in seen:
                seen.add(signature)
                approaches.append(approach)
    usable = sum(a.origin in {"model", "task_heading"} for a in approaches)
    print(f"  Extracted {len(approaches)} distinct phrases ({usable} model/task-heading candidates, "
          f"{len(approaches) - usable} provisional).")
    if fallback_count:
        warnings.append(f"{fallback_count} items came from provisional evidence-sentence fallback, not validated model labels.")
    if not approaches:
        warnings.append("No candidate phrases extracted. Check PDF extraction and section-selection diagnostics.")
    else:
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps({
            "version": VERSION,
            "approaches": [asdict(a) for a in approaches],
            "warnings": warnings,
        }, indent=2, ensure_ascii=False), encoding="utf-8")
    return approaches, warnings


def _topic_context(text: str) -> str:
    # The research-section extractor intentionally excludes the abstract;
    # recover it directly so relevance judgments have the target's topic.
    match = re.search(r"(?im)^\s*(?:(?:\d+(?:\.\d+)*)\s+)?abstract\s*$", text)
    if match:
        return _clean(text[match.end():match.end() + 1700])[:850]
    return _clean(text)[:850]


def _review_candidate(llm: LocalLLM, candidate: Approach, target: list[Approach], target_context: str) -> tuple[str, str]:
    target_labels = [a.label for a in target if a.component == candidate.component]
    prompt = (
        "Assess a potential contribution from SOURCE to TARGET. "
        "A source approach adds coverage only when it is not already represented "
        "by an equivalent target approach AND plausibly applies to the target topic. "
        "Reply with exactly one status followed by a vertical bar and a brief reason. "
        "Possible statuses: HIGH, MEDIUM, LOW, ALREADY, UNRELATED, UNCERTAIN. "
        "Use HIGH only for directly applicable additions, MEDIUM for reasonably adaptable "
        "additions, LOW for speculative transfer, ALREADY for equivalent existing coverage, "
        "UNRELATED for no sensible transfer, UNCERTAIN if information is insufficient. "
        "Do not reverse source and target; do not invent paper content."
    )
    data = (
        f"TARGET research context: {target_context}\n"
        f"TARGET's existing {candidate.component}: {json.dumps(target_labels[:18], ensure_ascii=False)}\n"
        f"SOURCE proposed {candidate.component} approach: {candidate.label}\n"
        f"SOURCE PDF evidence: {candidate.evidence}"
    )
    response = llm.generate([
        {"role": "system", "content": prompt},
        {"role": "user", "content": data}
    ], max_new_tokens=85).strip()
    match = re.match(r"^\s*(HIGH|MEDIUM|LOW|ALREADY|UNRELATED|UNCERTAIN)\b\s*(?:\|\s*(.*))?", response, re.I | re.S)
    if match is None:
        return "UNCERTAIN", "Model returned an unrecognized judgment."
    reason = (match.group(2) or "No explanation provided.").splitlines()[0].strip()[:350]
    return match.group(1).upper(), reason


def analyze_coverage(
    llm: LocalLLM,
    target_text: str,
    source_text: str,
    cache_dir: Path | str = "data/component_cache",
) -> CoverageComparison:
    target, target_warnings = extract_paper_components(llm, target_text, "target", cache_dir)
    source, source_warnings = extract_paper_components(llm, source_text, "source", cache_dir)
    output = CoverageComparison(target=target, source=source,
                                target_warnings=target_warnings,
                                source_warnings=source_warnings)
    current = {component: {_key(a.label) for a in target if a.component == component}
               for component in COMPONENTS}
    target_context = _topic_context(target_text)
    if not target or not source:
        output.undecided.append("Comparison skipped: at least one paper has no extracted approaches.")
        return output
    checked = 0
    for source_item in source:
        # Fallback sentences aren't defined research approaches. Keep them in the
        # diagnostic extract, but don't score them as contributions.
        if source_item.origin not in {"model", "task_heading"}:
            continue
        # Python enforces source provenance and rejects exact overlap before any LLM judgment.
        if (_key(source_item.label) in current[source_item.component]
                or _already_represented(source_item, target)):
            output.already_covered.append(source_item.label)
            continue
        if _table_noise(source_item):
            continue
        if checked >= MAX_COMPARISONS:
            output.undecided.append(f"Not judged (comparison limit): {source_item.label}")
            continue
        checked += 1
        status, reason = _review_candidate(llm, source_item, target, target_context)
        print(f"  Comparing {checked}: {source_item.label} -> {status}")
        if status in {"HIGH", "MEDIUM"}:
            output.contributions.append(Contribution(
                component=source_item.component,
                approach=source_item.label,
                relevance=status,
                explanation=reason,
                evidence=source_item.evidence,
                section=source_item.section,
                origin=source_item.origin,
            ))
        elif status == "UNCERTAIN":
            output.undecided.append(f"{source_item.label}: {reason}")
    return output
