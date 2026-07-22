"""
parser.py
----------
A lightweight rule-based Natural Language parsing engine that converts a
free-form text or voice-transcribed command into structured invoice data.

This module deliberately avoids external paid NLP APIs so that the system
remains free to run and easy to deploy for Nigerian SMEs with limited
internet bandwidth and no budget for third-party AI services. It uses
pattern matching, keyword spotting, and number-word conversion tailored to
common Nigerian English phrasing (e.g. "naira", "bags", "cartons", "pieces").

Supported example commands:
    "Create invoice for John Doe, 2 bags of rice at 15000 naira each"
    "Bill Amaka Stores for 5 cartons of indomie at 3500 each, due in 7 days"
    "Invoice Chidi 3 plates of jollof rice 2000 naira each and 1 bottle of coke 500"
    "New invoice for Grace Ventures: 10 pieces of soap at 800, 20% discount"
"""

import re
from decimal import Decimal, InvalidOperation


NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "twenty": 20, "thirty": 30,
    "forty": 40, "fifty": 50, "a": 1, "an": 1,
}

# Common unit words customers/SMEs use when speaking
UNIT_WORDS = [
    "bags", "bag", "cartons", "carton", "pieces", "piece", "pcs", "pc",
    "plates", "plate", "bottles", "bottle", "packs", "pack", "kg", "kgs",
    "litres", "litre", "liters", "liter", "boxes", "box", "units", "unit",
    "dozen", "dozens", "rolls", "roll", "bundles", "bundle", "sets", "set",
]

CURRENCY_WORDS = ["naira", "ngn", "₦", "n"]


def _word_to_number(token):
    """Convert a number word or digit string to a numeric value."""
    token = token.lower().strip()
    if token in NUMBER_WORDS:
        return NUMBER_WORDS[token]
    try:
        return float(token)
    except ValueError:
        return None


def _clean_amount(raw):
    """Strip currency words/symbols and commas from a matched amount string."""
    raw = raw.lower()
    for word in CURRENCY_WORDS:
        raw = raw.replace(word, "")
    raw = raw.replace(",", "").strip()
    try:
        return Decimal(raw)
    except InvalidOperation:
        return None


class ParsedInvoiceCommand:
    """Structured result returned by parse_command()."""

    def __init__(self):
        self.customer_name = None
        self.items = []  # list of dicts: {description, quantity, unit, unit_price}
        self.discount_percent = Decimal("0")
        self.due_in_days = None
        self.success = False
        self.errors = []

    def as_dict(self):
        return {
            "customer_name": self.customer_name,
            "items": [
                {**item, "unit_price": str(item["unit_price"]), "quantity": str(item["quantity"])}
                for item in self.items
            ],
            "discount_percent": str(self.discount_percent),
            "due_in_days": self.due_in_days,
            "success": self.success,
            "errors": self.errors,
        }


CUSTOMER_PATTERNS = [
    # "create invoice for John Doe, ..." / "new invoice for Grace Ventures: ..."
    r"(?:create|new|generate|make)?\s*invoice\s+for\s+([A-Za-z][A-Za-z .&'-]+?)(?:,|:|\s+for\s+\d|\s+\d|\s+with|\s+due|$)",
    # "invoice John Doe, ..." (no "for")
    r"invoice\s+([A-Za-z][A-Za-z .&'-]+?)(?:,|:|\s+for\s+\d|\s+\d|\s+with|\s+due|$)",
    # "bill Amaka Stores for 5 cartons..." -> name comes right after "bill", stop before the quantity "for <number>"
    r"bill\s+([A-Za-z][A-Za-z .&'-]+?)\s+for\s+\d",
    # generic fallback: "... for <Name>, <items>"
    r"\bfor\s+([A-Za-z][A-Za-z .&'-]+?)(?:,|:|\s+for\s+\d|\s+\d)",
]

