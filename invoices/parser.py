"""
parser.py
---------
Production-quality, rule-based parsing for voice-transcribed and typed
invoice commands aimed at Nigerian SMEs.

This module intentionally stays dependency-free so it can be dropped into a
Django project without extra services or paid NLP APIs.

The parser is organized into clearly separated stages:
1. Imports
2. Constants
3. Dataclasses
4. Text normalization
5. Number word conversion
6. Money parsing
7. Customer extraction
8. Discount extraction
9. Due date extraction
10. Item splitting
11. Item parsing
12. Validation
13. Confidence scoring
14. parse_command()
15. Self-test section
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Iterable, List, Optional, Sequence, Tuple


# =============================================================================
# 2. Constants
# =============================================================================

# Canonical unit forms returned by the parser. Plural forms map to singular
# forms so downstream code can handle invoice items consistently.
UNIT_ALIASES = {
    "bag": "bag",
    "bags": "bag",
    "carton": "carton",
    "cartons": "carton",
    "crate": "crate",
    "crates": "crate",
    "piece": "piece",
    "pieces": "piece",
    "box": "box",
    "boxes": "box",
    "pack": "pack",
    "packs": "pack",
    "packet": "packet",
    "packets": "packet",
    "roll": "roll",
    "rolls": "roll",
    "bundle": "bundle",
    "bundles": "bundle",
    "plate": "plate",
    "plates": "plate",
    "bottle": "bottle",
    "bottles": "bottle",
    "kg": "kg",
    "kgs": "kg",
    "kilogram": "kg",
    "kilograms": "kg",
    "litre": "litre",
    "litres": "litre",
    "liter": "litre",
    "liters": "litre",
    "dozen": "dozen",
    "dozens": "dozen",
    "pair": "pair",
    "pairs": "pair",
}

SUPPORTED_UNITS = tuple(sorted(UNIT_ALIASES.keys(), key=len, reverse=True))

# Words that can appear in spoken quantities.
NUMBER_WORDS = {
    "zero": 0,
    "oh": 0,
    "a": 1,
    "an": 1,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
}

SCALE_WORDS = {
    "hundred": 100,
    "thousand": 1_000,
    "million": 1_000_000,
}

SUPPORTED_NUMBER_WORDS = tuple(sorted({*NUMBER_WORDS.keys(), *SCALE_WORDS.keys()}, key=len, reverse=True))

PRICE_CONNECTORS = {
    "at",
    "for",
    "costing",
    "cost",
    "priced",
    "price",
    "@",
}

TIME_WORDS = {
    "day",
    "days",
    "week",
    "weeks",
    "month",
    "months",
    "year",
    "years",
    "today",
    "tomorrow",
    "later",
    "after",
}

FILLER_WORDS = {
    "please",
    "kindly",
    "just",
    "uh",
    "um",
    "er",
    "please,",
}

COMMAND_PREFIX_RE = re.compile(
    r"""
    ^\s*
    (?:(?:please|kindly|just|uh|um|er)\s+)*
    (?:(?:create|new|make|generate|send)\s+)?
    (?:an?\s+)?
    invoice\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

BILL_PREFIX_RE = re.compile(r"^\s*(?:please\s+)?bill\b", re.IGNORECASE)

CUSTOMER_START_CONNECTORS_RE = re.compile(r"^\s*(?:for|to)\b\s*", re.IGNORECASE)

DISCOUNT_RE = re.compile(
    r"""
    (?P<pct>\d+(?:\.\d+)?)\s*(?:%|percent)\s*discount
    |
    discount\s*(?:of\s*)?(?P<pct2>\d+(?:\.\d+)?)\s*(?:%|percent)?
    """,
    re.IGNORECASE | re.VERBOSE,
)

DUE_RE = re.compile(
    r"""
    (?:due\s+in|in|within|payment\s+due\s+in)\s+
    (?P<days>\d+|(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|million)(?:\s+(?:and\s+)?)?)+
    \s+days?
    """,
    re.IGNORECASE | re.VERBOSE,
)

# A quantity is usually the first element of an item segment.
QUANTITY_START_RE = re.compile(
    rf"\b(?:\d[\d.]*|\d+(?:,\d{{3}})*(?:\.\d+)?(?:\s*(?:k|m|thousand|million))?|{'|'.join(re.escape(word) for word in SUPPORTED_NUMBER_WORDS)}|\d+)\b",
    re.IGNORECASE,
)

