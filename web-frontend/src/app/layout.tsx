/*
 * This file is part of Nurse Scheduling Project, see <https://github.com/j3soon/nurse-scheduling>.
 *
 * Copyright (C) 2023-2025 Johnson Sun
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
import type { Metadata } from "next";
import Script from "next/script";
import Navigation from "@/components/Navigation";
import VersionWarningBanner from "@/components/VersionWarningBanner";
import { CURRENT_APP_VERSION } from "@/utils/version";
import {
  GITHUB_REPO_URL,
  GITHUB_TAGS_URL,
  GITHUB_LICENSE_URL,
  GITHUB_CODE_FREQUENCY_URL,
  GITHUB_ACKNOWLEDGMENTS_URL,
  GITHUB_AUTHOR_URL,
  AGPL_LICENSE_URL,
} from "@/constants/urls";
import "./globals.css";

export const metadata: Metadata = {
  title: "Nurse Scheduling System",
  description: "A user-friendly web app to automate the nurse scheduling task.",
  icons: {
    icon: "/favicon.svg",
  },
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
        <VersionWarningBanner />
        <Navigation />
        <main style={{ paddingLeft: '2.5rem', paddingRight: '2.5rem' }}>
          {children}
        </main>
        <footer style={{ textAlign: 'center', padding: '1.5rem', marginTop: '2rem', fontSize: '0.875rem', color: 'gray' }}>
          <div>
            <a href={GITHUB_LICENSE_URL} target="_blank" rel="noopener noreferrer" className="footer-link">Copyright ©</a>{' '}
            <a href={GITHUB_CODE_FREQUENCY_URL} target="_blank" rel="noopener noreferrer" className="footer-link">2023-{new Date().getFullYear()}</a>{' '}
            <a href={GITHUB_AUTHOR_URL} target="_blank" rel="noopener noreferrer" className="footer-link">Johnson Sun</a> &{' '}
            <a href={GITHUB_ACKNOWLEDGMENTS_URL} target="_blank" rel="noopener noreferrer" className="footer-link">Contributors</a>.
          </div>
          <div>
            <a href={GITHUB_REPO_URL} target="_blank" rel="noopener noreferrer" className="footer-link">Nurse Scheduling Project</a>{' '}
            <a href={GITHUB_TAGS_URL} target="_blank" rel="noopener noreferrer" className="footer-link">{CURRENT_APP_VERSION}</a>.{' '}
            Licensed under{' '}
            <a href={AGPL_LICENSE_URL} target="_blank" rel="noopener noreferrer" className="footer-link">AGPL-3.0</a>.
          </div>
        </footer>
      </body>
    </html>
  );
}
