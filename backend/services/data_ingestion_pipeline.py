import logging
import asyncio
from typing import Dict, Any
from services.data_downloader import USPTODataDownloader
from services.reaction_processor import ReactionProcessor
from services.reaction_database import ReactionDatabase
from tqdm import tqdm

logger = logging.getLogger(__name__)

class DataIngestionPipeline:
    """Complete pipeline for ingesting reaction data."""
    
    def __init__(self):
        self.downloader = USPTODataDownloader()
        self.processor = ReactionProcessor()
        self.database = ReactionDatabase()
    
    async def run_ingestion(self, batch_size: int = 1000, max_reactions: int = None) -> Dict[str, Any]:
        """Run the complete data ingestion pipeline."""
        logger.info("Starting data ingestion pipeline")
        
        # Step 1: Download data
        logger.info("Step 1: Downloading USPTO dataset...")
        self.downloader.download_dataset()
        
        # Step 2: Load data
        logger.info("Step 2: Loading dataset...")
        raw_data = self.downloader.load_dataset()
        raw_reactions = raw_data.get('reactions', [])
        
        if max_reactions:
            raw_reactions = raw_reactions[:max_reactions]
        
        logger.info(f"Loaded {len(raw_reactions)} raw reactions")
        
        # Step 3: Initialize database
        logger.info("Step 3: Initializing database indexes...")
        await self.database.init_indexes()
        
        # Step 4: Process and insert in batches
        logger.info(f"Step 4: Processing reactions in batches of {batch_size}...")
        
        total_inserted = 0
        for i in tqdm(range(0, len(raw_reactions), batch_size), desc="Processing batches"):
            batch = raw_reactions[i:i + batch_size]
            
            # Process batch
            processed = self.processor.process_batch(batch)
            
            # Insert into database
            if processed:
                inserted = await self.database.insert_reactions(processed)
                total_inserted += inserted
        
        # Step 5: Get statistics
        stats = await self.database.get_database_stats()
        
        logger.info("Data ingestion complete!")
        logger.info(f"Total reactions inserted: {total_inserted}")
        logger.info(f"Database stats: {stats}")
        
        return {
            "status": "success",
            "total_processed": self.processor.processed_count,
            "total_failed": self.processor.failed_count,
            "total_inserted": total_inserted,
            "database_stats": stats
        }

async def main():
    """Run data ingestion as a standalone script."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    pipeline = DataIngestionPipeline()
    
    # Run ingestion with sample data (300 reactions)
    result = await pipeline.run_ingestion(batch_size=100, max_reactions=300)
    
    print("\n" + "="*50)
    print("Data Ingestion Summary")
    print("="*50)
    print(f"Status: {result['status']}")
    print(f"Processed: {result['total_processed']}")
    print(f"Failed: {result['total_failed']}")
    print(f"Inserted: {result['total_inserted']}")
    print(f"\nDatabase Statistics:")
    for key, value in result['database_stats'].items():
        print(f"  {key}: {value}")
    print("="*50)

if __name__ == "__main__":
    asyncio.run(main())
