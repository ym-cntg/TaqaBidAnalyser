export const metadata = {
  title: "TAQA Maximo Integration",
  description: "Deployment connectivity check against real Maximo data",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
