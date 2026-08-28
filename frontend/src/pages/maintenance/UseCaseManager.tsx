import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import ColorButton from "./components/ColorButton";
import ConfirmModal from "./components/ConfirmModal";
import DataTable, { ColumnDef } from "./components/DataTable";

type UseCase = {
    id: number;
    name: string;
};

const COLUMNS: ColumnDef<UseCase>[] = [
    { header: "Use Case Name", key: "name" },
];

export default function UseCaseManager() {
    const navigate = useNavigate();
    const [useCases, setUseCases] = useState<UseCase[]>([]);
    const [selectedId, setSelectedId] = useState<number | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [showModal, setShowModal] = useState(false);
    const [deleting, setDeleting] = useState(false);

    useEffect(() => {
        fetch("http://localhost:8000/api/maintenance/use-cases/")
            .then((res) => {
                if (!res.ok) throw new Error(`Server error: ${res.status}`);
                return res.json();
            })
            .then((data) => {
                if (!Array.isArray(data)) throw new Error("Unexpected response format");
                setUseCases(data);
            })
            .catch((err) => setError(err.message))
            .finally(() => setLoading(false));
    }, []);

    async function handleConfirmRemove() {
        if (selectedId === null || selectedUseCase === null) return;
        setDeleting(true);
        try {
            const res = await fetch(`http://localhost:8000/api/maintenance/use-cases/${selectedUseCase.name}`, {
                method: "DELETE",
            });
            if (!res.ok) {
                const data = await res.json().catch(() => ({}));
                throw new Error(data.detail ?? `Server error: ${res.status}`);
            }
            setUseCases((prev) => prev.filter((u) => u.id !== selectedId));
            setSelectedId(null);
            setShowModal(false);
        } catch (err) {
            setError(err instanceof Error ? err.message : "Unknown error");
            setShowModal(false);
        } finally {
            setDeleting(false);
        }
    }

    const selectedUseCase = useCases.find((u) => u.id === selectedId) ?? null;

    return (
        <div className="flex flex-col p-0 text-black grow gap-3 min-h-0">
            <div>
                <h1 className="font-semibold text-2xl">Use Cases</h1>
                <p className="text-gray-600 text-sm">
                    This is a list of the current use cases used to classify hardware devices.
                </p>
                <p className="text-gray-600 text-sm">
                    To remove a use case, select the row and click "Remove Use Case." To add a new use case, click "Add Use Case."
                </p>
            </div>

            <div className="flex flex-col grow min-h-0 overflow-hidden">
                {loading ? (
                    <p className="text-gray-400 text-sm">Loading...</p>
                ) : error ? (
                    <p className="text-red-500 text-sm">Failed to load use cases: {error}</p>
                ) : (
                    <DataTable
                        columns={COLUMNS}
                        data={useCases}
                        selectedId={selectedId}
                        onSelectRow={setSelectedId}
                    />
                )}
            </div>

            <div className="flex min-h-fit min-w-fit">
                <ColorButton
                    className="mr-1"
                    color="var(--confirm-green)"
                    onClick={() => navigate("/admin/use-cases/add")}
                >
                    Add Use Case
                </ColorButton>
                <ColorButton
                    className="mr-1"
                    color="var(--back-gray)"
                    textColor="black"
                    disabled={selectedId === null}
                    onClick={() => selectedUseCase && navigate(`/admin/use-cases/edit/${selectedUseCase.name}`)}
                >
                    Rename Use Case
                </ColorButton>
                <ColorButton
                    color="var(--warning-red)"
                    disabled={selectedId === null}
                    onClick={() => setShowModal(true)}
                >
                    Remove Use Case
                </ColorButton>
            </div>

            {showModal && selectedUseCase && (
                <ConfirmModal
                    title="Remove Use Case"
                    message={`You are about to permanently remove "${selectedUseCase.name}" from the database. This action cannot be undone.`}
                    checkboxLabel="I understand this action is permanent."
                    confirmLabel="Remove Use Case"
                    cancelLabel="Go Back"
                    loading={deleting}
                    onConfirm={handleConfirmRemove}
                    onCancel={() => setShowModal(false)}
                />
            )}
        </div>
    );
}
