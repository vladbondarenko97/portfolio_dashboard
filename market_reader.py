import xml.etree.ElementTree as ET
import os
import csv
import json
import numpy as np
import yfinance as yf
import databento as db
from datetime import datetime, timedelta, timezone
from scipy.stats import norm

# --- CONFIGURATION ---
DATA_DIR = os.path.join(os.path.expanduser("~"), "Desktop", "CME_Data")
TODAY_STR = datetime.now().strftime("%b-%d-%y") 

DASHBOARD_FILE = os.path.join(DATA_DIR, TODAY_STR, "volume_dashboard.txt")
TACTICAL_FILE = os.path.join(DATA_DIR, TODAY_STR, "tactical_ruling.txt")

# Initialize Databento
DB_API_KEY = 'db-eLfjfMeAhtKf8QdqNWUFAhMGJAduq'
db_client = db.Historical(DB_API_KEY)

#--- BLACK-SCHOLES GAMMA CALCULATOR ---
def calculate_gamma(S, K, T, r, sigma):
    # Prevent division by zero for expired options or zero vol
    if T <= 0 or sigma <= 0:
        return 0.0

    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    nd1 = norm.pdf(d1) 
    gamma = nd1 / (S * sigma * np.sqrt(T))
    return gamma

def find_latest_files(lookback_days=5):
    today = datetime.now()
    found_dash = None
    found_tac = None

    for i in range(lookback_days + 1):
        check_date = today - timedelta(days=i)
        folder_str = check_date.strftime("%b-%d-%y")
        folder_path = os.path.join(DATA_DIR, folder_str)

        dash_path = os.path.join(folder_path, "volume_dashboard.txt")
        tac_path = os.path.join(folder_path, "tactical_ruling.txt")

        if not found_dash and os.path.exists(dash_path) and os.path.getsize(dash_path) > 0:
            found_dash = dash_path
            
        if not found_tac and os.path.exists(tac_path) and os.path.getsize(tac_path) > 0:
            found_tac = tac_path

        if found_dash and found_tac:
            break

    return found_dash, found_tac

