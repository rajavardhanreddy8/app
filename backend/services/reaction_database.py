import logging
from typing import List, Dict, Any
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from models.reaction_data import ReactionData, ReactionTemplate, ReagentCost
import os

logger = logging.getLogger(__name__)

class ReactionDatabase:
    """MongoDB interface for reaction data."""
    
    def __init__(self, mongo_url: str = None, db_name: str = None):
        self.mongo_url = mongo_url or os.getenv('MONGO_URL')
        self.db_name = db_name or os.getenv('DB_NAME', 'chemistry_db')
        self.client = AsyncIOMotorClient(self.mongo_url)
        self.db: AsyncIOMotorDatabase = self.client[self.db_name]
        
        # Collections
        self.reactions = self.db.reactions
        self.templates = self.db.reaction_templates
        self.costs = self.db.reagent_costs
    
    async def init_indexes(self):
        """Create database indexes for performance."""
        try:
            # Reactions indexes
            await self.reactions.create_index("reaction_type")
            await self.reactions.create_index("source")
            await self.reactions.create_index("yield_percent")
            await self.reactions.create_index("reactants")
            await self.reactions.create_index("products")
            
            # Templates indexes
            await self.templates.create_index("reaction_type")
            await self.templates.create_index("name")
            
            # Costs indexes
            await self.costs.create_index("smiles")
            await self.costs.create_index("name")
            
            logger.info("Database indexes created successfully")
        except Exception as e:
            logger.error(f"Failed to create indexes: {str(e)}")
    
    async def insert_reactions(self, reactions: List[ReactionData]) -> int:
        """Insert reactions into database."""
        try:
            if not reactions:
                return 0
            
            # Convert to dicts
            docs = [r.model_dump() for r in reactions]
            
            # Bulk insert
            result = await self.reactions.insert_many(docs, ordered=False)
            logger.info(f"Inserted {len(result.inserted_ids)} reactions")
            return len(result.inserted_ids)
            
        except Exception as e:
            logger.error(f"Failed to insert reactions: {str(e)}")
            return 0
    
    async def get_reactions_by_type(self, reaction_type: str, limit: int = 100) -> List[Dict]:
        """Get reactions by type."""
        cursor = self.reactions.find(
            {"reaction_type": reaction_type},
            {"_id": 0}
        ).limit(limit)
        return await cursor.to_list(length=limit)
    
    async def get_reactions_with_yield(self, min_yield: float = 0, limit: int = 1000) -> List[Dict]:
        """Get reactions with yield data."""
        cursor = self.reactions.find(
            {"yield_percent": {"$gte": min_yield, "$ne": None}},
            {"_id": 0}
        ).limit(limit)
        return await cursor.to_list(length=limit)
    
    async def count_reactions(self, filters: Dict = None) -> int:
        """Count reactions matching filters."""
        return await self.reactions.count_documents(filters or {})
    
    async def insert_template(self, template: ReactionTemplate) -> str:
        """Insert a reaction template."""
        try:
            doc = template.model_dump()
            result = await self.templates.insert_one(doc)
            return str(result.inserted_id)
        except Exception as e:
            logger.error(f"Failed to insert template: {str(e)}")
            return ""
    
    async def get_all_templates(self) -> List[Dict]:
        """Get all reaction templates."""
        cursor = self.templates.find({}, {"_id": 0})
        return await cursor.to_list(length=1000)
    
    async def insert_reagent_cost(self, cost: ReagentCost) -> str:
        """Insert reagent cost data."""
        try:
            doc = cost.model_dump()
            result = await self.costs.insert_one(doc)
            return str(result.inserted_id)
        except Exception as e:
            logger.error(f"Failed to insert cost: {str(e)}")
            return ""
    
    async def get_reagent_cost(self, smiles: str) -> Dict:
        """Get cost for a specific reagent."""
        return await self.costs.find_one({"smiles": smiles}, {"_id": 0})
    
    async def get_database_stats(self) -> Dict[str, int]:
        """Get database statistics."""
        return {
            "total_reactions": await self.count_reactions(),
            "reactions_with_yield": await self.count_reactions({"yield_percent": {"$ne": None}}),
            "total_templates": await self.templates.count_documents({}),
            "total_costs": await self.costs.count_documents({})
        }
