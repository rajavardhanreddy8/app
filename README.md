# AI Synthesis Route Planner

An AI-powered chemistry synthesis planning platform that uses Claude Sonnet 4.5 and RDKit to generate optimal chemical synthesis routes with high yield and low cost optimization.

## 🎯 Features

- **AI-Powered Retrosynthetic Analysis**: Uses Claude Sonnet 4.5 for intelligent synthesis route planning
- **Molecular Validation**: RDKit-based SMILES validation and molecular property calculation
- **Multi-Objective Optimization**: Optimize routes for yield, cost, time, or balanced approach
- **Route Scoring**: Intelligent scoring algorithm considering yield, cost, and complexity
- **Beautiful UI**: Modern React interface with real-time validation
- **Comprehensive Analysis**: Detailed molecular properties, reaction conditions, and cost estimates

## 🏗️ Architecture

### Backend (FastAPI + Python)
- **Molecular Service**: RDKit-based molecular structure parsing and validation
- **Claude Service**: LLM orchestration for synthesis planning
- **Synthesis Planner**: Route scoring and optimization algorithms
- **Orchestrator**: Complete workflow management
- **MongoDB**: Data persistence for synthesis history

### Frontend (React + Tailwind)
- **SMILES Input**: Text-based molecular structure input with validation
- **Route Visualization**: Beautiful display of multi-step synthesis routes
- **Real-time Feedback**: Live validation and error handling
- **Responsive Design**: Works on desktop and mobile

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+
- MongoDB
- Anthropic API key (or use DEMO_MODE)

### Installation

1. **Backend Setup**
```bash
cd /app/backend
pip install -r requirements.txt
```

2. **Frontend Setup**
```bash
cd /app/frontend
yarn install
```

3. **Environment Configuration**

Backend `.env`:
```
MONGO_URL="mongodb://localhost:27017"
DB_NAME="test_database"
CORS_ORIGINS="*"
ANTHROPIC_API_KEY="your-anthropic-key-here"
DEMO_MODE="false"  # Set to "true" for demo without API key
```

Frontend `.env`:
```
REACT_APP_BACKEND_URL=http://localhost:8001
```

4. **Start Services**
```bash
# Backend
uvicorn server:app --host 0.0.0.0 --port 8001

# Frontend
yarn start
```

## 📚 API Endpoints

### Synthesis Planning
```bash
POST /api/synthesis/plan
{
  "target_smiles": "CC(=O)Oc1ccccc1C(=O)O",
  "max_steps": 5,
  "optimize_for": "balanced"  # Options: "yield", "cost", "time", "balanced"
}
```

### Molecule Validation
```bash
POST /api/molecule/validate
{
  "smiles": "CC(=O)Oc1ccccc1C(=O)O"
}
```

### Molecule Analysis
```bash
POST /api/molecule/analyze
{
  "smiles": "CC(=O)Oc1ccccc1C(=O)O"
}
```

### Synthesis History
```bash
GET /api/synthesis/history?limit=10
```

## 🧪 Example Molecules

Try these SMILES strings:

- **Aspirin**: `CC(=O)Oc1ccccc1C(=O)O`
- **Caffeine**: `CN1C=NC2=C1C(=O)N(C(=O)N2C)C`
- **Ibuprofen**: `CC(C)Cc1ccc(cc1)C(C)C(=O)O`
- **Paracetamol**: `CC(=O)Nc1ccc(O)cc1`

## 🔬 How It Works

1. **Input**: User provides target molecule in SMILES format
2. **Validation**: RDKit validates molecular structure
3. **Planning**: Claude Sonnet 4.5 generates synthesis routes using retrosynthetic analysis
4. **Scoring**: Multi-objective algorithm scores routes based on:
   - Estimated yield (product of step yields)
   - Total cost (reagent costs)
   - Number of steps (complexity)
5. **Display**: Routes ranked by optimization criteria with detailed conditions

## 📊 Technology Stack

### Core Technologies
- **FastAPI**: Modern Python web framework
- **RDKit**: Cheminformatics and molecular property calculation
- **Claude Sonnet 4.5**: AI-powered synthesis planning
- **React 19**: Frontend framework
- **MongoDB**: Document database
- **Tailwind CSS**: Styling
- **Radix UI**: Component library

### ML/AI Libraries
- **Anthropic SDK**: Claude integration
- **scikit-learn**: ML utilities
- **XGBoost**: Potential yield prediction models
- **NumPy/Pandas**: Data processing

## 🎯 Project Roadmap

### ✅ Phase 1: MVP (Current)
- [x] Basic synthesis route planning
- [x] SMILES input and validation
- [x] Multi-objective route scoring
- [x] Beautiful UI with route visualization
- [x] Claude Sonnet 4.5 integration
- [x] Demo mode for testing without API key

### 🚧 Phase 2: Data Integration (Future)
- [ ] USPTO dataset integration (1.37M reactions)
- [ ] Open Reaction Database (ORD) ingestion
- [ ] Reaction template extraction
- [ ] Historical yield database

### 🔮 Phase 3: Advanced Features (Future)
- [ ] ML-based yield prediction models
- [ ] Kinetics prediction
- [ ] Condition optimization (temperature, catalyst, solvent)
- [ ] Scale-up modeling
- [ ] Cost database with real reagent prices
- [ ] Safety and hazard assessment
- [ ] Literature citation and references

### 🎓 Phase 4: Research Features (Future)
- [ ] Fine-tuned LLM on reaction data
- [ ] GNN-based molecular embeddings
- [ ] Automated reaction mechanism prediction
- [ ] Catalyst recommendation system
- [ ] Multi-step route optimization
- [ ] Uncertainty quantification

## 🔐 Security & Best Practices

- API keys stored in environment variables
- MongoDB with proper authentication
- CORS configured for production
- Input validation on all endpoints
- Structured logging for debugging
- Error handling and graceful degradation

## 🤝 Contributing

This project is designed for chemistry research and education. Key areas for contribution:

1. **Data**: Add more reaction templates and yield data
2. **ML Models**: Improve yield and condition prediction
3. **UI/UX**: Enhance visualization and user experience
4. **Chemistry**: Add domain expertise and validation rules
5. **Testing**: Comprehensive test coverage

## 📖 Scientific Background

The system uses **retrosynthetic analysis**, a technique where chemists work backward from a target molecule to identify simpler precursors. This approach was pioneered by E.J. Corey (Nobel Prize 1990).

### Key Concepts:
- **Retrosynthesis**: Breaking complex molecules into simpler building blocks
- **Reaction Templates**: Common reaction patterns from literature
- **Multi-objective Optimization**: Balancing yield, cost, and complexity
- **Molecular Descriptors**: Physicochemical properties (MW, logP, TPSA)

## 📝 License

This project is for educational and research purposes.

## 🙏 Acknowledgments

- **Anthropic**: Claude Sonnet 4.5 LLM
- **RDKit**: Open-source cheminformatics toolkit
- **USPTO**: Patent reaction database
- **Open Reaction Database**: Community-driven reaction data
- **Chemistry Community**: For domain expertise and validation

## 📞 Support

For questions about chemistry, synthesis planning, or system usage:
- Check the API documentation
- Review example molecules
- Enable DEMO_MODE for testing

---

**Built with ❤️ for the chemistry community**

*Accelerating chemical synthesis with AI*
