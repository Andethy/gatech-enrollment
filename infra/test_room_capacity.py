#!/usr/bin/env python3
"""
Test script to verify room capacity and loss calculation functionality.
This script directly tests the data processing logic without going through the API.
"""

import sys
import os
import json
import boto3
from datetime import datetime

# Add lambda directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'lambda', 'data-processing'))

from data_processor import DataProcessor

def test_room_capacity_functionality():
    """Test the room capacity matching and loss calculation."""
    
    print("🧪 Testing Room Capacity and Loss Calculation")
    print("=" * 50)
    
    # Initialize the data processor
    bucket_name = "gatech-enrollment-dev-536580887192"
    processor = DataProcessor(bucket_name)
    
    print(f"📦 Using S3 bucket: {bucket_name}")
    
    # Test capacity data loading
    print("\n1. Testing capacity data loading...")
    try:
        processor.ensure_capacity_data_loaded()
        
        if processor.room_capacity_data is not None:
            print(f"✅ Room capacity data loaded: {len(processor.room_capacity_data)} records")
            print("Sample capacity data:")
            print(processor.room_capacity_data.head())
        else:
            print("❌ Room capacity data not loaded")
            return False
            
        if processor.building_mappings is not None:
            print(f"✅ Building mappings loaded: {len(processor.building_mappings)} records")
            print("Sample building mappings:")
            print(processor.building_mappings.head())
        else:
            print("❌ Building mappings not loaded")
            return False
            
    except Exception as e:
        print(f"❌ Error loading capacity data: {e}")
        return False
    
    # Create sample enrollment data for testing
    print("\n2. Creating sample enrollment data...")
    import pandas as pd
    
    sample_data = [
        {
            "CRN": "12345",
            "Term": "Fall 2024",
            "Subject": "CS",
            "Course": "1331",
            "Building": "Skiles",
            "Room": "235",
            "Enrollment Actual": 25,
            "Enrollment Maximum": 30
        },
        {
            "CRN": "12346", 
            "Term": "Fall 2024",
            "Subject": "CS",
            "Course": "1332",
            "Building": "Boggs",
            "Room": "B5",
            "Enrollment Actual": 120,
            "Enrollment Maximum": 150
        },
        {
            "CRN": "12347",
            "Term": "Fall 2024", 
            "Subject": "MATH",
            "Course": "1554",
            "Building": "Unknown Building",
            "Room": "999",
            "Enrollment Actual": 50,
            "Enrollment Maximum": 60
        }
    ]
    
    df = pd.DataFrame(sample_data)
    print(f"✅ Created sample data with {len(df)} records")
    print("Sample enrollment data:")
    print(df[["CRN", "Building", "Room", "Enrollment Actual"]])
    
    # Test room data appending
    print("\n3. Testing room data appending...")
    try:
        result_df = processor.append_room_data(df)
        
        print(f"✅ Room data appended successfully")
        print("Result columns:", list(result_df.columns))
        
        # Check if Building Code and Room Capacity columns were added
        if "Building Code" in result_df.columns and "Room Capacity" in result_df.columns:
            print("✅ Building Code and Room Capacity columns added")
            
            # Show results
            print("\nResults:")
            display_cols = ["CRN", "Building", "Building Code", "Room", "Room Capacity", "Enrollment Actual"]
            available_cols = [col for col in display_cols if col in result_df.columns]
            print(result_df[available_cols])
            
            # Check for successful matches
            matched_count = result_df["Room Capacity"].notna().sum()
            total_count = len(result_df)
            print(f"\n📊 Room capacity matches: {matched_count}/{total_count}")
            
            if matched_count > 0:
                print("✅ Some room capacities were successfully matched!")
                
                # Test loss calculation
                print("\n4. Testing loss calculation...")
                try:
                    result_df["Loss"] = processor._calculate_loss(result_df)
                    
                    if "Loss" in result_df.columns:
                        print("✅ Loss calculation completed")
                        
                        # Show final results
                        final_cols = ["CRN", "Building", "Room", "Room Capacity", "Enrollment Actual", "Loss"]
                        available_final_cols = [col for col in final_cols if col in result_df.columns]
                        print("\nFinal results with loss calculation:")
                        print(result_df[available_final_cols])
                        
                        # Validate loss calculations
                        valid_loss_count = result_df["Loss"].notna().sum()
                        print(f"\n📊 Valid loss calculations: {valid_loss_count}/{total_count}")
                        
                        if valid_loss_count > 0:
                            print("✅ Loss calculations completed successfully!")
                            return True
                        else:
                            print("⚠️  No valid loss calculations (expected if no room capacity matches)")
                            return matched_count == 0  # OK if no matches, not OK if matches but no loss calc
                    else:
                        print("❌ Loss column not added")
                        return False
                        
                except Exception as e:
                    print(f"❌ Error calculating loss: {e}")
                    return False
            else:
                print("⚠️  No room capacity matches found")
                print("This could be due to:")
                print("- Building names not matching between GT Scheduler and building mappings")
                print("- Room numbers not matching between enrollment data and capacity data")
                print("- Issues with the matching algorithm")
                return False
        else:
            print("❌ Building Code or Room Capacity columns not added")
            return False
            
    except Exception as e:
        print(f"❌ Error appending room data: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Main test function."""
    print("🚀 Starting Room Capacity Test")
    print(f"⏰ Test started at: {datetime.now()}")
    
    try:
        success = test_room_capacity_functionality()
        
        if success:
            print("\n🎉 All tests passed! Room capacity and loss calculation are working correctly.")
            return 0
        else:
            print("\n❌ Tests failed. Room capacity functionality needs debugging.")
            return 1
            
    except Exception as e:
        print(f"\n💥 Test script failed with error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)