def analyze_market():
    DASHBOARD_FILE, TACTICAL_FILE = find_latest_files(lookback_days=5)

    if not DASHBOARD_FILE or not TACTICAL_FILE:
        print(f"❌ Error: Could not find valid data files in the last 5 days of folders.")
        return

    # Parse BOTH XML files
    dash_tree = ET.parse(DASHBOARD_FILE)
    dash_root = dash_tree.getroot()
    
    tac_tree = ET.parse(TACTICAL_FILE)
    tac_root = tac_tree.getroot()

    # --- SAFE EXTRACTION HELPERS ---
    def safe_get(parent_node, path, default="unavailable"):
        if parent_node is None: return default
        node = parent_node.find(path)
        return node.text if node is not None and node.text is not None else default

    def safe_get_attr(parent_node, path, attr_name, default="unavailable"):
        if parent_node is None: return default
        node = parent_node.find(path)
        return node.attrib.get(attr_name, default) if node is not None else default

    # --- 1. VMRI (From Tactical) ---
    vmri_score = safe_get(tac_root, './/VLAD_MACRO_RISK_INDEX/score')
    vmri_tier = safe_get(tac_root, './/VLAD_MACRO_RISK_INDEX/threat_level')

    # --- 2. UPCOMING MACRO EVENTS (From Tactical) ---
    catalyst_status = safe_get(tac_root, './/catalyst_calendar/status', 'CLEAR')
    events = []
    for ev in tac_root.findall('.//upcoming_macro_events/event'):
        e_date = ev.attrib.get('date', '')
        e_time = ev.attrib.get('time', '')
        e_impact = ev.attrib.get('impact', '')
        e_title = ev.attrib.get('title', '')
        e_est = ev.attrib.get('forecast', 'N/A')
        events.append(f"{e_date} @ {e_time} [{e_impact}] {e_title} (Est: {e_est})")
        
    tripwire_str = "\n  - ".join(events) if events else "None"

    # --- 3. COMEX INVENTORY (From Dashboard) ---
    vaults = dash_root.find('.//latest_vaults')
    if vaults is not None:
        registered = vaults.attrib.get('registered', '0')
        eligible = vaults.attrib.get('eligible', '0')
        daily_change = vaults.attrib.get('daily_change', '0')
    else:
        registered, eligible, daily_change = '0', '0', '0'

    # --- 4. PRECIOUS METALS & ARBS (Split Sources) ---
    spot = safe_get_attr(dash_root, './/market_prices/spot', 'price', 'unavailable')
    gold = safe_get(tac_root, './/gold_price', 'unavailable')
    gsr = safe_get(tac_root, './/gold_silver_ratio', 'unavailable')

    shfe_cny_kg = safe_get(tac_root, './/shfe_silver/cny_per_kg')
    shfe_usd_kg = safe_get(tac_root, './/shfe_silver/usd_per_kg')
    shfe_usd_oz = safe_get(tac_root, './/shfe_silver/usd_per_oz')
    shfe_comex  = safe_get(tac_root, './/shfe_silver/comex_spot')
    shfe_prem   = safe_get(tac_root, './/shfe_silver/premium')

    if spot in ['unavailable', 'None', '0', '0.0'] and gold != 'unavailable' and gsr != 'unavailable':
        try:
            spot = str(round(float(gold) / float(gsr), 4))
        except:
            spot = 'unavailable'

    # --- 5. OPTIONS & SENTIMENT ---
    pc_nodes = dash_root.findall('.//sp500_put_call_flow/day')
    if pc_nodes:
        pc_ratio = float(pc_nodes[-1].attrib.get('ratio', '0'))
        if pc_ratio > 2.0: pc_status = "EXTREME FEAR (Heavy Put Buying)"
        elif pc_ratio > 1.3: pc_status = "BEARISH (Downside Hedging)"
        else: pc_status = "BULLISH / NEUTRAL"
    else:
        pc_ratio, pc_status = 0.0, "unavailable"

    vix = safe_get(tac_root, './/vix/value')
    vix_change = safe_get(tac_root, './/vix/change')

    # --- 6. SILVER DIVERGENCE ---
    div_nodes = dash_root.findall('.//silver_divergence/day')
    if div_nodes:
        inst_level = float(div_nodes[-1].attrib.get('institutions', '0'))
        retail_level = float(div_nodes[-1].attrib.get('retail', '0'))
        inst_status = "HIGH CONVICTION (Accumulating)" if inst_level >= 80 else "DISTRIBUTING"
        retail_status = "CAPITULATION" if retail_level < 50 else "BUYING"
    else:
        inst_level, retail_level, inst_status, retail_status = 0, 0, "unavailable", "unavailable"

    # --- 7. MACRO & LIQUIDITY ---
    ten_y_yield = safe_get(tac_root, './/macro_kill_switches/ten_year_treasury')
    dxy = safe_get(tac_root, './/dxy/value')
    oas = safe_get(tac_root, './/credit_markets/high_yield_oas_spread')
    rrp = safe_get(tac_root, './/liquidity_plumbing/reverse_repo_bn/latest')

    # --- 8. PHYSICAL ARBITRAGE (TOP 3 EAGLES) ---
    eagles_data = []
    phys_arb_node = tac_root.find('.//physical_arbitrage')
    
    if phys_arb_node is not None:
        for listing in phys_arb_node.findall('listing'):
            name = listing.attrib.get('name', 'Unknown')
            if len(name) > 42: 
                name = name[:39] + "..."
                
            cost_str = listing.attrib.get('total_cost', '$0').replace('$', '').replace(',', '')
            prem_pct = listing.attrib.get('premium_percent', '0%')
            
            try:
                eagles_data.append({'name': name, 'cost': float(cost_str), 'premium': prem_pct})
            except ValueError:
                continue
                
        eagles_data.sort(key=lambda x: x['cost'])
        
    eagle_lines = []
    if eagles_data:
        for i, eagle in enumerate(eagles_data[:3]):
            eagle_lines.append(f"  {i+1}. ${eagle['cost']:.2f} | {eagle['premium']} Prem | {eagle['name']}")
        eagles_str = "\n".join(eagle_lines)
    else:
        eagles_str = "  - No listings available"

    last_updated = safe_get(dash_root, './/last_updated', datetime.now().strftime("%Y-%m-%d %I:%M %p"))

    # ==========================================
    # --- INSTITUTIONAL GEX & MAX PAIN ---
    # ==========================================
    try:
        ticker = yf.Ticker("SPY")
        spot_price = ticker.info.get('regularMarketPrice') or ticker.history(period='1d')['Close'].iloc[-1]
        
        expirations = ticker.options
        if not expirations:
            gex_final = json.dumps({"status": "error", "message": "No options data available."}, indent=2)
        else:
            # We use the front expiration (closest Friday) for Max Pain and Gamma
            front_exp = expirations[0] 
            target_exps = expirations[:3] 
            gex_by_strike = {}
            risk_free_rate = 0.05 
            
            # --- MAX PAIN CALCULATION (Front Expiration) ---
            front_chain = ticker.option_chain(front_exp)
            all_strikes = set(front_chain.calls['strike']).union(set(front_chain.puts['strike']))
            loss_at_strike = {}
            
            for test_strike in all_strikes:
                call_loss = sum([row['openInterest'] * max(0, test_strike - row['strike']) for _, row in front_chain.calls.iterrows() if test_strike > row['strike']])
                put_loss = sum([row['openInterest'] * max(0, row['strike'] - test_strike) for _, row in front_chain.puts.iterrows() if test_strike < row['strike']])
                loss_at_strike[test_strike] = call_loss + put_loss
            
            max_pain_strike = min(loss_at_strike, key=loss_at_strike.get)

            # --- GEX CALCULATION ---
            for exp in target_exps:
                opt_chain = ticker.option_chain(exp)
                exp_date = datetime.strptime(exp, '%Y-%m-%d')
                days_to_exp = (exp_date - datetime.today()).days
                T = max(days_to_exp / 365.0, 0.001) 
                
                for _, row in opt_chain.calls.iterrows():
                    strike, oi, iv = row['strike'], row['openInterest'], row['impliedVolatility']
                    if oi > 0 and iv > 0.01:
                        gamma = calculate_gamma(spot_price, strike, T, risk_free_rate, iv)
                        gex_by_strike[strike] = gex_by_strike.get(strike, 0) + (gamma * oi * 100 * spot_price)

                for _, row in opt_chain.puts.iterrows():
                    strike, oi, iv = row['strike'], row['openInterest'], row['impliedVolatility']
                    if oi > 0 and iv > 0.01:
                        gamma = calculate_gamma(spot_price, strike, T, risk_free_rate, iv)
                        gex_by_strike[strike] = gex_by_strike.get(strike, 0) - (gamma * oi * 100 * spot_price)

            # --- NET GAMMA STATE ---
            total_gamma = sum(gex_by_strike.values())
            if total_gamma > 0:
                gamma_state = f"LONG GAMMA (+${total_gamma:,.0f}) [Suppressing Volatility / Market Makers Buying Dips]"
            else:
                gamma_state = f"SHORT GAMMA (${total_gamma:,.0f}) [Violent Swings / Market Makers Selling Rips]"

            # Filter for Walls
            lower_bound = spot_price * 0.90
            upper_bound = spot_price * 1.10
            filtered_strikes = {k: v for k, v in gex_by_strike.items() if lower_bound <= k <= upper_bound}
            
            call_wall_strike = max(filtered_strikes, key=filtered_strikes.get) if filtered_strikes else 0
            put_wall_strike = min(filtered_strikes, key=filtered_strikes.get) if filtered_strikes else 0

            payload = {
                "spot": round(spot_price, 2),
                "net_gamma_state": gamma_state,
                "front_week_max_pain": max_pain_strike,
                "call_wall": call_wall_strike,
                "put_wall": put_wall_strike,
            }
            gex_final = json.dumps(payload, indent=2)

    except Exception as e:
        gex_final = json.dumps({"status": "error", "message": str(e)}, indent=2)


    # ==========================================
    # --- DARK POOL & WHALE SWEEPS ---
    # ==========================================
    ticker_sym = "SPY"
    now = datetime.now(timezone.utc)
    
    # --- THE T+1 HISTORICAL BARRIER FIX (Original Working Logic) ---
    yesterday = now - timedelta(days=1)
    available_end = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
    
    if available_end.weekday() == 6: 
        end_time = available_end - timedelta(days=1)
    elif available_end.weekday() == 0: 
        end_time = available_end - timedelta(days=2)
    else:
        end_time = available_end
        
    start_time_1d = end_time - timedelta(days=1)
    start_time_5d = end_time - timedelta(days=7) 
    
    try:
        # 1. FETCH EXACTLY 1-DAY EQUITY BLOCKS (Restoring your working logic)
        data_1d = db_client.timeseries.get_range(
            dataset='DBEQ.BASIC',
            schema='trades',       
            symbols=[ticker_sym],
            start=start_time_1d.isoformat(),
            end=end_time.isoformat(),
            limit=50000            
        )
        df_1d = data_1d.to_df()
        
        # 1-Day Variables
        total_block_volume = 0
        total_notional = 0.0
        largest_block = 0
        avg_block_price = 0.0
        sentiment = "NEUTRAL"
        bullish_vol = 0
        bearish_vol = 0
        recent_prints = []

        if not df_1d.empty:
            blocks_1d = df_1d[df_1d['size'] >= 10000].copy()
            if not blocks_1d.empty:
                total_block_volume = int(blocks_1d['size'].sum())
                total_notional = float((blocks_1d['price'] * blocks_1d['size']).sum())
                largest_block = int(blocks_1d['size'].max())
                avg_block_price = float(total_notional / total_block_volume) if total_block_volume > 0 else 0.0
                
                bullish_vol = int(blocks_1d[blocks_1d['side'] == 'A']['size'].sum())
                bearish_vol = int(blocks_1d[blocks_1d['side'] == 'B']['size'].sum())
                
                if bullish_vol > bearish_vol * 1.2: sentiment = "BULLISH"
                elif bearish_vol > bullish_vol * 1.2: sentiment = "BEARISH"

                # 5 Most Recent Massive Prints
                recent_trades = blocks_1d.tail(5).sort_index(ascending=False)
                for index, row in recent_trades.iterrows():
                    recent_prints.append({
                        "time": index.strftime("%H:%M:%S"),
                        "price": round(float(row['price']), 4),
                        "size": int(row['size']),
                        "side": "BUY" if row['side'] == 'A' else "SELL" if row['side'] == 'B' else "UNK"
                    })

        # 2. FETCH 5-DAY EQUITY BLOCKS (Heatmap)
        data_5d = db_client.timeseries.get_range(
            dataset='DBEQ.BASIC',
            schema='trades',       
            symbols=[ticker_sym],
            start=start_time_5d.isoformat(),
            end=end_time.isoformat(),
            limit=100000            
        )
        df_5d = data_5d.to_df()
        hvn_zones = []
        
        if not df_5d.empty:
            blocks_5d = df_5d[df_5d['size'] >= 10000].copy()
            if not blocks_5d.empty:
                blocks_5d['price_zone'] = (blocks_5d['price'] * 2).round() / 2
                heatmap = blocks_5d.groupby('price_zone')['size'].sum().reset_index()
                heatmap = heatmap.sort_values(by='size', ascending=False).head(3)
                
                for _, row in heatmap.iterrows():
                    hvn_zones.append(f"${row['price_zone']:.2f} ({int(row['size']):,} shares)")

        # --- FINAL UNIFIED PAYLOAD ---
        dp_payload = {
            "status": "success",
            "data": {
                "ticker": ticker_sym,
                "total_block_volume": total_block_volume,
                "total_notional_usd": round(total_notional, 2),
                "largest_single_block": largest_block,
                "vwap_price": round(avg_block_price, 2),
                "sentiment": {
                    "bias": sentiment,
                    "bull_volume": bullish_vol,
                    "bear_volume": bearish_vol
                },
                "5_day_support_resistance_nodes": hvn_zones,
                "recent_prints": recent_prints
            }
        }
        darkpool_final = json.dumps(dp_payload, indent=2)

    except Exception as e:
        darkpool_final = json.dumps({"status": "error", "message": str(e)}, indent=2)

    # ==========================================
    # --- PILLAR 2: ADVANCED TECHNICALS (MTF) ---
    # ==========================================
    try:
        spy_tech = yf.Ticker("SPY")
        
        # 1. Pull MTF Data
        df_1h = spy_tech.history(period="1mo", interval="1h")
        df_daily = spy_tech.history(period="2y", interval="1d")
        df_weekly = spy_tech.history(period="5y", interval="1wk")

        if df_daily.empty or df_1h.empty:
            technicals_final = json.dumps({"status": "error", "message": "No technical data found."}, indent=2)
        else:
            current_price = df_daily['Close'].iloc[-1]

            # --- TREND CALCULATIONS ---
            # 1H Trend (20-period EMA)
            ema_20_1h = df_1h['Close'].ewm(span=20, adjust=False).mean().iloc[-1]
            trend_1h = "BULLISH" if current_price > ema_20_1h else "BEARISH"

            # Daily Trend (20-period EMA)
            ema_20_d = df_daily['Close'].ewm(span=20, adjust=False).mean().iloc[-1]
            trend_daily = "BULLISH" if current_price > ema_20_d else "BEARISH"

            # Weekly Trend (20-period SMA)
            sma_20_w = df_weekly['Close'].rolling(window=20).mean().iloc[-1]
            trend_weekly = "BULLISH" if current_price > sma_20_w else "BEARISH"

            # --- ALIGNMENT LOGIC ---
            if trend_1h == "BULLISH" and trend_daily == "BEARISH" and trend_weekly == "BEARISH":
                alignment_status = "BEAR MARKET RALLY (Short Squeeze Trap)"
            elif trend_1h == "BEARISH" and trend_daily == "BULLISH" and trend_weekly == "BULLISH":
                alignment_status = "BULL MARKET DIP (Buying Opportunity)"
            elif trend_1h == trend_daily == trend_weekly:
                alignment_status = f"FULL ALIGNMENT ({trend_1h})"
            else:
                alignment_status = "MIXED / TRANSITION"

            # --- DAILY INDICATORS (Keep existing logic) ---
            sma_50 = df_daily['Close'].rolling(window=50).mean().iloc[-1]
            sma_200 = df_daily['Close'].rolling(window=200).mean().iloc[-1]
            
            df_daily['Price_Zone'] = (df_daily['Close'] * 2).round() / 2
            poc_price = df_daily.tail(30).groupby('Price_Zone')['Volume'].sum().idxmax()

            # RSI & Divergence (Keep existing logic)
            delta = df_daily['Close'].diff()
            gain = delta.where(delta > 0, 0).ewm(alpha=1/14, adjust=False).mean()
            loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()
            rs = gain / loss
            current_rsi = 100 - (100 / (1 + rs.iloc[-1]))

            # --- FINAL TECHNICAL PAYLOAD ---
            tech_payload = {
                "status": "success",
                "data": {
                    "current_price": round(current_price, 2),
                    "volume_profile_30d_poc": round(poc_price, 2),
                    "mtf_alignment": alignment_status,
                    "trend_matrix": {
                        "1H": trend_1h,
                        "Daily": trend_daily,
                        "Weekly": trend_weekly,
                        "vs_200_SMA": "BULLISH" if current_price > sma_200 else "BEARISH"
                    },
                    "rsi_14d": round(current_rsi, 2)
                }
            }
            technicals_final = json.dumps(tech_payload, indent=2)

    except Exception as e:
        technicals_final = json.dumps({"status": "error", "message": str(e)}, indent=2)

    # ==========================================
    # --- PILLAR 3: THE WEATHER (VOLATILITY) ---
    # ==========================================
    try:
        # Pull live data from CBOE indices via Yahoo Finance
        vix_ticker = yf.Ticker("^VIX")
        vix3m_ticker = yf.Ticker("^VIX3M")
        
        hist_vix = vix_ticker.history(period="1d")
        hist_vix3m = vix3m_ticker.history(period="1d")
        
        if hist_vix.empty or hist_vix3m.empty:
            vix_final = json.dumps({"status": "error", "message": "Failed to pull live CBOE data."}, indent=2)
        else:
            current_vix = hist_vix['Close'].iloc[-1]
            current_vix3m = hist_vix3m['Close'].iloc[-1]
            
            # --- TERM STRUCTURE LOGIC ---
            vix_diff = current_vix - current_vix3m
            
            if current_vix > current_vix3m:
                term_structure = f"BACKWARDATION (VIX is {abs(vix_diff):.2f} pts HIGHER than 3M. Extreme Near-Term Panic / Selloff)"
            else:
                term_structure = f"CONTANGO (VIX is {abs(vix_diff):.2f} pts LOWER than 3M. Normal / Complacent Market)"
                
            vix_payload = {
                "status": "success",
                "data": {
                    "spot_vix": round(current_vix, 2),
                    "vix_3m": round(current_vix3m, 2),
                    "term_structure": term_structure
                }
            }
            vix_final = json.dumps(vix_payload, indent=2)

    except Exception as e:
        vix_final = json.dumps({"status": "error", "message": str(e)}, indent=2)

    # ==========================================
    # --- PILLAR 4: UNDER THE HOOD (BREADTH) ---
    # ==========================================
    try:
        # Pull SPY, Equal-Weight SPY (RSP), and the top 3 heavyweights
        breadth_tickers = yf.Tickers("SPY RSP NVDA AAPL MSFT")
        # Pull 2 days of history to calculate today's percentage change
        hist_breadth = breadth_tickers.history(period="2d")['Close']

        if hist_breadth.empty or len(hist_breadth) < 2:
            breadth_final = json.dumps({"status": "error", "message": "Failed to pull breadth data."}, indent=2)
        else:
            # Calculate daily percentage changes
            pct = ((hist_breadth.iloc[-1] - hist_breadth.iloc[-2]) / hist_breadth.iloc[-2]) * 100

            spy_pct = pct['SPY']
            rsp_pct = pct['RSP']
            
            # --- BREADTH CONDITION LOGIC ---
            if spy_pct > 0 and rsp_pct > 0:
                breadth_cond = "BROAD RALLY (Healthy Participation)"
            elif spy_pct > 0 and rsp_pct <= 0:
                breadth_cond = "NARROW RALLY (Top-Heavy / Fakeout)"
            elif spy_pct < 0 and rsp_pct < 0:
                breadth_cond = "BROAD SELLOFF (True Market Weakness)"
            elif spy_pct < 0 and rsp_pct >= 0:
                breadth_cond = "TECH ROTATION (Mega-caps bleeding, broader market holding)"
            else:
                breadth_cond = "FLAT / MIXED"

            breadth_payload = {
                "status": "success",
                "data": {
                    "market_condition": breadth_cond,
                    "spy_daily_change": f"{spy_pct:+.2f}%",
                    "rsp_daily_change": f"{rsp_pct:+.2f}%",
                    "heavyweight_alignment": {
                        "NVDA": f"{pct['NVDA']:+.2f}%",
                        "AAPL": f"{pct['AAPL']:+.2f}%",
                        "MSFT": f"{pct['MSFT']:+.2f}%"
                    }
                }
            }
            breadth_final = json.dumps(breadth_payload, indent=2)

    except Exception as e:
        breadth_final = json.dumps({"status": "error", "message": str(e)}, indent=2)

    # ==========================================
    # --- PILLAR 5: THE EXECUTION ENGINE (SYNCHRONIZED) ---
    # ==========================================
    try:
        confluence_score = 0
        score_breakdown = []
        
        # --- REGIME IDENTIFICATION ---
        vix = locals().get('current_vix', 0)
        if vix > 20:
            regime = "HIGH VOLATILITY (Structural Dominance)"
            w_breadth, w_tech, w_gamma, w_pain = 1, 0, 2, 2
        else:
            regime = "LOW/NORMAL VOLATILITY (Trend Dominance)"
            w_breadth, w_tech, w_gamma, w_pain = 2, 1, 1, 1

        score_breakdown.append(f"Regime: {regime}")

        # 1. The Breadth Vote (Weighted)
        if "BROAD RALLY" in locals().get('breadth_cond', ''):
            confluence_score += w_breadth
            score_breakdown.append(f"Breadth: +{w_breadth} (Broad Participation)")
        elif "NARROW RALLY" in locals().get('breadth_cond', '') or "BROAD SELLOFF" in locals().get('breadth_cond', ''):
            confluence_score -= w_breadth
            score_breakdown.append(f"Breadth: -{w_breadth} (Narrow/Weak Participation)")

        # 2. The Dark Pool Sentiment Vote (Weighted)
        dp_sent = locals().get('sentiment', 'NEUTRAL')
        if dp_sent == "BULLISH":
            confluence_score += w_gamma 
            score_breakdown.append(f"DP Sentiment: +{w_gamma} (Institutional Accumulation)")
        elif dp_sent == "BEARISH":
            confluence_score -= w_gamma
            score_breakdown.append(f"DP Sentiment: -{w_gamma} (Institutional Distribution)")
        else:
            score_breakdown.append("DP Sentiment: 0 (Neutral Imbalance)")

        # 3. The MTF Alignment Vote (Weighted - PHASE 3)
        mtf = locals().get('alignment_status', '')
        if w_tech > 0:
            if "FULL ALIGNMENT (BULLISH)" in mtf:
                confluence_score += (w_tech + 1)
                score_breakdown.append(f"Trend: +{w_tech+1} (Full MTF Bullish Alignment)")
            elif "FULL ALIGNMENT (BEARISH)" in mtf:
                confluence_score -= (w_tech + 1)
                score_breakdown.append(f"Trend: -{w_tech+1} (Full MTF Bearish Alignment)")
            elif "BEAR MARKET RALLY" in mtf:
                confluence_score -= 1 
                score_breakdown.append("Trend: -1 (Trap - Bullish 1H in Bearish Macro)")
            elif "BULL MARKET DIP" in mtf:
                confluence_score += 1 
                score_breakdown.append("Trend: +1 (Dip - Bearish 1H in Bullish Macro)")
            else:
                score_breakdown.append("Trend: 0 (Mixed/Non-Aligned)")
        else:
            score_breakdown.append("Trend: 0 (Muted due to High VIX)")

        # 4. The Gamma Vote (Weighted)
        cp = locals().get('current_price', 0)
        cw = locals().get('call_wall_strike', 0)
        pw = locals().get('put_wall_strike', 0)
        if cp > cw and cw != 0:
            confluence_score -= w_gamma
            score_breakdown.append(f"Gamma: -{w_gamma} (Overextended/MM Selling)")
        elif cp < pw and pw != 0:
            confluence_score += w_gamma
            score_breakdown.append(f"Gamma: +{w_gamma} (Bounce Zone/MM Buying)")

        # 5. The Max Pain Gravity (Weighted)
        mp = locals().get('max_pain_strike', 0)
        if cp > mp + 2 and mp != 0:
            confluence_score -= w_pain
            score_breakdown.append(f"Max Pain: -{w_pain} (Downward Gravity)")
        elif cp < mp - 2 and mp != 0:
            confluence_score += w_pain
            score_breakdown.append(f"Max Pain: +{w_pain} (Upward Gravity)")

        # --- THE FINAL VERDICT ---
        if confluence_score >= 3:
            directional_bias = f"BULLISH (+{confluence_score}) [CALL TRIGGER ACTIVE]"
        elif confluence_score <= -3:
            directional_bias = f"BEARISH ({confluence_score}) [PUT TRIGGER ACTIVE]"
        else:
            directional_bias = f"CASH POSITION ({confluence_score}) [CONFLICTING SIGNALS - HOLD]"

        # ==========================================
        # --- PHASE 2: STRUCTURAL STRIKE SELECTION ---
        # ==========================================
        target_strike = "NONE"
        strike_rationale = "N/A"
        
        # 1. Safely extract numeric Dark Pool nodes from the string array we made earlier
        dp_nodes = []
        for zone in locals().get('hvn_zones', []):
            try:
                # Extracts the '647.00' from '$647.00 (905,000 shares)'
                price = float(zone.split(' ')[0].replace('$', '').replace(',', ''))
                dp_nodes.append(price)
            except:
                pass

        # 2. Apply the Magnet Logic
        if confluence_score >= 3:
            # BULLISH: Look UP for resistance magnets
            overhead_magnets = [p for p in dp_nodes if p > cp]
            if cw > cp: overhead_magnets.append(cw) # Add Call Wall if it's above us
            
            if overhead_magnets:
                target_strike = min(overhead_magnets) # Snap to the *nearest* ceiling
                strike_rationale = "Snapped to nearest overhead DP Node or Call Wall."
            else:
                target_strike = round(cp + 2, 0)
                strike_rationale = "Defaulted to +$2 out-of-the-money (No clear overhead nodes)."

        elif confluence_score <= -3:
            # BEARISH: Look DOWN for support magnets
            support_magnets = [p for p in dp_nodes if p < cp]
            if mp > 0 and mp < cp: support_magnets.append(mp) # Add Max Pain if it's below us
            
            if support_magnets:
                target_strike = max(support_magnets) # Snap to the *nearest* floor
                strike_rationale = "Snapped to nearest underlying DP Node or Max Pain."
            else:
                target_strike = round(cp - 2, 0)
                strike_rationale = "Defaulted to -$2 out-of-the-money (No clear support nodes)."
        else:
            strike_rationale = "Cash Position - No strike required."


        # ==========================================
        # --- PHASE 3: VOLATILITY-ADJUSTED EXPIRATION ---
        # ==========================================
        vix = locals().get('current_vix', 0)
        target_expiration = "NONE"
        expiration_rationale = "N/A"

        # Only calculate expiration if we have a valid trade trigger
        if confluence_score >= 3 or confluence_score <= -3:
            if 0 < vix < 15:
                min_dte, max_dte = 14, 21
                expiration_rationale = f"VIX is Low ({vix:.2f}). 14-21 DTE selected (Options are cheap)."
            elif 15 <= vix <= 20:
                min_dte, max_dte = 21, 30
                expiration_rationale = f"VIX is Normal ({vix:.2f}). 21-30 DTE selected."
            elif vix > 20:
                min_dte, max_dte = 30, 45
                expiration_rationale = f"VIX is High ({vix:.2f}). 30-45 DTE selected to buffer IV Crush & Theta."
            else:
                min_dte, max_dte = 21, 30
                expiration_rationale = "VIX Data Missing. Defaulting to 21-30 DTE."

            # Find the first Friday within our DTE window
            today_dt = datetime.today()
            
            for i in range(min_dte, max_dte + 7):
                check_date = today_dt + timedelta(days=i)
                if check_date.weekday() == 4: # 4 = Friday
                    target_expiration = check_date.strftime("%Y-%m-%d")
                    break
        else:
            expiration_rationale = "Cash Position - No expiration required."

        # ==========================================
        # --- PHASE 4: THE SNIPER PRICE PULL & KELLY OUTPUT ---
        # ==========================================
        trade_ticket = "N/A"
        actual_exp = target_expiration

        if confluence_score >= 3 or confluence_score <= -3:
            # --- THE KELLY OUTPUT (Position Sizing) ---
            abs_score = abs(confluence_score)
            if abs_score == 3:
                risk_profile = "Conviction: LOW. Suggested Size: 1/3rd standard position."
            elif abs_score == 4:
                risk_profile = "Conviction: HIGH. Suggested Size: Standard swing position."
            elif abs_score >= 5:
                risk_profile = "Conviction: EXTREME. Suggested Size: Max allocation / Add on dips."
            else:
                risk_profile = "N/A"

            if target_expiration != "NONE" and target_strike != "NONE":
                try:
                    spy_ticker = yf.Ticker("SPY")
                    available_exps = spy_ticker.options
                    
                    if target_expiration not in available_exps:
                        target_dt = datetime.strptime(target_expiration, "%Y-%m-%d")
                        actual_exp = min(available_exps, key=lambda d: abs(datetime.strptime(d, "%Y-%m-%d") - target_dt))
                        expiration_rationale += f" (Adjusted to nearest available: {actual_exp})"
                    
                    chain = spy_ticker.option_chain(actual_exp)
                    opt_df = chain.calls if confluence_score >= 3 else chain.puts
                    opt_type = "CALL" if confluence_score >= 3 else "PUT"
                    
                    available_strikes = opt_df['strike'].tolist()
                    closest_strike = min(available_strikes, key=lambda x: abs(x - target_strike))
                    
                    if closest_strike != target_strike:
                        strike_rationale += f" (Adjusted from ${target_strike} to nearest: ${closest_strike})"
                        target_strike = closest_strike
                    
                    contract_row = opt_df[opt_df['strike'] == target_strike].iloc[0]
                    
                    # --- FORMATTING THE COMPLETE TICKET ---
                    trade_ticket = {
                        "contract": contract_row['contractSymbol'],
                        "type": opt_type,
                        "strike": f"${target_strike}",
                        "expiration": actual_exp,
                        "allocation": risk_profile, # <--- NEW KELLY OUTPUT
                        "pricing": f"Bid: ${contract_row['bid']:.2f} | Ask: ${contract_row['ask']:.2f} | Last: ${contract_row['lastPrice']:.2f}",
                        "metrics": f"IV: {contract_row['impliedVolatility']*100:.2f}% | Volume: {contract_row['volume']} | OI: {contract_row['openInterest']}"
                    }

                except Exception as e:
                    trade_ticket = f"Failed to pull live contract data: {e}"
        else:
            trade_ticket = "CASH POSITION - No trade ticket generated."

        # --- ASSEMBLE FINAL ENGINE PAYLOAD ---
        engine_payload = {
            "status": "success",
            "data": {
                "total_score": confluence_score,
                "directional_bias": directional_bias,
                "matrix_breakdown": score_breakdown,
                "optimal_strike": {
                    "strike_price": f"${target_strike}" if target_strike != "NONE" else target_strike,
                    "rationale": strike_rationale
                },
                "optimal_expiration": {
                    "date": actual_exp,
                    "rationale": expiration_rationale
                },
                "live_trade_ticket": trade_ticket
            }
        }
        engine_final = json.dumps(engine_payload, indent=2)

    except Exception as e:
        engine_final = json.dumps({"status": "error", "message": str(e)}, indent=2)

    # ==========================================
    # --- HISTORICAL CSV LOGGING (THE MASTER LEDGER V2) ---
    # ==========================================
    ledger_path = os.path.join(DATA_DIR, "institutional_ledger.csv") # Renamed to V2 for new columns
    file_exists = os.path.isfile(ledger_path)

    csv_row = {
        "Date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Ticker": "SPY",
        # PILLAR 1: ENGINE
        "Spot_Price": round(locals().get('spot_price', 0), 2) if locals().get('spot_price') else "N/A",
        "Net_Gamma": locals().get('total_gamma', "N/A"),
        "Max_Pain": locals().get('max_pain_strike', "N/A"),
        "Call_Wall": locals().get('call_wall_strike', "N/A"),
        "Put_Wall": locals().get('put_wall_strike', "N/A"),
        "DP_Sentiment": locals().get('sentiment', "N/A"),
        "DP_Volume": locals().get('total_block_volume', "N/A"),
        "DP_Notional": round(locals().get('total_notional', 0), 2) if locals().get('total_notional') else "N/A",
        "DP_VWAP": round(locals().get('avg_block_price', 0), 2) if locals().get('avg_block_price') else "N/A",
        "DP_Largest_Block": locals().get('largest_block', "N/A"),
        
        # PILLAR 2: BATTLEFIELD
        "Tech_30d_POC": round(locals().get('poc_price', 0), 2) if locals().get('poc_price') else "N/A",
        "Tech_20_EMA": round(locals().get('ema_20', 0), 2) if locals().get('ema_20') else "N/A",
        "Tech_50_SMA": round(locals().get('sma_50', 0), 2) if locals().get('sma_50') else "N/A",
        "Tech_200_SMA": round(locals().get('sma_200', 0), 2) if locals().get('sma_200') else "N/A",
        "Tech_14d_RSI": round(locals().get('current_rsi', 0), 2) if locals().get('current_rsi') else "N/A",
        "Tech_Divergence": locals().get('divergence_flag', "N/A").split(" ")[0], 
        
        # PILLAR 3: WEATHER
        "VIX_Spot": round(locals().get('current_vix', 0), 2) if locals().get('current_vix') else "N/A",
        "VIX_3M": round(locals().get('current_vix3m', 0), 2) if locals().get('current_vix3m') else "N/A",
        "VIX_Term_Struct": locals().get('term_structure', "N/A").split(" ")[0],
        
        # PILLAR 4: BREADTH
        "Breadth_Condition": locals().get('breadth_cond', "N/A").split(" ")[0],
        "SPY_Daily_Pct": round(locals().get('spy_pct', 0), 2) if locals().get('spy_pct') else "N/A",
        "RSP_Daily_Pct": round(locals().get('rsp_pct', 0), 2) if locals().get('rsp_pct') else "N/A",
        "NVDA_Pct": round(locals().get('pct', {}).get('NVDA', 0), 2) if locals().get('pct') is not None else "N/A",
        "AAPL_Pct": round(locals().get('pct', {}).get('AAPL', 0), 2) if locals().get('pct') is not None else "N/A",
        "MSFT_Pct": round(locals().get('pct', {}).get('MSFT', 0), 2) if locals().get('pct') is not None else "N/A"
    }

    try:
        with open(ledger_path, mode='a', newline='') as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=csv_row.keys())
            if not file_exists:
                writer.writeheader() 
            writer.writerow(csv_row)
    except Exception as e:
        print(f"\n⚠️ WARNING: Failed to write to Master CSV Ledger: {e}\n")
        
    # --- FORMATTING ---
    # (This is where your existing try/except for spot_f and the print(report) block goes)

    # --- FORMATTING ---
    try:
        spot_f = f"${float(spot):.2f}" if spot not in ['unavailable', 'None'] else "unavailable"
        gold_f = f"${float(gold):.2f}" if gold not in ['unavailable', 'None'] else "unavailable"
    except:
        spot_f, gold_f = spot, gold

    report = f"""🌅 MORNING MARKET BRIEF 🌅
{last_updated}

🚨 VLAD MACRO RISK INDEX (VMRI)
  - Score: {vmri_score}
  - Threat Level: {vmri_tier}

⏰ CATALYST CALENDAR
  - Status: {catalyst_status}
  - Scheduled Events: 
  - {tripwire_str}

🏦 COMEX INVENTORY
  - Registered: {float(registered):,.2f}M oz
  - Eligible: {float(eligible):,.2f}M oz
  - Daily Change: {daily_change}

💰 PRECIOUS METALS & ARBS
  - Gold Price: {gold_f}
  - Gold/Silver Ratio: {gsr}
  - COMEX Spot Silver: {spot_f}

🇨🇳 SHANGHAI PHYSICAL ARBITRAGE (SGE)
  - SGE Quote: {shfe_cny_kg} CNY/kg
  - USD Equiv: {shfe_usd_kg}/kg ({shfe_usd_oz}/oz)
  - Tax-Adj Premium: {shfe_prem}/oz

📉 S&P 500 OPTIONS FLOW
  - Put/Call Ratio: {pc_ratio:.2f} ({pc_status})
  - VIX (Volatility): {vix} ({vix_change})

🧠 SILVER DIVERGENCE
  - Institutions: {inst_level:.2f} [{inst_status}]
  - Retail: {retail_level:.2f} [{retail_status}]

🌍 MACRO & LIQUIDITY
  - 10Y Yield: {ten_y_yield}%
  - DXY (Dollar): {dxy}
  - High Yield OAS: {oas}
  - Fed Reverse Repo: ${rrp}B

🦅 PHYSICAL ARBITRAGE (CHEAPEST EAGLES on eBay)
{eagles_str}

========================================
 🦅 INSTITUTIONAL FLOW ($SPY)
========================================
🧠 GEX DATA (Options Engine):
{gex_final}

🌊 DARK POOL DATA (Off-Exchange Blocks):
{darkpool_final}

⚔️ THE BATTLEFIELD (Advanced Technicals):
{technicals_final}

🌪️ THE WEATHER (Volatility & Term Structure):
{vix_final}

🩻 UNDER THE HOOD (Market Breadth):
{breadth_final}

🎯 ALGORITHMIC EXECUTION ENGINE:
{engine_final}
"""
    print(report)

if __name__ == "__main__":
    analyze_market()