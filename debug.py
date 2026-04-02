import akshare as ak

def get_china_spot_benchmark():
    try:
        # Pulls the official Shanghai Silver Benchmark
        df = ak.spot_silver_benchmark_sge()
        
        latest = df.iloc[-1]
        # Columns: '交易时间', '晚盘价' (Night), '早盘价' (Morning)
        price = latest['晚盘价'] if latest['晚盘价'] > 0 else latest['早盘价']
        
        return price
    except Exception as e:
        print(f"SGE Benchmark Error: {e}")
        return "unavailable"

china_spot = get_china_spot_benchmark()
print(f"Shanghai Spot Benchmark: ¥{china_spot} CNY/kg")