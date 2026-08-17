import AppHeader from "@/components/AppHeader";

export default function ContractLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: { id: string };
}) {
  return (
    <div>
      <AppHeader contractId={params.id} />
      <div className="wrap">{children}</div>
    </div>
  );
}
