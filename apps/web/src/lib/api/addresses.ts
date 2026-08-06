import "server-only";

import { apiClient } from "@/lib/api/client";
import { extractErrorMessage } from "@/lib/api/errors";
import type { components } from "@/lib/api/schema";

export type Address = components["schemas"]["user_AddressResponse"];
export type AddressCreateInput = components["schemas"]["user_AddressCreate"];
export type AddressUpdateInput = components["schemas"]["user_AddressUpdate"];

export interface AddressResult {
  ok: boolean;
  address?: Address;
  message?: string;
}

export async function listAddresses(): Promise<Address[]> {
  const { data, error } = await apiClient.GET("/api/v1/me/addresses");
  if (error) {
    return [];
  }
  return data;
}

export async function getAddress(addressId: string): Promise<Address | null> {
  const { data, error } = await apiClient.GET(
    "/api/v1/me/addresses/{address_id}",
    { params: { path: { address_id: addressId } } },
  );
  if (error) {
    return null;
  }
  return data;
}

export async function createAddress(
  input: AddressCreateInput,
): Promise<AddressResult> {
  const { data, error } = await apiClient.POST("/api/v1/me/addresses", {
    params: { header: { "Idempotency-Key": crypto.randomUUID() } },
    body: input,
  });
  if (error) {
    return { ok: false, message: extractErrorMessage(error) };
  }
  return { ok: true, address: data };
}

export async function updateAddress(
  addressId: string,
  input: AddressUpdateInput,
  version: number,
): Promise<AddressResult> {
  const { data, error } = await apiClient.PATCH(
    "/api/v1/me/addresses/{address_id}",
    {
      params: {
        path: { address_id: addressId },
        header: { "If-Match": String(version) },
      },
      body: input,
    },
  );
  if (error) {
    return { ok: false, message: extractErrorMessage(error) };
  }
  return { ok: true, address: data };
}

export async function deleteAddress(
  addressId: string,
  version: number,
): Promise<AddressResult> {
  const { error } = await apiClient.DELETE("/api/v1/me/addresses/{address_id}", {
    params: {
      path: { address_id: addressId },
      header: { "If-Match": String(version) },
    },
  });
  if (error) {
    return { ok: false, message: extractErrorMessage(error) };
  }
  return { ok: true };
}
