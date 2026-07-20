import { cn } from "@/lib/utils";

export function StatTile({
  label,
  value,
  sub,
  tone = "default",
  className,
}: {
  label: string;
  value: React.ReactNode;
  sub?: React.ReactNode;
  tone?: "default" | "buy" | "sell" | "muted";
  className?: string;
}) {
  return (
    <div className={cn("rounded-lg border border-border bg-card p-4", className)}>
      <div className="text-xs font-medium text-muted-foreground">{label}</div>
      <div
        className={cn(
          "mt-1 text-xl font-semibold tabular-nums",
          tone === "buy" && "text-buy",
          tone === "sell" && "text-sell",
          tone === "muted" && "text-muted-foreground"
        )}
      >
        {value}
      </div>
      {sub && <div className="mt-0.5 text-xs text-muted-foreground">{sub}</div>}
    </div>
  );
}
