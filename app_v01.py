"""Research Landscape v0.1 — PostgreSQL-backed coverage explorer.

Run at the repository root: python -m streamlit run app_v01.py

Local Streamlit interface, offline draggable graph, no extra graph packages.
"""
from __future__ import annotations

import html
import hashlib
import re
import sys
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from research_landscape.storage.database import load_paper_from_database
from research_landscape.storage.paper_library import search_saved_papers
from research_landscape.processing.paper_pdf import acquire_paper_pdf
from research_landscape.processing.pdf_extraction import extract_pdf_text
from research_landscape.processing.component_analysis import analyze_coverage
from research_landscape.processing.comparison_reports import (
    latest_report, read_report, report_path, save_report,
)
from research_landscape.llm.local_model import LocalLLM


st.set_page_config(page_title="Research Landscape v0.1", page_icon="🔬", layout="wide")
st.markdown("""
<style>
.block-container {max-width: 1220px; padding-top: 2.0rem;}
.rl-eyebrow {letter-spacing: .14em; text-transform: uppercase; font-size: .74rem;
  font-weight: 750; color: #6792bd; margin-bottom: .5rem;}
.rl-lead {max-width: 760px; opacity: .78; font-size: 1.04rem; line-height: 1.55;}
.rl-small {font-size: .82rem; opacity: .72;}
[data-testid="stMetricValue"] {font-size: 1.7rem;}
</style>
""", unsafe_allow_html=True)


