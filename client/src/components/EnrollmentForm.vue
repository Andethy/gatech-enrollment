<script setup lang="ts">
import { ref, computed } from 'vue';
import type { EnrollmentRequest, CourseRange } from '../types';

const emit = defineEmits<{
  submit: [request: EnrollmentRequest];
}>();

defineProps<{
  loading: boolean;
}>();

// Form state
const numTerms = ref(1);
const subjectInput = ref('');
const courseRangeInput = ref('');
const skipSummer = ref(false);
const oneFile = ref(false);
const groupData = ref<'all' | 'grouped' | 'both'>('all');

// Validation
const errors = ref<Record<string, string>>({});

const isValid = computed(() => {
  return Object.keys(errors.value).length === 0 && numTerms.value >= 1;
});

function validateNumTerms() {
  if (numTerms.value < 1) {
    errors.value.numTerms = 'Number of terms must be at least 1';
  } else if (numTerms.value > 20) {
    errors.value.numTerms = 'Number of terms cannot exceed 20';
  } else {
    delete errors.value.numTerms;
  }
}

function parseSubjects(): string[] {
  if (!subjectInput.value.trim()) return [];
  return subjectInput.value
    .toUpperCase()
    .split(/[,\s]+/)
    .map((s: string) => s.trim())
    .filter((s: string) => s.length > 0);
}

function parseCourseRanges(): CourseRange[] {
  if (!courseRangeInput.value.trim()) {
    return [{ lower: 0, upper: 99999 }];
  }

  const ranges: CourseRange[] = [];
  const parts = courseRangeInput.value.split(/[,\s]+/).filter((p: string) => p.trim());

  for (const part of parts) {
    const match = part.match(/^(\d+)-(\d+)$/);
    if (match && match[1] && match[2]) {
      ranges.push({
        lower: parseInt(match[1], 10),
        upper: parseInt(match[2], 10),
      });
    }
  }

  return ranges.length > 0 ? ranges : [{ lower: 0, upper: 99999 }];
}

function handleSubmit() {
  validateNumTerms();
  
  if (!isValid.value) return;

  const request: EnrollmentRequest = {
    numTerms: numTerms.value,
    subjects: parseSubjects(),
    courseRanges: parseCourseRanges(),
    skipSummer: skipSummer.value,
    oneFile: oneFile.value,
    groupData: groupData.value,
  };

  emit('submit', request);
}
</script>

<template>
  <form @submit.prevent="handleSubmit" class="enrollment-form">
    <!-- <div class="form-description">
      <p>
        This application allows you to retrieve historical enrollment data.
        All options are optional, and if unspecified, all course numbers will be
        fetched. For multiple course ranges, separate with commas. Optionally, you can skip summer terms.
      </p>
    </div> -->

    <!-- Number of Terms -->
    <div class="form-group">
      <label for="numTerms">Number of Terms:</label>
      <input
        id="numTerms"
        v-model.number="numTerms"
        type="number"
        min="1"
        max="20"
        @blur="validateNumTerms"
        :class="{ 'input-error': errors.numTerms }"
      />
      <span v-if="errors.numTerms" class="error-message">{{ errors.numTerms }}</span>
    </div>

    <!-- Subject -->
    <div class="form-group">
      <label for="subject">Subject(s):</label>
      <input
        id="subject"
        v-model="subjectInput"
        type="text"
        placeholder="e.g., CS, MATH, ECE"
      />
      <span class="hint">Leave empty for all subjects. Separate multiple with commas or spaces.</span>
    </div>

    <!-- Course Range -->
    <div class="form-group">
      <label for="courseRange">Course Range(s):</label>
      <input
        id="courseRange"
        v-model="courseRangeInput"
        type="text"
        placeholder="e.g., 1000-2999, 4000-4999"
      />
      <span class="hint">Format: lower-upper. Separate multiple ranges with commas.</span>
    </div>

    <!-- Group Data Options -->
    <div class="form-group">
      <label>Group Crosslisted Courses:</label>
      <div class="radio-group">
        <label class="radio-label">
          <input type="radio" v-model="groupData" value="all" />
          <span>Ungrouped</span>
        </label>
        <label class="radio-label">
          <input type="radio" v-model="groupData" value="grouped" />
          <span>Group Crosslisted</span>
        </label>
        <label class="radio-label">
          <input type="radio" v-model="groupData" value="both" />
          <span>Both</span>
        </label>
      </div>
    </div>

    <!-- Checkboxes -->
    <div class="form-group checkbox-group">
      <label class="checkbox-label">
        <input type="checkbox" v-model="skipSummer" /> Skip Summer Terms
      </label>
      <label class="checkbox-label">
        <input type="checkbox" v-model="oneFile" />Export to One File
      </label>
    </div>

    <!-- Submit Button -->
    <button type="submit" :disabled="!isValid || loading" class="submit-button">
      <span v-if="loading" class="spinner"></span>
      {{ loading ? 'Processing...' : 'Fetch Enrollment Data' }}
    </button>
  </form>
</template>

<style scoped>
.enrollment-form {
  max-width: 600px;
  margin: 0 auto;
  padding: 2rem;
}

.form-description {
  margin-bottom: 2rem;
  padding: 1rem;
  background-color: var(--color-background-soft);
  border-radius: 8px;
  text-align: center;
}

.form-description p {
  margin: 0;
  line-height: 1.6;
  color: var(--color-text-muted);
}

.form-group {
  margin-bottom: 1.5rem;
}

.form-group > label:first-child {
  display: block;
  margin-bottom: 0.5rem;
  font-weight: 600;
  color: var(--color-text);
}

.form-group input[type="text"],
.form-group input[type="number"] {
  width: 100%;
  padding: 0.75rem;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  font-size: 1rem;
  background-color: var(--color-background);
  color: var(--color-text);
  transition: border-color 0.2s, box-shadow 0.2s;
}

.form-group input:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px var(--color-primary-alpha);
}

.form-group input.input-error {
  border-color: var(--color-error);
}

.hint {
  display: block;
  margin-top: 0.25rem;
  font-size: 0.875rem;
  color: var(--color-text-muted);
}

.error-message {
  display: block;
  margin-top: 0.25rem;
  font-size: 0.875rem;
  color: var(--color-error);
}

.radio-group {
  display: flex;
  gap: 1.5rem;
  flex-wrap: wrap;
}

.radio-label,
.checkbox-label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  cursor: pointer;
}

.radio-label input,
.checkbox-label input {
  width: 1rem;
  height: 1rem;
  cursor: pointer;
  margin: 0;
  flex-shrink: 0;
}

.checkbox-group {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.submit-button {
  width: 100%;
  padding: 1rem;
  font-size: 1.1rem;
  font-weight: 600;
  color: white;
  background-color: var(--color-primary);
  border: none;
  border-radius: 8px;
  cursor: pointer;
  transition: background-color 0.2s, transform 0.1s;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
}

.submit-button:hover:not(:disabled) {
  background-color: var(--color-primary-dark);
}

.submit-button:active:not(:disabled) {
  transform: scale(0.98);
}

.submit-button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.spinner {
  width: 1.25rem;
  height: 1.25rem;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-radius: 50%;
  border-top-color: white;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
