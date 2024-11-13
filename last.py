import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, MetaData, text, event
from langchain_openai import AzureChatOpenAI
from langchain.prompts.chat import ChatPromptTemplate
from langchain_community.agent_toolkits.sql.base import create_sql_agent
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits.sql.toolkit import SQLDatabaseToolkit
from langchain.agents import AgentType
from flask import Flask, request, jsonify, render_template, session
import logging
import re
from datetime import datetime
import matplotlib.pyplot as plt
from io import BytesIO
import base64

# Load environment variables from .env file
load_dotenv()

# Retrieve environment variables
OPENAI_API_TYPE = os.getenv('OPENAI_API_TYPE', 'azure')
OPENAI_API_VERSION = os.getenv('OPENAI_API_VERSION', '2024-02-01')
OPENAI_API_BASE = os.getenv('OPENAI_API_BASE', 'https://armelyopenai.openai.azure.com/')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
OPENAI_CHAT_MODEL = os.getenv('OPENAI_CHAT_MODEL', 'gpt-4-model')

SQL_SERVER = os.getenv('SQL_SERVER', 'readtablewithopenai.database.windows.net')
SQL_DB = os.getenv('SQL_DB')
SQL_USERNAME = os.getenv('SQL_USERNAME')
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

# Get the current date and format it
current_date = datetime.now().strftime("%B %d, %Y")

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

# Set up Flask and session
app = Flask(__name__)
app.secret_key = os.urandom(24)  # Secure session with a random key

# Create SQL DB Agent
sqldb_agent = create_sql_agent(
    llm=llm,
    toolkit=sql_toolkit,
    agent_type=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
    handle_parsing_errors=True,
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
    """
    formatted_text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', response_text)
    formatted_text = re.sub(r'\*(.*?)\*', r'<i>\1</i>', formatted_text)
    markdown_link_pattern = r'\[([^\]]+)\]\(([^)]+)\)'
    formatted_text = re.sub(markdown_link_pattern, r'<a href="\2" target="_blank">\1</a>', formatted_text)
    formatted_text = formatted_text.replace('\n', '<br>')
    formatted_text = re.sub(r'(?<=:)\s*-\s*(.*?)(<br>|$)', r'<li>\1</li>', formatted_text)
    formatted_text = re.sub(r'(?<=:)\s*•\s*(.*?)(<br>|$)', r'<li>\1</li>', formatted_text)
    formatted_text = re.sub(r'(?<=:)\s*\d+\.\s*(.*?)(<br>|$)', r'<li>\1</li>', formatted_text)
    formatted_text = re.sub(r'(<li>.*?</li>)', r'<ul>\1</ul>', formatted_text, flags=re.DOTALL)
    formatted_text = formatted_text.replace('<br><li>', '<li>').replace('</li><br>', '</li>')
    return formatted_text

# Function to check if a value is null and provide a default message
def check_if_null(value):
    return value if value else "Provide examples of records to search"

# Function to build prompt with conversation history
def build_prompt_with_history(question):
    if 'conversation_history' not in session:
        session['conversation_history'] = []
    
    # Append the new question to conversation history
    session['conversation_history'].append(("user", question))
    
    # Build the prompt with the conversation history as a clear dialogue
    prompt_messages = [
        {"role": "system", "content": f"You are a helpful AI assistant. Today's date is {current_date}. You are an expert in querying SQL Databases."}
    ]
    
    # Append each message in conversation history as user/assistant format
    for role, content in session['conversation_history']:
        if role == "user":
            prompt_messages.append({"role": "user", "content": content})
        elif role == "ai":
            prompt_messages.append({"role": "assistant", "content": content})
    
    return prompt_messages

# Function to extract axis labels based on database query results
def extract_axes_labels(result):
    """
    Extracts x and y axis labels based on the column names from the Result object.
    """
    column_names = list(result.keys())  # Convert to list to make it subscriptable
    x_label = column_names[0] if len(column_names) > 0 else "Categories"
    y_label = column_names[1] if len(column_names) > 1 else "Values"
    return x_label, y_label

@app.route("/")
def index():
    return render_template("index.html")

logging.basicConfig(level=logging.DEBUG)

@app.route("/ask", methods=["POST"])
def ask():
    try:
        query = check_if_null(request.json.get("message"))
        
        # Generate prompt with conversation history
        final_prompt = build_prompt_with_history(query)
        
        # Generate response with error handling for parsing issues
        try:
            response = sqldb_agent.invoke(final_prompt)
            final_answer = response.get("output") if isinstance(response, dict) else response
            # Append the response to conversation history
            session['conversation_history'].append(("ai", final_answer))
        except ValueError as parse_error:
            logging.error("Parsing error encountered: %s", parse_error)
            final_answer = "I'm sorry, there was an issue processing your request. Could you try rephrasing your question?"
            session['conversation_history'].append(("ai", final_answer))

        formatted_answer = format_response_to_html(final_answer)

        # Check if the query is asking for a visualization
        if any(keyword in query.lower() for keyword in ["chart", "graph", "visual", "plot", "pie"]):
            with db_engine.connect() as connection:
                query_result = connection.execute(text(last_sql_statement))
                data = query_result.fetchall()

            # Get dynamic x and y labels based on the column names in the result
            x_label, y_label = extract_axes_labels(query_result)
            
            # Extract categories and values from data
            categories = [row[0] for row in data]
            values = [row[1] for row in data]

            if "pie" in query.lower():
                plt.figure(figsize=(8, 8))
                plt.pie(values, labels=categories, autopct='%1.1f%%', startangle=140)
                plt.title('Query Result Visualization (Pie Chart)')
            else:
                plt.figure(figsize=(10, 6))
                plt.bar(categories, values)
                plt.xlabel(x_label)
                plt.ylabel(y_label)
                plt.title('Query Result Visualization (Bar Chart)')

            img = BytesIO()
            plt.savefig(img, format="png")
            img.seek(0)
            img_base64 = base64.b64encode(img.getvalue()).decode()

            return jsonify({
                "summary": formatted_answer,
                "sql_statement": last_sql_statement,
                "chart_image": img_base64
            })
        
        return jsonify({
            "summary": formatted_answer,
            "sql_statement": last_sql_statement,
            "chart_image": None
        })
    
    except Exception as e:
        logging.error("An error occurred: %s", e, exc_info=True)
        return jsonify({"error": str(e)}), 500

@app.route("/reset", methods=["POST"])
def reset_conversation():
    session.pop('conversation_history', None)
    return jsonify({"message": "Conversation history has been reset."})

if __name__ == "__main__":
    app.run(debug=True)
