from flask import Flask, request, jsonify, send_from_directory
import os
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
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
from selenium.common.exceptions import TimeoutException, NoSuchElementException

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
        self.max_retries = 3
        self.retry_delay = 2

    def is_profile_url(self, url):
        """Check if the URL is a profile URL"""
        parsed = urlparse(url)
        path_parts = parsed.path.strip('/').split('/')
        return len(path_parts) >= 2 and path_parts[0] == 'author'

    def get_chrome_driver(self):
        """Set up and return a Chrome driver with optimal settings"""
        from selenium.webdriver.chrome.service import Service
        
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--disable-notifications')
        chrome_options.add_argument('--disable-popup-blocking')
        chrome_options.binary_location = '/usr/bin/chromium-browser'
        
        # Add additional headers
        chrome_options.add_argument(f'user-agent={self.headers["User-Agent"]}')
        
        # Create and configure ChromeDriver service
        service = Service(executable_path='/usr/bin/chromedriver')
        
        try:
            # Initialize and return ChromeDriver with service
            driver = webdriver.Chrome(service=service, options=chrome_options)
            return driver
        except Exception as e:
            logger.error(f"Failed to initialize Chrome driver: {str(e)}")
            raise

    def wait_for_element(self, driver, selector, by=By.CSS_SELECTOR, timeout=10):
        """Wait for an element to be present and visible"""
        try:
            element = WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((by, selector))
            )
            return element
        except TimeoutException:
            logger.error(f"Timeout waiting for element: {selector}")
            return None

    def scroll_page(self, driver, pause_time=1):
        """Scroll the page to load all content"""
        last_height = driver.execute_script("return document.body.scrollHeight")
        
        while True:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(pause_time)
            
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height

    def extract_resources_from_profile(self, driver, soup):
        """Extract resources from a profile page"""
        resources = []
        resource_cards = soup.find_all('article', {'class': 'showcase__item'})
        
        for card in resource_cards:
            try:
                # Get the download link
                download_link = card.find('a', {'class': 'showcase__link'})
                if not download_link:
                    continue
                    
                # Get the title
                title_elem = card.find('p', {'class': 'title'})
                title = title_elem.text.strip() if title_elem else ''
                
                # Get the image
                img_elem = card.find('img')
                img_url = img_elem.get('data-src') or img_elem.get('src') if img_elem else ''
                
                resource = {
                    'url': urljoin('https://www.freepik.com', download_link.get('href', '')),
                    'title': title or 'untitled',
                    'type': 'resource',
                    'preview_url': img_url
                }
                
                resources.append(resource)
                logger.info(f"Added resource from profile: {resource['title']}")
                
            except Exception as e:
                logger.error(f"Error processing profile card: {str(e)}")
                continue
                
        return resources

    def extract_resources_from_listing(self, driver, soup):
        """Extract resources from a listing page"""
        resources = []
        resource_cards = soup.find_all('div', {'class': 'list-content__item'})
        
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
                img_url = img_elem.get('data-src') or img_elem.get('src') if img_elem else ''
                
                resource = {
                    'url': urljoin('https://www.freepik.com', download_link.get('href', '')),
                    'title': title or 'untitled',
                    'type': 'resource',
                    'preview_url': img_url
                }
                
                resources.append(resource)
                logger.info(f"Added resource from listing: {resource['title']}")
                
            except Exception as e:
                logger.error(f"Error processing listing card: {str(e)}")
                continue
                
        return resources

    def start_scraping(self, url):
        self.is_scraping = True
        self.download_status['status'] = 'Scraping'
        logger.info(f"Starting scraping from URL: {url}")
        
        driver = None
        try:
            driver = self.get_chrome_driver()
            
            # Load the page with retry logic
            for attempt in range(self.max_retries):
                try:
                    driver.get(url)
                    break
                except Exception as e:
                    if attempt == self.max_retries - 1:
                        raise
                    time.sleep(self.retry_delay)
            
            logger.info("Page loaded successfully")
            
            # Wait for content to load based on URL type
            if self.is_profile_url(url):
                self.wait_for_element(driver, 'article.showcase__item')
            else:
                self.wait_for_element(driver, 'div.list-content__item')
            
            # Scroll to load all content
            self.scroll_page(driver)
            
            # Get the page source after JavaScript has rendered
            page_source = driver.page_source
            soup = BeautifulSoup(page_source, 'html.parser')
            
            # Extract resources based on URL type
            if self.is_profile_url(url):
                resources = self.extract_resources_from_profile(driver, soup)
            else:
                resources = self.extract_resources_from_listing(driver, soup)
            
            self.resources = resources
            self.download_status['total'] = len(resources)
            logger.info(f"Successfully extracted {len(resources)} resources")
            
            return resources
            
        except Exception as e:
            logger.error(f"Error during scraping: {str(e)}\n{traceback.format_exc()}")
            self.download_status['status'] = f'Error: {str(e)}'
            return []
        finally:
            if driver:
                driver.quit()
            self.is_scraping = False

    def download_file(self, url, filepath, resource_type='preview'):
        """Download a file with retry logic"""
        for attempt in range(self.max_retries):
            try:
                response = self.session.get(url, stream=True, headers=self.headers)
                response.raise_for_status()
                
                total_size = int(response.headers.get('content-length', 0))
                block_size = 8192
                downloaded = 0
                start_time = time.time()

                with open(filepath, 'wb') as f:
                    for data in response.iter_content(block_size):
                        if not self.is_downloading:
                            return False
                        
                        downloaded += len(data)
                        f.write(data)

                        elapsed = time.time() - start_time
                        if elapsed > 0:
                            speed = downloaded / (1024 * elapsed)
                            self.download_status['speed'] = f'{speed:.1f} KB/s'

                return True
                
            except Exception as e:
                logger.error(f"Download attempt {attempt + 1} failed: {str(e)}")
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)
                else:
                    raise

    def start_download(self, resources, output_dir='downloads'):
        self.is_downloading = True
        self.download_status['status'] = 'Downloading'
        os.makedirs(output_dir, exist_ok=True)

        try:
            for idx, resource in enumerate(resources, 1):
                if not self.is_downloading:
                    break

                self.download_status['current'] = idx
                logger.info(f"Downloading resource {idx}/{len(resources)}: {resource['title']}")

                try:
                    # Generate filename
                    filename = f"{resource['title']}_{idx}"
                    filename = "".join(c for c in filename if c.isalnum() or c in (' ', '-', '_', '.')).rstrip()
                    
                    # Download preview image
                    if resource['preview_url']:
                        preview_filepath = os.path.join(output_dir, f"{filename}_preview.jpg")
                        if self.download_file(resource['preview_url'], preview_filepath, 'preview'):
                            logger.info(f"Successfully downloaded preview: {filename}")
                    
                    # Try to download the actual resource
                    if resource['url']:
                        resource_filepath = os.path.join(output_dir, f"{filename}.jpg")
                        if self.download_file(resource['url'], resource_filepath, 'resource'):
                            logger.info(f"Successfully downloaded resource: {filename}")

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
    app.run(host='0.0.0.0', port=8000, debug=True)
