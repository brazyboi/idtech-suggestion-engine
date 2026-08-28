import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import ColorButton from "./components/ColorButton";
import ConfirmModal from "./components/ConfirmModal";
import DataTable, { ColumnDef } from "./components/DataTable";

type Software = {
  id: number;
  name: string;
};

const COLUMNS: ColumnDef<Software>[] = [{ header: "Software Name", key: "name" }];

export default function SoftwareManager() {
  const navigate = useNavigate();
  const [software, setSoftware] = useState<Software[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    fetch("http://localhost:8000/api/maintenance/software/")
      .then((res) => {
        if (!res.ok) {
          throw new Error(`Server error: ${res.status}`);
        }
        return res.json();
      })
      .then((data) => {
        if (!Array.isArray(data)) {
          throw new Error("Unexpected response format");
        }
        setSoftware(data);
      })
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false));
  }, []);

  const selectedDevice = software.find((item) => item.id === selectedId) ?? null;

  async function handleConfirmRemove() {
    if (selectedId === null || selectedDevice === null) {
      return;
    }

    setDeleting(true);
    try {
      const res = await fetch(`http://localhost:8000/api/maintenance/software/${selectedDevice.name}`, {
        method: "DELETE",
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail ?? `Server error: ${res.status}`);
      }
      setSoftware((prev) => prev.filter((item) => item.id !== selectedId));
      setSelectedId(null);
      setShowModal(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
      setShowModal(false);
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="flex flex-col p-0 text-black grow gap-3 min-h-0">
      <div>
        <h1 className="font-semibold text-2xl">Software</h1>
        <p className="text-gray-600 text-sm">This is a list of the current software that the AI is able to recommend.</p>
        <p className="text-gray-600 text-sm">
          To remove software, select the row and click "Remove Software." To add new software, click "Add Software."
        </p>
      </div>

      <div className="flex flex-col grow min-h-0 overflow-hidden">
        {loading ? (
          <p className="text-gray-400 text-sm">Loading...</p>
        ) : error ? (
          <p className="text-red-500 text-sm">Failed to load software: {error}</p>
        ) : (
          <DataTable columns={COLUMNS} data={software} selectedId={selectedId} onSelectRow={setSelectedId} />
        )}
      </div>

      <div className="flex min-h-fit min-w-fit">
        <ColorButton
          className="mr-1"
          color="var(--confirm-green)"
          onClick={() => navigate("/admin/software/add")}
        >
          Add Software
        </ColorButton>
        <ColorButton
          className="mr-1"
          color="var(--back-gray)"
          textColor="black"
          disabled={selectedId === null}
          onClick={() => selectedDevice && navigate(`/admin/software/edit/${selectedDevice.name}`)}
        >
          Rename Software
        </ColorButton>
        <ColorButton color="var(--warning-red)" disabled={selectedId === null} onClick={() => setShowModal(true)}>
          Remove Software
        </ColorButton>
      </div>

      {showModal && selectedDevice && (
        <ConfirmModal
          title="Remove Software"
          message={`You are about to permanently remove "${selectedDevice.name}" from the database of software. This action cannot be undone.`}
          checkboxLabel="I understand this action is permanent."
          confirmLabel="Remove Software"
          cancelLabel="Go Back"
          loading={deleting}
          onConfirm={handleConfirmRemove}
          onCancel={() => setShowModal(false)}
        />
      )}
    </div>
  );
}
