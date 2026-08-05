from app.services.openapi_aggregator import filter_paths_for_service, namespace_schema

FAKE_PRODUCT_SCHEMA = {
    "openapi": "3.1.0",
    "info": {"title": "Marketplace Product Service", "version": "1.0.0"},
    "paths": {
        "/api/v1/products": {
            "get": {
                "responses": {
                    "200": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": "#/components/schemas/ProductSummary"
                                }
                            }
                        }
                    }
                }
            }
        },
        "/health": {"get": {"responses": {"200": {"description": "ok"}}}},
        "/api/v1/internal/catalog-skus/{variant_id}": {
            "put": {"responses": {"200": {"description": "ok"}}}
        },
    },
    "components": {
        "schemas": {
            "ProductSummary": {
                "type": "object",
                "properties": {"id": {"type": "string"}},
            },
            "HTTPValidationError": {"type": "object"},
        },
        "securitySchemes": {"HTTPBearer": {"type": "http", "scheme": "bearer"}},
    },
}


def test_namespace_schema_renames_component_schemas():
    namespaced = namespace_schema("product", FAKE_PRODUCT_SCHEMA)
    schemas = namespaced["components"]["schemas"]
    assert "product_ProductSummary" in schemas
    assert "product_HTTPValidationError" in schemas
    assert "ProductSummary" not in schemas


def test_namespace_schema_rewrites_refs_to_match():
    namespaced = namespace_schema("product", FAKE_PRODUCT_SCHEMA)
    op = namespaced["paths"]["/api/v1/products"]["get"]
    ref = op["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
    assert ref == "#/components/schemas/product_ProductSummary"


def test_namespace_schema_leaves_security_schemes_unrenamed():
    # Every service defines the identical HTTPBearer scheme; keeping the
    # shared name lets Swagger UI's single Authorize button cover every
    # aggregated operation instead of one lock per service.
    namespaced = namespace_schema("product", FAKE_PRODUCT_SCHEMA)
    assert "HTTPBearer" in namespaced["components"]["securitySchemes"]


def test_namespace_schema_does_not_mutate_input():
    original_schema_count = len(FAKE_PRODUCT_SCHEMA["components"]["schemas"])
    namespace_schema("product", FAKE_PRODUCT_SCHEMA)
    assert len(FAKE_PRODUCT_SCHEMA["components"]["schemas"]) == original_schema_count
    assert "ProductSummary" in FAKE_PRODUCT_SCHEMA["components"]["schemas"]


def test_filter_paths_for_service_keeps_only_allowlisted_paths():
    kept = filter_paths_for_service("product", FAKE_PRODUCT_SCHEMA["paths"])
    assert set(kept) == {"/api/v1/products"}


def test_filter_paths_for_service_drops_internal_and_health_paths():
    kept = filter_paths_for_service("product", FAKE_PRODUCT_SCHEMA["paths"])
    assert "/health" not in kept
    assert "/api/v1/internal/catalog-skus/{variant_id}" not in kept


def test_filter_paths_for_service_excludes_paths_owned_by_other_services():
    # /api/v1/cart is allowlisted, but for cart-service, not product-service —
    # a stray/misconfigured path in a service's own schema must not leak
    # through under the wrong service.
    kept = filter_paths_for_service(
        "product", {"/api/v1/cart": {"get": {"responses": {}}}}
    )
    assert kept == {}
