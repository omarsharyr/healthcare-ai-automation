"""Conservative pattern matching for synthetic MVP data, not full de-identification."""
import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class RedactionResult:
    text: str = field(repr=False)
    counts: dict[str, int]


class PHIRedactionService:
    _patterns = (
        ("PATIENT_ID", re.compile(r"\b(?:PAT|PATIENT|MRN)[-:#\s]*[A-Z0-9]*\d[A-Z0-9-]*\b", re.I)),
        ("CLAIM_ID", re.compile(r"\b(?:CLM|CLAIM(?:\s+(?:ID|NUMBER|NO\.?))?)[-:#\s]*[A-Z0-9]*\d[A-Z0-9-]*\b", re.I)),
        ("EMAIL", re.compile(r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Z]{2,}\b", re.I)),
        # Redact numeric dates conservatively, including unlabelled DOB-like dates.
        ("DOB", re.compile(r"\b(?:\d{4}[-/.]\d{1,2}[-/.]\d{1,2}|\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4})\b")),
        ("DOB", re.compile(r"(?i)(?<=DOB )\d{1,2}\s+[A-Z]+\s+\d{4}\b")),
        ("PHONE", re.compile(r"(?<!\w)(?:\+?\d{1,3}[\s.-]?)?(?:\(\d{3}\)|\d{3})[\s.-]?\d{3}[\s.-]?\d{4}(?:\s*(?:ext\.?|x)\s*\d+)?(?!\w)", re.I)),
    )
    _named_dob = re.compile(
        r"\b(DOB|date\s+of\s+birth)\s*[:=]?\s*(?:[A-Z]+\s+\d{1,2},?\s+\d{4}|\d{1,2}\s+[A-Z]+\s+\d{4})\b", re.I,
    )

    def redact(self, text: str, patient_reference: str | None = None) -> RedactionResult:
        counts: dict[str, int] = {}
        if patient_reference:
            text, count = re.subn(re.escape(patient_reference), "[PATIENT_ID]", text, flags=re.I)
            if count:
                counts["PATIENT_ID"] = count
        text, count = self._named_dob.subn(lambda m: f"{m.group(1)} [DOB]", text)
        if count:
            counts["DOB"] = count
        for name, pattern in self._patterns:
            text, count = pattern.subn(f"[{name}]", text)
            if count:
                counts[name] = counts.get(name, 0) + count
        return RedactionResult(text=text, counts=counts)
