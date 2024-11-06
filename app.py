import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, MetaData, text, event
from langchain_openai import AzureChatOpenAI
from langchain.prompts.chat import ChatPromptTemplate
from langchain_community.agent_toolkits.sql.base import create_sql_agent
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits.sql.toolkit import SQLDatabaseToolkit
from langchain.agents import AgentType
from flask import Flask, request, jsonify, render_template
import logging
import re

# Load environment variables from .env file
load_dotenv()

# Retrieve environment variables
OPENAI_API_TYPE = os.getenv('OPENAI_API_TYPE', 'azure')
OPENAI_API_VERSION = os.getenv('OPENAI_API_VERSION', '2024-02-01')
OPENAI_API_BASE = os.getenv('OPENAI_API_BASE', 'https://armelyopenai.openai.azure.com/')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
OPENAI_CHAT_MODEL = os.getenv('OPENAI_CHAT_MODEL', 'gpt-4-model')

SQL_SERVER = os.getenv('SQL_SERVER', 'readtablewithopenai.database.windows.net')
SQL_DB = os.getenv('SQL_DB', 'sql_db')
SQL_USERNAME = os.getenv('SQL_USERNAME', 'sql_db')
SQL_PWD = os.getenv('SQL_PWD')

# SQLAlchemy setup
driver = '{ODBC Driver 17 for SQL Server}'
odbc_str = (
    'mssql+pyodbc:///?odbc_connect='
    f'Driver={driver};Server=tcp:{SQL_SERVER};PORT=1433;DATABASE={SQL_DB};'
    f'Uid={SQL_USERNAME};Pwd={SQL_PWD};Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;'
)
db_engine = create_engine(odbc_str)

# Reflect database metadata and filter out system tables
metadata = MetaData()
metadata.reflect(bind=db_engine)
user_tables = [table for table in metadata.tables if not table.lower().startswith("sys")]

# Initialize AzureChatOpenAI instance
llm = AzureChatOpenAI(
    api_key=OPENAI_API_KEY,
    azure_endpoint=OPENAI_API_BASE,
    api_version=OPENAI_API_VERSION,
    model=OPENAI_CHAT_MODEL,
    deployment_name=OPENAI_CHAT_MODEL,
    temperature=0
)

# Initialize SQL Database and Toolkit
db = SQLDatabase(db_engine)
sql_toolkit = SQLDatabaseToolkit(db=db, llm=llm)

# Conversation prompt setup
final_prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a helpful AI assistant, an expert in querying SQL Databases, particularly in providing information about Patients, Doctors, and Prescriptions. Use the following database schema to find answers to users' questions effectively.Database Schema Summary Appointments (AppointmentID, PatientID, DoctorID, AppointmentDate, Reason): Stores appointment details, linking patients to doctors with appointment dates and reasons. Doctors (DoctorID, FirstName, LastName, Specialty, Phone, Email): Contains information about doctors, including their specialties and contact details. Patients (PatientID, FirstName, LastName, DateOfBirth, Gender, Phone, Email, Address, DoctorID): Records patient details, including their assigned doctor and personal information like contact details and address. Prescriptions (PrescriptionID, AppointmentID, Medication, Dosage, Duration): Tracks medications prescribed during appointments, with dosage and duration information. vw_pat_doc (Patientid, firstname, lastname, dateofbirth, gender, address, doc_firstname, doc_lastname, specialty, phone): A view that combines patient and doctor information for easy access to patient-doctor relationships."),
    ("user", "{question}\n ai: "),
])

# Create SQL DB Agent
sqldb_agent = create_sql_agent(
    llm=llm,
    toolkit=sql_toolkit,
    agent_type=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
    verbose=True
)

# Global variable to store the last SQL statement
last_sql_statement = ""

# Set up SQLAlchemy event listener to capture SQL statements
@event.listens_for(db_engine, "before_cursor_execute")
def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    global last_sql_statement
    last_sql_statement = statement  # Store the SQL statement in a global variable
    logging.debug("Generated SQL Statement: %s", statement)

def format_response_to_html(response_text):
    """
    Formats the AI response text into HTML with basic support for bold, italic, 
    lists (ordered and unordered), and URLs converted into clickable links.
    Uses <br> for new lines instead of <p>.
    """
    # Handling bold text: **bold** becomes <b>bold</b>
    formatted_text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', response_text)

    # Handling italic text: *italic* becomes <i>italic</i>
    formatted_text = re.sub(r'\*(.*?)\*', r'<i>\1</i>', formatted_text)

    # Convert Markdown links to HTML links: [Text](URL) -> <a href="URL" target="_blank">Text</a>
    markdown_link_pattern = r'\[([^\]]+)\]\(([^)]+)\)'  # Markdown pattern for [Text](URL)
    formatted_text = re.sub(markdown_link_pattern, r'<a href="\2" target="_blank">\1</a>', formatted_text)

    # Replace newline characters with <br> for line breaks
    formatted_text = formatted_text.replace('\n', '<br>')

    # Convert unordered and ordered lists
    formatted_text = re.sub(r'(?<=:)\s*-\s*(.*?)(<br>|$)', r'<li>\1</li>', formatted_text)  # Unordered lists (-)
    formatted_text = re.sub(r'(?<=:)\s*•\s*(.*?)(<br>|$)', r'<li>\1</li>', formatted_text)  # Unordered lists (•)
    formatted_text = re.sub(r'(?<=:)\s*\d+\.\s*(.*?)(<br>|$)', r'<li>\1</li>', formatted_text)  # Ordered lists (1.)

    # Wrap lists with <ul> or <ol> tags
    formatted_text = re.sub(r'(<li>.*?</li>)', r'<ul>\1</ul>', formatted_text, flags=re.DOTALL)

    # Clean up any extra <br> tags around list items
    formatted_text = formatted_text.replace('<br><li>', '<li>').replace('</li><br>', '</li>')

    return formatted_text

# Flask application setup
app = Flask(__name__)

def check_if_null(value):
    return value if value else "Provide examples of records to search"


@app.route("/")
def index():
    # Render the index.html template
    return render_template("index.html")

# Set up logging
logging.basicConfig(level=logging.DEBUG)

@app.route("/ask", methods=["POST"])
def ask():
    try:
        query = check_if_null(request.json.get("message"))
        
        # Generate the response from OpenAI
        response = sqldb_agent.invoke(final_prompt.format(question=query))
        
        # Extract the final answer and format it as HTML
        final_answer = response.get("output") if isinstance(response, dict) else response
        formatted_answer = format_response_to_html(final_answer)

        # Include the last SQL statement in the response
        return jsonify({"summary": formatted_answer, "sql_statement": last_sql_statement, "response": []})
    
    except Exception as e:
        logging.error("An error occurred: %s", e, exc_info=True)
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True)
