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
JOB_RESPONSE=$(curl -s -X POST "$BASE_URL/schedule_spec/optimize" \
    -F "schedule_spec_file=@$TEST_DIR/01_1nurse_1shift_1day.yaml" \
    -w "\nHTTP Status: %{http_code}\n")
echo "$JOB_RESPONSE"
echo ""

echo "--------------------------------"
echo "YAML content as string"
YAML_CONTENT=$(cat "$TEST_DIR/01_1nurse_1shift_1day.yaml")
JOB_RESPONSE=$(curl -s -X POST "$BASE_URL/schedule_spec/optimize" \
    -F "schedule_spec_yaml=$YAML_CONTENT" \
    -w "\nHTTP Status: %{http_code}\n")
echo "$JOB_RESPONSE"
echo ""
