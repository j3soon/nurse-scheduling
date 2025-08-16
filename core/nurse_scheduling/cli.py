import sys
import argparse
import logging
import os.path
from . import scheduler

# TODO: Better CLI
# Ref: https://packaging.python.org/en/latest/guides/creating-command-line-tools/

def main():
    parser = argparse.ArgumentParser(description='Nurse Scheduling Tool')
    parser.add_argument('input_file_path', help='Path to the input file')
    parser.add_argument('output_path', nargs='?', help='Path to save the output file (optional)')
    parser.add_argument('--verbose', action='store_true', 
                       help='Enable verbose output (debug logging)')
    
    args = parser.parse_args()
    filepath = args.input_file_path
    output_path = args.output_path
    verbose = args.verbose
    
    if verbose:
        logging.basicConfig(level=logging.DEBUG)
    
    # Infer output format and prettify from file extension
    output_format = None
    prettify = False  # default prettify (for csv)
    if output_path:
        file_ext = os.path.splitext(output_path)[1].lower()
        if file_ext == '.xlsx':
            output_format = 'xlsx'
            prettify = True  # prettify for xlsx files
        elif file_ext == '.csv':
            output_format = 'csv'
            prettify = False  # no prettify for csv files
        elif file_ext and file_ext not in ['.csv', '.xlsx']:
            print(f"Error: Unsupported output file extension '{file_ext}'. Supported formats: .csv, .xlsx")
            sys.exit(1)
    
    df, solution, score, status = scheduler.schedule(filepath, prettify=prettify)

    if df is None:
        print("No solution found")
        sys.exit(0)
    
    if output_path:
        # Save DataFrame in the specified format
        if output_format == 'xlsx':
            df.to_excel(output_path, index=False, header=False)
        else:  # csv format
            # Save DataFrame to CSV with UTF-8 BOM for Excel compatibility
            df.to_csv(output_path, index=False, header=False, encoding='utf-8-sig')
        print(f"Results saved to {output_path}")
        print(f"Score: {score}")
        print(f"Status: {status}")
    else:
        print(df, solution, score, status)

if __name__ == "__main__":
    main()
