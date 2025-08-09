import sys
from . import scheduler

# TODO: Better CLI
# Ref: https://packaging.python.org/en/latest/guides/creating-command-line-tools/

def main():
    if len(sys.argv) < 2 or len(sys.argv) > 3:
        print("Usage: python -m nurse_scheduling.cli <input_file_path> [output_csv_path]")
        sys.exit(1)
    
    filepath = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) == 3 else None
    
    df, solution, score, status = scheduler.schedule(filepath)
    
    if output_path:
        # Save DataFrame to CSV
        df.to_csv(output_path, index=False, header=False)
        print(f"Results saved to {output_path}")
        print(f"Score: {score}")
        print(f"Status: {status}")
    else:
        print(df, solution, score, status)

if __name__ == "__main__":
    main()
