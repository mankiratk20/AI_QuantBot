"""
High-Performance REST API & Server-Sent Events (SSE) Streaming Engine.
Serves all 15 Trading Terminal views, connects the deterministic strategy engine,
executes orders, monitors risk, and broadcasts real-time prices & alerts.
"""

import os
import json
import time
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from flask import Flask, request, jsonify, Response, send_from_directory, render_template, session

from backend.config import BASE_DIR, INSTRUMENT_SPECS, TIMEFRAMES, DEFAULT_RISK_CONFIG, PROP_FIRM_PRESETS
from backend.storage.db import init_db, get_connection, log_audit
from backend.core.auth_manager import AuthManager
from backend.core.market_data import MarketDataEngine
from backend.core.smc_engine import analyze_market_state
from backend.core.strategy_builder import StrategyEngine
from backend.core.risk_engine import RiskManager
from backend.core.prop_firm_guard import PropFirmGuard
from backend.core.economic_calendar import EconomicCalendar
from backend.core.broker_adapters.paper_broker import PaperBroker
from backend.core.broker_adapters.mt5_adapter import MT5Adapter
from backend.core.broker_adapters.binance_adapter import BinanceAdapter
from backend.core.broker_adapters.ctrader_adapter import CTraderAdapter
from backend.core.order_execution import ExecutionEngine
from backend.core.trade_monitor import TradeMonitor
from backend.core.backtester import BacktestingEngine
from backend.core.journal_analytics import JournalAnalytics
from backend.core.notifications import NotificationManager

# Initialize Database Schema
init_db()

# Core Services Instantiation
market_data = MarketDataEngine()
risk_mgr = RiskManager()
prop_firm = PropFirmGuard()
calendar = EconomicCalendar()
notif_mgr = NotificationManager()
strategy_engine = StrategyEngine()
backtester = BacktestingEngine()
journal_analytics = JournalAnalytics()

# Active Broker Setup (Default to realistic Paper Broker simulator)
paper_broker = PaperBroker(initial_balance=10000.0)
mt5_broker = MT5Adapter()
binance_broker = BinanceAdapter()
ctrader_broker = CTraderAdapter()

active_broker = paper_broker

execution_engine = ExecutionEngine(
    broker=active_broker,
    risk_manager=risk_mgr,
    prop_firm_guard=prop_firm,
    economic_calendar=calendar,
    trading_mode="semi_automatic"  # semi_automatic by default; automatic is strictly disabled by default
)
trade_monitor = TradeMonitor(broker=active_broker)

# Flask Application Definition
frontend_dir = os.path.join(BASE_DIR, "frontend")
template_dir = os.path.join(frontend_dir, "templates")
static_dir = os.path.join(frontend_dir, "static")

app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)
app.secret_key = "smart-trading-bot-super-secure-key"

auth_mgr = AuthManager()

def get_current_user_id() -> Optional[str]:
    """Resolves authenticated user ID from Authorization header, query param, custom header, or session."""
    auth_header = request.headers.get("Authorization", "")
    token = None
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
    elif request.args.get("token"):
        token = request.args.get("token")

    if token:
        payload = auth_mgr.verify_token(token)
        if payload and "uid" in payload:
            return payload["uid"]
    if request.headers.get("X-User-Id"):
        return request.headers.get("X-User-Id")
    return session.get("user_id")

def get_current_user() -> Optional[Dict[str, Any]]:
    uid = get_current_user_id()
    if uid:
        return auth_mgr.get_user_by_id(uid)
    return None

def ensure_authenticated():
    uid = get_current_user_id()
    if not uid:
        return None, (jsonify({"success": False, "error": "Unauthorized. Please sign in to access terminal data."}), 401)
    return uid, None

# 0. User Authentication & Profile Endpoints
@app.route("/api/auth/register", methods=["POST"])
def auth_register():
    data = request.json or {}
    username = data.get("username", "")
    email = data.get("email", "")
    password = data.get("password", "")
    allow_example = data.get("allow_example_domains", False) or app.config.get("TESTING", False)

    ok, msg, res_data = auth_mgr.register(username, email, password, allow_example_domains=allow_example)
    if not ok:
        return jsonify({"success": False, "message": msg, "error": msg}), 400

    return jsonify({"success": True, "message": msg, **res_data}), 201

@app.route("/api/auth/confirm-signup", methods=["POST"])
def auth_confirm_signup():
    data = request.json or {}
    email = data.get("email", "")
    otp_code = data.get("otp_code", "")

    ok, msg, user = auth_mgr.confirm_signup(email, otp_code)
    if not ok:
        return jsonify({"success": False, "message": msg, "error": msg}), 400

    return jsonify({"success": True, "message": msg, "user": user}), 200

@app.route("/api/auth/resend-signup-otp", methods=["POST"])
def auth_resend_signup_otp():
    data = request.json or {}
    email = data.get("email", "")
    ok, msg, _ = auth_mgr.resend_signup_otp(email)
    if not ok:
        return jsonify({"success": False, "message": msg, "error": msg}), 400
    return jsonify({"success": True, "message": msg}), 200

@app.route("/api/auth/login", methods=["POST"])
def auth_login():
    data = request.json or {}
    ident = data.get("username", "") or data.get("email", "")
    password = data.get("password", "")

    ok, msg, res_data = auth_mgr.initiate_login(ident, password)
    if not ok:
        status_code = 403 if res_data and res_data.get("requires_confirmation") else 401
        return jsonify({"success": False, "message": msg, "error": msg, **(res_data or {})}), status_code

    return jsonify({"success": True, "message": msg, **res_data}), 200

