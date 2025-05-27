'use client';

import { usePathname, useRouter } from 'next/navigation';

export default function Navigation() {
  const router = useRouter();
  const pathname = usePathname();

  const tabs = [
    { name: '0. Home', path: '/' },
    { name: '1. People', path: '/people' },
  ];

  return (
    <nav className="bg-white shadow-sm">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex space-x-8">
          {tabs.map((tab) => (
            <button
              key={tab.path}
              onClick={() => router.push(tab.path)}
              className={`py-4 px-1 border-b-2 font-medium text-sm ${
                pathname === tab.path
                  ? 'border-blue-500 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              }`}
            >
              {tab.name}
            </button>
          ))}
        </div>
      </div>
    </nav>
  );
} 