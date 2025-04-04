import os
import tempfile
import shutil
import uuid
import json
import pickle
from fastapi import FastAPI, UploadFile, File, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
from typing import Dict, Any, Optional

from app import ResumeParsingBot

# Create data directory if it doesn't exist
DATA_DIR = "data_storage"
RESUME_DATA_FILE = os.path.join(DATA_DIR, "resume_sessions.pickle")
JD_DATA_FILE = os.path.join(DATA_DIR, "jd_sessions.pickle")
ANALYSIS_DATA_FILE = os.path.join(DATA_DIR, "analysis_sessions.pickle")

os.makedirs(DATA_DIR, exist_ok=True)

# Create FastAPI app
app = FastAPI(title="Resume Parser API", description="API for parsing resumes and job descriptions")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create dictionaries to temporarily store data
# Load from storage if available
try:
    with open(RESUME_DATA_FILE, 'rb') as f:
        resume_sessions = pickle.load(f)
    print(f"Loaded {len(resume_sessions)} resume sessions from storage")
except (FileNotFoundError, EOFError):
    resume_sessions = {}
    print("No resume sessions found, starting fresh")

try:
    with open(JD_DATA_FILE, 'rb') as f:
        jd_sessions = pickle.load(f)
    print(f"Loaded {len(jd_sessions)} JD sessions from storage")
except (FileNotFoundError, EOFError):
    jd_sessions = {}
    print("No JD sessions found, starting fresh")

try:
    with open(ANALYSIS_DATA_FILE, 'rb') as f:
        analysis_sessions = pickle.load(f)
    print(f"Loaded {len(analysis_sessions)} analysis sessions from storage")
except (FileNotFoundError, EOFError):
    analysis_sessions = {}
    print("No analysis sessions found, starting fresh")

# Function to save session data
def save_sessions():
    with open(RESUME_DATA_FILE, 'wb') as f:
        pickle.dump(resume_sessions, f)
    
    with open(JD_DATA_FILE, 'wb') as f:
        pickle.dump(jd_sessions, f)
    
    with open(ANALYSIS_DATA_FILE, 'wb') as f:
        pickle.dump(analysis_sessions, f)
    
    print("Session data saved to disk")

# Response Models
class StatusResponse(BaseModel):
    status: str
    message: str

class Query(BaseModel):
    query: str
    resume_id: str
    jd_id: Optional[str] = None

class JobDescription(BaseModel):
    jd: str
    
class MatchRequest(BaseModel):
    resume_id: str
    jd_id: str

class ClearSessionRequest(BaseModel):
    resume_id: str
    jd_id: str

@app.post("/upload-resume/", response_model=Dict[str, Any])
async def upload_resume(resume_file: UploadFile = File(...)):
    """Upload and process a resume file (PDF or DOCX)"""
    # Check file extension
    file_extension = os.path.splitext(resume_file.filename)[1].lower()
    if file_extension not in ['.pdf', '.docx', '.txt']:
        raise HTTPException(status_code=400, detail="Invalid file format. Please upload a PDF, DOCX, or TXT file.")
    
    # Create a temporary file
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=file_extension)
    
    try:
        # Write the uploaded file to the temporary file
        shutil.copyfileobj(resume_file.file, temp_file)
        temp_file.close()
        
        # Process the resume
        bot = ResumeParsingBot()
        result = bot.process_resume(temp_file.name)
        
        # Generate a unique ID for this resume
        resume_id = str(uuid.uuid4())
        
        # Store the result in the sessions dictionary
        if result["status"] == "success":
            # Add the ID to the resume data
            result["resume_data"]["id"] = resume_id
            resume_sessions[resume_id] = result["resume_data"]
            
            # Save to disk
            save_sessions()
            
            # Add the ID to the result
            result["resume_id"] = resume_id
        
        # Return the processing result
        return result
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing resume: {str(e)}")
    
    finally:
        # Clean up the temporary file
        if os.path.exists(temp_file.name):
            os.unlink(temp_file.name)

@app.post("/upload-jd/", response_model=Dict[str, Any])
async def upload_jd(jd_data: JobDescription):
    """Process a job description provided as text"""
    try:
        # Create a temporary file to store the job description text
        with tempfile.NamedTemporaryFile(delete=False, suffix='.txt', mode='w', encoding='utf-8') as temp_file:
            temp_file.write(jd_data.jd)
            temp_file_path = temp_file.name
        
        # Process the job description
        bot = ResumeParsingBot()
        result = bot.process_job_description(temp_file_path)
        
        # Generate a unique ID for this job description
        jd_id = str(uuid.uuid4())
        
        # Store the result in the sessions dictionary
        if result["status"] == "success":
            # Add the ID to the JD data
            result["jd_data"]["id"] = jd_id
            jd_sessions[jd_id] = result["jd_data"]
            
            # Save to disk
            save_sessions()
            
            # Add the ID to the result
            result["jd_id"] = jd_id
        
        # Return the processing result
        return result
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing job description: {str(e)}")
    
    finally:
        # Clean up the temporary file
        if os.path.exists(temp_file_path):
            os.unlink(temp_file_path)

