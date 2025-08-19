#!/usr/bin/env python3
"""
Test runner script with different test categories
"""
import sys
import subprocess
from pathlib import Path


def run_command(cmd):
    """Run a command and return success status"""
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    
    return result.returncode == 0


def main():
    """Main test runner"""
    if len(sys.argv) < 2:
        print("Usage: python run_tests.py <test_type>")
        print("Test types:")
        print("  unit       - Run unit tests only")
        print("  integration - Run integration tests only") 
        print("  all        - Run all tests")
        print("  coverage   - Run all tests with coverage report")
        print("  fast       - Run fast tests only (exclude slow)")
        sys.exit(1)
    
    test_type = sys.argv[1].lower()
    
    # Ensure we're in the project root
    if not Path("pytest.ini").exists():
        print("Error: Please run from the project root directory")
        sys.exit(1)
    
    base_cmd = ["python", "-m", "pytest"]
    
    if test_type == "unit":
        cmd = base_cmd + ["-m", "not integration", "-v"]
    elif test_type == "integration":
        cmd = base_cmd + ["-m", "integration", "-v"]
    elif test_type == "all":
        cmd = base_cmd + ["-v"]
    elif test_type == "coverage":
        cmd = base_cmd + ["--cov=src", "--cov-report=html", "--cov-report=term-missing", "-v"]
    elif test_type == "fast":
        cmd = base_cmd + ["-m", "not slow and not integration", "-v"]
    else:
        print(f"Unknown test type: {test_type}")
        sys.exit(1)
    
    print(f"Running {test_type} tests...")
    success = run_command(cmd)
    
    if success:
        print(f"\n✅ {test_type.title()} tests passed!")
        
        if test_type == "coverage":
            print("\n📊 Coverage report generated in htmlcov/index.html")
    else:
        print(f"\n❌ {test_type.title()} tests failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()