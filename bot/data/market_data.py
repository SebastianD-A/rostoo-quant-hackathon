#Built in libs
import io
import zipfile
from pathlib import Path

#Third party libs
import pandas as pd
import requests

#Binance data we want to query
binance_url = "https://data.binance.vision/data/spot/monthly/klines"

currencies_chosen = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

interval = "1h"

#File settings
data_dir = Path(__file__).parent/"binance historical"

#Binance Kline column names, taken from their public documentation and renamed to lowercase
columns = [
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time",
    "quote_asset_volume",
    "number_of_trades",
    "taker_buy_base_volume",
    "taker_buy_quote_volume",
    "ignore"
]

#download only 1 month of data
def download_month(year, month, currency):
    #reformat the args passed in this command to match Binance's format
    month_str = f"{year}-{month:02d}"

    #complete full url for monthly zip file
    url = f"{binance_url}/{currency}/{interval}/{currency}-{interval}-{month_str}.zip"

    #shows which data is about to be downloaded
    print(f"{month_str}, {currency}")
    response = requests.get(url)

    if response.status_code == 404:
        print(f"{month_str}; no data;{currency}")
        return None
    
    #stop program if another HTTP error shows up
    response.raise_for_status()

    #turn downloaded data as a file without needing to save the zip file
    with zipfile.ZipFile(io.BytesIO(response.content)) as zip_file:
        csv_file = zip_file.namelist()[0]

        with zip_file.open(csv_file) as file:
            df = pd.read_csv(file, header=None, names=columns)
            
            # Convert timestamps per month based on the year
            time_unit = "us" if year >= 2025 else "ms"
            df["open_time"] = pd.to_datetime(df["open_time"], unit=time_unit)
            df["close_time"] = pd.to_datetime(df["close_time"], unit=time_unit)
            
            return df

#downloading and combining data
def download_binance_historical_data( currencies, start_year, start_month, end_year, end_month):
    #Makes the 'binance historical' folder if it hasnt been made yet
    data_dir.mkdir(parents=True, exist_ok=True)

    for currency in currencies:
        #hold all Dataframe from each month
        all_data = []

        #start dates
        year = start_year
        month = start_month

        #Keep downloading data till end date
        while (year, month) <= (end_year, end_month):
            data = download_month(year, month, currency)
            
            if data is not None:
                all_data.append(data)

            month += 1

            if month > 12:
                month = 1
                year += 1

            #stop program if nothing is downloaded
        if not all_data:
            raise RuntimeError(f"No historical data able to be downloaded;{currency}")

        #combine all monthly Dataframe to one big Dataframe
        combined = pd.concat(all_data, ignore_index = True)

        #Sort and combine data

        combined = combined.sort_values("open_time")
        
        combined = combined.drop_duplicates(subset="open_time")

        output_file = data_dir/f"{currency}_{interval}.csv"

        combined.to_csv(output_file, index = False)

        print(f"{len(combined)} saved to {output_file}")

if __name__ == "__main__":

    # download from 1/2024 to 8/2026.
    download_binance_historical_data(currencies_chosen, start_year = 2024, start_month = 1, end_year = 2026, end_month = 8)