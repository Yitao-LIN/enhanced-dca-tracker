from __future__ import annotations

import csv
from dataclasses import dataclass
import io
import re
import unicodedata
import zipfile
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Iterable, Mapping

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
        "prix d exe",
        "prix d execution",
        "prix unitaire",
        "unit price",
    },
    "fees": {
        "fees",
        "frais",
        "commission",
        "courtage",
        "courtage prelevement",
        "courtage prelevements",
        "prelevement",
        "brokerage fees",
    },
    "amount": {
        "amount",
        "montant",
        "montant brut",
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

FORTUNEO_ARCHIVE_CSV_RE = re.compile(r"(^|/)HistoriqueOperations.*\.csv$", re.IGNORECASE)


class SemicolonDialect(csv.excel):
    delimiter = ";"

TYPE_ALIASES = {
    TransactionType.BUY: {"buy", "achat", "acheter", "subscription", "souscription"},
    TransactionType.SELL: {"sell", "vente", "vendre", "redemption", "rachat"},
    TransactionType.DIVIDEND: {"dividend", "dividende", "coupon"},
    TransactionType.FEE: {"fee", "fees", "frais", "commission"},
    TransactionType.CASH: {"cash", "versement", "deposit", "withdrawal", "retrait", "virement"},
}


@dataclass(frozen=True)
class CsvPreviewRow:
    row_number: int
    transaction: Transaction | None = None
    error: str | None = None
    security_label: str | None = None


class SecurityMappingRequired(ValueError):
    def __init__(self, row_number: int, security_label: str) -> None:
        self.row_number = row_number
        self.security_label = security_label
        super().__init__(f"Row {row_number}: security {security_label!r} needs a ticker mapping before import")


def parse_transactions_csv(
    raw_csv: str | bytes,
    security_mappings: Mapping[str, str] | None = None,
) -> list[Transaction]:
    text = _extract_csv_text(raw_csv)
    dialect = _sniff_dialect(text)
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    if not reader.fieldnames:
        return []

    header_map = _map_headers(reader.fieldnames)
    transactions = []
    for row_number, row in enumerate(reader, start=2):
        if not any(value and value.strip() for value in row.values()):
            continue
        transactions.append(_parse_row(row, header_map, row_number, security_mappings))
    return transactions


def preview_transactions_csv(
    raw_csv: str | bytes,
    security_mappings: Mapping[str, str] | None = None,
) -> list[CsvPreviewRow]:
    try:
        text = _extract_csv_text(raw_csv)
    except ValueError as exc:
        return [CsvPreviewRow(row_number=1, error=str(exc))]
    dialect = _sniff_dialect(text)
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    if not reader.fieldnames:
        return []

    try:
        header_map = _map_headers(reader.fieldnames)
    except ValueError as exc:
        return [CsvPreviewRow(row_number=1, error=str(exc))]

    rows = []
    for row_number, row in enumerate(reader, start=2):
        if not any(value and value.strip() for value in row.values()):
            continue
        try:
            rows.append(
                CsvPreviewRow(
                    row_number=row_number,
                    transaction=_parse_row(row, header_map, row_number, security_mappings),
                )
            )
        except SecurityMappingRequired as exc:
            rows.append(CsvPreviewRow(row_number=row_number, security_label=exc.security_label, error=str(exc)))
        except ValueError as exc:
            rows.append(CsvPreviewRow(row_number=row_number, error=str(exc)))
    return rows


def _extract_csv_text(raw_csv: str | bytes) -> str:
    if isinstance(raw_csv, str):
        return raw_csv
    if _is_zip_archive(raw_csv):
        return _extract_fortuneo_archive_csv(raw_csv)
    return _decode_csv_bytes(raw_csv)


def _is_zip_archive(raw_csv: bytes) -> bool:
    return zipfile.is_zipfile(io.BytesIO(raw_csv))


def _extract_fortuneo_archive_csv(raw_csv: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(raw_csv)) as archive:
        for name in archive.namelist():
            normalized_name = name.replace("\\", "/")
            if FORTUNEO_ARCHIVE_CSV_RE.search(normalized_name):
                with archive.open(name) as csv_file:
                    return _decode_csv_bytes(csv_file.read())
    raise ValueError("ZIP archive does not contain a Fortuneo HistoriqueOperations CSV file")


def _decode_csv_bytes(raw_csv: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "iso-8859-1"):
        try:
            return raw_csv.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw_csv.decode("utf-8", errors="replace")


def _sniff_dialect(text: str) -> csv.Dialect:
    first_line = text.splitlines()[0] if text.splitlines() else ""
    if first_line.count(";") > first_line.count(","):
        return SemicolonDialect()
    sample = text[:2048]
    try:
        return csv.Sniffer().sniff(sample, delimiters=";,|\t,")
    except csv.Error:
        return csv.excel


def _map_headers(fieldnames: Iterable[str]) -> dict[str, str]:
    normalized = {_normalize_header(name): name for name in fieldnames if name is not None}
    if _is_fortuneo_account_export(normalized):
        raise ValueError(
            "This looks like a Fortuneo bank-account export with Debit/Credit columns, not a bourse investment "
            "export. Export the Fortuneo bourse/investment history instead, with columns such as Operation, "
            "Code valeur or ISIN, Qte, Prix, and Devise."
        )
    mapped = {}
    for canonical, aliases in HEADER_ALIASES.items():
        for alias in aliases:
            if alias in normalized:
                mapped[canonical] = normalized[alias]
                break
    required = {"date", "type"}
    missing = sorted(required - mapped.keys())
    if missing:
        raise ValueError(f"CSV is missing required columns: {', '.join(missing)}")
    return mapped


def _is_fortuneo_account_export(normalized_headers: dict[str, str]) -> bool:
    headers = set(normalized_headers)
    has_account_flow_columns = {"debit", "credit"}.issubset(headers)
    has_account_history_columns = {"date operation", "date valeur", "libelle"}.issubset(headers)
    lacks_investment_columns = headers.isdisjoint({"operation", "code valeur", "code isin", "isin", "qte", "quantite"})
    return has_account_flow_columns and has_account_history_columns and lacks_investment_columns


def _parse_row(
    row: dict[str, str],
    header_map: dict[str, str],
    row_number: int,
    security_mappings: Mapping[str, str] | None = None,
) -> Transaction:
    transaction_type = _parse_transaction_type(_value(row, header_map, "type"), row_number)
    ticker = _parse_ticker(row, header_map, row_number, security_mappings)
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


def _parse_ticker(
    row: dict[str, str],
    header_map: dict[str, str],
    row_number: int,
    security_mappings: Mapping[str, str] | None = None,
) -> str:
    ticker = _value(row, header_map, "ticker").strip()
    if ticker:
        return ticker.upper()

    label = _value(row, header_map, "description").strip()
    if label:
        mapped_ticker = _mapped_ticker(label, security_mappings)
        if mapped_ticker:
            return mapped_ticker
        raise SecurityMappingRequired(row_number, label)
    raise ValueError(
        f"Row {row_number}: CSV row has no ticker/security code; "
        "add a Code valeur, ISIN, ticker, or symbol column before import"
    )


def _mapped_ticker(label: str, security_mappings: Mapping[str, str] | None) -> str | None:
    if not security_mappings:
        return None
    ticker = security_mappings.get(normalize_security_label(label)) or security_mappings.get(label)
    if ticker is None:
        return None
    ticker = str(ticker).strip().upper()
    return ticker or None


def normalize_security_label(value: str) -> str:
    return _normalize_header(value)


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
        for alias in aliases:
            if normalized == alias or normalized.startswith(f"{alias} "):
                return transaction_type
    raise ValueError(f"Row {row_number}: unsupported transaction type {value!r}")
