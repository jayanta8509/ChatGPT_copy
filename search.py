import os
import requests
import json
import logging
from typing import Dict, List, Any, Optional
from dotenv import load_dotenv
# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()
google_search_api_key = os.getenv("GOOGLE_SEARCH_API_KEY")
google_search_engine_id = os.getenv("GOOGLE_SEARCH_ENGINE_ID")

class GoogleSearchAPI:
    def __init__(self, api_key: str = google_search_api_key, 
                 search_engine_id: str = google_search_engine_id):
        """
        Initialize Google Search API client
        
        Args:
            api_key: Google Custom Search API key
            search_engine_id: Custom Search Engine ID
        """
        self.api_key = api_key
        self.search_engine_id = search_engine_id
        self.base_url = "https://www.googleapis.com/customsearch/v1"
    
    def search(self, query: str, num_results: int = 10, start_index: int = 1, 
               language: str = "en", country: str = "us") -> Dict[str, Any]:
        """
        Search for a topic using Google Custom Search API
        
        Args:
            query: The search query/topic
            num_results: Number of results to return (max 10 per request)
            start_index: Starting index for results (for pagination)
            language: Language for search results (default: 'en')
            country: Country for search results (default: 'us')
        
        Returns:
            Dictionary containing search results and metadata
        """
        try:
            # Prepare API parameters
            params = {
                'key': self.api_key,
                'cx': self.search_engine_id,
                'q': query,
                'num': min(num_results, 10),  # Google API max is 10 per request
                'start': start_index,
                'lr': f'lang_{language}',
                'gl': country,
                'safe': 'active'  # Safe search
            }
            
            logger.info(f"Searching for: '{query}' with {num_results} results")
            
            # Make API request
            response = requests.get(self.base_url, params=params, timeout=30)
            response.raise_for_status()
            
            # Parse response
            data = response.json()
            
            # Extract and format results
            results = self._format_results(data)
            
            logger.info(f"Successfully retrieved {len(results.get('items', []))} results")
            return results
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error during search: {str(e)}")
            return {
                "status": "error",
                "message": f"Network error: {str(e)}",
                "items": []
            }
        except Exception as e:
            logger.error(f"Error during search: {str(e)}")
            return {
                "status": "error", 
                "message": f"Search error: {str(e)}",
                "items": []
            }
    
    def _format_results(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format the raw API response into a cleaner structure
        
        Args:
            data: Raw response from Google Custom Search API
        
        Returns:
            Formatted search results
        """
        formatted_results = {
            "status": "success",
            "query": data.get('queries', {}).get('request', [{}])[0].get('searchTerms', ''),
            "total_results": data.get('searchInformation', {}).get('totalResults', '0'),
            "search_time": data.get('searchInformation', {}).get('searchTime', 0),
            "items": []
        }
        
        # Process search items
        items = data.get('items', [])
        for item in items:
            formatted_item = {
                "title": item.get('title', ''),
                "link": item.get('link', ''),
                "snippet": item.get('snippet', ''),
                "display_link": item.get('displayLink', ''),
                "formatted_url": item.get('formattedUrl', ''),
                "cacheId": item.get('cacheId', ''),
                "mime": item.get('mime', ''),
                "file_format": item.get('fileFormat', '')
            }
            
            # Add page map data if available
            if 'pagemap' in item:
                formatted_item['pagemap'] = item['pagemap']
            
            # Add image data if available
            if 'image' in item:
                formatted_item['image'] = item['image']
                
            formatted_results['items'].append(formatted_item)
        
        return formatted_results
    
    def search_multiple_pages(self, query: str, total_results: int = 20) -> Dict[str, Any]:
        """
        Search multiple pages to get more than 10 results
        
        Args:
            query: The search query
            total_results: Total number of results desired (will be rounded to nearest 10)
        
        Returns:
            Combined results from multiple pages
        """
        all_items = []
        pages_needed = min((total_results + 9) // 10, 10)  # Google API allows max 100 results (10 pages)
        
        combined_results = {
            "status": "success",
            "query": query,
            "total_results": "0",
            "search_time": 0,
            "items": []
        }
        
        for page in range(pages_needed):
            start_index = page * 10 + 1
            page_results = self.search(query, num_results=10, start_index=start_index)
            
            if page_results.get("status") == "error":
                combined_results["status"] = "partial_error"
                combined_results["error_message"] = page_results.get("message", "")
                break
            
            # Update metadata from first page
            if page == 0:
                combined_results["total_results"] = page_results.get("total_results", "0")
                combined_results["search_time"] = page_results.get("search_time", 0)
            
            # Add items from this page
            page_items = page_results.get("items", [])
            all_items.extend(page_items)
            
            # Stop if we got fewer results than expected (end of results)
            if len(page_items) < 10:
                break
        
        combined_results["items"] = all_items[:total_results]
        return combined_results
    
    def search_with_filters(self, query: str, site_search: Optional[str] = None,
                           file_type: Optional[str] = None, date_restrict: Optional[str] = None,
                           num_results: int = 10) -> Dict[str, Any]:
        """
        Search with additional filters
        
        Args:
            query: The search query
            site_search: Restrict search to specific site (e.g., 'reddit.com')
            file_type: Filter by file type (e.g., 'pdf', 'doc', 'ppt')
            date_restrict: Date restriction (e.g., 'd1' for past day, 'w1' for past week, 'm1' for past month)
            num_results: Number of results to return
        
        Returns:
            Filtered search results
        """
        # Modify query with filters
        filtered_query = query
        
        if site_search:
            filtered_query += f" site:{site_search}"
        
        if file_type:
            filtered_query += f" filetype:{file_type}"
        
        # Prepare additional parameters
        extra_params = {}
        if date_restrict:
            extra_params['dateRestrict'] = date_restrict
        
        try:
            params = {
                'key': self.api_key,
                'cx': self.search_engine_id,
                'q': filtered_query,
                'num': min(num_results, 10),
                'safe': 'active'
            }
            
            # Add extra parameters
            params.update(extra_params)
            
            logger.info(f"Searching with filters: '{filtered_query}'")
            
            response = requests.get(self.base_url, params=params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            results = self._format_results(data)
            
            logger.info(f"Successfully retrieved {len(results.get('items', []))} filtered results")
            return results
            
        except Exception as e:
            logger.error(f"Error during filtered search: {str(e)}")
            return {
                "status": "error",
                "message": f"Filtered search error: {str(e)}",
                "items": []
            }


# Convenience functions for easy usage
def search_topic(topic: str, num_results: int = 10) -> Dict[str, Any]:
    """
    Simple function to search for a topic
    
    Args:
        topic: The topic/query to search for
        num_results: Number of results to return
    
    Returns:
        Search results dictionary
    """
    search_api = GoogleSearchAPI()
    return search_api.search(topic, num_results)


def search_multiple_topics(topics: List[str], num_results_per_topic: int = 5) -> Dict[str, Any]:
    """
    Search for multiple topics and return combined results
    
    Args:
        topics: List of topics to search for
        num_results_per_topic: Number of results per topic
    
    Returns:
        Combined results for all topics
    """
    search_api = GoogleSearchAPI()
    all_results = {}
    
    for topic in topics:
        logger.info(f"Searching for topic: {topic}")
        results = search_api.search(topic, num_results_per_topic)
        all_results[topic] = results
    
    return all_results


def search_recent_news(topic: str, num_results: int = 10) -> Dict[str, Any]:
    """
    Search for recent news about a topic
    
    Args:
        topic: The topic to search for
        num_results: Number of results to return
    
    Returns:
        Recent news search results
    """
    search_api = GoogleSearchAPI()
    news_query = f"{topic} news"
    return search_api.search_with_filters(
        news_query, 
        date_restrict='m1',  # Past month
        num_results=num_results
    )


# Example usage
if __name__ == "__main__":
    # Example 1: Simple search
    print("=== Simple Search Example ===")
    results = search_topic("artificial intelligence", 5)
    if results.get("status") == "success":
        print(f"Found {len(results['items'])} results for 'artificial intelligence'")
        for i, item in enumerate(results['items'][:3], 1):
            print(f"{i}. {item['title']}")
            print(f"   {item['link']}")
            print(f"   {item['snippet'][:100]}...")
            print()
    else:
        print(f"Search failed: {results.get('message')}")
    
    print("\n" + "="*50 + "\n")
    
    # Example 2: Multiple topics
    print("=== Multiple Topics Example ===")
    topics = ["machine learning", "deep learning", "neural networks"]
    multi_results = search_multiple_topics(topics, 3)
    
    for topic, topic_results in multi_results.items():
        print(f"Results for '{topic}':")
        if topic_results.get("status") == "success":
            for i, item in enumerate(topic_results['items'], 1):
                print(f"  {i}. {item['title']}")
        print()
    
    print("\n" + "="*50 + "\n")
    
    # Example 3: Recent news
    print("=== Recent News Example ===")
    news_results = search_recent_news("ChatGPT", 3)
    if news_results.get("status") == "success":
        print(f"Recent news about ChatGPT:")
        for i, item in enumerate(news_results['items'], 1):
            print(f"{i}. {item['title']}")
            print(f"   {item['link']}")
            print()
    else:
        print(f"News search failed: {news_results.get('message')}")
