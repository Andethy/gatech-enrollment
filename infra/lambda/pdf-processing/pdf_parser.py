"""
PDF parsing module for Georgia Tech room capacity data.
Ported from the original rooms.py file.
"""

import logging
import regex
import pdfplumber
import pandas as pd
from typing import List, Tuple, Dict, Any
from io import BytesIO

logger = logging.getLogger(__name__)

class RoomCapacityParser:
    """Parser for Georgia Tech room capacity PDF files."""
    
    def __init__(self):
        # Regex patterns from the original application
        self.capacity_regex = r"(?=\b\w*\d\w*\b)([\w\d]+)[^\S\n]([\w\d]+)[^\S\n](\d+)"
        self.room_pattern = regex.compile(self.capacity_regex)
        self.building_pattern = regex.compile(r"(.+)[^\S\n]" + self.capacity_regex)
    
    def parse_pdf_from_bytes(self, pdf_bytes: bytes) -> pd.DataFrame:
        """
        Parse room capacity data from PDF bytes.
        
        Args:
            pdf_bytes (bytes): PDF file content as bytes
            
        Returns:
            pd.DataFrame: DataFrame with columns ["Building Code", "Room", "Room Capacity"]
            
        Raises:
            Exception: If PDF parsing fails
        """
        try:
            building_data = []
            room_data = []
            
            # Track rooms already visited to avoid aliases
            visited = set()
            
            with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
                logger.info(f"Processing PDF with {len(pdf.pages)} pages")
                
                for page_num, page in enumerate(pdf.pages):
                    logger.debug(f"Processing page {page_num + 1}")
                    text = page.extract_text()
                    
                    if text:
                        for line_num, line in enumerate(text.split("\n")):
                            line = line.strip()
                            
                            if not line:
                                continue
                            
                            # Match building name and code
                            building_match = self.building_pattern.search(line)
                            if building_match:
                                building_name, bldg_code, *_ = building_match.groups()
                                if bldg_code not in visited:
                                    building_data.append([building_name, bldg_code])
                                    visited.add(bldg_code)
                                    logger.debug(f"Found building: {building_name} ({bldg_code})")
                            
                            # Match capacity data
                            room_match = self.room_pattern.search(line)
                            if room_match:
                                bldg_code, room, capacity = room_match.groups()
                                try:
                                    # Validate capacity is a number
                                    capacity_int = int(capacity)
                                    room_data.append([bldg_code, room, capacity_int])
                                    logger.debug(f"Found room: {bldg_code} {room} (capacity: {capacity_int})")
                                except ValueError:
                                    logger.warning(f"Invalid capacity value '{capacity}' for room {bldg_code} {room}")
                                    continue
            
            if not room_data:
                raise ValueError("No room capacity data found in PDF")
            
            # Create DataFrame with room capacity data
            room_df = pd.DataFrame(room_data, columns=["Building Code", "Room", "Room Capacity"])
            
            logger.info(f"Successfully parsed {len(room_df)} room capacity records")
            logger.info(f"Found {len(building_data)} unique buildings")
            
            # Log some statistics
            if not room_df.empty:
                logger.info(f"Capacity range: {room_df['Room Capacity'].min()} - {room_df['Room Capacity'].max()}")
                logger.info(f"Buildings found: {sorted(room_df['Building Code'].unique())}")
            
            return room_df
            
        except Exception as e:
            logger.error(f"Error parsing PDF: {str(e)}", exc_info=True)
            raise Exception(f"Failed to parse PDF: {str(e)}")
    
    def validate_parsed_data(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Validate the parsed room capacity data.
        
        Args:
            df (pd.DataFrame): Parsed room capacity data
            
        Returns:
            Dict[str, Any]: Validation results with statistics and warnings
        """
        validation_results = {
            'is_valid': True,
            'warnings': [],
            'statistics': {},
            'errors': []
        }
        
        try:
            # Check if DataFrame is empty
            if df.empty:
                validation_results['is_valid'] = False
                validation_results['errors'].append("No data found in parsed results")
                return validation_results
            
            # Check required columns
            required_columns = ["Building Code", "Room", "Room Capacity"]
            missing_columns = [col for col in required_columns if col not in df.columns]
            if missing_columns:
                validation_results['is_valid'] = False
                validation_results['errors'].append(f"Missing required columns: {missing_columns}")
                return validation_results
            
            # Check for null values
            null_counts = df.isnull().sum()
            if null_counts.any():
                validation_results['warnings'].append(f"Found null values: {null_counts.to_dict()}")
            
            # Check capacity values
            invalid_capacities = df[df['Room Capacity'] <= 0]
            if not invalid_capacities.empty:
                validation_results['warnings'].append(f"Found {len(invalid_capacities)} rooms with invalid capacity (<=0)")
            
            # Check for duplicate rooms
            duplicates = df.duplicated(subset=['Building Code', 'Room'])
            if duplicates.any():
                duplicate_count = duplicates.sum()
                validation_results['warnings'].append(f"Found {duplicate_count} duplicate room entries")
            
            # Generate statistics
            validation_results['statistics'] = {
                'total_rooms': len(df),
                'unique_buildings': df['Building Code'].nunique(),
                'capacity_stats': {
                    'min': int(df['Room Capacity'].min()),
                    'max': int(df['Room Capacity'].max()),
                    'mean': float(df['Room Capacity'].mean()),
                    'median': float(df['Room Capacity'].median())
                },
                'buildings': sorted(df['Building Code'].unique().tolist())
            }
            
            logger.info(f"Validation completed: {validation_results['statistics']}")
            
        except Exception as e:
            validation_results['is_valid'] = False
            validation_results['errors'].append(f"Validation error: {str(e)}")
            logger.error(f"Error during validation: {str(e)}", exc_info=True)
        
        return validation_results