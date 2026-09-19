import type { MetadataRoute } from "next";

const CANVAS = "#000000";

export default function manifest(): MetadataRoute.Manifest {
  return {
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
      {
        src: "/icon-maskable-192.png",
        sizes: "192x192",
        type: "image/png",
        purpose: "maskable",
      },
      {
        src: "/icon-maskable-512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "maskable",
      },
    ],
  };
}
