def chunk_text(text: str, max_chars: int = 1500) -> list[str]:
    if max_chars <= 0:
        raise ValueError('max_chars must be > 0')
    paragraphs = text.split("\n\n")

    chunks = []
    current_chunk = ""

    for paragraph in paragraphs:
        paragraph = paragraph.strip()

        if not paragraph:
            continue

        if len(paragraph) > max_chars:
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = ""

            for start in range(0, len(paragraph), max_chars):
                chunks.append(paragraph[start:start + max_chars])

            continue

        if current_chunk and len(current_chunk) + len(paragraph) + 2> max_chars:
            chunks.append(current_chunk)
            current_chunk = ""

        if current_chunk:
            current_chunk += "\n\n"

        current_chunk += paragraph

    if current_chunk:
        chunks.append(current_chunk)
    return chunks