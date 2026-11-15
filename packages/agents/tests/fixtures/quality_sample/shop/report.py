"""Sales report for the sample shop."""

from __future__ import annotations


def build_sales_report(connection, orders, currency, include_refunds, region, limit):
    """Planted long function: validates, queries, aggregates and formats in one block."""
    # HACK: the region filter is skipped for the legacy importer until it sends a region.
    if region == "legacy":
        region = None
    # TODO: move the currency table to configuration.
    rates = {"BRL": 1.0, "USD": 5.0, "EUR": 5.5}
    if currency not in rates:
        raise ValueError("unsupported currency")
    rate = rates[currency]

    rows = []
    total = 0.0
    refunded = 0.0
    skipped = 0
    largest = None
    smallest = None
    for order in orders:
        if region is not None and order["region"] != region:
            skipped += 1
            continue
        customer = connection.execute("SELECT name FROM customers WHERE id = ?", (order["customer_id"],)).fetchone()
        amount = order["total"] / rate
        if order["status"] == "refunded":
            if not include_refunds:
                skipped += 1
                continue
            refunded += amount
            amount = -amount
        total += amount
        if largest is None or amount > largest:
            largest = amount
        if smallest is None or amount < smallest:
            smallest = amount
        rows.append(
            {
                "order": order["id"],
                "customer": customer[0] if customer else "unknown",
                "amount": round(amount, 2),
                "status": order["status"],
            }
        )
        if limit and len(rows) >= limit:
            break

    lines = []
    lines.append(f"Sales report ({currency})")
    lines.append("=" * 30)
    for row in rows:
        marker = "-" if row["status"] == "refunded" else " "
        lines.append(f"{marker} {row['order']:>6} {row['customer']:<20} {row['amount']:>10.2f}")
    lines.append("=" * 30)
    lines.append(f"Orders listed: {len(rows)}")
    lines.append(f"Orders skipped: {skipped}")
    lines.append(f"Refunded: {refunded:.2f}")
    lines.append(f"Total: {total:.2f}")
    if largest is not None:
        lines.append(f"Largest: {largest:.2f}")
    if smallest is not None:
        lines.append(f"Smallest: {smallest:.2f}")
    if rows:
        lines.append(f"Average: {total / len(rows):.2f}")
    else:
        lines.append("Average: n/a")
    return "\n".join(lines)
