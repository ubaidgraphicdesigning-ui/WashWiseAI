from decimal import Decimal
import pytest
from washwise_core import (
    calculate_order_total, clean_order_items, format_pkr,
    tracking_phone_matches, to_decimal,
)

def test_calculates_order_total():
    rows = [{"quantity": 2, "unit_price": 150}, {"quantity": 1, "unit_price": 275.50}]
    assert calculate_order_total(rows) == Decimal("575.50")

def test_rejects_empty_items():
    with pytest.raises(ValueError):
        calculate_order_total([])

def test_rejects_zero_quantity():
    with pytest.raises(ValueError):
        calculate_order_total([{"quantity": 0, "unit_price": 50}])

def test_phone_suffix_verification():
    assert tracking_phone_matches("03001234567", "4567")
    assert not tracking_phone_matches("03001234567", "9999")

def test_clean_order_items():
    result = clean_order_items([{"garment_name": " Shirt ", "service_name": "Wash", "quantity": 2, "unit_price": 100}])
    assert result[0]["garment_name"] == "Shirt"
    assert result[0]["quantity"] == 2.0

def test_money_format():
    assert format_pkr("1200.5") == "Rs 1,200.50"

def test_non_finite_amount_is_rejected():
    with pytest.raises(ValueError):
        to_decimal("NaN")
