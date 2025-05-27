'use client';

export default function Home() {
  return (
    <div className="min-h-[calc(100vh-4rem)] flex flex-col items-center justify-center">
      <h1 className="text-4xl font-bold mb-8 text-gray-800">
        Nurse Scheduling System
      </h1>
      <p className="text-lg text-gray-600 mb-8">
        Welcome to the Nurse Scheduling System. Use the tabs above to navigate.
      </p>
    </div>
  );
}