@app.route("/api/auth/verify-login-otp", methods=["POST"])
def auth_verify_login_otp():
    data = request.json or {}
    session_token = data.get("session_token", "")
    otp_code = data.get("otp_code", "")

    ok, msg, user = auth_mgr.verify_login_otp(session_token, otp_code)
    if not ok:
        return jsonify({"success": False, "message": msg, "error": msg}), 400

    session["user_id"] = user["id"]
    return jsonify({"success": True, "message": msg, "user": user, "token": user.get("token")}), 200

@app.route("/api/auth/resend-login-otp", methods=["POST"])
def auth_resend_login_otp():
    data = request.json or {}
    session_token = data.get("session_token", "")
    ok, msg, _ = auth_mgr.resend_login_otp(session_token)
    if not ok:
        return jsonify({"success": False, "message": msg, "error": msg}), 400
    return jsonify({"success": True, "message": msg}), 200

@app.route("/api/auth/forgot-password", methods=["POST"])
def auth_forgot_password():
    data = request.json or {}
    email_or_user = data.get("email", "") or data.get("username", "")
    ok, msg, res_data = auth_mgr.initiate_password_reset(email_or_user)
    if not ok:
        return jsonify({"success": False, "message": msg, "error": msg}), 400
    return jsonify({"success": True, "message": msg, **(res_data or {})}), 200

@app.route("/api/auth/reset-password", methods=["POST"])
def auth_reset_password():
    data = request.json or {}
    reset_token = data.get("reset_token", "")
    otp_code = data.get("otp_code", "")
    new_password = data.get("new_password", "")
    ok, msg = auth_mgr.complete_password_reset(reset_token, otp_code, new_password)
    if not ok:
        return jsonify({"success": False, "message": msg, "error": msg}), 400
    return jsonify({"success": True, "message": msg}), 200

@app.route("/api/auth/resend-reset-otp", methods=["POST"])
def auth_resend_reset_otp():
    data = request.json or {}
    reset_token = data.get("reset_token", "")
    ok, msg = auth_mgr.resend_password_reset_otp(reset_token)
    if not ok:
        return jsonify({"success": False, "message": msg, "error": msg}), 400
    return jsonify({"success": True, "message": msg}), 200

@app.route("/api/auth/save-email-settings", methods=["POST"])
def auth_save_email_settings():
    data = request.json or {}
    resend_key = (data.get("resend_api_key") or "").strip()
    brevo_key = (data.get("brevo_api_key") or "").strip()
    smtp_host = (data.get("smtp_host") or "").strip()
    smtp_port = data.get("smtp_port") or 587
    smtp_user = (data.get("smtp_user") or "").strip()
    smtp_password = (data.get("smtp_password") or "").strip()

    conn = get_connection()
    cursor = conn.cursor()

    if resend_key:
        cursor.execute(
            "INSERT INTO system_settings (key, value) VALUES ('resend_api_key', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (resend_key,)
        )
        os.environ["RESEND_API_KEY"] = resend_key

    if brevo_key:
        cursor.execute(
            "INSERT INTO system_settings (key, value) VALUES ('brevo_api_key', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (brevo_key,)
        )
        os.environ["BREVO_API_KEY"] = brevo_key

    if smtp_host and smtp_user and smtp_password:
        smtp_dict = {
            "enabled": True,
            "host": smtp_host,
            "port": int(smtp_port),
            "user": smtp_user,
            "password": smtp_password,
            "from_email": smtp_user,
            "use_ssl": int(smtp_port) == 465
        }
        cursor.execute(
            "INSERT INTO system_settings (key, value) VALUES ('smtp_settings', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (json.dumps(smtp_dict),)
        )
        os.environ["SMTP_HOST"] = smtp_host
        os.environ["SMTP_PORT"] = str(smtp_port)
        os.environ["SMTP_USER"] = smtp_user
        os.environ["SMTP_PASSWORD"] = smtp_password

    conn.commit()
    conn.close()

    # Also persist into .env file
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    env_file = os.path.join(base_dir, ".env")
    env_vars = {}
    if os.path.exists(env_file):
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    if "=" in line and not line.strip().startswith("#"):
                        k, v = line.strip().split("=", 1)
                        env_vars[k.strip()] = v.strip()
        except Exception:
            pass

    if resend_key:
        env_vars["RESEND_API_KEY"] = resend_key
    if brevo_key:
        env_vars["BREVO_API_KEY"] = brevo_key
    if smtp_host and smtp_user:
        env_vars["SMTP_HOST"] = smtp_host
        env_vars["SMTP_PORT"] = str(smtp_port)
        env_vars["SMTP_USER"] = smtp_user
        env_vars["SMTP_PASSWORD"] = smtp_password

    try:
        with open(env_file, "w", encoding="utf-8") as f:
            for k, v in env_vars.items():
                f.write(f"{k}={v}\n")
    except Exception:
        pass

    return jsonify({"success": True, "message": "Email settings saved and active!"}), 200

@app.route("/api/auth/email-settings-status", methods=["GET"])
def auth_email_settings_status():
    auth_mgr.email_service._load_env_and_settings()
    has_resend = bool(os.environ.get("RESEND_API_KEY"))
    has_brevo = bool(os.environ.get("BREVO_API_KEY"))
    has_smtp = bool(os.environ.get("SMTP_HOST") and os.environ.get("SMTP_USER"))
    return jsonify({
        "configured": has_resend or has_brevo or has_smtp,
        "providers": {
            "resend": has_resend,
            "brevo": has_brevo,
            "smtp": has_smtp
        }
    })

