import { notFound } from "next/navigation";

import { getProductBySlug } from "@/lib/api/products";
import { AddToCartForm } from "./AddToCartForm";

export default async function ProductDetailPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const product = await getProductBySlug(slug);

  if (!product) {
    notFound();
  }

  const variants = product.variants ?? [];
  const images = product.images ?? [];

  return (
    <div className="grid grid-cols-1 gap-10 md:grid-cols-2">
      <div className="flex flex-col gap-3">
        {images.length > 0 ? (
          images.map((image) => (
            // eslint-disable-next-line @next/next/no-img-element -- external, seller-supplied URLs; not worth Image optimization config for a v1 catalog
            <img
              key={image.id}
              src={image.url}
              alt={image.alt_text ?? product.name}
              className="w-full rounded-2xl border border-border object-cover shadow-sm"
            />
          ))
        ) : (
          <div className="flex aspect-square items-center justify-center rounded-2xl border border-dashed border-border bg-muted text-5xl font-semibold text-muted-foreground/40">
            {product.name.charAt(0).toUpperCase()}
          </div>
        )}
      </div>

      <div className="flex flex-col gap-5">
        <div>
          <span className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
            {product.brand ?? "Marketplace"}
          </span>
          <h1 className="mt-1 text-3xl font-semibold tracking-tight">
            {product.name}
          </h1>
        </div>

        {product.description ? (
          <p className="leading-relaxed text-muted-foreground">
            {product.description}
          </p>
        ) : null}

        {variants.length > 0 ? (
          <div className="rounded-2xl border border-border bg-card p-5 shadow-sm">
            <AddToCartForm product={product} />
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">
            No purchasable options are currently available for this product.
          </p>
        )}
      </div>
    </div>
  );
}
