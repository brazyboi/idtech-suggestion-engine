import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { adminFetch } from "../../api/adminAuth";

interface FunnelMetrics {
  sessions_started: number;
  recommendations_shown: number;
  leads_captured: number;
  recommendation_rate: number | null;
  conversion_rate: number | null;
  close_rate: number | null;
}

const formatPct = (value: number | null): string =>
  value === null ? "—" : `${Math.round(value * 100)}%`;

function FunnelSummary() {
  const [metrics, setMetrics] = useState<FunnelMetrics | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    adminFetch("/api/lead/metrics")
      .then((res) => {
        if (!res.ok) throw new Error(`Failed to load metrics: ${res.statusText}`);
        return res.json();
      })
      .then(setMetrics)
      .catch((err) => setError(String(err)));
  }, []);

  if (error) return null;
  if (!metrics) return null;

  const cards = [
    { label: "Conversations Started", value: metrics.sessions_started.toString() },
    {
      label: "Reached a Recommendation",
      value: `${metrics.recommendations_shown} (${formatPct(metrics.recommendation_rate)})`,
    },
    {
      label: "Converted to Lead",
      value: `${metrics.leads_captured} (${formatPct(metrics.conversion_rate)})`,
    },
    { label: "Close Rate (shown → lead)", value: formatPct(metrics.close_rate) },
  ];

  return (
    <div>
      <h2 className="text-lg font-semibold text-[#01784B] mb-2">Resolution Funnel</h2>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {cards.map((card) => (
          <div key={card.label} className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
            <p className="text-xs text-gray-500">{card.label}</p>
            <p className="mt-1 text-xl font-semibold text-black">{card.value}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

const sections = [
  {
    href: "/admin/leads",
    label: "Manage Leads",
    description: "Review captured lead records and follow-up details.",
  },
  {
    href: "/admin/hardware",
    label: "Manage Hardware",
    description: "Edit the hardware catalog used in recommendations.",
  },
  {
    href: "/admin/software",
    label: "Manage Software",
    description: "Update supported software options.",
  },
  {
    href: "/admin/categories",
    label: "Manage Categories",
    description: "Maintain hardware classification groups.",
  },
  {
    href: "/admin/use-cases",
    label: "Manage Use Cases",
    description: "Curate the use cases tied to recommendations.",
  },
];

export default function Dashboard() {
  return (
    <div className="flex flex-col gap-6 text-black grow">
      <div>
        <h1 className="text-2xl font-semibold">Admin Dashboard</h1>
        <p className="text-sm text-gray-600">
          Choose a maintenance area to update the catalog, review leads, or inspect supporting content.
        </p>
      </div>

      <FunnelSummary />

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {sections.map((section) => (
          <Link
            key={section.href}
            to={section.href}
            className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm transition hover:border-[#02AF6E] hover:shadow-md"
          >
            <h2 className="text-lg font-semibold text-[#01784B]">{section.label}</h2>
            <p className="mt-2 text-sm text-gray-600">{section.description}</p>
          </Link>
        ))}
      </div>
    </div>
  );
}
