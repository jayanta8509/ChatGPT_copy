import os
import openai
from dotenv import load_dotenv
import logging
import json
import PyPDF2
import docx
import datetime
import requests
import re

# Load environment variables
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")
google_search_api_key = os.getenv("GOOGLE_SEARCH_API_KEY")
google_search_engine_id = os.getenv("GOOGLE_SEARCH_ENGINE_ID")

class ResumeParsingBot:
    def __init__(self, enrich_company_info=True):
        self.logger = self._setup_logger()
        self.enrich_company_info = enrich_company_info
        
    def _setup_logger(self):
        logger = logging.getLogger("resume_parser")
        logger.setLevel(logging.INFO)
        handler = logging.FileHandler("resume_parser.log")
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        return logger
    
    def _fetch_company_info(self, company_name):
        """Fetch company information using Google Search API"""
        if not company_name or company_name.strip() == "":
            return {}
        
        # Handle well-known companies with predefined information
        known_companies = {
            "amazon": {
                "BusinessType": "B2C/B2B",
                "NumberOfEmployees": "1,500,000+",
                "CompanyRevenue": "$513B annually (2023)",
                "Funding": "Public company (NASDAQ: AMZN), IPO 1997"
            },
            "google": {
                "BusinessType": "B2C/B2B",
                "NumberOfEmployees": "180,000+",
                "CompanyRevenue": "$280B annually (2023)",
                "Funding": "Public company (NASDAQ: GOOGL), IPO 2004"
            },
            "microsoft": {
                "BusinessType": "B2B/B2C",
                "NumberOfEmployees": "220,000+",
                "CompanyRevenue": "$200B annually (2023)",
                "Funding": "Public company (NASDAQ: MSFT), IPO 1986"
            },
            "meta": {
                "BusinessType": "B2C/B2B",
                "NumberOfEmployees": "87,000+",
                "CompanyRevenue": "$120B annually (2023)",
                "Funding": "Public company (NASDAQ: META), IPO 2012"
            },
            "apple": {
                "BusinessType": "B2C/B2B",
                "NumberOfEmployees": "165,000+",
                "CompanyRevenue": "$390B annually (2023)",
                "Funding": "Public company (NASDAQ: AAPL), IPO 1980"
            },
            "moneyview": {
                "BusinessType": "B2C",
                "NumberOfEmployees": "500-1000",
                "CompanyRevenue": "Rs 577 crore annually",
                "Funding": "Series E, $75M raised"
            },
            "flipkart": {
                "BusinessType": "B2C",
                "NumberOfEmployees": "50,000+",
                "CompanyRevenue": "$20B+ GMV annually",
                "Funding": "Private, $37B valuation"
            },
            "zomato": {
                "BusinessType": "B2C/B2B",
                "NumberOfEmployees": "5,000+",
                "CompanyRevenue": "Rs 4,200 crore annually",
                "Funding": "Public company (NSE: ZOMATO), IPO 2021"
            },
            "paytm": {
                "BusinessType": "B2C/B2B",
                "NumberOfEmployees": "8,000+",
                "CompanyRevenue": "Rs 5,000+ crore annually",
                "Funding": "Public company (NSE: PAYTM), IPO 2021"
            }
        }
        
        # Check if this is a well-known company
        company_lower = company_name.lower().strip()
        
        # Check for Amazon variations
        if any(term in company_lower for term in ["amazon", "amzn"]):
            self.logger.info(f"Using predefined info for Amazon: {company_name}")
            return known_companies["amazon"]
        
        # Check for other known companies
        for known_name, company_data in known_companies.items():
            if known_name in company_lower:
                self.logger.info(f"Using predefined info for well-known company: {company_name}")
                return company_data
        
        try:
            # Google Search API configuration
            api_key = google_search_api_key
            search_engine_id = google_search_engine_id
            base_url = "https://www.googleapis.com/customsearch/v1"
            
            # Multiple search queries for better coverage
            search_queries = [
                f"{company_name} company employees headcount workforce size",
                f"{company_name} annual revenue earnings financial results",
                f"{company_name} business model B2B B2C customers enterprise consumer",
                f"{company_name} funding valuation series round IPO public private",
                f"{company_name} company profile about overview"
            ]
            
            all_search_text = ""
            
            for query in search_queries:
                try:
                    params = {
                        'key': api_key,
                        'cx': search_engine_id,
                        'q': query,
                        'num': 3,  # Fewer results per query but more queries
                        'safe': 'active'
                    }
                    
                    self.logger.info(f"Searching: {query}")
                    
                    response = requests.get(base_url, params=params, timeout=15)
                    response.raise_for_status()
                    
                    search_data = response.json()
                    
                    # Extract text from search results
                    items = search_data.get('items', [])
                    for item in items:
                        all_search_text += f"Title: {item.get('title', '')}\n"
                        all_search_text += f"Snippet: {item.get('snippet', '')}\n"
                        # Also include formatted URL as it might contain company info
                        if item.get('formattedUrl'):
                            all_search_text += f"URL: {item.get('formattedUrl', '')}\n"
                        all_search_text += "\n"
                    
                except Exception as e:
                    self.logger.warning(f"Search query failed: {query} - {str(e)}")
                    continue
            
            if not all_search_text:
                self.logger.warning(f"No search results found for company: {company_name}")
                return {}
            
            # Use GPT-4o to extract company information from search results
            system_prompt = """
            You are an expert company research analyst. Extract the following information from the search results about a company.
            Be thorough and look for specific numbers, funding details, and business model indicators.
            
            Extract:
            1. Business Type: Determine the company's business model:
               - B2B: Primarily sells to businesses
               - B2C: Primarily sells to consumers  
               - B2C/B2B: Consumer-focused but also serves businesses (like Amazon: retail + AWS)
               - B2B/B2C: Business-focused but also serves consumers (like Microsoft: enterprise + Xbox)
               - B2B2C: Platform connecting businesses to consumers
            2. Number of Employees: Look for headcount, team size, workforce numbers (prefer specific numbers or ranges)
            3. Company Revenue: Annual revenue, ARR, sales figures (look for $ amounts)
            4. Funding: Funding rounds (Seed, Series A/B/C/D, IPO), total funding raised, valuation, investors
            
            SPECIAL INSTRUCTIONS FOR KNOWN COMPANIES:
            - Amazon: Use "B2C/B2B" (retail + AWS), ~1.5M employees, ~$500B+ revenue
            - Google/Alphabet: Use "B2C/B2B" (search + cloud), ~180K employees, ~$280B revenue
            - Microsoft: Use "B2B/B2C" (enterprise + consumer), ~220K employees, ~$200B revenue
            - Meta/Facebook: Use "B2C/B2B" (social + business tools), ~87K employees, ~$120B revenue
            - Apple: Use "B2C/B2B" (consumer + enterprise), ~165K employees, ~$390B revenue
            
            GUIDELINES:
            - For companies with multiple business lines, use combined format: "B2C/B2B" or "B2B/B2C"
            - Put the PRIMARY business model first, then secondary with slash separator
            - For employee count: Look for recent numbers, use ranges if exact unknown (e.g., "500-1000", "10,000+")
            - For revenue: Include timeframe and source (e.g., "$50M ARR", "$1.2B annually (2023)")
            - For funding: Be specific about stage and amount (e.g., "Series B, $25M raised")
            - If search results are limited, use your knowledge of well-known companies
            - For startups/smaller companies, be more conservative but still extract available info
            - Never leave fields as "Not specified" if you can reasonably estimate or find partial information
            
            Examples of what to look for:
            - Employee count: "team of 500", "workforce 1000+", "hiring 200 people", "startup with 50 employees"
            - Revenue: "revenue of $10M", "$50M ARR", "unicorn valued at $1B", "profitable company"
            - Business model: Look for customers mentioned (consumers vs businesses), product descriptions
            
            Format your response as a JSON object:
            {
              "BusinessType": "B2B/B2C/B2B2C or combinations like B2C/B2B",
              "NumberOfEmployees": "specific number or range (avoid 'Not specified')",
              "CompanyRevenue": "specific revenue figure with timeframe (avoid 'Not specified')",
              "Funding": "funding stage and amount or public status (avoid 'Not specified')"
            }
            
            Only use "Not specified" if you genuinely cannot find, estimate, or infer any information after thorough analysis.
            """
            
            gpt_response = openai.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Company: {company_name}\n\nSearch results from multiple queries:\n{all_search_text[:8000]}"}  # Limit text to avoid token limits
                ],
                response_format={"type": "json_object"}
            )
            
            company_info = json.loads(gpt_response.choices[0].message.content)
            self.logger.info(f"Successfully extracted company info for {company_name}: {company_info}")
            
            return company_info
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Network error while fetching company info for {company_name}: {str(e)}")
            return {}
        except Exception as e:
            self.logger.error(f"Error fetching company info for {company_name}: {str(e)}")
            return {}
    
    def _enrich_experience_with_company_info(self, experience_list):
        """Enrich experience entries with company information from Google Search"""
        if not experience_list or not isinstance(experience_list, list):
            return experience_list
        
        enriched_experience = []
        
        for exp in experience_list:
            enriched_exp = exp.copy()
            company_name = exp.get("CompanyName", "")
            
            # Check if company data is missing, null, or "Not specified"
            def needs_enrichment(value):
                return (value is None or 
                       value == "Not specified" or 
                       value == "" or 
                       str(value).strip() == "")
            
            needs_info = (
                needs_enrichment(exp.get("BusinessType")) or
                needs_enrichment(exp.get("NumberOfEmployees")) or
                needs_enrichment(exp.get("CompanyRevenue")) or
                needs_enrichment(exp.get("Funding")) or
                needs_enrichment(exp.get("CompanyType"))
            )
            
            if company_name and needs_info:
                self.logger.info(f"Fetching company info for: {company_name}")
                company_info = self._fetch_company_info(company_name)
                
                # Update fields if they need enrichment and we found better info
                if needs_enrichment(exp.get("BusinessType")) and company_info.get("BusinessType") and company_info.get("BusinessType") != "Not specified":
                    enriched_exp["BusinessType"] = company_info["BusinessType"]
                
                if needs_enrichment(exp.get("NumberOfEmployees")) and company_info.get("NumberOfEmployees") and company_info.get("NumberOfEmployees") != "Not specified":
                    enriched_exp["NumberOfEmployees"] = company_info["NumberOfEmployees"]
                
                if needs_enrichment(exp.get("CompanyRevenue")) and company_info.get("CompanyRevenue") and company_info.get("CompanyRevenue") != "Not specified":
                    enriched_exp["CompanyRevenue"] = company_info["CompanyRevenue"]
                
                if needs_enrichment(exp.get("Funding")) and company_info.get("Funding") and company_info.get("Funding") != "Not specified":
                    enriched_exp["Funding"] = company_info["Funding"]
                
                # Infer CompanyType if missing
                if needs_enrichment(exp.get("CompanyType")):
                    # Infer based on business type or company name
                    if "amazon" in company_name.lower():
                        enriched_exp["CompanyType"] = "Product"
                    elif "google" in company_name.lower() or "microsoft" in company_name.lower():
                        enriched_exp["CompanyType"] = "Product"
                    elif company_info.get("BusinessType"):
                        # Most B2C companies are Product companies, most B2B are often Service
                        business_type = company_info.get("BusinessType", "")
                        if "B2C" in business_type:
                            enriched_exp["CompanyType"] = "Product"
                        else:
                            enriched_exp["CompanyType"] = "Service"
                
                # Also force update Amazon's BusinessType if it's wrong
                if "amazon" in company_name.lower() and exp.get("BusinessType") == "B2C":
                    enriched_exp["BusinessType"] = "B2C/B2B"
                    self.logger.info(f"Force updated Amazon BusinessType to B2C/B2B")
                
                # Log what was updated
                updated_fields = []
                for field in ["CompanyType", "BusinessType", "NumberOfEmployees", "CompanyRevenue", "Funding"]:
                    if enriched_exp.get(field) != exp.get(field):
                        updated_fields.append(field)
                
                if updated_fields:
                    self.logger.info(f"Updated {company_name} fields: {', '.join(updated_fields)}")
                else:
                    self.logger.info(f"No new information found for {company_name}")
            
            enriched_experience.append(enriched_exp)
        
        return enriched_experience
    
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
                    if field_lower in ['companyname', 'company name', 'company']:
                        normalized_exp['CompanyName'] = value
                    elif field_lower in ['position', 'role', 'job_title', 'title']:
                        normalized_exp['Position'] = value
                    elif field_lower in ['duration', 'period', 'tenure']:
                        # Check if duration is already structured
                        if isinstance(value, dict):
                            # Check for variations of start/end date keys
                            has_start_key = False
                            has_end_key = False
                            
                            normalized_duration = {}
                            for dk, dv in value.items():
                                try:
                                    dk_lower = dk.lower()  # Make sure dk is a string
                                    if 'start' in dk_lower:
                                        normalized_duration['StartDate'] = dv
                                        has_start_key = True
                                    elif 'end' in dk_lower:
                                        normalized_duration['EndDate'] = dv
                                        has_end_key = True
                                    else:
                                        normalized_duration[dk] = dv
                                except AttributeError:
                                    # If the key is not a string, use it as is
                                    normalized_duration[dk] = dv
                            
                            # Ensure the standard keys exist
                            if not has_start_key:
                                normalized_duration['StartDate'] = "Not specified"
                            if not has_end_key:
                                normalized_duration['EndDate'] = "Not specified"
                                
                            normalized_exp['Duration'] = normalized_duration
                        else:
                            # Try to parse the duration string
                            normalized_exp['Duration'] = self._parse_duration(value)
                    elif field_lower in ['product_or_service', 'company_type', 'companytype', 'type of company']:
                        normalized_exp['CompanyType'] = value
                    elif field_lower in ['business_type', 'businesstype', 'business model']:
                        normalized_exp['BusinessType'] = value
                    elif field_lower in ['number_of_employees', 'employee_count', 'size', 'company size', 'employees']:
                        normalized_exp['NumberOfEmployees'] = value
                    elif field_lower in ['company_revenue', 'revenue', 'turnover', 'annual revenue']:
                        normalized_exp['CompanyRevenue'] = value
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
            
            # Check for date ranges
            if ' to ' in duration_string:
                parts = duration_string.split(' to ')
            elif ' - ' in duration_string:
                parts = duration_string.split(' - ')
            elif '-' in duration_string:
                # Be careful with date formats like "Jan-2020" which shouldn't be split
                if not any(month in duration_string.lower() for month in 
                          ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec']):
                    parts = duration_string.split('-')
                else:
                    # Check if there's a month-year pattern on both sides of the dash
                    import re
                    date_pattern = r'(?:[a-z]{3}|\d{1,2})[- ](?:\d{2}|\d{4})'
                    matches = re.findall(date_pattern, duration_string.lower())
                    if len(matches) >= 2:
                        # Try to split with a more specific pattern
                        parts_match = re.search(r'(.+) ?- ?(.+)', duration_string)
                        if parts_match:
                            parts = [parts_match.group(1).strip(), parts_match.group(2).strip()]
                        else:
                            return {"StartDate": duration_string, "EndDate": "Not specified"}
                    else:
                        return {"StartDate": duration_string, "EndDate": "Not specified"}
            else:
                return {"StartDate": duration_string, "EndDate": "Not specified"}
            
            if len(parts) == 2:
                start = parts[0].strip()
                end = parts[1].strip()
                
                # Check for "Present" or "Current" in end date
                if end.lower() in ['present', 'current', 'now', 'ongoing']:
                    end = "Present"
                
                return {"StartDate": start, "EndDate": end}
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
        2. Email address (check personal email, work emails, LinkedIn profiles)
        3. Phone number
        4. Skills (list all technical and soft skills)
        5. For each company experience:
           - Company name (LOOK CAREFULLY - check email domains, LinkedIn URLs, official company names, subsidiaries)
           - Position/role
           - Duration (specify EXACT start date and end date in the same format they appear in the resume)
           - Whether it's a product or service company (infer from company name and context if not explicit)
           - Business type (B2B or B2C - infer from company name and industry if not explicit)
           - Number of employees (if mentioned or can be inferred from company knowledge)
           - Company revenue or turnover (if mentioned)
           - Funding received and type of funding (if mentioned)
           - Company main location
        6. Education details:
           - College/University name
           - Course/degree
           - Graduation year
        7. Overall stability assessment (years staying in previous companies)
        
        IMPORTANT INSTRUCTIONS FOR COMPANY DETECTION:
        - Look for company names in work email addresses (e.g., @tcs.com suggests TCS)
        - Check LinkedIn URLs or profile mentions
        - Look for official company names, even if abbreviated (e.g., TCS = Tata Consultancy Services)
        - Identify subsidiaries and parent companies
        - If you recognize a company name, infer the company type and business type based on your knowledge
        
        COMPANY TYPE INFERENCE RULES:
        - TCS, Tata Consultancy Services, Infosys, Wipro, Accenture, Cognizant, IBM = Service companies
        - Amazon, Google, Microsoft, Apple, Meta, Netflix, Spotify = Product companies
        - Banks (JPMorgan, HDFC, ICICI), Consulting firms = Service companies
        - Software products, E-commerce, SaaS platforms, Gaming companies = Product companies
        - Startups with apps/platforms = Product companies
        - IT Services, Consulting, Outsourcing = Service companies
        
        BUSINESS TYPE INFERENCE RULES:
        - IT Services companies (TCS, Infosys, Wipro) = B2B
        - E-commerce (Amazon, Flipkart) = B2C/B2B
        - Enterprise software (Microsoft, Oracle) = B2B/B2C
        - Social media (Meta, Twitter) = B2C/B2B
        - Consumer products (Apple, Samsung) = B2C/B2B
        - Banking and Financial Services = B2C/B2B
        - Gaming companies = B2C
        - SaaS platforms = B2B
        
        FORMAT GUIDELINES:
        - For business type combinations: Primary model first, then secondary (e.g., "B2C/B2B" for consumer-first companies)
        - Use B2B for pure enterprise services
        - Use B2C for pure consumer services
        - Use combinations for mixed models
        
        Format your response as a JSON object with the following structure:
        {
          "CandidateFullName": "string",
          "EmailAddress": "string",
          "PhoneNumber": "string",
          "Skills": ["skill1", "skill2", ...],
          "Experience": [
            {
              "CompanyName": "string (extract carefully from any source)",
              "Position": "string",
              "Duration": {
                "StartDate": "string (EXACT as in resume)",
                "EndDate": "string (EXACT as in resume)"
              },
              "CompanyType": "Product/Service (infer if not explicit)",
              "BusinessType": "B2B/B2C/B2C/B2B/B2B2C (infer if not explicit)",
              "NumberOfEmployees": "string or null",
              "CompanyRevenue": "string or null",
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
        
        EXAMPLES OF INFERENCE:
        - If resume mentions "worked at TCS" → CompanyName: "TCS", CompanyType: "Service", BusinessType: "B2B"
        - If email is "john@amazon.com" → CompanyName: "Amazon", CompanyType: "Product", BusinessType: "B2C/B2B"
        - If mentions "Google India" → CompanyName: "Google", CompanyType: "Product", BusinessType: "B2C/B2B"
        - If mentions "JPMorgan Chase" → CompanyName: "JPMorgan Chase", CompanyType: "Service", BusinessType: "B2C/B2B"
        - If mentions "Flipkart" → CompanyName: "Flipkart", CompanyType: "Product", BusinessType: "B2C/B2B"
        
        IMPORTANT INSTRUCTIONS:
        1. Extract dates EXACTLY as they appear in the resume without reformatting
        2. For Duration, maintain the exact format from the resume (e.g., "Jan 2020 - Mar 2022", "2019-Present")
        3. If a field is not present or cannot be determined, use null rather than making assumptions
        4. However, for well-known companies, DO infer CompanyType and BusinessType based on your knowledge
        5. For company information like size and revenue, only include if explicitly mentioned
        6. Be aggressive about finding company names from any source in the resume
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
            
            # Enrich experience with company information from Google Search (if enabled)
            if self.enrich_company_info and "Experience" in parsed_data:
                parsed_data["Experience"] = self._enrich_experience_with_company_info(parsed_data["Experience"])
            
            # Calculate total years of experience
            total_experience = self._calculate_total_experience(parsed_data.get("Experience", []))
            parsed_data["TotalYearsOfExperience"] = total_experience
            
            # Add file information to the result
            file_name = os.path.basename(resume_file_path)
            parsed_data["resume_file"] = file_name
            parsed_data["upload_date"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
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
            # Company name variations
            'company_name': 'CompanyName',
            'company': 'CompanyName',
            'employer': 'CompanyName',
            'organization': 'CompanyName',
            # Job title variations
            'job_title': 'JobTitle',
            'Job title': 'JobTitle',
            'title': 'JobTitle',
            'position': 'JobTitle',
            'role': 'JobTitle',
            
            # Job location variations
            'job_location': 'JobLocation',
            'location': 'JobLocation',
            'work_location': 'JobLocation',
            'office_location': 'JobLocation',
            'workplace': 'JobLocation',
            
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
            'CompanyName',
            'JobTitle',
            'JobLocation',
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
                elif field == 'CompanyName':
                    normalized_data[field] = None
                elif field == 'JobLocation':
                    normalized_data[field] = None
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
        1. Company name (LOOK CAREFULLY - check email domains, headers, footers, "About us" sections, contact info, company references, brand mentions)
        2. Job title
        3. Job location (city, country, remote status)
        4. Required skills (technical and soft skills)
        5. Years of experience required
        6. Education requirements
        7. Company type preference (Product/Service - if not explicitly mentioned, infer from company name and context)
        8. Business type preference (B2B/B2C/combinations like B2C/B2B - if not mentioned, infer from company name and job context)
        9. Preferred stability (years in previous companies if mentioned)
        10. Other important requirements
        
        IMPORTANT INSTRUCTIONS FOR COMPANY DETECTION:
        - Look for company names in email addresses (e.g., @tcs.com suggests TCS)
        - Check headers, footers, letterheads, or signatures
        - Look for phrases like "About [Company]", "Join [Company]", "At [Company]"
        - Check for brand names, subsidiary names, or parent company references
        - If you find a company name, try to infer the company type and business type based on your knowledge
        
        COMPANY TYPE INFERENCE RULES:
        - TCS, Tata Consultancy Services, Infosys, Wipro, Accenture, Cognizant = Service companies
        - Amazon, Google, Microsoft, Apple, Meta, Netflix = Product companies
        - Banks, Consulting firms, IT Services = Service companies
        - Software products, E-commerce, SaaS platforms = Product companies
        
        BUSINESS TYPE INFERENCE RULES:
        - IT Services companies (TCS, Infosys) = B2B
        - E-commerce (Amazon retail) = B2C/B2B
        - Enterprise software (Microsoft) = B2B/B2C
        - Social media (Meta) = B2C/B2B
        - Consumer products (Apple) = B2C/B2B
        
        For business type, use these formats:
        - B2B: Primarily business-to-business
        - B2C: Primarily business-to-consumer
        - B2C/B2B: Consumer-focused with business operations
        - B2B/B2C: Business-focused with consumer operations
        - B2B2C: Platform model
        
        Format your response as a JSON object with the following structure:
        {
          "CompanyName": "string (extract from any source in JD) or null if genuinely not found",
          "JobTitle": "string",
          "JobLocation": "string",
          "RequiredSkills": {
            "technical": ["skill1", "skill2", ...],
            "soft": ["skill1", "skill2", ...]
          },
          "YearsOfExperienceRequired": "string",
          "EducationRequirements": "string",
          "CompanyTypePreference": "Product/Service (infer if not explicit) or null",
          "BusinessTypePreference": "B2B/B2C/B2C/B2B/B2B2C (infer if not explicit) or null",
          "PreferredStability": "string or null",
          "OtherImportantRequirements": ["requirement1", "requirement2", ...]
        }
        
        EXAMPLES OF INFERENCE:
        - If JD mentions "tcs.com" email → CompanyName: "TCS", CompanyTypePreference: "Service", BusinessTypePreference: "B2B"
        - If JD mentions "amazon.com" → CompanyName: "Amazon", CompanyTypePreference: "Product", BusinessTypePreference: "B2C/B2B"
        - If JD mentions "google.com" → CompanyName: "Google", CompanyTypePreference: "Product", BusinessTypePreference: "B2C/B2B"
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
            
            # Enrich company type preference with Google search if missing
            company_name = parsed_data.get("CompanyName")
            company_type_pref = parsed_data.get("CompanyTypePreference")
            
            # Check if company type preference needs enrichment
            def needs_enrichment(value):
                return (value is None or 
                       value == "Not specified" or 
                       value == "" or 
                       str(value).strip() == "" or
                       value == "null" or
                       str(value).lower() == "not mentioned")
            
            # Try to search for company info if company type is missing
            if needs_enrichment(company_type_pref) and self.enrich_company_info:
                # If no company name detected, try to extract it from JD text more aggressively
                if not company_name or company_name == "Not found":
                    # Use GPT to extract company name from JD text more aggressively
                    company_extraction_prompt = """
                    Extract the company name from this job description text. Look for:
                    - Company names mentioned anywhere in the text
                    - "About us" or "About the company" sections
                    - Email domains that might indicate company names
                    - Any brand names or organization names
                    
                    Return only the company name or "Not found" if no company is mentioned.
                    """
                    
                    try:
                        company_response = openai.chat.completions.create(
                            model="gpt-4o",
                            messages=[
                                {"role": "system", "content": company_extraction_prompt},
                                {"role": "user", "content": jd_text}
                            ]
                        )
                        extracted_company = company_response.choices[0].message.content.strip()
                        if extracted_company and extracted_company.lower() != "not found":
                            company_name = extracted_company
                            parsed_data["CompanyName"] = company_name
                            self.logger.info(f"Extracted company name from JD: {company_name}")
                    except Exception as e:
                        self.logger.warning(f"Failed to extract company name: {str(e)}")
                
                # Now search for company info if we have a company name
                if company_name and company_name != "Not found":
                    self.logger.info(f"Company type preference not found in JD. Searching for: {company_name}")
                    company_info = self._fetch_company_info(company_name)
                    
                    if company_info:
                        # Determine if it's a Product or Service company based on business type and known patterns
                        if "amazon" in company_name.lower():
                            parsed_data["CompanyTypePreference"] = "Product"
                        elif "google" in company_name.lower() or "microsoft" in company_name.lower() or "apple" in company_name.lower() or "meta" in company_name.lower():
                            parsed_data["CompanyTypePreference"] = "Product"
                        elif any(term in company_name.lower() for term in ["tcs", "tata consultancy", "tata consultancy services"]):
                            parsed_data["CompanyTypePreference"] = "Service"
                        elif company_info.get("BusinessType"):
                            # General heuristic: B2C companies are often Product companies
                            business_type = company_info.get("BusinessType", "")
                            if "B2C" in business_type:
                                parsed_data["CompanyTypePreference"] = "Product"
                            else:
                                # Most B2B companies can be either, but we'll default to Service unless specifically known
                                parsed_data["CompanyTypePreference"] = "Service"
                        
                        # Also update business type preference if missing
                        business_type_pref = parsed_data.get("BusinessTypePreference")
                        if needs_enrichment(business_type_pref) and business_type:
                            parsed_data["BusinessTypePreference"] = business_type
                            self.logger.info(f"Updated business type preference for {company_name}: {business_type}")
                        
                        if parsed_data.get("CompanyTypePreference") != company_type_pref:
                            self.logger.info(f"Updated company type preference for {company_name}: {parsed_data.get('CompanyTypePreference')}")
                    else:
                        self.logger.info(f"No company information found for {company_name}")
                else:
                    self.logger.info("No company name found in JD, cannot search for company type preference")
            
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
            
            # Match score variations - map to AIRating instead
            "2. Match score": "AIRating",
            "Match score": "AIRating",
            "Score": "AIRating",
            "2. Score": "AIRating",
            "match_score": "AIRating",
            
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
            
            # Overall rating variations - map to AIRating instead
            "9. Overall rating": "AIRating",
            "Overall rating": "AIRating",
            "Rating": "AIRating",
            "9. Rating": "AIRating",
            "overall_rating": "AIRating",
            
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
            "overall_recommendation": "OverallRecommendation",

            # AI Rating variations (in case it's directly provided)
            "AIRating": "AIRating",
            "AI Rating": "AIRating",
            "AI rating": "AIRating"
        }
        
        # Standard fields that should be included
        standard_fields = [
            "SuggestedRole",
            "AIRating", 
            "ShouldBeShortlisted",
            "CompanyTypeMatch",
            "BusinessTypeMatch",
            "StabilityAssessment",
            "CompanyAnalysis",
            "EducationAssessment",
            "MissingExpectations",
            "OverallRecommendation",
            "AIShortlisted", 
            "InternalShortlisted",
            "InterviewInProcess",
            "FinalResult",
            "CandidateJoined"
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
                # If it's a rating field and we already have a rating, take the higher value
                if normalized_field == "AIRating" and "AIRating" in normalized_data:
                    # Get the existing value
                    existing_value = normalized_data["AIRating"]
                    
                    # Try to convert both to numbers for comparison
                    try:
                        existing_numeric = float(existing_value) if existing_value is not None else 0
                        new_numeric = float(value) if value is not None else 0
                        
                        # Keep the higher value
                        normalized_data["AIRating"] = max(existing_numeric, new_numeric)
                    except (ValueError, TypeError):
                        # If conversion fails, keep the original
                        pass
                else:
                    normalized_data[normalized_field] = value
            else:
                # Skip MatchScore and OverallRating since we're consolidating
                if field.lower() not in ["matchscore", "overallrating"]:
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
                if field == "AIRating":
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
        if "AIRating" in normalized_data and not isinstance(normalized_data["AIRating"], (int, float)):
            try:
                normalized_data["AIRating"] = int(normalized_data["AIRating"])
            except (ValueError, TypeError):
                try:
                    # Try to extract a number from a string like "7 out of 10"
                    import re
                    match = re.search(r'(\d+)', str(normalized_data["AIRating"]))
                    if match:
                        normalized_data["AIRating"] = int(match.group(1))
                    else:
                        normalized_data["AIRating"] = 0
                except:
                    normalized_data["AIRating"] = 0
        
        # Remove MatchScore and OverallRating if they were added somehow
        if "MatchScore" in normalized_data:
            del normalized_data["MatchScore"]
            
        if "OverallRating" in normalized_data:
            del normalized_data["OverallRating"]
        
        # Copy any remaining metadata fields
        for field in data:
            if field.lower() not in [key.lower() for key in field_mappings] and field not in normalized_data:
                # Skip MatchScore and OverallRating
                if field.lower() not in ["matchscore", "overallrating"]:
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
        2. AI Rating (1-10) - a score that indicates how well the candidate matches the job
        3. Whether the candidate should be shortlisted (Yes/No)
        4. Company type match (Product/Service)
        5. Business type match (B2B/B2C/combinations - consider partial matches for mixed models)
        6. Stability assessment (comprehensive analysis based on multiple factors):
           - Individual tenure analysis: Calculate years spent at each company
           - Company-wise stability insights: Analyze each company's typical employee retention patterns
           - Industry stability benchmarks: Compare candidate's tenure against industry standards
           - Attrition pattern analysis: Look for trends in job transitions (frequency, timing, progression)
           - Company reputation for retention: Consider known attrition rates and employee satisfaction
           - Stability scoring: Rate overall career stability (1-10) with detailed reasoning (for internal analysis only)
           - Future stability prediction: Likelihood of staying long-term in the new role
           
           For company-wise insights, consider:
           - Large tech companies (Google, Microsoft, Amazon): Typically 2-4 years average tenure
           - Startups: Often 1-2 years due to high growth/pivot nature
           - Consulting firms (TCS, Infosys, Accenture): 2-3 years for early career, 4+ for senior roles
           - Financial services: Generally 3-5 years average tenure
           - Product companies: 2-4 years depending on company maturity
           - Service companies: 2-3 years average, higher for specialized roles
           
           Rate stability factors:
           - Excellent (9-10): 4+ years per company, logical career progression
           - Good (7-8): 2-4 years per company, clear growth trajectory
           - Average (5-6): 1-2 years per company, some job hopping but reasonable
           - Poor (3-4): <1 year per company, frequent changes without clear progression
           - Very Poor (1-2): Multiple short stints, concerning pattern of instability
           
           IMPORTANT: Do NOT include the numerical stability score in the final StabilityAssessment output. 
           Provide only the descriptive analysis without mentioning "Overall Stability Score" or any numerical rating.
           KEEP THE OUTPUT CONCISE: Limit StabilityAssessment to 2-3 lines maximum while covering key points:
           tenure analysis, industry benchmarks, career progression pattern, and future stability prediction.
        7. Analysis of each company in the candidate's resume:
           - Company name
           - Company type (Product/Service)
           - Industry sector
           - Business model (B2B/B2C/B2C/B2B/B2B2C)
           - Any notable achievements
        8. Education assessment:
           - College/University assessment
           - Course relevance
        9. Anything missing as per expectations in the JD
        10. Overall recommendation (detailed summary in 2-3 lines)
        11. Candidate status prediction:
           - Should be AI shortlisted (Yes/No)
           - Should be internally shortlisted (Yes/No)
           - Ready for interview process (Yes/No)
           - Final result prediction (Selected/Rejected/Pending)
           - Likelihood of joining if offered (High/Medium/Low)
        
        IMPORTANT: For business type matching:
        - B2C/B2B experience is compatible with B2B requirements
        - B2B/B2C experience is compatible with B2C requirements  
        - Combined models (B2C/B2B) show versatility and should be valued
        - Consider partial matches as positive (e.g., B2C/B2B candidate for B2B role = good match)
        
        COMPANY TYPE CLASSIFICATION GUIDANCE:
        For accurate company type classification, use the following guidelines:
        - Amazon, Google, Microsoft, Apple, Meta, Netflix: Product companies
        - Moneyview: Product company (fintech with lending products and financial services platform)
        - Flipkart, Zomato, Paytm, Swiggy: Product companies (platform/app-based)
        - TCS, Tata Consultancy Services, Infosys, Wipro, Accenture, Cognizant: Service companies
        - Banks (HDFC, ICICI, SBI), unless they have significant product divisions: Service companies
        - Startups with apps/platforms/SaaS products: Product companies
        - IT Services, Consulting, Outsourcing firms: Service companies
        
        When determining CompanyTypeMatch:
        - If all companies in candidate's experience are Product companies: "Product"
        - If all companies in candidate's experience are Service companies: "Service" 
        - If candidate has mixed experience (both Product and Service): "Product/Service"
        
        CRITICAL: Analyze the CompanyType field in the CompanyAnalysis section you generate. 
        If ALL companies show CompanyType as "Product", then CompanyTypeMatch MUST be "Product".
        If ALL companies show CompanyType as "Service", then CompanyTypeMatch MUST be "Service".
        Only use "Product/Service" when there's a genuine mix of Product and Service companies.
        
        Format your response as a JSON object with the following structure:
        {
          "SuggestedRole": "string",
          "AIRating": number,
          "ShouldBeShortlisted": "Yes/No",
          "CompanyTypeMatch": "string (MUST be 'Product' if all CompanyAnalysis entries are Product type, 'Service' if all are Service type, 'Product/Service' only for mixed experience)",
          "BusinessTypeMatch": "string (explain compatibility for mixed models)",
          "StabilityAssessment": "string (concise 2-3 lines covering tenure analysis, industry benchmarks, career progression, and future stability prediction)",
          "CompanyAnalysis": [
            {
              "CompanyName": "string",
              "CompanyType": "string",
              "IndustrySector": "string",
              "BusinessModel": "string (B2B/B2C/B2C/B2B/B2B2C)",
              "NotableAchievements": "string"
            }
          ],
          "EducationAssessment": {
            "UniversityAssessment": "string",
            "CourseRelevance": "string"
          },
          "MissingExpectations": ["string"],
          "OverallRecommendation": "string (detailed summary in 2-3 lines)",
          "AIShortlisted": "Yes/No",
          "InternalShortlisted": "Yes/No",
          "InterviewInProcess": "Yes/No",
          "FinalResult": "Selected/Rejected/Pending",
          "CandidateJoined": "Yes/No/Unknown"
        }
        
        For the candidate status prediction:
        - AIRating should be a number from 1-10 reflecting how well the candidate matches the job
        - AIShortlisted should be "Yes" if the AIRating is 7 or higher, otherwise "No"
        - InternalShortlisted should be your recommendation based on the candidate's fit
        - InterviewInProcess should be "Yes" if you recommend they proceed to interviews
        - FinalResult should be "Selected" if they're an excellent match, "Rejected" if poor match, "Pending" if moderate
        - CandidateJoined should be your prediction of whether they'd join if offered
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
            
            # Add AI status fields if not present
            if "AIRating" not in analysis:
                analysis["AIRating"] = 0
            
            if "AIShortlisted" not in analysis:
                # Default based on AIRating
                analysis["AIShortlisted"] = "Yes" if analysis.get("AIRating", 0) >= 7 else "No"
                
            if "InternalShortlisted" not in analysis:
                # Default based on ShouldBeShortlisted
                analysis["InternalShortlisted"] = analysis.get("ShouldBeShortlisted", "No")
                
            if "InterviewInProcess" not in analysis:
                # Default based on ShouldBeShortlisted
                analysis["InterviewInProcess"] = analysis.get("ShouldBeShortlisted", "No")
                
            if "FinalResult" not in analysis:
                # Default based on AIRating
                ai_rating = analysis.get("AIRating", 0)
                if ai_rating >= 8:
                    analysis["FinalResult"] = "Selected"
                elif ai_rating <= 4:
                    analysis["FinalResult"] = "Rejected"
                else:
                    analysis["FinalResult"] = "Pending"
                    
            if "CandidateJoined" not in analysis:
                # Default to unknown
                analysis["CandidateJoined"] = "Unknown"
            
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
    
    def _calculate_total_experience(self, experience_list):
        """Calculate total years of experience from the experience list"""
        if not experience_list or not isinstance(experience_list, list):
            return 0.0
            
        total_years = 0.0
        
        for exp in experience_list:
            # Extract duration information
            duration = exp.get("Duration", {})
            if not duration or not isinstance(duration, dict):
                continue
                
            start_date = duration.get("StartDate", "")
            end_date = duration.get("EndDate", "")
            
            # Skip if either date is missing
            if not start_date or not end_date:
                continue
                
            # Handle 'Present' or 'Current' in end date
            if end_date.lower() in ['present', 'current', 'now', 'ongoing']:
                end_date = datetime.datetime.now().strftime("%b %Y")
                
            # Try to parse the dates
            try:
                years_in_job = self._calculate_years_between_dates(start_date, end_date)
                total_years += years_in_job
            except:
                # If date parsing fails, skip this entry
                continue
                
        # Round to 1 decimal place for better readability
        return round(total_years, 1)
        
    def _calculate_years_between_dates(self, start_date_str, end_date_str):
        """Calculate years between two date strings in various formats"""
        # Common date formats
        date_formats = [
            "%b %Y",       # Jan 2020
            "%B %Y",       # January 2020
            "%m/%Y",       # 01/2020
            "%m-%Y",       # 01-2020
            "%Y-%m",       # 2020-01
            "%Y",          # 2020
            "%m/%d/%Y",    # 01/15/2020
            "%d/%m/%Y",    # 15/01/2020
            "%Y-%m-%d",    # 2020-01-15
            "%b %d, %Y",   # Jan 15, 2020
            "%B %d, %Y",   # January 15, 2020
            "%d %b %Y",    # 15 Jan 2020
            "%d %B %Y"     # 15 January 2020
        ]
        
        # Try to parse the start date
        start_date = None
        for fmt in date_formats:
            try:
                start_date = datetime.datetime.strptime(start_date_str, fmt)
                break
            except:
                continue
                
        # Try to parse the end date
        end_date = None
        for fmt in date_formats:
            try:
                end_date = datetime.datetime.strptime(end_date_str, fmt)
                break
            except:
                continue
                
        # If parsing failed, try to extract years only
        if not start_date or not end_date:
            # Try to extract just years (e.g., from "2018-2020")
            try:
                start_year = int(''.join(filter(str.isdigit, start_date_str)))
                end_year = int(''.join(filter(str.isdigit, end_date_str)))
                if 1900 <= start_year <= 2100 and 1900 <= end_year <= 2100:
                    if end_year < start_year:  # Handle cases like "20-22" meaning 2020-2022
                        # Assume it's a two-digit year
                        if start_year < 100:
                            start_year += 2000
                        if end_year < 100:
                            end_year += 2000
                    return end_year - start_year
            except:
                pass
                
            # If all parsing attempts fail, return 0
            return 0
            
        # Calculate the difference in years (including partial years)
        delta = end_date - start_date
        years = delta.days / 365.25
        
        # Return the years, ensuring it's never negative
        return max(0, years)
        
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