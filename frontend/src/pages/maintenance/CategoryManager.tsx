import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import ColorButton from "./components/ColorButton";
import ConfirmModal from "./components/ConfirmModal";
import DataTable, { ColumnDef } from "./components/DataTable";

type Category = {
    id: number;
    name: string;
};

const COLUMNS: ColumnDef<Category>[] = [
    { header: "Category Name", key: "name" },
];

export default function CategoryManager() {
    const navigate = useNavigate();
    const [categories, setCategories] = useState<Category[]>([]);
    const [selectedId, setSelectedId] = useState<number | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [showModal, setShowModal] = useState(false);
    const [deleting, setDeleting] = useState(false);

    useEffect(() => {
        fetch("http://localhost:8000/api/maintenance/categories/")
            .then((res) => {
                if (!res.ok) throw new Error(`Server error: ${res.status}`);
                return res.json();
            })
            .then((data) => {
                if (!Array.isArray(data)) throw new Error("Unexpected response format");
                setCategories(data);
            })
            .catch((err) => setError(err.message))
            .finally(() => setLoading(false));
    }, []);

    async function handleConfirmRemove() {
        if (selectedId === null || selectedCategory === null) return;
        setDeleting(true);
        try {
            const res = await fetch(`http://localhost:8000/api/maintenance/categories/${selectedCategory.name}`, {
                method: "DELETE",
            });
            if (!res.ok) {
                const data = await res.json().catch(() => ({}));
                throw new Error(data.detail ?? `Server error: ${res.status}`);
            }
            setCategories((prev) => prev.filter((c) => c.id !== selectedId));
            setSelectedId(null);
            setShowModal(false);
        } catch (err) {
            setError(err instanceof Error ? err.message : "Unknown error");
            setShowModal(false);
        } finally {
            setDeleting(false);
        }
    }

    const selectedCategory = categories.find((c) => c.id === selectedId) ?? null;

    return (
        <div className="flex flex-col p-0 text-black grow gap-3 min-h-0">
            <div>
                <h1 className="font-semibold text-2xl">Categories</h1>
                <p className="text-gray-600 text-sm">
                    This is a list of the current categories used to classify hardware devices.
                </p>
                <p className="text-gray-600 text-sm">
                    To remove a category, select the row and click "Remove Category." To add a new category, click "Add Category."
                </p>
            </div>

            <div className="flex flex-col grow min-h-0 overflow-hidden">
                {loading ? (
                    <p className="text-gray-400 text-sm">Loading...</p>
                ) : error ? (
                    <p className="text-red-500 text-sm">Failed to load categories: {error}</p>
                ) : (
                    <DataTable
                        columns={COLUMNS}
                        data={categories}
                        selectedId={selectedId}
                        onSelectRow={setSelectedId}
                    />
                )}
            </div>

            <div className="flex min-h-fit min-w-fit">
                <ColorButton
                    className="mr-1"
                    color="var(--confirm-green)"
                    onClick={() => navigate("/admin/categories/add")}
                >
                    Add Category
                </ColorButton>
                <ColorButton
                    className="mr-1"
                    color="var(--back-gray)"
                    textColor="black"
                    disabled={selectedId === null}
                    onClick={() => selectedCategory && navigate(`/admin/categories/edit/${selectedCategory.name}`)}
                >
                    Rename Category
                </ColorButton>
                <ColorButton
                    color="var(--warning-red)"
                    disabled={selectedId === null}
                    onClick={() => setShowModal(true)}
                >
                    Remove Category
                </ColorButton>
            </div>

            {showModal && selectedCategory && (
                <ConfirmModal
                    title="Remove Category"
                    message={`You are about to permanently remove "${selectedCategory.name}" from the database. This action cannot be undone.`}
                    checkboxLabel="I understand this action is permanent."
                    confirmLabel="Remove Category"
                    cancelLabel="Go Back"
                    loading={deleting}
                    onConfirm={handleConfirmRemove}
                    onCancel={() => setShowModal(false)}
                />
            )}
        </div>
    );
}
