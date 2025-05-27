'use client';

export default function Home() {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-white">
      <h1 className="text-4xl font-bold mb-8 text-gray-800">
        Nurse Scheduling System
      </h1>
      <button
        className="px-8 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-lg font-medium"
        onClick={() => {
          // TODO: Add navigation or action when button is clicked
          console.log('Start button clicked');
        }}
      >
        Start
      </button>
    </div>
  );
}
