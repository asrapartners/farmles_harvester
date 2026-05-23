import hashlib
import re


def normalize_md_block(text: str) -> str:
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)  # images before links
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"^#+\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"[*_`>~]", "", text)
    return re.sub(r"\s+", " ", text.strip())


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def build_md_fingerprint(
    contents: list[str],
    threshold: float = 0.8,
    min_files: int = 3,
) -> frozenset[str]:
    if len(contents) < min_files:
        return frozenset()

    hash_counts: dict[str, int] = {}

    for content in contents:
        file_hashes: set[str] = set()
        for block in re.split(r"\n{2,}", content):
            normalized = normalize_md_block(block)
            if normalized:
                file_hashes.add(_hash(normalized))
        for h in file_hashes:
            hash_counts[h] = hash_counts.get(h, 0) + 1

    n = len(contents)
    return frozenset(h for h, count in hash_counts.items() if count / n >= threshold)


def strip_md_fingerprint(content: str, fingerprint: frozenset[str]) -> str:
    if not fingerprint:
        return content.strip()

    kept = []
    for block in re.split(r"\n{2,}", content):
        normalized = normalize_md_block(block)
        if not normalized or _hash(normalized) not in fingerprint:
            kept.append(block)

    return "\n\n".join(kept).strip()
