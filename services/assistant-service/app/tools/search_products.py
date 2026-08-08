from pydantic import BaseModel

from app.clients import ProductClient
from app.config import get_settings
from app.tools.types import ToolContext, ToolSpec

_client = ProductClient(get_settings())


class SearchProductsArgs(BaseModel):
    query: str | None = None
    category_id: str | None = None


async def handle(args: dict, context: ToolContext) -> dict:
    parsed = SearchProductsArgs.model_validate(args)
    items = await _client.search_products(
        parsed.query, parsed.category_id, context.request_id
    )
    return {"items": items}


SEARCH_PRODUCTS = ToolSpec(
    name="search_products",
    description=(
        "Search the marketplace product catalog by keyword and/or category. "
        "Returns a list of matching products. Use this when a buyer describes "
        "what they're looking for."
    ),
    input_schema=SearchProductsArgs.model_json_schema(),
    handler=handle,
)
