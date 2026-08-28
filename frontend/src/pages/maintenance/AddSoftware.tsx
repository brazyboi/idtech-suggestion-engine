import { useState } from "react";
import { useNavigate } from "react-router-dom";
import ColorButton from "./components/ColorButton";
import FormField from "./components/FormField";

type SoftwareForm = {
    software_name: string;
};

export default function AddSoftware() {
    const navigate = useNavigate();
    const [form, setForm] = useState<SoftwareForm>({
        software_name: "",
    });
    const [submitting, setSubmitting] = useState(false);
    const [error, setError] = useState<string | null>(null);

    function setField(key: keyof SoftwareForm) {
        return (value: string) => setForm((prev) => ({ ...prev, [key]: value }));
    }

    async function handleSubmit() {
        if (!form.software_name.trim()) {
            setError("Software Name is required.");
            return;
        }
        setError(null);
        setSubmitting(true);
        try {
            const payload = {
                name: form.software_name.trim(),
            };
            const res = await fetch("http://localhost:8000/api/maintenance/software/", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
            });
            console.log(res);
            if (!res.ok) {
                const data = await res.json().catch(() => ({}));
                throw new Error(data.detail ?? `Server error: ${res.status}`);
            }
            navigate("/admin/software");
        } catch (err) {
            setError(err instanceof Error ? err.message : "Unknown error");
            setSubmitting(false);
        }
    }

    return (
        <div className="flex flex-col p-0 text-black grow gap-4 min-h-0">
            <div>
                <h1 className="font-semibold text-2xl">Add Software</h1>
                <p className="text-gray-600 text-sm">
                    To add software to the pool of software that the AI can recommend, fill in the
                    following fields and press "Add Software."
                </p>
            </div>

            <div className="flex flex-col gap-3">
                <h2 className="font-semibold text-xl">Software Details</h2>
                <FormField label="Software Name" value={form.software_name} onChange={setField("software_name")} required />
            </div>

            {error && <p className="text-red-500 text-sm">{error}</p>}

            <div className="flex gap-2">
                <ColorButton
                    color="var(--confirm-green)"
                    onClick={handleSubmit}
                    disabled={submitting}
                >
                    Submit
                </ColorButton>
                <ColorButton
                    color="var(--warning-red)"
                    onClick={() => navigate("/admin/software")}
                    disabled={submitting}
                >
                    Back
                </ColorButton>
            </div>
        </div>
    );
}
