import os
import tempfile
import shutil
import uuid
import json
import logging
import sys
import requests
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

# Initialize empty dictionaries (only keep analysis_sessions)
analysis_sessions = {}

# Function to load session data from disk (simplified to only load analysis data)
def load_sessions():
    # Use function-local variables for concurrency safety
    analysis_data = {}
    
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
    
    # Return empty dictionaries for resume and jd sessions
    return {}, {}, analysis_data

# Function to save session data (simplified to only save analysis data)
def save_sessions(resume_data, jd_data, analysis_data):
    try:
        logger.debug(f"Saving {len(analysis_data)} analysis sessions to {ANALYSIS_DATA_FILE}")
        with open(ANALYSIS_DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(analysis_data, f, ensure_ascii=False, indent=2)
        
        logger.debug("Analysis session data saved to disk successfully")
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

@app.post("/upload-resume/", response_model=Dict[str, Any])
async def upload_resume(resume_file: UploadFile = File(...)):
    """Upload and process a resume file (PDF or DOCX)"""
    logger.info(f"Processing resume upload: {resume_file.filename}")
    
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
            
            # Add the ID to the result
            result["resume_id"] = resume_id
            
            logger.info(f"Resume {resume_id} processed successfully")
        
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
            
            # Add the ID to the result
            result["jd_id"] = jd_id
            
            logger.info(f"JD {jd_id} processed successfully")
        
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
    
    resume_id = match_request.resume_id
    jd_id = match_request.jd_id
    
    try:
        # Fetch resume data from external API
        logger.debug(f"Fetching resume data for ID {resume_id} from external API")
        resume_response = requests.post(
            "https://cvbackend.bestworks.cloud/api/v1/other/search-resume",
            json={"resume_id": resume_id}
        )
        if not resume_response.ok:
            logger.warning(f"Failed to fetch resume data: {resume_response.status_code} - {resume_response.text}")
            raise HTTPException(status_code=404, detail=f"Resume with ID {resume_id} not found in external API")
        
        resume_data = resume_response.json()
        if not resume_data.get("status"):
            logger.warning(f"External API returned error for resume: {resume_data.get('message')}")
            raise HTTPException(status_code=404, detail=f"Resume with ID {resume_id} not found: {resume_data.get('message')}")
        
        # Extract only the resume data we need for analysis
        resume_info = resume_data.get("data", {})
        
        # Fetch JD data from external API
        logger.debug(f"Fetching JD data for ID {jd_id} from external API")
        jd_response = requests.post(
            "https://cvbackend.bestworks.cloud/api/v1/other/search-jd",
            json={"jd_id": jd_id}
        )
        if not jd_response.ok:
            logger.warning(f"Failed to fetch JD data: {jd_response.status_code} - {jd_response.text}")
            raise HTTPException(status_code=404, detail=f"Job description with ID {jd_id} not found in external API")
        
        jd_data = jd_response.json()
        if not jd_data.get("status"):
            logger.warning(f"External API returned error for JD: {jd_data.get('message')}")
            raise HTTPException(status_code=404, detail=f"Job description with ID {jd_id} not found: {jd_data.get('message')}")
        
        # Extract only the JD data we need for analysis
        jd_info = jd_data.get("data", {})
        
        # Clean up the resume and JD data by removing unwanted fields
        cleaned_resume = {
            "CandidateFullName": resume_info.get("candidate_full_name"),
            "EmailAddress": resume_info.get("email_address"),
            "PhoneNumber": resume_info.get("phone_number"),
            "Skills": resume_info.get("skills", []),
            "Experience": resume_info.get("experience", []),
            "Education": resume_info.get("education_details", []),
            "StabilityAssessment": resume_info.get("overall_stability_assessment"),
            "TotalYearsOfExperience": resume_info.get("total_years_of_experience", 0.0),
            "resume_file": resume_info.get("resume_file"),
            "upload_date": resume_info.get("upload_date")
        }
        
        cleaned_jd = {
            "CompanyName": jd_info.get("company_name"),
            "JobTitle": jd_info.get("job_title"),
            "RequiredSkills": jd_info.get("required_skills", {"technical": [], "soft": []}),
            "YearsOfExperienceRequired": jd_info.get("years_of_experience_required"),
            "EducationRequirements": jd_info.get("education_requirements"),
            "CompanyTypePreference": jd_info.get("company_type_preference"),
            "BusinessTypePreference": jd_info.get("business_type_preference"),
            "PreferredStability": jd_info.get("preferred_stability"),
            "OtherImportantRequirements": jd_info.get("other_important_requirements", []),
            "jd_file": jd_info.get("jd_file"),
            "upload_date": jd_info.get("upload_date")
        }
        
        # Create a unique key for this analysis
        analysis_key = f"{resume_id}_{jd_id}"
        
        # Load current sessions to store the analysis result
        _, _, analysis_sessions = load_sessions()
        
        # Analyze the match
        bot = ResumeParsingBot()
        result = bot.analyze_match(cleaned_resume, cleaned_jd)
        
        # Store the analysis result
        if result["status"] == "success":
            # We don't need to add IDs inside the match_analysis object since they're already at the root level
            analysis_sessions[analysis_key] = result["match_analysis"]
            
            # Save to disk
            if save_sessions({}, {}, analysis_sessions):
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
    
    resume_id = query.resume_id
    jd_id = query.jd_id
    
    try:
        # Fetch resume data from external API
        logger.debug(f"Fetching resume data for ID {resume_id} from external API")
        resume_response = requests.post(
            "https://cvbackend.bestworks.cloud/api/v1/other/search-resume",
            json={"resume_id": resume_id}
        )
        if not resume_response.ok:
            logger.warning(f"Failed to fetch resume data: {resume_response.status_code} - {resume_response.text}")
            raise HTTPException(status_code=404, detail=f"Resume with ID {resume_id} not found in external API")
        
        resume_data = resume_response.json()
        if not resume_data.get("status"):
            logger.warning(f"External API returned error for resume: {resume_data.get('message')}")
            raise HTTPException(status_code=404, detail=f"Resume with ID {resume_id} not found: {resume_data.get('message')}")
        
        # Extract only the resume data we need for chat
        resume_info = resume_data.get("data", {})
        
        # Clean up the resume data by removing unwanted fields
        cleaned_resume = {
            "CandidateFullName": resume_info.get("candidate_full_name"),
            "EmailAddress": resume_info.get("email_address"),
            "PhoneNumber": resume_info.get("phone_number"),
            "Skills": resume_info.get("skills", []),
            "Experience": resume_info.get("experience", []),
            "Education": resume_info.get("education_details", []),
            "StabilityAssessment": resume_info.get("overall_stability_assessment"),
            "TotalYearsOfExperience": resume_info.get("total_years_of_experience", 0.0),
            "resume_file": resume_info.get("resume_file"),
            "upload_date": resume_info.get("upload_date")
        }
        
        # Get JD data if an ID was provided
        cleaned_jd = None
        if jd_id:
            logger.debug(f"Fetching JD data for ID {jd_id} from external API")
            jd_response = requests.post(
                "https://cvbackend.bestworks.cloud/api/v1/other/search-jd",
                json={"jd_id": jd_id}
            )
            if not jd_response.ok:
                logger.warning(f"Failed to fetch JD data: {jd_response.status_code} - {jd_response.text}")
                raise HTTPException(status_code=404, detail=f"Job description with ID {jd_id} not found in external API")
            
            jd_data = jd_response.json()
            if not jd_data.get("status"):
                logger.warning(f"External API returned error for JD: {jd_data.get('message')}")
                raise HTTPException(status_code=404, detail=f"Job description with ID {jd_id} not found: {jd_data.get('message')}")
            
            # Extract only the JD data we need for chat
            jd_info = jd_data.get("data", {})
            
            cleaned_jd = {
                "CompanyName": jd_info.get("company_name"),
                "JobTitle": jd_info.get("job_title"),
                "RequiredSkills": jd_info.get("required_skills", {"technical": [], "soft": []}),
                "YearsOfExperienceRequired": jd_info.get("years_of_experience_required"),
                "EducationRequirements": jd_info.get("education_requirements"),
                "CompanyTypePreference": jd_info.get("company_type_preference"),
                "BusinessTypePreference": jd_info.get("business_type_preference"),
                "PreferredStability": jd_info.get("preferred_stability"),
                "OtherImportantRequirements": jd_info.get("other_important_requirements", []),
                "jd_file": jd_info.get("jd_file"),
                "upload_date": jd_info.get("upload_date")
            }
        
        # Get analysis data if available
        analysis_data = None
        if jd_id:
            analysis_key = f"{resume_id}_{jd_id}"
            # Load current sessions to get the analysis data if available
            _, _, analysis_sessions = load_sessions()
            if analysis_key in analysis_sessions:
                analysis_data = analysis_sessions[analysis_key]
            else:
                logger.debug(f"No analysis data found for {resume_id} and {jd_id}")
        
        # Process the chat message
        bot = ResumeParsingBot()
        result = bot.chat_message(
            cleaned_resume,
            cleaned_jd,
            analysis_data,
            query.query
        )
        
        # If the resume data was updated (status change), store in analysis sessions instead
        if result.get("updated_resume_data") and jd_id:
            # Load current sessions
            _, _, analysis_sessions = load_sessions()
            analysis_key = f"{resume_id}_{jd_id}"
            
            # Store status updates in the analysis data
            if analysis_key in analysis_sessions:
                # Update existing analysis with status information
                analysis_sessions[analysis_key]["AIShortlisted"] = result["updated_resume_data"].get("internal_shortlisted", "No")
                analysis_sessions[analysis_key]["InterviewInProcess"] = result["updated_resume_data"].get("interview_in_process", "No")
                analysis_sessions[analysis_key]["FinalResult"] = result["updated_resume_data"].get("final_result", "Pending")
                analysis_sessions[analysis_key]["CandidateJoined"] = result["updated_resume_data"].get("candidate_joined", "No")
                
                # Save to disk
                if save_sessions({}, {}, analysis_sessions):
                    logger.info(f"Updated analysis status for {resume_id} and {jd_id} saved successfully")
                else:
                    logger.error(f"Failed to save updated analysis status for {resume_id} and {jd_id} to disk")
        
        # Add IDs to the result
        result["resume_id"] = resume_id
        if jd_id:
            result["jd_id"] = jd_id
        
        return result
    
    except Exception as e:
        logger.error(f"Error processing chat: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error processing chat: {str(e)}")

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