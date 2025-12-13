import { ref, readonly } from 'vue';
import type { EnrollmentRecord, ApiStatus } from '../types';

// Shared state
const records = ref<EnrollmentRecord[]>([]);
const status = ref<ApiStatus>({
  loading: false,
  error: null,
  progress: 0,
  message: '',
});

export function useEnrollmentStore() {
  const setRecords = (data: EnrollmentRecord[]) => {
    records.value = data;
  };

  const clearRecords = () => {
    records.value = [];
  };

  const setLoading = (isLoading: boolean, message = '') => {
    status.value.loading = isLoading;
    status.value.message = message;
    if (isLoading) {
      status.value.error = null;
    }
  };

  const setError = (error: string | null) => {
    status.value.error = error;
    status.value.loading = false;
  };

  const setProgress = (progress: number) => {
    status.value.progress = Math.min(100, Math.max(0, progress));
  };

  const reset = () => {
    records.value = [];
    status.value = {
      loading: false,
      error: null,
      progress: 0,
      message: '',
    };
  };

  return {
    // State (readonly to prevent direct mutation)
    records: readonly(records),
    status: readonly(status),
    
    // Actions
    setRecords,
    clearRecords,
    setLoading,
    setError,
    setProgress,
    reset,
  };
}
