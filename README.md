# Resume Parser and Job Matching API

This application provides an API for processing resumes in PDF/DOCX format and job descriptions in text format. It uses GPT-4o to extract structured information and perform matching analysis, returning all results as JSON.

## Features

### Resume Processing
- Extract personal details (name, email, phone)
- Extract comprehensive skill set (technical and soft skills)
- Detailed company experience analysis
- Education details
- Stability assessment based on work history

### Job Description Analysis
- Extract job title and required skills
- Experience requirements and education requirements
- Company type and business model preferences

### Candidate-Job Matching
- Suggested role (Frontend, Backend, DevOps, etc.)
- Match score (1-10)
- AI shortlist recommendation
- Detailed company-by-company analysis
- Education assessment
- Gap analysis (skills or experience missing)

### Interactive Chat
- Ask questions about the candidate
- Update candidate status through natural language commands
- Status updates are reflected in JSON responses

## Setup

1. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
2. Create a `.env` file and add your OpenAI API key:
   ```
   OPENAI_API_KEY=your_api_key_here
   ```
3. Start the API server:
   ```
   python api.py
   ```
   The API will be available at `http://localhost:8000`

## API Documentation

Once the server is running, visit `http://localhost:8000/docs` for complete interactive API documentation.

### API Endpoints

#### POST /upload-resume/
Upload and process a resume file (PDF, DOCX, or TXT).

Request:
- Form data with `resume_file`

Response:
```json
{
  "resume_data": { ... },
  "usage": {
    "tokens": 1234,
    "cost": 0.01234
  },
  "status": "success"
}
```

#### POST /upload-jd/
Process a job description provided as text.

Request:
```json
{
  "jd": "We are looking for a Full Stack Developer with 5+ years of experience in building web applications using React, Node.js, and MongoDB..."
}
```

Response:
```json
{
  "jd_data": { ... },
  "usage": {
    "tokens": 1234,
    "cost": 0.01234
  },
  "status": "success"
}
```

#### POST /analyze-match/
Analyze how well the resume matches the job description.

Response:
```json
{
  "match_analysis": { ... },
  "usage": {
    "tokens": 1234,
    "cost": 0.01234
  },
  "status": "success"
}
```

#### POST /chat/
Chat with the AI about the resume and job description.

Request:
```json
{
  "query": "What are the candidate's strengths?"
}
```

Response:
```json
{
  "response": "The candidate has strong skills in...",
  "updated_resume_data": { ... },
  "usage": {
    "tokens": 1234,
    "cost": 0.01234
  },
  "status": "success"
}
```

#### POST /clear-session/
Clear the current session data.

Response:
```json
{
  "status": "success",
  "message": "Session cleared successfully"
}
```

#### GET /current-data/
Get all current session data.

Response:
```json
{
  "resume_data": { ... },
  "jd_data": { ... },
  "analysis_data": { ... }
}
```

## Example Client

An example client script is provided in `api_client_example.py`. Run it to see a complete workflow:

```
python api_client_example.py
```

## Using the API in Your Own Code

```python
import requests
import json

# Upload resume
with open('resume.pdf', 'rb') as f:
    files = {'resume_file': ('resume.pdf', f)}
    resume_response = requests.post('http://localhost:8000/upload-resume/', files=files)

# Process job description as text
jd_text = "We are looking for a Full Stack Developer with 5+ years of experience..."
jd_data = {'jd': jd_text}
jd_headers = {'Content-Type': 'application/json'}
jd_response = requests.post(
    'http://localhost:8000/upload-jd/',
    headers=jd_headers,
    data=json.dumps(jd_data)
)

# Analyze match
match_response = requests.post('http://localhost:8000/analyze-match/')

# Chat with AI
chat_data = {'query': 'What are the candidate\'s key strengths?'}
chat_headers = {'Content-Type': 'application/json'}
chat_response = requests.post(
    'http://localhost:8000/chat/',
    headers=chat_headers,
    data=json.dumps(chat_data)
)
```

## Important Notes

- The API uses in-memory session storage, so data is lost when the server restarts
- All uploaded files are processed and then immediately deleted
- No permanent storage is used for any data
- The API is designed for use with a frontend or other client application

## Supported File Formats

- Resumes: PDF, DOCX, TXT
- Job Descriptions: Plain text input

## Chat Commands for Status Updates

You can update candidate status through chat with commands like:

- "Shortlist John Doe internally"
- "Move John Doe (john@example.com) to interview process"
- "Mark candidate John Doe (1234567890) as selected"
- "Reject the candidate"
- "Candidate has joined the company"

The system will extract the candidate information and update their status accordingly. 