@app.route("/api/auth/test-email", methods=["POST"])
def auth_test_email():
    data = request.json or {}
    to_email = (data.get("email") or "").strip()
    if not to_email:
        return jsonify({"success": False, "message": "Recipient email address is required.", "error": "Recipient email required."}), 400

    ok, msg, meta = auth_mgr.email_service.send_email(
        to_email,
        "🧪 Quant Trading Bot - Test Email",
        f"Hello,\n\nThis is a live test email from your AI Quant Trading Terminal.\nIf you received this message, your outgoing email dispatcher is configured correctly and ready to deliver OTP codes!\n\nTimestamp: {datetime.now(timezone.utc).isoformat()}",
        f"""<div style="background-color:#0b132b; color:#f8fafc; font-family:'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; padding:24px; border-radius:10px; max-width:480px; margin:auto; border:1px solid #1e293b;">
            <h2 style="color:#10b981; margin:0 0 10px 0;">✅ Test Email Succeeded!</h2>
            <p style="color:#cbd5e1; font-size:14px;">Your AI Quant Trading Terminal email dispatcher is working properly.</p>
            <p style="color:#94a3b8; font-size:12px;">Recipient: <strong>{to_email}</strong></p>
        </div>"""
    )
    if not ok:
        return jsonify({"success": False, "message": msg, "error": msg, "meta": meta}), 400
    return jsonify({"success": True, "message": msg, "meta": meta}), 200

@app.route("/api/auth/logout", methods=["POST"])
def auth_logout():
    session.pop("user_id", None)
    return jsonify({"success": True, "message": "Logged out successfully."})

@app.route("/api/auth/me", methods=["GET"])
def auth_me():
    user = get_current_user()
    if user:
        return jsonify({"authenticated": True, "user": user})
    return jsonify({"authenticated": False, "user": None})

@app.route("/")
def index():
    return render_template("index.html")

# 1. System Status & KPIs
@app.route("/api/status", methods=["GET"])
def get_system_status():
    uid, err = ensure_authenticated()
    if err:
        return err

    acc = active_broker.get_account_info()
    risk_mgr.config["account_balance"] = acc["balance"]
    risk_mgr.config["account_currency"] = acc["currency"]
    prop_firm.update_account_state(acc["balance"], acc["equity"])
    prop_metrics = prop_firm.get_metrics()
    open_positions = active_broker.get_open_positions()

    active_strats = [s for s in strategy_engine.get_all_strategies(user_id=uid) if s.get("is_active")]

    return jsonify({
        "account": acc,
        "trading_mode": execution_engine.trading_mode,
        "kill_switch_active": risk_mgr.config.get("emergency_kill_switch_active", False),
        "active_broker": acc.get("broker", "Paper Broker"),
        "active_strategy_count": len(active_strats),
        "active_strategies": [s["name"] for s in active_strats],
        "open_positions_count": len(open_positions),
        "prop_firm_summary": {
            "profile": prop_metrics["profile_name"],
            "daily_drawdown_remaining": prop_metrics["daily_drawdown_remaining"],
            "overall_drawdown_remaining": prop_metrics["overall_drawdown_remaining"],
            "is_breached": prop_metrics["is_breached"]
        },
        "server_time_utc": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
    })

# 2. Market Data Endpoints
@app.route("/api/market-data/instruments", methods=["GET"])
def get_instruments():
    return jsonify({
        "instruments": INSTRUMENT_SPECS,
        "timeframes": TIMEFRAMES
    })

@app.route("/api/market-data/quote/<symbol>", methods=["GET"])
def get_quote(symbol):
    sym = symbol.upper()
    quote = market_data.get_quote(sym)
    return jsonify(quote)

@app.route("/api/market-data/bars/<symbol>/<timeframe>", methods=["GET"])
def get_bars(symbol, timeframe):
    sym = symbol.upper()
    tf = timeframe.upper()
    limit = int(request.args.get("limit", 100))
    df = market_data.get_bars(sym, tf, limit=limit)
    return jsonify(df.to_dict(orient="records"))

@app.route("/api/market-data/analysis/<symbol>/<timeframe>", methods=["GET"])
def get_smc_analysis(symbol, timeframe):
    sym = symbol.upper()
    tf = timeframe.upper()
    df = market_data.get_bars(sym, tf, limit=120)
    analysis = analyze_market_state(df)
    return jsonify(analysis)

# 3. Strategy Builder Endpoints (With User Ownership & Privacy)
@app.route("/api/strategies", methods=["GET"])
def list_strategies():
    uid = get_current_user_id()
    return jsonify(strategy_engine.get_all_strategies(user_id=uid))

@app.route("/api/strategies", methods=["POST"])
def save_strategy():
    try:
        data = request.json or {}
        uid = get_current_user_id()
        strat_id = strategy_engine.save_strategy(data, user_id=uid)
        return jsonify({"success": True, "id": strat_id})
    except PermissionError as pe:
        return jsonify({"success": False, "error": str(pe)}), 403
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/strategies/<strat_id>", methods=["DELETE"])
def delete_strategy(strat_id):
    try:
        uid = get_current_user_id()
        deleted = strategy_engine.delete_strategy(strat_id, user_id=uid)
        if not deleted:
            return jsonify({"success": False, "error": "Strategy not found."}), 404
        return jsonify({"success": True})
    except PermissionError as pe:
        return jsonify({"success": False, "error": str(pe)}), 403
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/strategies/<strat_id>/toggle", methods=["POST"])
def toggle_strategy(strat_id):
    try:
        data = request.json or {}
        is_active = data.get("is_active", True)
        uid = get_current_user_id()
        strategy_engine.set_active_state(strat_id, is_active, user_id=uid)
        return jsonify({"success": True, "id": strat_id, "is_active": is_active})
    except PermissionError as pe:
        return jsonify({"success": False, "error": str(pe)}), 403
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# 4. Trading Signals & AI Analysis Scanner
@app.route("/api/signals", methods=["GET"])
def get_signals():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM signals ORDER BY created_at DESC LIMIT 30")
    rows = cursor.fetchall()
    signals = []
    for r in rows:
        signals.append({
            "id": r["id"],
            "strategy_id": r["strategy_id"],
            "symbol": r["symbol"],
            "timeframe": r["timeframe"],
            "direction": r["direction"],
            "entry_price": r["entry_price"],
            "stop_loss": r["stop_loss"],
            "take_profit": r["take_profit"],
            "risk_reward_ratio": r["risk_reward_ratio"],
            "position_size_lots": r["position_size_lots"],
            "confidence_score": r["confidence_score"],
            "market_structure_summary": r["market_structure_summary"],
            "status": r["status"],
            "created_at": r["created_at"]
        })
    conn.close()
    return jsonify(signals)

