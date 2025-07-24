from flask import Flask, request, jsonify, render_template
from flask_sqlalchemy import SQLAlchemy
import os
import docx 
import PyPDF2 
import requests # req lib for api, using gemini so need ts
import json

app=Flask(__name__)
#app config for sql database ig.
app.config['SQLALCHEMY_DATABASE_URI']='mysql+mysqlconnector://flaskuser:8xt12as13@localHost:3306/jobsh_db'
app.config['SQLALCHEMY_TRACK_MODIFICATION']=False

#gemini api key syncin :)
GEMINI_API_KEY='AIzaSyBqpJhTMWOpJ9hOp02VQCM_CapdAs1pfJA'
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"

db = SQLAlchemy(app)

# --- Database Models ---
class Resume(db.Model):
    __tablename__ = 'resumes'
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    content = db.Column(db.Text, nullable=False)
    upload_date = db.Column(db.DateTime, default=db.func.now())

    def __repr__(self):
        return f'<Resume {self.id}: {self.filename}>'

class ParsedResume(db.Model):
    __tablename__ = 'parsed_resumes'
    id = db.Column(db.Integer, primary_key=True)
    resume_id = db.Column(db.Integer, db.ForeignKey('resumes.id'), unique=True, nullable=False)
    parsed_data_json = db.Column(db.Text, nullable=False)
    parsed_date = db.Column(db.DateTime, default=db.func.now())

    resume = db.relationship('Resume', backref=db.backref('parsed_data', uselist=False))

    def __repr__(self):
        return f'<ParsedResume for Resume {self.resume_id}>'

class JobDescription(db.Model):
    __tablename__ = 'job_descriptions'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    company = db.Column(db.String(255), nullable=True)
    description = db.Column(db.Text, nullable=False)
    upload_date = db.Column(db.DateTime, default=db.func.now())

    def __repr__(self):
        return f'<JobDescription {self.id}: {self.title} at {self.company}>'

class JobMatchResult(db.Model):
    __tablename__ = 'job_match_results'
    id = db.Column(db.Integer, primary_key=True)
    resume_id = db.Column(db.Integer, db.ForeignKey('resumes.id'), nullable=False)
    job_id = db.Column(db.Integer, db.ForeignKey('job_descriptions.id'), nullable=False)
    match_score = db.Column(db.Integer, nullable=False) 
    justification = db.Column(db.Text, nullable=True) 
    aligned_skills = db.Column(db.Text, nullable=True) 
    missing_skills = db.Column(db.Text, nullable=True) 
    match_date = db.Column(db.DateTime, default=db.func.now())

  
    __table_args__ = (db.UniqueConstraint('resume_id', 'job_id', name='_resume_job_uc'),)

    resume = db.relationship('Resume', backref=db.backref('matches'))
    job_description = db.relationship('JobDescription', backref=db.backref('matches'))

    def __repr__(self):
        return f'<JobMatchResult R:{self.resume_id} J:{self.job_id} Score:{self.match_score}>'

def extract_text_from_docx(docx_file):
    document = docx.Document(docx_file)
    full_text = []
    for para in document.paragraphs:
        full_text.append(para.text)
    return '\n'.join(full_text)

def extract_text_from_pdf(pdf_file):
    pdf_reader = PyPDF2.PdfReader(pdf_file)
    full_text = []
    for page in pdf_reader.pages:
        full_text.append(page.extract_text())
    return '\n'.join(full_text)