# e.g. "2 bags of rice at 15000 naira each" / "3 plates of jollof rice 2000 naira each"
ITEM_PATTERN = re.compile(
    r"(?P<qty>\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|twenty|thirty|forty|fifty|a|an)\s+"
    r"(?P<unit>" + "|".join(UNIT_WORDS) + r")?\s*(?:of\s+)?"
    r"(?P<desc>[A-Za-z][A-Za-z ]*?)"
    r"\s+(?:at|for|costing|cost)?\s*"
    r"(?:₦|n|ngn)?\s*"
    r"(?P<price>[\d,]+(?:\.\d+)?)\s*(?:naira|ngn|₦)?\s*(?:each|per\s+\w+)?",
    re.IGNORECASE,
)

DUE_PATTERN = re.compile(r"due\s+in\s+(\d+)\s*days?", re.IGNORECASE)
DISCOUNT_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*%\s*discount", re.IGNORECASE)


def parse_command(text):
    """
    Parse a free-form invoice command (typed or voice-transcribed) into
    structured data: customer name, line items, discount, and due date.

    Returns a ParsedInvoiceCommand instance.
    """
    result = ParsedInvoiceCommand()
    if not text or not text.strip():
        result.errors.append("Empty command received.")
        return result

    cleaned = text.strip()

    # 1. Extract customer name
    customer_name = None
    customer_match_span = None
    for pattern in CUSTOMER_PATTERNS:
        match = re.search(pattern, cleaned, re.IGNORECASE)
        if match:
            candidate = match.group(1).strip(" ,:")
            # Avoid swallowing a leading number (e.g. "for 2 bags")
            if candidate and not candidate[0].isdigit():
                customer_name = candidate.title()
                customer_match_span = match.span(1)
                break
    result.customer_name = customer_name
    if not customer_name:
        result.errors.append(
            "Could not detect a customer name. Try phrasing like "
            "'Create invoice for <Customer Name>, <items>'."
        )

    # Remove the matched customer-name text so the item parser does not
    # mistakenly re-match trailing words of the name as a line item
    # (e.g. "...Amaka Stores for 5 cartons" -> "Stores" being read as an item).
    items_text = cleaned
    if customer_match_span:
        start, end = customer_match_span
        items_text = cleaned[:start] + " " + cleaned[end:]

    # 2. Extract due date (in days from issue date)
    due_match = DUE_PATTERN.search(cleaned)
    if due_match:
        result.due_in_days = int(due_match.group(1))

    # 3. Extract discount
    discount_match = DISCOUNT_PATTERN.search(cleaned)
    if discount_match:
        result.discount_percent = Decimal(discount_match.group(1))

    # 4. Extract line items (scan the text with the customer name removed)
    for match in ITEM_PATTERN.finditer(items_text):
        qty_raw = match.group("qty")
        unit = (match.group("unit") or "unit").strip().lower()
        desc = match.group("desc").strip()
        price_raw = match.group("price")

        qty = _word_to_number(qty_raw)
        price = _clean_amount(price_raw)

        # Skip junk matches where description accidentally captured "due in 7"
        if not desc or desc.lower() in ("due", "in", "and"):
            continue
        if qty is None or price is None:
            continue

        result.items.append({
            "description": desc.title(),
            "quantity": qty,
            "unit": unit,
            "unit_price": price,
        })

    if not result.items:
        result.errors.append(
            "Could not detect any line items. Try phrasing like "
            "'2 bags of rice at 15000 naira each'."
        )

    result.success = bool(result.customer_name) and bool(result.items)
    return result


# ---------------------------------------------------------------------------
# Self-test examples (used during development/testing, see Chapter 4 tests)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    samples = [
        "Create invoice for John Doe, 2 bags of rice at 15000 naira each",
        "Bill Amaka Stores for 5 cartons of indomie at 3500 each, due in 7 days",
        "Invoice Chidi for 3 plates of jollof rice at 2000 naira each and 1 bottle of coke at 500 naira",
        "New invoice for Grace Ventures, 10 pieces of soap at 800 naira each, 20% discount",
    ]
    for s in samples:
        r = parse_command(s)
        print("INPUT:", s)
        print("PARSED:", r.as_dict())
        print("-" * 60)
