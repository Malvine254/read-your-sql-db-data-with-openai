import os
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

# Create the SQL Alchemy engine
driver = '{ODBC Driver 17 for SQL Server}'
odbc_str = (
    'mssql+pyodbc:///?odbc_connect='
    'Driver=' + driver +
    ';Server=tcp:' + str(SQL_SERVER) +
    ';PORT=1433'
    ';DATABASE=' + str(SQL_DB) +
    ';Uid=' + str(SQL_USERNAME) +
    ';Pwd=' + str(SQL_PWD) +
    ';Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;'
)

db_engine = create_engine(odbc_str)

# Reflect the tables in the database
metadata = MetaData()
metadata.reflect(bind=db_engine)

# Get the table names
# table_names = metadata.tables.keys()
# print("Tables in the database:")
# for table_name in table_names:
#     print(table_name)

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
    ("system", "You are a helpful AI assistant expert in querying SQL Database to find answers to user's questions about Categories, Products, and Orders."),
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
response = sqldb_agent.invoke(final_prompt.format(question="Patients that live in address called 505 Oak St but Male"))
print("Response from AI assistant:", response)
