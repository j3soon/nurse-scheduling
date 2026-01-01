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

# Pytest tests for nurse scheduling FastAPI server.
# Based on the FastAPI Testing guide: https://fastapi.tiangolo.com/tutorial/testing/

import os
import sys
# Add the project root to the Python path so imports will work when running directly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from nurse_scheduling.serve import app

# Test client
client = TestClient(app)

# Test directories
TEST_DIR = Path(__file__).parent / "testcases" / "basics"
VALID_YAML_FILE = TEST_DIR / "01_1nurse_1shift_1day.yaml"
ERROR_YAML_FILE = TEST_DIR / "01_1nurse_1shift_1day_extra_parameter_error.txt"


class TestServerHealth:
    """Test server health and basic endpoints."""
    
    def test_server_root(self):
        """Check if server is running and returns correct response."""
        response = client.get("/")
        assert response.status_code == 200
        json_data = response.json()
        assert "message" in json_data
        assert "version" in json_data
        assert json_data["message"] == "Nurse Scheduling API"
        assert json_data["version"] == "alpha"


class TestValidRequests:
    """Test valid optimization requests."""
    
    def test_valid_yaml_file_upload(self):
        """Valid YAML file upload."""
        with open(VALID_YAML_FILE, "rb") as f:
            response = client.post(
                "/optimize-and-export-xlsx",
                files={"file": ("01_1nurse_1shift_1day.yaml", f, "application/x-yaml")}
            )
        
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        assert "Content-Disposition" in response.headers
        assert "attachment; filename=01_1nurse_1shift_1day.xlsx" in response.headers["Content-Disposition"]
        
        # Check custom headers
        assert "X-Schedule-Score" in response.headers
        assert response.headers["X-Schedule-Score"] == "0"
        assert "X-Schedule-Status" in response.headers
        assert response.headers["X-Schedule-Status"] == "OPTIMAL"

        # Verify XLSX content is not empty
        assert len(response.content) > 0
    
    def test_yaml_content_as_string(self):
        """YAML content as string."""
        with open(VALID_YAML_FILE, "r") as f:
            yaml_content = f.read()
        
        response = client.post(
            "/optimize-and-export-xlsx",
            data={"yaml_content": yaml_content}
        )
        
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        assert "Content-Disposition" in response.headers
        assert "attachment; filename=nurse-scheduling-" in response.headers["Content-Disposition"]
        
        # Check custom headers
        assert "X-Schedule-Score" in response.headers
        assert response.headers["X-Schedule-Score"] == "0"
        assert "X-Schedule-Status" in response.headers
        assert response.headers["X-Schedule-Status"] == "OPTIMAL"
        
        # Verify XLSX content is not empty
        assert len(response.content) > 0
    
    def test_valid_yaml_with_optional_parameters(self):
        """Valid YAML with optional parameters (prettify=true, timeout=60)."""
        with open(VALID_YAML_FILE, "rb") as f:
            response = client.post(
                "/optimize-and-export-xlsx",
                files={"file": ("01_1nurse_1shift_1day.yaml", f, "application/x-yaml")},
                data={"prettify": "true", "timeout": "60"}
            )
        
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        assert "Content-Disposition" in response.headers
        assert "attachment; filename=01_1nurse_1shift_1day.xlsx" in response.headers["Content-Disposition"]
        
        # Check custom headers
        assert "X-Schedule-Score" in response.headers
        assert response.headers["X-Schedule-Score"] == "0"
        assert "X-Schedule-Status" in response.headers
        assert response.headers["X-Schedule-Status"] == "OPTIMAL"
        
        # Verify XLSX content is not empty
        assert len(response.content) > 0


