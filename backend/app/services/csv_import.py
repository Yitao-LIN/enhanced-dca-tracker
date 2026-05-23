from __future__ import annotations

import csv
import io
import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Iterable

from app.domain import Transaction, TransactionType


HEADER_ALIASES = {
    "date": {
        "date",
        "date operation",
        "date d operation",
        "date execution",
        "trade date",
    },
    "ticker": {
        "ticker",
        "symbol",
        "code valeur",
        "code isin",
        "isin",
        "mnemo",
        "libelle valeur",
        "security",
    },
    "type": {
        "type",
        "operation",
        "sens",
        "transaction type",
        "nature",
    },
    "quantity": {
        "quantity",
        "quantite",
        "nombre",
        "shares",
        "qte",
    },
    "price": {
        "price",
        "cours",
        "prix",
        "prix unitaire",
        "unit price",
    },
    "fees": {
        "fees",
        "frais",
        "commission",
        "brokerage fees",
    },
    "amount": {
        "amount",
        "montant",
        "net amount",
        "montant net",
    },
    "currency": {
        "currency",
        "devise",
    },
    "account": {
        "account",
        "compte",
    },
    "description": {
        "description",
        "libelle",
        "label",
        "valeur",
    },
}

TYPE_ALIASES = {
    TransactionType.BUY: {"buy", "achat", "acheter", "subscription", "souscription"},
    TransactionType.SELL: {"sell", "vente", "vendre", "redemption", "rachat"},
    TransactionType.DIVIDEND: {"dividend", "dividende", "coupon"},
    TransactionType.FEE: {"fee", "fees", "frais", "commission"},
    TransactionType.CASH: {"cash", "versement", "deposit", "withdrawal", "retrait", "virement"},
}


def parse_transactions_csv(raw_csv: str | bytes) -> list[Transaction]:
    text = _decode_csv(raw_csv)
    dialect = _sniff_dialect(text)
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    if not reader.fieldnames:
        return []

    header_map = _map_headers(reader.fieldnames)
    transactions = []
    for row_number, row in enumerate(reader, start=2):
        if not any(value and value.strip() for value in row.values()):
            continue
        transactions.append(_parse_row(row, header_map, row_number))
    return transactions


def _decode_csv(raw_csv: str | bytes) -> str:
    if isinstance(raw_csv, str):
        return raw_csv
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "iso-8859-1"):
        try:
            return raw_csv.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw_csv.decode("utf-8", errors="replace")


def _sniff_dialect(text: str) -> csv.Dialect:
    sample = text[:2048]
    try:
        return csv.Sniffer().sniff(sample, delimiters=";,|\t,")
    except csv.Error:
        return csv.excel


def _map_headers(fieldnames: Iterable[str]) -> dict[str, str]:
    normalized = {_normalize_header(name): name for name in fieldnames if name is not None}
    mapped = {}
    for canonical, aliases in HEADER_ALIASES.items():
        for alias in aliases:
            if alias in normalized:
                mapped[canonical] = normalized[alias]
                break
    required = {"date", "ticker", "type"}
    missing = sorted(required - mapped.keys())
    if missing:
        raise ValueError(f"CSV is missing required columns: {', '.join(missing)}")
    return mapped


def _parse_row(row: dict[str, str], header_map: dict[str, str], row_number: int) -> Transaction:
    transaction_type = _parse_transaction_type(_value(row, header_map, "type"), row_number)
    quantity = _parse_decimal(_value(row, header_map, "quantity"), default=Decimal("0"))
    price = _parse_decimal(_value(row, header_map, "price"), default=Decimal("0"))
    amount = _parse_decimal(_value(row, header_map, "amount"), default=None)
    fees = abs(_parse_decimal(_value(row, header_map, "fees"), default=Decimal("0")))

    if quantity == 0 and amount is not None and price != 0:
        quantity = abs(amount / price)
    if price == 0 and amount is not None and quantity != 0:
        price = abs(amount / quantity)
    if transaction_type in {TransactionType.DIVIDEND, TransactionType.CASH} and price == 0 and amount is not None:
        price = abs(amount)
        quantity = Decimal("1")

    ticker = _value(row, header_map, "ticker").strip().upper()
    return Transaction(
        transaction_date=_parse_date(_value(row, header_map, "date"), row_number),
        ticker=ticker,
        transaction_type=transaction_type,
        quantity=abs(quantity),
        price=abs(price),
        fees=fees,
        currency=(_value(row, header_map, "currency") or "EUR").strip().upper(),
        account=(_value(row, header_map, "account") or None),
        description=(_value(row, header_map, "description") or None),
    )


def _value(row: dict[str, str], header_map: dict[str, str], canonical: str) -> str:
    source = header_map.get(canonical)
    if source is None:
        return ""
    value = row.get(source)
    return "" if value is None else str(value).strip()


def _normalize_header(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = value.encode("ascii", "ignore").decode("ascii")
    value = value.replace("'", " ")
    value = re.sub(r"[^a-zA-Z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip().lower()


def _parse_decimal(value: str, default: Decimal | None) -> Decimal | None:
    if not value:
        return default
    cleaned = value.replace("\u00a0", " ").replace(" ", "")
    cleaned = cleaned.replace("EUR", "").replace("$", "").replace("%", "")
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    else:
        cleaned = cleaned.replace(",", ".")
    cleaned = re.sub(r"[^0-9.\-]", "", cleaned)
    if cleaned in {"", "-", "."}:
        return default
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return default


def _parse_date(value: str, row_number: int) -> date:
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Row {row_number}: unsupported date format {value!r}")


def _parse_transaction_type(value: str, row_number: int) -> TransactionType:
    normalized = _normalize_header(value)
    for transaction_type, aliases in TYPE_ALIASES.items():
        if normalized in aliases:
            return transaction_type
    raise ValueError(f"Row {row_number}: unsupported transaction type {value!r}")
