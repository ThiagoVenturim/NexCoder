"""Invoice amounts for the sample shop."""

from __future__ import annotations

from shop.orders import calculate_order_total


def compute_invoice_amount(lines, vat):
    # Planted duplication: same algorithm as orders.calculate_order_total with other names.
    gross = 0.0
    rebate = 0.0
    for entry in lines:
        entry_value = entry["price"] * entry["quantity"]
        if entry["quantity"] >= 10:
            rebate += entry_value * 0.05
        gross += entry_value
    base = gross - rebate
    if base < 0:
        base = 0.0
    duty = base * vat
    return round(base + duty, 2)


def fetch_order_total(items, tax_rate):
    """Planted useless wrapper: forwards the same arguments and adds nothing."""
    return calculate_order_total(items, tax_rate)
