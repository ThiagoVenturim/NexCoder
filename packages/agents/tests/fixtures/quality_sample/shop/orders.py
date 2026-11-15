"""Order totals for the sample shop."""

from __future__ import annotations


def calculate_order_total(items, tax_rate):
    """Sum the order items, apply bulk discounts and add tax."""
    subtotal = 0.0
    discount = 0.0
    for item in items:
        line_value = item["price"] * item["quantity"]
        if item["quantity"] >= 10:
            discount += line_value * 0.05
        subtotal += line_value
    taxable = subtotal - discount
    if taxable < 0:
        taxable = 0.0
    tax = taxable * tax_rate
    return round(taxable + tax, 2)
