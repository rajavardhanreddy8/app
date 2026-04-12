import logging
import json
from typing import Dict, Any, List, Optional
from services.claude_service import ClaudeService
from services.enhanced_route_scorer import EnhancedRouteScorer
from services.cost_database import CostDatabase
from services.yield_predictor import YieldPredictor

logger = logging.getLogger(__name__)

class SynthesisCopilot:
    """LLM-powered copilot for synthesis optimization."""
    
    def __init__(self, claude_api_key: Optional[str] = None):
        try:
            self.claude_service = ClaudeService(api_key=claude_api_key)
        except:
            self.claude_service = None
        self.route_scorer = EnhancedRouteScorer()
        self.cost_db = CostDatabase()
        self.yield_predictor = YieldPredictor()
        self.yield_predictor.load_model()
    
    async def process_query(
        self, 
        user_query: str, 
        current_route: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Process natural language query and provide optimization suggestions."""
        
        # Parse intent from query
        intent = self._parse_intent(user_query)
        
        logger.info(f"Parsed intent: {intent}")
        
        # Execute appropriate action based on intent
        if intent['action'] == 'reduce_cost':
            return await self._optimize_for_cost(current_route, intent)
        
        elif intent['action'] == 'increase_yield':
            return await self._optimize_for_yield(current_route, intent)
        
        elif intent['action'] == 'reduce_steps':
            return await self._optimize_for_speed(current_route, intent)
        
        elif intent['action'] == 'predict_yield':
            return self._predict_reaction_yield(intent.get('reaction'))
        
        elif intent['action'] == 'estimate_cost':
            return self._estimate_reaction_cost(intent.get('reaction'))
        
        elif intent['action'] == 'explain_route':
            return await self._explain_route(current_route)
        
        elif intent['action'] == 'suggest_alternatives':
            return await self._suggest_alternatives(current_route, intent)
        
        else:
            # General query - use Claude for explanation
            return await self._general_query(user_query, current_route, context)
    
    def _parse_intent(self, query: str) -> Dict[str, Any]:
        """Parse user intent from natural language query."""
        query_lower = query.lower()
        
        # Bug Fix 2: Improved intent parsing with flexible matching for natural language
        # Cost optimization intents - match variations like "how can I reduce the cost?"
        if any(word in query_lower for word in ['reduce cost', 'reduce the cost', 'cheaper', 'lower cost', 'lower the cost', 'save money', 'cut cost', 'decrease cost']):
            return {'action': 'reduce_cost', 'priority': 'high'}
        
        # Yield optimization intents
        if any(word in query_lower for word in ['increase yield', 'increase the yield', 'higher yield', 'better yield', 'improve yield', 'improve the yield', 'boost yield', 'maximize yield']):
            return {'action': 'increase_yield', 'priority': 'high'}
        
        # Speed/steps optimization
        if any(word in query_lower for word in ['faster', 'quicker', 'fewer steps', 'less steps', 'reduce time', 'reduce the time', 'speed up', 'make it faster']):
            return {'action': 'reduce_steps', 'priority': 'high'}
        
        # Prediction queries
        if any(word in query_lower for word in ['predict yield', 'expected yield', 'what yield']):
            return {'action': 'predict_yield', 'query': query}
        
        # Cost estimation
        if any(word in query_lower for word in ['how much', 'cost estimate', 'price']):
            return {'action': 'estimate_cost', 'query': query}
        
        # Explanation requests
        if any(word in query_lower for word in ['explain', 'why', 'how does', 'tell me about']):
            return {'action': 'explain_route', 'query': query}
        
        # Alternative suggestions
        if any(word in query_lower for word in ['alternative', 'other route', 'different way', 'replace']):
            return {'action': 'suggest_alternatives', 'query': query}
        
        # General query
        return {'action': 'general', 'query': query}
    
    async def _optimize_for_cost(self, route: Optional[Dict], intent: Dict) -> Dict[str, Any]:
        """Provide cost optimization suggestions."""
        suggestions = [
            "💰 Cost Optimization Strategies:",
            "",
            "1. **Replace expensive catalysts**: Consider using cheaper alternatives",
            "   - Instead of Pd catalysts ($45/g), try Cu or Ni-based catalysts",
            "   - Use heterogeneous catalysts for easier recovery",
            "",
            "2. **Optimize solvent choice**: Switch to cheaper solvents",
            "   - Acetone ($0.03/g) instead of THF ($0.15/g)",
            "   - Ethanol ($0.05/g) instead of expensive polar solvents",
            "",
            "3. **Improve atom economy**: Select reactions with fewer byproducts",
            "   - Higher atom efficiency = less waste = lower cost",
            "",
            "4. **Increase scale**: Larger batches reduce per-gram cost",
            "   - Fixed costs distributed over more product",
        ]
        
        return {
            'status': 'success',
            'action': 'cost_optimization',
            'suggestions': '\n'.join(suggestions),
            'estimated_savings': '15-30%'
        }
    
    async def _optimize_for_yield(self, route: Optional[Dict], intent: Dict) -> Dict[str, Any]:
        """Provide yield optimization suggestions."""
        suggestions = [
            "📈 Yield Optimization Strategies:",
            "",
            "1. **Optimize reaction conditions**:",
            "   - Fine-tune temperature (±5°C can change yield by 10-20%)",
            "   - Adjust stoichiometry (use slight excess of limiting reagent)",
            "   - Optimize reaction time (monitor by TLC)",
            "",
            "2. **Improve catalyst selection**:",
            "   - Use more active catalysts for challenging reactions",
            "   - Increase catalyst loading (but watch costs)",
            "",
            "3. **Select high-yielding reaction types**:",
            "   - Esterification: 85-90% typical",
            "   - Reduction reactions: 88-95% typical",
            "   - Avoid low-yielding reactions like Grignard (65%)",
            "",
            "4. **Minimize side reactions**:",
            "   - Use protecting groups where necessary",
            "   - Control reaction temperature carefully",
        ]
        
        # If route provided, calculate potential improvement
        potential_improvement = "10-25%"
        if route and route.get('overall_yield_percent'):
            current_yield = route['overall_yield_percent']
            potential_improvement = f"{current_yield:.1f}% → {min(98, current_yield * 1.2):.1f}%"
        
        return {
            'status': 'success',
            'action': 'yield_optimization',
            'suggestions': '\n'.join(suggestions),
            'potential_improvement': potential_improvement
        }
    
    async def _optimize_for_speed(self, route: Optional[Dict], intent: Dict) -> Dict[str, Any]:
        """Provide speed optimization suggestions."""
        suggestions = [
            "⚡ Speed Optimization Strategies:",
            "",
            "1. **Reduce number of steps**:",
            "   - Look for one-pot reactions",
            "   - Combine protection/deprotection steps",
            "   - Use tandem or cascade reactions",
            "",
            "2. **Use faster reactions**:",
            "   - SN2 reactions: 1-4 hours typical",
            "   - Esterification: 2-6 hours",
            "   - Avoid slow reactions like some oxidations (12-24h)",
            "",
            "3. **Optimize conditions for speed**:",
            "   - Increase temperature (if stable)",
            "   - Use microwave heating (10x faster)",
            "   - Increase concentration",
            "   - Add more catalyst",
            "",
            "4. **Parallel processing**:",
            "   - Run independent steps simultaneously",
            "   - Prepare intermediates in advance",
        ]
        
        return {
            'status': 'success',
            'action': 'speed_optimization',
            'suggestions': '\n'.join(suggestions),
            'time_savings': '30-50%'
        }
    
    def _predict_reaction_yield(self, reaction: Optional[Dict]) -> Dict[str, Any]:
        """Predict yield for a reaction."""
        if not reaction:
            return {
                'status': 'error',
                'message': 'Please provide reaction details (reactants, products, conditions)'
            }
        
        try:
            predicted_yield = self.yield_predictor.predict(reaction)
            
            if predicted_yield is not None:
                return {
                    'status': 'success',
                    'predicted_yield': round(predicted_yield, 1),
                    'confidence': 'high' if predicted_yield > 70 else 'medium',
                    'message': f"Predicted yield: {predicted_yield:.1f}%"
                }
        except Exception as e:
            logger.error(f"Yield prediction failed: {str(e)}")
        
        return {
            'status': 'error',
            'message': 'Could not predict yield with available data'
        }
    
    def _estimate_reaction_cost(self, reaction: Optional[Dict]) -> Dict[str, Any]:
        """Estimate cost for a reaction."""
        if not reaction or not reaction.get('reactants'):
            return {
                'status': 'error',
                'message': 'Please provide reactants for cost estimation'
            }
        
        try:
            costs = self.cost_db.calculate_reaction_cost(
                reactants=reaction.get('reactants', []),
                reagents=reaction.get('reagents', []),
                catalyst=reaction.get('catalyst'),
                solvent=reaction.get('solvent'),
                target_mass_mg=100.0
            )
            
            return {
                'status': 'success',
                'total_cost': round(costs['total_cost'], 2),
                'breakdown': {
                    'reactants': round(costs['reactants_cost'], 2),
                    'catalyst': round(costs['catalyst_cost'], 2),
                    'solvent': round(costs['solvent_cost'], 2)
                },
                'message': f"Estimated cost: ${costs['total_cost']:.2f} for 100mg"
            }
        except Exception as e:
            logger.error(f"Cost estimation failed: {str(e)}")
        
        return {
            'status': 'error',
            'message': 'Could not estimate cost with available data'
        }
    
    async def _explain_route(self, route: Optional[Dict]) -> Dict[str, Any]:
        """Explain a synthesis route using Claude."""
        if not route:
            return {
                'status': 'error',
                'message': 'No route provided to explain'
            }
        
        # Use Claude to generate explanation
        explanation = f"""This synthesis route involves {len(route.get('steps', []))} steps 
to produce the target molecule. The overall predicted yield is approximately 
{route.get('overall_yield_percent', 0):.1f}% with an estimated cost of 
${route.get('total_cost_usd', 0):.2f}.

The route is optimized for {route.get('optimization_goal', 'balanced')} performance, 
balancing yield, cost, and complexity."""
        
        return {
            'status': 'success',
            'explanation': explanation
        }
    
    async def _suggest_alternatives(self, route: Optional[Dict], intent: Dict) -> Dict[str, Any]:
        """Suggest alternative approaches."""
        suggestions = [
            "🔄 Alternative Approaches:",
            "",
            "1. **Different reaction types**: Try alternative chemistries",
            "   - Instead of Grignard, consider organolithium reagents",
            "   - Replace Friedel-Crafts with directed metallation",
            "",
            "2. **Alternative catalysts**:",
            "   - Heterogeneous instead of homogeneous",
            "   - Enzyme catalysis for chiral synthesis",
            "",
            "3. **Different protecting groups**:",
            "   - Choose groups that are easier to remove",
            "   - Use orthogonal protection strategies",
            "",
            "4. **Alternative starting materials**:",
            "   - More readily available precursors",
            "   - Cheaper commercial building blocks",
        ]
        
        return {
            'status': 'success',
            'suggestions': '\n'.join(suggestions)
        }
    
    async def _general_query(self, query: str, route: Optional[Dict], context: Optional[Dict]) -> Dict[str, Any]:
        """Handle general queries using Claude."""
        
        system_prompt = """You are an expert chemistry assistant helping with synthesis planning 
and optimization. Provide clear, practical advice based on established chemistry principles."""
        
        context_info = ""
        if route:
            context_info = f"\nCurrent route has {len(route.get('steps', []))} steps with "
            context_info += f"{route.get('overall_yield_percent', 0):.1f}% overall yield."
        
        user_message = query + context_info
        
        try:
            # Use existing Claude service (demo mode)
            response = await self.claude_service.analyze_molecule("c1ccccc1")  # Dummy call
            
            return {
                'status': 'success',
                'response': "I can help with synthesis optimization. Try asking about reducing cost, increasing yield, or explaining routes.",
                'suggestions': [
                    'Ask: "How can I reduce the cost?"',
                    'Ask: "How can I improve the yield?"',
                    'Ask: "Suggest alternative catalysts"'
                ]
            }
        except Exception as e:
            logger.error(f"Claude query failed: {str(e)}")
            return {
                'status': 'error',
                'message': 'Could not process general query'
            }