@app.route("/api/signals/scan", methods=["POST"])
def trigger_market_scan():
    """
    Scans active instruments using user's active strategies.
    Strictly generates signals only when all user rules are met.
    """
    active_strats = [s for s in strategy_engine.get_all_strategies() if s.get("is_active")]
    if not active_strats:
        return jsonify({"success": False, "message": "No strategies are currently active. Enable a strategy first."})

    signals_generated = []
    for strat in active_strats:
        for sym in strat.get("instruments", ["EURUSD"]):
            for tf in strat.get("timeframes", ["15M"]):
                df = market_data.get_bars(sym, tf, limit=120)
                quote = market_data.get_quote(sym)
                matched, report = strategy_engine.evaluate_strategy(strat, df, current_spread_pips=quote["spread_pips"])

                if matched:
                    # Calculate entry, SL, TP based on market structure
                    direction = report.get("direction", "BUY")
                    close_p = float(df["close"].iloc[-1])
                    spec = INSTRUMENT_SPECS[sym]
                    point_size = spec["point_size"]
                    atr_series = df["high"] - df["low"]
                    curr_atr = float(atr_series.iloc[-14:].mean())

                    sl_dist = max(spec["pip_size"] * 10, curr_atr * 1.5)
                    min_rr = strat.get("risk_settings", {}).get("min_risk_reward", 2.0)
                    tp_dist = sl_dist * min_rr

                    if direction == "BUY":
                        entry_p = close_p
                        sl_p = round(entry_p - sl_dist, spec["digits"])
                        tp_p = round(entry_p + tp_dist, spec["digits"])
                    else:
                        entry_p = close_p
                        sl_p = round(entry_p + sl_dist, spec["digits"])
                        tp_p = round(entry_p - tp_dist, spec["digits"])

                    # Confluence score
                    from backend.core.ai_explanation import calculate_confluence_score
                    score = calculate_confluence_score(
                        satisfied_conditions=report["satisfied"],
                        not_satisfied_conditions=report["not_satisfied"],
                        market_state=report["market_analysis"]
                    )

                    sig_res = execution_engine.process_strategy_signal(
                        strategy=strat,
                        symbol=sym,
                        timeframe=tf,
                        direction=direction,
                        entry_price=entry_p,
                        stop_loss=sl_p,
                        take_profit=tp_p,
                        confluence_score=score,
                        eval_report=report
                    )

                    if sig_res.get("status") in ["PENDING_APPROVAL", "SIGNAL_GENERATED", "EXECUTED"]:
                        signals_generated.append(sig_res)
                        notif_mgr.send_alert(
                            title=f"New Trade Signal: {direction} {sym}",
                            message=f"Strategy '{strat['name']}' matched on {tf}. Entry: {entry_p}, SL: {sl_p}, TP: {tp_p} ({min_rr}R). Score: {score:.1f}%",
                            category="SIGNAL",
                            level="success",
                            data=sig_res
                        )

    return jsonify({"success": True, "signals_generated_count": len(signals_generated), "signals": signals_generated})

@app.route("/api/signals/approve/<signal_id>", methods=["POST"])
def approve_signal(signal_id):
    res = execution_engine.approve_signal(signal_id)
    if res.get("success"):
        notif_mgr.send_alert("Trade Executed", f"Signal {signal_id} approved. Ticket #{res.get('ticket')}", category="EXECUTION", level="success")
    return jsonify(res)

@app.route("/api/signals/reject/<signal_id>", methods=["POST"])
def reject_signal(signal_id):
    data = request.json or {}
    res = execution_engine.reject_signal(signal_id, reason=data.get("reason", "Rejected via dashboard"))
    return jsonify(res)

