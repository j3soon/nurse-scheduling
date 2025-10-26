#!/bin/bash
# Test script for nurse scheduling FastAPI server
# Make sure the server is running first: fastapi dev core/nurse_scheduling/serve.py

set -e

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd)"

BASE_URL="http://localhost:8000"
TEST_DIR="$SCRIPT_DIR/testcases/basics"
OUTPUT_DIR="$SCRIPT_DIR/test_serve_output"

# Create output directory
mkdir -p "$OUTPUT_DIR"

echo "Check if server is running"
curl "$BASE_URL/"
echo ""
echo ""

echo "--------------------------------"
echo "Valid YAML file upload"
curl -X POST "$BASE_URL/optimize-and-export-xlsx" \
    -F "file=@$TEST_DIR/01_1nurse_1shift_1day.yaml" \
    -o "$OUTPUT_DIR/01_1nurse_1shift_1day.xlsx" \
    -w "\nHTTP Status: %{http_code}\n" \
    -D "$OUTPUT_DIR/headers_test2.txt"
echo ""

echo "--------------------------------"
echo "YAML content as string"
YAML_CONTENT=$(cat "$TEST_DIR/01_1nurse_1shift_1day.yaml")
curl -X POST "$BASE_URL/optimize-and-export-xlsx" \
    -F "yaml_content=$YAML_CONTENT" \
    -o "$OUTPUT_DIR/01_1nurse_1shift_1day_from_string.xlsx" \
    -w "\nHTTP Status: %{http_code}\n"
echo ""
