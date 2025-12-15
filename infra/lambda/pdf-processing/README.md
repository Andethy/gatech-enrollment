# PDF Processing Lambda Function

This Lambda function handles PDF processing and room capacity data management for the Georgia Tech Enrollment Cloud Backend.

## Endpoints

### POST /api/v1/capacity/upload

Uploads and processes a PDF file containing room capacity data.

**Request:**
- Method: POST
- Content-Type: multipart/form-data
- Body: PDF file as form data
- Authentication: Required (Cognito JWT token)

**Response:**
- 200: Processing completed successfully
- 400: Invalid request (wrong content type, invalid PDF, etc.)
- 401: Authentication required
- 500: Processing error

**Example Response:**
```json
{
  "job_id": "uuid-string",
  "status": "completed",
  "message": "PDF processed successfully",
  "results": {
    "files": [
      {
        "filename": "capacities_20231201_143022.csv",
        "download_url": "https://s3.amazonaws.com/...",
        "size_bytes": 12345,
        "file_type": "timestamped_capacity_data"
      },
      {
        "filename": "capacities.csv",
        "download_url": "https://s3.amazonaws.com/...",
        "size_bytes": 12345,
        "file_type": "current_capacity_data"
      }
    ],
    "statistics": {
      "total_rooms": 150,
      "unique_buildings": 25,
      "capacity_stats": {
        "min": 10,
        "max": 500,
        "mean": 85.5,
        "median": 75
      }
    }
  }
}
```

### GET /api/v1/capacity/data

Retrieves current room capacity data.

**Request:**
- Method: GET
- Query Parameters:
  - `format`: "json" (default) or "csv"
- Authentication: Required (Cognito JWT token)

**Response:**
- 200: Data retrieved successfully
- 404: No capacity data available
- 401: Authentication required
- 500: Retrieval error

**JSON Response Example:**
```json
{
  "download_url": "https://s3.amazonaws.com/...",
  "filename": "capacities.csv",
  "last_modified": "2023-12-01T14:30:22Z",
  "size_bytes": 12345,
  "format_options": {
    "csv_direct": "api.example.com/api/v1/capacity/data?format=csv",
    "json_metadata": "api.example.com/api/v1/capacity/data?format=json"
  },
  "statistics": {
    "total_rooms": 150,
    "unique_buildings": 25,
    "capacity_range": {
      "min": 10,
      "max": 500
    },
    "total_capacity": 12825
  }
}
```

**CSV Response:**
When `format=csv` is specified, returns the CSV file directly with appropriate headers.

## Features

### PDF Processing
- Parses Georgia Tech room capacity PDF files using regex patterns
- Validates parsed data for completeness and accuracy
- Generates CSV files in the expected format
- Creates both timestamped and current versions
- Provides detailed error messages for parsing failures

### Data Management
- Stores processed data in S3 with proper organization
- Creates backups of previous capacity data
- Generates presigned URLs for secure file downloads
- Tracks processing jobs with status updates
- Provides comprehensive statistics and metadata

### Error Handling
- Validates file formats and sizes
- Handles multipart form data parsing
- Provides detailed error messages
- Logs all operations for debugging
- Graceful handling of missing data

### Security
- Requires Cognito authentication for all endpoints
- Validates file types and sizes
- Uses presigned URLs for secure downloads
- Implements proper CORS headers
- Sanitizes all user inputs

## File Structure

- `index.py`: Main Lambda handler and endpoint routing
- `pdf_parser.py`: PDF parsing logic using pdfplumber and regex
- `requirements.txt`: Python dependencies

## Dependencies

- boto3: AWS SDK for S3 operations
- pdfplumber: PDF text extraction
- pandas: Data processing and CSV generation
- regex: Advanced pattern matching for room data

## Environment Variables

- `S3_BUCKET_NAME`: S3 bucket for file storage
- `LOG_LEVEL`: Logging level (INFO, DEBUG, etc.)
- `ENVIRONMENT`: Deployment environment (dev, prod, etc.)

## S3 Structure

```
bucket/
├── room-capacity/
│   ├── capacities.csv                    # Current capacity data
│   ├── capacities_YYYYMMDD_HHMMSS_jobid.csv  # Timestamped versions
│   └── backups/
│       └── capacities_backup_YYYYMMDD_HHMMSS.csv
├── job-status/
│   └── {job-id}.json                     # Job status tracking
├── notifications/
│   └── capacity_updates/
│       └── YYYYMMDD/
│           └── {job-id}.json             # Update notifications
└── capacity-updates/
    └── summaries/
        └── YYYY/MM/DD/
            └── {job-id}_summary.json     # Processing summaries
```

## Testing

The function includes comprehensive validation and error handling. For testing:

1. Use valid PDF files with Georgia Tech room capacity data
2. Test with various file sizes and formats
3. Verify authentication with valid/invalid tokens
4. Test both JSON and CSV response formats
5. Verify proper error responses for edge cases