import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import ColorButton from "./components/ColorButton";
import ConfirmModal from "./components/ConfirmModal";
import DataTable, { ColumnDef } from "./components/DataTable";

type HardwareDevice = {
  id: number;
  model_name: string;
  operate_temperature: string | null;
  input_power: string | null;
  ip_rating: string | null;
  ik_rating: string | null;
  interface: string | null;
  is_active: boolean;
};

const COLUMNS: ColumnDef<HardwareDevice>[] = [
  { header: "Model Name", key: "model_name" },
  { header: "Operating Temp.", key: "operate_temperature" },
  { header: "Input Power", key: "input_power" },
  { header: "IP Rating", key: "ip_rating" },
  { header: "IK Rating", key: "ik_rating" },
  { header: "Interface", key: "interface" },
];

export default function HardwareManager() {
  const navigate = useNavigate();
  const [devices, setDevices] = useState<HardwareDevice[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    fetch("http://localhost:8000/api/maintenance/hardware/")
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
        setDevices(data);
      })
      .catch((err) => handleError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false));
  }, []);

  const selectedDevice = devices.find((device) => device.id === selectedId) ?? null;

  function handleError(message: string) {
    setError(message);
    setSelectedId(null);
  }

  async function handleConfirmRemove() {
    if (selectedId === null || selectedDevice === null) {
      return;
    }

    setDeleting(true);
    try {
      const res = await fetch(`http://localhost:8000/api/maintenance/hardware/${selectedDevice.model_name}`, {
        method: "DELETE",
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail ?? `Server error: ${res.status}`);
      }
      setDevices((prev) => prev.filter((device) => device.id !== selectedId));
      setSelectedId(null);
      setShowModal(false);
    } catch (err) {
      handleError(err instanceof Error ? err.message : "Unknown error");
      setShowModal(false);
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="flex flex-col p-0 text-black grow gap-3 min-h-0">
      <div>
        <h1 className="font-semibold text-2xl">Hardware Devices</h1>
        <p className="text-gray-600 text-sm">
          This is a list of the current hardware devices that the AI has knowledge of while making recommendations.
        </p>
        <p className="text-gray-600 text-sm">
          To remove a hardware device, select the row and click "Remove Device." To add a new hardware device, click
          "Add Device."
        </p>
      </div>

      <div className="flex flex-col grow min-h-0 overflow-hidden">
        {loading ? (
          <p className="text-gray-400 text-sm">Loading...</p>
        ) : error ? (
          <p className="text-red-500 text-sm">Failed to load devices: {error}</p>
        ) : (
          <DataTable columns={COLUMNS} data={devices} selectedId={selectedId} onSelectRow={setSelectedId} />
        )}
      </div>

      <div className="flex min-h-fit min-w-fit">
        <ColorButton
          className="mr-1"
          color="var(--confirm-green)"
          onClick={() => navigate("/admin/hardware/add")}
        >
          Add Device
        </ColorButton>
        <ColorButton
          className="mr-1"
          color="var(--back-gray)"
          textColor="black"
          disabled={selectedId === null}
          onClick={() => navigate(`/admin/hardware/edit/${selectedDevice?.model_name}`)}
        >
          View/Edit Details
        </ColorButton>
        <ColorButton color="var(--warning-red)" disabled={selectedId === null} onClick={() => setShowModal(true)}>
          Remove Device
        </ColorButton>
      </div>

      {showModal && selectedDevice && (
        <ConfirmModal
          title="Remove Device"
          message={`You are about to permanently remove "${selectedDevice.model_name}" from the database. This action cannot be undone.`}
          checkboxLabel="I understand this action is permanent."
          confirmLabel="Remove Device"
          cancelLabel="Go Back"
          loading={deleting}
          onConfirm={handleConfirmRemove}
          onCancel={() => setShowModal(false)}
        />
      )}
    </div>
  );
}
