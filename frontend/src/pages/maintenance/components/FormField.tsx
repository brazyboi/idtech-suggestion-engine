type FormFieldProps = {
    label: string;
    value: string;
    onChange: (value: string) => void;
    required?: boolean;
    placeholder?: string;
    disabled?: boolean;
};

export default function FormField({ label, value, onChange, required, placeholder, disabled }: FormFieldProps) {
    return (
        <div className="grid grid-cols-[180px_1fr] items-center gap-x-4">
            <label className="text-right text-sm text-gray-700">
                {label}
                {required && <span className="text-red-500 ml-0.5">*</span>}
            </label>
            <input
                type="text"
                value={value}
                onChange={(e) => onChange(e.target.value)}
                placeholder={placeholder}
                disabled={disabled}
                className={[
                    "rounded px-3 py-2 text-sm w-full focus:outline-none focus:ring-1 focus:ring-gray-300",
                    disabled
                        ? "bg-gray-200 text-gray-400 cursor-not-allowed"
                        : "bg-gray-100",
                ].join(" ")}
            />
        </div>
    );
}