# Matches money-like expressions that may appear in an item segment.
MONEY_FRAGMENT_RE = re.compile(
    r"""
    (?:
        (?:(?:naira|ngn)\s*)?
        (?:\d[\d,]*(?:\.\d+)?(?:\s*(?:k|m|thousand|million))?)
    )
    |
    (?:
        (?:(?:naira|ngn)\s*)?
        (?:\d+(?:\.\d+)?\s*(?:k|m|thousand|million))
    )
    |
    (?:
        (?:(?:naira|ngn)\s*)?
        (?:
            one|two|three|four|five|six|seven|eight|nine|ten|
            eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|
            twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|million|and
        )
        (?:\s+
            (?:
                one|two|three|four|five|six|seven|eight|nine|ten|
                eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|
                twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|million|and
            )
        )*
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)

LEADING_CONNECTORS_RE = re.compile(r"^(?:and|,|;|:|then|with|plus|for|to)\b\s*", re.IGNORECASE)
TRAILING_CONNECTORS_RE = re.compile(r"\b(?:and|,|;|:|then|with|plus|for|to)\s*$", re.IGNORECASE)
LEADING_ITEM_NOISE_RE = re.compile(r"^\s*(?:and|,|;|:|then|with|plus)\s*", re.IGNORECASE)

WORD_SPLIT_RE = re.compile(r"\s+")
NON_ITEM_TAIL_RE = re.compile(r"\b(?:due|discount|percent|payment)\b", re.IGNORECASE)


# =============================================================================
# 3. Dataclasses
# =============================================================================


@dataclass
class InvoiceItem:
    """
    Represents a single line item on an invoice.

    quantity is stored as Decimal so the parser can support future fractional
    quantities without changing the data model.
    """

    quantity: Decimal
    unit: str
    description: str
    unit_price: Decimal

    def as_dict(self) -> dict:
        """Return a JSON-friendly representation of the item."""
        return {
            "quantity": str(self.quantity),
            "unit": self.unit,
            "description": self.description,
            "unit_price": str(self.unit_price),
        }


@dataclass
class ParsedInvoiceCommand:
    """
    Final structured output returned by parse_command().

    The dataclass is intentionally compact and serialisable so Django views or
    serializers can convert it into dictionaries or JSON without extra logic.
    """

    customer_name: Optional[str] = None
    items: List[InvoiceItem] = field(default_factory=list)
    discount_percent: Decimal = Decimal("0")
    due_in_days: Optional[int] = None
    success: bool = False
    confidence: float = 0.0
    errors: List[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        """Return a plain dictionary version of the parsed command."""
        return {
            "customer_name": self.customer_name,
            "items": [item.as_dict() for item in self.items],
            "discount_percent": str(self.discount_percent),
            "due_in_days": self.due_in_days,
            "success": self.success,
            "confidence": self.confidence,
            "errors": list(self.errors),
        }


# =============================================================================
# 4. Text normalization
# =============================================================================


def normalize_text(text: str) -> str:
    """
    Clean and standardize raw input before parsing.

    The goal is not to make the text perfect English. The goal is to create a
    predictable, parser-friendly version of the command:
    - Unicode characters are normalised.
    - Currency symbols are expanded to the word 'naira'.
    - Numeric commas are removed from amounts.
    - Repeated spaces and noisy punctuation are collapsed.
    - Common transcription fillers are removed.
    """

    if text is None:
        return ""

    text = unicodedata.normalize("NFKC", str(text))
    text = text.lower().strip()

    # Replace common voice-transcription fillers before we start splitting text.
    for filler in FILLER_WORDS:
        text = re.sub(rf"\b{re.escape(filler)}\b", " ", text)

    # Normalise common currency symbols and shorthand.
    text = text.replace("₦", " naira ")
    text = re.sub(r"\bngn\b", " naira ", text)
    text = re.sub(r"\bn(?=\d)", "naira ", text)

    # Remove commas from numbers first so 45,000 becomes 45000, then convert
    # leftover punctuation into space separators.
    text = re.sub(r"(?<=\d),(?=\d)", "", text)

    # Normalise punctuation that typically separates clauses in transcribed text.
    text = re.sub(r"[\r\n\t]+", " ", text)
    text = re.sub(r"[;:]+", " ", text)
    text = re.sub(r"[!?]+", " ", text)
    text = re.sub(r"[“”\"`]+", " ", text)

    # Turn percent signs into a spoken word so discount parsing becomes easier.
    text = text.replace("%", " percent ")

    # Keep decimal points intact, but remove most other stray punctuation.
    text = re.sub(r"(?<!\d)\.(?!\d)", " ", text)
    text = re.sub(r"[(),]+", " ", text)

    # Convert repeated hyphens and underscores into spaces.
    text = re.sub(r"[-_]+", " ", text)

    # Collapse duplicate whitespace created by the substitutions above.
    text = re.sub(r"\s+", " ", text).strip()

    return text


def strip_token(token: str) -> str:
    """
    Remove light punctuation from a single token while preserving digits and
    decimal points.
    """

    token = token.strip().strip(",")
    token = token.strip()
    token = token.strip("[]{}<>")
    token = token.strip("'\"")
    token = token.strip()

    # Remove a trailing full stop if it is not part of a decimal number.
    if token.endswith(".") and not re.search(r"\d\.\d$", token):
        token = token[:-1]

    return token


def tokenize(text: str) -> List[str]:
    """
    Split text into lightweight tokens after normalisation.

    This is intentionally simple. The parser is rule-based, so it performs best
    when tokens are easy to inspect and reason about.
    """

    if not text:
        return []
    return [strip_token(part) for part in WORD_SPLIT_RE.split(text) if strip_token(part)]


def smart_title(text: str) -> str:
    """
    Title-case a customer name without destroying punctuation-heavy business
    names like 'M&J Foods' or 'Grace-Ventures'.
    """

    if not text:
        return ""

    words = []
    for token in text.split():
        if token == "&":
            words.append(token)
            continue
        if "-" in token:
            words.append("-".join(piece.capitalize() for piece in token.split("-") if piece))
            continue
        if "'" in token:
            words.append("'".join(piece.capitalize() for piece in token.split("'") if piece))
            continue
        words.append(token.capitalize())

    return " ".join(words).strip()


def clean_fragment(text: str) -> str:
    """
    Apply light cleanup to a text fragment that is about to be parsed.

    This is used for item segments and customer name fragments.
    """

    if not text:
        return ""
    text = text.strip()
    text = re.sub(r"\s+", " ", text)
    text = text.strip(" ,;:-")
    return text


# =============================================================================
# 5. Number word conversion
# =============================================================================


def is_number_word(token: str) -> bool:
    """Return True when a token is a supported spoken number word."""

    return token in NUMBER_WORDS or token in SCALE_WORDS or token in {"and"}


def parse_numeric_token(token: str) -> Optional[Decimal]:
    """
    Parse a single token that may be numeric, scaled numeric, or a compact
    money token like '45k' or '2m'.
    """

    if not token:
        return None

    token = strip_token(token).lower()

    m = re.fullmatch(r"(\d+(?:\.\d+)?)([km])", token)
    if m:
        value = Decimal(m.group(1))
        suffix = m.group(2)
        if suffix == "k":
            return value * Decimal("1000")
        if suffix == "m":
            return value * Decimal("1000000")

    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(thousand|million)", token)
    if m:
        value = Decimal(m.group(1))
        return value * Decimal(str(SCALE_WORDS[m.group(2)]))

    if re.fullmatch(r"\d+(?:\.\d+)?", token):
        return Decimal(token)

    return None


def consume_number_phrase(tokens: Sequence[str], start_index: int = 0) -> Tuple[Optional[Decimal], int]:
    """
    Consume as many tokens as possible from a spoken-number phrase.

    Examples handled:
    - one
    - twenty three
    - one hundred and twenty
    - two million
    - 45
    - 45k
    - 2 million

    Returns:
    - the parsed Decimal value or None
    - how many tokens were consumed
    """

    if start_index >= len(tokens):
        return None, 0

    total = Decimal("0")
    current = Decimal("0")
    consumed = 0
    matched = False

    i = start_index
    while i < len(tokens):
        token = strip_token(tokens[i]).lower()
        if not token:
            i += 1
            consumed += 1
            continue

        # "and" is a filler inside spoken numbers: "one hundred and five".
        if token == "and" and matched:
            i += 1
            consumed += 1
            continue

        numeric = parse_numeric_token(token)
        if numeric is not None:
            current += numeric
            matched = True
            i += 1
            consumed += 1
            continue

        if token in NUMBER_WORDS:
            current += Decimal(str(NUMBER_WORDS[token]))
            matched = True
            i += 1
            consumed += 1
            continue

        if token == "hundred":
            if current == 0:
                current = Decimal("1")
            current *= Decimal("100")
            matched = True
            i += 1
            consumed += 1
            continue

        if token in {"thousand", "million"}:
            scale = Decimal(str(SCALE_WORDS[token]))
            if current == 0:
                current = Decimal("1")
            total += current * scale
            current = Decimal("0")
            matched = True
            i += 1
            consumed += 1
            continue

        break

    if not matched:
        return None, 0

    return total + current, consumed


def number_words_to_decimal(text: str) -> Optional[Decimal]:
    """
    Convert an entire short spoken-number phrase into Decimal.

    This helper is used when parsing customer-facing numbers such as quantities
    and money phrases.
    """

    tokens = tokenize(text)
    value, consumed = consume_number_phrase(tokens, 0)
    if value is None or consumed != len(tokens):
        return None
    return value


# =============================================================================
# 6. Money parsing
# =============================================================================


def normalize_money_fragment(fragment: str) -> str:
    """
    Prepare a short money phrase for numeric parsing.

    This strips currency words, whitespace noise, and common non-value tokens
    like 'each' or 'per item'.
    """

    if not fragment:
        return ""

    fragment = unicodedata.normalize("NFKC", fragment).lower().strip()
    fragment = fragment.replace("₦", " ")
    fragment = re.sub(r"\b(?:naira|ngn|each|per|item|items|unit|units|piece|pieces)\b", " ", fragment)
    fragment = re.sub(r"(?<=\d),(?=\d)", "", fragment)
    fragment = re.sub(r"\s+", " ", fragment).strip()
    return fragment


def parse_money_value(fragment: str) -> Optional[Decimal]:
    """
    Parse money-like text into a Decimal.

    Supported forms include:
    - 45000
    - 45,000
    - ₦45,000
    - 45000 naira
    - 45k
    - 2 million
    - 45 thousand
    - forty five thousand
    """

    fragment = normalize_money_fragment(fragment)
    if not fragment:
        return None

    tokens = tokenize(fragment)
    if not tokens:
        return None

    # First try to parse the full token sequence as a spoken number.
    value, consumed = consume_number_phrase(tokens, 0)
    if value is not None and consumed == len(tokens):
        return value

    # Then try a single compact numeric token or a digit+scale pair.
    if len(tokens) == 1:
        numeric = parse_numeric_token(tokens[0])
        if numeric is not None:
            return numeric

    # Handle cases like "45 thousand" or "2 million" after cleanup.
    if len(tokens) == 2:
        base = parse_numeric_token(tokens[0])
        if base is not None and tokens[1] in SCALE_WORDS:
            return base * Decimal(str(SCALE_WORDS[tokens[1]]))

    # As a final fallback, look for the first numeric token and scale it if
    # the next token is a known multiplier.
    for idx, token in enumerate(tokens):
        numeric = parse_numeric_token(token)
        if numeric is None:
            continue
        if idx + 1 < len(tokens) and tokens[idx + 1] in SCALE_WORDS:
            return numeric * Decimal(str(SCALE_WORDS[tokens[idx + 1]]))
        return numeric

    return None


def find_best_money_candidate(text: str) -> Tuple[Optional[str], Optional[Decimal], int, int]:
    """
    Search a short item tail for the most likely unit-price expression.

    The function returns a tuple of:
    - matched text
    - parsed Decimal value
    - start index in the original string
    - end index in the original string

    The scoring favors:
    - values preceded by price connectors like 'at' or 'for'
    - values near the end of the segment
    - values with currency/scaling cues like 'naira', 'k', 'million'
    """

    if not text:
        return None, None, -1, -1

    tokens = tokenize(text)
    if not tokens:
        return None, None, -1, -1

    best_score = -10_000
    best = (None, None, -1, -1)

    # We scan all short windows because the amount may be one token ("350000")
    # or multiple tokens ("2 million" / "forty five thousand").
    max_window = min(5, len(tokens))
    for start in range(len(tokens)):
        for end in range(start + 1, min(len(tokens), start + max_window) + 1):
            window_tokens = tokens[start:end]
            window_text = " ".join(window_tokens)
            value = parse_money_value(window_text)
            if value is None:
                continue

            lower_window = {tok.lower() for tok in window_tokens}
            if lower_window & TIME_WORDS:
                # A money amount should not look like "7 days".
                continue

            before = tokens[start - 1].lower() if start > 0 else ""
            after = tokens[end].lower() if end < len(tokens) else ""

            score = 0
            if before in PRICE_CONNECTORS:
                score += 4
            if end == len(tokens):
                score += 3
            if after in {"each", "per"}:
                score += 2
            if any(tok in {"naira", "ngn"} for tok in window_tokens):
                score += 2
            if any(tok.endswith("k") or tok.endswith("m") for tok in window_tokens):
                score += 2
            if any(re.fullmatch(r"\d[\d.]*", tok) for tok in window_tokens):
                score += 1

            # Penalise obviously time-related fragments unless they are clearly
            # tied to an invoice price.
            if after in TIME_WORDS or before in {"due", "in", "within"}:
                score -= 5

            if score > best_score or (score == best_score and start > best[2]):
                best_score = score
                best = (window_text, value, start, end)

    # Require at least a modest score so plain "7" in a due-date clause is not
    # mistaken for a price.
    if best_score < 1:
        return None, None, -1, -1

    return best


# =============================================================================
# 7. Customer extraction
# =============================================================================


def find_command_anchor(text: str) -> Tuple[int, int]:
    """
    Find the position where the actual customer content starts.

    This strips command words like 'create invoice', 'bill', and optional
    polite fillers.
    """

    match = COMMAND_PREFIX_RE.search(text)
    if match:
        return match.start(), match.end()

    match = BILL_PREFIX_RE.search(text)
    if match:
        return match.start(), match.end()

    # If the sentence does not explicitly start with a command word, we simply
    # treat the entire string as parseable text.
    return 0, 0


def extract_customer(text: str) -> Tuple[Optional[str], Optional[Tuple[int, int]]]:
    """
    Extract the customer name while avoiding item descriptions.

    The parser stops the customer name at the first strong item-like boundary:
    - a quantity start such as '2' or 'one'
    - a discount clause
    - a due-date clause
    - the end of the sentence

    Returns:
    - the cleaned customer name
    - the character span of the extracted name inside the normalised text
    """

    if not text:
        return None, None

    _, anchor_end = find_command_anchor(text)
    remainder_raw = text[anchor_end:]

    # Track how much text we skip so the returned character span is accurate
    # when the caller wants to remove the customer segment from the source text.
    leading_match = CUSTOMER_START_CONNECTORS_RE.match(remainder_raw)
    leading_offset = leading_match.end() if leading_match else 0
    remainder = remainder_raw[leading_offset:].strip()
    remainder = clean_fragment(remainder)

    if not remainder:
        return None, None

    # Find the first obvious item/discount/due boundary.
    boundaries = []
    for pattern in (QUANTITY_START_RE, DISCOUNT_RE, DUE_RE):
        match = pattern.search(remainder)
        if match:
            boundaries.append(match.start())

    if boundaries:
        cut = min(boundaries)
        raw_slice = remainder_raw[leading_offset:leading_offset + cut]
    else:
        raw_slice = remainder_raw[leading_offset:]

    # Remove trailing connector words from the raw slice before we clean it,
    # so the returned span does not accidentally eat into the item text.
    raw_slice = re.sub(r"\b(?:for|to|and|with|of)\s*$", "", raw_slice, flags=re.IGNORECASE)
    raw_slice = raw_slice.rstrip(" ,;:-")
    candidate = clean_fragment(raw_slice)

    # Remove trailing connector words that sometimes appear between the name
    # and the item list, e.g. "Bill Blessing Stores for 5 cartons ...".
    candidate = re.sub(r"\b(?:for|to|and|with|of)\s*$", "", candidate).strip(" ,;:-")
    candidate = clean_fragment(candidate)

    if not candidate:
        return None, None

    # If the candidate is too short or looks like item text, keep the parser
    # conservative and refuse to guess.
    if re.search(r"\b(?:bags?|cartons?|crates?|pieces?|boxes?|packs?|packets?|rolls?|bundles?|plates?|bottles?|kg|kgs|litre|litres|dozen|pairs?)\b", candidate):
        return None, None

    customer_start = anchor_end + leading_offset
    customer_end = customer_start + len(raw_slice)
    return smart_title(candidate), (customer_start, customer_end)


# =============================================================================
# 8. Discount extraction
# =============================================================================


def extract_discount(text: str) -> Optional[Decimal]:
    """
    Extract a discount percentage from the normalised command text.

    Supports phrases like:
    - 10% discount
    - discount 10%
    - 10 percent discount
    """

    if not text:
        return None

    match = DISCOUNT_RE.search(text)
    if not match:
        return None

    pct = match.group("pct") or match.group("pct2")
    if not pct:
        return None

    try:
        value = Decimal(pct)
    except InvalidOperation:
        return None

    return value


# =============================================================================
# 9. Due date extraction
# =============================================================================


def extract_due_date(text: str) -> Optional[int]:
    """
    Extract a due date in days.

    Supported phrasing includes:
    - due in 7 days
    - in 7 days
    - within 7 days
    - payment due in 7 days
    """

    if not text:
        return None

    match = DUE_RE.search(text)
    if not match:
        return None

    raw_days = match.group("days")
    if not raw_days:
        return None

    # Try digit parsing first, then spoken-number parsing.
    if re.fullmatch(r"\d+", raw_days.strip()):
        return int(raw_days)

    value = number_words_to_decimal(raw_days)
    if value is None:
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# =============================================================================
# 10. Item splitting
# =============================================================================


def find_quantity_spans(text: str) -> List[Tuple[int, int]]:
    """
    Locate all likely item starts in the text.

    This function intentionally errs on the side of finding too many candidate
    starts. Later validation removes false positives such as due-date numbers.
    """

    spans: List[Tuple[int, int]] = []
    if not text:
        return spans

    for match in QUANTITY_START_RE.finditer(text):
        start = match.start()
        if start > 0:
            prefix = text[:start].rstrip()
            if prefix:
                last_token = strip_token(prefix.split()[-1]).lower()
                # Accept quantities that begin the segment or follow a clear
                # item separator. This prevents prices like "45000" from being
                # treated as brand-new items after the word "at".
                if last_token not in {"and", "plus", "then", "with", "for", "to"} and prefix[-1] not in {",", ";", ":", " "}:
                    continue
        spans.append((match.start(), match.end()))

    # Deduplicate while preserving order. This is helpful when overlapping
    # quantity patterns are found in long spoken-number phrases.
    cleaned: List[Tuple[int, int]] = []
    last_start = -1
    for start, end in spans:
        if start == last_start:
            continue
        cleaned.append((start, end))
        last_start = start
    return cleaned


def split_items(text: str, customer_span: Optional[Tuple[int, int]] = None) -> List[str]:
    """
    Split the invoice section into candidate item segments.

    The function uses quantity starts rather than blindly splitting on 'and'
    because 'and' may appear inside descriptions or spoken numbers.

    Example:
    "2 bags of rice at 45000 each and 1 bottle of coke at 500"
    becomes two separate candidate segments.
    """

    if not text:
        return []

    working = text
    if customer_span:
        start, end = customer_span
        if 0 <= start < end <= len(working):
            working = working[:start] + " " + working[end:]

    working = clean_fragment(working)
    if not working:
        return []

    quantity_spans = find_quantity_spans(working)
    if not quantity_spans:
        return []

    segments: List[str] = []
    for idx, (start, _) in enumerate(quantity_spans):
        end = quantity_spans[idx + 1][0] if idx + 1 < len(quantity_spans) else len(working)
        segment = clean_fragment(working[start:end])
        segment = LEADING_ITEM_NOISE_RE.sub("", segment)
        segment = clean_fragment(segment)
        if segment:
            segments.append(segment)

    return segments


# =============================================================================
# 11. Item parsing
# =============================================================================


def canonical_unit(unit: str) -> str:
    """Map a unit token to its canonical singular form."""

    return UNIT_ALIASES.get(unit.lower(), unit.lower())


def parse_item_segment(segment: str) -> Tuple[Optional[InvoiceItem], Optional[str]]:
    """
    Parse a single item segment into an InvoiceItem.

    The parser expects the segment to begin with a quantity, followed by an
    optional unit, then a description, and finally a unit price.

    Returns:
    - the parsed item or None
    - an optional error message
    """

    if not segment:
        return None, "Empty item segment."

    segment = clean_fragment(segment)
    if not segment:
        return None, "Empty item segment."

    tokens = tokenize(segment)
    if not tokens:
        return None, "Could not read item segment."

    qty, consumed = consume_number_phrase(tokens, 0)
    if qty is None or consumed <= 0:
        return None, f"Could not parse item quantity from: '{segment}'."

    remainder_tokens = tokens[consumed:]
    if not remainder_tokens:
        return None, f"Could not parse item description from: '{segment}'."

    # Optional unit immediately after the quantity.
    unit = "unit"
    if remainder_tokens and remainder_tokens[0].lower() in UNIT_ALIASES:
        unit = canonical_unit(remainder_tokens[0])
        remainder_tokens = remainder_tokens[1:]

    # Optional "of" after the unit, as in "2 bags of rice".
    if remainder_tokens and remainder_tokens[0].lower() == "of":
        remainder_tokens = remainder_tokens[1:]

    if not remainder_tokens:
        return None, f"Could not parse item description from: '{segment}'."

    remainder_text = " ".join(remainder_tokens).strip()

    # Trailing command clauses should not be part of the item description or
    # price extraction. We trim them here so the last item can still be parsed
    # correctly when the user appends "discount" or "due in X days".
    remainder_text = re.split(r"\b(?:discount|due)\b", remainder_text, maxsplit=1, flags=re.IGNORECASE)[0].strip()

    # Locate the best money candidate inside the tail.
    money_text, money_value, start_idx, end_idx = find_best_money_candidate(remainder_text)
    if money_value is None:
        return None, f"Could not find a unit price in item segment: '{segment}'."

    tail_tokens = tokenize(remainder_text)
    price_tokens = tokenize(money_text or "")

    # Rebuild description by removing the matched money window from the tail.
    description_tokens = tail_tokens[:start_idx] + tail_tokens[end_idx:]
    description = clean_fragment(" ".join(description_tokens))

    # Remove price-introducer words that may have stayed behind after slicing.
    description = re.sub(r"\b(?:at|for|costing|cost|priced|price|each|per)\b", " ", description)
    description = clean_fragment(description)

    # Reject clauses that are clearly not a product description.
    if not description or re.search(r"\b(?:due|discount|days?|week|weeks|month|months|year|years)\b", description):
        return None, f"Could not parse a valid item description from: '{segment}'."

    # If the description accidentally contains only price connector residue, try
    # again by trimming connector words from the front.
    description = re.sub(r"^(?:of|the|a|an)\s+", "", description).strip()
    if not description:
        return None, f"Could not parse a valid item description from: '{segment}'."

    try:
        item = InvoiceItem(
            quantity=qty,
            unit=unit,
            description=smart_title(description),
            unit_price=money_value,
        )
    except Exception as exc:  # pragma: no cover - defensive guard
        return None, f"Failed to build item from segment '{segment}': {exc}"

    return item, None


# =============================================================================
# 12. Validation
# =============================================================================


def validate_parsed_command(result: ParsedInvoiceCommand) -> List[str]:
    """
    Validate the parsed command and return a list of user-facing errors.

    Validation is intentionally strict enough to prevent malformed invoices but
    permissive enough to tolerate normal voice-transcription noise.
    """

    errors: List[str] = []

    if not result.customer_name:
        errors.append("Could not detect a customer name.")

    if not result.items:
        errors.append("Could not detect any invoice items.")

    if result.discount_percent is not None:
        try:
            if result.discount_percent < 0:
                errors.append("Discount cannot be negative.")
            if result.discount_percent > 100:
                errors.append("Discount cannot be greater than 100 percent.")
        except Exception:
            errors.append("Discount value is invalid.")

    if result.due_in_days is not None and result.due_in_days < 0:
        errors.append("Due date cannot be negative.")

    for idx, item in enumerate(result.items, start=1):
        if item.quantity <= 0:
            errors.append(f"Item {idx} has an invalid quantity.")
        if not item.description:
            errors.append(f"Item {idx} is missing a description.")
        if item.unit_price <= 0:
            errors.append(f"Item {idx} has an invalid unit price.")
        if not item.unit:
            errors.append(f"Item {idx} is missing a unit.")

    return errors


# =============================================================================
# 13. Confidence scoring
# =============================================================================


def calculate_confidence(result: ParsedInvoiceCommand) -> float:
    """
    Compute a confidence score from 0.0 to 1.0.

    The score rewards:
    - presence of a customer name
    - at least one parsed item
    - well-formed items
    - no validation errors

    It penalises:
    - parser errors
    - incomplete items
    """

    score = 0.0

    if result.customer_name:
        score += 0.25

    if result.items:
        score += 0.35
        item_scores = []
        for item in result.items:
            item_score = 0.0
            if item.quantity > 0:
                item_score += 0.25
            if item.description:
                item_score += 0.25
            if item.unit_price > 0:
                item_score += 0.25
            if item.unit:
                item_score += 0.25
            item_scores.append(item_score)
        score += 0.25 * (sum(item_scores) / len(item_scores))

    if result.discount_percent is not None:
        score += 0.05

    if result.due_in_days is not None:
        score += 0.05

    # Penalise each validation error slightly. This keeps confidence sensible
    # even when a command is partially understood.
    score -= min(0.35, 0.05 * len(result.errors))

    return max(0.0, min(1.0, round(score, 3)))


# =============================================================================
# 14. parse_command()
# =============================================================================


def parse_command(text: str) -> ParsedInvoiceCommand:
    """
    Parse a raw invoice command into a ParsedInvoiceCommand dataclass.

    Parsing flow:
    1. Normalise the text.
    2. Extract customer name.
    3. Extract discount.
    4. Extract due date.
    5. Split candidate item segments.
    6. Parse each item segment.
    7. Validate the result.
    8. Score confidence.
    """

    result = ParsedInvoiceCommand()

    normalized = normalize_text(text)
    if not normalized:
        result.errors.append("Empty command received.")
        result.confidence = 0.0
        result.success = False
        return result

    customer_name, customer_span = extract_customer(normalized)
    result.customer_name = customer_name

    discount = extract_discount(normalized)
    if discount is not None:
        result.discount_percent = discount

    due_in_days = extract_due_date(normalized)
    if due_in_days is not None:
        result.due_in_days = due_in_days

    # Remove the customer section before splitting items so the parser does not
    # accidentally treat customer words as item text.
    items_source = normalized
    if customer_span:
        start, end = customer_span
        if 0 <= start < end <= len(items_source):
            items_source = items_source[:start] + " " + items_source[end:]
            items_source = clean_fragment(items_source)

    # If we still have a leading command prefix, keep the item splitter focused
    # on the item area.
    items_source = COMMAND_PREFIX_RE.sub("", items_source, count=1)
    items_source = BILL_PREFIX_RE.sub("", items_source, count=1)
    items_source = CUSTOMER_START_CONNECTORS_RE.sub("", items_source, count=1)
    items_source = clean_fragment(items_source)

    candidate_segments = split_items(items_source)

    for segment in candidate_segments:
        item, error = parse_item_segment(segment)
        if item is not None:
            result.items.append(item)
        elif error:
            # Store parser hints only when they are likely meaningful. This
            # keeps the output useful without becoming too noisy.
            if "Could not find a unit price" in error or "Could not parse item" in error:
                continue

    # Validation runs after parsing so it can add consistent, user-facing
    # messages for all missing or malformed fields.
    result.errors.extend(validate_parsed_command(result))

    # Decide final success only after validation.
    result.success = len(result.errors) == 0

    # Confidence is computed last so the score reflects the final parsed state.
    result.confidence = calculate_confidence(result)

    return result


# =============================================================================
# 15. Self-test section
# =============================================================================


if __name__ == "__main__":
    samples = [
        "Create invoice for John Doe, 2 bags of rice at 45000 naira each",
        "Bill Blessing Stores for 5 cartons of Indomie at 4200 each and 2 cartons of Coke at 5800 each",
        "Invoice Grace Ventures 10 bags of cement at ₦10500 each, 10% discount, due in 7 days",
        "Invoice Chidi Enterprises for one laptop at 350000 and two wireless mice at 12000 each",
        "Create invoice for Jide Traders, 3 crates of eggs at 2200 each",
        "Bill Ada Market for 4 packs of bottled water at 1500 each due in 14 days",
        "Invoice Kemi Stores 2 boxes of biscuits at 1800 each and 1 carton of milk at 13500",
        "New invoice for Blue Nile Ventures, 10 pieces of pen at 200 each, 5 percent discount",
        "Generate invoice for Tayo Supermarket 6 bottles of fanta at 850 each and 6 bottles of coke at 900 each",
        "Please create invoice for Harmony Foods 1 bag of beans at 45000",
        "Invoice for Muna Enterprise 2 million naira generator at 2 million",
        "Bill Olumide Stores for 45k printer at 45k",
        "Create invoice for Grace and Mercy Shop 3 bundles of tissue at 3200 each",
        "Invoice Chika 8 plates of jollof rice at 2500 each and 2 plates of salad at 1000 each",
        "Create invoice for Amina Ventures 1 dozen eggs at 2800 each",
        "Bill Ibrahim Superstore for 5 cartons of soap at 6500 each, due in 21 days",
        "Invoice for Sunrise Foods 2 bags of garri at 38000 and 1 bag of rice at 52000",
        "New invoice for Royal Mart 12 packs of water at 900 each, 15 percent discount",
        "Invoice for Nneka Stores one television at 350000 and two remotes at 5000 each",
        "Create invoice for Victor Metals 3 kg of nails at 7500 each and 2 kg of screws at 8200 each",
        "Bill Precious Plaza for two cartons of noodles at forty five thousand each",
        "Invoice for Evergreen Supplies 7 rolls of toilet paper at 1200 each",
    ]

    for idx, sample in enumerate(samples, start=1):
        parsed = parse_command(sample)
        print(f"\nTEST {idx}")
        print("INPUT:", sample)
        print("SUCCESS:", parsed.success)
        print("CONFIDENCE:", parsed.confidence)
        print("CUSTOMER:", parsed.customer_name)
        print("DUE:", parsed.due_in_days)
        print("DISCOUNT:", parsed.discount_percent)
        print("ERRORS:", parsed.errors)
        print("ITEMS:", [item.as_dict() for item in parsed.items])
