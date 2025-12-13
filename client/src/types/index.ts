// Types for the Georgia Tech Enrollment Data application

export interface EnrollmentRequest {
  numTerms: number;
  subjects: string[];
  courseRanges: CourseRange[];
  skipSummer: boolean;
  oneFile: boolean;
  groupData: 'all' | 'grouped' | 'both';
}

export interface CourseRange {
  lower: number;
  upper: number;
}

export interface EnrollmentRecord {
  term: string;
  subject: string;
  course: string;
  crn: string;
  section: string;
  startTime: string;
  endTime: string;
  days: string;
  building: string;
  room: string;
  primaryInstructors: string;
  additionalInstructors: string;
  enrollmentActual: number | null;
  enrollmentMaximum: number | null;
  enrollmentSeatsAvailable: number | null;
  waitlistCapacity: number | null;
  waitlistActual: number | null;
  waitlistSeatsAvailable: number | null;
  buildingCode: string;
  roomCapacity: number | null;
  loss: number | null;
}

export interface EnrollmentResponse {
  success: boolean;
  data: EnrollmentRecord[];
  fileName: string;
  error?: string;
}

export interface Term {
  term: string;
  name: string;
}

export interface ApiStatus {
  loading: boolean;
  error: string | null;
  progress: number;
  message: string;
}
