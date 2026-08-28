import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import ColorButton from "./components/ColorButton";
import FormField from "./components/FormField";
import MultiSelectField from "./components/MultiSelectField";

type HardwareForm = {
    model_name: string;
    operate_temperature: string;
    input_power: string;
    ip_rating: string;
    ik_rating: string;
    interface: string;
    categories: string[];
    use_cases: string[];
    software: string[];
};

export default function EditHardware() {
    const navigate = useNavigate();
    const { name } = useParams<{ name: string }>();
    const [form, setForm] = useState<HardwareForm>({
        model_name: "",
        operate_temperature: "",
        input_power: "",
        ip_rating: "",
        ik_rating: "",
        interface: "",
        categories: [],
        use_cases: [],
        software: [],
    });
    const [options, setOptions] = useState<{ categories: string[]; useCases: string[]; software: string[] }>({
        categories: [], useCases: [], software: [],
    });
    const [submitting, setSubmitting] = useState(false);
    const [error, setError] = useState<string | null>(null);

    function setField(key: keyof HardwareForm) {
        return (value: string) => setForm((prev) => ({ ...prev, [key]: value }));
    }

    useEffect(() => {
        fetch(`http://localhost:8000/api/maintenance/hardware/${name}`)
            .then((res) => {
                if (!res.ok) throw new Error(`Server error: ${res.status}`);
                return res.json();
            })
            .then((data) => {
                setForm({
                    model_name: data.model_name ?? "",
                    operate_temperature: data.operate_temperature ?? "",
                    input_power: data.input_power ?? "",
                    ip_rating: data.ip_rating ?? "",
                    ik_rating: data.ik_rating ?? "",
                    interface: data.interface ?? "",
                    categories: data.categories ?? [],
                    use_cases: data.use_cases ?? [],
                    software: data.software ?? [],
                });
            })
            .catch((err) => setError(err.message));
    }, [name]);

    useEffect(() => {
        Promise.all([
            fetch("http://localhost:8000/api/maintenance/categories").then((r) => r.json()),
            fetch("http://localhost:8000/api/maintenance/use-cases").then((r) => r.json()),
            fetch("http://localhost:8000/api/maintenance/software").then((r) => r.json()),
        ]).then(([cats, useCases, sw]) => {
            setOptions({
                categories: cats.map((x: { name: string }) => x.name),
                useCases: useCases.map((x: { name: string }) => x.name),
                software: sw.map((x: { name: string }) => x.name),
            });
        }).catch(() => {});
    }, []);

    async function handleSubmit() {
        if (!form.model_name.trim()) {
            setError("Model Name is required.");
            return;
        }
        setError(null);
        setSubmitting(true);
        try {
            const payload = {
                model_name: form.model_name.trim(),
                operate_temperature: form.operate_temperature.trim() || null,
                input_power: form.input_power.trim() || null,
                ip_rating: form.ip_rating.trim() || null,
                ik_rating: form.ik_rating.trim() || null,
                interface: form.interface.trim() || null,
                categories: form.categories,
                use_cases: form.use_cases,
                software: form.software,
            };
            const res = await fetch(`http://localhost:8000/api/maintenance/hardware/${name}`, {
                method: "PATCH",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
            });
            if (!res.ok) {
                const data = await res.json().catch(() => ({}));
                throw new Error(data.detail ?? `Server error: ${res.status}`);
            }
            navigate("/admin");
        } catch (err) {
            setError(err instanceof Error ? err.message : "Unknown error");
            setSubmitting(false);
        }
    }

    return (
        <div className="flex flex-col p-0 text-black grow min-h-0">
            <div className="mb-4">
                <h1 className="font-semibold text-2xl">Edit Device</h1>
                <p className="text-gray-600 text-sm">
                    To add a device to the pool of devices that the AI can recommend, fill in the
                    following fields and press "Save Changes."
                </p>
            </div>

            <div className="flex flex-col gap-3 flex-1 overflow-y-auto min-h-0 pb-4">
                <h2 className="font-semibold text-xl">Hardware Device Details</h2>
                <FormField label="Model Name" value={form.model_name} onChange={setField("model_name")} required disabled />
                <FormField label="Operating Temperature" value={form.operate_temperature} onChange={setField("operate_temperature")} />
                <FormField label="Input Power" value={form.input_power} onChange={setField("input_power")} />
                <FormField label="IP Rating" value={form.ip_rating} onChange={setField("ip_rating")} />
                <FormField label="IK Rating" value={form.ik_rating} onChange={setField("ik_rating")} />
                <FormField label="Interface" value={form.interface} onChange={setField("interface")} />
                <MultiSelectField
                    label="Categories"
                    options={options.categories}
                    selected={form.categories}
                    onChange={(v) => setForm((prev) => ({ ...prev, categories: v }))}
                />
                <MultiSelectField
                    label="Use Cases"
                    options={options.useCases}
                    selected={form.use_cases}
                    onChange={(v) => setForm((prev) => ({ ...prev, use_cases: v }))}
                />
                <MultiSelectField
                    label="Software"
                    options={options.software}
                    selected={form.software}
                    onChange={(v) => setForm((prev) => ({ ...prev, software: v }))}
                />
            </div>

            {error && <p className="text-red-500 text-sm mt-2">{error}</p>}

            <div className="flex gap-2 pt-2 shrink-0">
                <ColorButton
                    color="var(--confirm-green)"
                    onClick={handleSubmit}
                    disabled={submitting}
                >
                    Save Changes
                </ColorButton>
                <ColorButton
                    color="var(--back-gray)"
                    textColor="black"
                    onClick={() => navigate("/admin")}
                    disabled={submitting}
                >
                    Back
                </ColorButton>
            </div>
        </div>
    );
}
