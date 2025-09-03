
import pandas as pd
import time
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import os

def scrape_bettingpros_prop_bets():
    """
    Scrapes BettingPros NFL prop bets and saves to CSV
    """
    chrome_options = Options()
    # chrome_options.add_argument('--headless')  # Disabled for visible browser
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')

    driver = webdriver.Chrome(options=chrome_options)

    try:
        print("Loading BettingPros prop bets page...")
        driver.get("https://www.bettingpros.com/nfl/picks/prop-bets/")

        wait = WebDriverWait(driver, 20)

        # Enhanced popup handling
        time.sleep(4)  # Wait longer for popup to appear
        popup_closed = False
        try:
            # Try common selectors for close buttons
            for selector in [
                '[aria-label="Close"]',
                '.close',
                '.modal-close',
                '.Popup__close',
                '.newsletter-modal__close',
                '.newsletter-modal__close-btn',
                '.bp-modal__close',
                '.bp-modal-close',
                '.bp-modal__close-btn',
                '.bp-modal__close-button',
                '.bp-modal__close-icon',
                'button',
                'svg',
            ]:
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    for el in elements:
                        if el.is_displayed():
                            # Try clicking if it looks like a close button
                            txt = el.text.strip().lower()
                            if txt in ['×', 'close', 'no thanks', 'dismiss', 'cancel', 'got it', 'ok'] or el.get_attribute('aria-label') in ['Close', 'close']:
                                el.click()
                                print(f"Closed popup with selector: {selector} and text: {txt}")
                                time.sleep(1)
                                popup_closed = True
                                break
                        if popup_closed:
                            break
                    if popup_closed:
                        break
                except Exception:
                    continue
            if not popup_closed:
                # Try to send ESC key to close overlays
                from selenium.webdriver.common.keys import Keys
                body = driver.find_element(By.TAG_NAME, 'body')
                body.send_keys(Keys.ESCAPE)
                print("Sent ESC key to close popup")
                time.sleep(1)
        except Exception:
            pass

        # Wait longer for dynamic content to load
        time.sleep(6)
        print("Scrolling player list container to load more data...")
        max_scrolls = 40
        last_row_count = 0
        container = None
        # Use the provided class for the scrollable container
        try:
            container = driver.find_element(By.CSS_SELECTOR, '.table-overflow--is-scrollable-vertical.props-table')
            print("Found scrollable container with class 'table-overflow--is-scrollable-vertical props-table'")
        except Exception:
            print("Could not find scrollable player list container, defaulting to page scroll.")
            container = None

        for i in range(max_scrolls):
            try:
                if container:
                    driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight;", container)
                else:
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                print(f"Scroll {i+1}/{max_scrolls}...")
                time.sleep(15)
                table = driver.find_element(By.CSS_SELECTOR, 'table')
                rows = table.find_elements(By.TAG_NAME, "tr")
                if len(rows) == last_row_count:
                    print("No new rows loaded, stopping scroll.")
                    break
                last_row_count = len(rows)
            except Exception:
                print("Table not found during scrolling.")
                break

        print("Extracting prop bet data...")
        today_date = datetime.now().strftime('%Y-%m-%d')
        os.makedirs('Data', exist_ok=True)

        prop_bets = []

        # Try more specific selector for prop bet table
        try:
            table = driver.find_element(By.CSS_SELECTOR, 'table')
            headers = [th.text.strip().lower() for th in table.find_elements(By.TAG_NAME, "th")]
            if 'player' in headers or 'name' in headers:
                rows = table.find_elements(By.TAG_NAME, "tr")[1:]  # skip header
                for row in rows:
                    cells = row.find_elements(By.TAG_NAME, "td")
                    if len(cells) >= 5:
                        # Split player cell into name, position, matchup
                        player_raw = cells[0].text.strip()
                        player_name, position, matchup = '', '', ''
                        try:
                            parts = player_raw.split('\n')
                            if len(parts) >= 3:
                                player_name = parts[0].strip()
                                position = parts[1].strip()
                                matchup = parts[2].replace('- ', '').strip()
                            elif len(parts) == 2:
                                player_name = parts[0].strip()
                                position = parts[1].strip()
                        except Exception:
                            player_name = player_raw
                        # Remove line breaks from bet_type and line columns
                        bet_type = ' '.join(cells[1].text.strip().splitlines())
                        line = ' '.join(cells[2].text.strip().splitlines())
                        odds = ' '.join(cells[3].text.strip().splitlines())
                        sportsbook = cells[4].text.strip()
                        prop_bets.append({
                            'player_name': player_name,
                            'position': position,
                            'matchup': matchup,
                            'bet_type': bet_type,
                            'line': line,
                            'odds': odds,
                            'sportsbook': sportsbook,
                            'date_scraped': today_date
                        })
        except Exception as e:
            print(f"Table not found or error extracting rows: {e}")

        if prop_bets:
            df = pd.DataFrame(prop_bets)
            filename = f'Data/bettingpros_prop_bets_{today_date}.csv'
            df.to_csv(filename, index=False)
            print(f"\n✅ Successfully scraped {len(df)} prop bets")
            print(f"📄 Data saved to {filename}")
            print(f"📅 Data scraped on: {today_date}")
            print(f"\nTop 5 prop bets:")
            print(df.head())
            return df
        else:
            print("❌ No prop bet data found")
            return None

    except Exception as e:
        print(f"❌ Error occurred: {e}")
        return None
    finally:
        driver.quit()
        print("\nBrowser closed")

if __name__ == "__main__":
    scrape_bettingpros_prop_bets()