# 4.5 Manual & One-Click Order Placement
@app.route("/api/trade/place", methods=["POST"])
def place_manual_order():
    """
    Direct trade execution endpoint for Order Ticket and One-Click Trading.
    Places order on active connected broker (MT5, Binance, cTrader, or Paper).
    """
    uid, err = ensure_authenticated()
    if err:
        return err

    data = request.json or {}
    symbol = data.get("symbol", "EURUSD").upper()
    direction = data.get("direction", "BUY").upper()
    order_type = data.get("order_type", "MARKET").upper()
    volume = float(data.get("volume", 0.01))
    price = float(data.get("price")) if data.get("price") else None
    sl = float(data.get("stop_loss")) if data.get("stop_loss") else None
    tp = float(data.get("take_profit")) if data.get("take_profit") else None
    comment = data.get("comment", f"User Manual Order ({uid})")

    # 1. Kill Switch Check
    if risk_mgr.config.get("emergency_kill_switch_active", False):
        return jsonify({"success": False, "error": "Emergency Kill Switch is active. Trading is locked."}), 400

    # 2. Prop firm check
    open_pos = active_broker.get_open_positions()
    prop_ok, prop_reason = prop_firm.can_open_new_trade(volume, len(open_pos))
    if not prop_ok:
        return jsonify({"success": False, "error": prop_reason}), 400

    # 3. Dispatch to active broker
    order_res = active_broker.place_order(
        symbol=symbol,
        order_type=direction if order_type == "MARKET" else f"{direction}_{order_type}",
        volume=volume,
        price=price,
        stop_loss=sl,
        take_profit=tp,
        comment=comment
    )

    if order_res.get("success"):
        ticket = order_res.get("ticket")
        fill_price = order_res.get("fill_price", price)
        log_audit(
            "MANUAL_TRADE_EXECUTED", "INFO",
            f"Manual {direction} executed: {volume} lots of {symbol} at {fill_price}. Ticket #{ticket}",
            {"ticket": ticket, "symbol": symbol, "direction": direction, "volume": volume, "sl": sl, "tp": tp, "user_id": uid}
        )
        notif_mgr.send_alert(
            title=f"Order Filled: {direction} {volume} {symbol}",
            message=f"Filled at {fill_price} on {active_broker.get_account_info().get('broker')}. Ticket #{ticket}",
            category="EXECUTION",
            level="success",
            data=order_res
        )
        return jsonify(order_res)
    else:
        err = order_res.get("error", "Order placement failed at broker")
        log_audit("MANUAL_TRADE_REJECTED", "WARNING", f"Manual order rejected: {err}")
        return jsonify({"success": False, "error": err}), 400

# 5. Position Management
@app.route("/api/positions", methods=["GET"])
def get_positions():
    uid, err = ensure_authenticated()
    if err:
        return err
    positions = active_broker.get_open_positions()
    return jsonify(positions)

@app.route("/api/positions/close/<ticket>", methods=["POST"])
def close_position(ticket):
    uid, err = ensure_authenticated()
    if err:
        return err
    data = request.json or {}
    vol = data.get("volume")
    res = active_broker.close_position(ticket, volume=vol, close_reason=f"User Close ({uid})")
    return jsonify(res)

@app.route("/api/positions/modify/<ticket>", methods=["POST"])
def modify_position(ticket):
    uid, err = ensure_authenticated()
    if err:
        return err
    data = request.json or {}
    sl = data.get("stop_loss")
    tp = data.get("take_profit")
    success = active_broker.modify_order(ticket, stop_loss=sl, take_profit=tp)
    return jsonify({"success": success, "ticket": ticket})

@app.route("/api/positions/close-all", methods=["POST"])
def emergency_close_all():
    uid, err = ensure_authenticated()
    if err:
        return err
    open_pos = active_broker.get_open_positions()
    closed = []
    for p in open_pos:
        r = active_broker.close_position(p["ticket"], close_reason=f"Emergency Close All ({uid})")
        closed.append(r)
    log_audit("EMERGENCY_CLOSE_ALL", "WARNING", f"User {uid} closed all {len(closed)} open positions immediately.")
    notif_mgr.send_alert("Emergency Close All", f"All {len(closed)} positions were forcibly closed.", category="RISK", level="danger")
    return jsonify({"success": True, "closed_count": len(closed), "results": closed})

# 6. Prop Firm Protection Mode
@app.route("/api/prop-firm", methods=["GET"])
def get_prop_firm_status():
    uid, err = ensure_authenticated()
    if err:
        return err
    acc = active_broker.get_account_info()
    prop_firm.update_account_state(acc.get("balance", 10000.0), acc.get("equity", 10000.0))
    metrics = prop_firm.get_metrics()
    metrics["connected_broker"] = acc.get("broker", "Paper Simulator")
    metrics["connected_balance"] = acc.get("balance", 10000.0)
    metrics["connected_equity"] = acc.get("equity", 10000.0)
    metrics["connected_currency"] = acc.get("currency", "USD")
    return jsonify(metrics)

@app.route("/api/prop-firm/profile", methods=["POST"])
def set_prop_firm_profile():
    uid, err = ensure_authenticated()
    if err:
        return err
    data = request.json or {}
    profile_name = data.get("profile_name", "FTMO Standard")
    starting_balance = float(data.get("starting_balance", 10000.0))
    custom_rules = data.get("custom_rules")
    prop_firm.set_profile(profile_name, starting_balance, custom_rules)
    return jsonify({"success": True, "metrics": prop_firm.get_metrics()})

@app.route("/api/prop-firm/sync", methods=["POST"])
def sync_prop_firm_with_account():
    uid, err = ensure_authenticated()
    if err:
        return err
    data = request.json or {}
    acc = active_broker.get_account_info()
    server = data.get("server") or ""
    metrics = prop_firm.sync_with_connected_account(
        broker_name=acc.get("broker", "Paper Simulator"),
        balance=acc.get("balance", 10000.0),
        equity=acc.get("equity", 10000.0),
        server=server,
        currency=acc.get("currency", "USD")
    )
    return jsonify({
        "success": True,
        "message": f"Prop firm mode matched to connected account (${metrics['starting_balance']:,.2f} Challenge Size)",
        "metrics": metrics
    })

