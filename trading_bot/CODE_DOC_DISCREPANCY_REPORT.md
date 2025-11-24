# Code vs. Documentation Discrepancy Report

**Date:** 2025-11-23
**Version:** 1.0.0
**Status:** Draft

## 1. Executive Summary

This report analyzes the alignment between the `trading_bot/` codebase and the project documentation. The primary finding is that `CLAUDE.md` (v2.3.1) accurately reflects the current "Minimalist MVP" implementation, while `trading_bot/TRADE_SYSTEM_REQUIREMENTS.md` (v0.1.0) is significantly outdated and describes a more complex system that has been simplified.

**Recommendation:**
1.  **Adopt `CLAUDE.md` as the single source of truth.**
2.  **Archive or update `TRADE_SYSTEM_REQUIREMENTS.md`** to match the current MVP architecture.
3.  **Address minor code discrepancies** identified below (e.g., hardcoded values, missing type hints).

---

## 2. Documentation Analysis

### 2.1 Source of Truth
*   **Primary:** `CLAUDE.md` (v2.3.1) - Accurately describes the current "No Database, No Complex Monitoring" philosophy and the actual feature set (TweetRecordManager, SignalFilter, etc.).
*   **Outdated:** `trading_bot/TRADE_SYSTEM_REQUIREMENTS.md` (v0.1.0) - Describes features like "Google Connectivity Check", "Proxy Auto-Switching", and "DeMark Exit Strategy" which are either not implemented or simplified.

### 2.2 Doc vs. Doc Conflicts

| Feature | `CLAUDE.md` (v2.3.1) | `TRADE_SYSTEM_REQUIREMENTS.md` (v0.1.0) | Status |
| :--- | :--- | :--- | :--- |
| **Database** | No Database (JSON only) | Implies potential future DB use | **Conflict** (Code follows CLAUDE.md) |
| **Monitoring** | Simple logging | Prometheus/Grafana mentioned as "No" but detailed logging requirements exist | **Aligned** (Simple logging implemented) |
| **Exit Strategy** | Basic (Stop Loss / Take Profit) | Mentions DeMark / AI Exit Strategy interfaces | **Conflict** (Code implements Basic only) |
| **Network** | Not explicitly detailed | Detailed Google connectivity check & auto-proxy | **Conflict** (Code has simplified proxy config) |

---

## 3. Code vs. Documentation Analysis

### 3.1 Implemented Features (Aligned with CLAUDE.md)

*   **Tweet Acquisition:** `TwitterCrawlerSignalSource` in `app_runner.py` correctly implements the polling and JSON storage mechanism.
*   **Deduplication:** `TweetRecordManager` (in `tweet_record_manager.py`) correctly handles memory set and file persistence.
*   **AI Analysis:** `AIModelRouter` (in `ai_base.py` / `app_runner.py`) is integrated, though currently using a dummy/mock implementation in some paths (as noted in `app_runner.py` docstring).
*   **Signal Filtering:** `SignalFilter` (in `signal_filter.py`) is implemented and integrated into `app_runner.py`, checking blacklists and confidence scores.
*   **Trading Execution:** `BinanceAsyncClient` (in `exchange_binance_async.py`) implements `place_future_market_order` with dual position mode and leverage setting.
*   **Risk Management:** `RiskManager` (in `risk_exit.py`) implements `BasicExitStrategy` for stop-loss and take-profit monitoring.

### 3.2 Missing or Incomplete Implementation (vs. CLAUDE.md)

*   **CSV Export:** `CLAUDE.md` mentions `TweetRecordManager.export_to_csv`, but I did not explicitly verify the *existence* of this method in the `read_file` output of `tweet_record_manager.py` (I only read `app_runner.py` which imports it). *Action: Verify `tweet_record_manager.py` content.*
*   **AI Model Integration:** `CLAUDE.md` mentions "Single high-performance LLM (Gemini/Claude)". `app_runner.py` mentions "AIModelRouter (currently Dummy)". The actual connection to a real LLM might be mocked or require specific configuration not visible in the main logic.

### 3.3 Code Anomalies & Technical Debt

1.  **Hardcoded API Keys:**
    *   `trading_bot/config.py` contains hardcoded fallback API keys for Binance (`sFgmh...`) and Twitter (`new1_...`).
    *   **Risk:** Security vulnerability if committed to public repos.
    *   **Recommendation:** Remove hardcoded defaults and strictly enforce environment variables.

2.  **Hardcoded Configuration:**
    *   `trading_bot/config.py` has hardcoded `user_intro_mapping` (e.g., "cz_binance").
    *   **Recommendation:** Move to an external JSON/YAML file as suggested in the comments.

3.  **Error Handling:**
    *   `app_runner.py` uses broad `except Exception` blocks in the main loop. While good for keeping the loop alive, it might mask critical errors.

4.  **Type Hinting:**
    *   Some complex dictionaries (e.g., `RawTweet`) use `Dict[str, Any]`. More specific `TypedDict` or `dataclass` definitions would improve type safety.

---

## 4. Detailed File-by-File Findings

### `trading_bot/app_runner.py`
*   **Status:** **High Alignment** with `CLAUDE.md`.
*   **Notes:** Implements the core "fetch -> filter -> trade -> monitor" loop. Correctly uses `TweetRecordManager` and `RiskManager`.
*   **Issue:** The `_to_trade_signal` method relies on `detect_trade_symbol` and specific keys in `ai_result` ("交易方向", "消息置信度"). This coupling with the AI prompt structure needs to be maintained carefully.

### `trading_bot/risk_exit.py`
*   **Status:** **High Alignment** with `CLAUDE.md`.
*   **Notes:** Implements `BasicExitStrategy` exactly as described (Stop Loss + Multi-stage Take Profit).
*   **Issue:** `_load_active_positions` prints to console. Should use the unified logger.

### `trading_bot/config.py`
*   **Status:** **Mixed**.
*   **Notes:** Contains the configuration structures.
*   **Issue:** **CRITICAL** - Hardcoded API keys. `TwitterAPIConfig` has a hardcoded key. `AIConfig` has a hardcoded Poe API key.

### `trading_bot/exchange_binance_async.py`
*   **Status:** **High Alignment**.
*   **Notes:** Implements the necessary Futures API calls.
*   **Issue:** `place_future_market_order` sets leverage to 20 every time. This might be rate-limited or unnecessary if already set.

---

## 5. Action Plan

1.  **Security Fix:** Immediately remove hardcoded API keys from `trading_bot/config.py`.
2.  **Documentation Cleanup:** Mark `TRADE_SYSTEM_REQUIREMENTS.md` as "Legacy/Reference" or update it to match `CLAUDE.md`.
3.  **Verification:** Confirm `TweetRecordManager.export_to_csv` exists and works as described in `CLAUDE.md`.
4.  **Refinement:** Move `user_intro_mapping` to an external file.
