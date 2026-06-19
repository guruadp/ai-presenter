import { ReactNode } from "react";

type Variant = "default" | "indigo" | "green" | "amber" | "red";

interface BadgeProps {
  variant?: Variant;
  children: ReactNode;
}

const styles: Record<Variant, string> = {
  default: "bg-gray-100 text-gray-600",
  indigo: "bg-indigo-50 text-indigo-700",
  green: "bg-emerald-50 text-emerald-700",
  amber: "bg-amber-50 text-amber-700",
  red: "bg-red-50 text-red-700",
};

export default function Badge({ variant = "default", children }: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center text-xs font-medium px-2 py-0.5 rounded-full ${styles[variant]}`}
    >
      {children}
    </span>
  );
}