# 7. Economic News Calendar (Forex Factory Integration)
@app.route("/api/economic-calendar", methods=["GET"])
def get_calendar():
    sym = request.args.get("symbol")
    base = sym[:3] if sym and len(sym) >= 3 else None
    quote = sym[3:6] if sym and len(sym) >= 6 else None
    currency = request.args.get("currency")
    impact = request.args.get("impact")

    if currency and currency.upper() != "ALL":
        base = currency.upper()
        quote = None

    events = calendar.get_upcoming_events(base, quote, min_impact=impact)
    return jsonify({
        "events": events,
        "total_count": len(events),
        "source": "Forex Factory",
        "config": {
            "pre_news_buffer_minutes": calendar.pre_news_buffer_minutes,
            "post_news_buffer_minutes": calendar.post_news_buffer_minutes,
            "block_high_impact": calendar.block_high_impact,
            "block_medium_impact": calendar.block_medium_impact
        }
    })

@app.route("/api/economic-calendar/refresh", methods=["POST"])
def refresh_calendar_feed():
    synced = calendar.sync_live_forex_factory_feed(force=True)
    events = calendar.get_upcoming_events()
    return jsonify({
        "success": True,
        "synced": synced,
        "count": len(events),
        "message": f"Successfully synced {len(events)} real-world news events from Forex Factory."
    })

@app.route("/api/economic-calendar/config", methods=["POST"])
def configure_calendar():
    data = request.json or {}
    calendar.configure(
        pre_mins=int(data.get("pre_news_buffer_minutes", 30)),
        post_mins=int(data.get("post_news_buffer_minutes", 30)),
        block_high=bool(data.get("block_high_impact", True)),
        block_med=bool(data.get("block_medium_impact", False))
    )
    return jsonify({"success": True, "message": "News calendar blackout parameters updated."})

# 8. Backtesting Engine
@app.route("/api/backtest/run", methods=["POST"])
def run_backtest_endpoint():
    uid, err = ensure_authenticated()
    if err:
        return err
    try:
        data = request.json or {}
        symbol = data.get("symbol", "EURUSD")
        timeframe = data.get("timeframe", "15M")
        strategy_id = data.get("strategy_id")
        bars_count = int(data.get("bars_count", 500))

        all_strats = strategy_engine.get_all_strategies(user_id=uid)
        strategy_data = next((s for s in all_strats if s["id"] == strategy_id), None)
        if not strategy_data:
            strategy_data = all_strats[0] if all_strats else {}

        df = market_data.get_bars(symbol, timeframe, limit=bars_count)
        if len(df) < bars_count:
            quote = market_data.get_quote(symbol)
            curr_bid = quote.get("bid", 1.0850)
            df = market_data._generate_calibrated_bars(
                symbol, timeframe, bars_count=bars_count, base_price=curr_bid, target_last_price=curr_bid
            )

        result = backtester.run_backtest(
            strategy_data=strategy_data,
            df=df,
            symbol=symbol,
            timeframe=timeframe,
            starting_balance=float(data.get("starting_balance", 10000.0)),
            risk_percent=float(data.get("risk_percent", 1.0))
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e), "summary": {"total_trades": 0, "win_rate": 0, "net_profit": 0, "profit_factor": 0}, "trades": []}), 500

# 9. Trading Journal & Analytics
@app.route("/api/journal", methods=["GET"])
def get_journal():
    uid, err = ensure_authenticated()
    if err:
        return err
    limit = int(request.args.get("limit", 50))
    return jsonify(journal_analytics.get_all_entries(limit))

@app.route("/api/journal", methods=["POST"])
def add_journal_entry():
    uid, err = ensure_authenticated()
    if err:
        return err
    data = request.json or {}
    journal_analytics.record_completed_trade(
        ticket=data.get("ticket", f"TK-{int(time.time())}"),
        symbol=data.get("symbol", "EURUSD"),
        strategy_name=data.get("strategy_name", "Manual"),
        direction=data.get("direction", "BUY"),
        entry_price=float(data.get("entry_price", 1.0850)),
        exit_price=float(data.get("exit_price", 1.0870)),
        stop_loss=float(data.get("stop_loss", 1.0840)),
        take_profit=float(data.get("take_profit", 1.0870)),
        lots=float(data.get("lots", 0.1)),
        risk_percent=float(data.get("risk_percent", 1.0)),
        net_profit=float(data.get("net_profit", 20.0)),
        entry_time=data.get("entry_time", time.strftime("%Y-%m-%d %H:%M:%S")),
        exit_time=data.get("exit_time", time.strftime("%Y-%m-%d %H:%M:%S")),
        entry_reason=data.get("entry_reason", "Strategy rule compliance"),
        exit_reason=data.get("exit_reason", "Take profit target reached"),
        market_conditions=data.get("market_conditions", "Normal volatility"),
        lessons_learned=data.get("lessons_learned", "Followed trading plan"),
        tags=data.get("tags", ["PlanFollowed"])
    )
    return jsonify({"success": True})

@app.route("/api/analytics", methods=["GET"])
def get_analytics():
    uid, err = ensure_authenticated()
    if err:
        return err
    return jsonify(journal_analytics.get_performance_analytics())

# 10. Notifications & Audit Logs
@app.route("/api/notifications", methods=["GET"])
def get_notifications():
    uid, err = ensure_authenticated()
    if err:
        return err
    return jsonify(notif_mgr.get_notifications())

@app.route("/api/audit-logs", methods=["GET"])
def get_audit_logs():
    uid, err = ensure_authenticated()
    if err:
        return err
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM audit_logs ORDER BY id DESC LIMIT 50")
    rows = cursor.fetchall()
    logs = [dict(r) for r in rows]
    conn.close()
    return jsonify(logs)

