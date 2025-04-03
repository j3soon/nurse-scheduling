import os
import pandas as pd
from datetime import datetime

def parse_special_date_info(csv_file_path):
    df = pd.read_csv(csv_file_path, encoding='utf-8')
    df = df[df['備註'].notna()]
    special_date_info = list(zip(df['西元日期'], df['備註'], df['是否放假']==2))
    return special_date_info

def main():
    filename = "114年中華民國政府行政機關辦公日曆表.csv"
    # Get the directory of the current script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # Construct the path to the CSV file
    csv_file_path = os.path.join(script_dir, filename)
    # Parse the holiday calendar
    special_date_info = parse_special_date_info(csv_file_path)
    
    # Print the results
    print(f"Found {len(special_date_info)} special date entries:")
    for date, description, is_holiday in special_date_info:
        # Convert the date string to a datetime object
        print(f"('{datetime.strptime(str(date), '%Y%m%d').date()}', '{description}', {is_holiday}),")

if __name__ == "__main__":
    main()
