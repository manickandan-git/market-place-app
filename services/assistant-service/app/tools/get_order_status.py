from pydantic import BaseModel

from app.clients import OrderClient
from app.config import get_settings
from app.tools._order_utils import summarize_order
from app.tools.types import ToolContext, ToolSpec

_client = OrderClient(get_settings())


class GetOrderStatusArgs(BaseModel):
    order_id: str


async def handle(args: dict, context: ToolContext) -> dict:
    parsed = GetOrderStatusArgs.model_validate(args)
    if not context.access_token:
        return {
            "authenticated": False,
            "message": "You need to sign in to check an order's status.",
        }
    order = await _client.get_order(
        parsed.order_id, context.access_token, context.request_id
    )
    return {
        "authenticated": True,
        "order": summarize_order(order) if order else None,
    }


GET_ORDER_STATUS = ToolSpec(
    name="get_order_status",
    description=(
        "Look up the status of a single order by its order ID, for the "
        "signed-in buyer. Returns order=null if the order doesn't exist or "
        "doesn't belong to the buyer. If the buyer is a guest (not signed "
        "in), this returns authenticated=False instead of an error — tell "
        "them they need to sign in to check an order."
    ),
    input_schema=GetOrderStatusArgs.model_json_schema(),
    handler=handle,
)