# 11. Security, Kill Switch, and Mode Controls
@app.route("/api/settings/kill-switch", methods=["POST"])
def toggle_kill_switch():
    uid, err = ensure_authenticated()
    if err:
        return err
    data = request.json or {}
    active = data.get("active", True)
    if active:
        risk_mgr.trigger_emergency_kill_switch(reason=data.get("reason", f"User {uid} Triggered"))
        notif_mgr.send_alert("KILL SWITCH ACTIVATED", "Trading bot locked. All auto-executions disabled.", category="SECURITY", level="danger")
    else:
        risk_mgr.reset_kill_switch()
        notif_mgr.send_alert("Kill Switch Deactivated", f"Trading unlocked by user {uid}.", category="SECURITY", level="info")
    return jsonify({"success": True, "kill_switch_active": risk_mgr.config["emergency_kill_switch_active"]})

def load_saved_broker_config():
    """Loads saved broker credentials from system_settings and initializes active broker."""
    global active_broker
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM system_settings WHERE key = 'active_broker_config'")
        row = cursor.fetchone()
        conn.close()
        if row:
            cfg = json.loads(row["value"])
            b_type = cfg.get("broker", "paper")
            creds = cfg.get("credentials", {})
            if b_type == "mt5" and mt5_broker.mt5_lib and mt5_broker.connect(creds):
                active_broker = mt5_broker
            elif b_type == "binance" and os.environ.get("TRADING_BOT_ONLINE") == "1" and binance_broker.connect(creds):
                active_broker = binance_broker
            elif b_type == "ctrader" and os.environ.get("TRADING_BOT_ONLINE") == "1" and ctrader_broker.connect(creds):
                active_broker = ctrader_broker
            execution_engine.broker = active_broker
            trade_monitor.broker = active_broker
    except Exception as e:
        print(f"Error loading broker config: {e}")

# Only auto-connect if running live online server
if os.environ.get("TRADING_BOT_ONLINE") == "1":
    load_saved_broker_config()

@app.route("/api/broker/config", methods=["GET"])
def get_broker_config():
    uid, err = ensure_authenticated()
    if err:
        return err

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT broker, credentials FROM user_broker_configs WHERE user_id = ?", (uid,))
    row = cursor.fetchone()
    conn.close()

    if row:
        saved_broker_type = row["broker"]
        saved_cfg = {"broker": saved_broker_type, "credentials": json.loads(row["credentials"])}
    else:
        saved_broker_type = "paper"
        saved_cfg = {"broker": "paper", "credentials": {"initial_balance": 10000.0}}

    # Mask password / secret
    masked_creds = dict(saved_cfg.get("credentials", {}))
    if "password" in masked_creds:
        masked_creds["password"] = "••••••••"
    if "api_secret" in masked_creds:
        masked_creds["api_secret"] = "••••••••"

    return jsonify({
        "active_broker": active_broker.get_account_info(),
        "saved_broker_type": saved_broker_type,
        "credentials": masked_creds
    })

@app.route("/api/broker/connect", methods=["POST"])
def connect_real_broker():
    global active_broker
    uid, err = ensure_authenticated()
    if err:
        return err

    data = request.json or {}
    broker_name = data.get("broker", "paper").lower()
    credentials = data.get("credentials", {})

    success = False
    message = ""

    if broker_name == "mt5":
        if not mt5_broker.mt5_lib:
            message = "MetaTrader5 Python connector library is not installed. To connect directly to your MT5 desktop terminal, run: pip install MetaTrader5"
            return jsonify({"success": False, "message": message}), 400
        success = mt5_broker.connect(credentials)
        if success:
            active_broker = mt5_broker
            message = f"Successfully connected to MetaTrader 5 ({credentials.get('server')}) account #{credentials.get('login')}!"
        else:
            message = f"Failed to connect to MT5 server '{credentials.get('server')}'. Please check your Login ID, Password, and ensure the MT5 terminal is running."
            return jsonify({"success": False, "message": message}), 400

    elif broker_name == "binance":
        success = binance_broker.connect(credentials)
        if success:
            active_broker = binance_broker
            message = "Successfully connected to Binance Futures account!"
        else:
            message = "Failed to connect to Binance. Please verify your API Key and Secret."
            return jsonify({"success": False, "message": message}), 400

    elif broker_name == "ctrader":
        success = ctrader_broker.connect(credentials)
        if success:
            active_broker = ctrader_broker
            message = f"Successfully connected to cTrader Open API (Account #{credentials.get('account_id')})!"
        else:
            message = "Failed to connect to cTrader Open API. Please verify Client ID and Secret."
            return jsonify({"success": False, "message": message}), 400

    else:
        # Paper broker
        bal = float(credentials.get("initial_balance", 10000.0))
        paper_broker.balance = bal
        paper_broker.initial_balance = bal
        paper_broker.equity = bal
        active_broker = paper_broker
        success = True
        message = f"Switched to Paper Trading Simulator with ${bal:,.2f} initial balance."

    execution_engine.broker = active_broker
    trade_monitor.broker = active_broker
    acc = active_broker.get_account_info()
    risk_mgr.config["account_balance"] = acc.get("balance", 10000.0)
    risk_mgr.config["account_currency"] = acc.get("currency", "USD")
    prop_firm.sync_with_connected_account(
        broker_name=acc.get("broker", broker_name),
        balance=acc.get("balance", 10000.0),
        equity=acc.get("equity", 10000.0),
        server=credentials.get("server", ""),
        currency=acc.get("currency", "USD")
    )
    market_data.set_broker(active_broker)

    # Save to user_broker_configs table specifically for this user
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO user_broker_configs (user_id, broker, credentials, updated_at)
        VALUES (?, ?, ?, ?)
    """, (uid, broker_name, json.dumps(credentials), datetime.now().isoformat()))
    conn.commit()
    conn.close()

    log_audit("REAL_BROKER_CONNECTED", "INFO", message, {"broker": broker_name, "user_id": uid})
    notif_mgr.send_alert("Broker Connected", message, category="BROKER", level="success")

    return jsonify({
        "success": True,
        "message": message,
        "broker": active_broker.get_account_info()
    })

@app.route("/api/broker/disconnect", methods=["POST"])
def disconnect_real_broker():
    global active_broker
    uid, err = ensure_authenticated()
    if err:
        return err

    if active_broker != paper_broker:
        active_broker.disconnect()
    active_broker = paper_broker
    execution_engine.broker = active_broker
    trade_monitor.broker = active_broker
    acc = active_broker.get_account_info()
    risk_mgr.config["account_balance"] = acc.get("balance", 10000.0)
    risk_mgr.config["account_currency"] = acc.get("currency", "USD")
    prop_firm.sync_with_connected_account(
        broker_name="Paper Broker",
        balance=acc.get("balance", 10000.0),
        equity=acc.get("equity", 10000.0),
        server="",
        currency=acc.get("currency", "USD")
    )
    market_data.set_broker(active_broker)

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO user_broker_configs (user_id, broker, credentials, updated_at)
        VALUES (?, 'paper', ?, ?)
    """, (uid, json.dumps({"initial_balance": 10000.0}), datetime.now().isoformat()))
    conn.commit()
    conn.close()

    log_audit("BROKER_DISCONNECTED", "INFO", f"User {uid} disconnected real broker; reverted to Paper Simulator.")
    return jsonify({"success": True, "broker": active_broker.get_account_info()})