def graph_html(source_title: str, target_title: str, source_year: str, target_year: str, additions: int | None) -> str:
    """Generate a draggable directed two-node graph with no JS dependencies.

    Paper titles are escaped before insertion into HTML. Drag affects layout
    only; node direction and scientific meaning do not change.
    """
    s_title = html.escape(source_title[:110])
    t_title = html.escape(target_title[:110])
    s_year = html.escape(source_year)
    t_year = html.escape(target_year)
    label = "Not analyzed" if additions is None else f"{additions} candidate addition{'s' if additions != 1 else ''}"
    label = html.escape(label)
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1" />
<style>
* {{box-sizing:border-box}} html,body {{margin:0;background:transparent;font-family:Inter,Segoe UI,Arial,sans-serif;}}
#board {{height:326px;position:relative;overflow:hidden;border:1px solid #d9e4f0;
  border-radius:18px;background:radial-gradient(ellipse at 22% 15%, #ebf5ff 0%, transparent 54%),
  radial-gradient(ellipse at 95% 95%, #effaf7 0%, transparent 52%),#f8fafc;}}
#board::after {{content:"";position:absolute;inset:0;pointer-events:none;opacity:.32;
  background-image:radial-gradient(#9bb5cd .7px, transparent .7px);background-size:17px 17px;}}
#linebox {{position:absolute;inset:0;width:100%;height:100%;z-index:1;pointer-events:none;overflow:visible}}
.node {{position:absolute;z-index:2;width: min(43%,270px);min-width:165px;
  border:1px solid #cbdced;border-radius:15px;padding:15px 16px;
  background:white;box-shadow:0 11px 28px rgba(31,60,95,.13);user-select:none;
  cursor:grab;touch-action:none;color:#1f3146;}}
.node:active {{cursor:grabbing;box-shadow:0 14px 30px rgba(31,60,95,.22)}}
.node.target {{border-color:#a8cec1}}
.kind {{font-size:10px;font-weight:800;letter-spacing:.13em;text-transform:uppercase;color:#4c80ac;
  display:flex;align-items:center;gap:7px}}
.target .kind {{color:#36856d}}
.icon {{font-size:18px;line-height:1.4}}
.name {{font-size:14px;font-weight:760;line-height:1.28;margin:9px 0 8px;
  max-height:3.84em;overflow:hidden;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;}}
.year {{font-size:12px;color:#687b8d}}
.pill {{position:absolute;left:50%;top:18px;transform:translateX(-50%);z-index:3;
  background:white;border:1px solid #dbe6ee;color:#52677b;padding:7px 13px;
  border-radius:22px;font-size:11px;font-weight:720;white-space:nowrap;box-shadow:0 4px 12px #b8cada2e}}
.hint {{position:absolute;left:16px;bottom:10px;z-index:3;color:#708397;
 font-size:11px;pointer-events:none}}
@media(max-width:520px) {{.node {{padding:10px;min-width:0;width:43%;}} .name {{font-size:12px}}
 .pill {{top:8px;font-size:10px}} .hint{{font-size:9px}} }}
</style></head><body>
<div id="board" aria-label="Draggable graph connecting a source research paper to a target research paper">
<svg id="linebox" aria-hidden="true"><defs><marker id="head" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#6790aa" /></marker></defs>
<path id="link" stroke="#6790aa" stroke-width="2.5" fill="none" marker-end="url(#head)" /></svg>
<div class="pill">{label}</div>
<div class="node source" id="source" tabindex="0"><div class="kind"><span class="icon">📄</span>Source paper</div><div class="name">{s_title}</div><div class="year">{s_year}</div></div>
<div class="node target" id="target" tabindex="0"><div class="kind"><span class="icon">🎯</span>Target paper</div><div class="name">{t_title}</div><div class="year">{t_year}</div></div>
<div class="hint">Drag either card to rearrange · arrow always means source → target</div>
</div>
<script>
(() => {{
  const board = document.querySelector('#board');
  const source = document.querySelector('#source');
  const target = document.querySelector('#target');
  const path = document.querySelector('#link');
  let initialized = false;
  function move(el,x,y) {{
    x = Math.min(Math.max(6,x), board.clientWidth-el.offsetWidth-6);
    y = Math.min(Math.max(46,y), board.clientHeight-el.offsetHeight-28);
    el.style.left = Math.max(6,x)+'px';el.style.top = Math.max(46,y)+'px';
    draw();
  }}
  function rect(el) {{
    return {{x:el.offsetLeft,y:el.offsetTop,w:el.offsetWidth,h:el.offsetHeight}};
  }}
  function clip(r,ox,oy) {{
    const cx=r.x+r.w/2,cy=r.y+r.h/2,dx=ox-cx,dy=oy-cy;
    const t=1/Math.max(Math.abs(dx)/(r.w/2+8), Math.abs(dy)/(r.h/2+8),.0001);
    return [cx+dx*t,cy+dy*t];
  }}
  function draw() {{
    const a=rect(source),b=rect(target);
    const ac=[a.x+a.w/2,a.y+a.h/2],bc=[b.x+b.w/2,b.y+b.h/2];
    const s=clip(a,...bc),e=clip(b,...ac);
    path.setAttribute('d',`M ${{s[0]}} ${{s[1]}} L ${{e[0]}} ${{e[1]}}`);
  }}
  function initialize() {{
    if (!initialized) {{
      move(source,board.clientWidth*.08,board.clientHeight*.43);
      move(target,board.clientWidth*.92-target.offsetWidth,board.clientHeight*.43);
      initialized=true;
    }}
    draw();
  }}
  for(const el of [source,target]) {{
    let grab=null;
    el.addEventListener('pointerdown',e=>{{
      if(e.button !== 0 && e.pointerType !== 'touch') return;
      grab={{id:e.pointerId,startX:e.clientX,startY:e.clientY,left:el.offsetLeft,top:el.offsetTop}};
      el.setPointerCapture(e.pointerId);
    }});
    el.addEventListener('pointermove',e=>{{
      if(!grab || e.pointerId !== grab.id)return;
      move(el,grab.left+e.clientX-grab.startX,grab.top+e.clientY-grab.startY);
    }});
    for(const evt of ['pointerup','pointercancel','lostpointercapture'])
      el.addEventListener(evt,()=>{{grab=null}});
  }}
  if(typeof ResizeObserver !== 'undefined') new ResizeObserver(()=>{{
    if (initialized) {{for (const el of [source,target]) move(el,el.offsetLeft,el.offsetTop)}}
    else initialize();
  }}).observe(board);
  initialize();
}})();
</script></body></html>"""


def _paper_label(row: dict) -> str:
    title = str(row.get("title") or "Untitled").strip()
    year = row.get("year") or "n.d."
    return f"{title} ({year})"


def _paper_abstract(paper, label: str) -> None:
    title = getattr(paper, "title", "Untitled") or "Untitled"
    year = getattr(paper, "year", None) or "Unknown year"
    with st.expander(f"{label}: {title} ({year})"):
        st.write(getattr(paper, "abstract", None) or "No abstract in the database.")
        st.caption(f"Database ID: {paper.paper_id}")


def _get_pdf_options() -> list[Path]:
    folder = ROOT / "data" / "pdfs"
    if not folder.exists():
        return []
    return [p for p in sorted(folder.glob("*.pdf"))
            if not re.fullmatch(r"paper_[0-9a-f]{20}\.pdf", p.name)]


@st.cache_resource
def load_model() -> LocalLLM:
    return LocalLLM()


st.markdown('<div class="rl-eyebrow">Research Landscape / Version 0.1</div>', unsafe_allow_html=True)
st.title("Paper Coverage Explorer")
st.markdown(
    '<p class="rl-lead">Find saved papers, connect a source to a target, and examine '
    'potential research approaches the source could contribute. Move the paper cards '
    'around the canvas to explore their connection.</p>', unsafe_allow_html=True
)
st.caption("An exploratory tool: candidate additions are model-generated suggestions, not verified research gaps or numerical coverage scores.")

st.subheader("1 · Choose papers from your library")
left, right = st.columns(2, gap="large")
try:
    with left:
        target_search = st.text_input("Search target papers", placeholder="Try a title, DOI, or paper ID", key="target_search")
        target_rows = search_saved_papers(target_search, limit=100)
        target_choices = {str(r["paper_id"]): r for r in target_rows}
        target_id = st.selectbox(
            "Target paper", options=list(target_choices),
            format_func=lambda pid: _paper_label(target_choices[pid]),
            placeholder="No matching papers", key="target_choice",
        )
    with right:
        source_search = st.text_input("Search source papers", placeholder="Try a title, DOI, or paper ID", key="source_search")
        source_rows = search_saved_papers(source_search, limit=100)
        source_choices = {str(r["paper_id"]): r for r in source_rows}
        source_id = st.selectbox(
            "Source paper", options=[pid for pid in source_choices if pid != target_id],
            format_func=lambda pid: _paper_label(source_choices[pid]),
            placeholder="No matching papers", key="source_choice",
        )
except Exception as exc:
    st.error("Could not search PostgreSQL. Verify your .env database settings and that the server is running.")
    with st.expander("Technical details"):
        st.exception(exc)
    st.stop()

if not target_id or not source_id:
    st.info("Choose two different papers. Search by title if a paper isn't in the initial list.")
    st.stop()

try:
    target = load_paper_from_database(target_id)
    source = load_paper_from_database(source_id)
    if target is None or source is None:
        raise ValueError("A selected paper could not be retrieved from PostgreSQL.")
except Exception as exc:
    st.error("Could not load the selected paper metadata.")
    with st.expander("Technical details"):
        st.exception(exc)
    st.stop()

_paper_abstract(target, "Target")
_paper_abstract(source, "Source")

pdf_options = _get_pdf_options()
with st.expander("PDF sources · optional local files or uploads", expanded=False):
    st.caption(
        "Normally the app uses a cached PDF or downloads one from the saved PDF URL/arXiv ID. "
        "For your existing Attention and BERT files, choose them once here; they'll then be cached "
        "under the corresponding database paper IDs. Uploaded PDF takes precedence over a local selection."
    )
    pcol1, pcol2 = st.columns(2)
    with pcol1:
        target_override = st.selectbox(
            "Target PDF", options=[None] + pdf_options,
            format_func=lambda p: "Automatic (cache / download)" if p is None else p.name,
            key=f"target_pdf_override_{target_id}"
        )
        target_upload = st.file_uploader("Or upload target PDF", type=["pdf"], key=f"target_upload_{target_id}")
    with pcol2:
        source_override = st.selectbox(
            "Source PDF", options=[None] + pdf_options,
            format_func=lambda p: "Automatic (cache / download)" if p is None else p.name,
            key=f"source_pdf_override_{source_id}"
        )
        source_upload = st.file_uploader("Or upload source PDF", type=["pdf"], key=f"source_upload_{source_id}")

act_col, refresh_col = st.columns([2, 2], vertical_alignment="bottom")
with act_col:
    run = st.button("Analyze source → target", type="primary", use_container_width=True)
with refresh_col:
    refresh = st.checkbox("Run comparison again (ignore saved report)", value=False)

pair = (str(target.paper_id), str(source.paper_id))
report = None
pair_in_session = st.session_state.get("rl_pair")
if pair_in_session == pair:
    report = st.session_state.get("rl_report")
if report is None:
    report = latest_report(ROOT, *pair)

if run:
    try:
        with st.spinner("Locating PDFs, reading text, and preparing the research comparison..."):
            target_pdf, target_pdf_state = acquire_paper_pdf(
                target, ROOT, local_override=target_override,
                upload=target_upload.getvalue() if target_upload is not None else None,
            )
            source_pdf, source_pdf_state = acquire_paper_pdf(
                source, ROOT, local_override=source_override,
                upload=source_upload.getvalue() if source_upload is not None else None,
            )
            # Different database IDs can point to separate copies of the same PDF.
            # Refuse to analyze those as two distinct scientific papers.
            if (target_pdf.resolve() == source_pdf.resolve() or
                hashlib.sha256(target_pdf.read_bytes()).digest() ==
                    hashlib.sha256(source_pdf.read_bytes()).digest()):
                raise ValueError("Target and source contain the same PDF. Choose two different papers/files.")
            dest = report_path(ROOT, *pair, target_pdf, source_pdf)
            if dest.exists() and not refresh:
                report = read_report(dest)
                note = "Loaded saved comparison — no new model run."
            else:
                target_text = extract_pdf_text(target_pdf)
                source_text = extract_pdf_text(source_pdf)
                if len(target_text.strip()) < 500 or len(source_text.strip()) < 500:
                    raise ValueError("At least one PDF yielded less than 500 characters; scanned PDFs need OCR.")
                result = analyze_coverage(
                    load_model(), target_text, source_text,
                    cache_dir=ROOT / "data" / "component_cache",
                )
                report = save_report(dest, target, source, result, target_pdf, source_pdf)
                note = "Analysis saved. Repeating this pair will reuse the report unless you choose to rerun."
            st.session_state["rl_report"] = report
            st.session_state["rl_pair"] = pair
        st.success(f"{note} Target: {target_pdf_state}. Source: {source_pdf_state}.")
    except Exception as exc:
        st.error("The comparison could not be completed. Your saved papers and previous reports were not changed.")
        with st.expander("Error details and how to troubleshoot", expanded=True):
            st.exception(exc)
            st.write("If automatic PDF retrieval failed, open **PDF sources** and choose the existing file or upload a PDF.")
        # Do not inadvertently present an old pair report as a new run.

st.divider()
st.subheader("2 · Research connection")
additions = len(report.get("contributions", [])) if report else None
components.html(graph_html(
    str(source.title or "Source"), str(target.title or "Target"),
    str(getattr(source, "year", None) or "n.d."),
    str(getattr(target, "year", None) or "n.d."),
    additions,
), height=340, scrolling=False)

if not report:
    st.info("Choose **Analyze source → target** to see the source's potential coverage additions and evidence. Dragging the paper cards only changes their positions, not the direction of the comparison.")
    st.stop()

st.caption("Showing a saved report for this ordered source → target pair. New PDF versions require a new analysis. These counts are not calibrated coverage percentages.")
contributions = report.get("contributions", [])
already = report.get("already_covered", [])
undecided = report.get("undecided", [])
metrics = st.columns(3)
metrics[0].metric("Potential additions", len(contributions))
metrics[1].metric("Known overlap", len(already))
metrics[2].metric("Uncertain / unevaluated", len(undecided))

st.subheader("3 · Potential coverage additions")
if not contributions:
    st.info("No proposed additions in this run. This does not mean the target has complete coverage.")
else:
    tabs = st.tabs(["Methods", "Experiments", "Theory"])
    for tab, component in zip(tabs, ("methods", "experiments", "theory")):
        with tab:
            items = [c for c in contributions if c.get("component") == component]
            if not items:
                st.caption("No proposed additions in this category.")
            for item in items:
                status = item.get("relevance", "UNCERTAIN")
                label = item.get("approach", "Unnamed approach")
                with st.expander(f"{label}  ·  {status}", expanded=False):
                    st.write(item.get("explanation") or "No explanation provided.")
                    st.markdown("**Excerpt from source PDF**")
                    st.write(item.get("evidence") or "No excerpt provided.")
                    st.caption(
                        f"Section: {item.get('section', 'unknown')}  ·  "
                        f"Extraction: {item.get('origin', 'unknown')}  ·  "
                        "Model suggestion; applicability not verified"
                    )

with st.expander(f"Already represented in target ({len(already)})"):
    if already:
        for item in already:
            st.write("•", item)
    else:
        st.caption("No overlap explicitly identified.")
with st.expander(f"Uncertain or unreviewed ({len(undecided)})"):
    if undecided:
        for item in undecided:
            st.write("•", item)
    else:
        st.caption("No uncertain items were recorded. This is not a quality guarantee.")
with st.expander("Extraction details and reliability notes"):
    for who in ("target", "source"):
        items = report.get(who, [])
        st.markdown(f"**{who.title()} — {len(items)} extracted candidates**")
        for item in items:
            st.caption(f"[{item.get('component', '?')}] {item.get('label', '?')}  "
                       f"({item.get('section', '?')}; {item.get('origin', '?')})")
        for warning in report.get(f"{who}_warnings", []):
            st.warning(warning)
    st.info("A phrase matched in the PDF is evidence of a mention, not proof of the authors' contribution. Apparent gaps and relevance ratings should be checked against the papers before drawing scientific conclusions.")

st.caption("Research Landscape v0.1 · PostgreSQL paper library · On-demand PDF cache · Local Qwen coverage analysis · Draggable two-paper graph")
