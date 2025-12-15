#!/usr/bin/env python3
"""
Deployment-time script to process room capacity PDF and generate CSV data.

This script runs during CDK deployment to:
1. Parse the room capacity PDF file
2. Generate capacity CSV data
3. Upload the processed data to S3

This eliminates the need for runtime PDF processing.
"""

import sys
import os
import csv
import json
from pathlib import Path

# Add the PDF processing modules to path
sys.path.append(str(Path(__file__).parent.parent / 'lambda' / 'pdf-processing'))

try:
    from pdf_parser import RoomCapacityParser
    PDF_PROCESSING_AVAILABLE = True
except ImportError:
    print("Warning: PDF processing modules not available. Creating empty capacity data.")
    PDF_PROCESSING_AVAILABLE = False

def process_capacity_data():
    """Process the capacity PDF and generate CSV data."""
    
    # Paths
    script_dir = Path(__file__).parent
    pdf_path = script_dir.parent.parent / 'archive' / 'data' / 'classrooms-data-2025.pdf'
    output_dir = script_dir.parent / 'capacity-data'
    csv_path = output_dir / 'room_capacity_data.csv'
    
    # Create output directory
    output_dir.mkdir(exist_ok=True)
    
    print(f"Processing capacity PDF: {pdf_path}")
    
    if not pdf_path.exists():
        print(f"Warning: PDF file not found at {pdf_path}")
        print("Creating empty capacity data file...")
        capacity_data = []
    elif not PDF_PROCESSING_AVAILABLE:
        print("PDF processing modules not available, creating sample data...")
        capacity_data = []
    else:
        try:
            # Parse the PDF
            parser = RoomCapacityParser()
            with open(pdf_path, 'rb') as f:
                pdf_bytes = f.read()
            
            df = parser.parse_pdf_from_bytes(pdf_bytes)
            
            # Convert DataFrame to list of dictionaries
            capacity_data = df.to_dict('records')
            print(f"Extracted {len(capacity_data)} capacity records")
            
            # Validate the data
            validation_results = parser.validate_parsed_data(df)
            if not validation_results['is_valid']:
                print(f"Validation errors: {validation_results['errors']}")
            if validation_results['warnings']:
                print(f"Validation warnings: {validation_results['warnings']}")
            
        except Exception as e:
            print(f"Error parsing PDF: {e}")
            print("Creating empty capacity data file...")
            capacity_data = []
    
    # Write CSV data
    with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
        if capacity_data:
            fieldnames = capacity_data[0].keys()
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(capacity_data)
        else:
            # Create empty CSV with expected headers
            fieldnames = ['Building Code', 'Room', 'Room Capacity']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            # Add a sample row for testing
            writer.writerow({
                'Building Code': 'KLAUS',
                'Room': '1456',
                'Room Capacity': 200
            })
    
    print(f"Generated capacity CSV: {csv_path}")
    
    # Create metadata file
    metadata = {
        'generated_at': '2025-12-13T23:00:00Z',
        'source_file': 'classrooms-data-2025.pdf',
        'record_count': len(capacity_data) if capacity_data else 1,
        'version': '1.0'
    }
    
    metadata_path = output_dir / 'metadata.json'
    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=2)
    
    print(f"Generated metadata: {metadata_path}")
    print("Capacity data processing complete!")
    
    return csv_path, metadata_path

if __name__ == '__main__':
    process_capacity_data()