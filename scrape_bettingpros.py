import pandas as pd
import time
import os
import traceback
import re
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import logging

# Configure module logger
logging.basicConfig(level=os.getenv('LOG_LEVEL', 'INFO'), format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger('scrape_bettingpros')


def scrape_bettingpros_prop_bets():
    """Scrape BettingPros NFL prop bets into CSV."""
    chrome_options = Options()
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--window-size=1366,1200')
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    headless = os.getenv("HEADLESS", "true").lower() in ("1", "true", "yes")
    if headless:
        chrome_options.add_argument("--headless=new")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    try:
        driver.set_window_size(1366, 1200)
    except Exception:
        pass

    today_date = datetime.now().strftime('%Y-%m-%d')
    os.makedirs('Data', exist_ok=True)

    # timing / counters
    run_start = time.perf_counter()
    total_new_rows = 0
    logger.info(f"Starting BettingPros scrape (HEADLESS={headless}) — output dir=Data, date={today_date}")

    try:
        driver.get("https://www.bettingpros.com/nfl/picks/prop-bets/")
        time.sleep(3)

        # Minimal popup dismissal heuristics
        def click_if_text_button(txts):
            try:
                buttons = driver.find_elements(By.TAG_NAME, 'button')
                for b in buttons:
                    try:
                        if not b.is_displayed():
                            continue
                        t = (b.text or '').strip().lower()
                        for want in txts:
                            if want in t:
                                b.click()
                                return True
                    except Exception:
                        continue
            except Exception:
                pass
            return False

        click_if_text_button(['accept', 'accept all', 'accept cookies', 'got it', 'dismiss', 'no thanks'])

        # Aggressive JS overlay removal (best-effort)
        try:
            js = """
            Array.from(document.querySelectorAll('div, section, aside')).forEach(function(el){
              try{
                var s = window.getComputedStyle(el);
                if ((s.position==='fixed' || s.position==='absolute') && el.offsetHeight>50 && el.offsetWidth>50) el.remove();
              }catch(e){}
            });
            """
            driver.execute_script(js)
            logger.debug("Executed overlay removal JS")
        except Exception:
            logger.debug("Overlay removal JS failed", exc_info=True)

        time.sleep(int(os.getenv('POST_POPUP_WAIT', '4')))

        candidate_table_selectors = [
            '.table-overflow--is-scrollable-vertical.props-table table',
            'table.table.table--is-striped',
            'table'
        ]

        def find_scrollable_container():
            selectors = ['.table-overflow--is-scrollable-vertical.props.table', '.table-overflow--is-scrollable-vertical.props-table', '.table-overflow.props-table', '.pbcs-table__wrapper']
            for sel in selectors:
                try:
                    el = driver.find_element(By.CSS_SELECTOR, sel)
                    client_h = driver.execute_script('return arguments[0].clientHeight;', el)
                    scroll_h = driver.execute_script('return arguments[0].scrollHeight;', el)
                    if scroll_h > client_h + 10:
                        logger.debug(f"Found scrollable container by selector {sel} (client_h={client_h}, scroll_h={scroll_h})")
                        return el
                except Exception:
                    continue
            # JS fallback: any scrollable div
            try:
                el = driver.execute_script("""
                var els = Array.from(document.querySelectorAll('div, section'));
                for (var i=0;i<els.length;i++){
                  var s = window.getComputedStyle(els[i]);
                  if ((s.overflowY=='auto' || s.overflowY=='scroll') && els[i].scrollHeight>els[i].clientHeight+10) return els[i];
                }
                return null;
                """)
                if el:
                    logger.debug("Found scrollable container via JS fallback")
                return el
            except Exception:
                return None

        def parse_table_to_list(table_el):
            """Robust table parser: map headers to columns, prefer cells matching patterns, and fall back to scanning row cells and buttons for line/odds and player name."""
            props = []
            try:
                headers = [th.text.strip().lower() for th in table_el.find_elements(By.TAG_NAME, 'th')]
            except Exception:
                headers = []
            try:
                rows = table_el.find_elements(By.TAG_NAME, 'tr')
            except Exception:
                rows = []

            # Build header map by keywords
            header_map = {}
            for i, h in enumerate(headers):
                if 'player' in h or 'name' in h:
                    header_map['player'] = i
                elif 'prop' in h or 'bet' in h or 'type' in h:
                    header_map['bet_type'] = i
                elif 'line' in h or 'o/u' in h or 'over' in h or 'under' in h:
                    header_map['line'] = i
                elif 'odd' in h or 'odds' in h:
                    header_map['odds'] = i

            start = 1 if rows and headers else 0

            for row in rows[start:]:
                try:
                    cells = row.find_elements(By.TAG_NAME, 'td')
                    # helper to safely read cell text
                    def ct(idx):
                        try:
                            return cells[idx].text.strip()
                        except Exception:
                            return ''

                    # Primary reads using header mapping
                    player_raw = ct(header_map.get('player', 0))
                    bet_raw = ct(header_map.get('bet_type', 1))
                    line_raw = ct(header_map.get('line', 2))
                    odds_raw = ct(header_map.get('odds', 3))

                    # If player_raw looks like junk (percent/no letters), try to find the first cell with letters
                    def first_alpha_cell():
                        for c in cells:
                            try:
                                t = c.text.strip()
                                if t and re.search(r'[A-Za-z]', t):
                                    return t
                            except Exception:
                                continue
                        return ''

                    if (not player_raw) or re.search(r'\d+%', player_raw) or not re.search(r'[A-Za-z]', player_raw):
                        alt = first_alpha_cell()
                        if alt:
                            player_raw = alt

                    # If odds_raw missing, scan row cells for parentheses or button text
                    if not odds_raw:
                        # look for parentheses in any cell
                        for c in cells:
                            try:
                                t = c.text or ''
                                m = re.search(r'\(([^)]+)\)', t)
                                if m:
                                    odds_raw = m.group(1).strip()
                                    break
                            except Exception:
                                continue
                        # fallback: look for button text inside the row
                        if not odds_raw:
                            try:
                                btns = row.find_elements(By.XPATH, ".//button")
                                for b in btns:
                                    try:
                                        bt = (b.text or '').strip()
                                        m = re.search(r'\(([^)]+)\)', bt)
                                        if m:
                                            odds_raw = m.group(1).strip()
                                            # also consider bet text from button (e.g., 'O 220.5')
                                            if not line_raw or not re.search(r'[ou]\s*\d', line_raw, re.I):
                                                # try to extract O/U and value
                                                m2 = re.search(r'\b([OUou])\s*([\d\.]+)', bt)
                                                if m2:
                                                    line_raw = (m2.group(1) + ' ' + m2.group(2)).strip()
                                            break
                                    except Exception:
                                        continue
                            except Exception:
                                pass

                    # If line_raw missing, scan cells/buttons for o/u or numeric patterns
                    if not line_raw or not re.search(r'[ou]\s*\d', line_raw, re.I):
                        found = ''
                        for c in cells:
                            try:
                                t = c.text or ''
                                if re.search(r'[ou]\s*\d', t, re.I) or re.search(r'\d+\.?\d*\s*(Pass|Rush|Rec|Yds|Yards|TD)', t, re.I):
                                    found = t.strip()
                                    break
                            except Exception:
                                continue
                        if not found:
                            try:
                                btns = row.find_elements(By.XPATH, ".//button")
                                for b in btns:
                                    try:
                                        bt = b.text or ''
                                        if re.search(r'[ou]\s*\d', bt, re.I) or re.search(r'\d+\.?\d*\s*(Pass|Rush|Rec|Yds|Yards|TD)', bt, re.I):
                                            found = bt.strip()
                                            break
                                    except Exception:
                                        continue
                            except Exception:
                                pass
                        if found:
                            line_raw = found

                    # parse player into name/position/matchup when possible
                    player_name = ''
                    position = ''
                    matchup = ''
                    try:
                        parts = player_raw.split('\n')
                        if parts:
                            player_name = parts[0].strip()
                        if len(parts) >= 2:
                            if re.search(r'\b(QB|RB|WR|TE|K|PK|DEF)\b', parts[1], re.I):
                                position = parts[1].strip()
                            else:
                                matchup = parts[1].strip()
                        if len(parts) >= 3:
                            matchup = parts[2].replace('- ', '').strip()
                    except Exception:
                        player_name = player_raw

                    # final normalization for odds and line
                    odds_val = ''
                    if odds_raw:
                        m_odds = re.search(r'\(([^)]+)\)', odds_raw)
                        if m_odds:
                            odds_val = m_odds.group(1).strip()
                        else:
                            odds_val = odds_raw.strip()

                    line_val = ''
                    bet_type_val = ''
                    if line_raw:
                        txt = re.sub(r'\([^)]*\)', '', line_raw).strip()
                        m = re.match(r'([ouOUn]?[\d\.\-]+)\s*(.*)', txt)
                        if m:
                            line_val = m.group(1).strip()
                            bet_type_val = m.group(2).strip()
                        else:
                            mn = re.search(r'([OUou]?\s*[\d\.]+)', txt)
                            if mn:
                                line_val = mn.group(1).strip()
                            bet_type_val = txt

                    # ensure we have a plausible player name (must contain letters)
                    if not player_name or not re.search(r'[A-Za-z]', player_name):
                        continue

                    props.append({
                        'player_name': player_name,
                        'position': position,
                        'matchup': matchup,
                        'bet_type': bet_type_val or bet_raw,
                        'line': line_val,
                        'odds': odds_val,
                        'sportsbook': '',
                        'date_scraped': today_date
                    })
                except Exception:
                    continue
            return props

        def parse_cards_fallback():
            candidates = []
            try:
                elems = driver.find_elements(By.CSS_SELECTOR, 'main div, .pbcs-content-container div, article, li')
            except Exception:
                elems = []
            patterns = re.compile(r'\b(pass|rush|receiv|rec|td|yards|yds|receptions|passing)\b', re.I)
            for el in elems:
                try:
                    txt = el.text.strip()
                    if not txt or not patterns.search(txt):
                        continue
                    lines = [l.strip() for l in txt.splitlines() if l.strip()]
                    # find bet line index
                    bet_idx = None
                    for i, l in enumerate(lines):
                        if re.search(r'[ou]\s*\d', l, re.I) or re.search(r'\d+\.?\d*\s*(Pass|Rush|Rec|Yds|Yards)', l, re.I):
                            bet_idx = i
                            break
                    if bet_idx is None or bet_idx == 0:
                        continue
                    # find player name above
                    player_name = None
                    for p in range(bet_idx-1, -1, -1):
                        cand = lines[p]
                        if len(cand) < 3:
                            continue
                        if any(x in cand.lower() for x in ['best nfl', 'prop bet', 'click to view', 'premium']):
                            continue
                        player_name = cand
                        break
                    if not player_name:
                        continue
                    bet_line = lines[bet_idx]
                    odds = ''
                    m = re.search(r'\(([^)]+)\)', bet_line)
                    if m:
                        odds = m.group(1).strip()
                    bet_text = re.sub(r'\([^)]*\)', '', bet_line).strip()
                    mm = re.match(r'([ouOUn]?[\d\.\-]+)\s*(.*)', bet_text)
                    line = ''
                    bet_type = bet_text
                    if mm:
                        line = mm.group(1).strip()
                        bet_type = mm.group(2).strip()
                    candidates.append({'player_name': player_name, 'position': '', 'matchup': '', 'bet_type': bet_type, 'line': line, 'odds': odds, 'sportsbook': '', 'date_scraped': today_date})
                except Exception:
                    continue
            # dedupe and filter
            seen = set()
            out = []
            for c in candidates:
                name = (c.get('player_name') or '').strip()
                # reject percent/junk names
                if not name or re.search(r'\d+%', name) or 'click to view' in name.lower() or not re.search(r'[A-Za-z]', name):
                    continue
                key = (name.lower(), c.get('bet_type','').strip().lower(), c.get('line','').strip(), c.get('odds','').strip())
                if key in seen:
                    continue
                seen.add(key)
                out.append(c)
            return out

        # scrolling loop
        container = find_scrollable_container()
        max_scrolls = int(os.getenv('MAX_SCROLLS', '40'))
        increment_wait = int(os.getenv('SCROLL_WAIT', '6'))
        prop_bets = []
        last_row_count = 0
        consecutive_no_growth = 0
        for i in range(max_scrolls):
            loop_start = time.perf_counter()
            try:
                if container:
                    client_h = driver.execute_script('return arguments[0].clientHeight;', container)
                    scroll_top = driver.execute_script('return arguments[0].scrollTop;', container)
                    scroll_height = driver.execute_script('return arguments[0].scrollHeight;', container)
                    next_top = scroll_top + client_h
                    if next_top + 60 >= scroll_height:
                        driver.execute_script('arguments[0].scrollTop = arguments[0].scrollHeight;', container)
                        time.sleep(increment_wait)
                    else:
                        driver.execute_script('arguments[0].scrollTop = arguments[1];', container, next_top)
                else:
                    driver.execute_script('window.scrollBy(0, Math.max(window.innerHeight*0.35, 300));')
                time.sleep(increment_wait)

                # attempt table parse
                table = None
                for sel in candidate_table_selectors:
                    try:
                        table = driver.find_element(By.CSS_SELECTOR, sel)
                        if table:
                            break
                    except Exception:
                        continue
                if table:
                    parse_start = time.perf_counter()
                    current = parse_table_to_list(table)
                    parse_elapsed = time.perf_counter() - parse_start
                    # merge dedupe
                    ek = set((p['player_name'].strip().lower(), p['bet_type'].strip().lower(), p['line'].strip(), p['odds'].strip()) for p in prop_bets)
                    new = 0
                    for p in current:
                        # skip junk
                        if not p.get('player_name'):
                            continue
                        if (p['player_name'].strip().lower(), p['bet_type'].strip().lower(), p['line'].strip(), p['odds'].strip()) not in ek:
                            prop_bets.append(p)
                            ek.add((p['player_name'].strip().lower(), p['bet_type'].strip().lower(), p['line'].strip(), p['odds'].strip()))
                            new += 1
                    total_new_rows += new
                    loop_elapsed = time.perf_counter() - loop_start
                    # ensure we have row count for logging/growth checks
                    try:
                        rows = table.find_elements(By.TAG_NAME, 'tr') if table else []
                    except Exception:
                        rows = []
                    logger.info(f"Scroll {i+1}/{max_scrolls}: rows_on_table={len(rows) if table else 'N/A'}, new_added={new}, total_props={len(prop_bets)}, parse_time={parse_elapsed:.2f}s, loop_time={loop_elapsed:.2f}s")
                    if new:
                        # save partial cleaned
                        cleaned = [r for r in prop_bets if not re.search(r'\d+%', (r.get('player_name') or '')) and 'click to view' not in (r.get('player_name') or '').lower() and re.search(r'[A-Za-z]', (r.get('player_name') or ''))]
                        try:
                            pd.DataFrame(cleaned).to_csv(f'Data/bettingpros_prop_bets_{today_date}.csv', index=False)
                            logger.info(f"Saved partial cleaned CSV with {len(cleaned)} rows -> Data/bettingpros_prop_bets_{today_date}.csv")
                        except Exception:
                            logger.exception("Failed to save partial CSV")

                # stop conditions based on growth
                # rows already computed above when table was present; ensure it's defined
                try:
                    rows = rows if 'rows' in locals() else (table.find_elements(By.TAG_NAME, 'tr') if table else [])
                except Exception:
                    rows = []
                if len(rows) == last_row_count:
                    consecutive_no_growth += 1
                    if consecutive_no_growth >= 4:
                        logger.debug("No growth on table rows for several iterations, breaking scroll loop")
                        break
                else:
                    last_row_count = len(rows)
                    consecutive_no_growth = 0
            except Exception:
                logger.exception("Exception in scroll loop, aborting")
                break

        # after scrolling and incremental parsing, save debug artifacts if nothing was captured
        try:
            if not prop_bets:
                html_path = f'Data/debug_page_after_scroll_{today_date}.html'
                png_path = f'Data/debug_screenshot_after_scroll_{today_date}.png'
                try:
                    with open(html_path, 'w', encoding='utf-8') as f:
                        f.write(driver.page_source)
                    logger.info(f"Saved debug HTML to {html_path}")
                except Exception as e:
                    logger.exception(f"Failed saving debug HTML: {e}")
                try:
                    driver.save_screenshot(png_path)
                    logger.info(f"Saved debug screenshot to {png_path}")
                except Exception as e:
                    logger.exception(f"Failed saving debug screenshot: {e}")
        except Exception:
            logger.exception("Failed during debug artifact saving")

        # if collected nothing from table, try card fallback
        if not prop_bets:
            cards = parse_cards_fallback()
            if cards:
                prop_bets = cards

        # final cleaning/dedupe
        final = []
        seen = set()
        for p in prop_bets:
            try:
                name = (p.get('player_name') or '').strip()
                bet = (p.get('bet_type') or '').strip()
                line = (p.get('line') or '').strip()
                odds = (p.get('odds') or '').strip()
                if not name:
                    continue
                if re.search(r'\d+%', name) or 'click to view' in name.lower() or 'out of' in name.lower() or not re.search(r'[A-Za-z]', name):
                    continue
                key = (name.lower(), bet.lower(), line, odds)
                if key in seen:
                    continue
                seen.add(key)
                final.append({'player_name': name, 'position': p.get('position',''), 'matchup': p.get('matchup',''), 'bet_type': bet, 'line': line, 'odds': odds, 'date_scraped': today_date})
            except Exception:
                continue

        # If cleaning removed everything, try to salvage any raw rows that contain alphabetic player names
        if not final:
            salvage = [p for p in prop_bets if re.search(r'[A-Za-z]', (p.get('player_name') or ''))]
            if salvage:
                logger.info('No cleaned rows after filtering — salvaging raw extracted rows that contain letters.')
                final = salvage
            else:
                # save raw debug CSV so you can inspect what was extracted
                if prop_bets:
                    try:
                        pd.DataFrame(prop_bets).to_csv(f'Data/bettingpros_prop_bets_raw_{today_date}.csv', index=False)
                        logger.info(f"No salvageable rows; raw extraction saved to Data/bettingpros_prop_bets_raw_{today_date}.csv")
                    except Exception:
                        logger.exception("Failed saving raw extraction CSV")
                else:
                    logger.info('No prop_bets captured at all during extraction.')
                return None

        if final:
            df = pd.DataFrame(final)
            try:
                df.to_csv(f'Data/bettingpros_prop_bets_final_{today_date}.csv', index=False)
                logger.info(f"Saved final CSV with {len(df)} rows -> Data/bettingpros_prop_bets_final_{today_date}.csv")
            except Exception:
                logger.exception("Failed saving final CSV")
            total_elapsed = time.perf_counter() - run_start
            logger.info(f"Scrape complete: total_rows={len(df)}, total_new_rows_added={total_new_rows}, elapsed={total_elapsed:.2f}s")
            return df
        else:
            logger.info('No prop bets found')
            return None

    except Exception as e:
        logger.exception(f'Error during scrape: {e}')
        return None
    finally:
        try:
            driver.quit()
        except Exception:
            pass


if __name__ == '__main__':
    scrape_bettingpros_prop_bets()
