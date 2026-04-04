import logging
from typing import List, Dict, Any, Optional
from rdkit import Chem
from rdkit.Chem import AllChem
from models.reaction_data import ReactionData
import re

logger = logging.getLogger(__name__)

class ReactionProcessor:
    """Process and validate chemical reactions."""
    
    def __init__(self):
        self.processed_count = 0
        self.failed_count = 0
    
    def parse_reaction_smiles(self, reaction_smiles: str) -> Optional[Dict[str, List[str]]]:
        """Parse reaction SMILES into reactants, reagents, and products."""
        try:
            # Standard format: reactants>reagents>products
            parts = reaction_smiles.split('>')
            
            if len(parts) != 3:
                logger.warning(f"Invalid reaction SMILES format: {reaction_smiles}")
                return None
            
            reactants = [s.strip() for s in parts[0].split('.') if s.strip()]
            reagents = [s.strip() for s in parts[1].split('.') if s.strip()]
            products = [s.strip() for s in parts[2].split('.') if s.strip()]
            
            # Validate SMILES
            all_valid = True
            for smiles in reactants + reagents + products:
                if smiles and not Chem.MolFromSmiles(smiles):
                    all_valid = False
                    break
            
            if not all_valid:
                return None
            
            return {
                "reactants": reactants,
                "reagents": reagents,
                "products": products
            }
            
        except Exception as e:
            logger.debug(f"Failed to parse reaction SMILES: {str(e)}")
            return None
    
    def classify_reaction_type(self, reaction_smiles: str) -> str:
        """Classify reaction type based on structural changes."""
        # Simple heuristic classification
        # In production, this would use ML or rule-based classification
        
        parsed = self.parse_reaction_smiles(reaction_smiles)
        if not parsed:
            return "unknown"
        
        # Check for common patterns
        reaction_lower = reaction_smiles.lower()
        
        if 'br' in reaction_lower and 'b(o)o' in reaction_lower:
            return "Suzuki coupling"
        elif 'c(=o)cl' in reaction_lower:
            return "Acylation"
        elif 'c(=o)o' in reaction_lower and 'o' in reaction_lower:
            return "Esterification"
        elif 'n' in reaction_lower and 'c(=o)' in reaction_lower:
            return "Amidation"
        else:
            return "General transformation"
    
    def process_raw_reaction(self, raw_data: Dict[str, Any]) -> Optional[ReactionData]:
        """Process raw reaction data into ReactionData model."""
        try:
            reaction_smiles = raw_data.get('reaction_smiles', '')
            
            if not reaction_smiles:
                return None
            
            # Parse reaction
            parsed = self.parse_reaction_smiles(reaction_smiles)
            if not parsed:
                self.failed_count += 1
                return None
            
            # Create ReactionData object
            reaction_data = ReactionData(
                reaction_smiles=reaction_smiles,
                reactants=parsed['reactants'],
                products=parsed['products'],
                reagents=parsed['reagents'],
                source="USPTO",
                reaction_type=raw_data.get('reaction_type') or self.classify_reaction_type(reaction_smiles),
                yield_percent=raw_data.get('yield'),
                temperature_celsius=raw_data.get('temperature'),
                solvent=raw_data.get('solvent'),
                catalyst=raw_data.get('catalyst'),
                patent_id=raw_data.get('patent_id'),
                validated=True
            )
            
            self.processed_count += 1
            return reaction_data
            
        except Exception as e:
            logger.debug(f"Failed to process reaction: {str(e)}")
            self.failed_count += 1
            return None
    
    def process_batch(self, raw_reactions: List[Dict[str, Any]]) -> List[ReactionData]:
        """Process a batch of raw reactions."""
        processed = []
        
        for raw in raw_reactions:
            reaction = self.process_raw_reaction(raw)
            if reaction:
                processed.append(reaction)
        
        logger.info(f"Processed {len(processed)}/{len(raw_reactions)} reactions")
        logger.info(f"Total: {self.processed_count} processed, {self.failed_count} failed")
        
        return processed
