from pathlib import Path
from transformers import AutoTokenizer
from research_landscape.processing.pdf_extraction import extract_pdf_text

PROJECT_ROOT = Path(__file__).resolve().parents[1]


PDF_PATH = (PROJECT_ROOT / "data" / "pdfs" /

            "c58bdb5a22eef5020abd9c2f1ea04462ca1def227abd55ca8d7b5e3239e32f09.pdf")

text = extract_pdf_text(PDF_PATH)

tokenizer = AutoTokenizer.from_pretrained(
    "Qwen/Qwen2.5-3B-Instruct"
)

tokens = tokenizer.encode(text, add_special_tokens=False)

print(f"Characters: {len(text):,}")
print(f"Tokens: {len(tokens):,}")
print(f"Characters per token: {len(text) / len(tokens):.2f}")

print(tokens[:20])

for token_id in tokens[:20]:
    print(token_id, repr(tokenizer.decode([token_id])))