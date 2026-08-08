# get availablility of a product by its sku
from pydantic import BaseModel

from app.clients import InventoryClient
from app.config import get_settings
from app.tools.types import ToolContext, ToolSpec

_client = InventoryClient(get_settings())

class GetAvailability(BaseModel):
    sku: str    

async def handle(args: dict, context: ToolContext) -> dict:
    parsed = GetAvailability.model_validate(args)
    availability = await _client.get_availability(
        parsed.sku, context.request_id
    )
    return {"availability": availability}

GET_AVAILABILITY = ToolSpec(
    name="get_availability",
    description=(
        "Retrieve the availability of a product in the marketplace catalog by its SKU. "
    ),
    input_schema=GetAvailability.model_json_schema(),
    handler=handle,
)



