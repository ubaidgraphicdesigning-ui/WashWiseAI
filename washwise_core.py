"""Pure business helpers for WashWise AI. No database or UI dependencies."""
from __future__ import annotations
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re
from typing import Iterable, Mapping, Any

CENT = Decimal("0.01")

def to_decimal(value: Any) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("Enter a valid amount.") from exc
    if not number.is_finite():
        raise ValueError("Amount must be a finite number.")
    return number.quantize(CENT, rounding=ROUND_HALF_UP)

def calculate_order_total(items: Iterable[Mapping[str, Any]]) -> Decimal:
    total = Decimal("0.00")
    count = 0
    for item in items:
        quantity = to_decimal(item.get("quantity", 0))
        unit_price = to_decimal(item.get("unit_price", 0))
        if quantity <= 0:
            raise ValueError("Every order item must have a quantity greater than zero.")
        if unit_price < 0:
            raise ValueError("Item price cannot be negative.")
        total += quantity * unit_price
        count += 1
    if count == 0:
        raise ValueError("Add at least one garment or service before creating an order.")
    return total.quantize(CENT, rounding=ROUND_HALF_UP)

def digits_only(value: str) -> str:
    return re.sub(r"\D", "", value or "")

def tracking_phone_matches(stored_phone: str, supplied_last4: str) -> bool:
    stored = digits_only(stored_phone)
    supplied = digits_only(supplied_last4)
    return len(stored) >= 4 and len(supplied) == 4 and stored[-4:] == supplied

def format_pkr(value: Any, currency: str = "PKR") -> str:
    amount = to_decimal(value)
    if currency == "PKR":
        return f"Rs {amount:,.2f}"
    return f"{currency} {amount:,.2f}"

def clean_order_items(items: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    cleaned: list[dict[str, Any]] = []
    for item in items:
        quantity = to_decimal(item.get("quantity", 0))
        unit_price = to_decimal(item.get("unit_price", 0))
        if quantity <= 0 or unit_price < 0:
            raise ValueError("Invalid quantity or price.")
        cleaned.append({
            "garment_name": str(item.get("garment_name", "")).strip()[:100],
            "service_id": item.get("service_id"),
            "service_name": str(item.get("service_name", "")).strip()[:100],
            "quantity": float(quantity),
            "unit_price": float(unit_price),
        })
    calculate_order_total(cleaned)
    if any(not x["garment_name"] or not x["service_name"] for x in cleaned):
        raise ValueError("Every item needs a garment and a service.")
    return cleaned
