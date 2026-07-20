import { WatchlistTile } from "./watchlist-tile";
import type { Instrument } from "@/types/api";

export function WatchlistSection({ instruments }: { instruments: Instrument[] }) {
  if (instruments.length === 0) {
    return <p className="text-sm text-muted-foreground">監視中の通貨ペアはありません。</p>;
  }
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
      {instruments.map((inst) => (
        <WatchlistTile key={inst.symbol} instrument={inst} />
      ))}
    </div>
  );
}
