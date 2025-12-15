"""
Data Processing Module for Georgia Tech Enrollment Data

This module handles the compilation and processing of enrollment data,
including CSV generation, room capacity integration, and data formatting.
"""

import asyncio
import logging
import pandas as pd
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from zoneinfo import ZoneInfo

from scheduler_client import SchedulerClient

logger = logging.getLogger(__name__)

class DataProcessor:
    """Handles enrollment data processing and CSV generation."""
    
    def __init__(self):
        """Initialize the data processor."""
        self.room_capacity_data: Optional[pd.DataFrame] = None
        self.building_mappings: Optional[pd.DataFrame] = None
        self._capacity_data_loaded = False
        self._building_mappings_loaded = False
    
    def ensure_capacity_data_loaded(self):
        """Ensure room capacity data and building mappings are loaded and cached."""
        try:
            if not self._capacity_data_loaded:
                self._load_room_capacity_data()
                self._capacity_data_loaded = True
            
            if not self._building_mappings_loaded:
                self._load_building_mappings()
                self._building_mappings_loaded = True
                
            logger.debug("Capacity data and building mappings are loaded and cached")
            
        except Exception as e:
            logger.error(f"Error ensuring capacity data is loaded: {e}")
            # Set flags to prevent repeated attempts in the same function execution
            self._capacity_data_loaded = True
            self._building_mappings_loaded = True
    
    def initialize_with_capacity_data(self):
        """
        Initialize the processor and preload capacity data for better performance.
        This should be called once during Lambda function initialization.
        """
        try:
            logger.info("Initializing DataProcessor with capacity data...")
            self.ensure_capacity_data_loaded()
            
            # Log initialization status
            capacity_count = len(self.room_capacity_data) if self.room_capacity_data is not None else 0
            mapping_count = len(self.building_mappings) if self.building_mappings is not None else 0
            
            logger.info(f"DataProcessor initialized: {capacity_count} capacity records, {mapping_count} building mappings")
            
        except Exception as e:
            logger.error(f"Error initializing DataProcessor with capacity data: {e}")
            # Continue with empty data rather than failing
    
    async def compile_enrollment_data(
        self,
        nterms: int,
        subjects: List[str],
        ranges: List[Tuple[int, int]],
        include_summer: bool,
        save_all: bool,
        save_grouped: bool
    ) -> Dict[str, Any]:
        """
        Generate enrollment data CSV files with requested parameters.

        Args:
            nterms: Number of most recent terms to process
            subjects: Which subjects to fetch courses for
            ranges: Which course number ranges to process
            include_summer: Whether to include summer terms in term count
            save_all: Whether to output ungrouped course data
            save_grouped: Whether to group crosslisted courses

        Returns:
            Dictionary containing generated file information
            
        Raises:
            ValueError: If invalid parameters or no terms available
            RuntimeError: If data fetching or processing fails
        """
        try:
            logger.info(f"Starting data compilation for {nterms} terms (include_summer={include_summer})")
            
            async with SchedulerClient() as client:
                # Fetch terms with enhanced error handling
                try:
                    terms = await client.fetch_nterms(nterms, include_summer)
                except ValueError as e:
                    raise ValueError(f"Invalid term count parameter: {str(e)}") from e
                except RuntimeError as e:
                    raise RuntimeError(f"Failed to fetch terms from GT Scheduler: {str(e)}") from e
                
                if not terms:
                    raise ValueError(f"No terms available with the specified criteria (nterms={nterms}, include_summer={include_summer})")
                
                # Log detailed term information
                parsed_terms = [client.parse_term(term) for term in terms]
                summer_terms = [term for term in parsed_terms if "Summer" in term]
                non_summer_terms = [term for term in parsed_terms if "Summer" not in term]
                
                logger.info(f"Processing {len(terms)} terms: {parsed_terms}")
                logger.info(f"Term breakdown: {len(non_summer_terms)} regular terms, {len(summer_terms)} summer terms")
                
                term_dfs = []
                last_updated_time = ""
                processed_terms = []
                
                for i, term in enumerate(terms):
                    term_name = client.parse_term(term)
                    logger.info(f"Processing term {i+1}/{len(terms)}: {term_name}")
                    
                    try:
                        # Fetch and process term data
                        data = await client.fetch_data(term=term)
                        if not data:
                            logger.warning(f"No data found for term {term_name}, skipping")
                            continue
                        
                        # Update timestamp (use most recent for combined files)
                        if not last_updated_time:
                            last_updated_time = self._format_timestamp(data.get('updatedAt', ''))
                        
                        # Process term data with filtering
                        term_data = await client.process_term(
                            term=term, 
                            subjects=subjects, 
                            ranges=ranges, 
                            data=data
                        )
                        
                        if not term_data:
                            logger.warning(f"No course data found for term {term_name} with current filters, skipping")
                            continue
                        
                        # Format dataframe with room capacity integration
                        df = self.format_dataframe(term_data)
                        
                        if df.empty:
                            logger.warning(f"No valid data after formatting for term {term_name}, skipping")
                            continue
                        
                        processed_terms.append(term_name)
                        
                        # Always use combined file mode - collect all term data
                        term_dfs.append(df)
                        
                        logger.info(f"Successfully processed {len(df)} records for term {term_name}")
                        
                    except Exception as term_error:
                        logger.error(f"Error processing term {term_name}: {term_error}")
                        # Continue with other terms rather than failing completely
                        continue
                
                # Validate that we processed at least some terms
                if not processed_terms and not term_dfs:
                    raise RuntimeError(f"No terms could be processed successfully. Requested {nterms} terms but none contained valid data with the specified filters.")
                
                # Handle file generation - always use combined file mode
                generated_files = []
                
                if term_dfs:
                    # Generate combined files for all terms
                    logger.info(f"Combining data from {len(term_dfs)} terms into single file")
                    combined_df = pd.concat(term_dfs, ignore_index=True)
                    generated_files = self._generate_combined_files(
                        combined_df, last_updated_time, save_all, save_grouped
                    )
                
                # Validate that we have generated the expected files based on preferences
                if not generated_files:
                    logger.warning("No files were generated despite having processed data")
                else:
                    # Log file generation summary
                    ungrouped_count = len([f for f in generated_files if f['type'] == 'ungrouped'])
                    grouped_count = len([f for f in generated_files if f['type'] == 'grouped'])
                    total_size = sum(f['size_bytes'] for f in generated_files)
                    
                    logger.info(f"File generation summary:")
                    logger.info(f"  - Total files: {len(generated_files)}")
                    logger.info(f"  - Ungrouped files: {ungrouped_count}")
                    logger.info(f"  - Grouped files: {grouped_count}")
                    logger.info(f"  - Total size: {total_size:,} bytes")
                    logger.info(f"  - Output format: combined")
                    logger.info(f"  - Grouping options: save_all={save_all}, save_grouped={save_grouped}")
                
                # Log completion summary
                total_records = sum(len(df) for df in term_dfs) if term_dfs else 0
                logger.info(f"Data compilation completed successfully:")
                logger.info(f"  - Terms requested: {nterms} (include_summer={include_summer})")
                logger.info(f"  - Terms processed: {len(processed_terms)} ({', '.join(processed_terms)})")
                logger.info(f"  - Total records: {total_records}")
                logger.info(f"  - Files generated: {len(generated_files)}")
                
                return {
                    'success': True,
                    'files': generated_files,
                    'terms_processed': len(processed_terms),
                    'terms_requested': nterms,
                    'processed_term_names': processed_terms,
                    'include_summer': include_summer,
                    'last_updated': last_updated_time,
                    'total_records': total_records
                }
                
        except ValueError:
            # Re-raise validation errors
            raise
        except RuntimeError:
            # Re-raise runtime errors  
            raise
        except Exception as e:
            logger.error(f"Unexpected error in compile_enrollment_data: {e}")
            raise RuntimeError(f"Data compilation failed: {str(e)}") from e
    
    def format_dataframe(self, data: List[Dict[str, Any]]) -> pd.DataFrame:
        """
        Format dataframe with additional columns and compute room loss.

        Args:
            data: Course data list

        Returns:
            Formatted dataframe
        """
        if not data:
            return pd.DataFrame()
        
        try:
            # Create dataframe from data
            df = pd.DataFrame([d for d in data if d is not None])
            
            if df.empty:
                return df
            
            # Ensure capacity data is loaded before processing
            self.ensure_capacity_data_loaded()
            
            # Append room capacity data and building codes
            df = self.append_room_data(df)
            
            # Calculate room utilization loss
            df["Loss"] = self._calculate_loss(df)
            
            # Sort by term and course for consistent output
            sort_columns = []
            if "Term" in df.columns:
                sort_columns.append("Term")
            if "Course" in df.columns:
                sort_columns.append("Course")
            
            if sort_columns:
                df = df.sort_values(by=sort_columns)
            
            logger.info(f"Formatted dataframe with {len(df)} rows, capacity data available for {df['Room Capacity'].notna().sum()} rooms")
            return df
            
        except Exception as e:
            logger.error(f"Error formatting dataframe: {e}")
            return pd.DataFrame()
    
    def append_room_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Supplement course dataframe with room capacity data.
        Uses the same algorithm as the original archive implementation.

        Args:
            df: Course data dataframe

        Returns:
            Dataframe with room capacity data
        """
        try:
            if df.empty:
                return df
            
            # Ensure capacity data and building mappings are loaded
            self.ensure_capacity_data_loaded()
            
            # Follow the exact archive algorithm:
            # 1. Create locations dataframe and merge with building mappings
            locations = df[["CRN", "Building", "Room"]].copy()
            
            if self.building_mappings is not None and not self.building_mappings.empty:
                locations = locations.merge(self.building_mappings, on="Building", how="left")
                logger.debug(f"Merged building mappings: {len(locations)} locations processed")
                
                # Debug: Log some sample building mappings
                mapped_buildings = locations[locations['Building Code'].notna()]
                if not mapped_buildings.empty:
                    logger.debug(f"Sample mapped buildings: {mapped_buildings[['Building', 'Building Code']].head().to_dict('records')}")
                
                unmapped_buildings = locations[locations['Building Code'].isna()]
                if not unmapped_buildings.empty:
                    unique_unmapped = unmapped_buildings['Building'].unique()
                    logger.warning(f"Unmapped buildings: {list(unique_unmapped)}")
            else:
                logger.error("No building mappings available - cannot match room capacity data")
                df["Building Code"] = ""
                df["Room Capacity"] = None
                return df
            
            # 2. Use building code and room tuple to index into and fetch capacity data
            if self.room_capacity_data is not None and not self.room_capacity_data.empty:
                try:
                    capacities = self.room_capacity_data.copy()
                    
                    # Create index tuples - handle NaN building codes by converting to empty string
                    capacities['idx'] = list(zip(
                        capacities['Building Code'].astype(str).str.lstrip('0'), 
                        capacities['Room']
                    ))
                    
                    # For locations, fill NaN building codes with empty string before creating tuples
                    locations['Building Code'] = locations['Building Code'].fillna('')
                    locations['idx'] = list(zip(
                        locations['Building Code'].astype(str).str.lstrip('0'), 
                        locations['Room']
                    ))
                    
                    # Debug: Log some sample indices
                    logger.debug(f"Sample capacity indices: {list(capacities['idx'].head())}")
                    logger.debug(f"Sample location indices: {list(locations['idx'].head())}")
                    
                    # Set index and map capacity data
                    capacities.set_index('idx', inplace=True)
                    locations["Room Capacity"] = locations["idx"].map(capacities["Room Capacity"])
                    
                    # Count successful matches for logging
                    matched_count = locations["Room Capacity"].notna().sum()
                    total_count = len(locations)
                    
                    logger.info(f"Room capacity data merged: {matched_count}/{total_count} locations matched")
                    
                    # Debug: Show some successful matches
                    successful_matches = locations[locations["Room Capacity"].notna()]
                    if not successful_matches.empty:
                        logger.debug(f"Sample successful matches: {successful_matches[['Building', 'Building Code', 'Room', 'Room Capacity']].head().to_dict('records')}")
                    
                    # Clean up the temporary index column
                    locations = locations.drop(columns=["idx"])
                    
                except Exception as merge_error:
                    logger.error(f"Error merging room capacity data: {merge_error}")
                    locations["Room Capacity"] = None
            else:
                logger.error("No room capacity data available")
                locations["Room Capacity"] = None
            
            # 3. Merge back with original dataframe (following archive pattern)
            # Keep only the columns we need to add, similar to archive's approach
            capacity_info = locations[["CRN", "Building Code", "Room Capacity"]].copy()
            
            # Merge back with original dataframe
            result = df.merge(capacity_info, on="CRN", how="left")
            
            logger.info(f"Appended room data to {len(result)} rows")
            return result
            
        except Exception as e:
            logger.error(f"Error appending room data: {e}")
            # Return original dataframe with empty room capacity column if error
            df["Building Code"] = ""
            df["Room Capacity"] = None
            return df
    
    def group_by_room_and_time(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Group crosslisted courses sharing rooms/meeting times.

        Args:
            data: Course data dataframe

        Returns:
            Dataframe with crosslisted course groupings
        """
        try:
            if data.empty:
                return data
            
            def unique_join(series):
                """Join unique values with comma separation."""
                return ', '.join(set(str(x) for x in series if pd.notna(x)))
            
            # Columns to group by
            group_columns = [
                'Term', 
                'Start Time', 
                'End Time', 
                'Days', 
                'Building', 
                'Building Code', 
                'Room', 
                'Room Capacity',
            ]
            
            # Filter group columns to only include those that exist
            existing_group_columns = [col for col in group_columns if col in data.columns]
            
            # Define aggregate functions
            agg_functions = {
                "Subject": ("Subject", unique_join),
                "Course": ("Course", unique_join),
                "CRN": ("CRN", unique_join),
                "Primary Instructor(s)": ("Primary Instructor(s)", unique_join),
                "Additional Instructor(s)": ("Additional Instructor(s)", unique_join),
                "Enrollment Actual": ("Enrollment Actual", "sum"),
                "Enrollment Maximum": ("Enrollment Maximum", "sum"),
                "Enrollment Seats Available": ("Enrollment Seats Available", "sum"),
                "Waitlist Capacity": ("Waitlist Capacity", "sum"),
                "Waitlist Actual": ("Waitlist Actual", "sum"),
                "Waitlist Seats Available": ("Waitlist Seats Available", "sum"),
                "Loss": ("Loss", "sum"),
                "Count": ("CRN", "count"),
            }
            
            # Add any additional columns not in the predefined list
            for col in data.columns:
                if col not in agg_functions and col not in existing_group_columns:
                    agg_functions[col] = (col, unique_join)
            
            # Filter agg_functions to only include columns that exist in the dataframe
            existing_agg_functions = {
                k: v for k, v in agg_functions.items() 
                if v[0] in data.columns
            }
            
            # Perform grouping
            grouped = data.groupby(existing_group_columns, dropna=False).agg(
                **existing_agg_functions
            ).reset_index()
            
            logger.info(f"Grouped {len(data)} rows into {len(grouped)} groups")
            return grouped
            
        except Exception as e:
            logger.error(f"Error grouping data: {e}")
            return data  # Return original data if grouping fails
    
    def _calculate_loss(self, df: pd.DataFrame) -> pd.Series:
        """
        Calculate room utilization loss as (1 - enrollment/capacity).
        
        Args:
            df: Dataframe with enrollment and capacity data
            
        Returns:
            Series with loss calculations
        """
        try:
            # Handle missing or invalid data
            enrollment = pd.to_numeric(df.get("Enrollment Actual", 0), errors='coerce').fillna(0)
            capacity = pd.to_numeric(df.get("Room Capacity", 0), errors='coerce')
            
            # Initialize loss series with NaN
            loss = pd.Series([float('nan')] * len(df), index=df.index)
            
            # Calculate loss only where we have valid capacity data
            valid_capacity_mask = (capacity.notna()) & (capacity > 0)
            
            if valid_capacity_mask.any():
                # Calculate loss for valid capacity data: (1 - enrollment/capacity)
                valid_loss = 1.0 - (enrollment[valid_capacity_mask] / capacity[valid_capacity_mask])
                loss[valid_capacity_mask] = valid_loss
                
                # Log statistics
                valid_count = valid_capacity_mask.sum()
                total_count = len(df)
                avg_loss = valid_loss.mean()
                
                logger.debug(f"Calculated loss for {valid_count}/{total_count} records, average loss: {avg_loss:.3f}")
            else:
                logger.debug("No valid capacity data found for loss calculation")
            
            return loss
            
        except Exception as e:
            logger.error(f"Error calculating loss: {e}")
            return pd.Series([float('nan')] * len(df), index=df.index)
    
    def _load_room_capacity_data(self):
        """Load room capacity data from S3 or local storage."""
        try:
            import boto3
            import os
            from io import StringIO
            
            bucket_name = os.getenv('S3_BUCKET_NAME')
            if not bucket_name:
                logger.warning("S3_BUCKET_NAME not configured, using empty capacity data")
                self.room_capacity_data = pd.DataFrame(columns=['Building Code', 'Room', 'Room Capacity'])
                return
            
            s3_client = boto3.client('s3')
            
            # Try to load the latest capacity file
            try:
                response = s3_client.get_object(
                    Bucket=bucket_name,
                    Key='capacity-data/room_capacity_data.csv'
                )
                csv_content = response['Body'].read().decode('utf-8')
                self.room_capacity_data = pd.read_csv(StringIO(csv_content))
                
                # Ensure required columns exist
                required_columns = ['Building Code', 'Room', 'Room Capacity']
                for col in required_columns:
                    if col not in self.room_capacity_data.columns:
                        logger.warning(f"Missing column '{col}' in capacity data")
                        self.room_capacity_data[col] = None
                
                # Convert Room Capacity to numeric, handling errors gracefully
                self.room_capacity_data['Room Capacity'] = pd.to_numeric(
                    self.room_capacity_data['Room Capacity'], 
                    errors='coerce'
                )
                
                logger.info(f"Successfully loaded {len(self.room_capacity_data)} room capacity records from S3")
                
            except s3_client.exceptions.NoSuchKey:
                logger.info("No room capacity file found in S3, using empty data")
                self.room_capacity_data = pd.DataFrame(columns=['Building Code', 'Room', 'Room Capacity'])
            except Exception as s3_error:
                logger.warning(f"Failed to load capacity data from S3: {s3_error}, using empty data")
                self.room_capacity_data = pd.DataFrame(columns=['Building Code', 'Room', 'Room Capacity'])
            
        except Exception as e:
            logger.error(f"Error loading room capacity data: {e}")
            self.room_capacity_data = pd.DataFrame(columns=['Building Code', 'Room', 'Room Capacity'])
    
    def _load_building_mappings(self):
        """Load building name to code mappings."""
        try:
            import boto3
            import os
            from io import StringIO
            
            bucket_name = os.getenv('S3_BUCKET_NAME')
            if not bucket_name:
                logger.warning("S3_BUCKET_NAME not configured, using empty building mappings")
                self.building_mappings = pd.DataFrame(columns=['Building', 'Building Code'])
                return
            
            s3_client = boto3.client('s3')
            
            # Try to load the latest building mappings file
            try:
                response = s3_client.get_object(
                    Bucket=bucket_name,
                    Key='capacity-data/gt-scheduler-buildings.csv'
                )
                csv_content = response['Body'].read().decode('utf-8')
                self.building_mappings = pd.read_csv(StringIO(csv_content))
                
                # Ensure required columns exist
                required_columns = ['Building', 'Building Code']
                for col in required_columns:
                    if col not in self.building_mappings.columns:
                        logger.warning(f"Missing column '{col}' in building mappings")
                        self.building_mappings[col] = ""
                
                logger.info(f"Loaded {len(self.building_mappings)} building mappings from S3")
                
            except s3_client.exceptions.NoSuchKey:
                logger.info("No building mappings file found in S3, using empty data")
                self.building_mappings = pd.DataFrame(columns=['Building', 'Building Code'])
            except Exception as s3_error:
                logger.warning(f"Failed to load building mappings from S3: {s3_error}, using empty data")
                self.building_mappings = pd.DataFrame(columns=['Building', 'Building Code'])
            
        except Exception as e:
            logger.error(f"Error loading building mappings: {e}")
            self.building_mappings = pd.DataFrame(columns=['Building', 'Building Code'])
    
    def _format_timestamp(self, updated_at: str) -> str:
        """
        Format timestamp from GT Scheduler API.
        
        Args:
            updated_at: ISO timestamp string
            
        Returns:
            Formatted timestamp string
        """
        try:
            if not updated_at:
                return datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d-%H%M")
            
            # Parse ISO timestamp and convert to Eastern time
            dt = datetime.fromisoformat(updated_at.replace('Z', '+00:00'))
            eastern_dt = dt.astimezone(ZoneInfo("America/New_York"))
            return eastern_dt.strftime("%Y-%m-%d-%H%M")
            
        except Exception as e:
            logger.error(f"Error formatting timestamp: {e}")
            return datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d-%H%M")
    
    def _generate_term_files(
        self, 
        df: pd.DataFrame, 
        term_name: str, 
        timestamp: str,
        save_all: bool, 
        save_grouped: bool
    ) -> List[Dict[str, Any]]:
        """
        Generate file information for individual term data.
        
        Supports ungrouped, grouped, and both output formats with appropriate file naming
        and handles crosslisted course grouping logic.
        
        Args:
            df: Term dataframe with enrollment data
            term_name: Human-readable term name (e.g., "Spring 2025")
            timestamp: Formatted timestamp for file naming
            save_all: Whether to save ungrouped data
            save_grouped: Whether to save grouped data
            
        Returns:
            List of file information dictionaries with metadata
        """
        files = []
        
        try:
            if df.empty:
                logger.warning(f"Empty dataframe provided for term {term_name}, no files generated")
                return files
            
            # Generate base filename with proper formatting
            # Convert term name to filename-safe format (e.g., "Spring 2025" -> "spring_2025")
            safe_term_name = '_'.join(term_name.lower().split())
            base_name = f"{safe_term_name}_enrollment_data_{timestamp}.csv"
            
            # Generate ungrouped file if requested
            if save_all:
                try:
                    csv_content = df.to_csv(index=False)
                    files.append({
                        'filename': base_name,
                        'type': 'ungrouped',
                        'format': 'individual_term',
                        'term': term_name,
                        'data': df,
                        'csv_content': csv_content,
                        'size_bytes': len(csv_content.encode('utf-8')),
                        'record_count': len(df),
                        'description': f'Ungrouped enrollment data for {term_name}'
                    })
                    logger.debug(f"Generated ungrouped file for {term_name}: {len(df)} records")
                except Exception as e:
                    logger.error(f"Error generating ungrouped file for {term_name}: {e}")
            
            # Generate grouped file if requested
            if save_grouped:
                try:
                    # Apply crosslisted course grouping logic
                    grouped_df = self.group_by_room_and_time(df)
                    
                    if not grouped_df.empty:
                        grouped_name = f"grouped_{base_name}"
                        csv_content = grouped_df.to_csv(index=False)
                        
                        files.append({
                            'filename': grouped_name,
                            'type': 'grouped',
                            'format': 'individual_term',
                            'term': term_name,
                            'data': grouped_df,
                            'csv_content': csv_content,
                            'size_bytes': len(csv_content.encode('utf-8')),
                            'record_count': len(grouped_df),
                            'original_record_count': len(df),
                            'grouping_ratio': len(grouped_df) / len(df) if len(df) > 0 else 0,
                            'description': f'Grouped enrollment data for {term_name} (crosslisted courses combined)'
                        })
                        logger.debug(f"Generated grouped file for {term_name}: {len(df)} -> {len(grouped_df)} records (ratio: {len(grouped_df)/len(df):.2f})")
                    else:
                        logger.warning(f"Grouping resulted in empty dataframe for {term_name}")
                except Exception as e:
                    logger.error(f"Error generating grouped file for {term_name}: {e}")
            
            # Log generation summary
            file_types = [f['type'] for f in files]
            total_size = sum(f['size_bytes'] for f in files)
            logger.info(f"Generated {len(files)} files for term {term_name}: {file_types} (total size: {total_size:,} bytes)")
            
            return files
            
        except Exception as e:
            logger.error(f"Error generating term files for {term_name}: {e}")
            return []
    
    def _generate_combined_files(
        self, 
        df: pd.DataFrame, 
        timestamp: str,
        save_all: bool, 
        save_grouped: bool
    ) -> List[Dict[str, Any]]:
        """
        Generate file information for combined term data.
        
        Supports ungrouped, grouped, and both output formats for multi-term data
        with appropriate file naming and crosslisted course grouping logic.
        
        Args:
            df: Combined dataframe with data from multiple terms
            timestamp: Formatted timestamp for file naming
            save_all: Whether to save ungrouped data
            save_grouped: Whether to save grouped data
            
        Returns:
            List of file information dictionaries with metadata
        """
        files = []
        base_name = f"enrollment_data_{timestamp}.csv"
        
        try:
            if df.empty:
                logger.warning("Empty combined dataframe provided, no files generated")
                return files
            
            # Extract term information for metadata
            unique_terms = []
            if 'Term' in df.columns:
                unique_terms = sorted(df['Term'].unique().tolist())
            
            # Generate ungrouped combined file if requested
            if save_all:
                try:
                    csv_content = df.to_csv(index=False)
                    files.append({
                        'filename': base_name,
                        'type': 'ungrouped',
                        'format': 'combined_terms',
                        'terms': unique_terms,
                        'data': df,
                        'csv_content': csv_content,
                        'size_bytes': len(csv_content.encode('utf-8')),
                        'record_count': len(df),
                        'term_count': len(unique_terms),
                        'description': f'Ungrouped enrollment data for {len(unique_terms)} terms: {", ".join(unique_terms)}'
                    })
                    logger.debug(f"Generated combined ungrouped file: {len(df)} records across {len(unique_terms)} terms")
                except Exception as e:
                    logger.error(f"Error generating combined ungrouped file: {e}")
            
            # Generate grouped combined file if requested
            if save_grouped:
                try:
                    # Apply crosslisted course grouping logic across all terms
                    grouped_df = self.group_by_room_and_time(df)
                    
                    if not grouped_df.empty:
                        grouped_name = f"grouped_{base_name}"
                        csv_content = grouped_df.to_csv(index=False)
                        
                        files.append({
                            'filename': grouped_name,
                            'type': 'grouped',
                            'format': 'combined_terms',
                            'terms': unique_terms,
                            'data': grouped_df,
                            'csv_content': csv_content,
                            'size_bytes': len(csv_content.encode('utf-8')),
                            'record_count': len(grouped_df),
                            'original_record_count': len(df),
                            'term_count': len(unique_terms),
                            'grouping_ratio': len(grouped_df) / len(df) if len(df) > 0 else 0,
                            'description': f'Grouped enrollment data for {len(unique_terms)} terms: {", ".join(unique_terms)} (crosslisted courses combined)'
                        })
                        logger.debug(f"Generated combined grouped file: {len(df)} -> {len(grouped_df)} records (ratio: {len(grouped_df)/len(df):.2f})")
                    else:
                        logger.warning("Grouping resulted in empty combined dataframe")
                except Exception as e:
                    logger.error(f"Error generating combined grouped file: {e}")
            
            # Log generation summary
            file_types = [f['type'] for f in files]
            total_size = sum(f['size_bytes'] for f in files)
            logger.info(f"Generated {len(files)} combined files: {file_types} (total size: {total_size:,} bytes)")
            
            # Log detailed file information
            for file_info in files:
                logger.info(f"  - {file_info['filename']}: {file_info['record_count']:,} records, {file_info['size_bytes']:,} bytes")
            
            return files
            
        except Exception as e:
            logger.error(f"Error generating combined files: {e}")
            return []