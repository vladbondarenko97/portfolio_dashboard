import numpy as np
import pandas as pd
from scipy.stats import norm
import os
from datetime import datetime, timedelta

class QuantEngine:
    def __init__(self, ledger_file):
        self.ledger_file = ledger_file
        self.rolling_window = 30 # days
        
    def get_historical_baseline(self):
        """Loads historical data and calculates means/std devs for normalization."""
        if not os.path.exists(self.ledger_file):
            return None
        
        df = pd.read_csv(self.ledger_file)
        df['Datetime'] = pd.to_datetime(df['Datetime'], format='mixed')
        
        # Filter for last 30 days
        cutoff = datetime.now() - timedelta(days=self.rolling_window)
        hist_df = df[df['Datetime'] >= cutoff]
        
        if hist_df.empty:
            hist_df = df.tail(100) # Fallback to last 100 entries if 30 days is empty
            
        metrics = {
            'vix': {'mean': hist_df['VIX'].mean(), 'std': hist_df['VIX'].std()},
            'gex': {'mean': hist_df['GEX'].mean(), 'std': hist_df['GEX'].std()},
            'dix': {'mean': hist_df['DIX'].mean(), 'std': hist_df['DIX'].std()},
        }
        return metrics

    def calculate_z_score_oscillator(self, current_data):
        """
        Normalizes multiple factors into a -100 to +100 oscillator.
        Factors: VIX, GEX (Gamma Exposure), DIX (Dark Pool Index).
        """
        baseline = self.get_historical_baseline()
        if not baseline:
            return 0.0
            
        # 1. VIX Z-Score (Higher VIX = Bearish/Extension)
        vix_z = (current_data['vix'] - baseline['vix']['mean']) / baseline['vix']['std'] if baseline['vix']['std'] > 0 else 0
        
        # 2. GEX Z-Score (Lower GEX = Higher Volatility/Short Gamma)
        gex_z = (current_data['gex'] - baseline['gex']['mean']) / baseline['gex']['std'] if baseline['gex']['std'] > 0 else 0
        
        # 3. DIX Z-Score (Higher DIX = Dark Pool Accumulation/Bullish)
        dix_z = (current_data['dix'] - baseline['dix']['mean']) / baseline['dix']['std'] if baseline['dix']['std'] > 0 else 0
        
        # Composite Z-Score (Inverse VIX, normal GEX, normal DIX)
        composite_z = (-vix_z + gex_z + dix_z) / 3
        
        # Cap at -3 to +3 std devs and scale to -100 to +100
        score = np.clip(composite_z, -2, 2) * 50 # Scale 2SD to 100
        return float(score)

    def calculate_strike_probabilities(self, spot, vol, strikes, days=5):
        """
        Calculates log-normal probability of expiring ITM.
        """
        T = days / 365.0
        r = 0.05 # Risk-free rate
        
        probs = []
        for K in strikes:
            # Standard Black-Scholes d2 for probability of expiring ITM (P(S > K))
            d2 = (np.log(spot / K) + (r - 0.5 * vol**2) * T) / (vol * np.sqrt(T))
            
            # Probability S > K (for Calls)
            # If we want generic 'ITM' we might need to know if it's a call or put
            # Here we just return the probability of price being above K
            prob_above = norm.cdf(d2)
            
            probs.append({
                'strike': K,
                'prob': float(prob_above)
            })
            
        return probs

    def get_gamma_state(self, spot, zero_gamma, previous_spot=None):
        """
        Calculates distance and velocity relative to Zero Gamma.
        """
        distance = spot - zero_gamma
        distance_pct = distance / spot
        
        velocity = 0.0
        if previous_spot is not None:
            velocity = spot - previous_spot # Points change
            
        return {
            'distance': float(distance),
            'distance_pct': float(distance_pct),
            'velocity': float(velocity),
            'short_gamma_active': distance < 0
        }