@app.post("/analyze-match/", response_model=Dict[str, Any])
async def analyze_match(match_request: MatchRequest):
    """Analyze how well the resume matches the job description"""
    # Check if both resume and JD data are available
    resume_id = match_request.resume_id
    jd_id = match_request.jd_id
    
    if resume_id not in resume_sessions:
        raise HTTPException(status_code=404, detail=f"Resume with ID {resume_id} not found")
    
    if jd_id not in jd_sessions:
        raise HTTPException(status_code=404, detail=f"Job description with ID {jd_id} not found")
    
    # Create a unique key for this analysis
    analysis_key = f"{resume_id}_{jd_id}"
    
    try:
        # Analyze the match
        bot = ResumeParsingBot()
        result = bot.analyze_match(resume_sessions[resume_id], jd_sessions[jd_id])
        
        # Store the analysis result
        if result["status"] == "success":
            # We don't need to add IDs inside the match_analysis object since they're already at the root level
            analysis_sessions[analysis_key] = result["match_analysis"]
            
            # Save to disk
            save_sessions()
        
        # Add IDs to the result at root level only
        result["resume_id"] = resume_id
        result["jd_id"] = jd_id
        
        return result
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error analyzing match: {str(e)}")

@app.post("/chat/", response_model=Dict[str, Any])
async def chat(query: Query):
    """Chat with the AI about the resume and job description"""
    resume_id = query.resume_id
    jd_id = query.jd_id
    
    # Check if resume data is available
    if resume_id not in resume_sessions:
        raise HTTPException(status_code=404, detail=f"Resume with ID {resume_id} not found")
    
    # Get JD data if an ID was provided
    jd_data = None
    if jd_id and jd_id in jd_sessions:
        jd_data = jd_sessions[jd_id]
    
    # Get analysis data if available
    analysis_data = None
    if jd_id:
        analysis_key = f"{resume_id}_{jd_id}"
        if analysis_key in analysis_sessions:
            analysis_data = analysis_sessions[analysis_key]
    
    try:
        # Process the chat message
        bot = ResumeParsingBot()
        result = bot.chat_message(
            resume_sessions[resume_id],
            jd_data,
            analysis_data,
            query.query
        )
        
        # If the resume data was updated (status change), update the session
        if result.get("updated_resume_data"):
            resume_sessions[resume_id] = result["updated_resume_data"]
            # Save to disk
            save_sessions()
        
        # Add IDs to the result
        result["resume_id"] = resume_id
        if jd_id:
            result["jd_id"] = jd_id
        
        return result
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing chat: {str(e)}")

@app.post("/clear-specific-session/", response_model=StatusResponse)
async def clear_specific_session(clear_request: ClearSessionRequest):
    """Clear a specific resume-JD session combination"""
    resume_id = clear_request.resume_id
    jd_id = clear_request.jd_id
    
    # Check if IDs exist
    resume_exists = resume_id in resume_sessions
    jd_exists = jd_id in jd_sessions
    
    if not resume_exists and not jd_exists:
        return {"status": "error", "message": f"Neither resume ID {resume_id} nor JD ID {jd_id} found"}
    
    # Create the analysis key
    analysis_key = f"{resume_id}_{jd_id}"
    analysis_exists = analysis_key in analysis_sessions
    
    # Delete the analysis data if it exists
    if analysis_exists:
        del analysis_sessions[analysis_key]
    
    # Save changes to disk
    save_sessions()
    
    return {
        "status": "success", 
        "message": f"Session for resume ID {resume_id} and JD ID {jd_id} cleared successfully",
        "details": {
            "resume_found": resume_exists,
            "jd_found": jd_exists,
            "analysis_found_and_deleted": analysis_exists
        }
    }

@app.get("/list-resumes/", response_model=Dict[str, Any])
async def list_resumes():
    """List all available resume IDs with names"""
    resume_list = []
    for resume_id, resume_data in resume_sessions.items():
        resume_list.append({
            "id": resume_id,
            "name": resume_data.get("name") or resume_data.get("fullName", "Unknown"),
            "upload_date": resume_data.get("upload_date", "Unknown")
        })
    
    return {
        "status": "success",
        "resumes": resume_list
    }

@app.get("/list-jds/", response_model=Dict[str, Any])
async def list_jds():
    """List all available job description IDs with titles"""
    jd_list = []
    for jd_id, jd_data in jd_sessions.items():
        jd_list.append({
            "id": jd_id,
            "title": jd_data.get("job_title", "Unknown"),
            "upload_date": jd_data.get("upload_date", "Unknown")
        })
    
    return {
        "status": "success",
        "job_descriptions": jd_list
    }

def dev():
    """Run the server in development mode"""
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

def prod():
    """Run the server in production mode"""
    uvicorn.run("main:app", host="0.0.0.0", port=8000)

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "dev":
        dev()
    else:
        prod() 