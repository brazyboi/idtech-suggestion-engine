import { useEffect } from "react";
import type { Product } from "../types/messages";
import { downloadRecommendationPDF, RecommendationBundle } from "../api/client";
import GenericButton from "./GenericButton";

interface ProductModalProps {
  product: Product;
  onClose: () => void;
}

export default function ProductModal({ product, onClose }: ProductModalProps) {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);


  const handleRequestPDF = async () => {
    const bundle: RecommendationBundle = {
      hardware_name: product.name,
      highlights: [],
      explanation: product.description,
      hardware_items: [
        {
          name: product.name,
          role: "Recommended",
        },
      ],
    };
    const blob = await downloadRecommendationPDF(bundle);
    const url = URL.createObjectURL(blob);
    window.open(url, "_blank");
    window.addEventListener("unload", () => URL.revokeObjectURL(url), { once: true });
  };

  return (
    <div
      className="fixed inset-0 bg-black/60 flex items-center justify-center z-50"
      onClick={onClose}
    >
      <div
        className="chat-bg rounded-2xl shadow-2xl w-1/2 max-h-[80vh] overflow-y-auto p-8"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-2xl text-primary font-bold mb-2">Recommended Products</h2>
        <p className="text-secondary mb-6">Based on your responses, here are our top picks.</p>

        <div className="border border-gray-200 rounded-xl p-4 mb-4">
          <h3 className="text-lg font-semibold text-primary">{product.name} — SKU: {product.sku}</h3>
          <p className="text-secondary mt-1 text-sm">{product.description}</p>
        </div>

        <div className="flex flex-col items-center">
          <GenericButton
            className="btn-accent text-primary min-w-xl"
            onClick={handleRequestPDF}
          >
            Download Recommendation PDF
          </GenericButton>
          <button
            onClick={onClose}
            className="block mt-2 text-sm text-secondary hover:text-gray-600 underline cursor-pointer"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
