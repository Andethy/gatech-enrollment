// API service for communicating with the Lambda backend
import type { EnrollmentRequest, EnrollmentResponse, EnrollmentRecord, Term } from '../types';

// Base URL for the API - will be configured based on environment
const API_BASE_URL = import.meta.env.VITE_API_URL || 'https://api.enrollment.cs1332.cc';

// Polling configuration
const POLL_INTERVAL_MS = 2000; // Poll every 2 seconds
const MAX_POLL_ATTEMPTS = 150; // Max 5 minutes (150 * 2s)

interface JobSubmitResponse {
  job_id: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  message?: string;
}

interface JobStatusResponse {
  job_id: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  progress?: number;
  csv_data?: string;
  download_url?: string;
  error_message?: string;
}

type ProgressCallback = (progress: number, message: string) => void;

/**
 * Submits an enrollment data request and returns a job ID for polling
 */
async function submitEnrollmentJob(request: EnrollmentRequest): Promise<JobSubmitResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/enrollment/generate`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      nterms: request.numTerms,
      subjects: request.subjects,
      ranges: request.courseRanges.map(r => [r.lower, r.upper]),
      include_summer: !request.skipSummer,
      save_all: request.groupData === 'all' || request.groupData === 'both',
      save_grouped: request.groupData === 'grouped' || request.groupData === 'both',
    }),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
  }

  return await response.json();
}

/**
 * Polls for job status until completion or failure
 */
async function pollJobStatus(jobId: string): Promise<JobStatusResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/jobs/${jobId}/status`, {
    method: 'GET',
    headers: {
      'Content-Type': 'application/json',
    },
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
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

    const jobId = submitResponse.job_id;
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

      // Update progress based on simplified progress tracking
      let progress = statusResponse.progress || 0;
      if (progress === 0) progress = 10; // Show some progress while polling
      onProgress?.(progress, `Processing... (${attempts * 2}s elapsed)`);

      if (statusResponse.status === 'completed') {
        onProgress?.(100, 'Complete!');
        
        // Handle embedded CSV data or download URL
        if ('csv_data' in statusResponse && statusResponse.csv_data) {
          // Return embedded CSV data
          return {
            success: true,
            data: parseCSVToRecords(statusResponse.csv_data),
            fileName: 'enrollment_data.csv',
            message: 'Data retrieved successfully'
          } as EnrollmentResponse;
        } else if ('download_url' in statusResponse && statusResponse.download_url) {
          // Download CSV from URL
          const csvResponse = await fetch(statusResponse.download_url);
          if (!csvResponse.ok) {
            throw new Error('Failed to download CSV file');
          }
          const csvData = await csvResponse.text();
          return {
            success: true,
            data: parseCSVToRecords(csvData),
            fileName: 'enrollment_data.csv',
            message: 'Data downloaded successfully'
          } as EnrollmentResponse;
        }
        
        throw new Error('Job completed but no data returned');
      }

      if (statusResponse.status === 'failed') {
        throw new Error(statusResponse.error_message || 'Job failed');
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

    const response = await fetch(`${API_BASE_URL}/api/v1/enrollment/generate`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        nterms: request.numTerms,
        subjects: request.subjects,
        ranges: request.courseRanges.map(r => [r.lower, r.upper]),
        include_summer: !request.skipSummer,
        save_all: request.groupData === 'all' || request.groupData === 'both',
        save_grouped: request.groupData === 'grouped' || request.groupData === 'both',
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

/**
 * Parse CSV data to enrollment records
 */
function parseCSVToRecords(csvData: string): EnrollmentRecord[] {
  const lines = csvData.trim().split('\n');
  if (lines.length < 2 || !lines[0]) return [];

  const headers = lines[0].split(',').map(h => h.trim());
  const records: EnrollmentRecord[] = [];

  // Map CSV headers to expected field names
  const headerMap: Record<string, string> = {
    'Term': 'term',
    'Subject': 'subject',
    'Course': 'course',
    'CRN': 'crn',
    'Section': 'section',
    'Start Time': 'startTime',
    'End Time': 'endTime',
    'Days': 'days',
    'Building': 'building',
    'Room': 'room',
    'Primary Instructor(s)': 'primaryInstructors',
    'Additional Instructor(s)': 'additionalInstructors',
    'Enrollment Actual': 'enrollmentActual',
    'Enrollment Maximum': 'enrollmentMaximum',
    'Enrollment Seats Available': 'enrollmentSeatsAvailable',
    'Waitlist Capacity': 'waitlistCapacity',
    'Waitlist Actual': 'waitlistActual',
    'Waitlist Seats Available': 'waitlistSeatsAvailable',
    'Building Code': 'buildingCode',
    'Room Capacity': 'roomCapacity',
    'Loss': 'loss'
  };

  for (let i = 1; i < lines.length; i++) {
    const line = lines[i];
    if (!line) continue;
    
    const values = parseCSVLine(line);
    if (values.length !== headers.length) continue;

    const record: any = {};
    headers.forEach((header, index) => {
      const value = values[index]?.trim();
      const fieldName = headerMap[header] || header;
      
      // Convert numeric fields
      if (['enrollmentActual', 'enrollmentMaximum', 'enrollmentSeatsAvailable', 
           'waitlistCapacity', 'waitlistActual', 'waitlistSeatsAvailable', 
           'roomCapacity', 'loss'].includes(fieldName)) {
        record[fieldName] = value && value !== '' ? parseFloat(value) : null;
      } else {
        record[fieldName] = value || '';
      }
    });

    records.push(record as EnrollmentRecord);
  }

  return records;
}

/**
 * Parse a single CSV line handling quoted values
 */
function parseCSVLine(line: string): string[] {
  const result: string[] = [];
  let current = '';
  let inQuotes = false;
  
  for (let i = 0; i < line.length; i++) {
    const char = line[i];
    
    if (char === '"') {
      if (inQuotes && line[i + 1] === '"') {
        current += '"';
        i++; // Skip next quote
      } else {
        inQuotes = !inQuotes;
      }
    } else if (char === ',' && !inQuotes) {
      result.push(current);
      current = '';
    } else {
      current += char;
    }
  }
  
  result.push(current);
  return result;
}
