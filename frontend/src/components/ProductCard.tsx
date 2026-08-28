import type { Product } from "../types/messages";

interface ProductCardProps {
  product: Product;
}

export default function ProductCard({ product }: ProductCardProps) {
  // const [isDownloading, setIsDownloading] = useState(false);

  // const handleDownloadPDF = async () => {
  //   setIsDownloading(true);
  //   try {
  //     const bundle: RecommendationBundle = {
  //       hardware_name: product.name,
  //       hardware_items: [
  //         {
  //           name: product.name,
  //           role: "Recommended",
  //         },
  //       ],
  //       explanation: product.description,
  //       highlights: [],
  //     };
  //     const blob = await downloadRecommendationPDF(bundle);
  //     const url = URL.createObjectURL(blob);
  //     window.open(url, "_blank");
  //     window.addEventListener("unload", () => URL.revokeObjectURL(url), { once: true });
  //   } finally {
  //     setIsDownloading(false);
  //   }
  // };

  return (
    <div className="w-full rounded-xl border border-gray-200 bg-white/80 px-5 py-4">
      <p className="text-xs uppercase tracking-wide text-secondary">Recommended Hardware</p>
      <p className="mt-1 text-base font-semibold text-primary">{product.name}</p>
      {product.sku && <p className="mt-1 text-xs text-secondary">SKU: {product.sku}</p>}

      <div className="mt-3 flex flex-col gap-2">
        {product.product_url && (
          <a
            href={product.product_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center justify-center rounded-xl px-4 py-2 text-sm font-medium hover:cursor-pointer btn-accent"
          >
            View on ID TECH website →
          </a>
        )}

        {product.installation_docs && product.installation_docs.length > 0 && (
          <div className="mt-1">
            <p className="text-xs text-secondary mb-1">Installation Guides &amp; Docs:</p>
            <div className="flex flex-wrap gap-2">
              {product.installation_docs.map((doc, i) => (
                <a
                  key={i}
                  href={doc.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs text-blue-600 hover:text-blue-800 underline"
                >
                  {doc.title}
                </a>
              ))}
            </div>
          </div>
        )}

        {/* <GenericButton
          onClick={handleDownloadPDF}
          disabled={isDownloading}
          className="btn-accent text-primary text-xs mt-1 self-start"
        >
          {isDownloading ? "Generating PDF..." : "Download PDF"}
        </GenericButton> */}
      </div>
    </div>
  );
}
