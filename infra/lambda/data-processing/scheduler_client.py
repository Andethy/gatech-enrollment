"""
GT Scheduler Client for fetching enrollment and course data.

This module provides async HTTP client functionality for interacting with
Georgia Tech's scheduler APIs to fetch course and enrollment data.
"""

import aiohttp
import asyncio
import logging
import re
import time
from typing import Dict, List, Optional, Tuple, Any

logger = logging.getLogger(__name__)

class SchedulerClient:
    """Client for interacting with GT Scheduler APIs."""
    
    CRAWLER_URL = "https://gt-scheduler.github.io/crawler-v2/"
    SEAT_URL = "https://gt-scheduler.azurewebsites.net/proxy/class_section?"
    
    def __init__(self):
        """Initialize the scheduler client."""
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def __aenter__(self):
        """Async context manager entry."""
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30, connect=10),
            connector=aiohttp.TCPConnector(limit=10, limit_per_host=5)
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.close()
    
    def parse_term(self, term: str) -> str:
        """
        Parse GT Scheduler term string to readable format.

        Args:
            term: GT scheduler term string in YYYYMM format (e.g., 202502)

        Returns:
            Readable term format (e.g., "Spring 2025")
        """
        try:
            year, month = term[:4], int(term[4:])
            
            if month < 5:
                semester = "Spring"
            elif month < 8:
                semester = "Summer"
            else:
                semester = "Fall"

            return f"{semester} {year}"
        except (ValueError, IndexError) as e:
            logger.error(f"Error parsing term '{term}': {e}")
            return term  # Return original if parsing fails
    
    async def fetch_nterms(self, n: int, include_summer: bool = True) -> List[str]:
        """
        Get the term names for the n most recent terms.
        
        Fetches the specified number of most recent academic terms, with optional
        summer term inclusion/exclusion. Terms are sorted chronologically with
        the most recent terms first.

        Args:
            n: Number of terms to fetch (must be positive integer)
            include_summer: Whether to include summer terms in the count

        Returns:
            List of term strings in chronological order (most recent first)
            
        Raises:
            ValueError: If n is not a positive integer
            RuntimeError: If unable to fetch terms data from GT Scheduler
        """
        try:
            # Validate input parameters
            if not isinstance(n, int) or n < 1:
                raise ValueError(f"Term count must be a positive integer, got: {n}")
            
            # Fetch terms data from GT Scheduler
            url = f"{self.CRAWLER_URL}"
            data = await self._fetch_json(url)
            if not data:
                raise RuntimeError("Failed to fetch terms data from GT Scheduler API")

            # Extract and sort terms chronologically (most recent first)
            available_terms = [t["term"] for t in data.get("terms", [])]
            if not available_terms:
                logger.warning("No terms found in GT Scheduler data")
                return []
            
            # Sort terms in reverse chronological order (most recent first)
            sorted_terms = sorted(available_terms, reverse=True)
            
            # Filter terms based on summer inclusion preference
            selected_terms = []
            for term in sorted_terms:
                if len(selected_terms) >= n:
                    break
                
                # Check if this is a summer term
                parsed_term = self.parse_term(term)
                is_summer = "Summer" in parsed_term
                
                # Include term based on summer inclusion preference
                if include_summer or not is_summer:
                    selected_terms.append(term)
                else:
                    logger.debug(f"Skipping summer term: {parsed_term}")
            
            # Log the selection results
            selected_parsed = [self.parse_term(term) for term in selected_terms]
            logger.info(f"Selected {len(selected_terms)} terms (include_summer={include_summer}): {selected_parsed}")
            
            # Warn if we couldn't get the requested number of terms
            if len(selected_terms) < n:
                available_count = len([t for t in sorted_terms if include_summer or "Summer" not in self.parse_term(t)])
                logger.warning(f"Requested {n} terms but only {len(selected_terms)} available (include_summer={include_summer}, total_available={available_count})")
            
            return selected_terms
            
        except ValueError:
            # Re-raise validation errors
            raise
        except RuntimeError:
            # Re-raise runtime errors
            raise
        except Exception as e:
            logger.error(f"Unexpected error fetching terms: {e}")
            raise RuntimeError(f"Failed to fetch terms: {str(e)}") from e
    
    async def fetch_data(self, term: str) -> Optional[Dict[str, Any]]:
        """
        Get the term data and metadata for the specified term.

        Args:
            term: GT scheduler term string

        Returns:
            Processed GT scheduler term dictionary object
        """
        try:
            url = f"{self.CRAWLER_URL}{term}.json"
            data = await self._fetch_json(url)
            if not data:
                logger.error(f"Failed to fetch data for term {term}")
                return None

            # Format period times
            periods = data.get("caches", {}).get("periods", [])
            formatted_periods = []
            
            for period in periods:
                if period == "TBA":
                    formatted_periods.append(("", ""))
                else:
                    try:
                        start_time, end_time = period.split(" - ")
                        start_formatted = f"{start_time[:2]}:{start_time[2:]}"
                        end_formatted = f"{end_time[:2]}:{end_time[2:]}"
                        formatted_periods.append((start_formatted, end_formatted))
                    except (ValueError, IndexError):
                        formatted_periods.append(("", ""))
            
            processed = {
                "courses": data.get("courses", {}),
                "updatedAt": data.get("updatedAt", ""),
                "periods": formatted_periods,
                **{k: v for k, v in data.get("caches", {}).items() if k != "periods"}
            }

            logger.info(f"Successfully fetched data for term {term}")
            return processed
            
        except Exception as e:
            logger.error(f"Error fetching data for term {term}: {e}")
            return None
    
    async def fetch_enrollment(self, term: str, crns: List[str]) -> Dict[str, Dict[str, Optional[int]]]:
        """
        Get enrollment data for all specified CRNs.

        Args:
            term: GT scheduler term string
            crns: List of CRN strings

        Returns:
            Mapping of CRN to enrollment dictionary
        """
        if not crns:
            return {}
        
        try:
            logger.info(f"Fetching enrollment data for {len(crns)} CRNs")
            
            # Create URLs for all CRNs
            urls = [f"{self.SEAT_URL}term={term}&crn={crn}" for crn in crns]
            
            # Fetch all enrollment data concurrently with retry logic
            responses = await self._fetch_enrollment_batch(urls, crns)
            
            # Parse enrollment data from HTML responses
            enrollment_data = {}
            for crn, response in responses.items():
                enrollment_info = self._parse_enrollment_response(response)
                enrollment_data[crn] = enrollment_info
            
            logger.info(f"Successfully fetched enrollment data for {len(enrollment_data)} CRNs")
            return enrollment_data
            
        except Exception as e:
            logger.error(f"Error fetching enrollment data: {e}")
            return {}
    
    async def _fetch_enrollment_batch(self, urls: List[str], crns: List[str]) -> Dict[str, str]:
        """
        Fetch enrollment data for multiple URLs with retry logic.
        
        Args:
            urls: List of URLs to fetch
            crns: Corresponding CRNs for the URLs
            
        Returns:
            Dictionary mapping CRN to response text
        """
        responses = {}
        
        # Process in batches to avoid overwhelming the server
        batch_size = 10
        for i in range(0, len(urls), batch_size):
            batch_urls = urls[i:i + batch_size]
            batch_crns = crns[i:i + batch_size]
            
            tasks = []
            for url, crn in zip(batch_urls, batch_crns):
                task = self._fetch_with_retry(url, max_retries=3)
                tasks.append((crn, task))
            
            # Execute batch concurrently
            batch_results = await asyncio.gather(
                *[task for _, task in tasks], 
                return_exceptions=True
            )
            
            # Process results
            for (crn, _), result in zip(tasks, batch_results):
                if isinstance(result, Exception):
                    logger.warning(f"Failed to fetch enrollment for CRN {crn}: {result}")
                    responses[crn] = ""
                else:
                    responses[crn] = result or ""
            
            # Small delay between batches to be respectful to the server
            if i + batch_size < len(urls):
                await asyncio.sleep(0.1)
        
        return responses
    
    async def _fetch_with_retry(self, url: str, max_retries: int = 3) -> Optional[str]:
        """
        Fetch URL with retry logic and exponential backoff.
        
        Args:
            url: URL to fetch
            max_retries: Maximum number of retry attempts
            
        Returns:
            Response text or None if all retries failed
        """
        for attempt in range(max_retries + 1):
            try:
                if not self.session:
                    raise RuntimeError("HTTP session not initialized")
                
                async with self.session.get(url) as response:
                    if response.status == 200:
                        return await response.text()
                    elif response.status == 429:  # Rate limited
                        wait_time = 2 ** attempt
                        logger.warning(f"Rate limited, waiting {wait_time}s before retry")
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        logger.warning(f"HTTP {response.status} for {url}")
                        
            except asyncio.TimeoutError:
                logger.warning(f"Timeout for {url} (attempt {attempt + 1})")
            except Exception as e:
                logger.warning(f"Error fetching {url} (attempt {attempt + 1}): {e}")
            
            if attempt < max_retries:
                wait_time = 2 ** attempt
                await asyncio.sleep(wait_time)
        
        return None
    
    async def _fetch_json(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Fetch JSON data from URL with retry logic.
        
        Args:
            url: URL to fetch JSON from
            
        Returns:
            Parsed JSON data or None if failed
        """
        response_text = await self._fetch_with_retry(url)
        if response_text:
            try:
                import json
                return json.loads(response_text)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON from {url}: {e}")
        return None
    
    def _parse_enrollment_response(self, response: str) -> Dict[str, Optional[int]]:
        """
        Parse enrollment information from HTML response.
        
        Args:
            response: HTML response text
            
        Returns:
            Dictionary with enrollment information
        """
        enrollment_info = {
            "Enrollment Actual": None,
            "Enrollment Maximum": None,
            "Enrollment Seats Available": None,
            "Waitlist Capacity": None,
            "Waitlist Actual": None,
            "Waitlist Seats Available": None
        }

        for key in enrollment_info.keys():
            pattern = rf"{re.escape(key)}:</span> <span\s+dir=\"ltr\">(\d+)</span>"
            try:
                match = re.search(pattern, response)
                if match:
                    enrollment_info[key] = int(match.group(1))
            except (ValueError, AttributeError) as e:
                logger.debug(f"Could not parse {key} from response: {e}")

        return enrollment_info
    
    def parse_course_data(self, data: Dict[str, Any], subjects: List[str], ranges: List[Tuple[int, int]]) -> Tuple[Dict[str, List[str]], Dict[str, Dict[str, Any]]]:
        """
        Parse relevant course data for specified subjects and ranges.

        Args:
            data: GT scheduler term data dictionary
            subjects: List of subject strings (already normalized to uppercase)
            ranges: List of course number ranges to apply

        Returns:
            Tuple of (courses-to-crn dict, crn-to-data dict)
        """
        courses = {}  # {course: [crns]}
        parsed_data = {}  # {crn: data}
        
        # Subjects are already normalized to uppercase by validation module
        subjects_upper = subjects
        
        try:
            for course, course_data in data.get("courses", {}).items():
                match = re.match(r"([A-Za-z]+)\s(\d+)(\D*)", course)
                if not match:
                    continue
                
                sub, num_str, _ = match.groups()
                try:
                    num = int(num_str)
                except ValueError:
                    continue
                
                # Check subject filter (case-insensitive)
                valid_subject = not subjects_upper or sub.upper() in subjects_upper
                
                # Check number range filter
                valid_number = not ranges or any(low <= num <= high for low, high in ranges)
                
                if valid_subject and valid_number:
                    try:
                        crns = []
                        sections = course_data[1] if len(course_data) > 1 else {}
                        
                        for section_name, section_data in sections.items():
                            if not section_data or len(section_data) < 2:
                                continue
                            
                            crn = section_data[0]
                            crns.append(crn)
                            
                            # Parse instructor information
                            primary = []
                            additional = []
                            
                            if len(section_data) > 1 and len(section_data[1]) > 0:
                                meeting_info = section_data[1][0]
                                if len(meeting_info) > 4:
                                    instructors = meeting_info[4]
                                    for instructor in instructors:
                                        if "(P)" in instructor:
                                            primary.append(instructor[:-4])
                                        else:
                                            additional.append(instructor)
                                
                                # Parse meeting time and location
                                period_idx = meeting_info[0] if len(meeting_info) > 0 else 0
                                days = meeting_info[1] if len(meeting_info) > 1 else ""
                                location = meeting_info[2] if len(meeting_info) > 2 else "TBA"
                                
                                # Get time from periods
                                periods = data.get("periods", [])
                                start_time, end_time = "", ""
                                if 0 <= period_idx < len(periods):
                                    start_time, end_time = periods[period_idx]
                                
                                # Parse building and room
                                building = ""
                                room = ""
                                if location != "TBA":
                                    location_parts = location.split()
                                    if location_parts:
                                        room = location_parts[-1]
                                        building = ' '.join(location_parts[:-1])
                                
                                parsed_data[crn] = {
                                    "Section": section_name,
                                    "Start Time": start_time,
                                    "End Time": end_time,
                                    "Days": days,
                                    "Building": building,
                                    "Room": room,
                                    "Primary Instructor(s)": ', '.join(primary),
                                    "Additional Instructor(s)": ', '.join(additional),
                                }
                        
                        if crns:
                            courses[course] = crns
                            
                    except Exception as e:
                        logger.warning(f"Error parsing course {course}: {e}")
                        continue
            
            logger.info(f"Parsed {len(courses)} courses with {len(parsed_data)} sections")
            return courses, parsed_data
            
        except Exception as e:
            logger.error(f"Error parsing course data: {e}")
            return {}, {}
    
    def process_course(self, term: str, course: str, crns: List[str], 
                      data: Dict[str, Dict[str, Any]], 
                      enrollment: Dict[str, Dict[str, Optional[int]]]) -> List[Dict[str, Any]]:
        """
        Aggregate parsed course data, enrollment data, and filter data.

        Args:
            term: GT scheduler term string
            course: Course string
            crns: List of CRNs
            data: Parsed course data
            enrollment: Enrollment mapping (CRNs to enrollment)

        Returns:
            List of output data rows
        """
        sections = []
        
        for crn in crns:
            section_data = {
                "Term": self.parse_term(term),
                "Subject": course.split(" ")[0],
                "Course": course,
                "CRN": crn,
                **data.get(crn, {}),
                **enrollment.get(crn, {})
            }
            sections.append(section_data)

        return sections
    
    async def process_term(self, term: str, subjects: List[str], 
                          ranges: List[Tuple[int, int]], 
                          data: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Compile data for all courses in the term with specified filters.

        Args:
            term: GT scheduler term string
            subjects: List of subject strings
            ranges: List of course number ranges to apply
            data: Unparsed course data (will fetch if None)

        Returns:
            List of output data rows
        """
        try:
            if data is None:
                data = await self.fetch_data(term=term)
                if not data:
                    logger.error(f"Failed to fetch data for term {term}")
                    return []

            logger.info(f"Processing term {self.parse_term(term)}")
            
            # Parse course data
            courses, parsed_data = self.parse_course_data(data, subjects=subjects, ranges=ranges)
            
            if not parsed_data:
                logger.warning(f"No courses found for term {term} with given filters")
                return []
            
            # Fetch enrollment data
            logger.info(f"Fetching enrollment data for {len(parsed_data)} sections")
            enrollment = await self.fetch_enrollment(term=term, crns=list(parsed_data.keys()))
            
            # Process all courses
            out = []
            for course, crns in courses.items():
                sections = self.process_course(term, course, crns, parsed_data, enrollment)
                out.extend(sections)
            
            logger.info(f"Processed {len(out)} sections for term {self.parse_term(term)}")
            return out
            
        except Exception as e:
            logger.error(f"Error processing term {term}: {e}")
            return []