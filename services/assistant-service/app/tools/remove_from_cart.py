"""
This file contains tools for removing items from the shopping cart in the application.
It provides functions to handle CartClient remove_item functionality.
"""

from pydantic import BaseModel

from app.clients import CartClient
from app.config import get_settings
from app.tools.types import ToolContext, ToolSpec

_client = CartClient(get_settings())


class RemoveFromCartArgs(BaseModel):
    product_id: str
    variant_id: str


async def handle(args: dict, context: ToolContext) -> dict:
    parsed = RemoveFromCartArgs.model_validate(args)
    if not context.access_token:
        return {
            "authenticated": False,
            "message": "You need to sign in to remove items from your cart.",
        }
    result = await _client.remove_item(
        access_token=context.access_token,
        product_id=parsed.product_id,
        variant_id=parsed.variant_id,
        request_id=context.request_id,
    )

    if result is None:
        return {
            "authenticated": True,
            "removed": False,
            "message": "That item isn't in your cart.",
        }
    return {
        "authenticated": True,
        "removed": True,
        "cart": result,
    }


REMOVE_FROM_CART = ToolSpec(
    name="remove_from_cart",
    description=(
        "Remove an item from the shopping cart. Requires the buyer to be signed in."
    ),
    input_schema=RemoveFromCartArgs.model_json_schema(),
    handler=handle,
    is_write=True,
)
