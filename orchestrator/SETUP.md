# Orchestrator Setup Guide

## Prerequisites

### 1. Google Cloud CLI (Required for Vertex AI Authentication)

The orchestrator uses **Application Default Credentials (ADC)** from the Google Cloud CLI to authenticate with Vertex AI. You must install it first.

**Installation:**

- **Windows (using PowerShell):**
  ```powershell
  # Using Google's official installer
  (New-Object Net.WebClient).DownloadFile('https://dl.google.com/dl/cloudsdk/channels/rapid/GoogleCloudSDKInstaller.exe', "$env:Temp\GoogleCloudSDKInstaller.exe")
  & "$env:Temp\GoogleCloudSDKInstaller.exe"
  ```
  Or download from: https://cloud.google.com/sdk/docs/install-sdk#windows

- **macOS:**
  ```bash
  curl https://sdk.cloud.google.com | bash
  exec -l $SHELL
  ```

- **Linux:**
  ```bash
  curl https://sdk.cloud.google.com | bash
  exec -l $SHELL
  ```

### 2. Authenticate with Google Cloud

After installing the Google Cloud CLI, authenticate to get Application Default Credentials:

```bash
gcloud auth application-default login
```

This will open a browser window to sign in with your Google account. ADC will be saved locally and automatically used by Vertex AI.

### 3. Set Environment Variables

Update `.env` with your Vertex AI project settings:

```env
# Vertex AI Configuration (uses Application Default Credentials from gcloud CLI)
VERTEX_AI_PROJECT_ID=your-project-id-here
VERTEX_AI_LOCATION=us-central1
```

## How It Works

1. **No JSON Service Key Needed**: Instead of downloading a service account key JSON file, the orchestrator uses your local `gcloud` authentication
2. **Automatic Provider Selection**:
   - If `VERTEX_AI_PROJECT_ID` is set → Uses **Vertex AI** (via gcloud CLI)
   - If not set → Falls back to **Gemini API** (via `GEMINI_API_KEY`)
3. **Cached Client**: The Vertex AI client is cached for performance

## Installation

```bash
pip install -r requirements.txt
```

### Key Dependencies for Vertex AI

- `google-cloud-aiplatform>=1.72.0` – Vertex AI Python SDK
- `google-auth>=2.0.0` – Authentication library (uses ADC from gcloud)

## Running the Orchestrator

```bash
python main.py
```

## Troubleshooting

### "Vertex AI init failed" or "Project not found"
- Verify `VERTEX_AI_PROJECT_ID` is correct in `.env`
- Run `gcloud auth application-default login` again
- Check: `gcloud config get-value project`

### "gcloud: command not found"
- Google Cloud CLI is not installed or not in PATH
- Restart your terminal after installing gcloud
- Check installation: `gcloud --version`

### "Permission denied" or "403 Forbidden"
- Your Google account doesn't have access to the Vertex AI project
- Contact your GCP project administrator to add the necessary IAM roles

## Next Steps

1. Ensure Google Cloud CLI is installed
2. Run `gcloud auth application-default login`
3. Update `.env` with your Vertex AI project ID
4. Run `pip install -r requirements.txt`
5. Start the orchestrator with `python main.py`
