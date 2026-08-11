from app.tools.add_to_cart import ADD_TO_CART
from app.tools.get_availability import GET_AVAILABILITY
from app.tools.get_my_orders import GET_MY_ORDERS
from app.tools.get_order_status import GET_ORDER_STATUS
from app.tools.get_policy import GET_POLICY
from app.tools.get_product import GET_PRODUCT
from app.tools.list_categories import LIST_CATEGORIES
from app.tools.remove_from_cart import REMOVE_FROM_CART
from app.tools.search_products import SEARCH_PRODUCTS
from app.tools.types import ToolSpec

TOOLS: list[ToolSpec] = [
    SEARCH_PRODUCTS,
    GET_PRODUCT,
    GET_AVAILABILITY,
    LIST_CATEGORIES,
    GET_POLICY,
    GET_MY_ORDERS,
    GET_ORDER_STATUS,
    ADD_TO_CART,
    REMOVE_FROM_CART,
]

TOOLS_BY_NAME: dict[str, ToolSpec] = {tool.name: tool for tool in TOOLS}