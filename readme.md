# Fantasy Football Draft Analysis Tools

A collection of Python scripts to scrape and analyze fantasy football draft data from ESPN and Boris Chen's tier rankings.

## Overview

This project provides automated web scraping tools to collect:
- **ESPN Live Draft Trends** - Real-time ADP (Average Draft Position) data with 7-day changes
- **Boris Chen Tier Rankings** - Expert consensus rankings for Standard, PPR, and Half-PPR scoring formats

All data is saved with timestamps for historical tracking and trend analysis.

## Features

- 📊 Scrapes ESPN's live draft results across all pages (250+ players)
- 📈 Downloads Boris Chen's tier rankings for all scoring formats
- 📅 Automatically timestamps all data for historical tracking
- 💾 Saves data in CSV format for easy analysis
- 🔄 Handles pagination automatically
- 🛡️ Includes error handling and retry logic

## Requirements

- Python 3.7+
- Chrome browser installed
- ChromeDriver (automatically managed by Selenium)

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/fantasy-draft-analysis.git
cd fantasy-draft-analysis