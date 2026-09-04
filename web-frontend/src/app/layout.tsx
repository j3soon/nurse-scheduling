/*
 * This file is part of Nurse Scheduling Project, see <https://github.com/j3soon/nurse-scheduling>.
 *
 * Copyright (C) 2023-2026 Johnson Sun
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU Affero General Public License as
 * published by the Free Software Foundation, either version 3 of the
 * License, or (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU Affero General Public License for more details.
 *
 * You should have received a copy of the GNU Affero General Public License
 * along with this program.  If not, see <https://www.gnu.org/licenses/>.
 */

// The layout for the entire app
import type { Metadata, Viewport } from "next";
import Script from "next/script";
import Navigation from "@/components/Navigation";
import Footer from "@/components/Footer";
import VersionWarningBanner from "@/components/VersionWarningBanner";
import { SchedulingDataProvider } from "@/hooks/useSchedulingData";
import { UnsavedEditingStateProvider } from "@/utils/unsavedEditingState";
import "./globals.css";

export const metadata: Metadata = {
  title: "Nurse Scheduling System",
  description: "A user-friendly web app to automate the nurse scheduling task.",
  icons: {
    icon: "/favicon.svg",
  },
};

export const viewport: Viewport = {
  colorScheme: "light",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>
        <Script
          async
          src={`https://www.googletagmanager.com/gtag/js?id=${process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID}`}
          strategy="afterInteractive"
        />
        <Script id="google-analytics" strategy="afterInteractive">
          {`
            window.dataLayer = window.dataLayer || [];
            function gtag(){dataLayer.push(arguments);}
            gtag('js', new Date());

            gtag('config', '${process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID}');
          `}
        </Script>
        <UnsavedEditingStateProvider>
          <SchedulingDataProvider>
            <VersionWarningBanner />
            <Navigation />
            <main style={{ paddingLeft: '2.5rem', paddingRight: '2.5rem' }}>
              {children}
            </main>
            <Footer />
          </SchedulingDataProvider>
        </UnsavedEditingStateProvider>
      </body>
    </html>
  );
}
