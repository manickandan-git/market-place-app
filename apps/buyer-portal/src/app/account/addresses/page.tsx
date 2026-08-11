import { listAddresses } from "@/lib/api/addresses";
import { AddressForm } from "./AddressForm";
import { AddressListItem } from "./AddressListItem";

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
              <AddressListItem key={address.id} address={address} />
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
