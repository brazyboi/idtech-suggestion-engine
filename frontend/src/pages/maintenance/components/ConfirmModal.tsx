import { useState } from "react";
import ColorButton from "./ColorButton";

type ConfirmModalProps = {
    title: string;
    message: string;
    checkboxLabel: string;
    confirmLabel?: string;
    cancelLabel?: string;
    loading?: boolean;
    onConfirm: () => void;
    onCancel: () => void;
};

export default function ConfirmModal({
    title,
    message,
    checkboxLabel,
    confirmLabel = "Confirm",
    cancelLabel = "Cancel",
    loading = false,
    onConfirm,
    onCancel,
}: ConfirmModalProps) {
    const [checked, setChecked] = useState(false);

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
            <div className="bg-white rounded-xl shadow-xl p-6 w-full max-w-md flex flex-col gap-4">
                <div>
                    <h2 className="font-semibold text-xl text-black">{title}</h2>
                    <p className="text-gray-600 text-sm mt-1">{message}</p>
                </div>

                <label className="flex items-center gap-2 cursor-pointer select-none text-sm text-gray-700">
                    <input
                        type="checkbox"
                        checked={checked}
                        onChange={(e) => setChecked(e.target.checked)}
                        className="w-4 h-4 accent-[var(--confirm-green)] cursor-pointer"
                    />
                    {checkboxLabel}
                </label>

                <div className="flex gap-2">
                    <ColorButton
                        color="var(--warning-red)"
                        disabled={!checked || loading}
                        onClick={onConfirm}
                    >
                        {confirmLabel}
                    </ColorButton>
                    <ColorButton
                        color="var(--back-gray)"
                        textColor="black"
                        disabled={loading}
                        onClick={onCancel}
                    >
                        {cancelLabel}
                    </ColorButton>
                </div>
            </div>
        </div>
    );
}
