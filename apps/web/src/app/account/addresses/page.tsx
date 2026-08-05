import { listAddresses } from "@/lib/api/addresses";
import { badge, card } from "@/lib/ui";
import { AddressForm } from "./AddressForm";
import { DeleteAddressButton } from "./DeleteAddressButton";

export default async function AddressesPage() {
  const addresses = await listAddresses();

  return (
    <div className="flex flex-col gap-10">
      <div>
        <h1 className="mb-6 text-3xl font-semibold tracking-tight">
          Addresses
        </h1>
        {addresses.length === 0 ? (
          <p className="text-muted-foreground">
            You haven&apos;t saved any addresses yet.
          </p>
        ) : (
          <ul className="flex flex-col gap-3">
            {addresses.map((address) => (
              <li
                key={address.id}
                className={card + " flex items-start justify-between gap-4"}
              >
                <address className="not-italic text-sm leading-relaxed">
                  {address.label ? (
                    <p className="font-medium">{address.label}</p>
                  ) : null}
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
                  {address.is_default ? (
                    <span className={badge + " ml-2"}>Default</span>
                  ) : null}
                </address>
                <DeleteAddressButton
                  addressId={address.id}
                  version={address.version}
                />
              </li>
            ))}
          </ul>
        )}
      </div>

      <div>
        <h2 className="mb-4 text-xl font-semibold">Add a new address</h2>
        <AddressForm />
      </div>
    </div>
  );
}
