from pydantic import BaseModel

from app.clients import OrderClient
from app.config import get_settings
from app.tools._order_utils import summarize_order
from app.tools.types import ToolContext, ToolSpec

_client = OrderClient(get_settings())


class GetMyOrdersArgs(BaseModel):
    pass


async def handle(args: dict, context: ToolContext) -> dict:
    GetMyOrdersArgs.model_validate(args)
    if not context.access_token:
        return {
            "authenticated": False,
            "message": "You need to sign in to view your orders.",
        }
    page = await _client.get_my_orders(context.access_token, context.request_id)
    return {
        "authenticated": True,
        "orders": [summarize_order(o) for o in page["items"]],
        "total": page["total_items"],
    }


GET_MY_ORDERS = ToolSpec(
    name="get_my_orders",
    description=(
        "List the signed-in buyer's own orders. If the buyer is a guest "
        "(not signed in), this returns authenticated=False instead of an "
        "error — tell them they need to sign in to check their orders."
    ),
    input_schema=GetMyOrdersArgs.model_json_schema(),
    handler=handle,
)