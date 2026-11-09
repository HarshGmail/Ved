const CANVAS = "#000000";

export const dynamic = "force-static";

const APP_MANIFEST = {
  name: "Ved",
  short_name: "Ved",
  description: "Personal AI operating layer",
  start_url: "/",
  display: "standalone",
  background_color: CANVAS,
  theme_color: CANVAS,
  icons: [
    { src: "/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
    { src: "/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
    { src: "/icon-maskable-192.png", sizes: "192x192", type: "image/png", purpose: "maskable" },
    { src: "/icon-maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
  ],
};

export function GET() {
  return new Response(JSON.stringify(APP_MANIFEST), {
    headers: { "content-type": "application/manifest+json", "cache-control": "public, max-age=3600" },
  });
}
