import os
import json
from dotenv import load_dotenv
from sqlalchemy import create_engine, MetaData
from langchain_openai import AzureChatOpenAI
from langchain.prompts.chat import ChatPromptTemplate
from langchain_community.agent_toolkits.sql.base import create_sql_agent
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits.sql.toolkit import SQLDatabaseToolkit
from langchain.agents import AgentType

# Load environment variables from .env file
load_dotenv()

# Retrieve environment variables
OPENAI_API_TYPE = 'azure'
OPENAI_API_VERSION = '2024-02-01'
OPENAI_API_BASE = 'https://armelyopenai.openai.azure.com/'
OPENAI_API_KEY = 'bf960d750ff946e8a8908e7f5ed53b71'
OPENAI_CHAT_MODEL = 'gpt-4-model'

SQL_SERVER = 'readtablewithopenai.database.windows.net'
SQL_DB = 'sql_db'
SQL_USERNAME = 'sql_db'
SQL_PWD = 'Igneus1998$'

# Check if any of the required environment variables are None
required_env_vars = [OPENAI_API_TYPE, OPENAI_API_VERSION, OPENAI_API_BASE, OPENAI_API_KEY, OPENAI_CHAT_MODEL]
missing_env_vars = [var for var in required_env_vars if var is None]
if missing_env_vars:
    print("Error: The following environment variables are not set:", missing_env_vars)
    exit(1)

# Check if any of the required SQL environment variables are None
required_sql_vars = [SQL_SERVER, SQL_DB, SQL_USERNAME, SQL_PWD]
missing_sql_vars = [var for var in required_sql_vars if var is None]
if missing_sql_vars:
    print("Error: The following SQL environment variables are not set:", missing_sql_vars)
    exit(1)

# Create the SQL Alchemy engine with connection pooling
driver = '{ODBC Driver 17 for SQL Server}'
odbc_str = (
    f"mssql+pyodbc://{SQL_USERNAME}:{SQL_PWD}@{SQL_SERVER}:1433/{SQL_DB}"
    "?driver=ODBC+Driver+17+for+SQL+Server"
    "&Encrypt=yes&TrustServerCertificate=no&Connection Timeout=30"
)
db_engine = create_engine(odbc_str, pool_size=10, max_overflow=20, pool_timeout=30, pool_recycle=1800)

# Reflect the tables in the database
metadata = MetaData()
metadata.reflect(bind=db_engine)

# Cache directory
CACHE_DIR = 'table_cache'
os.makedirs(CACHE_DIR, exist_ok=True)


def cache_table(table_name, data):
    with open(os.path.join(CACHE_DIR, f"{table_name}.json"), 'w') as f:
        json.dump(data, f)


def load_cached_table(table_name):
    cache_path = os.path.join(CACHE_DIR, f"{table_name}.json")
    if os.path.exists(cache_path):
        with open(cache_path, 'r') as f:
            return json.load(f)
    return None


def get_table_data(table_name):
    # Check if the table is already cached
    cached_data = load_cached_table(table_name)
    if cached_data is not None:
        return cached_data

    # If not cached, retrieve data from the database
    table = metadata.tables[table_name]
    conn = db_engine.connect()
    data = conn.execute(table.select()).fetchall()
    conn.close()

    # Convert to list of dicts and cache it
    data_dict = [dict(row) for row in data]
    cache_table(table_name, data_dict)

    return data_dict


# Initialize AzureChatOpenAI
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

# Define the conversation prompt
final_prompt = ChatPromptTemplate.from_messages([
    ("system",
     "You are a helpful AI assistant expert in querying SQL Database to find answers to user's questions about Categories, Products, and Orders."),
    ("user", "{question}\nai: "),
])

# Create SQL DB Agent
sqldb_agent = create_sql_agent(
    llm=llm,
    toolkit=sql_toolkit,
    agent_type=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
    verbose=True
)

# Example query to the AI assistant
query = "SELECT * FROM Patients"
data = get_table_data('Patients')
print("Retrieved data:", data)

# Use the cached data in your application
response = sqldb_agent.invoke(final_prompt.format(question="Patients that live in address called 505 Oak St but Male"))
print("Response from AI assistant:", response)
