"""
This file contains tools for adding items to the shopping cart in the application.
It provides functions to handle CartClient add_item functionality.
"""
from pydantic import BaseModel, Field

from app.clients import CartClient
from app.config import get_settings
from app.tools.types import ToolContext, ToolSpec

_client = CartClient(get_settings())


class AddToCartArgs(BaseModel):
    product_id: str
    variant_id: str
    quantity: int = Field(default=1, ge=1, le=1000)


async def handle(args: dict, context: ToolContext) -> dict:
    parsed = AddToCartArgs.model_validate(args)
    if not context.access_token:
        return {
            "authenticated": False,
            "message": "You need to sign in to add items to your cart.",
        }
    result = await _client.add_item(
        access_token=context.access_token,
        product_id=parsed.product_id,
        variant_id=parsed.variant_id,
        quantity=parsed.quantity,
        request_id=context.request_id
    )
    return {
        "authenticated": True,
        "cart": result,
    }


ADD_TO_CART = ToolSpec(
    name="add_to_cart",
    description=(
        "Add an item to the shopping cart. Requires the buyer to be signed in."
    ),
    input_schema=AddToCartArgs.model_json_schema(),
    handler=handle,
)
