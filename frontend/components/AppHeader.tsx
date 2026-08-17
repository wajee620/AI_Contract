"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, Contract } from "@/lib/api";

/** The sticky app shell nav from the Covenant design: brand, tab pills for the
 *  active contract, the current-contract chip, and an Upload shortcut. */
export default function AppHeader({ contractId }: { contractId: string }) {
  const pathname = usePathname();
  const router = useRouter();
  const [contract, setContract] = useState<Contract | null>(null);

  useEffect(() => {
    let alive = true;
    api
      .getContract(contractId)
      .then((c) => alive && setContract(c))
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [contractId]);

  const base = `/contracts/${contractId}`;
  const tabs = [
    { href: base, label: "Overview" },
    { href: `${base}/obligations`, label: "Tracker" },
    { href: `${base}/calendar`, label: "Calendar" },
    { href: `${base}/risks`, label: "Risks" },
    { href: `${base}/review`, label: "Review" },
    { href: `${base}/ask`, label: "Ask" },
  ];

  const parties = contract?.meta?.parties?.length
    ? contract.meta.parties.join(" ↔ ")
    : contract?.filename;

  return (
    <div className="appbar">
      <div className="appbar-inner">
        <Link href="/" className="brand">
          Covenant
        </Link>
        <div className="nav-pills">
          {tabs.map((t) => (
            <Link key={t.href} href={t.href} className={`nav-pill ${pathname === t.href ? "active" : ""}`}>
              {t.label}
            </Link>
          ))}
        </div>
        <div className="flex items-center gap-12">
          {parties && (
            <span className="chip" title={contract?.filename}>
              {parties.length > 46 ? parties.slice(0, 44) + "…" : parties}
            </span>
          )}
          <button className="btn btn-ghost btn-sm" onClick={() => router.push("/contracts")}>
            Upload
          </button>
        </div>
      </div>
    </div>
  );
}
