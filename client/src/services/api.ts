// API service for communicating with the Lambda backend
import type { EnrollmentRequest, EnrollmentResponse, Term } from '../types';

// Base URL for the API - will be configured based on environment
const API_BASE_URL = import.meta.env.VITE_API_URL || 'https://your-api-gateway-url.amazonaws.com/prod';

// Polling configuration
const POLL_INTERVAL_MS = 2000; // Poll every 2 seconds
const MAX_POLL_ATTEMPTS = 150; // Max 5 minutes (150 * 2s)

interface JobSubmitResponse {
  jobId: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  message?: string;
}

interface JobStatusResponse {
  jobId: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  progress?: number;
  message?: string;
  result?: EnrollmentResponse;
}

type ProgressCallback = (progress: number, message: string) => void;

/**
 * Submits an enrollment data request and returns a job ID for polling
 */
async function submitEnrollmentJob(request: EnrollmentRequest): Promise<JobSubmitResponse> {
  const response = await fetch(`${API_BASE_URL}/enrollment`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      num_terms: request.numTerms,
      subjects: request.subjects,
      ranges: request.courseRanges.map(r => [r.lower, r.upper]),
      skip_summer: request.skipSummer,
      one_file: request.oneFile,
      group_data: request.groupData,
    }),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.message || `HTTP error! status: ${response.status}`);
  }

  return await response.json();
}

/**
 * Polls for job status until completion or failure
 */
async function pollJobStatus(jobId: string): Promise<JobStatusResponse> {
  const response = await fetch(`${API_BASE_URL}/enrollment/status/${jobId}`, {
    method: 'GET',
    headers: {
      'Content-Type': 'application/json',
    },
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.message || `HTTP error! status: ${response.status}`);
  }

  return await response.json();
}

/**
 * Fetches enrollment data with async polling support for long-running operations
 */
export async function fetchEnrollmentData(
  request: EnrollmentRequest,
  onProgress?: ProgressCallback
): Promise<EnrollmentResponse> {
  try {
    // Submit the job
    onProgress?.(0, 'Submitting request...');
    const submitResponse = await submitEnrollmentJob(request);

    // If the response already contains the result (fast path), return it
    if ('data' in submitResponse && 'success' in submitResponse) {
      return submitResponse as unknown as EnrollmentResponse;
    }

    const jobId = submitResponse.jobId;
    if (!jobId) {
      throw new Error('No job ID returned from server');
    }

    onProgress?.(5, 'Request submitted. Processing enrollment data...');

    // Poll for completion
    let attempts = 0;
    while (attempts < MAX_POLL_ATTEMPTS) {
      await sleep(POLL_INTERVAL_MS);
      attempts++;

      const statusResponse = await pollJobStatus(jobId);

      // Update progress
      const progress = statusResponse.progress ?? Math.min(10 + attempts * 2, 90);
      onProgress?.(progress, statusResponse.message || `Processing... (${attempts * 2}s elapsed)`);

      if (statusResponse.status === 'completed') {
        onProgress?.(100, 'Complete!');
        if (statusResponse.result) {
          return statusResponse.result;
        }
        throw new Error('Job completed but no result returned');
      }

      if (statusResponse.status === 'failed') {
        throw new Error(statusResponse.message || 'Job failed');
      }
    }

    throw new Error('Request timed out. Please try again with fewer terms or a more specific filter.');
  } catch (error) {
    console.error('API Error:', error);
    throw error;
  }
}

/**
 * Alternative: Fetch enrollment data synchronously (for backends that support it)
 * Use this if your backend handles the full request in one call
 */
export async function fetchEnrollmentDataSync(
  request: EnrollmentRequest,
  onProgress?: ProgressCallback
): Promise<EnrollmentResponse> {
  try {
    onProgress?.(10, 'Fetching enrollment data...');

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 300000); // 5 minute timeout

    const response = await fetch(`${API_BASE_URL}/enrollment`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        num_terms: request.numTerms,
        subjects: request.subjects,
        ranges: request.courseRanges.map(r => [r.lower, r.upper]),
        skip_summer: request.skipSummer,
        one_file: request.oneFile,
        group_data: request.groupData,
      }),
      signal: controller.signal,
    });

    clearTimeout(timeoutId);

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.message || `HTTP error! status: ${response.status}`);
    }

    onProgress?.(90, 'Processing response...');
    const result = await response.json();
    onProgress?.(100, 'Complete!');
    
    return result;
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') {
      throw new Error('Request timed out. Please try again with fewer terms or a more specific filter.');
    }
    console.error('API Error:', error);
    throw error;
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * Fetches available terms from the GT Scheduler API
 */
export async function fetchAvailableTerms(): Promise<Term[]> {
  try {
    // GT Scheduler crawler URL - this is publicly accessible
    const response = await fetch('https://gt-scheduler.github.io/crawler-v2/');
    
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const data = await response.json();
    
    // Parse and format terms
    return data.terms.map((t: { term: string }) => ({
      term: t.term,
      name: parseTermName(t.term),
    })).sort((a: Term, b: Term) => b.term.localeCompare(a.term));
  } catch (error) {
    console.error('Error fetching terms:', error);
    throw error;
  }
}

/**
 * Converts a term code to a readable name (e.g., "202502" -> "Spring 2025")
 */
function parseTermName(term: string): string {
  const year = term.substring(0, 4);
  const month = parseInt(term.substring(4), 10);

  let semester: string;
  if (month < 5) {
    semester = 'Spring';
  } else if (month < 8) {
    semester = 'Summer';
  } else {
    semester = 'Fall';
  }

  return `${semester} ${year}`;
}

/**
 * Downloads data as a CSV file
 */
export function downloadCSV(data: string, filename: string): void {
  const blob = new Blob([data], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.setAttribute('href', url);
  link.setAttribute('download', filename);
  link.style.visibility = 'hidden';
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

/**
 * Converts enrollment records to CSV format
 */
export function recordsToCSV(records: Record<string, unknown>[]): string {
  if (records.length === 0) return '';

  const firstRecord = records[0];
  if (!firstRecord) return '';
  
  const headers = Object.keys(firstRecord);
  const csvRows = [
    headers.join(','),
    ...records.map(record => 
      headers.map(header => {
        const value = record[header];
        // Escape values that contain commas or quotes
        if (typeof value === 'string' && (value.includes(',') || value.includes('"'))) {
          return `"${value.replace(/"/g, '""')}"`;
        }
        return value ?? '';
      }).join(',')
    )
  ];

  return csvRows.join('\n');
}
