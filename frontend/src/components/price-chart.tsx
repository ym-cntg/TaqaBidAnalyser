"use client";

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import type { BOQExtraction } from "@/lib/api";

const COLORS = [
  "#2563eb",
  "#16a34a",
  "#dc2626",
  "#9333ea",
  "#ea580c",
  "#0891b2",
];

interface PriceChartProps {
  extractions: Record<string, BOQExtraction[]>;
}

export function PriceChart({ extractions }: PriceChartProps) {
  const bidders = Object.keys(extractions);
  if (bidders.length === 0) {
    return (
      <div className="h-64 flex items-center justify-center text-muted-foreground">
        No data available
      </div>
    );
  }

  // Build chart data: each round is an x-axis point
  const allRounds = new Set<string>();
  for (const exts of Object.values(extractions)) {
    for (const ext of exts) {
      allRounds.add(ext.round_name);
    }
  }

  const roundOrder = ["original", "round1", "round2", "round3", "round4"];
  const sortedRounds = [...allRounds].sort(
    (a, b) => roundOrder.indexOf(a) - roundOrder.indexOf(b)
  );

  const data = sortedRounds.map((round) => {
    const point: Record<string, string | number> = {
      round: round.charAt(0).toUpperCase() + round.slice(1),
    };
    for (const [bidder, exts] of Object.entries(extractions)) {
      const ext = exts.find((e) => e.round_name === round);
      if (ext?.total_contract_price) {
        point[bidder] = Math.round(ext.total_contract_price / 1_000_000);
      }
    }
    return point;
  });

  return (
    <ResponsiveContainer width="100%" height={320}>
      <LineChart data={data}>
        <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
        <XAxis dataKey="round" className="text-xs" />
        <YAxis
          className="text-xs"
          tickFormatter={(val) => `${val}M`}
          domain={["auto", "auto"]}
        />
        <Tooltip
          formatter={(value) => [`AED ${value}M`, ""]}
          contentStyle={{
            backgroundColor: "var(--card)",
            border: "1px solid var(--border)",
            borderRadius: "8px",
          }}
        />
        <Legend />
        {bidders.map((bidder, idx) => (
          <Line
            key={bidder}
            type="monotone"
            dataKey={bidder}
            stroke={COLORS[idx % COLORS.length]}
            strokeWidth={2.5}
            dot={{ r: 5 }}
            activeDot={{ r: 7 }}
            connectNulls
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}
