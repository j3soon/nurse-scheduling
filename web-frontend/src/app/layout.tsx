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
        <footer style={{ textAlign: 'center', padding: '1.5rem', marginTop: '2rem', fontSize: '0.875rem', color: 'gray' }}>
          <div>
            <a href="https://github.com/j3soon/nurse-scheduling/blob/main/LICENSE" target="_blank" rel="noopener noreferrer" className="footer-link">Copyright ©</a>{' '}
            <a href="https://github.com/j3soon/nurse-scheduling/graphs/code-frequency" target="_blank" rel="noopener noreferrer" className="footer-link">2023-{new Date().getFullYear()}</a>{' '}
            <a href="https://github.com/j3soon" target="_blank" rel="noopener noreferrer" className="footer-link">Johnson Sun</a> &{' '}
            <a href="https://github.com/j3soon/nurse-scheduling#acknowledgments" target="_blank" rel="noopener noreferrer" className="footer-link">Contributors</a>.
          </div>
          <div>
            <a href="https://github.com/j3soon/nurse-scheduling" target="_blank" rel="noopener noreferrer" className="footer-link">Nurse Scheduling Project</a>{' '}
            <a href="https://github.com/j3soon/nurse-scheduling/releases" target="_blank" rel="noopener noreferrer" className="footer-link">v0.0.0</a>.{' '}
            Licensed under{' '}
            <a href="https://www.gnu.org/licenses/agpl-3.0.html" target="_blank" rel="noopener noreferrer" className="footer-link">AGPL-3.0</a>.
          </div>
        </footer>
      </body>
    </html>
  );
}
