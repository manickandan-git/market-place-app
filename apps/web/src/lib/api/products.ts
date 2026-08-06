import "server-only";

import { apiClient } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

export type ProductSummary = components["schemas"]["product_ProductSummary"];
export type ProductDetail = components["schemas"]["product_ProductResponse"];
export type Category = components["schemas"]["product_CategoryResponse"];

export interface ListProductsParams {
  page?: number;
  pageSize?: number;
  categoryId?: string;
  q?: string;
}

export interface ListProductsResult {
  items: ProductSummary[];
  page: number;
  pageSize: number;
  totalItems: number;
  totalPages: number;
  /** False on a gateway/product-service failure — distinct from a
   * genuinely empty result set, so the page can tell "nothing matched
   * your search" apart from "we couldn't reach the catalog" and word the
   * empty state accordingly, same pattern as every other list/get
   * function in lib/api/* (getCart, getProfile, listCategories, ...):
   * degrade gracefully, never throw a raw error out of a data fetch for
   * an expected failure mode like a downstream being briefly unreachable. */
  ok: boolean;
}

export async function listProducts(
  params: ListProductsParams = {},
): Promise<ListProductsResult> {
  const { data, error } = await apiClient.GET("/api/v1/products", {
    params: {
      query: {
        page: params.page,
        page_size: params.pageSize,
        category_id: params.categoryId || undefined,
        q: params.q || undefined,
      },
    },
  });
  if (error) {
    return {
      items: [],
      page: params.page ?? 1,
      pageSize: params.pageSize ?? 20,
      totalItems: 0,
      totalPages: 1,
      ok: false,
    };
  }
  return {
    items: data.items,
    page: data.pagination.page,
    pageSize: data.pagination.page_size,
    totalItems: data.pagination.total_items,
    totalPages: data.pagination.total_pages,
    ok: true,
  };
}

export async function getProductBySlug(
  slug: string,
): Promise<ProductDetail | null> {
  const { data, error } = await apiClient.GET(
    "/api/v1/products/by-slug/{slug}",
    { params: { path: { slug } } },
  );
  if (error) {
    return null;
  }
  return data;
}

export async function listCategories(): Promise<Category[]> {
  const { data, error } = await apiClient.GET("/api/v1/categories");
  if (error) {
    return [];
  }
  return data;
}
