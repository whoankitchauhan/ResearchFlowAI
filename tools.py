import os

from langchain.tools import tool
import requests
from bs4 import BeautifulSoup
from tavily import TavilyClient
from dotenv import load_dotenv

load_dotenv()


def _get_tavily_client() -> TavilyClient:
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        raise RuntimeError("TAVILY_API_KEY is required to use web search.")
    return TavilyClient(api_key=api_key)


@tool 
def web_search(query: str) -> str:
    """Search the web for recent information. 
    The query must consist of short, specific keywords or direct questions. 
    Avoid unnecessary conversational words like 'please', 'find', or 'search for'."""
    results = _get_tavily_client().search(query=query, max_results=2)
    
    try:
    
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
        return soup.get_text(separator='\n', strip=True)[:3000]  # Return the first 3000 characters of the text
    except Exception as e:
        return f"An error occurred while scraping the URL: {str(e)}"