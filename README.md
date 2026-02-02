# CalibraMark

**AI-driven prediction market analysis and trading system for Polymarket**

CalibraMark uses specialized AI agents powered by Claude to identify mispricings in prediction markets, validate edge through rigorous backtesting, and execute paper trades with comprehensive risk management.

## 🎯 Project Philosophy

**The evaluation framework is the product.** CalibraMark is built on the principle that any trading system must prove itself through honest evaluation before risking real capital. The system prioritizes:

1. **Evaluation First**: Backtesting and calibration metrics built before trading logic
2. **Statistical Rigor**: All claims of edge must be statistically significant (p < 0.05)
3. **Honest Assessment**: The system must be able to prove itself wrong
4. **Risk Management**: Multiple layers of protection (Kelly criterion, position limits, kill switch)

## 🏗️ Architecture

CalibraMark uses a three-tier architecture:

### 1. MCP Servers (Data Providers)
Independent Python processes providing tools via Model Context Protocol:
- **Polymarket Server**: Market data, prices, execution
- **News Server**: RSS feed aggregation and filtering
- **Fundamentals Server**: yfinance, SEC EDGAR, FRED API
- **OpenBB Server**: Unified financial data interface

### 2. Claude Code Skills (Reasoning Patterns)
Markdown files in `.claude/skills/` containing structured prompts:
- **probability-calibration**: Structured probability estimation with bias checks
- **kelly-criterion**: Optimal position sizing (25% fractional Kelly)
- **event-classification**: Market categorization and data source identification
- **sentiment-analysis**: News sentiment scoring with credibility assessment
- **check-status**: System status and performance metrics

### 3. Python Agents (Orchestrators)
Python scripts that coordinate the pipeline:
- **Market Scanner**: Filter markets by liquidity, resolution date, probability deviation
- **News Sentiment Agent**: Fetch news and invoke sentiment-analysis skill
- **Fundamentals Agent**: Fetch data and invoke fundamental-analysis skill
- **Calibration Agent**: Gatekeeper that synthesizes inputs and makes final decisions
- **Execution Agent**: Execute paper trades with kill switch and risk checks

## 🚀 Quick Start

### Prerequisites

- Python 3.9 or higher
- Anthropic API key
- (Optional) Polymarket API credentials for paper trading

### Installation

1. **Create and activate virtual environment**
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. **Install dependencies**
```bash
pip install -r requirements.txt
```

3. **Configure environment**
```bash
cp .env.template .env
# Edit .env and add your API keys
```

Required in `.env`:
- `ANTHROPIC_API_KEY`: Your Anthropic API key (required)

## 💡 Usage

### Check System Status

```bash
/check-status
```

Displays current bankroll, P&L, Brier score, and graduation criteria progress.

### Fetch Historical Data

```bash
python scripts/fetch_historical_data.py --start-date 2024-07-01 --end-date 2025-01-31
```

## 📈 Evaluation & Graduation Criteria

### Requirements (ALL must be met for 30 consecutive days)

1. ✅ **Brier Score < 0.15** - Well-calibrated predictions
2. ✅ **Positive P&L with p < 0.05** - Statistically significant profitability
3. ✅ **Max Drawdown < 20%** - Risk management working
4. ✅ **Win Rate > 52%** - Better than random

## ⚠️ Risk Management

- **Fractional Kelly (25%)**: Conservative position sizing
- **Max Position**: $1,000 per market
- **Max Daily Loss**: $200
- **Max Drawdown**: 20% (triggers kill switch)
- **Paper Trading First**: No real money until validated

## 📂 Development Status

### ✅ Phase 1: Foundation & Evaluation Infrastructure (COMPLETE)
- [x] Project configuration and utilities
- [x] Evaluation framework (calibration, backtesting, monitoring)
- [x] Initial Claude Code skills

### 🚧 Phase 2-5: In Progress
- [ ] MCP Servers
- [ ] Agents
- [ ] Orchestration
- [ ] Documentation

## ⚖️ Disclaimers

**CalibraMark is a research and educational project. It is NOT financial advice. You are solely responsible for any trading decisions.**

## 📄 License

MIT License