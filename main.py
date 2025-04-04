import os
import tempfile
import shutil
import uuid
import json
import logging
import sys
from fastapi import FastAPI, UploadFile, File, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
from typing import Dict, Any, Optional

from app import ResumeParsingBot

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("api_server.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("resume_api")

# Create data directory if it doesn't exist
DATA_DIR = "data_storage"
RESUME_DATA_FILE = os.path.join(DATA_DIR, "resume_sessions.json")
JD_DATA_FILE = os.path.join(DATA_DIR, "jd_sessions.json")
ANALYSIS_DATA_FILE = os.path.join(DATA_DIR, "analysis_sessions.json")

os.makedirs(DATA_DIR, exist_ok=True)
logger.info(f"Data directory: {os.path.abspath(DATA_DIR)}")

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

# Initialize empty dictionaries
resume_sessions = {}
jd_sessions = {}
analysis_sessions = {}

# Function to load session data from disk
def load_sessions():
    # Use function-local variables for concurrency safety
    resume_data = {}
    jd_data = {}
    analysis_data = {}
    
    # Load resume sessions
    try:
        logger.debug(f"Loading resume sessions from {RESUME_DATA_FILE}")
        if os.path.exists(RESUME_DATA_FILE) and os.path.getsize(RESUME_DATA_FILE) > 0:
            with open(RESUME_DATA_FILE, 'r', encoding='utf-8') as f:
                resume_data = json.load(f)
            logger.debug(f"Loaded {len(resume_data)} resume sessions from storage")
        else:
            logger.warning(f"Resume sessions file does not exist or is empty: {RESUME_DATA_FILE}")
    except Exception as e:
        logger.error(f"Error loading resume sessions: {str(e)}")
    
    # Load JD sessions
    try:
        logger.debug(f"Loading JD sessions from {JD_DATA_FILE}")
        if os.path.exists(JD_DATA_FILE) and os.path.getsize(JD_DATA_FILE) > 0:
            with open(JD_DATA_FILE, 'r', encoding='utf-8') as f:
                jd_data = json.load(f)
            logger.debug(f"Loaded {len(jd_data)} JD sessions from storage")
        else:
            logger.warning(f"JD sessions file does not exist or is empty: {JD_DATA_FILE}")
    except Exception as e:
        logger.error(f"Error loading JD sessions: {str(e)}")
    
    # Load analysis sessions
    try:
        logger.debug(f"Loading analysis sessions from {ANALYSIS_DATA_FILE}")
        if os.path.exists(ANALYSIS_DATA_FILE) and os.path.getsize(ANALYSIS_DATA_FILE) > 0:
            with open(ANALYSIS_DATA_FILE, 'r', encoding='utf-8') as f:
                analysis_data = json.load(f)
            logger.debug(f"Loaded {len(analysis_data)} analysis sessions from storage")
        else:
            logger.warning(f"Analysis sessions file does not exist or is empty: {ANALYSIS_DATA_FILE}")
    except Exception as e:
        logger.error(f"Error loading analysis sessions: {str(e)}")
    
    return resume_data, jd_data, analysis_data

# Function to save session data
def save_sessions(resume_data, jd_data, analysis_data):
    try:
        logger.debug(f"Saving {len(resume_data)} resume sessions to {RESUME_DATA_FILE}")
        with open(RESUME_DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(resume_data, f, ensure_ascii=False, indent=2)
        
        logger.debug(f"Saving {len(jd_data)} JD sessions to {JD_DATA_FILE}")
        with open(JD_DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(jd_data, f, ensure_ascii=False, indent=2)
        
        logger.debug(f"Saving {len(analysis_data)} analysis sessions to {ANALYSIS_DATA_FILE}")
        with open(ANALYSIS_DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(analysis_data, f, ensure_ascii=False, indent=2)
        
        logger.debug("All session data saved to disk successfully")
        return True
    except Exception as e:
        logger.error(f"Error saving session data: {str(e)}")
        return False

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
    logger.info(f"Processing resume upload: {resume_file.filename}")
    
    # Load current sessions
    resume_sessions, jd_sessions, analysis_sessions = load_sessions()
    
    # Check file extension
    file_extension = os.path.splitext(resume_file.filename)[1].lower()
    if file_extension not in ['.pdf', '.docx', '.txt']:
        logger.warning(f"Invalid file format: {file_extension}")
        raise HTTPException(status_code=400, detail="Invalid file format. Please upload a PDF, DOCX, or TXT file.")
    
    # Create a temporary file
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=file_extension)
    
    try:
        # Write the uploaded file to the temporary file
        shutil.copyfileobj(resume_file.file, temp_file)
        temp_file.close()
        logger.debug(f"Saved resume to temporary file: {temp_file.name}")
        
        # Process the resume
        bot = ResumeParsingBot()
        result = bot.process_resume(temp_file.name)
        
        # Generate a unique ID for this resume
        resume_id = str(uuid.uuid4())
        logger.info(f"Generated resume ID: {resume_id}")
        
        # Store the result in the sessions dictionary
        if result["status"] == "success":
            # Add the ID to the resume data
            result["resume_data"]["id"] = resume_id
            resume_sessions[resume_id] = result["resume_data"]
            
            # Save to disk
            if save_sessions(resume_sessions, jd_sessions, analysis_sessions):
                logger.info(f"Resume {resume_id} saved successfully")
            else:
                logger.error(f"Failed to save resume {resume_id} to disk")
            
            # Add the ID to the result
            result["resume_id"] = resume_id
            
            # Log current session state
            logger.debug(f"Current resume sessions: {list(resume_sessions.keys())}")
        
        # Return the processing result
        return result
    
    except Exception as e:
        logger.error(f"Error processing resume: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error processing resume: {str(e)}")
    
    finally:
        # Clean up the temporary file
        if os.path.exists(temp_file.name):
            os.unlink(temp_file.name)
            logger.debug(f"Removed temporary file: {temp_file.name}")

@app.post("/upload-jd/", response_model=Dict[str, Any])
async def upload_jd(jd_data: JobDescription):
    """Process a job description provided as text"""
    logger.info("Processing job description upload")
    
    # Load current sessions
    resume_sessions, jd_sessions, analysis_sessions = load_sessions()
    
    try:
        # Create a temporary file to store the job description text
        with tempfile.NamedTemporaryFile(delete=False, suffix='.txt', mode='w', encoding='utf-8') as temp_file:
            temp_file.write(jd_data.jd)
            temp_file_path = temp_file.name
            logger.debug(f"Saved JD to temporary file: {temp_file_path}")
        
        # Process the job description
        bot = ResumeParsingBot()
        result = bot.process_job_description(temp_file_path)
        
        # Generate a unique ID for this job description
        jd_id = str(uuid.uuid4())
        logger.info(f"Generated JD ID: {jd_id}")
        
        # Store the result in the sessions dictionary
        if result["status"] == "success":
            # Add the ID to the JD data
            result["jd_data"]["id"] = jd_id
            jd_sessions[jd_id] = result["jd_data"]
            
            # Save to disk
            if save_sessions(resume_sessions, jd_sessions, analysis_sessions):
                logger.info(f"JD {jd_id} saved successfully")
            else:
                logger.error(f"Failed to save JD {jd_id} to disk")
            
            # Add the ID to the result
            result["jd_id"] = jd_id
            
            # Log current session state
            logger.debug(f"Current JD sessions: {list(jd_sessions.keys())}")
        
        # Return the processing result
        return result
    
    except Exception as e:
        logger.error(f"Error processing job description: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error processing job description: {str(e)}")
    
    finally:
        # Clean up the temporary file
        if os.path.exists(temp_file_path):
            os.unlink(temp_file_path)
            logger.debug(f"Removed temporary file: {temp_file_path}")

@app.post("/analyze-match/", response_model=Dict[str, Any])
async def analyze_match(match_request: MatchRequest):
    """Analyze how well the resume matches the job description"""
    logger.info(f"Analyzing match for resume {match_request.resume_id} and JD {match_request.jd_id}")
    
    # Load current sessions
    resume_sessions, jd_sessions, analysis_sessions = load_sessions()
    
    # Check if both resume and JD data are available
    resume_id = match_request.resume_id
    jd_id = match_request.jd_id
    
    # Debug log the current session state
    logger.debug(f"Current resume sessions: {list(resume_sessions.keys())}")
    logger.debug(f"Current JD sessions: {list(jd_sessions.keys())}")
    
    if resume_id not in resume_sessions:
        logger.warning(f"Resume with ID {resume_id} not found")
        raise HTTPException(status_code=404, detail=f"Resume with ID {resume_id} not found")
    
    if jd_id not in jd_sessions:
        logger.warning(f"Job description with ID {jd_id} not found")
        # Check if the data files exist and log details
        logger.debug(f"Checking JD file: {os.path.exists(JD_DATA_FILE)}")
        if os.path.exists(JD_DATA_FILE):
            logger.debug(f"JD file size: {os.path.getsize(JD_DATA_FILE)}")
            
            # Try to read the raw file content for debugging
            try:
                with open(JD_DATA_FILE, 'r', encoding='utf-8') as f:
                    jd_raw = f.read()
                logger.debug(f"JD file preview: {jd_raw[:100]}...")
            except Exception as e:
                logger.error(f"Failed to read JD file: {str(e)}")
        
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
            if save_sessions(resume_sessions, jd_sessions, analysis_sessions):
                logger.info(f"Analysis for {resume_id} and {jd_id} saved successfully")
            else:
                logger.error(f"Failed to save analysis for {resume_id} and {jd_id} to disk")
        
        # Add IDs to the result at root level only
        result["resume_id"] = resume_id
        result["jd_id"] = jd_id
        
        return result
    
    except Exception as e:
        logger.error(f"Error analyzing match: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error analyzing match: {str(e)}")

@app.post("/chat/", response_model=Dict[str, Any])
async def chat(query: Query):
    """Chat with the AI about the resume and job description"""
    logger.info(f"Processing chat for resume {query.resume_id} and JD {query.jd_id}")
    
    # Load current sessions
    resume_sessions, jd_sessions, analysis_sessions = load_sessions()
    
    resume_id = query.resume_id
    jd_id = query.jd_id
    
    # Check if resume data is available
    if resume_id not in resume_sessions:
        logger.warning(f"Resume with ID {resume_id} not found")
        raise HTTPException(status_code=404, detail=f"Resume with ID {resume_id} not found")
    
    # Get JD data if an ID was provided
    jd_data = None
    if jd_id and jd_id in jd_sessions:
        jd_data = jd_sessions[jd_id]
    elif jd_id:
        logger.warning(f"Job description with ID {jd_id} not found")
        raise HTTPException(status_code=404, detail=f"Job description with ID {jd_id} not found")
    
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
            if save_sessions(resume_sessions, jd_sessions, analysis_sessions):
                logger.info(f"Updated resume {resume_id} saved successfully")
            else:
                logger.error(f"Failed to save updated resume {resume_id} to disk")
        
        # Add IDs to the result
        result["resume_id"] = resume_id
        if jd_id:
            result["jd_id"] = jd_id
        
        return result
    
    except Exception as e:
        logger.error(f"Error processing chat: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error processing chat: {str(e)}")

@app.post("/clear-specific-session/", response_model=StatusResponse)
async def clear_specific_session(clear_request: ClearSessionRequest):
    """Clear a specific resume-JD session combination"""
    logger.info(f"Clearing session for resume {clear_request.resume_id} and JD {clear_request.jd_id}")
    
    # Load current sessions
    resume_sessions, jd_sessions, analysis_sessions = load_sessions()
    
    resume_id = clear_request.resume_id
    jd_id = clear_request.jd_id
    
    # Check if IDs exist
    resume_exists = resume_id in resume_sessions
    jd_exists = jd_id in jd_sessions
    
    if not resume_exists and not jd_exists:
        logger.warning(f"Neither resume ID {resume_id} nor JD ID {jd_id} found")
        return {"status": "error", "message": f"Neither resume ID {resume_id} nor JD ID {jd_id} found"}
    
    # Create the analysis key
    analysis_key = f"{resume_id}_{jd_id}"
    analysis_exists = analysis_key in analysis_sessions
    
    # Delete the analysis data if it exists
    if analysis_exists:
        del analysis_sessions[analysis_key]
        logger.info(f"Deleted analysis for {resume_id} and {jd_id}")
    
    # Save changes to disk
    if save_sessions(resume_sessions, jd_sessions, analysis_sessions):
        logger.info(f"Session changes saved successfully")
    else:
        logger.error(f"Failed to save session changes to disk")
    
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
    logger.info("Listing all resumes")
    
    # Load current sessions
    resume_sessions, _, _ = load_sessions()
    
    resume_list = []
    for resume_id, resume_data in resume_sessions.items():
        resume_list.append({
            "id": resume_id,
            "name": resume_data.get("name") or resume_data.get("fullName") or resume_data.get("CandidateFullName", "Unknown"),
            "upload_date": resume_data.get("upload_date", "Unknown")
        })
    
    return {
        "status": "success",
        "resumes": resume_list
    }

@app.get("/list-jds/", response_model=Dict[str, Any])
async def list_jds():
    """List all available job description IDs with titles"""
    logger.info("Listing all job descriptions")
    
    # Load current sessions
    _, jd_sessions, _ = load_sessions()
    
    jd_list = []
    for jd_id, jd_data in jd_sessions.items():
        jd_list.append({
            "id": jd_id,
            "title": jd_data.get("job_title") or jd_data.get("Job title", "Unknown"),
            "upload_date": jd_data.get("upload_date", "Unknown")
        })
    
    return {
        "status": "success",
        "job_descriptions": jd_list
    }

@app.get("/debug-sessions/", response_model=Dict[str, Any])
async def debug_sessions():
    """Debug endpoint to check the current state of sessions"""
    logger.info("Debug session state requested")
    
    # Load current sessions
    resume_sessions, jd_sessions, analysis_sessions = load_sessions()
    
    return {
        "resume_sessions": list(resume_sessions.keys()),
        "jd_sessions": list(jd_sessions.keys()),
        "analysis_sessions": list(analysis_sessions.keys()),
        "resume_count": len(resume_sessions),
        "jd_count": len(jd_sessions),
        "analysis_count": len(analysis_sessions),
        "data_dir": os.path.abspath(DATA_DIR),
        "files_exist": {
            "resume_file": os.path.exists(RESUME_DATA_FILE),
            "jd_file": os.path.exists(JD_DATA_FILE),
            "analysis_file": os.path.exists(ANALYSIS_DATA_FILE)
        },
        "file_sizes": {
            "resume_file": os.path.getsize(RESUME_DATA_FILE) if os.path.exists(RESUME_DATA_FILE) else 0,
            "jd_file": os.path.getsize(JD_DATA_FILE) if os.path.exists(JD_DATA_FILE) else 0,
            "analysis_file": os.path.getsize(ANALYSIS_DATA_FILE) if os.path.exists(ANALYSIS_DATA_FILE) else 0
        }
    }

@app.post("/reset-data-store/", response_model=StatusResponse)
async def reset_data_store():
    """Reset all data storage and create new empty files"""
    logger.warning("Resetting all data storage files")
    
    # Create empty JSON files
    try:
        with open(RESUME_DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump({}, f)
            
        with open(JD_DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump({}, f)
            
        with open(ANALYSIS_DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump({}, f)
            
        logger.info("All data files reset successfully")
        return {
            "status": "success",
            "message": "All data storage has been reset"
        }
    except Exception as e:
        logger.error(f"Error resetting data files: {str(e)}")
        return {
            "status": "error",
            "message": f"Error resetting data files: {str(e)}"
        }

def dev():
    """Run the server in development mode"""
    logger.info("Starting server in development mode")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

def prod():
    """Run the server in production mode"""
    logger.info("Starting server in production mode")
    uvicorn.run("main:app", host="0.0.0.0", port=8000)

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "dev":
        dev()
    else:
        prod()