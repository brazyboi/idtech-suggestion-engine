import { type ReactNode } from "react";

interface GenericButtonProps {
    onClick?: () => void;
    children?: ReactNode;
    className?: string;
    disabled?: boolean;
}

export default function GenericButton({
    onClick,
    children,
    className = "btn-accent",
    disabled = false,
}: GenericButtonProps) {
    return (
        <button
            onClick={onClick}
            disabled={disabled}
            className={`hover:cursor-pointer rounded-xl px-4 py-2 ${className} ${disabled ? "opacity-50 cursor-not-allowed" : ""}`}
        >
            {children ?? "Button"}
        </button>
    );
};
