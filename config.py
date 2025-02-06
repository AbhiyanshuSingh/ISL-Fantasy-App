import pymysql
import os

def get_database_connection():
    return pymysql.connect(
        host=os.getenv("DB_HOST", "localhost"),  
        user=os.getenv("DB_USER", "root"),  
        password=os.getenv("DB_PASS", "root"),  
        database=os.getenv("DB_NAME", "fantasy_appc"),  
        ssl={'ssl': {}}
    )