@app.route("/api/settings/mode", methods=["POST"])
def set_trading_mode():
    uid, err = ensure_authenticated()
    if err:
        return err
    data = request.json or {}
    mode = data.get("mode", "semi_automatic")
    execution_engine.set_trading_mode(mode)
    notif_mgr.send_alert("Trading Mode Changed", f"Switched to {mode.upper()} mode.", category="SYSTEM", level="info")
    return jsonify({"success": True, "mode": mode})

@app.route("/api/settings/broker", methods=["POST"])
def set_active_broker():
    global active_broker
    uid, err = ensure_authenticated()
    if err:
        return err
    data = request.json or {}
    broker_name = data.get("broker", "paper").lower()
    credentials = data.get("credentials", {})

    if broker_name == "mt5":
        success = mt5_broker.connect(credentials)
        if success:
            active_broker = mt5_broker
        else:
            return jsonify({"success": False, "message": "Failed to connect to MT5. Reverting to Paper Broker."}), 400
    elif broker_name == "binance":
        success = binance_broker.connect(credentials)
        if success:
            active_broker = binance_broker
        else:
            return jsonify({"success": False, "message": "Failed to connect to Binance. Check API keys."}), 400
    elif broker_name == "ctrader":
        success = ctrader_broker.connect(credentials)
        if success:
            active_broker = ctrader_broker
        else:
            return jsonify({"success": False, "message": "Failed to connect to cTrader Open API."}), 400
    else:
        active_broker = paper_broker

    execution_engine.broker = active_broker
    trade_monitor.broker = active_broker
    acc = active_broker.get_account_info()
    risk_mgr.config["account_balance"] = acc.get("balance", 10000.0)
    risk_mgr.config["account_currency"] = acc.get("currency", "USD")
    prop_firm.sync_with_connected_account(
        broker_name=acc.get("broker", broker_name),
        balance=acc.get("balance", 10000.0),
        equity=acc.get("equity", 10000.0),
        server=credentials.get("server", ""),
        currency=acc.get("currency", "USD")
    )
    market_data.set_broker(active_broker)

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO user_broker_configs (user_id, broker, credentials, updated_at)
        VALUES (?, ?, ?, ?)
    """, (uid, broker_name, json.dumps(credentials), datetime.now().isoformat()))
    conn.commit()
    conn.close()

    log_audit("BROKER_SWITCHED", "INFO", f"Active broker changed to {active_broker.get_account_info().get('broker')} for user {uid}")
    return jsonify({"success": True, "broker": active_broker.get_account_info()})

# 12. Real-Time Server-Sent Events (SSE) Stream
@app.route("/api/stream/events")
def stream_events():
    uid = get_current_user_id()
    if not uid:
        return jsonify({"error": "Unauthorized"}), 401

    def event_stream():
        while True:
            # Update a micro-tick on active instruments
            for sym in ["EURUSD", "GBPUSD", "XAUUSD", "BTCUSD"]:
                q = market_data.update_live_tick(sym)
                # Mark-to-market open positions
                active_broker.update_live_quote(sym, q["bid"], q["ask"])

            # Run active trade monitor (break-even, partial TP, trailing SL)
            actions = trade_monitor.check_and_manage_positions(market_data)

            # Package state payload
            payload = {
                "quotes": {s: market_data.get_quote(s) for s in ["EURUSD", "GBPUSD", "XAUUSD", "BTCUSD", "US30", "GBPJPY"]},
                "account": active_broker.get_account_info(),
                "positions": active_broker.get_open_positions(),
                "actions": actions,
                "timestamp": time.time()
            }

            yield f"data: {json.dumps(payload)}\n\n"
            time.sleep(1.0)  # Stream update every 1 second

    return Response(event_stream(), mimetype="text/event-stream")

def start_server(port=5000, debug=False):
    env_port = int(os.environ.get("PORT", port))
    app.run(host="0.0.0.0", port=env_port, debug=debug, threaded=True)

if __name__ == "__main__":
    start_server()