class TestErrorCases:
    """Test error cases and validation."""
    
    def test_both_file_and_yaml_content_provided(self):
        """Error case - both file and yaml_content provided."""
        with open(VALID_YAML_FILE, "rb") as f:
            yaml_content = f.read().decode('utf-8')
            f.seek(0)  # Reset file pointer
            
            response = client.post(
                "/optimize-and-export-xlsx",
                files={"file": ("01_1nurse_1shift_1day.yaml", f, "application/x-yaml")},
                data={"yaml_content": yaml_content}
            )
        
        assert response.status_code == 400
        assert "detail" in response.json()
        assert "not both" in response.json()["detail"].lower()
    
    def test_neither_file_nor_yaml_content_provided(self):
        """Error case - neither file nor yaml_content provided."""
        response = client.post("/optimize-and-export-xlsx")
        
        assert response.status_code == 400
        assert "detail" in response.json()
        assert "must be provided" in response.json()["detail"].lower()
    
    def test_invalid_file_type(self):
        """Error case - invalid file type."""
        with open(ERROR_YAML_FILE, "rb") as f:
            response = client.post(
                "/optimize-and-export-xlsx",
                files={"file": ("01_1nurse_1shift_1day_extra_parameter_error.txt", f, "text/plain")}
            )
        
        assert response.status_code == 400
        assert "detail" in response.json()
        assert "invalid file type" in response.json()["detail"].lower()
    
    def test_yaml_with_extra_parameters(self):
        """Error case - YAML with extra parameters."""
        with open(ERROR_YAML_FILE, "r") as f:
            error_yaml_content = f.read()
        
        response = client.post(
            "/optimize-and-export-xlsx",
            data={"yaml_content": error_yaml_content}
        )
        
        assert response.status_code == 500
        assert "detail" in response.json()
        assert "error" in response.json()["detail"].lower()


class TestMultipleValidScenarios:
    """Test multiple valid YAML scenarios to ensure robustness."""
    
    @pytest.mark.parametrize("yaml_file", [
        "01_1nurse_1shift_1day.yaml",
        "02_3nurses_1shift_1day.yaml",
        "02_4nurses_3shifts_3days.yaml",
        "03_4nurses_3shifts_7days.yaml",
    ])
    def test_various_valid_yaml_files(self, yaml_file):
        """Test various valid YAML files to ensure they all work."""
        yaml_path = TEST_DIR / yaml_file
        
        if not yaml_path.exists():
            pytest.skip(f"Test file {yaml_file} not found")
        
        with open(yaml_path, "rb") as f:
            response = client.post(
                "/optimize-and-export-xlsx",
                files={"file": (yaml_file, f, "application/x-yaml")}
            )
        
        # Should return 200 or handle gracefully
        assert response.status_code == 200
        
        if response.status_code == 200:
            assert response.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            assert len(response.content) > 0


class TestEdgeCases:
    """Test edge cases and boundary conditions."""
    
    def test_empty_yaml_content(self):
        """Test with empty YAML content."""
        response = client.post(
            "/optimize-and-export-xlsx",
            data={"yaml_content": ""}
        )
        
        # Should return an error for empty content
        assert response.status_code == 400
    
    def test_invalid_yaml_syntax(self):
        """Test with invalid YAML syntax."""
        invalid_yaml = "this is not: valid: yaml: syntax:"
        
        response = client.post(
            "/optimize-and-export-xlsx",
            data={"yaml_content": invalid_yaml}
        )
        
        # Should return an error for invalid YAML
        assert response.status_code == 500
        assert "detail" in response.json()
    
    def test_timeout_parameter_values(self):
        """Test different timeout parameter values."""
        with open(VALID_YAML_FILE, "rb") as f:
            response = client.post(
                "/optimize-and-export-xlsx",
                files={"file": ("01_1nurse_1shift_1day.yaml", f, "application/x-yaml")},
                data={"timeout": "1"}  # Very short timeout
            )
        
        # Should either succeed quickly or handle timeout gracefully
        assert response.status_code == 200
    
    def test_prettify_parameter_false(self):
        """Test prettify parameter set to false."""
        with open(VALID_YAML_FILE, "rb") as f:
            response = client.post(
                "/optimize-and-export-xlsx",
                files={"file": ("01_1nurse_1shift_1day.yaml", f, "application/x-yaml")},
                data={"prettify": "false"}
            )
        
        assert response.status_code == 200
        assert len(response.content) > 0


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "--log-cli-level=INFO"])
