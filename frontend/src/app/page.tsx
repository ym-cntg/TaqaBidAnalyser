"use client";

import { useEffect, useState } from "react";

type RfqCountResponse = {
  row_count?: number;
  catalog?: string;
  schema?: string;
  error?: string;
};

export default function Home() {
  const [result, setResult] = useState<RfqCountResponse | null>(null);
  const [status, setStatus] = useState<"loading" | "ok" | "error">("loading");

  useEffect(() => {
    fetch("/api/rfq-count")
      .then((res) => res.json())
      .then((data: RfqCountResponse) => {
        setResult(data);
        setStatus(data.error ? "error" : "ok");
      })
      .catch((err) => {
        setResult({ error: String(err) });
        setStatus("error");
      });
  }, []);

  return (
    <main style={{ fontFamily: "monospace", padding: "2rem", maxWidth: 640 }}>
      <h1>Maximo Integration — Connectivity Check</h1>
      {status === "loading" && <p>Connecting to Unity Catalog...</p>}
      {status === "ok" && result && (
        <p>
          ✅ Connected. <code>{result.catalog}.{result.schema}.rfq</code> has{" "}
          <strong>{result.row_count?.toLocaleString()}</strong> rows.
        </p>
      )}
      {status === "error" && (
        <div>
          <p>❌ Connection failed.</p>
          <pre style={{ whiteSpace: "pre-wrap", color: "crimson" }}>
            {result?.error}
          </pre>
        </div>
      )}
    </main>
  );
}