# --- Gemini API Interaction Functions ---
def parse_resume_with_gemini(resume_text):
    prompt = f"""
    You are an expert resume parser. Analyze the following resume text and extract key information into a structured JSON format.
    If a field is not found, use "N/A". Ensure all arrays are empty if no relevant data is found.

    Extract the following fields:
    - "name": Full name of the candidate.
    - "contact_info":
        - "email": Email address.
        - "phone": Phone number.
        - "linkedin": LinkedIn profile URL.
        - "portfolio": Personal portfolio/website URL.
    - "summary": A brief professional summary or objective.
    - "skills": An array of key skills (e.g., ["Python", "SQL", "Project Management"]). Categorize if possible (e.g., "Programming Languages", "Tools", "Soft Skills").
    - "experience": An array of work experiences, each object containing:
        - "title": Job title.
        - "company": Company name.
        - "location": Job location.
        - "dates": Employment period (e.g., "Jan 2020 - Dec 2022").
        - "description": A brief summary of responsibilities and achievements (as a single string).
    - "education": An array of educational entries, each object containing:
        - "degree": Degree obtained (e.g., "B.S. in Computer Science").
        - "institution": Name of the institution.
        - "location": Institution location.
        - "dates": Attendance period or graduation date (e.g., "Sep 2018 - May 2022").
        - "gpa": GPA (if available).
    - "projects": An array of projects, each object containing:
        - "name": Project name.
        - "description": Project description.
        - "link": Link to project (e.g., GitHub).
    - "certifications": An array of certifications, each object containing:
        - "name": Certification name.
        - "issuer": Issuing body.
        - "date": Date obtained.

    Here is the resume text:
    ---
    {resume_text}
    ---
    """

    headers = {
        'Content-Type': 'application/json',
    }
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": prompt}
                ]
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": {
                "type": "OBJECT",
                "properties": {
                    "name": {"type": "STRING"},
                    "contact_info": {
                        "type": "OBJECT",
                        "properties": {
                            "email": {"type": "STRING"},
                            "phone": {"type": "STRING"},
                            "linkedin": {"type": "STRING"},
                            "portfolio": {"type": "STRING"}
                        }
                    },
                    "summary": {"type": "STRING"},
                    "skills": {
                        "type": "ARRAY",
                        "items": {"type": "STRING"}
                    },
                    "experience": {
                        "type": "ARRAY",
                        "items": {
                            "type": "OBJECT",
                            "properties": {
                                "title": {"type": "STRING"},
                                "company": {"type": "STRING"},
                                "location": {"type": "STRING"},
                                "dates": {"type": "STRING"},
                                "description": {"type": "STRING"}
                            }
                        }
                    },
                    "education": {
                        "type": "ARRAY",
                        "items": {
                            "type": "OBJECT",
                            "properties": {
                                "degree": {"type": "STRING"},
                                "institution": {"type": "STRING"},
                                "location": {"type": "STRING"},
                                "dates": {"type": "STRING"},
                                "gpa": {"type": "STRING"}
                            }
                        }
                    },
                    "projects": {
                        "type": "ARRAY",
                        "items": {
                            "type": "OBJECT",
                            "properties": {
                                "name": {"type": "STRING"},
                                "description": {"type": "STRING"},
                                "link": {"type": "STRING"}
                            }
                        }
                    },
                    "certifications": {
                        "type": "ARRAY",
                        "items": {
                            "type": "OBJECT",
                            "properties": {
                                "name": {"type": "STRING"},
                                "issuer": {"type": "STRING"},
                                "date": {"type": "STRING"}
                            }
                        }
                    }
                }
            }
        }
    }

    try:
        print(f"Attempting to connect to Gemini API URL for parsing: {GEMINI_API_URL}")
        response = requests.post(GEMINI_API_URL, headers=headers, data=json.dumps(payload))
        response.raise_for_status()
        
        result = response.json()
        
        if result.get('candidates') and result['candidates'][0].get('content') and result['candidates'][0]['content'].get('parts'):
            parsed_json_string = result['candidates'][0]['content']['parts'][0]['text']
            return json.loads(parsed_json_string)
        else:
            print("Unexpected Gemini API response structure for parsing:", result)
            return {"error": "Unexpected API response structure from Gemini."}

    except requests.exceptions.RequestException as e:
        print(f"Error communicating with Gemini API for parsing: {e}")
        return {"error": f"Failed to connect to AI service: {e}"}
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON from Gemini API for parsing: {e}")
        print(f"Raw Gemini response for parsing: {response.text}")
        return {"error": f"Failed to parse AI response: {e}"}
    except Exception as e:
        print(f"An unexpected error occurred during Gemini parsing: {e}")
        return {"error": f"An unexpected error occurred: {e}"}

