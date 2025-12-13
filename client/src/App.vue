<script setup lang="ts">
import { ref } from 'vue';
import EnrollmentForm from './components/EnrollmentForm.vue';
import ResultsTable from './components/ResultsTable.vue';
import StatusMessage from './components/StatusMessage.vue';
import { fetchEnrollmentData, downloadCSV, recordsToCSV } from './services/api';
import type { EnrollmentRequest, EnrollmentRecord } from './types';

// Application state
const loading = ref(false);
const statusType = ref<'info' | 'success' | 'error' | 'loading'>('info');
const statusMessage = ref('');
const statusProgress = ref(0);
const showStatus = ref(false);
const results = ref<EnrollmentRecord[]>([]);
const resultFilename = ref('');

async function handleSubmit(request: EnrollmentRequest) {
  loading.value = true;
  showStatus.value = true;
  statusType.value = 'loading';
  statusMessage.value = 'Submitting request...';
  statusProgress.value = 0;
  results.value = [];
  resultFilename.value = '';

  try {
    // Progress callback to update UI during long-running operations
    const onProgress = (progress: number, message: string) => {
      statusProgress.value = progress;
      statusMessage.value = message;
    };

    const response = await fetchEnrollmentData(request, onProgress);

    if (response.success && response.data) {
      results.value = response.data;
      resultFilename.value = response.fileName;
      statusType.value = 'success';
      statusMessage.value = `Successfully retrieved ${response.data.length} enrollment records.`;
    } else {
      statusType.value = 'error';
      statusMessage.value = response.error || 'An unexpected error occurred.';
    }
  } catch (error) {
    statusType.value = 'error';
    statusMessage.value = error instanceof Error 
      ? `Error: ${error.message}` 
      : 'An unexpected error occurred while fetching data.';
  } finally {
    loading.value = false;
  }
}

function handleDownload() {
  if (results.value.length === 0) return;

  // Convert records to the CSV format matching the original Python output
  const csvRecords = results.value.map((r: EnrollmentRecord) => ({
    'Term': r.term,
    'Subject': r.subject,
    'Course': r.course,
    'CRN': r.crn,
    'Section': r.section,
    'Start Time': r.startTime,
    'End Time': r.endTime,
    'Days': r.days,
    'Building': r.building,
    'Room': r.room,
    'Primary Instructor(s)': r.primaryInstructors,
    'Additional Instructor(s)': r.additionalInstructors,
    'Enrollment Actual': r.enrollmentActual,
    'Enrollment Maximum': r.enrollmentMaximum,
    'Enrollment Seats Available': r.enrollmentSeatsAvailable,
    'Waitlist Capacity': r.waitlistCapacity,
    'Waitlist Actual': r.waitlistActual,
    'Waitlist Seats Available': r.waitlistSeatsAvailable,
    'Building Code': r.buildingCode,
    'Room Capacity': r.roomCapacity,
    'Loss': r.loss,
  }));

  const csv = recordsToCSV(csvRecords);
  const filename = resultFilename.value || `enrollment_data_${new Date().toISOString().slice(0, 10)}.csv`;
  downloadCSV(csv, filename);
}

function handleClear() {
  results.value = [];
  resultFilename.value = '';
  showStatus.value = false;
}
</script>

<template>
  <div class="app">
    <header class="app-header">
      <div class="header-content">
        <img src="https://i0.wp.com/ams.gatech.edu/wp-content/uploads/2017/02/georgia-tech-yellow-jackets-logo.png?w=300&ssl=1" alt="Georgia Tech Logo" class="logo" />
        <div class="header-text">
          <h1>Georgia Tech Enrollment Data</h1>
          <p class="subtitle">Historical course enrollment data retrieval tool</p>
        </div>
      </div>
    </header>

    <main class="app-main">
      <EnrollmentForm :loading="loading" @submit="handleSubmit" />

      <StatusMessage
        v-if="showStatus"
        :type="statusType"
        :message="statusMessage"
        :progress="statusType === 'loading' ? statusProgress : undefined"
      />

      <ResultsTable
        v-if="results.length > 0"
        :records="results"
        :filename="resultFilename"
        @download="handleDownload"
        @clear="handleClear"
      />
    </main>

    <footer class="app-footer">
      <p>
        Data sourced from 
        <a href="https://www.gt-scheduler.org/" target="_blank" rel="noopener">GT Scheduler</a>
        &nbsp;•&nbsp;
        <a href="https://github.com/Andethy/gatech-enrollment" target="_blank" rel="noopener">GitHub Repository</a>
      </p>
      <p class="credits">Made by Andrew DiBiasio, Jack Hayley, Lucian Tash</p>
    </footer>
  </div>
</template>

<style scoped>
.app {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

.app-header {
  background: linear-gradient(135deg, var(--color-gt-gold) 0%, var(--color-gt-gold-dark) 100%);
  padding: 1.5rem 2rem;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
}

.header-content {
  max-width: 1200px;
  margin: 0 auto;
  display: flex;
  align-items: center;
  gap: 1.5rem;
}

.logo {
  width: 60px;
  height: 60px;
}

.header-text h1 {
  margin: 0;
  font-size: 1.75rem;
  color: var(--color-gt-navy);
  font-weight: 700;
}

.subtitle {
  margin: 0.25rem 0 0 0;
  color: var(--color-gt-navy);
  opacity: 0.8;
  font-size: 0.95rem;
}

.app-main {
  flex: 1;
  max-width: 1200px;
  width: 100%;
  margin: 0 auto;
  padding: 2rem;
}

.app-footer {
  background-color: var(--color-background-soft);
  border-top: 1px solid var(--color-border);
  padding: 1rem 2rem;
  text-align: center;
}

.app-footer p {
  margin: 0;
  font-size: 0.875rem;
  color: var(--color-text-muted);
}

.app-footer .credits {
  margin-top: 0.5rem;
}

.app-footer a {
  color: var(--color-primary);
  text-decoration: none;
}

.app-footer a:hover {
  text-decoration: underline;
}

@media (max-width: 640px) {
  .header-content {
    flex-direction: column;
    text-align: center;
  }

  .header-text h1 {
    font-size: 1.5rem;
  }

  .app-main {
    padding: 1rem;
  }
}
</style>
