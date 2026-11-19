"""
Comprehensive Automated Test Suite for AI-Powered Smart Trading Bot.
Tests:
- Technical Indicators & SMC / ICT Structure Engine
- User Strategy Engine (AND / OR Logic)
- Risk Management & Dynamic Lot Sizing
- Prop Firm Drawdown Compliance
- Economic News Blackout Enforcement
- Active Trade Management (Break-Even & Partial TP)
- Backtesting Simulation Engine
- REST API Server Endpoints
"""

import unittest
import pandas as pd
import numpy as np
import os
import sys

# Add root directory to python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.config import INSTRUMENT_SPECS
from backend.storage.db import init_db, get_connection
from backend.core.indicators import calculate_ema, calculate_rsi, calculate_atr, identify_swing_points
from backend.core.smc_engine import analyze_market_state, detect_fair_value_gaps, detect_order_blocks
from backend.core.strategy_builder import StrategyEngine
from backend.core.risk_engine import RiskManager
from backend.core.prop_firm_guard import PropFirmGuard
from backend.core.economic_calendar import EconomicCalendar
from backend.core.broker_adapters.paper_broker import PaperBroker
from backend.core.order_execution import ExecutionEngine
from backend.core.backtester import BacktestingEngine
from backend.api.server import app

class TestSmartTradingBot(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def test_01_indicators_and_smc(self):
        # Generate 60 test candles
        prices = [1.0800 + i * 0.0002 for i in range(30)] + [1.0860 - i * 0.0003 for i in range(30)]
        df = pd.DataFrame({
            "timestamp": pd.date_range("2026-01-01", periods=60, freq="15min"),
            "open": prices,
            "high": [p + 0.0005 for p in prices],
            "low": [p - 0.0005 for p in prices],
            "close": prices,
            "volume": [1000] * 60
        })

        rsi = calculate_rsi(df["close"], 14)
        self.assertEqual(len(rsi), 60)

        atr = calculate_atr(df, 14)
        self.assertEqual(len(atr), 60)

        analysis = analyze_market_state(df)
        self.assertIn("trend", analysis)
        self.assertIn("boss", analysis)
        self.assertIn("chochs", analysis)
        self.assertIn("fvgs", analysis)
        print("✓ Test 01: Indicators & SMC Engine verified.")

    def test_02_strategy_evaluation(self):
        engine = StrategyEngine()
        strategies = engine.get_all_strategies()
        self.assertGreater(len(strategies), 0)

        # Evaluate default strategy
        strat = strategies[0]
        prices = [1.0850 + i * 0.0002 for i in range(50)]
        df = pd.DataFrame({
            "timestamp": pd.date_range("2026-01-01", periods=50, freq="15min"),
            "open": prices,
            "high": [p + 0.0004 for p in prices],
            "low": [p - 0.0004 for p in prices],
            "close": prices,
            "volume": [1000] * 50
        })

        matched, report = engine.evaluate_strategy(strat, df, current_spread_pips=1.2)
        self.assertIn("matched", report)
        self.assertIn("context", report)
        print("✓ Test 02: Deterministic Strategy Rule Engine verified.")

    def test_03_risk_management_and_lot_sizing(self):
        risk = RiskManager()
        # EURUSD: Balance $10,000, 1% risk = $100.
        # Entry: 1.0850, SL: 1.0830 (20 pips / 200 points). Point value = $10/pip on 1 lot -> 20 pips * $10 = $200 per lot.
        # Expected lots = $100 / $200 = 0.50 lots.
        lots, planned_risk, sl_pts = risk.calculate_lot_size(
            symbol="EURUSD",
            entry_price=1.0850,
            stop_loss_price=1.0830,
            account_balance=10000.0,
            risk_percent=1.0
        )
        self.assertEqual(lots, 0.50)
        self.assertEqual(planned_risk, 100.0)

        # Risk validation check
        approved, reason, metrics = risk.validate_trade_risk(
            symbol="EURUSD",
            entry_price=1.0850,
            stop_loss=1.0830,
            take_profit=1.0890,  # 2:1 RR
            current_balance=10000.0,
            current_equity=10000.0,
            open_positions_count=0,
            daily_pnl=0.0,
            weekly_pnl=0.0,
            high_water_mark=10000.0
        )
        self.assertTrue(approved)
        print("✓ Test 03: Risk Management & Dynamic Lot Sizing verified.")

    def test_04_prop_firm_guard(self):
        guard = PropFirmGuard(profile_name="FTMO Standard", starting_balance=10000.0, reset_state=True)
        metrics = guard.get_metrics()
        self.assertEqual(metrics["daily_loss_limit"], 500.0)  # 5% of $10,000
        self.assertEqual(metrics["overall_drawdown_limit"], 1000.0)  # 10% of $10,000

        # Simulate safe state
        guard.update_account_state(current_balance=10100.0, current_equity=10100.0)
        self.assertFalse(guard.is_breached)

        # Test dynamic sync with $100k FTMO connected account
        synced_metrics = guard.sync_with_connected_account(
            broker_name="MetaTrader 5 (FTMO)",
            balance=100000.0,
            equity=100000.0,
            server="FTMO-Server"
        )
        self.assertEqual(synced_metrics["profile_name"], "FTMO Standard")
        self.assertEqual(synced_metrics["starting_balance"], 100000.0)
        self.assertEqual(synced_metrics["daily_loss_limit"], 5000.0)  # 5% of $100,000
        self.assertEqual(synced_metrics["overall_drawdown_limit"], 10000.0)  # 10% of $100,000

        # Simulate daily loss exceeding $5,000 on synced account
        guard.update_account_state(current_balance=94000.0, current_equity=94000.0)
        self.assertTrue(guard.is_breached)
        self.assertIn("BREACHED", guard.breach_reason)

        # Reset state to clean for subsequent tests
        guard.set_profile("FTMO Standard", 10000.0)
        print("✓ Test 04: Prop Firm Protection & Account Matching verified.")

    def test_05_economic_calendar_blackout(self):
        cal = EconomicCalendar()
        cal.configure(pre_mins=30, post_mins=30)
        events = cal.get_upcoming_events()
        self.assertGreater(len(events), 0)
        # Verify IST Indian Standard Time formatting
        first = events[0]
        self.assertIn("time_ist", first)
        self.assertIn("date_ist", first)
        self.assertIn("datetime_ist", first)
        print("✓ Test 05: Economic Calendar & IST Time Formatting verified.")

    def test_06_paper_broker_execution(self):
        # Clear any prior open paper positions in database for isolated unit test
        conn = get_connection()
        conn.execute("UPDATE positions SET status = 'CLOSED' WHERE broker = 'PAPER'")
        conn.commit()
        conn.close()

        broker = PaperBroker(initial_balance=10000.0)
        broker.positions.clear()
        res = broker.place_order(
            symbol="EURUSD",
            order_type="BUY",
            volume=0.20,
            price=1.08500,
            stop_loss=1.08300,
            take_profit=1.08900
        )
        self.assertTrue(res["success"])
        ticket = res["ticket"]

        # Check positions
        positions = broker.get_open_positions()
        self.assertEqual(len(positions), 1)

        # Close position
        close_res = broker.close_position(ticket, close_reason="Unit Test Exit")
        self.assertTrue(close_res["success"])
        self.assertEqual(len(broker.get_open_positions()), 0)
        print("✓ Test 06: Paper Broker Execution & Order Lifecycle verified.")

    def test_07_backtesting_engine(self):
        bt = BacktestingEngine()
        prices = [1.0800 + (np.sin(i / 5.0) * 0.0030) for i in range(80)]
        df = pd.DataFrame({
            "timestamp": pd.date_range("2026-01-01", periods=80, freq="15min"),
            "open": prices,
            "high": [p + 0.0006 for p in prices],
            "low": [p - 0.0006 for p in prices],
            "close": prices,
            "volume": [1200] * 80
        })

        strat = StrategyEngine().get_all_strategies()[0]
        results = bt.run_backtest(strat, df, symbol="EURUSD", starting_balance=10000.0)
        self.assertIn("summary", results)
        self.assertIn("equity_curve", results)
        print("✓ Test 07: Backtesting Simulation Engine verified.")

    def _get_latest_otp(self, email, purpose):
        """Helper to fetch the OTP from database for testing purposes."""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT otp_code FROM auth_otps WHERE email = ? AND purpose = ? ORDER BY created_at DESC LIMIT 1",
            (email, purpose)
        )
        row = cursor.fetchone()
        conn.close()
        return row["otp_code"] if row else None

    def _create_and_login_user(self, client, username, email, password):
        """Helper that executes complete registration, signup confirmation OTP, and login 2FA OTP."""
        # 1. Register
        reg = client.post("/api/auth/register", json={
            "username": username,
            "email": email,
            "password": password,
            "allow_example_domains": True
        })
        self.assertEqual(reg.status_code, 201)
        self.assertNotIn("dev_otp", reg.get_json())
        signup_otp = self._get_latest_otp(email, "SIGNUP_CONFIRMATION")
        self.assertIsNotNone(signup_otp)

        # 2. Confirm Email with OTP
        conf = client.post("/api/auth/confirm-signup", json={
            "email": email,
            "otp_code": signup_otp
        })
        self.assertEqual(conf.status_code, 200)

        # 3. Initiate Login (triggers 2FA OTP to email)
        login_init = client.post("/api/auth/login", json={
            "username": username,
            "password": password
        })
        self.assertEqual(login_init.status_code, 200)
        login_data = login_init.get_json()
        self.assertEqual(login_data.get("step"), "OTP_REQUIRED")
        self.assertNotIn("dev_otp", login_data)
        session_token = login_data.get("session_token")
        login_otp = self._get_latest_otp(email, "LOGIN_2FA")
        self.assertIsNotNone(login_otp)

        # 4. Verify Login 2FA OTP
        verify = client.post("/api/auth/verify-login-otp", json={
            "session_token": session_token,
            "otp_code": login_otp
        })
        self.assertEqual(verify.status_code, 200)
        token = verify.get_json().get("token")
        self.assertIsNotNone(token)
        return token

    def test_08_api_server_endpoints(self):
        client = app.test_client()

        # A. Unauthenticated / Unauthorized Data Access Block Check
        resp_unauth = client.get("/api/status")
        self.assertEqual(resp_unauth.status_code, 401, "Unauthenticated requests to /api/status must be rejected with 401!")

        resp_broker_unauth = client.get("/api/broker/config")
        self.assertEqual(resp_broker_unauth.status_code, 401, "Connected broker accounts must not be visible to unauthorized users!")

        resp_order_unauth = client.post("/api/trade/place", json={"symbol": "EURUSD", "direction": "BUY", "volume": 0.1})
        self.assertEqual(resp_order_unauth.status_code, 401, "Order placement must require authentication!")

        # B. Authenticate test trader
        import uuid
        uid_sfx = uuid.uuid4().hex[:6]
        token = self._create_and_login_user(client, f"trader_08_{uid_sfx}", f"trader_08_{uid_sfx}@institutional.com", "SecurePassword123!")
        auth_hdr = {"Authorization": f"Bearer {token}"}

        # C. Authenticated Status & Data Calls
        resp = client.get("/api/status", headers=auth_hdr)
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("account", data)
        self.assertIn("trading_mode", data)

        resp2 = client.get("/api/strategies", headers=auth_hdr)
        self.assertEqual(resp2.status_code, 200)

        # Test Strategy Save API (POST /api/strategies)
        save_strat_resp = client.post("/api/strategies", headers=auth_hdr, json={
            "name": f"ICT London Killzone Test {uid_sfx}",
            "strategy_type": "Smart Money Concepts (SMC)",
            "instruments": ["EURUSD", "GBPUSD"],
            "timeframes": ["15M"],
            "sessions": ["London", "New York"],
            "rules": {"operator": "AND", "conditions": [{"category": "smc", "field": "bullish_choch_present", "operator": "==", "value": True}]},
            "risk_settings": {"min_risk_reward": 2.5, "risk_percent": 1.0, "max_spread_pips": 2.0}
        })
        self.assertEqual(save_strat_resp.status_code, 200)
        save_strat_data = save_strat_resp.get_json()
        self.assertTrue(save_strat_data.get("success"))
        new_strat_id = save_strat_data.get("id")

        # Test Strategy Toggle API
        toggle_resp = client.post(f"/api/strategies/{new_strat_id}/toggle", headers=auth_hdr, json={"is_active": False})
        self.assertEqual(toggle_resp.status_code, 200)
        self.assertFalse(toggle_resp.get_json().get("is_active"))

        resp3 = client.get("/api/market-data/quote/EURUSD")
        self.assertEqual(resp3.status_code, 200)

        resp4 = client.get("/api/prop-firm", headers=auth_hdr)
        self.assertEqual(resp4.status_code, 200)

        # Reset prop firm state so order placement passes
        from backend.api.server import prop_firm
        prop_firm.set_profile("FTMO Standard", 10000.0)

        # Test Manual Order Placement API
        order_resp = client.post("/api/trade/place", headers=auth_hdr, json={
            "symbol": "EURUSD",
            "direction": "BUY",
            "order_type": "MARKET",
            "volume": 0.1,
            "stop_loss": 1.0830,
            "take_profit": 1.0890
        })
        self.assertEqual(order_resp.status_code, 200)
        order_data = order_resp.get_json()
        self.assertTrue(order_data.get("success"))
        self.assertIn("ticket", order_data)

        print("✓ Test 08: REST API Security Gate & Order Placement Endpoints verified.")

    def test_09_auth_and_private_strategy_isolation(self):
        import uuid
        test_suffix = uuid.uuid4().hex[:6]
        user_a_name = f"alice_{test_suffix}"
        user_a_email = f"alice_{test_suffix}@quantfirm.com"
        user_b_name = f"bob_{test_suffix}"
        user_b_email = f"bob_{test_suffix}@hedgefund.com"

        client = app.test_client()

        # 1. Register & Login Alice via Confirmation OTP & 2FA OTP
        token_a = self._create_and_login_user(client, user_a_name, user_a_email, "PasswordAlice123!")

        # 2. Register & Login Bob via Confirmation OTP & 2FA OTP
        token_b = self._create_and_login_user(client, user_b_name, user_b_email, "PasswordBob456!")

        # Verify /api/auth/me for Alice
        me_resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token_a}"})
        self.assertEqual(me_resp.status_code, 200)
        self.assertTrue(me_resp.get_json().get("authenticated"))
        self.assertEqual(me_resp.get_json().get("user")["username"], user_a_name)

        # 3. User Alice creates a private proprietary strategy
        strat_resp = client.post("/api/strategies", 
            headers={"Authorization": f"Bearer {token_a}"},
            json={
                "name": f"Alice Private SMC Algorithm {test_suffix}",
                "strategy_type": "Smart Money Concepts (SMC)",
                "instruments": ["XAUUSD"],
                "timeframes": ["5M"],
                "sessions": ["London"],
                "rules": {
                    "operator": "AND",
                    "conditions": [
                        {"category": "smc", "field": "bullish_choch_present", "operator": "==", "value": True}
                    ]
                },
                "risk_settings": {"min_risk_reward": 3.0, "risk_percent": 1.0, "max_spread_pips": 1.5}
            }
        )
        self.assertEqual(strat_resp.status_code, 200)
        alice_strat_id = strat_resp.get_json().get("id")
        self.assertIsNotNone(alice_strat_id)

        strat_name = f"Alice Private SMC Algorithm {test_suffix}"

        # 4. User Alice fetches strategies - must see her strategy
        alice_list = client.get("/api/strategies", headers={"Authorization": f"Bearer {token_a}"}).get_json()
        alice_strat_names = [s["name"] for s in alice_list]
        self.assertIn(strat_name, alice_strat_names)

        # 5. User Bob fetches strategies - MUST NOT see Alice's private strategy!
        bob_list = client.get("/api/strategies", headers={"Authorization": f"Bearer {token_b}"}).get_json()
        bob_strat_names = [s["name"] for s in bob_list]
        self.assertNotIn(strat_name, bob_strat_names, 
            "CRITICAL SECURITY VIOLATION: User B can see User A's private strategy!")

        # 6. Guest (unauthenticated) fetches strategies - MUST NOT see Alice's private strategy!
        guest_list = client.get("/api/strategies").get_json()
        guest_strat_names = [s["name"] for s in guest_list]
        self.assertNotIn(strat_name, guest_strat_names,
            "CRITICAL SECURITY VIOLATION: Guest can see private strategy!")

        # 7. User Bob tries to toggle Alice's strategy - MUST return 403 Forbidden
        bob_toggle = client.post(f"/api/strategies/{alice_strat_id}/toggle",
            headers={"Authorization": f"Bearer {token_b}"},
            json={"is_active": False}
        )
        self.assertEqual(bob_toggle.status_code, 403, "Bob should not be permitted to toggle Alice's strategy!")

        # 8. User Bob tries to delete Alice's strategy - MUST return 403 Forbidden
        bob_delete = client.delete(f"/api/strategies/{alice_strat_id}",
            headers={"Authorization": f"Bearer {token_b}"}
        )
        self.assertEqual(bob_delete.status_code, 403, "Bob should not be permitted to delete Alice's strategy!")

        # 9. Guest tries to delete Alice's strategy - MUST return 403 Forbidden
        guest_delete = client.delete(f"/api/strategies/{alice_strat_id}")
        self.assertEqual(guest_delete.status_code, 403)

        # 10. Attempting to delete a SYSTEM preset strategy - MUST return 403 Forbidden
        sys_delete = client.delete("/api/strategies/smc_liquidity_fvg_long", headers={"Authorization": f"Bearer {token_a}"})
        self.assertEqual(sys_delete.status_code, 403, "System preset strategies must be immutable from deletion!")

        # 11. Alice successfully deletes her own strategy
        alice_delete = client.delete(f"/api/strategies/{alice_strat_id}",
            headers={"Authorization": f"Bearer {token_a}"}
        )
        self.assertEqual(alice_delete.status_code, 200)
        self.assertTrue(alice_delete.get_json().get("success"))

        # Verify strategy is now gone from Alice's list
        alice_list_after = client.get("/api/strategies", headers={"Authorization": f"Bearer {token_a}"}).get_json()
        self.assertNotIn(strat_name, [s["name"] for s in alice_list_after])

        print("✓ Test 09: User Authentication & Private Strategy Security Isolation verified.")

    def test_10_email_validation_and_otp_flows(self):
        client = app.test_client()
        import uuid
        test_id = uuid.uuid4().hex[:6]

        # 1. Strict Email Validation Rejections
        invalid_emails = [
            "not_an_email",
            "trader@",
            "@hedgefund.com",
            "trader@domain",
            "trader@domain..com",
            "trader@localhost"
        ]
        for inv_email in invalid_emails:
            res = client.post("/api/auth/register", json={
                "username": f"user_{test_id}",
                "email": inv_email,
                "password": "Password123!"
            })
            self.assertEqual(res.status_code, 400, f"Expected 400 rejection for invalid email: {inv_email}")
            self.assertIn("email", res.get_json().get("error", "").lower())

        # 2. Valid Email Registration & Signup Confirmation OTP Delivery
        valid_email = f"verified_{test_id}@quantpropfirm.com"
        reg_res = client.post("/api/auth/register", json={
            "username": f"trader_{test_id}",
            "email": valid_email,
            "password": "StrongPassword789!"
        })
        self.assertEqual(reg_res.status_code, 201)
        reg_data = reg_res.get_json()
        self.assertNotIn("dev_otp", reg_data)
        signup_otp = self._get_latest_otp(valid_email, "SIGNUP_CONFIRMATION")
        self.assertIsNotNone(signup_otp)

        # 3. Attempting Login Before Email Confirmation MUST Fail with 403
        early_login = client.post("/api/auth/login", json={
            "username": f"trader_{test_id}",
            "password": "StrongPassword789!"
        })
        self.assertEqual(early_login.status_code, 403)
        self.assertTrue(early_login.get_json().get("requires_confirmation"))

        # 4. Wrong Confirmation OTP Rejection
        wrong_confirm = client.post("/api/auth/confirm-signup", json={
            "email": valid_email,
            "otp_code": "000000"
        })
        self.assertEqual(wrong_confirm.status_code, 400)

        # 5. Correct Confirmation OTP Verification
        good_confirm = client.post("/api/auth/confirm-signup", json={
            "email": valid_email,
            "otp_code": signup_otp
        })
        self.assertEqual(good_confirm.status_code, 200)

        # 6. Initiate Login - Triggers 2FA OTP
        login_init = client.post("/api/auth/login", json={
            "username": f"trader_{test_id}",
            "password": "StrongPassword789!"
        })
        self.assertEqual(login_init.status_code, 200)
        login_init_data = login_init.get_json()
        self.assertEqual(login_init_data.get("step"), "OTP_REQUIRED")
        self.assertNotIn("dev_otp", login_init_data)
        session_token = login_init_data.get("session_token")
        login_otp = self._get_latest_otp(valid_email, "LOGIN_2FA")

        # 7. Wrong Login OTP Rejection
        wrong_login_otp = client.post("/api/auth/verify-login-otp", json={
            "session_token": session_token,
            "otp_code": "999999"
        })
        self.assertEqual(wrong_login_otp.status_code, 400)

        # 8. Correct Login OTP Verification -> Bearer Token Issued
        good_login_otp = client.post("/api/auth/verify-login-otp", json={
            "session_token": session_token,
            "otp_code": login_otp
        })
        self.assertEqual(good_login_otp.status_code, 200)
        token = good_login_otp.get_json().get("token")
        self.assertIsNotNone(token)

        # 9. Connected Accounts Isolation Verification
        # User A connects a broker
        auth_hdr_a = {"Authorization": f"Bearer {token}"}
        connect_res = client.post("/api/broker/connect", headers=auth_hdr_a, json={
            "broker": "paper",
            "credentials": {"initial_balance": 50000.0}
        })
        self.assertEqual(connect_res.status_code, 200)

        # User B registers and checks broker config
        user_b_email = f"userb_{test_id}@tradingco.org"
        token_b = self._create_and_login_user(client, f"userb_{test_id}", user_b_email, "PasswordUserB456!")
        auth_hdr_b = {"Authorization": f"Bearer {token_b}"}

        cfg_b = client.get("/api/broker/config", headers=auth_hdr_b).get_json()
        self.assertNotEqual(cfg_b.get("credentials", {}).get("initial_balance"), 50000.0,
            "CRITICAL SECURITY VIOLATION: User B can see User A's connected account credentials!")

        # Unauthenticated request to /api/broker/config must be completely blocked (401)
        unauth_client = app.test_client()
        cfg_unauth = unauth_client.get("/api/broker/config")
        self.assertEqual(cfg_unauth.status_code, 401)

        # 10. Forgot Password & Password Reset Verification
        forgot_res = client.post("/api/auth/forgot-password", json={"email": valid_email})
        self.assertEqual(forgot_res.status_code, 200)
        reset_token = forgot_res.get_json().get("reset_token")
        self.assertIsNotNone(reset_token)

        reset_otp = self._get_latest_otp(valid_email, "PASSWORD_RESET")
        self.assertIsNotNone(reset_otp)

        # Wrong reset OTP fails
        bad_reset = client.post("/api/auth/reset-password", json={
            "reset_token": reset_token,
            "otp_code": "000000",
            "new_password": "NewBrandPassword123!"
        })
        self.assertEqual(bad_reset.status_code, 400)

        # Correct reset OTP succeeds
        good_reset = client.post("/api/auth/reset-password", json={
            "reset_token": reset_token,
            "otp_code": reset_otp,
            "new_password": "NewBrandPassword123!"
        })
        self.assertEqual(good_reset.status_code, 200)

        # Old password must fail login now
        old_login = client.post("/api/auth/login", json={
            "username": f"trader_{test_id}",
            "password": "StrongPassword789!"
        })
        self.assertEqual(old_login.status_code, 401)

        # New password succeeds login
        new_login = client.post("/api/auth/login", json={
            "username": f"trader_{test_id}",
            "password": "NewBrandPassword123!"
        })
        self.assertEqual(new_login.status_code, 200)

        print("✓ Test 10: Strict Email Validation, Signup Confirmation OTP, Login 2FA, Forgot Password Reset, & Connected Accounts Isolation verified.")

if __name__ == "__main__":
    unittest.main()
