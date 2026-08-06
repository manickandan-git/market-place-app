"use client";

import { useState } from "react";

import type { Address } from "@/lib/api/addresses";
import { badge, card, link } from "@/lib/ui";
import { AddressForm } from "./AddressForm";
import { DeleteAddressButton } from "./DeleteAddressButton";

export function AddressListItem({ address }: { address: Address }) {
  const [editing, setEditing] = useState(false);

  if (editing) {
    return (
      <li>
        <AddressForm
          address={address}
          onSuccess={() => setEditing(false)}
          onCancel={() => setEditing(false)}
        />
      </li>
    );
  }

  return (
    <li className={card + " flex items-start justify-between gap-4"}>
      <address className="not-italic text-sm leading-relaxed">
        {address.label ? <p className="font-medium">{address.label}</p> : null}
        {address.recipient_name}
        <br />
        {address.address_line1}
        {address.address_line2 ? (
          <>
            <br />
            {address.address_line2}
          </>
        ) : null}
        <br />
        {address.city}
        {address.state_or_region ? `, ${address.state_or_region}` : ""}{" "}
        {address.postal_code}
        <br />
        {address.country_code}
        {address.is_default ? <span className={badge + " ml-2"}>Default</span> : null}
      </address>
      <div className="flex flex-col items-end gap-2">
        <button
          type="button"
          onClick={() => setEditing(true)}
          className={link + " text-sm"}
        >
          Edit
        </button>
        <DeleteAddressButton addressId={address.id} version={address.version} />
      </div>
    </li>
  );
}
