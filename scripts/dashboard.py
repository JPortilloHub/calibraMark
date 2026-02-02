"""CalibraMark Streamlit Dashboard - Performance monitoring and analysis."""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import get_settings
from utils.data_storage import DataStorage
from evaluation.paper_trading_monitor import PaperTradingMonitor
from evaluation.calibration_metrics import calculate_brier_score
from evaluation.statistical_tests import calculate_sharpe_ratio, calculate_max_drawdown


st.set_page_config(
    page_title="CalibraMark Dashboard",
    page_icon="📊",
    layout="wide",
)


@st.cache_resource
def get_storage():
    return DataStorage()


@st.cache_resource
def get_monitor():
    return PaperTradingMonitor(storage=get_storage())


def render_header():
    st.title("📊 CalibraMark Dashboard")
    st.caption("AI-Driven Prediction Market Analysis & Paper Trading")

    from utils.kill_switch import KillSwitch
    ks = KillSwitch()
    if ks.is_active():
        state = ks.get_state()
        st.error(f"⚠️ KILL SWITCH ACTIVE: {state.get('reason', 'Unknown')}")
    else:
        st.success("System Active")


def render_kpis():
    storage = get_storage()
    monitor = get_monitor()

    col1, col2, col3, col4, col5 = st.columns(5)

    bankroll = monitor.get_current_bankroll()
    settings = get_settings()
    starting = settings.paper_trading_starting_bankroll
    pnl = bankroll - starting

    with col1:
        st.metric("Bankroll", f"${bankroll:,.2f}", f"${pnl:+,.2f}")
    with col2:
        peak = monitor.get_peak_bankroll()
        dd = monitor.calculate_current_drawdown()
        st.metric("Drawdown", f"{dd:.1f}%", delta_color="inverse")
    with col3:
        trades = storage.get_all_trades()
        st.metric("Total Trades", len(trades))
    with col4:
        open_trades = storage.get_open_trades()
        st.metric("Open Positions", len(open_trades))
    with col5:
        closed = [t for t in trades if t.get("status") == "CLOSED"]
        if closed:
            wins = sum(1 for t in closed if (t.get("pnl") or 0) > 0)
            rate = wins / len(closed) * 100
            st.metric("Win Rate", f"{rate:.1f}%")
        else:
            st.metric("Win Rate", "N/A")


def render_trade_history():
    st.subheader("Trade History")

    storage = get_storage()
    trades = storage.get_all_trades(limit=100)

    if not trades:
        st.info("No trades yet. Run a market scan to get started.")
        return

    df = pd.DataFrame(trades)

    # Format columns
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.strftime("%Y-%m-%d %H:%M")
    if "entry_price" in df.columns:
        df["entry_price"] = df["entry_price"].apply(lambda x: f"{x:.2%}" if x else "")
    if "agent_probability" in df.columns:
        df["agent_probability"] = df["agent_probability"].apply(lambda x: f"{x:.2%}" if x else "")
    if "position_size" in df.columns:
        df["position_size"] = df["position_size"].apply(lambda x: f"${x:.2f}" if x else "")
    if "pnl" in df.columns:
        df["pnl"] = df["pnl"].apply(lambda x: f"${x:+.2f}" if x is not None else "")

    display_cols = [
        c for c in ["timestamp", "market_question", "side", "position_size",
                     "entry_price", "agent_probability", "pnl", "status"]
        if c in df.columns
    ]

    st.dataframe(df[display_cols], use_container_width=True, hide_index=True)


def render_calibration():
    st.subheader("Calibration Analysis")

    storage = get_storage()
    history = storage.get_calibration_history(days=30)

    if not history:
        st.info("No calibration data yet. Complete some trades to see calibration metrics.")
        return

    df = pd.DataFrame(history)

    col1, col2 = st.columns(2)

    with col1:
        st.line_chart(df.set_index("date")["brier_score"], y_label="Brier Score")
        latest = df.iloc[0]["brier_score"]
        target = 0.15
        st.caption(f"Latest Brier Score: {latest:.4f} (target < {target})")

    with col2:
        st.line_chart(df.set_index("date")["win_rate"], y_label="Win Rate")


def render_graduation_criteria():
    st.subheader("Graduation Criteria")

    monitor = get_monitor()
    metrics = monitor.get_performance_metrics()

    criteria = {
        "30 Days Trading": {
            "current": metrics.get("trading_days", 0),
            "target": 30,
            "unit": "days",
        },
        "Brier Score < 0.15": {
            "current": metrics.get("brier_score", 1.0),
            "target": 0.15,
            "unit": "",
            "lower_is_better": True,
        },
        "Positive P&L (p < 0.05)": {
            "current": metrics.get("pnl_pvalue", 1.0),
            "target": 0.05,
            "unit": "",
            "lower_is_better": True,
        },
        "Max Drawdown < 20%": {
            "current": metrics.get("max_drawdown", 0),
            "target": 20.0,
            "unit": "%",
            "lower_is_better": True,
        },
        "Win Rate > 52%": {
            "current": metrics.get("win_rate", 0) * 100,
            "target": 52.0,
            "unit": "%",
        },
    }

    for name, criterion in criteria.items():
        current = criterion["current"]
        target = criterion["target"]
        lower_better = criterion.get("lower_is_better", False)

        if lower_better:
            met = current <= target
        else:
            met = current >= target

        icon = "✅" if met else "❌"
        st.write(f"{icon} **{name}**: {current:.2f}{criterion['unit']} (target: {target}{criterion['unit']})")


def render_open_positions():
    st.subheader("Open Positions")

    storage = get_storage()
    open_trades = storage.get_open_trades()

    if not open_trades:
        st.info("No open positions.")
        return

    df = pd.DataFrame(open_trades)
    display_cols = [c for c in ["market_question", "side", "position_size", "entry_price", "agent_probability", "expected_value"]
                    if c in df.columns]
    st.dataframe(df[display_cols], use_container_width=True, hide_index=True)


def main():
    render_header()
    st.divider()
    render_kpis()
    st.divider()

    tab1, tab2, tab3, tab4 = st.tabs(["Trade History", "Open Positions", "Calibration", "Graduation"])

    with tab1:
        render_trade_history()
    with tab2:
        render_open_positions()
    with tab3:
        render_calibration()
    with tab4:
        render_graduation_criteria()


if __name__ == "__main__":
    main()
