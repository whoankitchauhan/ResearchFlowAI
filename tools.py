from pydoc import text

from langchain.tools import tool
from sqlalchemy import text
import requests
from bs4 import BeautifulSoup
from tavily import TavilyClient
import os
from dotenv import load_dotenv
from rich import print
load_dotenv()

tavily = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

@tool 
def web_search(query: str) -> str:
    """Search the web for recent information. 
    The query must consist of short, specific keywords or direct questions. 
    Avoid unnecessary conversational words like 'please', 'find', or 'search for'."""
    try:
        results = tavily.search(query=query, max_results=2)
    
        out = []
    
        for r in results['results']:
            out.append(f"Title: {r['title']}\nURL: {r['url']}\nSnippet: {r['content'][:300]}\n")  
        
        
        return "\n----\n".join(out)
    except Exception as e:
        return f"An error occurred while searching: {str(e)}"

@tool
def scrape_url(url: str) -> str:
    """Extract clean readable text from a specific website link. 
    Use this ONLY when you already have a full target URL and need to read its content.
    Do not use this for general search queries."""
    try:
        response = requests.get(url,timeout=8, headers={'User-Agent': 'Mozilla/5.0'})
        response.raise_for_status()  # Raise an error for bad responses
        soup = BeautifulSoup(response.content, 'html.parser')
        for tag in soup(['script', 'style',"nav" , "footer"]):
            tag.decompose()  # Remove script and style elements
        text = soup.get_text(separator='\n', strip=True)
        return soup.get_text(separator='\n', strip=True)[:3000]  # Return the first 3000 characters of the text
    except Exception as e:
        return f"An error occurred while scraping the URL: {str(e)}"