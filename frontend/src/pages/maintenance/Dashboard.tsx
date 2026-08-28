import { Link } from "react-router-dom";

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
  {
    href: "/admin/prompts",
    label: "Manage Prompts",
    description: "Inspect prompt tooling and future prompt management.",
  },
  {
    href: "/admin/docs",
    label: "Manage Docs",
    description: "Inspect documentation tooling and future document management.",
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
