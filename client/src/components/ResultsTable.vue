<script setup lang="ts">
import { ref, computed } from 'vue';
import type { EnrollmentRecord } from '../types';

const props = defineProps<{
  records: EnrollmentRecord[];
  filename: string;
}>();

const emit = defineEmits<{
  download: [];
  clear: [];
}>();

// Pagination
const currentPage = ref(1);
const pageSize = ref(25);

const totalPages = computed(() => Math.ceil(props.records.length / pageSize.value));

const paginatedRecords = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value;
  return props.records.slice(start, start + pageSize.value);
});

// Sorting
const sortKey = ref<keyof EnrollmentRecord | ''>('');
const sortOrder = ref<'asc' | 'desc'>('asc');

function sortBy(key: keyof EnrollmentRecord) {
  if (sortKey.value === key) {
    sortOrder.value = sortOrder.value === 'asc' ? 'desc' : 'asc';
  } else {
    sortKey.value = key;
    sortOrder.value = 'asc';
  }
}

const sortedRecords = computed(() => {
  if (!sortKey.value) return paginatedRecords.value;

  return [...paginatedRecords.value].sort((a, b) => {
    const aVal = a[sortKey.value as keyof EnrollmentRecord];
    const bVal = b[sortKey.value as keyof EnrollmentRecord];

    if (aVal === null || aVal === undefined) return 1;
    if (bVal === null || bVal === undefined) return -1;

    let comparison = 0;
    if (typeof aVal === 'number' && typeof bVal === 'number') {
      comparison = aVal - bVal;
    } else {
      comparison = String(aVal).localeCompare(String(bVal));
    }

    return sortOrder.value === 'asc' ? comparison : -comparison;
  });
});

function prevPage() {
  if (currentPage.value > 1) currentPage.value--;
}

function nextPage() {
  if (currentPage.value < totalPages.value) currentPage.value++;
}

// Format loss percentage
function formatLoss(loss: number | null): string {
  if (loss === null) return '-';
  return `${(loss * 100).toFixed(1)}%`;
}

// Column definitions for display
const columns: { key: keyof EnrollmentRecord; label: string; width?: string }[] = [
  { key: 'term', label: 'Term', width: '100px' },
  { key: 'course', label: 'Course', width: '100px' },
  { key: 'crn', label: 'CRN', width: '70px' },
  { key: 'section', label: 'Section', width: '70px' },
  { key: 'days', label: 'Days', width: '70px' },
  { key: 'startTime', label: 'Start', width: '70px' },
  { key: 'endTime', label: 'End', width: '70px' },
  { key: 'building', label: 'Building', width: '150px' },
  { key: 'room', label: 'Room', width: '60px' },
  { key: 'primaryInstructors', label: 'Instructor', width: '150px' },
  { key: 'enrollmentActual', label: 'Enrolled', width: '70px' },
  { key: 'enrollmentMaximum', label: 'Max', width: '60px' },
  { key: 'enrollmentSeatsAvailable', label: 'Avail', width: '60px' },
  { key: 'roomCapacity', label: 'Room Cap', width: '80px' },
  { key: 'loss', label: 'Loss %', width: '70px' },
];
</script>

