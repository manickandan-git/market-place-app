from pydantic import BaseModel

from app.clients import ProductClient
from app.config import get_settings
from app.tools.types import ToolContext, ToolSpec

_client = ProductClient(get_settings())

class GetProduct(BaseModel):
    slug: str

async def handle(args: dict, context: ToolContext) -> dict:
    parsed = GetProduct.model_validate(args)
    product = await _client.get_product_by_slug(
        parsed.slug, context.request_id
    )
    return {"product": product}


GET_PRODUCT = ToolSpec(
    name="get_product",
    description=(
        "Retrieve a product from the marketplace catalog by its slug. "
        "Use this when you have a specific product in mind."
    ),
    input_schema=GetProduct.model_json_schema(),
    handler=handle,
)
