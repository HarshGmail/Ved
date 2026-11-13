import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { INSTALL_CAPTURE_SCRIPT } from "./install-prompt";
import { InstallBanner } from "./install-banner";
import { LaunchSplash } from "./launch-splash";
import { ServiceWorkerRegistration } from "./service-worker-registration";

const SPLASH_DEVICES = [
  { width: 1290, height: 2796, ratio: 3 },
  { width: 1179, height: 2556, ratio: 3 },
  { width: 1284, height: 2778, ratio: 3 },
  { width: 1170, height: 2532, ratio: 3 },
  { width: 1125, height: 2436, ratio: 3 },
  { width: 1242, height: 2688, ratio: 3 },
  { width: 828, height: 1792, ratio: 2 },
  { width: 1242, height: 2208, ratio: 3 },
  { width: 750, height: 1334, ratio: 2 },
  { width: 2048, height: 2732, ratio: 2 },
  { width: 1668, height: 2388, ratio: 2 },
];

function startupImageFor({ width, height, ratio }: (typeof SPLASH_DEVICES)[number]) {
  const cssWidth = width / ratio;
  const cssHeight = height / ratio;
  return {
    url: `/splash/${width}x${height}.png`,
    media: `(device-width: ${cssWidth}px) and (device-height: ${cssHeight}px) and (-webkit-device-pixel-ratio: ${ratio}) and (orientation: portrait)`,
  };
}

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Ved",
  description: "Personal AI operating layer",
  appleWebApp: {
    capable: true,
    title: "Ved",
    statusBarStyle: "black-translucent",
    startupImage: SPLASH_DEVICES.map(startupImageFor),
  },
};

export const viewport: Viewport = {
  themeColor: "#000000",
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable}`}>
      <head>
        <link rel="manifest" href="/app-manifest" crossOrigin="use-credentials" />
        <script dangerouslySetInnerHTML={{ __html: INSTALL_CAPTURE_SCRIPT }} />
      </head>
      <body>
        <LaunchSplash />
        <InstallBanner />
        {children}
        <ServiceWorkerRegistration />
      </body>
    </html>
  );
}
