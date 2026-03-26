#!/usr/bin/env python3
"""
Verify Vertex AI setup for the orchestrator.
Run this after installing dependencies to ensure everything is configured correctly.
"""

import os
import sys
import subprocess
from pathlib import Path


def check_gcloud_installed():
    """Check if gcloud CLI is installed"""
    try:
        result = subprocess.run(["gcloud", "--version"], capture_output=True, text=True)
        if result.returncode == 0:
            print("✓ Google Cloud CLI is installed")
            print(f"  {result.stdout.split(chr(10))[0]}")
            return True
    except FileNotFoundError:
        pass
    
    print("✗ Google Cloud CLI is NOT installed")
    print("  Install from: https://cloud.google.com/sdk/docs/install")
    print("  After installation, run: gcloud auth application-default login")
    return False


def check_adc_credentials():
    """Check if Application Default Credentials are configured"""
    adc_path = Path.home() / ".config" / "gcloud" / "application_default_credentials.json"
    if sys.platform == "win32":
        adc_path = Path.home() / "AppData" / "Roaming" / "gcloud" / "application_default_credentials.json"
    
    if adc_path.exists():
        print("✓ Application Default Credentials (ADC) are configured")
        return True
    else:
        print("✗ Application Default Credentials NOT found")
        print(f"  Expected at: {adc_path}")
        print("  Run: gcloud auth application-default login")
        return False


def check_env_variables():
    """Check if required environment variables are set"""
    from dotenv import load_dotenv
    
    load_dotenv()
    
    project_id = os.getenv("VERTEX_AI_PROJECT_ID")
    location = os.getenv("VERTEX_AI_LOCATION", "us-central1")
    
    if project_id:
        print("✓ VERTEX_AI_PROJECT_ID is set")
        print(f"  Project: {project_id}")
        print(f"  Location: {location}")
        return True
    else:
        print("✗ VERTEX_AI_PROJECT_ID is NOT set in .env")
        print("  Add to .env: VERTEX_AI_PROJECT_ID=your-project-id")
        return False


def check_python_packages():
    """Check if required Python packages are installed"""
    try:
        import vertexai
        print("✓ google-cloud-aiplatform is installed")
    except ImportError:
        print("✗ google-cloud-aiplatform is NOT installed")
        print("  Run: pip install -r requirements.txt")
        return False
    
    try:
        import google.auth
        print("✓ google-auth is installed")
    except ImportError:
        print("✗ google-auth is NOT installed")
        print("  Run: pip install -r requirements.txt")
        return False
    
    return True


def main():
    print("=" * 60)
    print("Vertex AI Orchestrator Setup Verification")
    print("=" * 60)
    print()
    
    checks = [
        ("Google Cloud CLI", check_gcloud_installed),
        ("Application Default Credentials (ADC)", check_adc_credentials),
        ("Environment Variables", check_env_variables),
        ("Python Packages", check_python_packages),
    ]
    
    results = []
    for name, check_fn in checks:
        print(f"\n{name}:")
        try:
            result = check_fn()
            results.append((name, result))
        except Exception as e:
            print(f"✗ Error checking {name}: {e}")
            results.append((name, False))
    
    print("\n" + "=" * 60)
    print("Summary:")
    print("=" * 60)
    
    all_pass = all(result for _, result in results)
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {name}")
    
    print()
    if all_pass:
        print("✓ All checks passed! Your setup is ready.")
        return 0
    else:
        print("✗ Some checks failed. See errors above for fixes.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