<template>
  <div class="results-container">
    <div class="results-header">
      <div class="results-info">
        <span class="record-count">{{ records.length }} records found</span>
        <span class="filename">{{ filename }}</span>
      </div>
      <div class="results-actions">
        <button @click="emit('download')" class="action-button download-button">
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
            <polyline points="7 10 12 15 17 10"></polyline>
            <line x1="12" y1="15" x2="12" y2="3"></line>
          </svg>
          Download CSV
        </button>
        <button @click="emit('clear')" class="action-button clear-button">
          Clear Results
        </button>
      </div>
    </div>

    <div class="table-wrapper">
      <table class="results-table">
        <thead>
          <tr>
            <th 
              v-for="col in columns" 
              :key="col.key"
              :style="{ width: col.width }"
              @click="sortBy(col.key)"
              class="sortable"
            >
              {{ col.label }}
              <span v-if="sortKey === col.key" class="sort-indicator">
                {{ sortOrder === 'asc' ? '▲' : '▼' }}
              </span>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="record in sortedRecords" :key="record.crn + record.term">
            <td>{{ record.term }}</td>
            <td>{{ record.course }}</td>
            <td>{{ record.crn }}</td>
            <td>{{ record.section }}</td>
            <td>{{ record.days || '-' }}</td>
            <td>{{ record.startTime || '-' }}</td>
            <td>{{ record.endTime || '-' }}</td>
            <td>{{ record.building || '-' }}</td>
            <td>{{ record.room || '-' }}</td>
            <td class="instructor-cell">{{ record.primaryInstructors || '-' }}</td>
            <td>{{ record.enrollmentActual ?? '-' }}</td>
            <td>{{ record.enrollmentMaximum ?? '-' }}</td>
            <td>{{ record.enrollmentSeatsAvailable ?? '-' }}</td>
            <td>{{ record.roomCapacity ?? '-' }}</td>
            <td>{{ formatLoss(record.loss) }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="pagination" v-if="totalPages > 1">
      <button @click="prevPage" :disabled="currentPage === 1" class="page-button">
        ← Previous
      </button>
      <span class="page-info">
        Page {{ currentPage }} of {{ totalPages }}
      </span>
      <button @click="nextPage" :disabled="currentPage === totalPages" class="page-button">
        Next →
      </button>
    </div>
  </div>
</template>

<style scoped>
.results-container {
  margin-top: 2rem;
  padding: 1.5rem;
  background-color: var(--color-background-soft);
  border-radius: 12px;
}

.results-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
  flex-wrap: wrap;
  gap: 1rem;
}

.results-info {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.record-count {
  font-weight: 600;
  font-size: 1.1rem;
}

.filename {
  font-size: 0.875rem;
  color: var(--color-text-muted);
}

.results-actions {
  display: flex;
  gap: 0.75rem;
}

.action-button {
  padding: 0.5rem 1rem;
  font-size: 0.9rem;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.download-button {
  background-color: var(--color-success);
  color: white;
  border: none;
}

.download-button:hover {
  background-color: var(--color-success-dark);
}

.clear-button {
  background-color: transparent;
  color: var(--color-text-muted);
  border: 1px solid var(--color-border);
}

.clear-button:hover {
  background-color: var(--color-background);
  color: var(--color-text);
}

.table-wrapper {
  overflow-x: auto;
  border-radius: 8px;
  border: 1px solid var(--color-border);
}

.results-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.875rem;
  min-width: 1200px;
}

.results-table th {
  background-color: var(--color-background-muted);
  padding: 0.75rem 0.5rem;
  text-align: left;
  font-weight: 600;
  border-bottom: 2px solid var(--color-border);
  white-space: nowrap;
}

.results-table th.sortable {
  cursor: pointer;
  user-select: none;
}

.results-table th.sortable:hover {
  background-color: var(--color-background);
}

.sort-indicator {
  margin-left: 0.25rem;
  font-size: 0.75rem;
}

.results-table td {
  padding: 0.6rem 0.5rem;
  border-bottom: 1px solid var(--color-border);
  white-space: nowrap;
}

.results-table tbody tr:hover {
  background-color: var(--color-background);
}

.instructor-cell {
  max-width: 150px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.pagination {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 1rem;
  margin-top: 1rem;
  padding-top: 1rem;
  border-top: 1px solid var(--color-border);
}

.page-button {
  padding: 0.5rem 1rem;
  background-color: var(--color-background);
  border: 1px solid var(--color-border);
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
}

.page-button:hover:not(:disabled) {
  background-color: var(--color-primary);
  color: white;
  border-color: var(--color-primary);
}

.page-button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.page-info {
  font-size: 0.9rem;
  color: var(--color-text-muted);
}
</style>
