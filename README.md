# Georgia Tech Enrollment Data - Web Application

A Vue.js web application for retrieving historical course enrollment data from Georgia Tech. This is the frontend component that communicates with an AWS Lambda backend.

## Quick Start

### One-Command Deployment
```bash
./deploy.sh
```

This script will:
- Check prerequisites (Node.js, Python, AWS CLI, CDK)
- Install all dependencies
- Build the client application
- Deploy the AWS infrastructure
- Process capacity data

### Development Setup
```bash
./setup.sh
```

This script will:
- Copy environment templates to `.env` files
- Install all dependencies
- Prepare the development environment

### Manual Setup

1. **Environment Configuration**
   ```bash
   cp infra/.env.template infra/.env
   cp client/.env.template client/.env
   ```
   
   Edit `infra/.env` with your AWS configuration and `client/.env` with your API URL.

2. **Install Dependencies**
   ```bash
   # Infrastructure
   cd infra && npm install
   
   # Client
   cd ../client && npm install
   ```

3. **Deploy Backend**
   ```bash
   cd infra
   cdk deploy
   ```

4. **Run Development Server**
   ```bash
   cd client
   npm run dev
   ```

## API Contract

The frontend expects the backend to implement an **async job-based API** since enrollment data retrieval can take several minutes. The flow is:

1. **Submit job** → Get job ID
2. **Poll for status** → Until completed or failed
3. **Get results** → From final status response

### POST /enrollment (Submit Job)

**Request Body:**
```json
{
  "num_terms": 1,
  "subjects": ["CS", "MATH"],
  "ranges": [[1000, 2999], [4000, 4999]],
  "skip_summer": false,
  "group_data": "all"
}
```

**Response (Job Submitted):**
```json
{
  "jobId": "abc123-def456",
  "status": "pending",
  "message": "Job submitted successfully"
}
```

### GET /enrollment/status/{jobId} (Poll Status)

**Response (Processing):**
```json
{
  "jobId": "abc123-def456",
  "status": "processing",
  "progress": 45,
  "message": "Processing Spring 2025 data..."
}
```

**Response (Completed):**
```json
{
  "jobId": "abc123-def456",
  "status": "completed",
  "progress": 100,
  "result": {
    "success": true,
    "data": [...],
    "fileName": "fall_2025_enrollment_data_2025-12-13.csv"
  }
}
```

**Response (Failed):**
```json
{
  "jobId": "abc123-def456",
  "status": "failed",
  "message": "Error: Unable to fetch term data"
}
```

### Job Status Values
| Status | Description |
|--------|-------------|
| `pending` | Job received, waiting to start |
| `processing` | Job is running |
| `completed` | Job finished successfully |
| `failed` | Job encountered an error |

### Result Data Structure

When `status` is `completed`, the `result` field contains:
```json
{
  "success": true,
  "data": [
    {
      "term": "Fall 2025",
      "subject": "CS",
      "course": "CS 1301",
      "crn": "12345",
      "section": "A",
      "startTime": "08:25",
      "endTime": "09:15",
      "days": "MWF",
      "building": "College of Computing",
      "room": "16",
      "primaryInstructors": "John Doe",
      "additionalInstructors": "",
      "enrollmentActual": 45,
      "enrollmentMaximum": 50,
      "enrollmentSeatsAvailable": 5,
      "waitlistCapacity": 10,
      "waitlistActual": 0,
      "waitlistSeatsAvailable": 10,
      "buildingCode": "50",
      "roomCapacity": 240,
      "loss": 0.8125
    }
  ],
  "fileName": "fall_2025_enrollment_data_2025-12-13.csv"
}
```

## Data Fields

| Field | Description |
|-------|-------------|
| Term | Semester and year (e.g., "Fall 2025") |
| Subject | Course subject code (e.g., "CS") |
| Course | Full course code (e.g., "CS 1301") |
| CRN | Course Reference Number |
| Section | Section identifier |
| Start Time / End Time | Class meeting times |
| Days | Meeting days (M, T, W, R, F) |
| Building / Room | Physical location |
| Primary Instructor(s) | Main instructor(s) |
| Enrollment Actual | Current enrollment count |
| Enrollment Maximum | Maximum allowed enrollment |
| Seats Available | Remaining seats |
| Waitlist fields | Waitlist capacity and current count |
| Room Capacity | Physical room capacity |
| Loss | Room utilization loss (1 - actual/capacity) |

## Technologies

- **Vue 3** - Progressive JavaScript framework
- **TypeScript** - Type-safe JavaScript
- **Vite** - Fast build tool and dev server
- **CSS Variables** - Theming with dark mode support

## License

MIT


Original Python desktop application made by Andrew DiBiasio.