"""Cosmetic search system with fuzzy matching and caching."""
import logging
import aiohttp
import difflib
from datetime import datetime, timedelta
from typing import List, Optional

from config import get_settings
from database import db, CosmeticCache

logger = logging.getLogger(__name__)

# Fortnite API endpoint for cosmetics
FORTNITE_API_URL = "https://fortnite-api.com/v2/cosmetics/br"


class CosmeticSearchService:
    """Service for searching and caching Fortnite cosmetics."""
    
    def __init__(self):
        self.settings = get_settings()
        self._cache_loaded = False
    
    async def refresh_cache(self, force: bool = False) -> bool:
        """
        Refresh cosmetic cache from Fortnite API.
        
        Args:
            force: Force refresh even if cache is recent
            
        Returns:
            True if cache was refreshed
        """
        try:
            # Check cache age
            if not force:
                cache_age = await db.get_cosmetic_cache_age()
                if cache_age:
                    age_hours = (datetime.utcnow() - cache_age).total_seconds() / 3600
                    if age_hours < self.settings.cosmetic_cache_refresh_hours:
                        logger.debug("Cosmetic cache is still fresh")
                        self._cache_loaded = True
                        return False
            
            logger.info("Refreshing cosmetic cache from Fortnite API...")
            
            async with aiohttp.ClientSession() as session:
                async with session.get(FORTNITE_API_URL) as response:
                    if response.status != 200:
                        logger.error(f"Failed to fetch cosmetics: HTTP {response.status}")
                        return False
                    
                    data = await response.json()
            
            cosmetics = data.get("data", [])
            cached_count = 0
            
            for item in cosmetics:
                cosmetic_type = self._map_type(item.get("type", {}).get("value", ""))
                if not cosmetic_type:
                    continue
                
                cache_item = CosmeticCache(
                    type=cosmetic_type,
                    cosmetic_id=item.get("id", ""),
                    name=item.get("name", "Unknown"),
                    display_name=item.get("name", "Unknown"),
                    rarity=item.get("rarity", {}).get("value", "common"),
                    description=item.get("description", ""),
                    search_text=item.get("name", "").lower()
                )
                
                await db.cache_cosmetic(cache_item)
                cached_count += 1
            
            logger.info(f"Cached {cached_count} cosmetics")
            self._cache_loaded = True
            return True
            
        except Exception as e:
            logger.error(f"Error refreshing cosmetic cache: {e}")
            return False
    
    def _map_type(self, api_type: str) -> Optional[str]:
        """Map Fortnite API type to our type."""
        type_mapping = {
            "outfit": "outfit",
            "backpack": "backpack",
            "pickaxe": "pickaxe",
            "emote": "emote",
            "emoji": "emote",
            "spray": "emote",
            "toy": "emote"
        }
        return type_mapping.get(api_type.lower())
    
    async def search(
        self,
        cosmetic_type: str,
        query: str,
        page: int = 1
    ) -> tuple[List[CosmeticCache], int, int]:
        """
        Search for cosmetics.
        
        Args:
            cosmetic_type: Type of cosmetic ('skin', 'backbling', 'pickaxe', 'emote')
            query: Search query
            page: Page number (1-indexed)
            
        Returns:
            Tuple of (results, total_count, total_pages)
        """
        # Ensure cache is loaded
        if not self._cache_loaded:
            await self.refresh_cache()
        
        per_page = self.settings.cosmetic_results_per_page
        skip = (page - 1) * per_page
        
        # Get results from database
        results = await db.search_cosmetics(
            cosmetic_type=cosmetic_type,
            query=query,
            limit=per_page,
            skip=skip
        )
        
        # Get total count for pagination
        total_count = await db.count_cosmetic_search(cosmetic_type, query)
        total_pages = (total_count + per_page - 1) // per_page
        
        # Sort by fuzzy match score and rarity
        results = self._sort_results(results, query)
        
        return results, total_count, max(1, total_pages)
    
    def _sort_results(
        self,
        results: List[CosmeticCache],
        query: str
    ) -> List[CosmeticCache]:
        """Sort results by relevance and rarity."""
        rarity_order = {
            "mythic": 0,
            "legendary": 1,
            "epic": 2,
            "rare": 3,
            "uncommon": 4,
            "common": 5
        }
        
        def score_item(item: CosmeticCache) -> tuple:
            # Fuzzy match score using difflib (higher is better, so negate for sorting)
            fuzzy_score = -difflib.SequenceMatcher(None, query.lower(), item.name.lower()).ratio() * 100
            # Exact match bonus
            exact_bonus = 0 if query.lower() in item.name.lower() else 100
            # Rarity order
            rarity = rarity_order.get(item.rarity.lower(), 6)
            return (exact_bonus, fuzzy_score, rarity)
        
        return sorted(results, key=score_item)
    
    async def get_by_id(
        self,
        cosmetic_type: str,
        cosmetic_id: str
    ) -> Optional[CosmeticCache]:
        """Get a specific cosmetic by ID."""
        return await db.get_cosmetic_by_id(cosmetic_type, cosmetic_id)
    
    async def fuzzy_search(
        self,
        cosmetic_type: str,
        query: str,
        limit: int = 10
    ) -> List[CosmeticCache]:
        """
        Perform fuzzy search with scoring.
        
        Returns top matches sorted by relevance.
        """
        # Get more results than needed for better fuzzy matching
        results, _, _ = await self.search(cosmetic_type, query, page=1)
        
        # Score and sort by fuzzy ratio using difflib
        scored = []
        for item in results:
            score = difflib.SequenceMatcher(None, query.lower(), item.name.lower()).ratio() * 100
            # Bonus for partial match
            if query.lower() in item.name.lower():
                score += 30
            scored.append((score, item))
        
        # Sort by score descending
        scored.sort(key=lambda x: x[0], reverse=True)
        
        return [item for _, item in scored[:limit]]


# Global cosmetic search service instance
cosmetic_search = CosmeticSearchService()
