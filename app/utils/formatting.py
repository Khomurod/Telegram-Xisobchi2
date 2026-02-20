"""
Shared formatting helpers used across handlers and services.
"""


def format_amount(amount: float, currency: str) -> str:
    """Format amount with currency symbol.

    Examples:
        format_amount(50000, "UZS") → "50,000 so'm"
        format_amount(100.50, "USD") → "$100.50"
    """
    if currency == "USD":
        return f"${amount:,.2f}"
    return f"{amount:,.0f} so'm"
