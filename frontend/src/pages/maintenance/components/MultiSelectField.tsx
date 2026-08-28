type MultiSelectFieldProps = {
    label: string;
    options: string[];
    selected: string[];
    onChange: (selected: string[]) => void;
    disabled?: boolean;
};

export default function MultiSelectField({ label, options, selected, onChange, disabled }: MultiSelectFieldProps) {
    function toggle(name: string) {
        if (selected.includes(name)) {
            onChange(selected.filter((s) => s !== name));
        } else {
            onChange([...selected, name]);
        }
    }

    return (
        <div className="grid grid-cols-[180px_1fr] items-start gap-x-4">
            <span className="text-right text-sm text-gray-700 pt-2">{label}</span>
            <div
                className={[
                    "max-h-36 overflow-y-auto border border-gray-200 rounded px-3 py-2 text-sm",
                    disabled ? "bg-gray-200 text-gray-400" : "bg-gray-100",
                ].join(" ")}
            >
                {options.length === 0 ? (
                    <span className="text-gray-400 text-xs">No options available</span>
                ) : (
                    options.map((name) => (
                        <label key={name} className="flex items-center gap-2 py-0.5 cursor-pointer">
                            <input
                                type="checkbox"
                                checked={selected.includes(name)}
                                onChange={() => toggle(name)}
                                disabled={disabled}
                                className="accent-[var(--confirm-green)]"
                            />
                            {name}
                        </label>
                    ))
                )}
            </div>
        </div>
    );
}
