

export default function ColorButton({ children, className, textColor, color, onClick, disabled }: { children: React.ReactNode; className?: string; textColor?: string; color: string; onClick: () => void; disabled?: boolean }) {
    return (
        <button
            onClick={disabled ? undefined : onClick}
            disabled={disabled}
            style={{ backgroundColor: color, color: `${textColor ?? "white"}` }}
            className={[
                className ?? "",
                "font-bold py-2 px-4 rounded-2xl",
                disabled ? "opacity-50 cursor-not-allowed" : "cursor-pointer",
            ].join(" ")}
        >
            {children}
        </button>
    );
}