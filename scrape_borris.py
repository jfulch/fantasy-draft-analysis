import pandas as pd
import requests
from datetime import datetime
import os

def download_boris_chen_csv_files():
    """
    Downloads Boris Chen draft sheets directly from CSV links
    """
    
    # Get today's date
    today_date = datetime.now().strftime('%Y-%m-%d')
    
    # Create Data directory if it doesn't exist
    os.makedirs('Data', exist_ok=True)
    
    # Define the CSV URLs and output filenames
    csv_sources = {
        'standard': {
            'url': 'https://s3-us-west-1.amazonaws.com/fftiers/out/weekly-ALL.csv',
            'filename': f'Data/boris_chen_standard_{today_date}.csv',
            'name': 'Standard'
        },
        'ppr': {
            'url': 'https://s3-us-west-1.amazonaws.com/fftiers/out/weekly-ALL-PPR.csv',
            'filename': f'Data/boris_chen_ppr_{today_date}.csv',
            'name': 'PPR'
        },
        'half_ppr': {
            'url': 'https://s3-us-west-1.amazonaws.com/fftiers/out/weekly-ALL-HALF-PPR.csv',
            'filename': f'Data/boris_chen_half_ppr_{today_date}.csv',
            'name': 'Half PPR'
        }
    }
    
    all_data = {}
    
    for format_key, format_info in csv_sources.items():
        print(f"\nDownloading {format_info['name']} data...")
        
        try:
            # Download the CSV file
            response = requests.get(format_info['url'])
            response.raise_for_status()
            
            # Save the raw CSV
            with open(format_info['filename'], 'wb') as f:
                f.write(response.content)
            
            # Read the CSV into a DataFrame
            df = pd.read_csv(format_info['filename'])
            
            # Add metadata columns
            df['scoring_format'] = format_info['name']
            df['date_scraped'] = today_date
            
            # Save the enhanced CSV
            df.to_csv(format_info['filename'], index=False)
            
            all_data[format_key] = df
            
            print(f"  ✅ Downloaded {len(df)} players for {format_info['name']}")
            print(f"  📄 Saved to {format_info['filename']}")
            
            # Show column names
            print(f"  Columns: {', '.join(df.columns[:6])}...")
            
            # Display sample data with actual columns
            print(f"  Sample data:")
            if 'Player.Name' in df.columns:
                # Use actual column names from Boris Chen CSV
                display_cols = ['Rank', 'Player.Name', 'Tier', 'Position']
                available_cols = [col for col in display_cols if col in df.columns]
                if available_cols:
                    print(df[available_cols].head(3).to_string(index=False))
            else:
                # Fallback: just show first few columns
                print(df.iloc[:3, :4].to_string(index=False))
            
        except requests.exceptions.RequestException as e:
            print(f"  ❌ Error downloading {format_info['name']}: {e}")
        except Exception as e:
            print(f"  ❌ Error processing {format_info['name']}: {e}")
    
    print(f"\n📅 All data downloaded on: {today_date}")
    print(f"✅ Download complete!")
    
    # Summary
    if all_data:
        print(f"\nSummary:")
        for format_name, df in all_data.items():
            print(f"  {format_name}: {len(df)} players")
            print(f"    Top 3: {', '.join(df['Player.Name'].head(3).tolist())}")
    
    return all_data

if __name__ == "__main__":
    # Run the downloader
    data = download_boris_chen_csv_files()