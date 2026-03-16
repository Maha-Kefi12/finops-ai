"""
Text formatting utilities — strips emojis, symbols, and special characters
from all LLM and agent output so the UI is clean and professional.
"""

import re


# Comprehensive regex that matches most emoji and symbol unicode ranges
_EMOJI_PATTERN = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F680-\U0001F6FF"  # transport & map
    "\U0001F700-\U0001F77F"  # alchemical
    "\U0001F780-\U0001F7FF"  # geometric extended
    "\U0001F800-\U0001F8FF"  # supplemental arrows-c
    "\U0001F900-\U0001F9FF"  # supplemental symbols
    "\U0001FA00-\U0001FA6F"  # chess symbols
    "\U0001FA70-\U0001FAFF"  # symbols extended-a
    "\U00002702-\U000027B0"  # dingbats
    "\U000024C2-\U0001F251"  # enclosed characters
    "\U0000FE0F"             # variation selector
    "\U0000200D"             # zero width joiner
    "\U00002600-\U000026FF"  # misc symbols
    "\U00002700-\U000027BF"  # dingbats
    "\U0000231A-\U0000231B"  # watch/hourglass
    "\U00002328"             # keyboard
    "\U000023CF"             # eject
    "\U000023E9-\U000023F3"  # media controls
    "\U000023F8-\U000023FA"  # media controls
    "\U0000200B"             # zero width space
    "]+",
    flags=re.UNICODE,
)

# Also strip leading symbol markers like ⚠️, 🔴, ✅, 🎯 followed by space
_LEADING_SYMBOL = re.compile(r"^\s*" + _EMOJI_PATTERN.pattern + r"\s*", flags=re.UNICODE | re.MULTILINE)


def strip_latex(text: str) -> str:
    """Convert LaTeX notation to clean display text (no backslashes/symbols)."""
    if not text or not isinstance(text, str):
        return text or ""
    # \text{...} -> contents only
    text = re.sub(r"\\text\s*\{([^}]*)\}", r"\1", text)
    # Common LaTeX -> plain
    text = re.sub(r"\\times\s*", " x ", text)
    text = re.sub(r"\\cdot\s*", " ", text)
    text = re.sub(r"\\quad\s*", " ", text)
    text = re.sub(r"\\,", " ", text)
    text = re.sub(r"\\\$", "$", text)
    # Inline math \( ... \) -> replace with cleaned inner text
    def _replace_inline_math(match):
        inner = match.group(1)
        inner = re.sub(r"\\times\s*", " x ", inner)
        inner = re.sub(r"\\text\s*\{([^}]*)\}", r"\1", inner)
        inner = re.sub(r"\\,", " ", inner)
        return inner.strip()
    text = re.sub(r"\\\(([^)]*)\)", _replace_inline_math, text)
    # Display math \[ ... \]
    text = re.sub(r"\\\[.*?\\\]", "", text, flags=re.DOTALL)
    # $$ ... $$
    text = re.sub(r"\$\$[^$]*\$\$", "", text)
    # Remove backslash-escaped single chars
    text = re.sub(r"\\([^a-zA-Z{])", r"\1", text)
    return text


def strip_symbols(text) -> str:
    """Remove all emoji and special symbol characters from text.
    Cleans up leading symbols and collapses extra whitespace.
    Handles non-string input gracefully by converting to str first."""
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)
    if not text:
        return text
    # Remove LaTeX first
    text = strip_latex(text)
    # Remove all emoji/symbols
    cleaned = _EMOJI_PATTERN.sub("", text)
    # Collapse multiple spaces
    cleaned = re.sub(r"  +", " ", cleaned)
    # Strip leading/trailing whitespace per line
    cleaned = "\n".join(line.strip() for line in cleaned.splitlines())
    return cleaned.strip()


def clean_findings(findings: list) -> list:
    """Strip symbols from all finding descriptions and recommendations."""
    for f in findings:
        if "description" in f:
            f["description"] = strip_symbols(f["description"])
        if "aws_recommendation" in f:
            f["aws_recommendation"] = strip_symbols(f["aws_recommendation"])
    return findings


def clean_recommendations(recs: list) -> list:
    """Strip symbols from a list of recommendation strings or dicts."""
    cleaned = []
    for r in recs:
        if isinstance(r, dict):
            # LLM sometimes returns recs as objects — flatten to string
            text = r.get("action") or r.get("recommendation") or r.get("description") or r.get("text") or str(r)
            cleaned.append(strip_symbols(text))
        else:
            cleaned.append(strip_symbols(r))
    return cleaned


def clean_agent_output(output: dict) -> dict:
    """Strip symbols from all text fields in an agent output dict."""
    if "analysis" in output:
        output["analysis"] = strip_symbols(output["analysis"])
    if "findings" in output:
        output["findings"] = clean_findings(output["findings"])
    if "recommendations" in output:
        output["recommendations"] = clean_recommendations(output["recommendations"])
    if "raw_llm_response" in output:
        output["raw_llm_response"] = strip_symbols(output["raw_llm_response"])
    return output
