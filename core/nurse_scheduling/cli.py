import sys
import argparse
from . import scheduler

# TODO: Better CLI
# Ref: https://packaging.python.org/en/latest/guides/creating-command-line-tools/

def main():
    parser = argparse.ArgumentParser(description='Nurse Scheduling Tool')
    parser.add_argument('input_file_path', help='Path to the input file')
    parser.add_argument('output_csv_path', nargs='?', help='Path to save the output CSV file (optional)')
    parser.add_argument('--prettify', action='store_true', 
                       help='Add extra columns and rows with counts (OFF counts per person, shift type counts per date)')
    
    args = parser.parse_args()
    filepath = args.input_file_path
    output_path = args.output_csv_path
    prettify = args.prettify
    
    df, solution, score, status = scheduler.schedule(filepath, prettify=prettify)

    if df is None:
        print("No solution found")
        sys.exit(0)
    
    if output_path:
        # Save DataFrame to CSV with UTF-8 BOM for Excel compatibility
        df.to_csv(output_path, index=False, header=False, encoding='utf-8-sig')
        print(f"Results saved to {output_path}")
        print(f"Score: {score}")
        print(f"Status: {status}")
    else:
        print(df, solution, score, status)

if __name__ == "__main__":
    main()
