'use client';

import { useState } from 'react';
import { useScheduling } from '@/contexts/SchedulingContexts';

export default function Home() {
  const { createNewState } = useScheduling();
  const [showConfirmDialog, setShowConfirmDialog] = useState(false);

  const handleStartNew = () => {
    setShowConfirmDialog(true);
  };

  const confirmStartNew = () => {
    createNewState();
    setShowConfirmDialog(false);
  };

  return (
    <div className="min-h-[calc(100vh-4rem)] flex flex-col items-center justify-center px-4 sm:px-6 lg:px-8">
      <div className="w-full max-w-3xl text-center">
        <h1 className="text-4xl font-bold mb-8 text-gray-800">
          Nurse Scheduling System
        </h1>
        <p className="text-lg text-gray-600 mb-8">
          Welcome to the Nurse Scheduling System. Use the tabs above to navigate.
        </p>
        <div className="flex flex-col sm:flex-row gap-4 justify-center">
          <button
            onClick={handleStartNew}
            className="px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
          >
            New Schedule
          </button>
          <button
            onClick={() => window.location.href = '/people'}
            className="px-6 py-3 bg-gray-600 text-white rounded-lg hover:bg-gray-700 transition-colors"
          >
            Continue
          </button>
        </div>
      </div>

      {/* Confirmation Dialog */}
      {showConfirmDialog && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-lg p-6 max-w-md w-full">
            <h2 className="text-xl font-bold mb-4 text-gray-800">Confirm Reset</h2>
            <p className="text-gray-600 mb-6">
              Are you sure you want to start from a new state? This will reset all your current data.
            </p>
            <div className="flex justify-end gap-4">
              <button
                onClick={() => setShowConfirmDialog(false)}
                className="px-4 py-2 text-gray-600 hover:text-gray-800"
              >
                Cancel
              </button>
              <button
                onClick={confirmStartNew}
                className="px-4 py-2 bg-red-600 text-white rounded hover:bg-red-700"
              >
                Reset Data
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
