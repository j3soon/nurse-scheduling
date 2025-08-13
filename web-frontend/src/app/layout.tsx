// The layout for the entire app
import type { Metadata } from "next";
import Navigation from "@/components/Navigation";
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
        <Navigation />
        <main style={{ paddingLeft: '2.5rem', paddingRight: '2.5rem' }}>
          {children}
        </main>
      </body>
    </html>
  );
}
