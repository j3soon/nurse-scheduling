"""
This file is part of Nurse Scheduling Project, see <https://github.com/j3soon/nurse-scheduling>.

Copyright (C) 2023-2026 Johnson Sun

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as
published by the Free Software Foundation, either version 3 of the
License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

import sys
import argparse
import logging
import os.path
from io import BytesIO
from . import scheduler, exporter

# TODO: Better CLI
# Ref: https://packaging.python.org/en/latest/guides/creating-command-line-tools/

def main():
    parser = argparse.ArgumentParser(description='Nurse Scheduling Tool')
    parser.add_argument('input_file_path', help='Path to the input file')
    parser.add_argument('output_path', nargs='?', help='Path to save the output file (optional)')
    parser.add_argument('--prettify', action='store_true',
                       help='Enable prettify mode for enhanced output formatting')
    parser.add_argument('-v', '--verbose', action='count', default=0,
                       help='Increase verbosity (can be used multiple times: -v, -vv, -vvv)')
    parser.add_argument('--timeout', type=int, default=None,
                       help='Maximum running time in seconds. If reached, the solver will stop and the current best result (if any) will be exported.')
    
    args = parser.parse_args()
    filepath = args.input_file_path
    output_path = args.output_path
    prettify = args.prettify
    verbose = args.verbose
    
    # Configure logging based on verbosity level
    if verbose >= 2:
        logging.basicConfig(level=logging.DEBUG, format='%(levelname)s: %(message)s')
    elif verbose == 1:
        logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    else:
        logging.basicConfig(level=logging.WARNING, format='%(levelname)s: %(message)s')
    
    # Infer output format from file extension
    output_format = None
    if output_path:
        file_ext = os.path.splitext(output_path)[1].lower()
        if file_ext == '.xlsx':
            output_format = 'xlsx'
        elif file_ext == '.csv':
            if prettify:
                print("Error: Prettify mode is not supported for CSV files")
                sys.exit(1)
            output_format = 'csv'
        elif file_ext and file_ext not in ['.csv', '.xlsx']:
            print(f"Error: Unsupported output file extension '{file_ext}'. Supported formats: .csv, .xlsx")
            sys.exit(1)
    
    # Read input file
    if not os.path.isfile(filepath):
        print(f"Error: File '{filepath}' not found")
        sys.exit(1)
    
    with open(filepath, 'rb') as f:
        file_content = f.read()
    
    df, solution, score, status, cell_export_info = scheduler.schedule(file_content, prettify=prettify, timeout=args.timeout)

    if df is None:
        print("No solution found")
        sys.exit(0)
    
    if output_path:
        # Export to buffer and write to file
        buffer = BytesIO()
        if output_format == 'xlsx':
            exporter.export_to_excel(df, buffer, cell_export_info)
        else:  # csv format
            exporter.export_to_csv(df, buffer)
        
        # Write buffer to file
        with open(output_path, 'wb') as f:
            f.write(buffer.getvalue())
        
        print(f"Results saved to {output_path}")
        print(f"Score: {score}")
        print(f"Status: {status}")
    else:
        print(df, solution, score, status)

if __name__ == "__main__":
    main()
