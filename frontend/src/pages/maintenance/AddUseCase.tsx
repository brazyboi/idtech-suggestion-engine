import { useState } from "react";
import { useNavigate } from "react-router-dom";
import ColorButton from "./components/ColorButton";
import FormField from "./components/FormField";

type UseCaseForm = {
    name: string;
};

export default function AddUseCase() {
    const navigate = useNavigate();
    const [form, setForm] = useState<UseCaseForm>({ name: "" });
    const [submitting, setSubmitting] = useState(false);
    const [error, setError] = useState<string | null>(null);

    async function handleSubmit() {
        if (!form.name.trim()) {
            setError("Use Case Name is required.");
            return;
        }
        setError(null);
        setSubmitting(true);
        try {
            const res = await fetch("http://localhost:8000/api/maintenance/use-cases", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ name: form.name.trim() }),
            });
            if (!res.ok) {
                const data = await res.json().catch(() => ({}));
                throw new Error(data.detail ?? `Server error: ${res.status}`);
            }
            navigate("/admin/use-cases");
        } catch (err) {
            setError(err instanceof Error ? err.message : "Unknown error");
            setSubmitting(false);
        }
    }

    return (
        <div className="flex flex-col p-0 text-black grow min-h-0">
            <div className="mb-4">
                <h1 className="font-semibold text-2xl">Add Use Case</h1>
                <p className="text-gray-600 text-sm">
                    Add a new use case that can be assigned to hardware devices.
                </p>
            </div>

            <div className="flex flex-col gap-3 flex-1 overflow-y-auto min-h-0 pb-4">
                <h2 className="font-semibold text-xl">Use Case Details</h2>
                <FormField
                    label="Use Case Name"
                    value={form.name}
                    onChange={(v) => setForm({ name: v })}
                    required
                />
            </div>

            {error && <p className="text-red-500 text-sm mt-2">{error}</p>}

            <div className="flex gap-2 pt-2 shrink-0">
                <ColorButton
                    color="var(--confirm-green)"
                    onClick={handleSubmit}
                    disabled={submitting}
                >
                    Add Use Case
                </ColorButton>
                <ColorButton
                    color="var(--back-gray)"
                    textColor="black"
                    onClick={() => navigate("/admin/use-cases")}
                    disabled={submitting}
                >
                    Back
                </ColorButton>
            </div>
        </div>
    );
}
