import type { Metadata } from "next";
import { ConnectionsPanel } from "../connections-panel";

export const metadata: Metadata = {
  title: "Connections · Ved",
};

export default function ConnectionsPage() {
  return <ConnectionsPanel />;
}
