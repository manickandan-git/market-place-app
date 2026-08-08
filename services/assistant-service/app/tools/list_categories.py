from pydantic import BaseModel

from app.clients import ProductClient
from app.config import get_settings
from app.tools.types import ToolContext, ToolSpec

_client = ProductClient(get_settings())
    
class ListCategoriesArgs(BaseModel):
    pass

async def handle(args: dict, context: ToolContext) -> dict:
    ListCategoriesArgs.model_validate(args)
    categories = await _client.list_categories(context.request_id)
    return {"categories": categories}

LIST_CATEGORIES = ToolSpec( 
    name="list_categories",
    description=(
        "List all product categories in the marketplace catalog. "
        "Use this to show buyers what categories are available."
    ),
    input_schema=ListCategoriesArgs.model_json_schema(),
    handler=handle,

)