def match_resume_to_job_with_gemini(parsed_resume_data, job_description_text):
    resume_str = json.dumps(parsed_resume_data, indent=2)

    prompt = f"""
    You are an expert HR AI assistant. Compare the following resume (structured JSON) with the job description (plain text).
    Provide a match score (0-100%), a concise justification for the score, a list of skills from the resume that align with the job, and a list of skills required by the job but missing from the resume.

    Resume (JSON):
    ---
    {resume_str}
    ---

    Job Description:
    ---
    {job_description_text}
    ---

    Provide the output in the following JSON format:
    {{
        "match_score": <integer 0-100>,
        "justification": "<string explaining the score>",
        "aligned_skills": ["skill1", "skill2", ...],
        "missing_skills": ["skillA", "skillB", ...]
    }}
    """

    headers = {
        'Content-Type': 'application/json',
    }
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": prompt}
                ]
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": {
                "type": "OBJECT",
                "properties": {
                    "match_score": {"type": "INTEGER"},
                    "justification": {"type": "STRING"},
                    "aligned_skills": {
                        "type": "ARRAY",
                        "items": {"type": "STRING"}
                    },
                    "missing_skills": {
                        "type": "ARRAY",
                        "items": {"type": "STRING"}
                    }
                }
            }
        }
    }

    try:
        print(f"Attempting to connect to Gemini API for matching URL: {GEMINI_API_URL}")
        response = requests.post(GEMINI_API_URL, headers=headers, data=json.dumps(payload))
        response.raise_for_status()
        
        result = response.json()
        
        if result.get('candidates') and result['candidates'][0].get('content') and result['candidates'][0]['content'].get('parts'):
            parsed_json_string = result['candidates'][0]['content']['parts'][0]['text']
            return json.loads(parsed_json_string)
        else:
            print("Unexpected Gemini API response structure for matching:", result)
            return {"error": "Unexpected API response structure for matching."}

    except requests.exceptions.RequestException as e:
        print(f"Error communicating with Gemini API for matching: {e}")
        return {"error": f"Failed to connect to AI service for matching: {e}"}
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON from Gemini API for matching: {e}")
        print(f"Raw Gemini response for matching: {response.text}")
        return {"error": f"Failed to parse AI response for matching: {e}"}
    except Exception as e:
        print(f"An unexpected error occurred during Gemini matching: {e}")
        return {"error": f"An unexpected error occurred during matching: {e}"}


# routes bruv

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/upload')
def upload_form():
    return render_template('upload.html')

@app.route('/upload_resume', methods=['POST'])
def upload_resume():
    if 'resume_file' not in request.files:
        return jsonify({"error": "No file part in the request"}), 400

    file = request.files['resume_file']

    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    allowed_extensions = {'txt', 'pdf', 'docx'}
    file_extension = file.filename.rsplit('.', 1)[1].lower()

    if file_extension in allowed_extensions:
        try:
            resume_content = ""
            if file_extension == 'txt':
                resume_content = file.read().decode('utf-8')
            elif file_extension == 'pdf':
                resume_content = extract_text_from_pdf(file)
            elif file_extension == 'docx':
                resume_content = extract_text_from_docx(file)
            
            if not resume_content.strip():
                return jsonify({"error": "Could not extract text from the uploaded file. It might be empty or unreadable."}), 400

            new_resume = Resume(
                filename=file.filename,
                content=resume_content
            )
            db.session.add(new_resume)
            db.session.commit()

            return jsonify({"message": f"Resume '{file.filename}' uploaded and saved successfully!", "resume_id": new_resume.id}), 200

        except Exception as e:
            db.session.rollback()
            print(f"Error during file processing: {e}") 
            return jsonify({"error": f"Error processing file: {e}. Please ensure it's a valid TXT, PDF, or DOCX."}), 500
    else:
        return jsonify({"error": "File type not allowed. Please upload a .txt, .pdf, or .docx file."}), 400

