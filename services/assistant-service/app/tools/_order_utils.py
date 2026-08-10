ORDER_FIELDS = (
    "id",
    "order_number",
    "status",
    "payment_status",
    "currency_code",
    "subtotal",
    "tax_total",
    "shipping_total",
    "discount_total",
    "grand_total",
    "shipping_address",
    "items",
    "created_at",
    "updated_at",
)


def summarize_order(order: dict) -> dict:
    """Trim an order-service order to what the assistant needs.

    Drops billing_address, payment_reference, reservation_group_id, and
    cancellation_reason before the order ever reaches Anthropic's API -
    none of them are needed to answer a buyer support question.
    """
    return {key: order[key] for key in ORDER_FIELDS if key in order}
