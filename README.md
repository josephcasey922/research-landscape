# Research Landscape v0.1 — database-backed two-paper coverage explorer

**Install only the four new Python files**; your existing code stays in place.

```text
research-landscape/
├── app_v01.py                                          NEW
├── src/research_landscape/
│   ├── storage/
│   │   ├── database.py                                 EXISTING (unchanged)
│   │   └── paper_library.py                            NEW
│   ├── processing/
│   │   ├── component_analysis.py                        EXISTING (unchanged)
│   │   ├── text_chunking.py                             EXISTING (unchanged)
│   │   ├── pdf_extraction.py                            EXISTING (unchanged)
│   │   ├── paper_pdf.py                                 NEW
│   │   └── comparison_reports.py                        NEW
│   └── llm/local_model.py                              EXISTING (unchanged)
└── data/pdfs/                                          EXISTING
```

The ZIP includes optional `tests/test_release.py`. You can ignore it when installing.

## Run

1. Unzip the archive **into the root of the existing `research-landscape` project**, preserving the folders. No existing project files are replaced.
2. Start PostgreSQL if it's not running. This app uses your existing `.env` credentials, `papers` table, `get_connection()`, and `load_paper_from_database()`.
3. In the PyCharm PowerShell terminal, from the project root, run:

   ```powershell
   python -m streamlit run app_v01.py
   ```

You do **not** need to set `PYTHONPATH` for this app: it adds your `src` folder at startup. No new TOML/configuration file is needed. Your existing Streamlit, psycopg, dotenv, PyMuPDF, PyTorch, and Transformers installations are reused; the draggable graph needs **no additional package** or internet access.

## First paper comparison

1. In **Search target papers**, type part of the title `Attention Is All You Need` and select the matching paper from your PostgreSQL database.
2. In **Search source papers**, type `BERT` and select BERT.
3. Open **PDF sources**. If PDFs are already in `data/pdfs`, select their local filenames (e.g., `attention.pdf` and `bert.pdf`). If not, leave **Automatic** to try your database PDF URL/arXiv ID, or upload PDFs directly.
4. Click **Analyze source → target**.
5. Inspect the suggested additions, source PDF excerpts, identified overlap, and the draggable graph.

The first explicit local-file assignment is copied to a stable paper-ID cache. Later comparisons reuse the cached PDFs. Per-paper components are cached using your existing `data/component_cache`; complete ordered-pair results are stored in `data/coverage_reports`. If you compare the same pair again with unchanged PDFs, no new model run is needed unless you check **Run comparison again**.

## What v0.1 can and cannot do

**Included:** searchable paper selection from PostgreSQL; source→target order; on-demand PDF download; local PDF assignments and PDF uploads; caching; existing Qwen component analysis; evidence excerpts; three-way reporting of additions, existing overlap, and uncertain/unreviewed material; draggable paper cards.

**Not yet included:** multiple-node clusters, saving graph positions, graph edits that alter the research analysis, authoring a paper, or scientifically calibrated coverage percentages. The draggable graph visualizes the two-paper comparison; it doesn't persist node positions across reruns.

**Reliability warning:** The underlying component analysis has produced mistaken classifications and questionable relevance judgments on Attention/BERT. This is still a research prototype. Treat proposed additions as hypotheses to investigate, *not* verified scientific gaps; a quote proves the term was mentioned, not necessarily that the paper's authors contributed the approach. The app intentionally reports counts, not percentages.

## Troubleshooting

- **No matching papers:** Search a shorter part of the title or a paper ID. The initial dropdown shows up to 100 high-citation papers; searching filters across the whole database.
- **PostgreSQL error:** Check that your server is running and your existing `.env` `DB_*` variables are correct.
- **PDF unavailable:** Choose one from `data/pdfs` in **PDF sources**, or upload it. This works even when the saved URL is missing or paywalled.
- **Incorrect PDF association:** Select the correct local PDF or upload for that paper and rerun. An explicit file replaces its cached PDF.
- **Model memory / time issue:** Continue using the exact `LocalLLM` setup that worked in the earlier comparison. Report caching avoids repeating the same full analysis.
- **Unexpected old output:** Check **Run comparison again (ignore saved report)**. Per-paper component extraction is still separately cached; its cache key is controlled by `component_analysis.VERSION`.

## Automated checks

The included optional tests don't need PostgreSQL or Streamlit:

```powershell
python -m unittest discover -s tests -v
```

Tests cover query parameterization, HTML title escaping, manual PDF mapping and caching, invalid upload handling, report directionality, and cache invalidation when a PDF changes. The graph was also browser-rendered and its drag interaction checked with a headless browser. These checks do not validate the scientific accuracy of Qwen's comparisons against your real PDFs.
