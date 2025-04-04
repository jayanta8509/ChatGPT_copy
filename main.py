import os
import tempfile
import shutil
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
from typing import Optional, List, Dict, Any
import json

from app import ResumeParsingBot

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

# Create a dictionary to temporarily store uploaded files
temp_files = {}
current_session = {
    "resume_data": None,
    "jd_data": None,
    "analysis_data": None
}

# Response Models
class StatusResponse(BaseModel):
    status: str
    message: str

class Query(BaseModel):
    query: str
    
class JobDescription(BaseModel):
    jd: str

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
        
        # Store the result in the current session
        if result["status"] == "success":
            current_session["resume_data"] = result["resume_data"]
        
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
        
        # Store the result in the current session
        if result["status"] == "success":
            current_session["jd_data"] = result["jd_data"]
        
        # Return the processing result
        return result
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing job description: {str(e)}")
    
    finally:
        # Clean up the temporary file
        if os.path.exists(temp_file_path):
            os.unlink(temp_file_path)

@app.post("/analyze-match/", response_model=Dict[str, Any])
async def analyze_match():
    """Analyze how well the resume matches the job description"""
    # Check if both resume and JD data are available
    if not current_session["resume_data"] or not current_session["jd_data"]:
        raise HTTPException(status_code=400, detail="Please upload both resume and job description first.")
    
    try:
        # Analyze the match
        bot = ResumeParsingBot()
        result = bot.analyze_match(current_session["resume_data"], current_session["jd_data"])
        
        # Store the analysis result in the current session
        if result["status"] == "success":
            current_session["analysis_data"] = result["match_analysis"]
        
        # Return the analysis result
        return result
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error analyzing match: {str(e)}")

@app.post("/chat/", response_model=Dict[str, Any])
async def chat(query: Query):
    """Chat with the AI about the resume and job description"""
    # Check if both resume and JD data are available
    if not current_session["resume_data"]:
        raise HTTPException(status_code=400, detail="Please upload a resume first.")
    
    try:
        # Process the chat message
        bot = ResumeParsingBot()
        result = bot.chat_message(
            current_session["resume_data"],
            current_session["jd_data"],
            current_session["analysis_data"],
            query.query
        )
        
        # If the resume data was updated (status change), update the session
        if result.get("updated_resume_data"):
            current_session["resume_data"] = result["updated_resume_data"]
        
        # Return the chat result
        return result
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing chat: {str(e)}")

@app.post("/clear-session/", response_model=StatusResponse)
async def clear_session():
    """Clear the current session data"""
    global current_session
    current_session = {
        "resume_data": None,
        "jd_data": None,
        "analysis_data": None
    }
    return {"status": "success", "message": "Session cleared successfully"}

@app.get("/current-data/", response_model=Dict[str, Any])
async def get_current_data():
    """Get all current session data"""
    return current_session

if __name__ == "__main__":
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True) 