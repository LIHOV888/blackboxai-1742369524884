from flask import Flask, request, jsonify, send_from_directory
import os
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import json
from datetime import datetime
import time
from threading import Thread
import re
import logging
import traceback
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder='static', static_url_path='')

# Serve static files
@app.route('/')
def root():
    return app.send_static_file('index.html')

# API endpoints
@app.route('/api/scrape', methods=['POST'])
def start_scraping():
    init_scraper()
    data = request.json
    url = data.get('url')
    
    if not url:
        return jsonify({'error': 'URL is required'}), 400
    
    try:
        resources = scraper.start_scraping(url)
        return jsonify({'resources': resources})
    except Exception as e:
        logger.error(f"Scraping error: {str(e)}\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/download', methods=['POST'])
def start_download():
    init_scraper()
    data = request.json
    resources = data.get('resources', [])
    
    if not resources:
        return jsonify({'error': 'No resources provided'}), 400
    
    # Start download in a separate thread
    thread = Thread(target=scraper.start_download, args=(resources,))
    thread.start()
    scraper.download_thread = thread
    
    return jsonify({'status': 'Download started'})

@app.route('/api/stop-scraping', methods=['POST'])
def stop_scraping():
    init_scraper()
    scraper.stop_scraping()
    return jsonify({'status': 'Scraping stopped'})

@app.route('/api/stop-download', methods=['POST'])
def stop_download():
    init_scraper()
    scraper.stop_download()
    return jsonify({'status': 'Download stopped'})

@app.route('/api/status')
def get_status():
    init_scraper()
    return jsonify(scraper.get_status())

# Initialize the scraper
scraper = None

def init_scraper():
    global scraper
    if scraper is None:
        scraper = FreepikScraper()

class FreepikScraper:
    def __init__(self):
        self.session = requests.Session()
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Cache-Control': 'max-age=0'
        }
        self.download_status = {
            'total': 0,
            'current': 0,
            'speed': '0 KB/s',
            'status': 'Ready'
        }
        self.is_scraping = False
        self.is_downloading = False
        self.resources = []
        self.download_thread = None

    def start_scraping(self, url):
        self.is_scraping = True
        self.download_status['status'] = 'Scraping'
        logger.info(f"Starting scraping from URL: {url}")
        
        try:
            # Set up Chrome options
            chrome_options = Options()
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            
            # Create a new Chrome driver
            driver = webdriver.Chrome(options=chrome_options)
            
            try:
                # Load the page
                driver.get(url)
                logger.info("Page loaded successfully")
                
                # Wait for the content to load
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CLASS_NAME, "list-content"))
                )
                
                # Get the page source after JavaScript has rendered
                page_source = driver.page_source
                soup = BeautifulSoup(page_source, 'html.parser')
                
                # Find all resource cards
                resource_cards = soup.find_all('div', {'class': 'list-content__item'})
                logger.info(f"Found {len(resource_cards)} resource cards")
                
                resources = []
                for card in resource_cards:
                    try:
                        # Get the download link
                        download_link = card.find('a', {'class': 'list-content__link'})
                        if not download_link:
                            continue
                            
                        # Get the title
                        title_elem = card.find('p', {'class': 'title'})
                        title = title_elem.text.strip() if title_elem else ''
                        
                        # Get the image
                        img_elem = card.find('img')
                        img_url = img_elem.get('data-src') if img_elem else ''
                        
                        resource = {
                            'url': urljoin('https://www.freepik.com', download_link.get('href', '')),
                            'title': title or 'untitled',
                            'type': 'photo',  # Since we're specifically searching for photos
                            'preview_url': img_url
                        }
                        
                        resources.append(resource)
                        logger.info(f"Added resource: {resource['title']}")
                        
                    except Exception as e:
                        logger.error(f"Error processing card: {str(e)}")
                        continue
                
                self.resources = resources
                self.download_status['total'] = len(resources)
                logger.info(f"Successfully extracted {len(resources)} resources")
                
                return resources
                
            finally:
                driver.quit()
                
        except Exception as e:
            logger.error(f"Error during scraping: {str(e)}\n{traceback.format_exc()}")
            self.download_status['status'] = f'Error: {str(e)}'
            return []
        finally:
            self.is_scraping = False

    def start_download(self, resources, output_dir='downloads'):
        self.is_downloading = True
        self.download_status['status'] = 'Downloading'
        os.makedirs(output_dir, exist_ok=True)

        try:
            for idx, resource in enumerate(resources, 1):
                if not self.is_downloading:
                    break

                self.download_status['current'] = idx
                start_time = time.time()

                logger.info(f"Downloading resource {idx}/{len(resources)}: {resource['title']}")

                try:
                    # Download the preview image first (it's guaranteed to be accessible)
                    if resource['preview_url']:
                        response = self.session.get(resource['preview_url'], stream=True, headers=self.headers)
                        response.raise_for_status()

                        # Generate filename
                        filename = f"{resource['title']}_{idx}.jpg"
                        filename = "".join(c for c in filename if c.isalnum() or c in (' ', '-', '_', '.')).rstrip()
                        filepath = os.path.join(output_dir, filename)

                        total_size = int(response.headers.get('content-length', 0))
                        block_size = 1024
                        downloaded = 0

                        with open(filepath, 'wb') as f:
                            for data in response.iter_content(block_size):
                                if not self.is_downloading:
                                    break
                                
                                downloaded += len(data)
                                f.write(data)

                                elapsed = time.time() - start_time
                                if elapsed > 0:
                                    speed = downloaded / (1024 * elapsed)
                                    self.download_status['speed'] = f'{speed:.1f} KB/s'

                        logger.info(f"Successfully downloaded: {filename}")

                except Exception as e:
                    logger.error(f"Error downloading resource {idx}: {str(e)}")
                    continue

                if not self.is_downloading:
                    self.download_status['status'] = 'Stopped'
                    break

        except Exception as e:
            logger.error(f"Error during download: {str(e)}")
            self.download_status['status'] = f'Error: {str(e)}'
        finally:
            self.is_downloading = False
            if self.download_status['status'] != 'Stopped':
                self.download_status['status'] = 'Complete'

    def stop_scraping(self):
        self.is_scraping = False
        self.download_status['status'] = 'Stopped'

    def stop_download(self):
        self.is_downloading = False
        self.download_status['status'] = 'Stopped'

    def get_status(self):
        return self.download_status

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)