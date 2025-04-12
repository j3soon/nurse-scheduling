import sys
from . import scheduler

# TODO: Better CLI
# Ref: https://packaging.python.org/en/latest/guides/creating-command-line-tools/

def main():
    if len(sys.argv) != 2:
        print("Usage: python -m nurse_scheduling.cli <input_file_path>")
        sys.exit(1)
    
    filepath = sys.argv[1]
    df, solution, score, status = scheduler.schedule(filepath)
    print(df)

if __name__ == "__main__":
    main()
