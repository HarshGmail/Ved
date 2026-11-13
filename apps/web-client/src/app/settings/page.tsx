import type { Metadata } from "next";
import { SettingsPanel } from "./settings-panel";

export const metadata: Metadata = {
  title: "Settings · Ved",
};

export default function SettingsPage() {
  return <SettingsPanel />;
}
