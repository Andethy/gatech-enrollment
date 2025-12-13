<script setup lang="ts">
defineProps<{
  type: 'info' | 'success' | 'error' | 'loading';
  message: string;
  progress?: number;
}>();
</script>

<template>
  <div :class="['status-message', `status-${type}`]">
    <div class="status-icon">
      <!-- Loading spinner -->
      <svg v-if="type === 'loading'" class="spinner-icon" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-dasharray="31.4 31.4" />
      </svg>
      
      <!-- Success checkmark -->
      <svg v-else-if="type === 'success'" xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path>
        <polyline points="22 4 12 14.01 9 11.01"></polyline>
      </svg>
      
      <!-- Error X -->
      <svg v-else-if="type === 'error'" xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="10"></circle>
        <line x1="15" y1="9" x2="9" y2="15"></line>
        <line x1="9" y1="9" x2="15" y2="15"></line>
      </svg>
      
      <!-- Info icon -->
      <svg v-else xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="10"></circle>
        <line x1="12" y1="16" x2="12" y2="12"></line>
        <line x1="12" y1="8" x2="12.01" y2="8"></line>
      </svg>
    </div>
    
    <div class="status-content">
      <p class="status-text">{{ message }}</p>
      
      <div v-if="type === 'loading' && progress !== undefined" class="progress-bar">
        <div class="progress-fill" :style="{ width: `${progress}%` }"></div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.status-message {
  display: flex;
  align-items: flex-start;
  gap: 1rem;
  padding: 1rem 1.25rem;
  border-radius: 8px;
  margin: 1.5rem 0;
}

.status-info {
  background-color: var(--color-info-bg);
  border: 1px solid var(--color-info-border);
  color: var(--color-info);
}

.status-success {
  background-color: var(--color-success-bg);
  border: 1px solid var(--color-success-border);
  color: var(--color-success);
}

.status-error {
  background-color: var(--color-error-bg);
  border: 1px solid var(--color-error-border);
  color: var(--color-error);
}

.status-loading {
  background-color: var(--color-primary-bg);
  border: 1px solid var(--color-primary-border);
  color: var(--color-primary);
}

.status-icon {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}

.spinner-icon {
  width: 24px;
  height: 24px;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

.status-content {
  flex: 1;
  min-width: 0;
}

.status-text {
  margin: 0;
  font-weight: 500;
  line-height: 1.5;
}

.progress-bar {
  margin-top: 0.75rem;
  height: 6px;
  background-color: rgba(255, 255, 255, 0.3);
  border-radius: 3px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background-color: currentColor;
  border-radius: 3px;
  transition: width 0.3s ease;
}
</style>