@app.route('/list_resumes')
def list_resumes():
    resumes = Resume.query.all()
    if not resumes:
        return jsonify({"message": "No resumes found in the database."}), 200
    
    resumes_list = []
    for resume in resumes:
        resumes_list.append({
            "id": resume.id,
            "filename": resume.filename,
            "upload_date": resume.upload_date.isoformat(),
            "content_preview": resume.content[:200] + "..." if len(resume.content) > 200 else resume.content
        })
    return jsonify(resumes_list), 200

@app.route('/parse_resume/<int:resume_id>')
def parse_resume(resume_id):
    resume = Resume.query.get(resume_id)
    if not resume:
        return jsonify({"error": "Resume not found."}), 404

    if ParsedResume.query.filter_by(resume_id=resume_id).first():
        return jsonify({"message": f"Resume ID {resume_id} has already been parsed. To re-parse, delete the existing parsed entry first."}), 200

    try:
        parsed_data = parse_resume_with_gemini(resume.content)

        if "error" in parsed_data:
            return jsonify({"error": f"Failed to parse resume with AI: {parsed_data['error']}"}), 500

        new_parsed_resume = ParsedResume(
            resume_id=resume.id,
            parsed_data_json=json.dumps(parsed_data)
        )
        db.session.add(new_parsed_resume)
        db.session.commit()

        return jsonify({"message": f"Resume ID {resume_id} parsed and saved successfully!", "parsed_data": parsed_data}), 200

    except Exception as e:
        db.session.rollback()
        print(f"Error during resume parsing for ID {resume_id}: {e}")
        return jsonify({"error": f"An unexpected error occurred during parsing: {e}"}), 500

@app.route('/view_parsed_resume/<int:resume_id>')
def view_parsed_resume(resume_id):
    parsed_resume = ParsedResume.query.filter_by(resume_id=resume_id).first()
    if not parsed_resume:
        return jsonify({"message": f"No parsed data found for Resume ID {resume_id}. Please parse it first."}), 404
    
    parsed_data = json.loads(parsed_resume.parsed_data_json)
    return jsonify({"resume_id": resume_id, "parsed_data": parsed_data, "parsed_date": parsed_resume.parsed_date.isoformat()}), 200

@app.route('/add_job_description')
def add_job_description_form():
    return render_template('job_description_form.html')

@app.route('/save_job_description', methods=['POST'])
def save_job_description():
    title = request.form.get('title')
    company = request.form.get('company')
    description = request.form.get('description')

    if not title or not description:
        return jsonify({"error": "Job Title and Description are required."}), 400

    try:
        new_jd = JobDescription(
            title=title,
            company=company,
            description=description
        )
        db.session.add(new_jd)
        db.session.commit()
        return jsonify({"message": f"Job Description '{title}' saved successfully!", "job_id": new_jd.id}), 200
    except Exception as e:
        db.session.rollback()
        print(f"Error saving job description: {e}")
        return jsonify({"error": f"Error saving job description: {e}"}), 500

@app.route('/list_job_descriptions')
def list_job_descriptions():
    job_descriptions = JobDescription.query.all()
    if not job_descriptions:
        return jsonify({"message": "No job descriptions found in the database."}), 200
    
    jd_list = []
    for jd in job_descriptions:
        jd_list.append({
            "id": jd.id,
            "title": jd.title,
            "company": jd.company,
            "upload_date": jd.upload_date.isoformat(),
            "description_preview": jd.description[:200] + "..." if len(jd.description) > 200 else jd.description
        })
    return jsonify(jd_list), 200

