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
    
    def _normalize_resume_fields(self, data):
        """Normalize field names in resume data to ensure consistency"""
        normalized_data = {}
        
        # Define field mappings (from possible GPT variations -> standard field)
        field_mappings = {
            # Candidate name variations
            'candidate_full_name': 'CandidateFullName',
            'candidate_name': 'CandidateFullName',
            'full_name': 'CandidateFullName',
            'name': 'CandidateFullName',
            'candidate': 'CandidateFullName',
            
            # Email variations
            'email_address': 'EmailAddress',
            'email': 'EmailAddress',
            
            # Phone variations
            'phone_number': 'PhoneNumber',
            'phone': 'PhoneNumber',
            'contact': 'PhoneNumber',
            'contact_number': 'PhoneNumber',
            
            # Skills variations
            'skills': 'Skills',
            'technical_skills': 'Skills',
            'skill_set': 'Skills',
            
            # Experience variations
            'work_experience': 'Experience',
            'experience': 'Experience',
            'employment_history': 'Experience',
            'work_history': 'Experience',
            'companies': 'Experience',
            
            # Education variations
            'education_details': 'Education',
            'education': 'Education',
            'educational_background': 'Education',
            'academic_background': 'Education',
            'academic_details': 'Education',
            
            # Stability assessment variations
            'overall_stability_assessment': 'StabilityAssessment',
            'stability_assessment': 'StabilityAssessment',
            'stability': 'StabilityAssessment'
        }
        
        # Standard fields that should be included
        standard_fields = [
            'CandidateFullName', 
            'EmailAddress', 
            'PhoneNumber', 
            'Skills', 
            'Experience', 
            'Education',
            'StabilityAssessment'
        ]
        
        # Normalize the main fields
        for field, value in data.items():
            field_lower = field.lower()
            
            # Find the standardized field name
            if field_lower in field_mappings:
                standard_field = field_mappings[field_lower]
                normalized_data[standard_field] = value
            else:
                # Keep original field if no mapping exists
                normalized_data[field] = value
        
        # Normalize nested fields in Experience
        experience_key = None
        for key in ['Experience', 'experience', 'work_experience', 'employment_history', 'work_history', 'companies']:
            if key in normalized_data:
                experience_key = key
                break
                
        if experience_key and isinstance(normalized_data[experience_key], list):
            for i, exp in enumerate(normalized_data[experience_key]):
                normalized_exp = {}
                for field, value in exp.items():
                    field_lower = field.lower()
                    
                    # Map experience fields
                    if field_lower in ['company_name', 'company']:
                        normalized_exp['CompanyName'] = value
                    elif field_lower in ['position', 'role', 'job_title', 'title']:
                        normalized_exp['Position'] = value
                    elif field_lower in ['duration', 'period', 'tenure']:
                        # Check if duration is already structured
                        if isinstance(value, dict) and ('start_date' in value or 'end_date' in value):
                            normalized_exp['Duration'] = value
                        else:
                            # Try to parse the duration string
                            normalized_exp['Duration'] = self._parse_duration(value)
                    elif field_lower in ['product_or_service', 'company_type']:
                        normalized_exp['CompanyType'] = value
                    elif field_lower in ['business_type']:
                        normalized_exp['BusinessType'] = value
                    elif field_lower in ['number_of_employees', 'employee_count', 'size']:
                        normalized_exp['NumberOfEmployees'] = value
                    elif field_lower in ['funding_received', 'funding', 'investment']:
                        normalized_exp['Funding'] = value
                    elif field_lower in ['company_location', 'location']:
                        normalized_exp['Location'] = value
                    else:
                        normalized_exp[field] = value
                
                normalized_data[experience_key][i] = normalized_exp
            
            # Rename the key to standard name
            if experience_key != 'Experience':
                normalized_data['Experience'] = normalized_data.pop(experience_key)
        
        # Normalize nested fields in Education
        education_key = None
        for key in ['Education', 'education', 'education_details', 'educational_background', 'academic_background', 'academic_details']:
            if key in normalized_data:
                education_key = key
                break
                
        if education_key and isinstance(normalized_data[education_key], list):
            for i, edu in enumerate(normalized_data[education_key]):
                normalized_edu = {}
                for field, value in edu.items():
                    field_lower = field.lower()
                    
                    # Map education fields
                    if field_lower in ['college_university_name', 'university', 'college', 'institution', 'school']:
                        normalized_edu['CollegeUniversity'] = value
                    elif field_lower in ['course_degree', 'degree', 'qualification', 'course', 'program']:
                        normalized_edu['CourseDegree'] = value
                    elif field_lower in ['graduation_year', 'year', 'completion_year', 'year_of_graduation']:
                        normalized_edu['GraduationYear'] = value
                    else:
                        normalized_edu[field] = value
                
                normalized_data[education_key][i] = normalized_edu
            
            # Rename the key to standard name
            if education_key != 'Education':
                normalized_data['Education'] = normalized_data.pop(education_key)
        
        # Ensure all standard fields exist
        for field in standard_fields:
            if field not in normalized_data:
                # Try to find a field that might contain this information
                found = False
                for key in data.keys():
                    if key.lower() in field_mappings and field_mappings[key.lower()] == field:
                        normalized_data[field] = data[key]
                        found = True
                        break
                
                if not found:
                    # Add empty placeholder if completely missing
                    if field == 'Skills':
                        normalized_data[field] = []
                    elif field in ['Experience', 'Education']:
                        normalized_data[field] = []
                    else:
                        normalized_data[field] = "Not found"
        
        # Copy any remaining metadata fields
        for field in data:
            if field not in field_mappings.keys() and field not in normalized_data:
                normalized_data[field] = data[field]
                
        return normalized_data
    
    def _parse_duration(self, duration_string):
        """Parse duration string into structured start and end dates"""
        if not duration_string:
            return {"StartDate": "Not specified", "EndDate": "Not specified"}
            
        try:
            # Common formats: "Jan 2020 - Present", "2018-2020", "Mar 2019 to Dec 2021"
            duration_string = duration_string.replace('–', '-')  # Standardize dash
            
            if ' to ' in duration_string:
                parts = duration_string.split(' to ')
            elif ' - ' in duration_string:
                parts = duration_string.split(' - ')
            elif '-' in duration_string:
                parts = duration_string.split('-')
            else:
                return {"StartDate": duration_string, "EndDate": "Not specified"}
            
            if len(parts) == 2:
                return {"StartDate": parts[0].strip(), "EndDate": parts[1].strip()}
            else:
                return {"StartDate": duration_string, "EndDate": "Not specified"}
        except:
            return {"StartDate": duration_string, "EndDate": "Not specified"}
    
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
        
        Format your response as a JSON object with the following structure:
        {
          "CandidateFullName": "string",
          "EmailAddress": "string",
          "PhoneNumber": "string",
          "Skills": ["skill1", "skill2", ...],
          "Experience": [
            {
              "CompanyName": "string",
              "Position": "string",
              "Duration": {
                "StartDate": "string",
                "EndDate": "string"
              },
              "CompanyType": "string",
              "BusinessType": "string",
              "NumberOfEmployees": "string or null",
              "Funding": "string or null",
              "Location": "string"
            }
          ],
          "Education": [
            {
              "CollegeUniversity": "string",
              "CourseDegree": "string",
              "GraduationYear": "string"
            }
          ],
          "StabilityAssessment": "string"
        }
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
            
            # Normalize the fields to ensure consistency
            parsed_data = self._normalize_resume_fields(parsed_data)
            
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
    
    def _normalize_jd_fields(self, data):
        """Normalize field names in job description data to ensure consistency"""
        normalized_data = {}
        
        # Define field mappings (from possible GPT variations -> standard field)
        field_mappings = {
            # Job title variations
            'job_title': 'JobTitle',
            'Job title': 'JobTitle',
            'title': 'JobTitle',
            'position': 'JobTitle',
            'role': 'JobTitle',
            
            # Skills variations
            'Required skills': 'RequiredSkills',
            'skills': 'RequiredSkills',
            'required_skills': 'RequiredSkills',
            'skill_requirements': 'RequiredSkills',
            'technical_skills': 'RequiredSkills',
            
            # Experience variations
            'Years of experience required': 'YearsOfExperienceRequired',
            'experience': 'YearsOfExperienceRequired',
            'experience_required': 'YearsOfExperienceRequired',
            'years_of_experience': 'YearsOfExperienceRequired',
            
            # Education variations
            'Education requirements': 'EducationRequirements',
            'education': 'EducationRequirements',
            'education_requirements': 'EducationRequirements',
            'qualification': 'EducationRequirements',
            
            # Company type variations
            'Company type preference': 'CompanyTypePreference',
            'company_type': 'CompanyTypePreference',
            'company_type_preference': 'CompanyTypePreference',
            
            # Business type variations
            'Business type preference': 'BusinessTypePreference',
            'business_type': 'BusinessTypePreference',
            'business_type_preference': 'BusinessTypePreference',
            
            # Stability variations
            'Preferred stability': 'PreferredStability',
            'stability': 'PreferredStability',
            'preferred_stability': 'PreferredStability',
            
            # Other requirements variations
            'Other important requirements': 'OtherImportantRequirements',
            'other_requirements': 'OtherImportantRequirements',
            'additional_requirements': 'OtherImportantRequirements',
            'other': 'OtherImportantRequirements'
        }
        
        # Standard fields that should be included
        standard_fields = [
            'JobTitle',
            'RequiredSkills',
            'YearsOfExperienceRequired',
            'EducationRequirements',
            'CompanyTypePreference',
            'BusinessTypePreference',
            'PreferredStability',
            'OtherImportantRequirements'
        ]
        
        # Normalize the main fields
        for field, value in data.items():
            field_lower = field.lower()
            
            # Find the standardized field name
            normalized_field = None
            for possible_field, standard_field in field_mappings.items():
                if field == possible_field or field_lower == possible_field.lower():
                    normalized_field = standard_field
                    break
            
            if normalized_field:
                # Handle special case for RequiredSkills which might be nested
                if normalized_field == 'RequiredSkills' and isinstance(value, dict):
                    # If skills are separated by technical/soft
                    skills = []
                    for skill_type, skill_list in value.items():
                        if isinstance(skill_list, list):
                            skills.extend(skill_list)
                        elif isinstance(skill_list, str):
                            skills.append(skill_list)
                    
                    # Create standardized structure with technical and soft skills
                    normalized_data[normalized_field] = {
                        'technical': [],
                        'soft': []
                    }
                    
                    # Try to categorize skills into technical and soft
                    for skill in skills:
                        # This is a simple heuristic and might need improvement
                        technical_indicators = ['python', 'java', 'c++', 'machine learning', 'data', 'cloud', 
                                              'database', 'sql', 'nosql', 'tensorflow', 'pytorch', 'docker', 
                                              'kubernetes', 'aws', 'gcp', 'azure', 'programming', 'coding', 
                                              'development', 'algorithm', 'deep learning', 'nlp', 'computer vision',
                                              'mlops', 'devops', 'framework']
                        
                        is_technical = any(indicator in skill.lower() for indicator in technical_indicators)
                        
                        if is_technical:
                            normalized_data[normalized_field]['technical'].append(skill)
                        else:
                            normalized_data[normalized_field]['soft'].append(skill)
                    
                elif normalized_field == 'RequiredSkills' and isinstance(value, list):
                    # If skills are in a simple list
                    normalized_data[normalized_field] = {
                        'technical': [],
                        'soft': []
                    }
                    
                    # Try to categorize skills
                    for skill in value:
                        technical_indicators = ['python', 'java', 'c++', 'machine learning', 'data', 'cloud', 
                                              'database', 'sql', 'nosql', 'tensorflow', 'pytorch', 'docker', 
                                              'kubernetes', 'aws', 'gcp', 'azure', 'programming', 'coding', 
                                              'development', 'algorithm', 'deep learning', 'nlp', 'computer vision',
                                              'mlops', 'devops', 'framework']
                        
                        is_technical = any(indicator in skill.lower() for indicator in technical_indicators)
                        
                        if is_technical:
                            normalized_data[normalized_field]['technical'].append(skill)
                        else:
                            normalized_data[normalized_field]['soft'].append(skill)
                else:
                    normalized_data[normalized_field] = value
            else:
                # Keep original field if no mapping exists
                normalized_data[field] = value
        
        # Ensure all standard fields exist
        for field in standard_fields:
            if field not in normalized_data:
                if field == 'RequiredSkills':
                    normalized_data[field] = {
                        'technical': [],
                        'soft': []
                    }
                elif field == 'OtherImportantRequirements':
                    normalized_data[field] = []
                else:
                    normalized_data[field] = None
        
        # Copy any remaining metadata fields
        for field in data:
            if field.lower() not in [key.lower() for key in field_mappings] and field not in normalized_data:
                normalized_data[field] = data[field]
        
        return normalized_data
    
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
        
        Format your response as a JSON object with the following structure:
        {
          "JobTitle": "string",
          "RequiredSkills": {
            "technical": ["skill1", "skill2", ...],
            "soft": ["skill1", "skill2", ...]
          },
          "YearsOfExperienceRequired": "string",
          "EducationRequirements": "string",
          "CompanyTypePreference": "string or null",
          "BusinessTypePreference": "string or null",
          "PreferredStability": "string or null",
          "OtherImportantRequirements": ["requirement1", "requirement2", ...]
        }
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
            
            # Normalize the fields to ensure consistency
            parsed_data = self._normalize_jd_fields(parsed_data)
            
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
    
    def _normalize_match_analysis(self, data):
        """Normalize field names in match analysis to ensure consistency"""
        normalized_data = {}
        
        # Define field mappings (from possible GPT variations -> standard field)
        field_mappings = {
            # Suggested role variations
            "1. Suggested role for the candidate": "SuggestedRole",
            "Suggested role": "SuggestedRole",
            "Role suggestion": "SuggestedRole",
            "Best role": "SuggestedRole",
            "1. Suggested role": "SuggestedRole",
            "suggested_role": "SuggestedRole",
            
            # Match score variations
            "2. Match score": "MatchScore",
            "Match score": "MatchScore",
            "Score": "MatchScore",
            "2. Score": "MatchScore",
            "match_score": "MatchScore",
            
            # Shortlist variations
            "3. Whether the candidate should be shortlisted": "ShouldBeShortlisted",
            "Should be shortlisted": "ShouldBeShortlisted",
            "Shortlist": "ShouldBeShortlisted",
            "3. Shortlist recommendation": "ShouldBeShortlisted",
            "shortlist_recommendation": "ShouldBeShortlisted",
            
            # Company type match variations
            "4. Company type match": "CompanyTypeMatch",
            "Company type match": "CompanyTypeMatch",
            "Company match": "CompanyTypeMatch",
            "4. Company match": "CompanyTypeMatch",
            "company_type_match": "CompanyTypeMatch",
            
            # Business type match variations
            "5. Business type match": "BusinessTypeMatch",
            "Business type match": "BusinessTypeMatch",
            "Business match": "BusinessTypeMatch",
            "5. Business match": "BusinessTypeMatch",
            "business_type_match": "BusinessTypeMatch",
            
            # Stability assessment variations
            "6. Stability assessment": "StabilityAssessment",
            "Stability assessment": "StabilityAssessment",
            "Stability": "StabilityAssessment",
            "6. Stability": "StabilityAssessment",
            "stability_assessment": "StabilityAssessment",
            
            # Company analysis variations
            "7. Analysis of each company in the candidate's resume": "CompanyAnalysis",
            "Company analysis": "CompanyAnalysis",
            "Analysis of companies": "CompanyAnalysis",
            "7. Company analysis": "CompanyAnalysis",
            "company_analysis": "CompanyAnalysis",
            
            # Education assessment variations
            "8. Education assessment": "EducationAssessment",
            "Education assessment": "EducationAssessment",
            "Education": "EducationAssessment",
            "8. Education": "EducationAssessment",
            "education_assessment": "EducationAssessment",
            
            # Overall rating variations
            "9. Overall rating": "OverallRating",
            "Overall rating": "OverallRating",
            "Rating": "OverallRating",
            "9. Rating": "OverallRating",
            "overall_rating": "OverallRating",
            
            # Missing expectations variations
            "10. Anything missing as per expectations in the JD": "MissingExpectations",
            "Anything missing": "MissingExpectations",
            "Missing skills": "MissingExpectations",
            "10. Missing skills": "MissingExpectations",
            "missing_expectations": "MissingExpectations",
            
            # Overall recommendation variations
            "11. Overall recommendation": "OverallRecommendation",
            "Overall recommendation": "OverallRecommendation",
            "Recommendation": "OverallRecommendation",
            "11. Recommendation": "OverallRecommendation",
            "overall_recommendation": "OverallRecommendation"
        }
        
        # Standard fields that should be included
        standard_fields = [
            "SuggestedRole",
            "MatchScore", 
            "ShouldBeShortlisted",
            "CompanyTypeMatch",
            "BusinessTypeMatch",
            "StabilityAssessment",
            "CompanyAnalysis",
            "EducationAssessment",
            "OverallRating",
            "MissingExpectations",
            "OverallRecommendation"
        ]
        
        # Normalize the main fields
        for field, value in data.items():
            # Handle fields that start with numbers or special cases
            normalized_field = None
            for possible_field, standard_field in field_mappings.items():
                if field == possible_field or field.lower() == possible_field.lower():
                    normalized_field = standard_field
                    break
            
            if normalized_field:
                normalized_data[normalized_field] = value
            else:
                # Keep original field if no mapping exists
                normalized_data[field] = value
        
        # Normalize nested fields in company analysis if it exists
        company_analysis_key = None
        for key in normalized_data.keys():
            if key == "CompanyAnalysis":
                company_analysis_key = key
                break
                
        if company_analysis_key and isinstance(normalized_data[company_analysis_key], list):
            for i, company in enumerate(normalized_data[company_analysis_key]):
                normalized_company = {}
                for field, value in company.items():
                    field_lower = field.lower()
                    
                    # Map company fields
                    if field_lower in ['companyname', 'company name', 'company', 'name']:
                        normalized_company['CompanyName'] = value
                    elif field_lower in ['company type', 'type']:
                        normalized_company['CompanyType'] = value
                    elif field_lower in ['industry sector', 'industry', 'sector']:
                        normalized_company['IndustrySector'] = value
                    elif field_lower in ['business model', 'business', 'model']:
                        normalized_company['BusinessModel'] = value
                    elif field_lower in ['notable achievements', 'achievements', 'accomplishments']:
                        normalized_company['NotableAchievements'] = value
                    else:
                        normalized_company[field] = value
                
                normalized_data[company_analysis_key][i] = normalized_company
        
        # Normalize education assessment if it exists
        education_key = None
        for key in normalized_data.keys():
            if key == "EducationAssessment":
                education_key = key
                break
                
        if education_key and isinstance(normalized_data[education_key], dict):
            normalized_edu = {}
            for field, value in normalized_data[education_key].items():
                field_lower = field.lower()
                
                # Map education assessment fields
                if field_lower in ['college/university assessment', 'university assessment', 'college assessment']:
                    normalized_edu['UniversityAssessment'] = value
                elif field_lower in ['course relevance', 'degree relevance', 'education relevance']:
                    normalized_edu['CourseRelevance'] = value
                else:
                    normalized_edu[field] = value
            
            normalized_data[education_key] = normalized_edu
        
        # Ensure all standard fields exist with appropriate default values
        for field in standard_fields:
            if field not in normalized_data:
                if field == "MatchScore" or field == "OverallRating":
                    normalized_data[field] = 0
                elif field == "ShouldBeShortlisted":
                    normalized_data[field] = "No"
                elif field == "CompanyAnalysis":
                    normalized_data[field] = []
                elif field == "EducationAssessment":
                    normalized_data[field] = {
                        "UniversityAssessment": "Not provided",
                        "CourseRelevance": "Not provided"
                    }
                elif field == "MissingExpectations":
                    normalized_data[field] = []
                else:
                    normalized_data[field] = "Not provided"
        
        # Ensure numeric fields are actually numbers
        if "MatchScore" in normalized_data and not isinstance(normalized_data["MatchScore"], (int, float)):
            try:
                normalized_data["MatchScore"] = int(normalized_data["MatchScore"])
            except (ValueError, TypeError):
                try:
                    # Try to extract a number from a string like "7 out of 10"
                    import re
                    match = re.search(r'(\d+)', str(normalized_data["MatchScore"]))
                    if match:
                        normalized_data["MatchScore"] = int(match.group(1))
                    else:
                        normalized_data["MatchScore"] = 0
                except:
                    normalized_data["MatchScore"] = 0
        
        if "OverallRating" in normalized_data and not isinstance(normalized_data["OverallRating"], (int, float)):
            try:
                normalized_data["OverallRating"] = int(normalized_data["OverallRating"])
            except (ValueError, TypeError):
                try:
                    # Try to extract a number from a string like "7 out of 10"
                    import re
                    match = re.search(r'(\d+)', str(normalized_data["OverallRating"]))
                    if match:
                        normalized_data["OverallRating"] = int(match.group(1))
                    else:
                        normalized_data["OverallRating"] = 0
                except:
                    normalized_data["OverallRating"] = 0
        
        # Copy any remaining metadata fields
        for field in data:
            if field not in field_mappings and field not in normalized_data:
                normalized_data[field] = data[field]
        
        # Ensure ShouldBeShortlisted is Yes/No 
        if "ShouldBeShortlisted" in normalized_data:
            value = str(normalized_data["ShouldBeShortlisted"]).lower()
            if value in ["yes", "true", "1", "y", "recommended", "strongly recommended"]:
                normalized_data["ShouldBeShortlisted"] = "Yes"
            elif value in ["no", "false", "0", "n", "not recommended"]:
                normalized_data["ShouldBeShortlisted"] = "No"
            # If it doesn't match any of these, keep the original value
                
        return normalized_data

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
           - Company name
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
        
        Format your response as a JSON object with the following structure:
        {
          "SuggestedRole": "string",
          "MatchScore": number,
          "ShouldBeShortlisted": "Yes/No",
          "CompanyTypeMatch": "string",
          "BusinessTypeMatch": "string",
          "StabilityAssessment": "string",
          "CompanyAnalysis": [
            {
              "CompanyName": "string",
              "CompanyType": "string",
              "IndustrySector": "string",
              "BusinessModel": "string",
              "NotableAchievements": "string"
            }
          ],
          "EducationAssessment": {
            "UniversityAssessment": "string",
            "CourseRelevance": "string"
          },
          "OverallRating": number,
          "MissingExpectations": ["string"],
          "OverallRecommendation": "string"
        }
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
            
            # Normalize the fields to ensure consistency
            analysis = self._normalize_match_analysis(analysis)
            
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
        candidate_fullname = resume_data.get('CandidateFullName', '')
        candidate_email_data = resume_data.get('EmailAddress', '')
        candidate_phone_data = resume_data.get('PhoneNumber', '')
        
        if (candidate_name and candidate_name.lower() != candidate_fullname.lower()) or \
           (candidate_email and candidate_email.lower() != candidate_email_data.lower()) or \
           (candidate_phone and candidate_phone != candidate_phone_data):
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
        self.logger.info(f"Updated status for candidate {candidate_fullname}: {update_info}")
        
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