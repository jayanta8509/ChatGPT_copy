import os
import openai
from dotenv import load_dotenv
import logging
import json
import PyPDF2
import docx
import datetime

# Load environment variables
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

class ResumeParsingBot:
    def __init__(self):
        self.logger = self._setup_logger()
        
    def _setup_logger(self):
        logger = logging.getLogger("resume_parser")
        logger.setLevel(logging.INFO)
        handler = logging.FileHandler("resume_parser.log")
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        return logger
    
    def process_resume(self, resume_file_path):
        """Process and parse a resume file and return JSON data"""
        # Extract text from resume file
        resume_text = self._extract_text_from_file(resume_file_path)
        
        # Use GPT-4o to extract structured information
        system_prompt = """
        You are an expert resume parser. Extract the following information from the resume:
        1. Candidate's full name
        2. Email address
        3. Phone number
        4. Skills (list all technical and soft skills)
        5. For each company experience:
           - Company name
           - Position/role
           - Duration (start date and end date)
           - Whether it's a product or service company
           - Business type (B2B or B2C if discernible)
           - Number of employees (if mentioned or can be inferred)
           - Funding received and type of funding (if mentioned)
           - Company main location
        6. Education details:
           - College/University name
           - Course/degree
           - Graduation year
        7. Overall stability assessment (years staying in previous companies)
        
        Format your response as a JSON object.
        """
        
        try:
            response = openai.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": resume_text}
                ],
                response_format={"type": "json_object"}
            )
            
            parsed_data = json.loads(response.choices[0].message.content)
            
            # Add file information to the result
            file_name = os.path.basename(resume_file_path)
            parsed_data["resume_file"] = file_name
            parsed_data["upload_date"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # Add empty status fields that will be updated later
            parsed_data["ai_rating"] = 0
            parsed_data["ai_shortlisted"] = "No"
            parsed_data["internal_shortlisted"] = "No"
            parsed_data["interview_in_process"] = "No"
            parsed_data["final_result"] = "Pending"
            parsed_data["candidate_joined"] = "No"
            
            # Calculate token usage
            tokens_used = response.usage.total_tokens
            cost = self._calculate_cost(tokens_used)
            
            # Add usage info to the result
            result = {
                "resume_data": parsed_data,
                "usage": {
                    "tokens": tokens_used,
                    "cost": cost
                },
                "status": "success"
            }
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error processing resume: {str(e)}")
            return {
                "status": "error",
                "message": f"Error processing resume: {str(e)}"
            }
    
    def process_job_description(self, jd_file_path):
        """Process and parse a job description file and return JSON data"""
        # Extract text from JD file
        jd_text = self._extract_text_from_file(jd_file_path)
        
        # Use GPT-4o to extract structured information
        system_prompt = """
        You are an expert job description analyst. Extract the following information:
        1. Job title
        2. Required skills (technical and soft skills)
        3. Years of experience required
        4. Education requirements
        5. Company type preference (Product/Service if mentioned)
        6. Business type preference (B2B/B2C if mentioned)
        7. Preferred stability (years in previous companies if mentioned)
        8. Other important requirements
        
        Format your response as a JSON object.
        """
        
        try:
            response = openai.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": jd_text}
                ],
                response_format={"type": "json_object"}
            )
            
            parsed_data = json.loads(response.choices[0].message.content)
            
            # Add file information
            file_name = os.path.basename(jd_file_path)
            parsed_data["jd_file"] = file_name
            parsed_data["upload_date"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # Calculate token usage
            tokens_used = response.usage.total_tokens
            cost = self._calculate_cost(tokens_used)
            
            # Add usage info to the result
            result = {
                "jd_data": parsed_data,
                "usage": {
                    "tokens": tokens_used,
                    "cost": cost
                },
                "status": "success"
            }
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error processing job description: {str(e)}")
            return {
                "status": "error",
                "message": f"Error processing job description: {str(e)}"
            }
    
    def analyze_match(self, resume_data, jd_data):
        """Analyze how well the candidate matches the job description"""
        if not resume_data or not jd_data:
            return {
                "status": "error",
                "message": "Please provide both resume and job description data."
            }
        
        # Format data for GPT-4o
        resume_json = json.dumps(resume_data)
        jd_json = json.dumps(jd_data)
        
        system_prompt = """
        You are an expert recruitment assistant. Analyze how well the candidate matches the job description.
        Provide the following:
        1. Suggested role for the candidate (e.g., Frontend, Backend, DevOps, etc.)
        2. Match score (1-10)
        3. Whether the candidate should be shortlisted (Yes/No)
        4. Company type match (Product/Service)
        5. Business type match (B2B/B2C)
        6. Stability assessment (based on years in previous companies)
        7. Analysis of each company in the candidate's resume:
           - Company type (Product/Service)
           - Industry sector
           - Business model (B2B/B2C)
           - Any notable achievements
        8. Education assessment:
           - College/University assessment
           - Course relevance
        9. Overall rating (1-10)
        10. Anything missing as per expectations in the JD
        11. Overall recommendation (detailed assessment)
        
        Format your response as a JSON object.
        """
        
        try:
            response = openai.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Resume information: {resume_json}\n\nJob Description: {jd_json}"}
                ],
                response_format={"type": "json_object"}
            )
            
            analysis = json.loads(response.choices[0].message.content)
            
            # Calculate token usage
            tokens_used = response.usage.total_tokens
            cost = self._calculate_cost(tokens_used)
            
            # Add timestamp to the analysis
            analysis["analysis_date"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # Add usage info to the result
            result = {
                "match_analysis": analysis,
                "usage": {
                    "tokens": tokens_used,
                    "cost": cost
                },
                "status": "success"
            }
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error analyzing match: {str(e)}")
            return {
                "status": "error",
                "message": f"Error analyzing match: {str(e)}"
            }
    
    def update_candidate_status(self, resume_data, update_info):
        """Update candidate status based on chat commands"""
        if not resume_data:
            return {
                "status": "error",
                "message": "No resume data provided"
            }
            
        # Check if the update contains candidate identifiers
        candidate_name = update_info.get('name')
        candidate_email = update_info.get('email')
        candidate_phone = update_info.get('phone')
        
        # Verify this is the correct candidate
        if (candidate_name and candidate_name.lower() != resume_data.get('name', '').lower()) or \
           (candidate_email and candidate_email.lower() != resume_data.get('email', '').lower()) or \
           (candidate_phone and candidate_phone != resume_data.get('phone')):
            return {
                "status": "error",
                "message": "Candidate information doesn't match"
            }
        
        # Apply status updates
        updated_resume = resume_data.copy()
        
        if update_info.get('internal_shortlisted'):
            updated_resume['internal_shortlisted'] = "Yes"
            
        if update_info.get('interview_in_process'):
            updated_resume['interview_in_process'] = "Yes"
            
        if update_info.get('final_result'):
            updated_resume['final_result'] = update_info.get('final_result')
            
        if update_info.get('candidate_joined'):
            updated_resume['candidate_joined'] = "Yes"
            
        # Log the update
        self.logger.info(f"Updated status for candidate {updated_resume.get('name')}: {update_info}")
        
        return {
            "status": "success",
            "message": "Candidate status updated",
            "updated_resume_data": updated_resume
        }
    
    def chat_message(self, resume_data, jd_data, analysis_data, user_message):
        """Process a chat message and extract any relevant information"""
        # Check if this is a status update command
        status_update = self._check_for_status_update(user_message)
        
        # If it's a status update, process it
        if status_update:
            update_result = self.update_candidate_status(resume_data, status_update)
            resume_data = update_result.get("updated_resume_data", resume_data)
        
        # Build context for GPT-4o
        context = f"""
        Candidate information: {json.dumps(resume_data) if resume_data else 'Not provided yet'}
        
        Job Description information: {json.dumps(jd_data) if jd_data else 'Not provided yet'}
        
        Analysis information: {json.dumps(analysis_data) if analysis_data else 'Not provided yet'}
        """
        
        system_prompt = """
        You are a helpful recruitment assistant chatbot that helps with analyzing resumes and job descriptions.
        Respond naturally to the user's questions. If they ask about the candidate or the job match, use the context provided.
        
        If the user is updating a candidate status (e.g., "Mark as internally shortlisted", "Move to interview process", etc.),
        acknowledge the update and confirm the new status.
        
        Keep your responses helpful, concise, and focused on recruitment topics.
        """
        
        try:
            response = openai.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Context:\n{context}\n\nUser message: {user_message}"}
                ]
            )
            
            bot_response = response.choices[0].message.content
            
            # Calculate token usage
            tokens_used = response.usage.total_tokens
            cost = self._calculate_cost(tokens_used)
            
            chat_result = {
                "response": bot_response,
                "updated_resume_data": resume_data if status_update else None,
                "usage": {
                    "tokens": tokens_used,
                    "cost": cost
                },
                "status": "success"
            }
            
            return chat_result
            
        except Exception as e:
            self.logger.error(f"Error in chat: {str(e)}")
            return {
                "status": "error",
                "message": f"I'm having trouble processing your request: {str(e)}"
            }
    
    def _extract_text_from_file(self, file_path):
        """Extract text from various file formats (PDF, DOCX, TXT)"""
        try:
            file_ext = os.path.splitext(file_path)[1].lower()
            
            # Handle PDF files
            if file_ext == '.pdf':
                text = ""
                with open(file_path, 'rb') as file:
                    pdf_reader = PyPDF2.PdfReader(file)
                    for page_num in range(len(pdf_reader.pages)):
                        text += pdf_reader.pages[page_num].extract_text()
                return text
            
            # Handle DOCX files
            elif file_ext == '.docx':
                doc = docx.Document(file_path)
                text = "\n".join([paragraph.text for paragraph in doc.paragraphs])
                return text
                
            # Handle plain text files
            elif file_ext == '.txt':
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
                    return file.read()
            
            else:
                self.logger.error(f"Unsupported file format: {file_ext}")
                return f"Unsupported file format: {file_ext}. Please use PDF, DOCX, or TXT files."
                
        except Exception as e:
            self.logger.error(f"Error extracting text: {str(e)}")
            return f"Error extracting text: {str(e)}"
    
    def _calculate_cost(self, tokens):
        """Calculate cost based on token usage"""
        # GPT-4o pricing (example - adjust based on actual pricing)
        return (tokens / 1000) * 0.01  # $0.01 per 1K tokens (example)
    
    def _check_for_status_update(self, message):
        """Check if the message contains a status update command"""
        message_lower = message.lower()
        
        status_updates = {}
        
        # Extract candidate identifiers if present
        # Look for patterns like "Shortlist John Doe (john@example.com, 1234567890)"
        import re
        
        # Name extraction
        name_match = re.search(r"(?:shortlist|interview|select|reject|joined|onboard)\s+([A-Za-z\s]+)(?:\s*\(|,|$)", message_lower)
        if name_match:
            status_updates["name"] = name_match.group(1).strip()
        
        # Email extraction
        email_match = re.search(r"([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)", message)
        if email_match:
            status_updates["email"] = email_match.group(1)
            
        # Phone extraction
        phone_match = re.search(r"(\d{10}|\d{3}[-.\s]\d{3}[-.\s]\d{4}|\(\d{3}\)\s*\d{3}[-.\s]\d{4})", message)
        if phone_match:
            status_updates["phone"] = phone_match.group(1)
        
        # Command extraction
        if "shortlist" in message_lower and "internal" in message_lower:
            status_updates["internal_shortlisted"] = True
        
        if any(phrase in message_lower for phrase in ["interview process", "move to interview", "start interview"]):
            status_updates["interview_in_process"] = True
        
        if "select" in message_lower or "offer" in message_lower:
            status_updates["final_result"] = "Selected"
        
        if "reject" in message_lower:
            status_updates["final_result"] = "Rejected"
        
        if "joined" in message_lower or "onboard" in message_lower:
            status_updates["candidate_joined"] = True
            
        return status_updates


# Example usage
if __name__ == "__main__":
    bot = ResumeParsingBot()
    
    # Process resume
    resume_result = bot.process_resume("./sample_resume.pdf")
    print(json.dumps(resume_result, indent=2))
    
    # Process job description
    jd_result = bot.process_job_description("./sample_jd.txt")
    print(json.dumps(jd_result, indent=2))
    
    # Analyze match (only if both resume and JD were successful)
    if resume_result.get("status") == "success" and jd_result.get("status") == "success":
        match_result = bot.analyze_match(resume_result.get("resume_data"), jd_result.get("jd_data"))
        print(json.dumps(match_result, indent=2))
        
        # Example chat interaction
        chat_result = bot.chat_message(
            resume_result.get("resume_data"),
            jd_result.get("jd_data"),
            match_result.get("match_analysis"),
            "Should we shortlist this candidate internally?"
        )
        print("Chat response:", chat_result.get("response"))