@app.route('/match_resume_to_all_jobs/<int:resume_id>')
def match_resume_to_all_jobs(resume_id):
    # 1. Fetch the parsed resume data
    parsed_resume = ParsedResume.query.filter_by(resume_id=resume_id).first()
    if not parsed_resume:
        return jsonify({"error": f"Parsed data for Resume ID {resume_id} not found. Please parse the resume first."}), 404
    
    resume_data = json.loads(parsed_resume.parsed_data_json)

    job_descriptions = JobDescription.query.all()
    if not job_descriptions:
        return jsonify({"message": "No job descriptions found in the database to match against."}), 200

    match_results = []
    for job_desc in job_descriptions:
        try:
            existing_match = JobMatchResult.query.filter_by(
                resume_id=resume_id, 
                job_id=job_desc.id
            ).first()

            if existing_match:
                match_data = {
                    "match_score": existing_match.match_score,
                    "justification": existing_match.justification,
                    "aligned_skills": json.loads(existing_match.aligned_skills) if existing_match.aligned_skills else [],
                    "missing_skills": json.loads(existing_match.missing_skills) if existing_match.missing_skills else []
                }
                print(f"Using existing match for Resume {resume_id} and Job {job_desc.id}")
            else:
                print(f"Matching Resume {resume_id} with Job {job_desc.id} ('{job_desc.title}')...")
                match_data = match_resume_to_job_with_gemini(resume_data, job_desc.description)

                if "error" in match_data:
                    print(f"Error matching Resume {resume_id} to Job {job_desc.id}: {match_data['error']}")
                    continue 


                new_match_entry = JobMatchResult(
                    resume_id=resume_id,
                    job_id=job_desc.id,
                    match_score=match_data.get('match_score', 0), 
                    justification=match_data.get('justification', 'N/A'),
                    aligned_skills=json.dumps(match_data.get('aligned_skills', [])),
                    missing_skills=json.dumps(match_data.get('missing_skills', []))
                )
                db.session.add(new_match_entry)
                db.session.commit()
                print(f"Match saved for Resume {resume_id} and Job {job_desc.id}")

            match_results.append({
                "job_id": job_desc.id,
                "job_title": job_desc.title,
                "company": job_desc.company,
                "match_score": match_data.get('match_score', 0),
                "justification": match_data.get('justification', 'N/A'),
                "aligned_skills": match_data.get('aligned_skills', []),
                "missing_skills": match_data.get('missing_skills', [])
            })

        except IntegrityError:
            db.session.rollback()
            print(f"Duplicate match attempt for Resume {resume_id} and Job {job_desc.id}. Skipping.")
        except Exception as e:
            db.session.rollback()
            print(f"An unexpected error occurred during matching loop for Job {job_desc.id}: {e}")
            continue 

    match_results.sort(key=lambda x: x['match_score'], reverse=True)

    return jsonify({"message": f"Matching complete for Resume ID {resume_id}.", "matches": match_results}), 200

@app.route('/view_matches_for_resume/<int:resume_id>')
def view_matches_for_resume(resume_id):
    matches = JobMatchResult.query.filter_by(resume_id=resume_id).order_by(JobMatchResult.match_score.desc()).all()
    
    if not matches:
        return jsonify({"message": f"No match results found for Resume ID {resume_id}. Please run the matching process first."}), 200
    
    results_list = []
    for match in matches:
        job_desc = JobDescription.query.get(match.job_id)
        results_list.append({
            "job_id": match.job_id,
            "job_title": job_desc.title if job_desc else "N/A",
            "company": job_desc.company if job_desc else "N/A",
            "match_score": match.match_score,
            "justification": match.justification,
            "aligned_skills": json.loads(match.aligned_skills) if match.aligned_skills else [],
            "missing_skills": json.loads(match.missing_skills) if match.missing_skills else [],
            "match_date": match.match_date.isoformat()
        })
    return jsonify({"resume_id": resume_id, "matches": results_list}), 200

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        print("MySQL Database tables created (if they didn't exist).")
    app.run(debug=True)
