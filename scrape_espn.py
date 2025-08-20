import pandas as pd
import time
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options

def scrape_espn_draft_trends():
    """
    Scrapes ESPN Fantasy Football live draft results and saves to CSV
    """
    
    # Configure Chrome options
    chrome_options = Options()
    chrome_options.add_argument('--headless')  # Run in background
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    
    # Initialize the driver
    driver = webdriver.Chrome(options=chrome_options)
    
    try:
        print("Loading ESPN draft results page...")
        driver.get("https://fantasy.espn.com/football/livedraftresults")
        
        # Wait for the main content to load
        wait = WebDriverWait(driver, 15)
        
        # Wait for player table to be present
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".Table__TBODY")))
        time.sleep(2)  # Additional wait for dynamic content
        
        print("Extracting player data...")
        
        # Get today's date
        today_date = datetime.now().strftime('%Y-%m-%d')
        
        players = []
        page_num = 1
        
        while True:
            print(f"Scraping page {page_num}...")
            
            # Find all player rows on current page
            player_rows = driver.find_elements(By.CSS_SELECTOR, "tr.Table__TR.Table__TR--sm")
            
            page_players_count = 0
            for row in player_rows:
                try:
                    cells = row.find_elements(By.TAG_NAME, "td")
                    
                    if len(cells) >= 5:  # Ensure we have enough data
                        player_data = {
                            'rank': cells[0].text.strip(),
                            'player_name': cells[1].find_element(By.CSS_SELECTOR, "a.AnchorLink").text.strip(),
                            'team': cells[1].find_element(By.CSS_SELECTOR, "span.playerinfo__playerteam").text.strip(),
                            'position': cells[2].text.strip(),
                            'adp': cells[3].text.strip(),
                            'avg_round': cells[4].text.strip() if len(cells) > 4 else '',
                            'date_scraped': today_date  # Add today's date
                        }
                        
                        if player_data['player_name']:  # Only add valid entries
                            players.append(player_data)
                            page_players_count += 1
                            
                except Exception as e:
                    continue  # Skip rows that don't match expected format
            
            print(f"  Found {page_players_count} players on page {page_num}")
            
            # Try to find and click the next page button
            try:
                # Look for the pagination next button
                next_button = driver.find_element(By.CSS_SELECTOR, "button.Pagination__Button--next")
                
                # Check if next button is disabled
                if "disabled" in next_button.get_attribute("class") or next_button.get_attribute("disabled"):
                    print("No more pages to scrape")
                    break
                    
                # Click the next button
                driver.execute_script("arguments[0].click();", next_button)
                
                # Wait for new content to load
                time.sleep(2)
                page_num += 1
                
            except:
                # No next button found or can't click it - we're done
                print("Reached last page")
                break
                
            # Safety check - don't scrape more than 10 pages (500 players)
            if page_num > 10:
                print("Reached maximum page limit")
                break
        
        # Remove duplicates (in case any were loaded twice)
        seen = set()
        unique_players = []
        for player in players:
            player_key = (player['player_name'], player['team'])
            if player_key not in seen:
                seen.add(player_key)
                unique_players.append(player)
        
        # Create DataFrame and save to CSV
        if unique_players:
            df = pd.DataFrame(unique_players)
            
            # Clean up the data
            df['rank'] = pd.to_numeric(df['rank'], errors='coerce')
            df['adp'] = pd.to_numeric(df['adp'], errors='coerce')
            
            # Sort by rank to ensure proper order
            df = df.sort_values('rank', na_position='last')
            
            # Save to CSV
            filename = f'espn_draft_trends_{today_date}.csv'
            df.to_csv(filename, index=False)
            
            print(f"\n✅ Successfully scraped {len(unique_players)} unique players")
            print(f"📄 Data saved to {filename}")
            print(f"📅 Data scraped on: {today_date}")
            print(f"\nTop 5 players:")
            print(df[['rank', 'player_name', 'position', 'adp', 'date_scraped']].head())
            
            return df
        else:
            print("❌ No player data found")
            return None
            
    except Exception as e:
        print(f"❌ Error occurred: {e}")
        return None
        
    finally:
        driver.quit()
        print("\nBrowser closed")

if __name__ == "__main__":
    # Run the scraper
    df = scrape_espn_draft_trends()