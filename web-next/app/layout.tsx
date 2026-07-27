import type { Metadata, Viewport } from "next";
import { Fraunces, Hanken_Grotesk } from "next/font/google";
import { Theme } from "@astryxdesign/core";
import { freemapTheme } from "@/theme/freemap";
import "./globals.css";

// Editorial pairing: a characterful optical serif for display, a clean
// grotesque for UI/body. Deliberately not Inter/Geist.
const fraunces = Fraunces({
  // --font-display, NOT --font-heading: the Tailwind @theme token --font-heading
  // is mapped to this in globals.css. Using --font-heading here collided with the
  // theme token and the serif silently never rendered.
  variable: "--font-display",
  subsets: ["latin"],
  axes: ["opsz", "SOFT"],
  display: "swap",
});

const hanken = Hanken_Grotesk({
  variable: "--font-sans",
  subsets: ["latin"],
  display: "swap",
});

const SITE = "https://freemap-seattle.vercel.app";

export const metadata: Metadata = {
  metadataBase: new URL(SITE),
  title: {
    default: "FreeMap — Free & BOGO deals near you",
    template: "%s · FreeMap",
  },
  description:
    "A live, interactive map of verified free and buy-one-get-one deals across Seattle and Atlanta, refreshed daily.",
  keywords: ["Seattle", "Atlanta", "free deals", "BOGO", "free food", "free stuff", "map"],
  applicationName: "FreeMap",
  openGraph: {
    type: "website",
    url: SITE,
    siteName: "FreeMap",
    title: "FreeMap — Free & BOGO deals near you",
    description:
      "A live map of verified free and BOGO deals across Seattle and Atlanta.",
  },
  twitter: {
    card: "summary_large_image",
    title: "FreeMap",
    description: "A live map of free & BOGO deals across Seattle and Atlanta.",
  },
  icons: {
    icon: [{ url: "/icon.svg", type: "image/svg+xml" }, { url: "/favicon.ico" }],
  },
};

export const viewport: Viewport = {
  themeColor: "#1f7a4d",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html
      lang="en"
      className={`${fraunces.variable} ${hanken.variable} h-full antialiased`}
    >
      <body className="min-h-full">
        <Theme theme={freemapTheme} mode="light">
          {children}
        </Theme>
      </body>
    </html>
  );
}
