// A component for the navigation top bar, side buttons, and keyboard shortcuts
'use client';

import { usePathname, useRouter } from 'next/navigation';
import { useEffect } from 'react';

export default function Navigation() {
  const router = useRouter();
  const pathname = usePathname();

  const tabs = [
    { name: '0. Home', path: '/' },
    { name: '1. Dates', path: '/dates' },
    { name: '2. People', path: '/people' },
    { name: '3. Shift Types', path: '/shift-types' },
    { name: '4. Shift Type Requirements', path: '/shift-type-requirements' },
    { name: '5. Shift Requests', path: '/shift-requests' },
    { name: '6. Shift Type Successions', path: '/shift-type-successions' },
    { name: '7. Shift Counts', path: '/shift-counts' },
    { name: '8. Shift Affinities', path: '/shift-affinities' },
    { name: '9. Save and Load', path: '/save-and-load' },
  ];

  const currentTabIndex = tabs.findIndex(tab => tab.path === pathname);

  const navigateToTab = (index: number) => {
    if (index < 0 || index >= tabs.length || index === currentTabIndex) {
      return;
    }
    router.push(tabs[index].path);
  };

  const navigatePrevious = () => navigateToTab(currentTabIndex - 1);
  const navigateNext = () => navigateToTab(currentTabIndex + 1);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      // Only handle keyboard shortcuts when no input/textarea/select is focused
      const activeElement = document.activeElement;
      const isInputFocused = activeElement && (
        activeElement.tagName === 'INPUT' ||
        activeElement.tagName === 'TEXTAREA' ||
        activeElement.tagName === 'SELECT' ||
        activeElement.getAttribute('contenteditable') === 'true'
      );

      if (isInputFocused) return;

      switch (event.key) {
        case '0':
        case '1':
        case '2':
        case '3':
        case '4':
        case '5':
        case '6':
        case '7':
        case '8':
        case '9': {
          event.preventDefault();
          const index = parseInt(event.key);
          if (index < tabs.length) {
            navigateToTab(index);
          }
          break;
        }

        case 'ArrowLeft':
          event.preventDefault();
          navigatePrevious();
          break;

        case 'ArrowRight':
          event.preventDefault();
          navigateNext();
          break;

        case 'ArrowUp':
          event.preventDefault();
          window.scrollBy({
            top: -window.innerHeight,
            behavior: 'smooth'
          });
          break;

        case 'ArrowDown':
          event.preventDefault();
          window.scrollBy({
            top: window.innerHeight,
            behavior: 'smooth'
          });
          break;
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [currentTabIndex]);

  return (
    <div className="relative">
      <nav className="bg-white shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex space-x-8">
            {tabs.map((tab, index) => (
              <button
                key={tab.path}
                onClick={() => navigateToTab(index)}
                className={`py-4 px-1 border-b-2 font-medium text-sm transition-all duration-300 transform ${
                  pathname === tab.path
                    ? 'border-blue-500 text-blue-600 scale-105'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 hover:scale-102'
                }`}
              >
                {tab.name}
              </button>
            ))}
          </div>
        </div>
      </nav>

      {/* Left Arrow */}
      {currentTabIndex > 0 && (
        <button
          onClick={navigatePrevious}
          className="fixed left-0 top-1/2 transform -translate-y-1/2 p-3 transition-all duration-200 z-10 hover:scale-110 group cursor-pointer"
          title="Previous tab (←)"
        >
          <svg className="w-8 h-8 text-gray-400 group-hover:text-gray-600 transition-colors duration-200" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
        </button>
      )}

      {/* Right Arrow */}
      {currentTabIndex < tabs.length - 1 && (
        <button
          onClick={navigateNext}
          className="fixed right-0 top-1/2 transform -translate-y-1/2 p-3 transition-all duration-200 z-10 hover:scale-110 group cursor-pointer"
          title="Next tab (→)"
        >
          <svg className="w-8 h-8 text-gray-400 group-hover:text-gray-600 transition-colors duration-200" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
          </svg>
        </button>
      )}
    </div>
  );
}
